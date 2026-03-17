# -*- coding: utf-8 -*-
# filename: naxuye_ultimate_workflow.py
import os
import sys
import json
import asyncio
import operator
import random
from typing import TypedDict, List, Dict, Any, Annotated, Optional
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. 核心算力与组件并网
try:
    from configs.resource_grid import SEMAPHORES
    from configs.naxuye_config_v26 import POWER_GRID
    print("✅ [System] 算力矩阵 v26 与并发锁池同步就绪")
except ImportError:
    print("⚠️ [Critical] 配置丢失：SEMAPHORES/POWER_GRID 未就绪，使用缺省配置")
    SEMAPHORES = {"ENGINEERING": asyncio.Semaphore(2)}
    POWER_GRID = {"ENGINEERING": [{"provider": "DeepSeek", "model": "deepseek-chat"}]}

from commander.intent_parser import intent_parser
from commander.planner import planner_node
from scout.intelligence_fetcher import intelligence_fetcher
from pillow.agent_builder import agent_builder
from commander.reviewer import reviewer_node
from commander.mindset import mindset_logic

BATCH_SIZE = 2  # 每批最多生产2个组件

# --- 2. 状态定义 ---
class AgentState(TypedDict):
    input: str
    chat_history: List[Any]
    plan: Dict[str, Any]
    intelligence: str
    draft: List[Dict[str, Any]]
    passed_slots: Annotated[List[Dict[str, Any]], operator.add]
    active_node: Dict[str, Any]
    audit_report: Dict[str, Any]
    final_decision: str
    error_log: Annotated[List[str], operator.add]
    retry_count: Annotated[int, operator.add]
    final_path: str
    # 分批生产新增字段
    target_components: List[Dict[str, Any]]  # 全量组件列表，Planner 第一次写入后不再覆盖
    batch_retry_count: int                   # 当前批次重试计数，不累加

# --- 3. 节点逻辑 ---

async def enhanced_dispatcher(state: AgentState):
    user_input = state.get("input", "").lower()
    strategic_keywords = ["生产", "构建", "重构", "逻辑", "设计", "开发", "agent"]
    tier = "STRATEGIC" if any(word in user_input for word in strategic_keywords) else "ENGINEERING"
    nodes = POWER_GRID.get(tier, POWER_GRID.get("ENGINEERING", []))
    selected_node = random.choice(nodes) if nodes else {}
    if selected_node:
        selected_node["tier"] = tier
    print(f"📡 [Dispatcher] 预判等级: {tier} | 注入物理算力: {selected_node.get('provider', 'DEFAULT')}")
    return {"active_node": selected_node}

async def enhanced_pillow_wrapper(state: AgentState):
    result = await agent_builder(state)
    current_report = result.get("audit_report", {})
    if current_report.get("failed_count", 0) > 0:
        failed_details = current_report.get("failed_details", [])
        if failed_details:
            error_msgs = [f"组件 {d.get('path')} 失败: {d.get('error_type')}" for d in failed_details]
            result["error_log"] = error_msgs
        result["retry_count"] = 1
    else:
        result["retry_count"] = 0
    return result

async def enhanced_reviewer_wrapper(state: AgentState):
    result = await reviewer_node(state)
    report = result.get("audit_report", state.get("audit_report", {}))
    score = report.get("score", 100)

    # 把 pillow 的 failed_count 合并进来
    pillow_failed = state.get("audit_report", {}).get("failed_count", 0)
    if pillow_failed > 0:
        report["failed_count"] = pillow_failed
        result["audit_report"] = report

    if score < 80:
        result["retry_count"] = 1
    return result

async def batch_scheduler(state: AgentState):
    """
    分批调度器：从 target_components 里取下一批未完成的组件
    注入到 plan.components，让 pillow 只生产这一批
    """
    target = state.get("target_components", [])
    passed = state.get("passed_slots", [])
    passed_names = {f['path'] for f in passed}

    # 找出还没完成的组件
    remaining = [c for c in target if c.get('path') not in passed_names]

    if not remaining:
        print("🎯 [BatchScheduler] 所有组件已完成，进入归档")
        return {"plan": {**state.get("plan", {}), "components": []}}

    # 取下一批
    next_batch = remaining[:BATCH_SIZE]
    batch_names = [c.get('path') for c in next_batch]
    print(f"📦 [BatchScheduler] 本批生产: {batch_names} | 剩余: {len(remaining)-len(next_batch)} 个待生产")

    # 重置本批次重试计数
    updated_plan = {**state.get("plan", {}), "components": next_batch}
    return {
        "plan": updated_plan,
        "batch_retry_count": 0
    }

