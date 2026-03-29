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
    if existing_targets and error_type not in ["SAFETY_INTERCEPT", "", "NONE"]:
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
        "你负责理解用户需求并设计可生产的 Agent 架构。\n\n"
        "【核心原则】优先使用单组件完成任务。一个 run() 内可以调用多个 skill，不需要拆分成多个文件。\n"
        "  只有当需求明确包含可独立复用的子模块时，才拆分为多组件，最多不超过 2 个。\n"
        f"{feedback_context}\n"
        "【组件 description 必须包含】：\n"
        "  - run() 的输入输出定义\n"
        "  - 具体实现步骤（按顺序调用哪些 skill、每步做什么）\n"
        "  - 依赖的环境变量名\n\n"
        "【工厂可用 skill】生成的代码只能用以下 skill，禁止直接 import 第三方库：\n"
        "  多个 skill 同时使用时必须用别名避免覆盖，示例：\n"
        "  - llm_call：from skills.llm_call import call as llm_call\n"
        "    result = await llm_call(prompt='...', provider='deepseek')  # 成功取 result['content']\n"
        "  - http_request：from skills.http_request import call as http_request\n"
        "    result = await http_request(url='...', method='GET')  # 成功取 result['body']\n"
        "  - web_scraper：from skills.web_scraper import call as web_scraper\n"
        "    result = await web_scraper(url='...', extract='text')  # 成功取 result['result']\n"
        "  - file_io：from skills.file_io import call as file_io\n"
        "    result = await file_io(action='read', path='...')  # 成功取 result['result']\n"
        "  - json_parser：from skills.json_parser import call as json_parser\n"
        "    result = await json_parser(action='parse', text='...')  # 成功取 result['result']\n"
        "  一个组件内可按需组合多个 skill，按步骤顺序调用即可。\n"
        "  超出上述资源的依赖必须在 description 中说明。\n\n"
        "【注册元信息】：\n"
        "  - agent_name：snake_case 英文，如 weather_query_agent\n"
        "  - agent_type：llm_call / api_integration / data_processing / tool 四选一\n"
        "  - input_schema：run() 参数字典\n"
        "  - trigger_keywords：中英文关键词，至少6个\n"
        "  - 每个组件标注 component_type（同样四选一）\n\n"
        "【测试用例】生成 2-3 个，字段：input / check_type(status_success|field_exists|contains_text) / check_value / description。\n"
        "  测试用例的 input 字段必须严格匹配 input_schema，不能多也不能少，值用真实可用的示例。\n\n"
        "【输出】合法纯 JSON，双引号，禁止 Markdown。\n"
        '{\n'
        '  "agent_name": "my_agent_name",\n'
        '  "agent_type": "llm_call",\n'
        '  "input_schema": {"param1": "str"},\n'
        '  "trigger_keywords": ["关键词1", "keyword2"],\n'
        '  "test_cases": [\n'
        '    {"input": {"param1": "value1"}, "check_type": "status_success", "check_value": "", "description": "正常输入测试"},\n'
        '    {"input": {"param1": ""}, "check_type": "status_success", "check_value": "", "description": "空输入边界测试"}\n'
        '  ],\n'
        '  "tier": "STRATEGIC",\n'
        '  "mode": "CONCURRENT",\n'
        '  "components": [\n'
        '    {"path": "core_logic.py", "tier": "STRATEGIC", "component_type": "llm_call", "timeout": 180, "description": "..."}\n'
        '  ],\n'
        '  "need_scout": true,\n'
        '  "query": "..."\n'
        '}\n'
    )

    provider_label = active_node.get('provider', 'DEFAULT')
    print(f"📊 [Planner] 正在进行战略拆解与分级... [算力驱动: {provider_label}]")

    # 查询工厂级记忆：有没有类似的成功案例可以参考
    memory_context = ""
    try:
        from configs.error_memory import get_similar_productions
        similar = get_similar_productions(user_input)
        if similar:
            cases = []
            for s in similar:
                cases.append(f"  - {s['agent_name']} (score={s['score']}): 组件={s['components']}")
            memory_text = "\n".join(cases)
            memory_context = (
                f"\n【工厂历史经验】以下是类似需求的成功案例，可以参考但不要照搬：\n"
                f"{memory_text}\n"
            )
            print(f"📚 [Planner] 找到 {len(similar)} 个历史参考案例")
    except Exception:
        pass

    try:
        print(f"📤 [Planner] 请求体: {user_input[:100]}...")
        res_json = await smart_dispatch(
            prompt=user_input + memory_context,
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
            # 去掉 LLM 可能生成的子目录前缀，只保留文件名
            if 'path' in c:
                c['path'] = os.path.basename(c['path'])

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
        test_cases = plan.get("test_cases", [])
        print(f"    ┗ 🏷️  Agent 名称: {agent_name}")
        print(f"    ┗ 📋 Input Schema: {input_schema}")
        print(f"    ┗ 🔑 Keywords: {trigger_keywords}")
        if test_cases:
            print(f"    ┗ 🧪 测试用例: {len(test_cases)} 个")

        # 第一次规划时写入 target_components（全量），后续批次调度从这里取
        return {
            "plan": plan,
            "target_components": components,
            "agent_name": agent_name,
            "input_schema": input_schema,
            "trigger_keywords": trigger_keywords,
            "test_cases": test_cases,
            "retry_count": 0,
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