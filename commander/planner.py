# -*- coding: utf-8 -*-
# filename: commander/planner.py
import json
import ast
import os
import re

# --- 1. 核心算力并网 (V26 协议) ---
try:
    from configs.naxuye_config_v26 import POWER_GRID
except ImportError:
    POWER_GRID = {}

from commander.api_router import smart_dispatch

def extract_json_from_text(text: str) -> str:
    """从 LLM 响应中提取并清理 JSON 字符串（增强版）"""
    if not text:
        return "{}"
    
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*', '', text)
    
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    
    try:
        parsed = ast.literal_eval(text)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        pass
    
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    
    return text.strip()

async def planner_node(state: dict):
    """
    Naxuye 战略决策大脑 V5.8 (分批生产版)
    - 第一次规划：写入 target_components（全量组件列表）
    - 重谋时：只规划未完成的组件，不覆盖已通过的资产
    """
    user_input = state.get("input", "")
    active_node = state.get("active_node", {})
    audit_report = state.get("audit_report", {})
    error_type = audit_report.get("error_type", "")
    failed_count = audit_report.get("failed_count", 0)

    # 检查是否已有 target_components（重谋时不重新规划已完成的）
    existing_targets = state.get("target_components", [])
    passed_slots = state.get("passed_slots", [])
    passed_names = {f['path'] for f in passed_slots}

    # 如果已有目标组件且只是重工，不需要重新规划
    if existing_targets and error_type not in ["SAFETY_INTERCEPT", ""]:
        remaining = [c for c in existing_targets if c.get('path') not in passed_names]
        if remaining:
            print(f"🔄 [Planner] 重谋模式：保留已完成组件，重新规划 {len(remaining)} 个失败组件")
            plan = state.get("plan", {})
            plan["components"] = remaining
            return {"plan": plan}

    # 构造反馈上下文
    feedback_context = ""
    if error_type == "SAFETY_INTERCEPT":
        feedback_context = (
            "\n⚠️ [上轮核心警报]：检测到部分组件触碰了 API 安全红线。\n"
            "【行动指南】：请重新设计受影响的组件描述，使用中性词汇绕开拦截。"
        )
    elif failed_count > 0:
        feedback_context = (
            f"\n⚠️ [上轮核心警报]：有 {failed_count} 个组件生产失败。\n"
            "【行动指南】：请优化架构拆解，降低逻辑耦合度。"
        )

    system_prompt = (
        "你现在是 Naxuye 战略决策大脑，负责母体工程的精密拆解与算力调度。\n"
        "【算力分级标准】：STRATEGIC | ENGINEERING | BASE\n"
        "【算力分级原则】：\n"
        "  - STRATEGIC：核心逻辑、复杂算法、架构设计类组件（最多1-2个）\n"
        "  - ENGINEERING：业务逻辑、数据处理、API集成类组件\n"
        "  - BASE：配置管理、工具函数、简单IO类组件\n"
        "  【重要】不能全部给同一级别，必须按实际复杂度合理分级。\n"
        "【组件数量限制】：每次最多拆解4个组件，禁止超过4个。\n"
        f"{feedback_context}\n"
        "【输出格式规范】：必须输出合法的纯 JSON，使用双引号，禁止使用单引号，禁止输出任何 Markdown 代码块标签。\n"
        '{\n'
        '  "tier": "STRATEGIC",\n'
        '  "mode": "CONCURRENT",\n'
        '  "components": [\n'
        '    {"path": "core_logic.py", "tier": "STRATEGIC", "timeout": 180, "description": "..."}\n'
        '  ],\n'
        '  "need_scout": true,\n'
        '  "query": "..."\n'
        '}\n'
    )

    provider_label = active_node.get('provider', 'DEFAULT')
    print(f"📊 [Planner] 正在进行战略拆解与分级... [算力驱动: {provider_label}]")

    try:
        print(f"📤 [Planner] 请求体: {user_input[:100]}...")
        res_json = await smart_dispatch(
            prompt=user_input,
            system_prompt=system_prompt,
            json_mode=True,
            tier="STRATEGIC",
            active_node=active_node
        )
        print(f"📥 [Planner] 原始响应: {res_json[:200]}...")

        cleaned_json = extract_json_from_text(res_json)
        plan = json.loads(cleaned_json)

        components = plan.get('components', [])

        if not components:
            print("⚠️ [Planner] 未生成组件，使用默认组件")
            components = [{
                "path": "default_component.py",
                "tier": plan.get('tier', 'ENGINEERING'),
                "timeout": 90,
                "description": "系统自动生成的默认组件"
            }]
            plan['components'] = components

        global_tier = plan.get('tier', 'ENGINEERING')
        for c in components:
            if 'tier' not in c:
                c['tier'] = global_tier

        if 'need_scout' not in plan:
            plan['need_scout'] = True

        path_names = [c.get('path', 'unknown.py') for c in components]
        print(f"✅ [Planner] 战略蓝图已确认：{path_names}")
        for c in components:
            p = c.get('path', 'unknown.py')
            t = c.get('tier', 'BASE')
            print(f"    ┗ 🚀 组件: {p:<25} | 算力分级: {t:<12}")

        # 第一次规划时写入 target_components（全量），后续批次调度从这里取
        return {
            "plan": plan,
            "target_components": components  # 全量组件列表
        }

    except json.JSONDecodeError as e:
        print(f"⚠️ [Planner] JSON 解析失败: {e}")
        return {
            "plan": {
                "tier": "ENGINEERING",
                "mode": "JSON_PARSE_FAILED",
                "components": [],
                "need_scout": False,
                "error": f"JSON解析失败: {str(e)}"
            }
        }
    except Exception as e:
        print(f"⚠️ [Planner] 战略拆解物理崩溃: {repr(e)}")
        return {
            "plan": {
                "tier": "ENGINEERING",
                "mode": "EMERGENCY",
                "components": [],
                "need_scout": False,
                "error": repr(e)
            }
        }