# -*- coding: utf-8 -*-
# filename: pillow/agent_builder.py

import os
import asyncio
import random
import re
import json
import copy
from typing import List, Dict, Any

# --- 统一导入超时和信号量配置 ---
try:
    from configs.resource_grid import SEMAPHORES, TIMEOUTS
except ImportError:
    # 降级配置
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
    from configs.naxuye_config_v26 import POWER_GRID
except ImportError:
    POWER_GRID = {}

from commander.api_router import smart_dispatch

_tier_index = {}

# --- 2. 集装箱路径规划器（只规划路径，不写文件，写文件全交给 mindset）---
def plan_container_path(filename: str) -> str:
    """只计算并返回目标路径，不创建任何文件或目录"""
    agent_id = filename.split('.')[0]
    workspace = os.getenv("NAXUYE_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace", "agent_factory"))
    project_dir = os.path.join(workspace, f"{agent_id}_SAFE")
    return project_dir

# --- 3. 增强版代码解析器 ---
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

# --- 4. 原子化生产单元 ---
async def atomic_produce(filename: str, task: str, intelligence: str, router_func, tier: str, active_node: dict = None) -> Dict[str, Any]:
    # 按组件 tier 动态选节点
    try:
        tier_nodes = POWER_GRID.get(tier, POWER_GRID.get("ENGINEERING", []))
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
    
    unit_prompt = (
        f"你现在是 Naxuye 首席铸造师。\n"
        f"【组件任务】：{task}\n"
        f"【当前目标】：编写组件 '{filename}' 的代码。\n"
        f"【算力对标】：{tier} 专家标准 ({provider_name})。\n"
        f"【参考情报】：{intelligence.get('content', intelligence) if isinstance(intelligence, dict) else intelligence}\n"
        f"【上轮审计反馈】：{intelligence.get('review_advice', '无') if isinstance(intelligence, dict) else '无'}\n"
        f"【强制要求】：\n"
        f"  1. 必须包含标准入口函数：async def run(input: dict) -> dict\n"
        f"  2. 所有 API 密钥必须用 os.getenv() 读取，禁止硬编码\n"
        f"  3. 时间戳必须用 time.time() 或 datetime.now()，禁止用 asyncio.get_event_loop().time()\n"
        f"  4. 禁止出现 Mock 类、Mock 函数、测试代码，禁止出现 if __name__ == '__main__'\n"
        f"  5. 错误处理统一返回格式：{{'error': '...', 'status': 'failed'}}\n"
        f"  6. 必须包含健康检查函数：async def health() -> dict，返回 {{'status': 'healthy'}}\n"
        f"  7. 所有配置（路径、超时）必须从环境变量或入参读取，禁止硬编码\n"
        f"  8. 必须包含日志记录，使用统一 logger，包含时间戳、模块名\n"
        f"  9. run() 的 input 参数必须做类型/字段校验\n"
        f" 10. 必须在文件顶部显式导入所有依赖，禁止在函数内部 import\n"
        f" 11. 代码顶部必须包含版本信息，格式：# version: v1.0, python>=3.11\n"
        f" 12. 代码顶部第一行必须是：# filename: {filename}\n"
        f" 13. 直接输出代码内容，禁止包含 Markdown 标记，禁止任何解释性文字。"
    )

    try:
        raw_content = await asyncio.wait_for(
            router_func(
                prompt=f"开始铸造：{filename}",
                system_prompt=unit_prompt,
                tier=tier,
                active_node=active_node
            ),
            timeout=TIMEOUTS.get(tier, 150)
        )
        
        if not raw_content or len(raw_content.strip()) == 0:
            return {"path": filename, "content": "", "status": "FAILED", "error_type": "EMPTY_RESPONSE"}
            
        parsed_files = parse_llm_output(raw_content, filename)
        result = parsed_files[0] if parsed_files else {"path": filename, "content": raw_content or "# 生成失败"}

        # 只规划路径，不写文件
        result["container_path"] = plan_container_path(filename)
        result["status"] = "SUCCESS"
        result["provider"] = provider_name
        result["tier"] = tier
        return result

    except asyncio.TimeoutError:
        print(f"⏰ [Pillow] {filename} 生产超时（{TIMEOUTS.get(tier, 150)}秒）")
        return {
            "path": filename,
            "content": "",
            "status": "FAILED",
            "error_type": "PRODUCTION_TIMEOUT",
            "error_detail": "API 响应超时"
        }
    except Exception as e:
        error_msg = str(e).upper()
        print(f"⚠️ [Pillow] {filename} 物理触发异常: {error_msg}")
        error_type = "SAFETY_INTERCEPT" if any(word in error_msg for word in ["SAFETY", "POLICY", "BLOCKED"]) else "GENERAL_ERROR"
        return {
            "path": filename,
            "content": "",
            "status": "FAILED",
            "error_type": error_type,
            "error_detail": str(e)
        }

# --- 5. 核心调度引擎 ---
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

    async def locked_produce(item, i):
        comp_tier = item['tier']
        sem = SEMAPHORES.get(comp_tier, SEMAPHORES.get("ENGINEERING", asyncio.Semaphore(3)))
        async with sem:
            await asyncio.sleep(i * 0.3 + random.uniform(0.1, 0.2))
            try:
                return await asyncio.wait_for(
                    atomic_produce(item['path'], task, intelligence, smart_dispatch, comp_tier, active_node=active_node),
                    timeout=TIMEOUTS.get(comp_tier, 150) + 60
                )
            except asyncio.TimeoutError:
                return {
                    "path": item['path'],
                    "status": "FAILED",
                    "error_type": "LOCKED_PRODUCE_TIMEOUT",
                    "error_detail": "信号量内生产超时"
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