async def ultimate_logistic_node(state: AgentState):
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

# --- 4. 路由逻辑 ---

def should_continue(state: AgentState):
    """Reviewer 后的路由：决定重工、归档、还是取下一批"""
    report = state.get("audit_report", {})
    score = report.get("score", 0)
    retries = state.get("retry_count", 0)
    error_type = report.get("error_type", "")
    failed_count = report.get("failed_count", 0)

    if error_type == "SAFETY_INTERCEPT":
        print("🚩 [Strategy] 检测到安全红线，强制回流至 Planner 重新设计蓝图")
        return "rebuild_plan"

    if score < 80 or failed_count > 0:
        if retries < 6:
            print(f"⚠️ [QC] 纯度不足({score}) | 失败组件: {failed_count} 个，启动重工")
            return "rework_code"
        else:
            print("🚨 [QC] 重工耗尽，被迫打回战略层重新规划")
            return "rebuild_plan"

    # 本批通过，检查是否还有下一批
    target = state.get("target_components", [])
    passed = state.get("passed_slots", [])
    passed_names = {f['path'] for f in passed}
    remaining = [c for c in target if c.get('path') not in passed_names]

    if remaining:
        print(f"✅ [QC] 本批审计通过({score})，还有 {len(remaining)} 个组件待生产，取下一批")
        return "next_batch"
    else:
        print(f"✅ [QC] 全部组件审计通过({score})，进入落盘阶段")
        return "archive"

def mindset_check(state: AgentState):
    final_decision = state.get("final_decision")
    if final_decision == "REJECTED":
        print("🔄 [Router] Mindset 拒绝签署，打回 Planner 重谋")
        return "rethink"
    else:
        print("📦 [Router] Mindset 签署通过，进入 Logistic 归档")
        return "archive"

def logistic_check(state: AgentState):
    final_decision = state.get("final_decision")
    if final_decision == "ERROR":
        print("🚨 [Router] Logistic 归档失败，打回 Planner 重试")
        return "rethink"
    if not state.get("final_path"):
        print("⚠️ [Router] 未检测到归档路径，打回重试")
        return "rethink"
    print("✅ [Router] 双质检通过，流程结束")
    return "end"

# --- 5. 架构编排 ---
workflow = StateGraph(AgentState)

workflow.add_node("intent_parser", intent_parser)
workflow.add_node("planner", planner_node)
workflow.add_node("dispatcher", enhanced_dispatcher)
workflow.add_node("scout", intelligence_fetcher)
workflow.add_node("batch_scheduler", batch_scheduler)
workflow.add_node("pillow", enhanced_pillow_wrapper)
workflow.add_node("reviewer", enhanced_reviewer_wrapper)
workflow.add_node("mindset", mindset_logic)
workflow.add_node("logistic", ultimate_logistic_node)

workflow.set_entry_point("intent_parser")

workflow.add_edge("intent_parser", "dispatcher")
workflow.add_edge("dispatcher", "planner")
workflow.add_edge("planner", "scout")
workflow.add_edge("scout", "batch_scheduler")  # planner 后先进分批调度
workflow.add_edge("batch_scheduler", "pillow")
workflow.add_edge("pillow", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    should_continue,
    {
        "rework_code": "pillow",
        "next_batch": "batch_scheduler",  # 本批通过，取下一批
        "rebuild_plan": "planner",
        "archive": "mindset"
    }
)

workflow.add_conditional_edges(
    "mindset",
    mindset_check,
    {
        "rethink": "planner",
        "archive": "logistic"
    }
)

workflow.add_conditional_edges(
    "logistic",
    logistic_check,
    {
        "rethink": "planner",
        "end": END
    }
)

naxuye_app = workflow.compile()