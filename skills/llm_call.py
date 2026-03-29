# filename: skills/llm_call.py
# version: v1.0, python>=3.11
# 职责：统一 LLM 调用接口，支持多模型切换
# ============================================================

import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Skills.LLMCall")


# ============================================================
# 模型配置
# ============================================================

PROVIDERS = {
    "dashscope": {
        "env_key": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "default_model": "qwen-turbo"
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "default_model": "deepseek-chat"
    },
    "zhipuai": {
        "env_key": "ZHIPUAI_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "default_model": "glm-4-flash"
    },
    "chaosuan": {
        "env_key": "CHAOSUAN_API_KEY",
        "base_url": "https://api.chaosuan.com/v1/chat/completions",
        "default_model": "chaosuan-default"
    }
}


# ============================================================
# 对外接口
# ============================================================

async def call(
    prompt: str,
    provider: str = "dashscope",
    model: Optional[str] = None,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: int = 60
) -> Dict[str, Any]:
    """
    调用 LLM API。

    参数：
        prompt: 用户提示词
        provider: 模型提供商（dashscope/deepseek/zhipuai/chaosuan）
        model: 模型名称（不填则用 provider 默认模型）
        system_prompt: 系统提示词
        temperature: 温度
        max_tokens: 最大输出 token
        timeout: 超时秒数

    返回：
        {"status": "success", "content": "LLM 回复文本", "model": ..., "timestamp": ...}
        {"status": "failed", "error": "...", "timestamp": ...}
    """
    if not prompt:
        return {"status": "failed", "error": "prompt 不能为空", "timestamp": time.time()}

    # 获取 provider 配置
    config = PROVIDERS.get(provider)
    if not config:
        return {
            "status": "failed",
            "error": f"不支持的 provider: {provider}，可选: {list(PROVIDERS.keys())}",
            "timestamp": time.time()
        }

    api_key = os.getenv(config["env_key"], "")
    if not api_key:
        return {
            "status": "failed",
            "error": f"未配置 {config['env_key']} 环境变量",
            "timestamp": time.time()
        }

    base_url = config["base_url"]
    model_name = model or config["default_model"]

    # 构造请求
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # 使用 http_request skill 发送请求
    from skills.http_request import call as http_call

    result = await http_call(
        url=base_url,
        method="POST",
        headers=headers,
        json_data=payload,
        timeout=timeout,
        retries=1
    )

    if result["status"] != "success":
        return {
            "status": "failed",
            "error": result.get("error", "HTTP 请求失败"),
            "provider": provider,
            "model": model_name,
            "timestamp": time.time()
        }

    # 解析 LLM 响应
    try:
        body = result["body"]
        if isinstance(body, str):
            import json
            body = json.loads(body)

        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})

        return {
            "status": "success",
            "content": content,
            "provider": provider,
            "model": model_name,
            "usage": usage,
            "timestamp": time.time()
        }
    except (KeyError, IndexError, TypeError) as e:
        return {
            "status": "failed",
            "error": f"LLM 响应解析失败: {str(e)[:100]}",
            "raw_body": str(result.get("body", ""))[:300],
            "provider": provider,
            "model": model_name,
            "timestamp": time.time()
        }