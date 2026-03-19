# -*- coding: utf-8 -*-
# filename: workflow_state.py
# 职责：定义 LangGraph 工作流的全局状态结构

import operator
from typing import TypedDict, List, Dict, Any, Annotated


class AgentState(TypedDict):
    # 用户输入
    input: str
    chat_history: List[Any]

    # 规划与情报
    plan: Dict[str, Any]
    intelligence: str

    # 生产与审计
    draft: List[Dict[str, Any]]
    passed_slots: Annotated[List[Dict[str, Any]], operator.add]
    active_node: Dict[str, Any]
    audit_report: Dict[str, Any]
    error_log: Annotated[List[str], operator.add]
    retry_count: Annotated[int, operator.add]

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