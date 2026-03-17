# filename: configs/naxuye_config_v26.py
import os
# 移除 load_dotenv()，让 main.py 统一管理

POWER_GRID = {
    # 1. 战略级：逻辑攻坚
    "STRATEGIC": [
         {
            "provider": "Zhipu",  # 统一命名
            "model": "glm-4.7",
            "url": "https://open.bigmodel.cn/api/paas/v4",
            "key": os.getenv("ZHIPU_API_KEY")  # 统一命名
        },

        {
            "provider": "Aliyun",  # 统一为 api_router 里用的名称
            "model": "qwen-max",
            "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key": os.getenv("ALIYUN_API_KEY")  # 统一命名
        },
        {
            "provider": "DeepSeek",
            "model": "deepseek-reasoner",
            "url": "https://api.deepseek.com",
            "key": os.getenv("DEEPSEEK_API_KEY")
        }
    ],

    # 2. 工程级：高精产线
    "ENGINEERING": [
        {
            "provider": "Aliyun",
            "model": "qwen-plus",
            "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key": os.getenv("ALIYUN_API_KEY")
        },
        {
            "provider": "Zhipu",
            "model": "glm-4-plus",
            "url": "https://open.bigmodel.cn/api/paas/v4",
            "key": os.getenv("ZHIPU_API_KEY")
        },
        {
            "provider": "DeepSeek",
            "model": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "key": os.getenv("DEEPSEEK_API_KEY")
        }
    ],

    # 3. 基础级：极速试错
    "BASE": [
        {
            "provider": "Aliyun",
            "model": "qwen-turbo",
            "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key": os.getenv("ALIYUN_API_KEY")
        },
        {
            "provider": "Zhipu",
            "model": "glm-4-flash",
            "url": "https://open.bigmodel.cn/api/paas/v4",
            "key": os.getenv("ZHIPU_API_KEY")
        }
    ],

    "GLOBAL_SCOUT": {
        "primary": "TAVILY",
        "tavily_key": os.getenv("TAVILY_API_KEY"),
        "zhipu_key": os.getenv("ZHIPU_SEARCH_KEY")
    }
}

def get_power_grid():
    return POWER_GRID

def get_scout_config():
    return POWER_GRID.get("GLOBAL_SCOUT", {})