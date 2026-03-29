# filename: skills/json_parser.py
# version: v1.0, python>=3.11
# 职责：JSON 解析/转换/提取，容错处理 LLM 输出的非标准 JSON
# ============================================================

import re
import json
import time
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("Skills.JsonParser")


# ============================================================
# 对外接口
# ============================================================

async def call(
    action: str = "parse",
    text: str = "",
    data: Any = None,
    path: Optional[str] = None
) -> Dict[str, Any]:
    """
    JSON 处理工具。

    参数：
        action: 操作类型
            - "parse": 解析文本为 JSON（容错，自动清洗 markdown 标记）
            - "extract": 从 JSON 中按路径提取值（如 "data.items[0].name"）
            - "stringify": 将 dict/list 转为 JSON 字符串
            - "validate": 验证文本是否为合法 JSON
        text: 输入文本（parse/validate 时使用）
        data: 输入数据（extract/stringify 时使用）
        path: 提取路径（extract 时使用，如 "choices[0].message.content"）

    返回：
        {"status": "success", "result": ..., "timestamp": ...}
        {"status": "failed", "error": "...", "timestamp": ...}
    """
    try:
        if action == "parse":
            result = _parse_json(text)
            if result is None:
                return {"status": "failed", "error": "无法解析为 JSON", "timestamp": time.time()}
            return {"status": "success", "result": result, "timestamp": time.time()}

        elif action == "extract":
            if data is None:
                return {"status": "failed", "error": "extract 需要提供 data 参数", "timestamp": time.time()}
            if not path:
                return {"status": "failed", "error": "extract 需要提供 path 参数", "timestamp": time.time()}
            result = _extract_path(data, path)
            return {"status": "success", "result": result, "timestamp": time.time()}

        elif action == "stringify":
            if data is None:
                return {"status": "failed", "error": "stringify 需要提供 data 参数", "timestamp": time.time()}
            result = json.dumps(data, ensure_ascii=False, indent=2)
            return {"status": "success", "result": result, "timestamp": time.time()}

        elif action == "validate":
            is_valid, error = _validate_json(text)
            return {
                "status": "success",
                "result": {"valid": is_valid, "error": error},
                "timestamp": time.time()
            }

        else:
            return {
                "status": "failed",
                "error": f"不支持的 action: {action}，可选: parse/extract/stringify/validate",
                "timestamp": time.time()
            }

    except Exception as e:
        logger.error(f"[JsonParser] {action} 失败: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "timestamp": time.time()}


# ============================================================
# 内部实现
# ============================================================

def _parse_json(text: str) -> Any:
    """
    容错解析 JSON。
    处理 LLM 常见问题：markdown 包裹、多余逗号、单引号等。
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # 第一次：直接尝试
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 清洗 markdown 标记
    cleaned = text
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
        if "```" in cleaned:
            cleaned = cleaned.split("```", 1)[0]
    elif "```" in cleaned:
        cleaned = re.sub(r'```\w*\n?', '', cleaned)
        cleaned = cleaned.replace('```', '')
    cleaned = cleaned.strip()

    # 第二次：清洗后尝试
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # 尝试提取 {} 或 [] 区间
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = cleaned.find(start_char)
        if start_idx != -1:
            end_idx = cleaned.rfind(end_char)
            if end_idx > start_idx:
                fragment = cleaned[start_idx:end_idx + 1]
                try:
                    return json.loads(fragment)
                except (json.JSONDecodeError, ValueError):
                    pass

    # 尝试修复常见问题：尾部多余逗号
    fixed = re.sub(r',\s*([}\]])', r'\1', cleaned)
    try:
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        pass

    return None


def _extract_path(data: Any, path: str) -> Any:
    """
    按路径从嵌套 dict/list 中提取值。
    支持格式：choices[0].message.content
    """
    current = data
    # 拆分路径：支持 . 和 [N]
    parts = re.split(r'\.|\[(\d+)\]', path)
    parts = [p for p in parts if p is not None and p != '']

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, (list, tuple)):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None

        if current is None:
            return None

    return current


def _validate_json(text: str) -> tuple:
    """验证 JSON 合法性，返回 (is_valid, error_msg)"""
    if not text or not text.strip():
        return False, "空文本"
    try:
        json.loads(text.strip())
        return True, None
    except json.JSONDecodeError as e:
        return False, f"Line {e.lineno}, Col {e.colno}: {e.msg}"