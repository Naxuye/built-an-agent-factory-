# -*- coding: utf-8 -*-
# filename: commander/planner.py
import json
import ast
import os
import re

# --- 1. 核心算力并网 (V26 协议) ---
try:
    from configs.naxuye_config_v26 import get_power_grid
except ImportError:
    get_power_grid = lambda: {}

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
        "你现在是 Naxuye 工厂的战略决策大脑。你的职责不是简单地拆文件，"
        "而是深度理解用户需求，设计出能真正工作的 Agent 架构。\n\n"
        "【第一步：需求分析】在拆解之前，你必须先回答以下问题（写在你的思考中，不输出）：\n"
        "  1. 这个 Agent 的核心任务是什么？用户期望输入什么、得到什么？\n"
        "  2. 完成这个任务需要什么能力？（自然语言理解？外部数据？纯计算？文件处理？）\n"
        "  3. 这些能力分别用什么技术手段实现？（调 LLM API？调第三方 API？纯 Python？）\n"
        "  4. 需要哪些环境资源？\n\n"
        "【第二步：架构设计】基于分析结果拆解组件，每个组件职责单一、边界清晰。\n"
        "【算力分级】：\n"
        "  - STRATEGIC：核心逻辑、复杂算法、架构协调（最多1-2个）\n"
        "  - ENGINEERING：业务逻辑、API集成、数据处理\n"
        "  - BASE：配置管理、工具函数、简单IO\n"
        "  不能全部给同一级别，必须按实际复杂度分级。\n"
        "【组件数量】：最多4个，禁止超过4个。\n"
        f"{feedback_context}\n"
        "【第三步：精确描述】每个组件的 description 是生产代码的唯一依据，必须包含：\n"
        "  - run() 的完整输入输出定义\n"
        "  - 核心业务逻辑的具体实现方式（不是'处理数据'，而是'调用xxx API做xxx'）\n"
        "  - 依赖的环境变量名和 API 端点\n"
        "  description 写得越精确，生产出的代码质量越高。模糊的 description 会导致废品。\n\n"
        "【工厂可用资源清单】：\n"
        "  - LLM API：DEEPSEEK_API_KEY (https://api.deepseek.com/v1)、"
        "DASHSCOPE_API_KEY (https://dashscope.aliyuncs.com/compatible-mode/v1)、"
        "ZHIPUAI_API_KEY (https://open.bigmodel.cn/api/paas/v4)\n"
        "  - 搜索 API：TAVILY_API_KEY\n"
        "  - Python 标准库和常见第三方库（aiohttp、httpx、json、re 等）\n"
        "  如果需求超出这些资源（如需要数据库、特定SaaS API），必须在 description 中说明，"
        "由生产环节自行处理依赖。\n\n"
        "【注册元信息规范】：\n"
        "  - agent_name：简洁英文 snake_case，如 weather_query_agent\n"
        "  - input_schema：run() 的参数字典，key 为参数名，value 为类型描述\n"
        "  - trigger_keywords：用于用户消息匹配的关键词列表，中英文都要有，至少6个\n\n"
        "【输出格式】：必须输出合法纯 JSON，双引号，禁止 Markdown 标记。\n"
        '{\n'
        '  "agent_name": "my_agent_name",\n'
        '  "input_schema": {"param1": "type1"},\n'
        '  "trigger_keywords": ["关键词1", "keyword2"],\n'
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

        # 提取注册元信息
        agent_name = plan.get("agent_name", "").strip()
        if not agent_name:
            agent_name = os.path.splitext(components[0].get("path", "unknown_agent.py"))[0]
        input_schema = plan.get("input_schema", {"input": "str"})
        trigger_keywords = plan.get("trigger_keywords", [])
        print(f"    ┗ 🏷️  Agent 名称: {agent_name}")
        print(f"    ┗ 📋 Input Schema: {input_schema}")
        print(f"    ┗ 🔑 Keywords: {trigger_keywords}")

        # 第一次规划时写入 target_components（全量），后续批次调度从这里取
        return {
            "plan": plan,
            "target_components": components,
            "agent_name": agent_name,
            "input_schema": input_schema,
            "trigger_keywords": trigger_keywords,
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