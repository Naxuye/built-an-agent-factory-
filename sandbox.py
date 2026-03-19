# filename: Nomos/sandbox.py
# version: v1.0, python>=3.11
# ============================================================
# NOMOS 进程沙箱管理器
# 职责：在独立进程中启动 Agent，实时监控资源占用
#       超时或内存溢出时从 OS 层面强制 kill
# ============================================================

import os
import sys
import time
import json
import logging
import asyncio
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None
    print("⚠️ [Sandbox] psutil 未安装，资源监控不可用。请运行: pip install psutil")

from Nomos.registry import get_agent, inject_env, update_run_stats

logger = logging.getLogger("Nomos.Sandbox")

# ============================================================
# 沙箱配置
# ============================================================

DEFAULT_TIMEOUT   = int(os.getenv("SANDBOX_TIMEOUT", "30"))      # 秒
MAX_MEMORY_MB     = int(os.getenv("SANDBOX_MAX_MEMORY_MB", "512"))  # MB
POLL_INTERVAL     = 0.5                                            # 资源监控轮询间隔（秒）

# ============================================================
# 运行结果结构
# ============================================================

class SandboxResult:
    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str = "",
        exit_code: int = -1,
        duration: float = 0.0,
        killed_reason: str = ""
    ):
        self.success = success
        self.output = output
        self.error = error
        self.exit_code = exit_code
        self.duration = duration
        self.killed_reason = killed_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration": round(self.duration, 2),
            "killed_reason": self.killed_reason,
            "timestamp": time.time()
        }

    def format_telegram(self) -> str:
        """格式化为 Telegram HTML 消息，自动转义输出内容"""
        import html
        icon = "✅" if self.success else "❌"
        lines = [f"{icon} <b>执行结果</b>"]
        lines.append(f"耗时: {self.duration:.2f}s")
        if self.output:
            preview = self.output[:500] + "..." if len(self.output) > 500 else self.output
            lines.append(f"输出:\n<pre>{html.escape(preview)}</pre>")
        if self.error:
            lines.append(f"错误: <code>{html.escape(self.error[:200])}</code>")
        if self.killed_reason:
            lines.append(f"⚠️ 终止原因: {self.killed_reason}")
        return "\n".join(lines)

# ============================================================
# 沙箱核心
# ============================================================

async def run_agent(name: str, input_data: Dict[str, Any]) -> SandboxResult:
    """
    在独立进程中启动指定 Agent，传入 input_data，返回执行结果。
    """
    # 1. 从注册表获取 Agent 信息
    agent = get_agent(name)
    if not agent:
        return SandboxResult(
            success=False,
            error=f"Agent '{name}' 未注册，拒绝执行",
            killed_reason="UNREGISTERED"
        )

    agent_path = agent.get("path", "")
    entry = agent.get("entry", "main.py")
    entry_file = os.path.join(agent_path, entry)

    if not os.path.exists(entry_file):
        return SandboxResult(
            success=False,
            error=f"入口文件不存在: {entry_file}",
            killed_reason="ENTRY_NOT_FOUND"
        )

    # 2. 注入环境变量
    env = os.environ.copy()
    injected = inject_env(name)
    env.update(injected)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

       # 3. 构造启动脚本（通过 stdin 传入 input_data）
    entry_module = entry.replace('.py', '')
    runner_script = f"""
import sys, json, asyncio
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, {repr(agent_path)})
input_data = json.loads(sys.stdin.read())
from {entry_module} import run
result = asyncio.run(run(input_data))
print(json.dumps(result, ensure_ascii=False))
"""

    input_json = json.dumps(input_data, ensure_ascii=False)
    start_time = time.time()
    process = None
    killed_reason = ""

    try:
        # 4. 启动子进程
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", runner_script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        logger.info(f"[Sandbox] Agent '{name}' 启动，PID: {process.pid}")

        # 5. 异步监控资源 + 等待完成
        stdout_data = b""
        stderr_data = b""

        async def _monitor():
            """监控资源占用，超时或内存溢出则 kill"""
            nonlocal killed_reason
            while True:
                await asyncio.sleep(POLL_INTERVAL)
                if process.returncode is not None:
                    break
                elapsed = time.time() - start_time
                if elapsed > DEFAULT_TIMEOUT:
                    killed_reason = f"TIMEOUT ({elapsed:.1f}s > {DEFAULT_TIMEOUT}s)"
                    logger.warning(f"[Sandbox] '{name}' 超时，强制 kill (PID: {process.pid})")
                    await _kill_process(process.pid)
                    break
                if psutil:
                    try:
                        proc = psutil.Process(process.pid)
                        mem_mb = proc.memory_info().rss / 1024 / 1024
                        if mem_mb > MAX_MEMORY_MB:
                            killed_reason = f"OOM ({mem_mb:.0f}MB > {MAX_MEMORY_MB}MB)"
                            logger.warning(f"[Sandbox] '{name}' 内存溢出，强制 kill")
                            await _kill_process(process.pid)
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break

        monitor_task = asyncio.create_task(_monitor())

        try:
            stdout_data, stderr_data = await process.communicate(
                input=input_json.encode('utf-8')
            )
        finally:
            monitor_task.cancel()

        duration = time.time() - start_time
        exit_code = process.returncode or 0

        if killed_reason:
            return SandboxResult(
                success=False,
                output=stdout_data.decode('utf-8', errors='replace'),
                error=stderr_data.decode('utf-8', errors='replace'),
                exit_code=exit_code,
                duration=duration,
                killed_reason=killed_reason
            )

        if exit_code != 0:
            return SandboxResult(
                success=False,
                output=stdout_data.decode('utf-8', errors='replace'),
                error=stderr_data.decode('utf-8', errors='replace'),
                exit_code=exit_code,
                duration=duration
            )

        # 6. 解析输出
        output_text = stdout_data.decode('utf-8', errors='replace').strip()
        update_run_stats(name)

        logger.info(f"[Sandbox] '{name}' 执行完成，耗时 {duration:.2f}s")
        return SandboxResult(
            success=True,
            output=output_text,
            exit_code=0,
            duration=duration
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[Sandbox] '{name}' 执行异常: {e}", exc_info=True)
        if process and process.returncode is None:
            await _kill_process(process.pid)
        return SandboxResult(
            success=False,
            error=str(e),
            duration=duration,
            killed_reason="EXCEPTION"
        )


async def _kill_process(pid: int):
    """从 OS 层面强制终止进程及其子进程"""
    try:
        if psutil:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.kill()
            logger.info(f"[Sandbox] PID {pid} 及其子进程已强制终止")
        else:
            # 降级：只 kill 主进程
            import signal
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        logger.error(f"[Sandbox] Kill PID {pid} 失败: {e}")


async def health_check(name: str) -> Dict[str, Any]:
    """
    调用 Agent 的 health() 接口检测存活状态。
    """
    agent = get_agent(name)
    if not agent:
        return {"status": "unregistered", "name": name}

    agent_path = agent.get("path", "")
    health_script = f"""
import sys, json, asyncio
sys.path.insert(0, {repr(agent_path)})
from main import health
result = asyncio.run(health())
print(json.dumps(result, ensure_ascii=False))
"""
    env = os.environ.copy()
    env.update(inject_env(name))

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", health_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        result = json.loads(stdout.decode('utf-8').strip())
        result["name"] = name
        return result
    except asyncio.TimeoutError:
        return {"status": "timeout", "name": name}
    except Exception as e:
        return {"status": "error", "name": name, "error": str(e)}