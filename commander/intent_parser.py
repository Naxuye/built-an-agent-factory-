# filename: commander/intent_parser.py

def intent_parser(state: dict):
    """
    Naxuye 意图解析器 V5.5 (自愈兼容版)
    """
    user_task = state.get("input", "")
    print(f"🎯 [Intent] 正在解析原始指令...")
    
    # 1. 深度清洗
    clean_task = user_task.strip()
    
    # 2. 状态初始化：这是防止全链路 KeyError 的物理屏障
    # 显式初始化 passed_slots 和 audit_report
    return {
        **state, 
        "input": f"【NAXUYE 核心指令】：{clean_task}",
        "passed_slots": state.get("passed_slots", []),
        "audit_report": state.get("audit_report", {"score": 100, "error_type": "NONE"}),
        "retry_count": state.get("retry_count", 0),
        "intelligence": state.get("intelligence", "待搜集")
    }