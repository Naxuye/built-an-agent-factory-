# -*- coding: utf-8 -*-
# filename: commander/smart_client.py
import os
import httpx
from urllib.parse import urlparse

# 🚨 关键：加上 async
async def get_smart_client(url: str = None):
    """
    【2026 智能路由适配器】
    原理：根据 URL 自动判定是否绕过系统代理（VPN）
    """
    if url is None:
        url = os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com")
    
    domain = urlparse(url).netloc
    
    # 国内 API 域名白名单
    direct_domains = [
        "aliyuncs.com",       # 阿里云
        "xfyun.cn",           # 讯飞
        "baidubce.com",       # 百度
        "volcengineapi.com",  # 字节/火山
        "deepseek.com",       # DeepSeek
        "bigmodel.cn",        # 智谱
        "open.bigmodel.cn",   # 智谱 API
        "zhipuai.cn",         # 智谱官网
        "localhost", "127.0.0.1"
    ]
    
    # 判断是否直连
    is_direct = any(d in domain for d in direct_domains)
    
    if is_direct:
        print(f"📡 [Router] 检测到国内节点 {domain}，已强制启用【物理直连】模式")
        return httpx.AsyncClient(
            trust_env=False, 
            timeout=httpx.Timeout(120.0, connect=15.0),
            follow_redirects=True
        )
    else:
        print(f"🌐 [Router] 检测到海外节点 {domain}，已启用【VPN 链路】模式")
        return httpx.AsyncClient(
            trust_env=True, 
            timeout=httpx.Timeout(120.0, connect=15.0),
            follow_redirects=True
        )

__all__ = ['get_smart_client']