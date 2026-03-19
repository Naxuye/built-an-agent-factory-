# -*- coding: utf-8 -*-
# filename: pillow/agent_builder.py

import os
import asyncio
import random
import re
import json
import copy
from typing import List, Dict, Any
from datetime import datetime

# --- 统一导入超时和信号量配置 ---
try:
    from configs.resource_grid import SEMAPHORES, TIMEOUTS
except ImportError:
    SEMAPHORES = {
        "STRATEGIC": asyncio.Semaphore(1),
        "ENGINEERING": asyncio.Semaphore(3),
        "BASE": asyncio.Semaphore(10)
    }
    TIMEOUTS = {
        "STRATEGIC": 180,
        "ENGINEERING": 150,
        "BASE": 120,
        "REVIEWER": 300
    }

# --- 核心算力并网 ---
try:
    from configs.naxuye_config_v26 import get_power_grid
except ImportError:
    get_power_grid = lambda: {}

from commander.api_router import smart_dispatch

_tier_index = {}

# --- 集装箱路径规划器 ---
def plan_container_path(filename: str) -> str:
    agent_id = filename.split('.')[0]
    workspace = os.getenv("NAXUYE_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace", "agent_factory"))
    return os.path.join(workspace, f"{agent_id}_SAFE")

# --- 模板加载函数 ---
def _load_template(filename: str, build_time: str) -> str:
    try:
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "templates", "agent_template.py"
        )
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        module_name = filename.replace('.py', '').replace('/', '.').replace('\\', '.')
        template = template.replace('{filename}', filename)
        template = template.replace('{build_time}', build_time)
        template = template.replace('{module_name}', module_name)
        return template
    except Exception as e:
        print(f"⚠️ [Pillow] 模板读取失败: {e}，使用纯 prompt 模式")
        return ""

# --- 代码解析器 ---
def parse_llm_output(text: str, default_filename: str = "unknown.py") -> List[Dict[str, Any]]:
    if not text:
        return [{"path": default_filename, "content": "# 生成失败：空响应"}]
    
    text = re.sub(r'^```\w*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n```$', '', text, flags=re.MULTILINE)
    text = text.replace('```', '').strip()
    
    files = []
    if "# filename:" in text:
        parts = text.split("# filename:")
        for part in parts[1:]:
            lines = part.strip().split("\n")
            if not lines:
                continue
            filename = lines[0].strip().strip('*').strip()
            content = "\n".join(lines[1:]).strip()
            if content:
                files.append({"path": filename, "content": content})
    else:
        files.append({"path": default_filename, "content": text})
    
    return files if files else [{"path": default_filename, "content": text}]

