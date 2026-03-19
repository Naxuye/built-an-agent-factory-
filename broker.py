# filename: Nomos/broker.py
# version: v1.0, python>=3.11
# ============================================================
# NOMOS 消息中转器
# 职责：Request-Ack-Push 模式
#       收到指令立即回 Ack，异步执行，完成后主动推送结果
#       支持自然语言意图解析，自动匹配 Agent 和构造输入
# ============================================================

import os
import time
import asyncio
import logging
import json as _json
from typing import Dict, Any, Optional, Callable, Awaitable

from Nomos.command import CommandPacket, Command, get_help_text
from Nomos.registry import (
    get_agent, list_agents, register_agent,
    format_agent_list, match_agent_by_keyword
)
from Nomos.sandbox import run_agent, health_check

logger = logging.getLogger("Nomos.Broker")

PushCallback = Callable[[str], Awaitable[None]]

# ============================================================
# 自然语言意图解析
# ============================================================

async def _parse_intent(user_text: str, agent: dict) -> dict:
    """
    用 LLM 把用户的自然语言解析成 Agent 需要的 input_data。
    参考 agent_manifest 里的 input_schema。
    """
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from commander.api_router import smart_dispatch

        input_schema = agent.get("input_schema", {})
        components = agent.get("components", [])
        component_desc = ", ".join([c.get("file", "") for c in components])

        system_prompt = (
            "你是一个参数解析助手。根据用户的自然语言输入和 Agent 的输入规格，"
            "构造正确的 JSON 参数对象。\n"
            f"Agent 名称: {agent.get('name')}\n"
            f"Agent 组件: {component_desc}\n"
            f"输入规格参考: {_json.dumps(input_schema, ensure_ascii=False)}\n"
            "【要求】：只输出合法的 JSON 对象，不要任何解释，不要 Markdown。"
        )

        result = await smart_dispatch(
            prompt=f"用户输入：{user_text}",
            system_prompt=system_prompt,
            tier="BASE",
            json_mode=True
        )

        return _json.loads(result)
    except Exception as e:
        logger.warning(f"[Broker] 意图解析失败: {e}，使用原始文本")
        return {"input": user_text}


# ============================================================
# 消息中转核心
# ============================================================

