# -*- coding: utf-8 -*-
# filename: scout/intelligence_fetcher.py
import os
import sys
import time
import json
import asyncio
from typing import Dict, Any
from tavily import TavilyClient

# 1. 核心配置与算力并网
try:
    from configs.naxuye_config_v26 import get_power_grid
except ImportError:
    get_power_grid = lambda: {}

from commander.api_router import smart_dispatch

def log_telemetry(node_name, provider, status, details=""):
    """
    能量监控：记录每一笔算力开支与节点状态 (全量复原)
    """
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "power_consumption.jsonl")
    
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "node": node_name,
        "provider": provider,
        "status": status,
        "details": str(details)[:150]
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

async def intelligence_fetcher(state: Dict[str, Any]):
    """
    Naxuye 侦察兵节点 V5.6 [双质检适配版]
    职责：组件级全网情报抓取 + 算力提纯总结
    """
    # --- [参数解构] ---
    task_input = state.get("input", "")
    plan = state.get("plan", {})
    components = plan.get("components", [])
    current_intel = state.get("intelligence", "")
    active_node = state.get("active_node", {}) # 🔑 接收分发的物理钥匙
    
    # 确保 active_node 不为空
    if not active_node:
        print("⚠️ [Scout] 未接收到物理算力钥匙，使用默认配置")
        active_node = {"provider": "DEFAULT", "model": "default"}
    
    # 判断是否需要执行搜索
    if not plan.get("need_scout", True):
        return {"intelligence": current_intel or "无需外部情报"}

    # --- [1. 确定搜索维度] ---
    search_queries = [f"Python {c.get('path') if isinstance(c, dict) else str(c)} implementation best practices" for c in components]
    if not search_queries:
        search_queries = [task_input]

    print(f"📡 [Scout] 启动全维度探针，维度数: {len(search_queries)}...")

    # --- [2. 物理 Key 与配置读取] ---
    scout_cfg = get_power_grid().get("GLOBAL_SCOUT", {})
    tavily_key = scout_cfg.get("tavily_key") or os.getenv("TAVILY_API_KEY")

    if not tavily_key:
        print("⚠️ [Scout] 雷达静默：未检测到 TAVILY_API_KEY。")
        log_telemetry("Scout", "TAVILY", "SILENT", "Missing API Key")
        return {
            "intelligence": current_intel + "\n【系统通知】：Tavily 雷达静默，情报缺失，流程继续。",
            "scout_report": {"scout_status": "SILENT"}
        }

    try:
        # --- [3. 异步深度抓取（并发搜索）] ---
        tavily = TavilyClient(api_key=tavily_key)
        
        async def search_component(query):
            try:
                response = await asyncio.to_thread(
                    tavily.search, 
                    query=query, 
                    search_depth="advanced",
                    max_results=2
                )
                results = response.get('results', [])
                return "\n".join([f"- {r['title']}: {r['content'][:150]}" for r in results[:2]])
            except Exception as e:
                return f"【{query[:30]}...】搜索失败: {str(e)[:50]}"
        
        # 并发搜索所有组件（最多3个，避免超时）
        tasks = [search_component(q) for q in search_queries[:3]]
        raw_contexts = await asyncio.gather(*tasks)
        raw_context = "\n\n".join(raw_contexts)
        
        print(f"🧠 [Scout] 正在利用 {active_node.get('provider', 'DEFAULT')} 算力提纯情报...")
        
        summary_prompt = (
            f"你现在是 Naxuye 战略情报分析官。\n"
            f"【原始数据】：{raw_context}\n"
            f"【任务】：针对目标 '{search_queries[0]}' 提取核心技术规范或 2026 最新趋势。\n"
            f"【要求】：直接输出技术要点，禁止任何客套话。"
        )

        # 🚨 [意志接驳]：这里必须传入 active_node，否则 Scout 会调用失败
        summary = await smart_dispatch(
            prompt=f"分析并提纯情报：{search_queries[0]}",
            system_prompt=summary_prompt,
            tier=plan.get("tier", "ENGINEERING"),
            active_node=active_node # 🔑 注入钥匙
        )
        
        new_intel = f"【2026 深度雷达总结】：\n{summary}"
        
        print(f"✅ [Scout] 情报提纯完成。")
        log_telemetry("Scout", "TAVILY+LLM", "SUCCESS", f"Query: {search_queries[0][:50]}")
        
        return {
            "intelligence": new_intel,
            "scout_report": {"scout_status": "SUCCESS"}
        }

    except Exception as e:
        error_msg = str(e)
        print(f"⚠️ [Scout] 探针回传受阻: {error_msg}")
        log_telemetry("Scout", "TAVILY+LLM", "FAILED", error_msg)
        
        # 🚨 双质检对齐：返回错误状态
        return {
            "intelligence": current_intel + f"\n【实时情报】：外部雷达受损 ({error_msg})，情报缺失，流程继续。",
            "scout_report": {"scout_status": "FAILED", "details": error_msg[:100]}
        }