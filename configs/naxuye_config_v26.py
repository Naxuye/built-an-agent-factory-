# filename: configs/naxuye_config_v26.py
import os


def get_power_grid():
    """延迟读取环境变量，确保 load_dotenv 已执行后再取值"""
    return {
        "STRATEGIC": [
            {
                "provider": "DeepSeek",
                "model": "deepseek-reasoner",
                "url": "https://api.deepseek.com",
                "key": os.getenv("DEEPSEEK_API_KEY")
            },
            {
                "provider": "Aliyun",
                "model": "qwen3-max",
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "key": os.getenv("DASHSCOPE_API_KEY")
            },
            {
                "provider": "Zhipu",
                "model": "glm-5",
                "url": "https://open.bigmodel.cn/api/paas/v4",
                "key": os.getenv("ZHIPUAI_API_KEY")
            },
        ],

        "ENGINEERING": [
            {
                "provider": "DeepSeek",
                "model": "deepseek-chat",
                "url": "https://api.deepseek.com",
                "key": os.getenv("DEEPSEEK_API_KEY")
            },
            {
                "provider": "Aliyun",
                "model": "qwen3.5-plus",
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "key": os.getenv("DASHSCOPE_API_KEY")
            },
            {
                "provider": "Aliyun",
                "model": "qwen3-coder-plus",
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "key": os.getenv("DASHSCOPE_API_KEY")
            },
            {
                "provider": "DeepSeek",
                "model": "deepseek-coder",
                "url": "https://api.deepseek.com",
                "key": os.getenv("DEEPSEEK_API_KEY")
            },
            {
                "provider": "Zhipu",
                "model": "glm-4-plus",
                "url": "https://open.bigmodel.cn/api/paas/v4",
                "key": os.getenv("ZHIPUAI_API_KEY")
            },
        ],

        "BASE": [
            {
                "provider": "DeepSeek",
                "model": "deepseek-chat",
                "url": "https://api.deepseek.com",
                "key": os.getenv("DEEPSEEK_API_KEY")
            },
            {
                "provider": "Aliyun",
                "model": "qwen3.5-flash",
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "key": os.getenv("DASHSCOPE_API_KEY")
            },
            {
                "provider": "Zhipu",
                "model": "glm-4-flash",
                "url": "https://open.bigmodel.cn/api/paas/v4",
                "key": os.getenv("ZHIPUAI_API_KEY")
            },
        ],

        "GLOBAL_SCOUT": {
            "primary": "TAVILY",
            "tavily_key": os.getenv("TAVILY_API_KEY"),
            "zhipu_key": os.getenv("ZHIPU_SEARCH_KEY")
        }
    }


def get_scout_config():
    return get_power_grid().get("GLOBAL_SCOUT", {})