class Broker:
    def __init__(self, push: PushCallback, factory_trigger: Optional[Callable] = None):
        self.push = push
        self.factory_trigger = factory_trigger
        self._tasks: Dict[str, asyncio.Task] = {}

    async def handle(self, packet: CommandPacket):
        ack_msg = self._build_ack(packet)
        await self.push(ack_msg)

        task = asyncio.create_task(self._dispatch(packet))
        task_key = f"{packet.command.name}_{time.time()}"
        self._tasks[task_key] = task
        task.add_done_callback(lambda t: self._tasks.pop(task_key, None))

    def _build_ack(self, packet: CommandPacket) -> str:
        cmd_name = packet.command.name
        agent = packet.agent_name or ""
        return (
            f"⚡ <b>[Nomos Ack]</b> 指令已收到\n"
            f"指令: <code>{cmd_name}</code>"
            f"{' | Agent: <code>' + agent + '</code>' if agent else ''}\n"
            f"正在处理，请稍候..."
        )

    async def _dispatch(self, packet: CommandPacket):
        try:
            cmd = packet.command
            if cmd == Command.HELP:
                await self.push(get_help_text())
            elif cmd == Command.LIST:
                await self.push(format_agent_list())
            elif cmd == Command.START:
                await self._handle_start(packet)
            elif cmd == Command.STATUS:
                await self._handle_status(packet)
            elif cmd == Command.STOP:
                await self._handle_stop(packet)
            elif cmd == Command.LOGS:
                await self._handle_logs(packet)
            elif cmd == Command.HOT_RELOAD:
                await self._handle_hot_reload(packet)
            elif cmd == Command.FACTORY:
                await self._handle_factory(packet)
            else:
                await self.push(f"⚠️ 指令 <code>{cmd.name}</code> 暂未实现")
        except Exception as e:
            logger.error(f"[Broker] 指令处理异常: {e}", exc_info=True)
            await self.push(f"❌ 执行出错: {str(e)}")

    async def _handle_start(self, packet: CommandPacket):
        name = packet.agent_name

        # 没有指定名字时，用关键词匹配
        if not name:
            name = match_agent_by_keyword(packet.args) if packet.args else None
        if not name:
            await self.push(
                "⚠️ 未找到匹配的 Agent。\n"
                "用法：<code>/start [agent_name] [输入内容或JSON]</code>\n"
                "或直接描述需求，例如：<code>/start 帮我查北京天气</code>\n"
                "发送 <code>/list</code> 查看所有可用 Agent。"
            )
            return

        agent = get_agent(name)
        if not agent:
            await self.push(f"❌ Agent <code>{name}</code> 未注册，发送 <code>/list</code> 查看可用 Agent")
            return

        await self.push(f"🚀 正在启动 <code>{name}</code>...")

        # ── 智能输入解析 ──────────────────────────────────────
        input_data = None

        # 1. 优先尝试直接 JSON 解析
        if packet.args:
            try:
                input_data = _json.loads(packet.args)
            except Exception:
                pass

        # 2. JSON 解析失败，用 LLM 解析自然语言
        if input_data is None and packet.args:
            await self.push("🧠 正在解析输入参数...")
            input_data = await _parse_intent(packet.args, agent)

        # 3. 没有任何输入，用空 dict
        if input_data is None:
            input_data = {}
        # ─────────────────────────────────────────────────────

        result = await run_agent(name, input_data)
        await self.push(result.format_telegram())

    async def _handle_status(self, packet: CommandPacket):
        name = packet.agent_name
        if not name:
            await self.push("⚠️ 请指定 Agent 名称，例如：<code>/status agent_name</code>")
            return

        await self.push(f"🔍 正在检测 <code>{name}</code> 健康状态...")
        result = await health_check(name)

        status = result.get("status", "unknown")
        icon = "🟢" if status == "healthy" else "🔴"
        msg = (
            f"{icon} <b>Agent 状态: {name}</b>\n"
            f"状态: <code>{status}</code>\n"
            f"时间戳: {result.get('timestamp', 'N/A')}"
        )
        if result.get("error"):
            msg += f"\n错误: {result['error']}"
        await self.push(msg)

    async def _handle_stop(self, packet: CommandPacket):
        name = packet.agent_name
        if not name:
            await self.push("⚠️ 请指定 Agent 名称")
            return
        from Nomos.registry import load_registry, save_registry
        registry = load_registry()
        if name in registry:
            registry[name]["status"] = "STOPPED"
            save_registry(registry)
            await self.push(f"🛑 Agent <code>{name}</code> 已标记为停止状态")
        else:
            await self.push(f"❌ Agent <code>{name}</code> 未注册")

    async def _handle_logs(self, packet: CommandPacket):
        name = packet.agent_name
        if not name:
            await self.push("⚠️ 请指定 Agent 名称")
            return

        agent = get_agent(name)
        if not agent:
            await self.push(f"❌ Agent <code>{name}</code> 未注册")
            return

        agent_path = agent.get("path", "")
        log_file = os.path.join(agent_path, "out", "agent.log")

        if not os.path.exists(log_file):
            await self.push(f"📭 <code>{name}</code> 暂无日志文件")
            return

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            last_lines = "".join(lines[-20:])
            await self.push(f"📋 <b>{name} 最近日志</b>\n<pre>{last_lines}</pre>")
        except Exception as e:
            await self.push(f"❌ 读取日志失败: {e}")

    async def _handle_hot_reload(self, packet: CommandPacket):
        name = packet.agent_name
        if not name:
            await self.push("⚠️ 请指定 Agent 名称")
            return

        agent = get_agent(name)
        if not agent:
            await self.push(f"❌ Agent <code>{name}</code> 未注册")
            return

        await self.push(f"🔄 正在热更新 <code>{name}</code>，将重新触发工厂生产...")

        if self.factory_trigger:
            description = f"重新构建 {name}"
            await self.factory_trigger(description)
        else:
            await self.push("⚠️ 工厂未连接，无法触发热更新")

    async def _handle_factory(self, packet: CommandPacket):
        description = packet.args
        if not description:
            await self.push(
                "⚠️ 请提供需求描述\n"
                "例如：<code>/factory 帮我写一个自动发邮件的agent</code>"
            )
            return

        await self.push(
            f"🏭 <b>工厂启动中</b>\n"
            f"需求：{description}\n"
            f"⏳ 生产需要几分钟，完成后自动推送结果..."
        )

        if self.factory_trigger:
            await self.factory_trigger(description)
        else:
            await self.push("⚠️ 工厂未连接，请确认 core.py 已正确初始化")