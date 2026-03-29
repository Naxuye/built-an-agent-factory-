# filename: skills/__init__.py
# version: v1.0, python>=3.11
# 职责：Skill 注册表 + 自动发现 + 对外暴露统一查询接口
# ============================================================

import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("Skills")

# ============================================================
# Skill 注册表
# ============================================================

# 已注册的 skill 模块映射：name -> module
_registry: Dict[str, Any] = {}


def _auto_discover():
    """自动扫描 skills 目录下的所有 skill 模块"""
    global _registry
    if _registry:
        return  # 已加载过

    skills_dir = os.path.dirname(os.path.abspath(__file__))
    skip_files = {"__init__.py", "base.py", "manifest.json"}

    for filename in os.listdir(skills_dir):
        if filename.endswith(".py") and filename not in skip_files:
            module_name = filename.replace(".py", "")
            try:
                mod = __import__(f"skills.{module_name}", fromlist=["call"])
                if hasattr(mod, "call"):
                    _registry[module_name] = mod
                    logger.debug(f"[Skills] 已注册: {module_name}")
            except Exception as e:
                logger.warning(f"[Skills] 加载失败: {module_name} - {e}")


def get_skill(name: str):
    """获取指定 skill 模块"""
    _auto_discover()
    return _registry.get(name)


def list_skills() -> List[str]:
    """返回所有已注册的 skill 名称"""
    _auto_discover()
    return list(_registry.keys())


def get_manifest() -> Dict[str, Any]:
    """
    读取 manifest.json，返回所有 skill 的描述信息。
    供 Planner 和 agent_builder 使用。
    """
    manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[Skills] manifest.json 读取失败: {e}")
        return {}


def get_skill_prompt_section() -> str:
    """
    生成供 agent_builder prompt 使用的 skill 列表描述。
    告诉 LLM 有哪些 skill 可用、怎么调用。
    """
    manifest = get_manifest()
    skills = manifest.get("skills", [])

    if not skills:
        return ""

    lines = ["【可用 Skill 列表】（优先使用 skill，不要直接 import 第三方库）："]
    for s in skills:
        name = s.get("name", "")
        desc = s.get("description", "")
        usage = s.get("usage_example", "")
        params = ", ".join([f'{p["name"]}: {p["type"]}' for p in s.get("params", [])])
        lines.append(f"  - skills.{name}.call({params}) — {desc}")
        if usage:
            lines.append(f"    示例: {usage}")

    lines.append("  调用方式: from skills.{skill_name} import call")
    lines.append("  所有 skill 返回 dict: {{\"status\": \"success/failed\", \"result\": ..., \"error\": ...}}")
    return "\n".join(lines)