# --- 原子化生产单元 ---
async def atomic_produce(filename: str, task: str, intelligence: str, router_func, tier: str, active_node: dict = None, input_schema: dict = None) -> Dict[str, Any]:
    # 按 tier 轮询选节点
    tier_nodes = get_power_grid().get(tier, get_power_grid().get("ENGINEERING", []))
    try:
        if tier_nodes:
            idx = _tier_index.get(tier, 0) % len(tier_nodes)
            _tier_index[tier] = idx + 1
            active_node = copy.deepcopy(tier_nodes[idx])
            active_node["tier"] = tier
        else:
            active_node = active_node or {}
    except Exception:
        active_node = active_node or {}

    provider_name = active_node.get("provider", "UNKNOWN")
    print(f"🏭 [Pillow] 正在生产 ({tier} | {provider_name}): {filename}...")

    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    template_code = _load_template(filename, build_time)
    template_section = (
        f"【标准模板】：以下是你必须严格遵守的代码骨架，"
        f"你只能填充 TODO 部分，禁止删除或修改骨架结构：\n"
        f"{template_code}\n"
    ) if template_code else ""

    input_schema = input_schema or {}
    input_schema_str = ", ".join([f'"{k}": {v}' for k, v in input_schema.items()]) if input_schema else "input: str"

    unit_prompt = (
        f"你现在是 Naxuye 首席铸造师。\n"
        f"【组件任务】：{task}\n"
        f"【当前目标】：编写组件 '{filename}' 的完整生产代码。\n"
        f"【算力对标】：{tier} 专家标准 ({provider_name})。\n"
        f"【参考情报】：{intelligence.get('content', intelligence) if isinstance(intelligence, dict) else intelligence}\n"
        f"{template_section}"
        f"【上轮审计反馈】：{intelligence.get('review_advice', '无') if isinstance(intelligence, dict) else '无'}\n"
        f"【强制规范】：\n"
        f"  1. 入口函数：async def run(input: dict) -> dict，input 字段名严格使用：{input_schema_str}\n"
        f"  2. 健康检查：async def health() -> dict，返回 {{'status': 'healthy'}}\n"
        f"  3. 错误响应：统一返回 {{'status': 'failed', 'error': '...', 'timestamp': time.time()}}\n"
        f"  4. 全局异常：run() 必须有 try/except 兜底，不能让异常直接抛出\n"
        f"  5. 日志：使用 logging.getLogger(__name__)，关键步骤必须记录\n"
        f"  6. 环境变量：API Key 只能用 DASHSCOPE_API_KEY / DEEPSEEK_API_KEY / ZHIPUAI_API_KEY / CHAOSUAN_API_KEY，不确定用 DASHSCOPE_API_KEY\n"
        f"  7. 异步资源：aiohttp.ClientSession 等必须用 async with 管理，禁止裸用\n"
        f"直接输出代码，禁止 Markdown 标记，禁止任何解释文字。"
    )

    async def _call(node: dict) -> str:
        return await asyncio.wait_for(
            router_func(
                prompt=f"开始铸造：{filename}",
                system_prompt=unit_prompt,
                tier=tier,
                active_node=node
            ),
            timeout=TIMEOUTS.get(tier, 150)
        )

    # ── 主调用，失败后自动切换节点重试一次 ──────────────────
    raw_content = None
    try:
        raw_content = await _call(active_node)
    except (asyncio.TimeoutError, Exception) as first_err:
        first_err_type = "超时" if isinstance(first_err, asyncio.TimeoutError) else str(first_err)
        print(f"⚠️ [Pillow] {filename} 首次调用失败（{provider_name} | {first_err_type}），切换节点重试...")

        # 切换到下一个节点
        fallback_node = None
        try:
            if tier_nodes and len(tier_nodes) > 1:
                fallback_idx = _tier_index.get(tier, 0) % len(tier_nodes)
                _tier_index[tier] = fallback_idx + 1
                fallback_node = copy.deepcopy(tier_nodes[fallback_idx])
                fallback_node["tier"] = tier
                fallback_provider = fallback_node.get("provider", "UNKNOWN")
                print(f"🔄 [Pillow] {filename} 切换到 {fallback_provider} 重试...")
                raw_content = await _call(fallback_node)
                # 更新 provider_name 用于记录
                provider_name = fallback_provider
                active_node = fallback_node
        except (asyncio.TimeoutError, Exception) as second_err:
            second_err_type = "超时" if isinstance(second_err, asyncio.TimeoutError) else str(second_err)
            print(f"❌ [Pillow] {filename} 重试也失败（{second_err_type}），放弃生产")
            error_msg = str(second_err).upper()
            error_type = "SAFETY_INTERCEPT" if any(w in error_msg for w in ["SAFETY", "POLICY", "BLOCKED"]) else "PRODUCTION_TIMEOUT"
            return {
                "path": filename,
                "content": "",
                "status": "FAILED",
                "error_type": error_type,
                "error_detail": f"主节点: {first_err_type} | 备用节点: {second_err_type}"
            }
    # ─────────────────────────────────────────────────────────

    if not raw_content or len(raw_content.strip()) == 0:
        return {"path": filename, "content": "", "status": "FAILED", "error_type": "EMPTY_RESPONSE"}

    parsed_files = parse_llm_output(raw_content, filename)
    result = parsed_files[0] if parsed_files else {"path": filename, "content": raw_content or "# 生成失败"}

    result["container_path"] = plan_container_path(filename)
    result["status"] = "SUCCESS"
    result["provider"] = provider_name
    result["tier"] = tier
    return result

