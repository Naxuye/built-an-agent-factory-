# -*- coding: utf-8 -*-
# filename: workflow_nodes.py
# 职责：LangGraph 节点的 wrapper 函数（dispatcher、pillow、reviewer、batch_scheduler、logistic）

import os
import json
import asyncio
import random

try:
    from configs.naxuye_config_v26 import get_power_grid
except ImportError:
    get_power_grid = lambda: {}

from pillow.agent_builder import agent_builder
from commander.reviewer import reviewer_node

BATCH_SIZE = 4


# ============================================================
# Dispatcher — 算力分发
# ============================================================

async def enhanced_dispatcher(state: dict):
    user_input = state.get("input", "").lower()
    strategic_keywords = ["生产", "构建", "重构", "逻辑", "设计", "开发", "agent"]
    tier = "STRATEGIC" if any(word in user_input for word in strategic_keywords) else "ENGINEERING"
    nodes = get_power_grid().get(tier, get_power_grid().get("ENGINEERING", []))
    selected_node = random.choice(nodes) if nodes else {}
    if selected_node:
        selected_node["tier"] = tier
    print(f"📡 [Dispatcher] 预判等级: {tier} | 注入物理算力: {selected_node.get('provider', 'DEFAULT')}")
    return {"active_node": selected_node}


# ============================================================
# Pillow Wrapper — 生产节点封装
# ============================================================

async def enhanced_pillow_wrapper(state: dict):
    result = await agent_builder(state)
    drafts = result.get("draft", [])
    current_report = result.get("audit_report", {})

    # 无新产出时，清掉 failed_count 防止残留值触发死循环
    if not drafts:
        result["audit_report"] = {"score": 100, "error_type": "NONE", "failed_count": 0}
        result["retry_count"] = 0
        return result

    if current_report.get("failed_count", 0) > 0:
        failed_details = current_report.get("failed_details", [])
        if failed_details:
            error_msgs = [f"组件 {d.get('path')} 失败: {d.get('error_type')}" for d in failed_details]
            result["error_log"] = error_msgs
        result["retry_count"] = state.get("retry_count", 0) + 1
    else:
        result["retry_count"] = 0
    return result


# ============================================================
# Reviewer Wrapper — 审计节点封装
# ============================================================

async def enhanced_reviewer_wrapper(state: dict):
    result = await reviewer_node(state)
    report = result.get("audit_report", state.get("audit_report", {}))
    score = report.get("score", 100)

    # 把 pillow 的 failed_count 合并进来
    pillow_failed = state.get("audit_report", {}).get("failed_count", 0)
    if pillow_failed > 0:
        report["failed_count"] = pillow_failed
        result["audit_report"] = report

    if score < 80:
        result["retry_count"] = state.get("retry_count", 0) + 1
    else:
        result["retry_count"] = 0
    return result


# ============================================================
# Batch Scheduler — 分批调度
# ============================================================

async def batch_scheduler(state: dict):
    """从 target_components 里取下一批未完成的组件"""
    target = state.get("target_components", [])
    passed = state.get("passed_slots", [])
    passed_names = {f['path'] for f in passed}

    remaining = [c for c in target if c.get('path') not in passed_names]

    if not remaining:
        print("🎯 [BatchScheduler] 所有组件已完成，进入归档")
        return {"plan": {**state.get("plan", {}), "components": []}}

    next_batch = remaining[:BATCH_SIZE]
    batch_names = [c.get('path') for c in next_batch]
    print(f"📦 [BatchScheduler] 本批生产: {batch_names} | 剩余: {len(remaining)-len(next_batch)} 个待生产")

    updated_plan = {**state.get("plan", {}), "components": next_batch}
    return {
        "plan": updated_plan,
        "batch_retry_count": 0
    }


# ============================================================
# Logistic — 交付归档
# ============================================================

async def ultimate_logistic_node(state: dict):
    passed_assets = state.get("passed_slots", [])
    default_workspace = os.getenv("NAXUYE_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace", "agent_factory"))
    final_path = state.get("final_path") or default_workspace

    if passed_assets:
        manifest_path = os.path.join(final_path, "manifest.json")
        manifest = {
            "timestamp": "2026-03-17",
            "total_components": len(passed_assets),
            "components": passed_assets,
            "provider": state.get('active_node', {}).get('provider', 'Standard'),
            "final_decision": state.get('final_decision', 'Ready')
        }
        try:
            os.makedirs(final_path, exist_ok=True)
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=4, ensure_ascii=False)
            print(f"📝 [Logistic] 生成资产清单: {manifest_path}")
        except Exception as e:
            print(f"⚠️ [Logistic] 清单生成失败: {e}")

    summary = (
        f"\n{'='*30}\n"
        f"📦 [Naxuye Logistic] 交付清单:\n"
        f"- 固化组件数: {len(passed_assets)} Units\n"
        f"- 归档物理坐标: {final_path}\n"
        f"- 算力调度记录: {state.get('active_node', {}).get('provider', 'Standard')}\n"
        f"- 最终签署状态: {state.get('final_decision', 'Ready')}\n"
        f"{'='*30}"
    )
    return {"final_decision": summary, "final_path": final_path}