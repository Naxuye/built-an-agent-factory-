import os
from dotenv import load_dotenv
import configs.naxuye_config_v26 as cfg

load_dotenv()

print("="*30)
print("🔍 NAXUYE 算力链路诊断")
print("="*30)

# 1. 检查环境变量
keys = {
    "ALIYUN": os.getenv("DASHSCOPE_API_KEY"),
    "ZHIPU": os.getenv("ZHIPUAI_API_KEY"),
    "DEEPSEEK": os.getenv("DEEPSEEK_API_KEY")
}

for name, val in keys.items():
    status = f"✅ 已读取 (前4位: {val[:4]})" if val else "❌ 缺失 (None)"
    print(f"{name:<10}: {status}")

print("-"*30)

# 2. 检查配置导入是否成功
try:
    grid = cfg.POWER_GRID
    strat_model = grid["STRATEGIC"][0]["model"]
    print(f"📦 配置文件加载成功")
    print(f"🎯 战略级首选模型: {strat_model}")
except Exception as e:
    print(f"❌ 配置文件解析失败: {e}")

print("="*30)