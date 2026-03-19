# -*- coding: utf-8 -*-
# filename: commander/api_router.py
import os
import json
import aiohttp
import asyncio
from typing import Dict, Any, Optional

# 导入智能路由适配器
try:
    from commander.smart_client import get_smart_client
except ImportError:
    # 降级方案：如果没有smart_client，定义一个简单的
    async def get_smart_client(url=None):
        import httpx
        return httpx.AsyncClient(timeout=60.0)

async def call_deepseek(prompt: str, system_prompt: str = "", model: str = "deepseek-chat", **kwargs):
    """调用 DeepSeek API"""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_CHAT_API_KEY")
    if not api_key:
        raise Exception("DEEPSEEK_API_KEY 未配置")
    
    url = "https://api.deepseek.com/v1/chat/completions"
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 4000)
    }
    
    # 使用智能客户端
    client = await get_smart_client(url)
    async with client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()  # ✅ 无需 await
        return result['choices'][0]['message']['content']

async def call_zhipu(prompt: str, system_prompt: str = "", model: str = "glm-4-plus", **kwargs):
    """调用智谱 API"""
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        raise Exception("ZHIPUAI_API_KEY 未配置")
    
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 4000)
    }
    
    client = await get_smart_client(url)
    async with client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()  # ✅ 修复：去掉 await
        return result['choices'][0]['message']['content']

async def call_aliyun(prompt: str, system_prompt: str = "", model: str = "qwen-max", **kwargs):
    """调用阿里云百炼 API"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise Exception("DASHSCOPE_API_KEY 未配置")
    
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 4000)
    }
    
    client = await get_smart_client(url)
    async with client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()  # ✅ 修复：去掉 await
        return result['choices'][0]['message']['content']

async def call_chaosuan(prompt: str, system_prompt: str = "", model: str = "Qwen3-235B-A22B", **kwargs):
    """调用超算 API（兼容 OpenAI 格式）"""
    api_key = os.getenv("CHAOSUAN_API_KEY")
    if not api_key:
        raise Exception("CHAOSUAN_API_KEY 未配置")
    
    base_url = os.getenv("CHAOSUAN_BASE_URL", "https://api.chaosuansishen.com/v1")
    url = f"{base_url}/chat/completions"
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 4000)
    }
    
    client = await get_smart_client(url)
    async with client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']

async def smart_dispatch(
    prompt: str,
    system_prompt: str = "",
    tier: str = "ENGINEERING",
    json_mode: bool = False,
    active_node: Optional[Dict[str, Any]] = None
):
    """
    Naxuye 智能路由分发器 (核心意志接驳点)
    
    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        tier: 算力等级 (STRATEGIC | ENGINEERING | BASE)
        json_mode: 是否返回 JSON 格式
        active_node: 物理算力节点配置，包含 provider 和 model
    
    Returns:
        str: API 响应内容
    """
    active_node = active_node or {}
    provider = active_node.get("provider", "DEFAULT")
    model = active_node.get("model")
    
    # 根据 provider 路由到对应 API
    try:
        if provider == "DeepSeek":
            result = await call_deepseek(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model or "deepseek-chat"
            )
        elif provider == "Zhipu":
            result = await call_zhipu(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model or "glm-4-plus"
            )
        elif provider == "Aliyun":
            result = await call_aliyun(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model or "qwen3.5-plus"
            )
        elif provider == "Chaosuan":
            result = await call_chaosuan(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model or "Qwen3-235B-A22B"
            )
        else:
            # 默认使用 DeepSeek
            print(f"⚠️ 未知 provider {provider}，使用 DeepSeek 兜底")
            result = await call_deepseek(
                prompt=prompt,
                system_prompt=system_prompt,
                model="deepseek-chat"
            )
        
        # JSON 模式处理
        if json_mode:
            try:
                json.loads(result)
                return result
            except:
                import re
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if json_match:
                    return json_match.group()
                else:
                    raise Exception("API 未返回合法 JSON")
        
        return result
        
    except Exception as e:
        print(f"❌ [smart_dispatch] 调用失败: {repr(e)}")
        raise

# 导出
__all__ = ['smart_dispatch']