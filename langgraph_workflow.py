# -*- coding: utf-8 -*-
# filename: langgraph_workflow.py
# 职责：LangGraph 图编排与路由逻辑（纯流程定义，不含节点实现）

import os
import sys
import asyncio
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 状态定义
from workflow_state import AgentState

# 节点函数
from commander.intent_parser import intent_parser
from commander.planner import planner_node
from scout.intelligence_fetcher import intelligence_fetcher
from commander.mindset import mindset_logic
from workflow_nodes import (
    enhanced_dispatcher,
    enhanced_pillow_wrapper,
    enhanced_reviewer_wrapper,
    batch_scheduler,
    ultimate_logistic_node,
)
from commander.smoke_test import smoke_test_node


# ============================================================
# 路由逻辑
# ============================================================

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

    if error_type == "PLANNER_FAILURE":
        print("🚨 [Strategy] Planner 节点失败，无法重工，强制终止流程")
        return "archive"

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


def smoke_test_check(state: AgentState):
    """冒烟测试后的路由：通过 → mindset，失败 → 打回 pillow 重工失败文件"""
    report = state.get("audit_report", {})
    if report.get("error_type") == "SMOKE_TEST_FAILURE":
        failed_count = report.get("failed_count", 0)
        print(f"🔴 [Router] 冒烟测试失败（{failed_count} 个文件），打回 Pillow 重工")
        return "failed"
    print("✅ [Router] 冒烟测试通过，进入签署")
    return "passed"


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


# ============================================================
# 图编排
# ============================================================

workflow = StateGraph(AgentState)

# 注册节点
workflow.add_node("intent_parser", intent_parser)
workflow.add_node("dispatcher", enhanced_dispatcher)
workflow.add_node("planner", planner_node)
workflow.add_node("scout", intelligence_fetcher)
workflow.add_node("batch_scheduler", batch_scheduler)
workflow.add_node("pillow", enhanced_pillow_wrapper)
workflow.add_node("reviewer", enhanced_reviewer_wrapper)
workflow.add_node("smoke_test", smoke_test_node)
workflow.add_node("mindset", mindset_logic)
workflow.add_node("logistic", ultimate_logistic_node)

# 线性流程
workflow.set_entry_point("intent_parser")
workflow.add_edge("intent_parser", "dispatcher")
workflow.add_edge("dispatcher", "planner")
workflow.add_edge("planner", "scout")
workflow.add_edge("scout", "batch_scheduler")
workflow.add_edge("batch_scheduler", "pillow")
workflow.add_edge("pillow", "reviewer")

# 条件路由
workflow.add_conditional_edges(
    "reviewer",
    should_continue,
    {
        "rework_code": "pillow",
        "next_batch": "batch_scheduler",
        "rebuild_plan": "planner",
        "archive": "smoke_test"       # 全部审计通过 → 先做冒烟测试
    }
)

workflow.add_conditional_edges(
    "smoke_test",
    smoke_test_check,
    {
        "passed": "mindset",           # 冒烟通过 → 进入签署
        "failed": "pillow"            # 冒烟失败 → 打回 Planner 重新规划
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