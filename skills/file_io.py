# filename: skills/file_io.py
# version: v1.0, python>=3.11
# 职责：文件读写封装，路径安全校验，防止越权访问
# ============================================================

import os
import time
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Skills.FileIO")


# ============================================================
# 安全配置
# ============================================================

# 允许操作的根目录（agent 只能在自己的工作目录下读写）
# 运行时由 sandbox 通过环境变量注入
ALLOWED_ROOT = os.getenv("AGENT_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace"))

# 禁止访问的路径模式
BLOCKED_PATTERNS = [
    ".env", ".git", "__pycache__", ".ssh", ".aws",
    "naxuye_memory.db", "agent_map.json"
]


def _is_safe_path(filepath: str) -> bool:
    """检查路径是否在允许范围内"""
    abs_path = os.path.abspath(filepath)
    abs_root = os.path.abspath(ALLOWED_ROOT)

    # 必须在允许的根目录下
    if not abs_path.startswith(abs_root):
        return False

    # 不能包含敏感路径
    for pattern in BLOCKED_PATTERNS:
        if pattern in abs_path:
            return False

    return True


# ============================================================
# 对外接口
# ============================================================

async def call(
    action: str,
    path: str,
    content: str = "",
    encoding: str = "utf-8",
    as_json: bool = False
) -> Dict[str, Any]:
    """
    文件读写操作。

    参数：
        action: "read" / "write" / "append" / "exists" / "list_dir"
        path: 文件路径
        content: 写入内容（write/append 时必填）
        encoding: 编码
        as_json: 读取时是否解析为 JSON

    返回：
        {"status": "success", "result": ..., "timestamp": ...}
        {"status": "failed", "error": "...", "timestamp": ...}
    """
    if not path:
        return {"status": "failed", "error": "path 不能为空", "timestamp": time.time()}

    if not _is_safe_path(path):
        logger.warning(f"[FileIO] 路径安全拦截: {path}")
        return {
            "status": "failed",
            "error": f"路径不在允许范围内或包含敏感文件: {path}",
            "timestamp": time.time()
        }

    try:
        if action == "read":
            if not os.path.exists(path):
                return {"status": "failed", "error": f"文件不存在: {path}", "timestamp": time.time()}
            with open(path, "r", encoding=encoding) as f:
                data = f.read()
            if as_json:
                data = json.loads(data)
            return {"status": "success", "result": data, "timestamp": time.time()}

        elif action == "write":
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding=encoding) as f:
                f.write(content)
            return {"status": "success", "result": f"已写入 {len(content)} 字符", "timestamp": time.time()}

        elif action == "append":
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding=encoding) as f:
                f.write(content)
            return {"status": "success", "result": f"已追加 {len(content)} 字符", "timestamp": time.time()}

        elif action == "exists":
            exists = os.path.exists(path)
            return {"status": "success", "result": exists, "timestamp": time.time()}

        elif action == "list_dir":
            if not os.path.isdir(path):
                return {"status": "failed", "error": f"不是目录: {path}", "timestamp": time.time()}
            items = os.listdir(path)
            return {"status": "success", "result": items, "timestamp": time.time()}

        else:
            return {
                "status": "failed",
                "error": f"不支持的 action: {action}，可选: read/write/append/exists/list_dir",
                "timestamp": time.time()
            }

    except json.JSONDecodeError as e:
        return {"status": "failed", "error": f"JSON 解析失败: {e}", "timestamp": time.time()}
    except PermissionError:
        return {"status": "failed", "error": f"权限不足: {path}", "timestamp": time.time()}
    except Exception as e:
        logger.error(f"[FileIO] {action} 失败: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "timestamp": time.time()}