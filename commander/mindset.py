# filename: commander/mindset.py
import os
from dotenv import load_dotenv
load_dotenv(override=True)
import json
import shutil
import subprocess
import threading
from datetime import datetime
from commander.logic_core_extractor import extract_core_logic
from Nomos.registry import register_agent

signing_lock = threading.Lock()

def _generate_manifest(project_id: str, assets: list, provider: str, score: int,
                        input_schema: dict = None, trigger_keywords: list = None) -> dict:
    """生成 agent_manifest.json，供管家调用索引"""
    components = []
    for asset in assets:
        components.append({
            "file": asset['path'],
            "tier": asset.get('tier', 'UNKNOWN'),
            "provider": asset.get('provider', provider)
        })
    return {
        "name": project_id,
        "version": "1.0.0",
        "build_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entry": assets[0]['path'] if assets else "main.py",
        "trigger_keywords": trigger_keywords or [],
        "input_schema": input_schema or {"input": "str"},
        "output_schema": {"result": "str"},
        "components": components,
        "quality_score": score,
        "provider": provider,
        "status": "READY"
    }

def _generate_readme(project_id: str, assets: list, score: int) -> str:
    """生成 README.md，供管家和开发者阅读"""
    component_list = "\n".join([f"- `{a['path']}`" for a in assets])
    return f"""# {project_id}

> 由 Naxuye 工厂自动生成 | Build Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 调用方式

```python
from main import run
result = await run({{"input": "你的指令"}})
```

## 组件清单

{component_list}

## 质量评分

{score} / 100

## 说明

请在 `agent_manifest.json` 中补充 `trigger_keywords`，管家将根据关键词自动匹配调用此 agent。
"""

def mindset_logic(state: dict):
    """
    Naxuye 物理落盘与工厂归档器 (V5.8 PostChecker 增强版)
    职责：人工终审、静态校验、去重抛光、物理归档、生成 manifest 和 README
    """
    report = state.get("audit_report", {})
    score = report.get("score", 0)
    active_node = state.get("active_node", {})
    provider = active_node.get("provider", "UNKNOWN")

    raw_assets = state.get("passed_slots", [])
    if not raw_assets:
        raw_assets = state.get("draft", [])

    unique_map = {asset['path']: asset for asset in raw_assets}
    passed_assets = list(unique_map.values())

    with signing_lock:
        print("\n" + "█"*45)
        print(f"🛡️ [Mindset] 正在进行全量资产签署审计...")
        print(f"📦 待签组件清单：{[f['path'] for f in passed_assets]}")
        print(f"⚖️ 综合得分：{score}")
        print(f"📜 审计摘要：{report.get('summary', '无')}")
        print("█"*45 + "\n")

        auto_approve = os.getenv("NAXUYE_AUTO_APPROVE", "false").lower() == "true"

        if auto_approve:
            confirm = "y" if score >= 80 else ""
        else:
            if score < 80:
                print("🚨 [警告] 审计评分未达标。")
                confirm = input("👉 强行签署(FORCE) 或 发回重工(ENTER): ").strip()
            else:
                confirm = input("👉 审计合格。确认物理归档吗？(Y/n): ").strip().lower()

    if confirm in ["y", "yes", "", "force", "FORCE"]:

        try:
            polished_assets = extract_core_logic(passed_assets)
        except Exception as e:
            print(f"⚠️ [Mindset] 代码抛光失败: {e}，使用原始资产")
            polished_assets = passed_assets

        # 读取注册元信息（Planner 生成）
        agent_name_from_state = state.get("agent_name", "").strip()
        if agent_name_from_state:
            project_id = agent_name_from_state
        else:
            base_ref = os.path.basename(polished_assets[0]['path'])
            project_id = os.path.splitext(base_ref)[0]

        input_schema = state.get("input_schema") or {"input": "str"}
        trigger_keywords = state.get("trigger_keywords") or []

        workspace = os.getenv("NAXUYE_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace", "agent_factory"))
        tag = "SAFE" if score >= 80 else "RISK"
        timestamp = datetime.now().strftime("%H%M%S")
        dest_path = os.path.join(workspace, f"{project_id}_{tag}_{timestamp}")

        try:
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)

            for sub in ['', 'in', 'out', 'data']:
                os.makedirs(os.path.join(dest_path, sub), exist_ok=True)

            for file in polished_assets:
                safe_path = file['path'].strip().replace(" ", "_")
                file_path = os.path.join(dest_path, safe_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(file['content'])
                try:
                    subprocess.run(["black", file_path], capture_output=True, timeout=5, check=False)
                except:
                    pass

            # 生成 agent_manifest.json（附上 PostChecker 得分）
            manifest = _generate_manifest(project_id, polished_assets, provider, score,
                                          input_schema=input_schema,
                                          trigger_keywords=trigger_keywords)
            with open(os.path.join(dest_path, "agent_manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=4, ensure_ascii=False)

            readme = _generate_readme(project_id, polished_assets, score)
            with open(os.path.join(dest_path, "README.md"), "w", encoding="utf-8") as f:
                f.write(readme)

            with open(os.path.join(dest_path, "signal.flag"), "w", encoding="utf-8") as f:
                f.write("READY")

            print(f"🌟 [Mindset] 签署成功！全量资产已归档：{dest_path}")

            # 自动注册到 Nomos
            try:
                from Nomos.registry import register_agent
                manifest_path = os.path.join(dest_path, "agent_manifest.json")
                if os.path.exists(manifest_path):
                    register_agent(manifest_path)
            except Exception as e:
                print(f"⚠️ [Mindset] Nomos 注册失败（不影响归档）: {e}")

            return {
                "final_decision": "APPROVED",
                "passed_slots": [],
                "final_path": dest_path
            }

        except Exception as e:
            print(f"❌ [Mindset] 物理落盘失败: {e}")
            import traceback
            traceback.print_exc()
            return {"final_decision": "ERROR"}

    else:
        print(f"🚫 [Mindset] 拒绝签署。组件发回重工循环。")
        return {"final_decision": "REJECTED"}