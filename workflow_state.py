# -*- coding: utf-8 -*-
# filename: workflow_state.py
# 职责：定义 LangGraph 工作流的全局状态结构

import operator
from typing import TypedDict, List, Dict, Any, Annotated


def _replace(old, new):
    """替换而非追加，用于需要覆盖的状态字段"""
    return new if new is not None else old


class AgentState(TypedDict):
    # 用户输入
    input: str
    chat_history: List[Any]

    # 规划与情报
    plan: Dict[str, Any]
    intelligence: str

    # 生产与审计
    draft: List[Dict[str, Any]]
    passed_slots: Annotated[List[Dict[str, Any]], _replace]
    active_node: Dict[str, Any]
    audit_report: Dict[str, Any]
    scout_report: Dict[str, Any]
    error_log: Annotated[List[str], operator.add]
    retry_count: int

    # 归档
    final_decision: str
    final_path: str

    # 分批生产
    target_components: List[Dict[str, Any]]
    batch_retry_count: int

    # 注册元信息（Planner 生成，Mindset 消费）
    agent_name: str
    input_schema: Dict[str, Any]
    trigger_keywords: List[str]

    # 测试用例（Planner 生成，SmokeTest 消费）
    test_cases: List[Dict[str, Any]]