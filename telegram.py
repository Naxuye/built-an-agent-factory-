# filename: Nomos/telegram.py
# version: v1.0, python>=3.11
# ============================================================
# NOMOS Telegram 接入层
# 职责：接收 Telegram 消息，解析指令，推送结果
#       使用 polling 模式，不需要公网 IP
# ============================================================

import os
import logging
import asyncio
from typing import Optional

try:
    from telegram import Update, Bot
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters
    )
except ImportError:
    raise ImportError("请安装 python-telegram-bot：pip install python-telegram-bot")

from Nomos.command import parse_message, Command
from Nomos.broker import Broker

logger = logging.getLogger("Nomos.Telegram")

# ============================================================
# 配置
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ============================================================
# Telegram Bot
# ============================================================

class NomosBot:
    def __init__(self, broker: Broker):
        if not BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN 未配置，请检查 .env 文件")
        if not CHAT_ID:
            raise ValueError("TELEGRAM_CHAT_ID 未配置，请检查 .env 文件")

        self.broker = broker
        self.bot = Bot(token=BOT_TOKEN)
        self.app = Application.builder().token(BOT_TOKEN).build()
        self._setup_handlers()

        # 把推送函数注入到 broker
        self.broker.push = self.push

    def _setup_handlers(self):
        """注册所有消息处理器"""
        # 处理所有文本消息（包括 /command 和普通文本）
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )
        # 处理 / 开头的命令
        for cmd in ["start", "status", "reload", "list", "stop", "logs", "help", "factory"]:
            self.app.add_handler(CommandHandler(cmd, self._on_command))

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理普通文本消息"""
        if not self._is_authorized(update):
            return
        text = update.message.text or ""
        await self._process(text)

    async def _on_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /command 格式的指令"""
        if not self._is_authorized(update):
            return
        # 重建完整文本（含参数）
        text = update.message.text or ""
        await self._process(text)

    async def _process(self, text: str):
        """解析并分发指令"""
        packet = parse_message(text)
        if packet is None:
            await self.push(
                f"❓ 未识别的指令：`{text}`\n"
                f"发送 `/help` 查看所有可用指令。"
            )
            return
        await self.broker.handle(packet)

    def _is_authorized(self, update: Update) -> bool:
        """只允许指定 CHAT_ID 的用户操作"""
        user_id = str(update.effective_chat.id)
        if user_id != str(CHAT_ID):
            logger.warning(f"[Telegram] 未授权访问，chat_id: {user_id}")
            return False
        return True

    async def push(self, message: str):
        """主动推送消息到指定 chat（带重试机制）"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                max_len = 4000
                if len(message) <= max_len:
                    await self.bot.send_message(
                        chat_id=CHAT_ID,
                        text=message,
                        parse_mode="HTML"
                    )
                else:
                    chunks = [message[i:i+max_len] for i in range(0, len(message), max_len)]
                    for chunk in chunks:
                        await self.bot.send_message(
                            chat_id=CHAT_ID,
                            text=chunk,
                            parse_mode="HTML"
                        )
                        await asyncio.sleep(0.3)
                return  # 成功直接返回
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # 等2秒重试
                else:
                    logger.error(f"[Telegram] 推送失败（{max_retries}次重试后）: {e}")

    async def send_startup_message(self):
        """启动时发送上线通知"""
        from Nomos.registry import list_agents
        agents = list_agents()
        msg = (
            f"🟢 **Nomos 已上线**\n"
            f"已注册 Agent: {len(agents)} 个\n"
            f"发送 `/help` 查看指令手册\n"
            f"发送 `/list` 查看所有 Agent"
        )
        await self.push(msg)

    async def run(self):
        """启动 polling 模式（手动控制生命周期，避免事件循环冲突）"""
        logger.info("[Telegram] Nomos Bot 启动，polling 模式...")
        await self.send_startup_message()
        # 手动控制生命周期
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        while True:
            await asyncio.sleep(1)