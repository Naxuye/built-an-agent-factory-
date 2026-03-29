# -*- coding: utf-8 -*-
# filename: commander/reviewer.py
import json
import ast
import re
import asyncio  
import copy    
from configs.resource_grid import TIMEOUTS
from commander.post_checker import check_assets  # 🚨 新增导入

# --- 1. 核心算力并网 (V26 协议) ---
try:
    from configs.naxuye_config_v26 import get_power_grid
except ImportError:
    get_power_grid = lambda: {}

from commander.api_router import smart_dispatch

# 🚨 轮询计数器
_reviewer_index = 0

def physical_syntax_check(filename: str, code: str):
    """
    铁面法官：100% 拦截 Python 语法错误。
    """
    if not filename.lower().endswith('.py'):
        return True, "Non-Python file, direct pass."
    
    # 清洗 Markdown 标记
    clean_code = re.sub(r'```(python|py)?', '', code, flags=re.IGNORECASE).replace('```', '').strip()
    
    if not clean_code:
        return False, "Empty content after cleaning."

    try:
        ast.parse(clean_code)
        return True, "OK"
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"

async def reviewer_node(state: dict):
    """
    Naxuye 审计节点 V5.5 (损管分拣与算力透传版)
    """
    global _reviewer_index  # 声明全局变量
    
    # 轮询选择审计节点
    try:
        from configs.naxuye_config_v26 import get_power_grid
        nodes = get_power_grid().get("ENGINEERING", [])
        if nodes:
            active_node = copy.deepcopy(nodes[_reviewer_index % len(nodes)])
            _reviewer_index += 1
        else:
            active_node = state.get("active_node") or {}
    except Exception:
        active_node = state.get("active_node")
    
    # 检查 Planner 是否有错误
    plan = state.get("plan", {})
    if plan.get("error"):
        print(f"🚨 [Reviewer] 检测到 Planner 错误: {plan['error']}")
        return {
            "audit_report": {
                "score": 0,
                "error_type": "PLANNER_FAILURE",
                "failed_count": 1,
                "summary": f"Planner 错误: {plan['error']}"
            }
        }
    
    drafts = state.get("draft", []) # 本轮 Pillow 新产出的
    # 获取历史上已经过审的资产
    history_passed = state.get("passed_slots", []) or []
    
    # 损管识别：检查 Pillow 是否上报了“红线错误”
    pilllow_report = state.get("audit_report", {})
    if pilllow_report.get("error_type") == "SAFETY_INTERCEPT":
        print("🚩 [Reviewer] 检测到生产端红线拦截，直接触发损管路由。")
        return {
            "audit_report": {
                "score": 0, 
                "error_type": "SAFETY_INTERCEPT", 
                "summary": "生产端触发敏感词拦截"
            }
        }

    if not drafts:
        print("💡 [Reviewer] 本轮无新产出（可能已全部过审）。")
        return {
            "audit_report": {
                "score": 100,
                "summary": "资产已齐备",
                "failed_count": 0,   # 清除遗留的 failed_count，避免死循环
                "error_type": ""
            }
        }

    # 1. 物理质检
    pre_check_results = {}
    has_physical_error = False
    for d in drafts:
        is_ok, err_msg = physical_syntax_check(d['path'], d['content'])
        pre_check_results[d['path']] = {"ok": is_ok, "msg": err_msg}
        if not is_ok: has_physical_error = True

    # 🚨 新增：PostChecker 静态校验
    post_check = check_assets(drafts)
    post_check_summary = "\n".join(post_check["all_issues"]) if post_check["all_issues"] else "静态校验全部通过。"

    # 2. 准备审计上下文
    content_snapshot = "\n".join([f"--- FILE: {d['path']} ---\n{d['content']}" for d in drafts])
    syntax_warnings = "\n".join([f"⚠️ {k}: {v['msg']}" for k, v in pre_check_results.items() if not v['ok']])

    system_prompt = (
        "你现在是 Naxuye 首席代码审计官。\n"
        "【审计职责】：按以下四个维度逐一检查，给出综合评分。\n\n"
        "【1. 逻辑完整性】：检测变量定义、代码截断、逻辑死循环。\n"
        "【2. 安全性】：\n"
        "  - 是否有硬编码 API 密钥或密码（应使用 os.getenv）\n"
        "  - 是否有 timeout=None 等危险配置\n"
        "  - 是否有硬编码路径或配置\n"
        "【3. 规范性】：\n"
        "  - 是否包含 async def run(input: dict) -> dict\n"
        "  - 是否包含 async def health() -> dict\n"
        "  - 是否有 if __name__ == '__main__' 测试代码残留\n"
        "  - 是否有 Mock 类或测试代码混入\n"
        "【4. 健壮性】：\n"
        "  - run() 是否有输入参数校验\n"
        "  - 错误处理是否统一返回 {'error': ..., 'status': 'failed'}\n"
        "  - 是否有日志记录\n\n"
        f"【物理反馈】：{syntax_warnings if syntax_warnings else '语法校验通过。'}\n"
        f"【静态校验反馈】：{post_check_summary}\n"  # 🚨 新增行
        "【输出要求】：必须返回 JSON: { \"score\": 分数, \"passed_list\": [\"文件名\"], \"advice\": \"建议\" }"
    )

    provider_label = active_node.get('provider') if active_node else "DEFAULT"
    print(f"🔬 [Reviewer] 正在执行深度代码审计... [算力驱动: {provider_label}]")

    try:
        # 将钥匙喂给智能路由，并增加超时保护
        res_json = await asyncio.wait_for(
            smart_dispatch(
                prompt=f"待审组件内容：\n{content_snapshot}",
                system_prompt=system_prompt,
                tier="ENGINEERING",
                json_mode=True,
                active_node=active_node 
            ),
            timeout=TIMEOUTS.get("REVIEWER", 300)
        )
        
        # 工业级鲁棒性容错处理（应对大模型偶尔的 markdown 包裹）
        if "```json" in res_json:
            res_json = res_json.split("```json")[1].split("```")[0].strip()
            
        report = json.loads(res_json)
        llm_passed_names = report.get("passed_list", [])
        
        # 3. 最终分拣：LLM 认可 + 语法通过
        newly_passed_assets = []
        for d in drafts:
            name = d['path']
            if name in llm_passed_names and pre_check_results.get(name, {}).get("ok"):
                newly_passed_assets.append(d)
        
        # 惩罚机制
        score = report.get("score", 0)
        if has_physical_error: score = min(score, 40)
        report["score"] = score

        # 记录审计建议到纠错系统
        advice = report.get("advice", "")
        if advice and score < 80:
            try:
                from configs.error_memory import record_error, ErrorSource
                record_error(
                    pattern_type="LOGIC_ERROR",
                    pattern_detail=advice[:200],
                    source=ErrorSource.REVIEWER.value,
                    related_tier="GENERAL"
                )
            except Exception:
                pass

        print(f"⭐ [Audit] 评分: {score} | 本轮新增: {len(newly_passed_assets)} 个组件")
        
        # 构造返回字典：passed_slots 累积历史 + 本轮新增
        all_passed = list({a['path']: a for a in (history_passed + newly_passed_assets)}.values())
        return_update = {
            "audit_report": report,
            "passed_slots": all_passed
        }

        if score < 80:
            pass  # retry_count 由 wrapper 统一管理
        else:
            report["failed_count"] = 0
            
        return return_update

    except asyncio.TimeoutError:
        print(f"⏰ [Reviewer] 审计超时（300秒）")
        try:
            from configs.error_memory import record_error, ErrorSource
            record_error(
                pattern_type="TIMEOUT",
                pattern_detail="Reviewer 审计超时（300秒）",
                source=ErrorSource.REVIEWER.value,
                related_tier="GENERAL"
            )
        except Exception:
            pass
        return {
            "audit_report": {"score": 0, "error_type": "REVIEW_TIMEOUT", "summary": "审计超时"}
        }
    except Exception as e:
        print(f"⚠️ [Reviewer] 审计故障: {e}")
        return {
            "audit_report": {"score": 0, "summary": f"审计链路异常: {e}"}
        }