# --- 核心调度引擎 ---
async def agent_builder(state: Dict[str, Any]) -> Dict[str, Any]:
    task = state.get("input", "")
    plan = state.get("plan", {})
    global_tier = plan.get("tier", "ENGINEERING")

    intelligence_raw = state.get("intelligence", "无特定情报")
    review_advice = state.get("audit_report", {}).get("advice", "")
    intelligence = {"content": intelligence_raw, "review_advice": review_advice} if review_advice else intelligence_raw

    active_node = state.get("active_node", {})

    raw_slots = plan.get("components") or []
    passed_slots_objs = state.get("passed_slots", []) or []
    passed_names = [f['path'] for f in passed_slots_objs]

    production_list = []
    for s in raw_slots:
        path = s.get('path') if isinstance(s, dict) else str(s)
        tier = s.get('tier') if isinstance(s, dict) else global_tier
        if path not in passed_names:
            production_list.append({"path": path, "tier": tier})

    if not production_list:
        print("✅ [Pillow] 所有组件已就绪。")
        return {"draft": []}

    input_schema = state.get("input_schema", {})

    async def locked_produce(item, i):
        comp_tier = item['tier']
        sem = SEMAPHORES.get(comp_tier, SEMAPHORES.get("ENGINEERING", asyncio.Semaphore(3)))
        async with sem:
            await asyncio.sleep(i * 0.3 + random.uniform(0.1, 0.2))
            try:
                return await asyncio.wait_for(
                    atomic_produce(item['path'], task, intelligence, smart_dispatch, comp_tier,
                                   active_node=active_node, input_schema=input_schema),
                    timeout=TIMEOUTS.get(comp_tier, 150) + 60
                )
            except asyncio.TimeoutError:
                return {
                    "path": item['path'],
                    "status": "FAILED",
                    "error_type": "LOCKED_PRODUCE_TIMEOUT",
                    "error_detail": "信号量内生产超时"
                }
            except Exception as e:
                print(f"❌ [Pillow] {item['path']} 生产异常: {repr(e)}")
                return {
                    "path": item['path'],
                    "status": "FAILED",
                    "error_type": "PRODUCTION_EXCEPTION",
                    "error_detail": repr(e)
                }

    print(f"⚡ [Pillow] 算力矩阵点火。激活供应商: {active_node.get('provider', 'DEFAULT')}")

    try:
        new_results = await asyncio.gather(*[locked_produce(item, i) for i, item in enumerate(production_list)])
        success_results = [r for r in new_results if r and r.get("status") == "SUCCESS"]
        failed_results = [r for r in new_results if not r or r.get("status") == "FAILED"]

        worst_error = "SAFETY_INTERCEPT" if any(r.get("error_type") == "SAFETY_INTERCEPT" for r in failed_results) else ("PRODUCTION_FAILURE" if failed_results else "NONE")

        return {
            "draft": success_results,
            "audit_report": {
                "score": 0 if failed_results else 100,
                "error_type": worst_error,
                "failed_count": len(failed_results),
                "failed_details": [{"path": r.get("path"), "error_type": r.get("error_type")} for r in failed_results if r]
            }
        }
    except Exception as e:
        return {
            "draft": [],
            "audit_report": {
                "score": 0,
                "error_type": "CRITICAL_PILLOW_FAILURE",
                "failed_count": len(production_list),
                "detail": repr(e)
            },
            "retry_count": 1
        }