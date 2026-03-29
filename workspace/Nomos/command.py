# filename: nomos/command.py
# version: v1.0, python>=3.11
# ============================================================
# NOMOS 指令集枚举
# 职责：定义所有合法的远程指令，非法指令直接拦截
# ============================================================

import logging
import re
import time
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger("Nomos.Command")

# ============================================================
# 指令集定义
# ============================================================

class Command(Enum):
    START        = 0x01  # 唤醒/启动指定 Agent
    STATUS       = 0x02  # 查询 Agent 状态
    HOT_RELOAD   = 0x03  # 强制热更新/重新构建
    LIST         = 0x04  # 列出所有已注册 Agent
    STOP         = 0x05  # 停止指定 Agent
    LOGS         = 0x06  # 获取指定 Agent 最近日志
    HELP         = 0x07  # 显示帮助信息
    FACTORY      = 0x08  # 触发工厂生产新 Agent
    DELETE       = 0x09  # 删除指定 Agent（注销 + 清理文件）

# ============================================================
# 指令文本映射（Telegram 消息 → 指令枚举）
# ============================================================

# 支持的文本触发词
COMMAND_TEXT_MAP: Dict[str, Command] = {
    "/start":       Command.START,
    "/status":      Command.STATUS,
    "/reload":      Command.HOT_RELOAD,
    "/list":        Command.LIST,
    "/stop":        Command.STOP,
    "/logs":        Command.LOGS,
    "/help":        Command.HELP,
    "/factory":     Command.FACTORY,
    # 中文别名
    "启动":         Command.START,
    "状态":         Command.STATUS,
    "重载":         Command.HOT_RELOAD,
    "列表":         Command.LIST,
    "停止":         Command.STOP,
    "日志":         Command.LOGS,
    "帮助":         Command.HELP,
    "生产":         Command.FACTORY,
    "/delete":      Command.DELETE,
    "删除":         Command.DELETE,
}

# 每个指令的说明（用于 /help）
COMMAND_DESCRIPTIONS: Dict[Command, str] = {
    Command.START:      "0x01 启动指定 Agent，用法：/start [agent_name] [参数...]",
    Command.STATUS:     "0x02 查询 Agent 状态，用法：/status [agent_name]",
    Command.HOT_RELOAD: "0x03 热更新重构 Agent，用法：/reload [agent_name]",
    Command.LIST:       "0x04 列出所有已注册 Agent，用法：/list",
    Command.STOP:       "0x05 停止 Agent，用法：/stop [agent_name]",
    Command.LOGS:       "0x06 查看最近日志，用法：/logs [agent_name]",
    Command.HELP:       "0x07 显示帮助，用法：/help",
    Command.FACTORY:    "0x08 生产新 Agent，用法：/factory [需求描述]",
    Command.DELETE:     "0x09 删除 Agent，用法：/delete [agent_name]",
}

# ============================================================
# 指令解析器
# ============================================================

class CommandPacket:
    """解析后的指令数据包"""
    def __init__(self, command: Command, agent_name: Optional[str] = None, args: str = ""):
        self.command = command
        self.agent_name = agent_name
        self.args = args
        self.timestamp = time.time()

    def __repr__(self):
        return f"CommandPacket(cmd={self.command.name}, agent={self.agent_name}, args={self.args!r})"


def parse_message(text: str) -> Optional[CommandPacket]:
    """
    将 Telegram 消息文本解析为 CommandPacket。
    非法指令返回 None 并记录审计日志。
    """
    if not text or not text.strip():
        return None

    text = text.strip()
    parts = text.split(maxsplit=2)
    trigger = parts[0].lower()

    # 查找指令
    command = COMMAND_TEXT_MAP.get(trigger) or COMMAND_TEXT_MAP.get(parts[0])
    if command is None:
        logger.warning(f"[Nomos.Command] 非法指令拦截: {text!r}")
        return None

    # 提取 agent_name 和 args
    # FACTORY 指令：剩余全文作为需求描述
    if command == Command.FACTORY:
        args = " ".join(parts[1:]) if len(parts) > 1 else ""
        agent_name = None
    # START 指令：判断第二个词是否像 agent 名（snake_case，无空格连续词）
    # 如果像自然语言就整段作为 args 交给关键词匹配
    elif command == Command.START:
        second = parts[1] if len(parts) > 1 else ""
        rest = " ".join(parts[1:])
        # agent 名特征：纯英文/数字/下划线，且不含中文
        is_agent_name = bool(re.match(r'^[a-zA-Z0-9_]+$', second))
        if is_agent_name:
            agent_name = second
            args = parts[2] if len(parts) > 2 else ""
        else:
            agent_name = None
            args = rest
    else:
        agent_name = parts[1] if len(parts) > 1 else None
        args = parts[2] if len(parts) > 2 else ""

    packet = CommandPacket(command=command, agent_name=agent_name, args=args)
    logger.info(f"[Nomos.Command] 指令解析成功: {packet}")
    return packet


def get_help_text() -> str:
    """生成帮助文本"""
    lines = ["🤖 <b>Nomos 指令手册</b>\n"]
    for cmd, desc in COMMAND_DESCRIPTIONS.items():
        lines.append(f"• {desc}")
    lines.append("\n📌 agent_name 为注册表中的 Agent 名称，用 /list 查看所有可用 Agent。")
    return "\n".join(lines)