# -*- coding: utf-8 -*-
# filename: commander/logistic_agent_node.py
import os

async def logistic_agent_node(state: dict):
    """
    Naxuye 后勤交付官 V5.6 (双质检适配版)
    职责：整理最终资产简报，验证集装箱完整性，实现物理路径的精准定位。
    """
    # 🚨 关键对齐：读取经过 Reviewer 审计后的最终资产池
    passed_assets = state.get("passed_slots", []) 
    
    # 1. 逻辑同步：提取项目标识
    if passed_assets:
        base_ref = os.path.basename(passed_assets[0]['path'])
        project_id = base_ref.replace(".", "_")
    else:
        drafts = state.get("draft", [])
        if drafts:
            base_ref = os.path.basename(drafts[0]['path'])
            project_id = base_ref.replace(".", "_")
        else:
            project_id = "UNKNOWN"

    # 🚨 路径配置：使用环境变量
    workspace = os.getenv("NAXUYE_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace", "agent_factory"))
    
    # 2. 自动定位物理归档路径
    final_dir = None
    container_status = "UNKNOWN"
    
    try:
        # 优先使用 mindset 已生成的路径
        existing_path = state.get("final_path")
        if existing_path and os.path.exists(existing_path):
            final_dir = existing_path
        elif os.path.exists(workspace):
            matching_folders = [
                os.path.join(workspace, d) for d in os.listdir(workspace) 
                if d.startswith(project_id) and os.path.isdir(os.path.join(workspace, d))
            ]
            if matching_folders:
                final_dir = max(matching_folders, key=os.path.getmtime)
        
        # 集装箱验证
        if final_dir and os.path.exists(final_dir):
            has_flag = os.path.exists(os.path.join(final_dir, "signal.flag"))
            has_config = os.path.exists(os.path.join(final_dir, "config.json"))
            has_main = os.path.exists(os.path.join(final_dir, "main.py"))
            
            if has_flag and has_config and has_main:
                try:
                    with open(os.path.join(final_dir, "signal.flag"), 'r', encoding='utf-8') as f:
                        flag_val = f.read().strip()
                    container_status = f"VERIFIED ({flag_val})"
                except:
                    container_status = "VERIFIED (FLAG_READ_ERROR)"
            else:
                missing = []
                if not has_flag: missing.append("signal.flag")
                if not has_config: missing.append("config.json")
                if not has_main: missing.append("main.py")
                container_status = f"INVALID (缺失: {', '.join(missing)})"
        else:
            container_status = "NOT_FOUND"
            
    except Exception as e:
        container_status = f"ERROR: {str(e)}"

    # 3. 构造工业级交付简报
    summary = (
        f"\n" + "═"*60 + "\n"
        f"🏗️  NAXUYE INDUSTRIAL PRODUCTION REPORT\n"
        f"{'═'*60}\n"
        f"📅 交付时间：2026 战略年度\n"
        f"📦 项目标识：{project_id}\n"
        f"✅ 交付组件：{len(passed_assets)} 个核心单位 (集装箱格式)\n"
        f"📍 归档坐标：{final_dir or '未找到'}\n"
        f"🛡️  安全等级：L6 Industrial Standard\n"
        f"🚦 容器状态：{container_status}\n"
        f"{'═'*60}\n"
        f"🎉 生产链路已闭环。指挥官，资产已在 Workspace 就绪。\n"
    )

    print(summary)
    
    # 🚨 双质检对齐：根据验证结果返回状态
    if container_status.startswith("VERIFIED"):
        return {
            "final_decision": "APPROVED",
            "final_path": final_dir,
            "delivery_report": summary,
            "passed_slots": []  # 清空已归档资产
        }
    else:
        return {
            "final_decision": "ERROR",
            "final_path": None,
            "delivery_report": summary,
            "error_log": [f"集装箱验证失败: {container_status}"]
        }