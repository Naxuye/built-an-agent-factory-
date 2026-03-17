import copy # 🚨 必须引入

async def enhanced_dispatcher(state: AgentState):
    user_input = state.get("input", "").lower()
    strategic_keywords = ["生产", "构建", "重构", "逻辑", "设计", "开发", "agent"]
    tier = "STRATEGIC" if any(word in user_input for word in strategic_keywords) else "ENGINEERING"
    
    nodes = POWER_GRID.get(tier, POWER_GRID.get("ENGINEERING", []))
    
    # 🚨 修正 1：使用深拷贝，防止污染全局 POWER_GRID
    if nodes:
        raw_node = random.choice(nodes)
        selected_node = copy.deepcopy(raw_node) 
    else:
        selected_node = {"provider": "DEEPSEEK", "model": "deepseek-reasoner"}
    
    selected_node["tier"] = tier

    # 🚨 修正 2：物理补全 URL (防止漂移到 OpenAI 产生 401)
    # 如果配置里没写 URL，我们根据 provider 强制补上
    p = selected_node.get('provider', '').upper()
    if not selected_node.get('base_url'):
        if "ALIYUN" in p:
            selected_node['base_url'] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        elif "DEEPSEEK" in p:
            selected_node['base_url'] = "https://api.deepseek.com"
        elif "ZHIPU" in p:
            selected_node['base_url'] = "https://open.bigmodel.cn/api/paas/v4/"

    print(f"📡 [Dispatcher] 预判等级: {tier} | 注入物理算力: {p}")
    return {"active_node": selected_node}