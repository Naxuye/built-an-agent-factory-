# filename: Nomos/core.py
# version: v1.0, python>=3.11
# ============================================================
# NOMOS 主进程入口
# 职责：初始化所有模块，连接工厂，启动 Telegram Bot
# ============================================================

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── 路径配置 ─────────────────────────────────────────────────
NOMOS_DIR   = Path(__file__).parent
WORKSPACE   = NOMOS_DIR.parent
AGENT_ROOT  = os.getenv("NAXUYE_WORKSPACE", str(WORKSPACE / "agent_factory"))

# 把项目根目录加入 Python 路径
sys.path.insert(0, str(WORKSPACE.parent))
sys.path.insert(0, str(WORKSPACE))

# ── 加载环境变量 ──────────────────────────────────────────────
dotenv_path = WORKSPACE.parent / ".env"
load_dotenv(dotenv_path, override=True)

# ── 日志配置 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(NOMOS_DIR / "nomos.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger("Nomos.Core")

logging.getLogger("httpx").setLevel(logging.WARNING)

# ── 模块导入 ──────────────────────────────────────────────────
from Nomos.broker import Broker
from Nomos.telegram import NomosBot

# ============================================================
# 工厂触发器
# ============================================================

async def factory_trigger(description: str):
    """
    触发 Naxuye 工厂生产新 Agent。
    生产完成后自动注册到 Nomos 注册表。
    """
    try:
        logger.info(f"[Core] 工厂触发: {description}")

        # 导入工厂主流程
        from langgraph_workflow import naxuye_app
        from Nomos.registry import load_registry
        import glob

        # 记录生产前的 agent 列表
        before = set(glob.glob(str(Path(AGENT_ROOT) / "*_SAFE_*")))

        # 运行工厂
        final_state = await naxuye_app.ainvoke({
            "input": description,
            "chat_history": [],
            "plan": {},
            "intelligence": "",
            "active_node": {},
            "draft": [],
            "passed_slots": [],
            "audit_report": {"score": 0, "advice": "", "error_type": "NONE"},
            "error_log": [],
            "retry_count": 0,
            "final_decision": "",
            "final_path": "",
            "target_components": [],
            "batch_retry_count": 0,
            "agent_name": "",
            "input_schema": {},
            "trigger_keywords": [],
            "test_cases": [],
        })

        # 找到新产出的 agent 目录
        after = set(glob.glob(str(Path(AGENT_ROOT) / "*_SAFE_*")))
        new_dirs = after - before

        # 统计新产出的 Agent（不注册，由 mindset 负责）
        registered = [Path(d).name for d in new_dirs]

        final_path = final_state.get("final_path", "未知路径")
        return {
            "success": True,
            "final_path": final_path,
            "registered": registered
        }

    except Exception as e:
        logger.error(f"[Core] 工厂触发失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def factory_trigger_with_push(description: str, push_callback):
    """工厂触发 + 结果推送"""
    result = await factory_trigger(description)
    if result["success"]:
        registered = result.get("registered", [])
        msg = (
            f"✅ <b>工厂生产完成</b>\n"
            f"归档路径: <code>{result['final_path']}</code>\n"
            f"已注册 Agent: {', '.join(registered) if registered else '无新注册'}"
        )
    else:
        msg = f"❌ <b>工厂生产失败</b>\n错误: {result.get('error', '未知错误')}"
    await push_callback(msg)

# ============================================================
# 主入口
# ============================================================

async def main():
    logger.info("=" * 50)
    logger.info("🚀 Nomos 启动中...")
    logger.info(f"工作空间: {WORKSPACE}")
    logger.info(f"Agent 仓库: {AGENT_ROOT}")
    logger.info("=" * 50)

    # 初始化 Broker（push 函数由 NomosBot 注入）
    broker = Broker(
        push=None,  # 由 NomosBot 注入
        factory_trigger=None  # 下面注入
    )

    # 初始化 Telegram Bot
    bot = NomosBot(broker=broker)

    # 注入工厂触发器（闭包捕获 push）
    async def _factory_trigger(description: str):
        await factory_trigger_with_push(description, bot.push)

    broker.factory_trigger = _factory_trigger

    logger.info("✅ Nomos 所有模块初始化完成")

    # 启动 Telegram Bot（阻塞）
    await bot.run()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())