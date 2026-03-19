# filename: Nomos/registry.py
# version: v1.0, python>=3.11
# ============================================================
# NOMOS 注册表管理器
# 职责：维护 agent_map.json，管理 Agent 户口本
#       只有注册表中的 Agent 才能获得 API Key 和执行权限
# ============================================================

import os
import json
import logging
import time
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger("Nomos.Registry")

# ============================================================
# 注册表路径
# ============================================================

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_map.json")

# ============================================================
# Agent 记录结构
# ============================================================

def _make_agent_record(
    name: str,
    path: str,
    version: str = "1.0.0",
    keywords: List[str] = None,
    entry: str = "main.py",
    quality_score: int = 0,
    provider: str = "UNKNOWN",
    components: List[Dict] = None,
    input_schema: Dict = None   # ← 新增参数
) -> Dict[str, Any]:
    return {
        "name": name,
        "path": path,
        "version": version,
        "entry": entry,
        "keywords": keywords or [],
        "quality_score": quality_score,
        "provider": provider,
        "components": components or [],
        "input_schema": input_schema or {"input": "str"},  # ← 新增字段
        "status": "READY",
        "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_run": None,
        "run_count": 0
    }

# ============================================================
# 注册表核心操作
# ============================================================

def load_registry() -> Dict[str, Any]:
    """读取注册表，不存在则初始化空表"""
    if not os.path.exists(REGISTRY_PATH):
        logger.info("[Registry] 注册表不存在，初始化空表")
        return {}
    try:
        with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[Registry] 读取注册表失败: {e}")
        return {}


def save_registry(registry: Dict[str, Any]) -> bool:
    """保存注册表到磁盘"""
    try:
        os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
            json.dump(registry, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"[Registry] 保存注册表失败: {e}")
        return False


def register_agent(manifest_path: str) -> bool:
    """
    从工厂产出的 agent_manifest.json 自动注册 Agent。
    由 mindset.py 落盘后调用。
    """
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        name = manifest.get("name", "unknown")
        agent_dir = os.path.dirname(manifest_path)

        registry = load_registry()

        record = _make_agent_record(
            name=name,
            path=agent_dir,
            version=manifest.get("version", "1.0.0"),
            keywords=manifest.get("trigger_keywords", []),
            entry=manifest.get("entry", "main.py"),
            quality_score=manifest.get("quality_score", 0),
            provider=manifest.get("provider", "UNKNOWN"),
            components=manifest.get("components", []),
            input_schema=manifest.get("input_schema", {"input": "str"})  # ← 新增
        )

        registry[name] = record
        success = save_registry(registry)

        if success:
            print(f"✅ [Registry] Agent '{name}' 已注册 | 路径: {agent_dir}")
        return success

    except Exception as e:
        logger.error(f"[Registry] 注册失败: {e}")
        return False


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    """获取指定 Agent 的注册信息"""
    registry = load_registry()
    agent = registry.get(name)
    if not agent:
        logger.warning(f"[Registry] Agent '{name}' 未注册")
    return agent


def list_agents() -> List[Dict[str, Any]]:
    """列出所有已注册 Agent"""
    registry = load_registry()
    return list(registry.values())


def unregister_agent(name: str) -> bool:
    """注销 Agent"""
    registry = load_registry()
    if name not in registry:
        logger.warning(f"[Registry] Agent '{name}' 不存在，无法注销")
        return False
    del registry[name]
    success = save_registry(registry)
    if success:
        print(f"🗑️ [Registry] Agent '{name}' 已注销")
    return success


def update_run_stats(name: str) -> bool:
    """更新 Agent 运行统计（last_run、run_count）"""
    registry = load_registry()
    if name not in registry:
        return False
    registry[name]["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    registry[name]["run_count"] = registry[name].get("run_count", 0) + 1
    return save_registry(registry)


def inject_env(name: str) -> Dict[str, str]:
    """
    为指定 Agent 动态注入环境变量。
    只有注册表中的 Agent 才能获得 API Key。
    返回注入的环境变量字典，由 sandbox 传给子进程。
    """
    agent = get_agent(name)
    if not agent:
        logger.warning(f"[Registry] Agent '{name}' 未注册，拒绝注入环境变量")
        return {}

    # 从主进程环境变量中提取允许注入的 Key
    allowed_keys = [
        "DASHSCOPE_API_KEY",
        "DEEPSEEK_API_KEY",
        "ZHIPUAI_API_KEY",
        "CHAOSUAN_API_KEY",
        "TAVILY_API_KEY",
        "NAXUYE_WORKSPACE",
        "SANDBOX_PATH",
    ]

    env = {}
    for key in allowed_keys:
        val = os.getenv(key)
        if val:
            env[key] = val

    logger.info(f"[Registry] 为 '{name}' 注入 {len(env)} 个环境变量")
    return env


def match_agent_by_keyword(text: str) -> Optional[str]:
    """
    根据关键词匹配最合适的 Agent 名称。
    供管家自动路由使用。
    """
    registry = load_registry()
    text_lower = text.lower()

    best_match = None
    best_score = 0

    for name, record in registry.items():
        keywords = record.get("keywords", [])
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > best_score:
            best_score = score
            best_match = name

    if best_match:
        logger.info(f"[Registry] 关键词匹配成功: '{best_match}' (得分: {best_score})")
    else:
        logger.warning(f"[Registry] 未找到匹配的 Agent，文本: {text!r}")

    return best_match


def format_agent_list() -> str:
    """格式化 Agent 列表，供 Telegram 展示"""
    agents = list_agents()
    if not agents:
        return "📭 注册表为空，还没有可用的 Agent。\n使用 /factory <需求> 生产一个。"

    lines = [f"📋 **已注册 Agent 列表** ({len(agents)} 个)\n"]
    for a in agents:
        status_icon = "🟢" if a.get("status") == "READY" else "🔴"
        lines.append(
            f"{status_icon} **{a['name']}** v{a.get('version', '?')}\n"
            f"   质量分: {a.get('quality_score', 0)} | 运行次数: {a.get('run_count', 0)}\n"
            f"   关键词: {', '.join(a.get('keywords', [])) or '未设置'}\n"
        )
    return "\n".join(lines)