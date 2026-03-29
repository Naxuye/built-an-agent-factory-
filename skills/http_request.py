# filename: skills/http_request.py
# version: v1.1, python>=3.11
# 职责：HTTP 请求封装，带超时、重试、错误处理、鉴权、默认UA
# ============================================================

import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Skills.HttpRequest")

# 延迟导入，避免未安装时直接崩
_requests = None

def _ensure_requests():
    global _requests
    if _requests is None:
        import requests
        _requests = requests
    return _requests


# ============================================================
# 配置
# ============================================================

DEFAULT_TIMEOUT    = 30
DEFAULT_RETRIES    = 2
RETRY_DELAY        = 1.0
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; NaxuyeAgent/1.0; +https://github.com/Naxuye)"


# ============================================================
# 对外接口
# ============================================================

async def call(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    data: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    auth: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    发送 HTTP 请求。

    参数：
        url       : 请求地址
        method    : GET / POST / PUT / DELETE
        headers   : 请求头（自动注入 User-Agent，可覆盖）
        params    : URL 查询参数
        json_data : JSON 请求体
        data      : 原始请求体
        timeout   : 超时秒数
        retries   : 重试次数
        auth      : 鉴权配置，支持两种格式：
                      {"type": "bearer", "token": "xxx"}
                      {"type": "basic", "username": "xxx", "password": "xxx"}

    返回：
        {"status": "success", "status_code": 200, "body": ..., "timestamp": ...}
        {"status": "failed", "error": "...", "timestamp": ...}
    """
    if not url:
        return {"status": "failed", "error": "url 不能为空", "timestamp": time.time()}

    requests = _ensure_requests()
    method = method.upper()
    last_error = None

    # 合并请求头：默认 User-Agent，调用方可覆盖
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(headers)

    # 注入鉴权头
    if auth:
        auth_type = auth.get("type", "").lower()
        if auth_type == "bearer":
            merged_headers["Authorization"] = f"Bearer {auth.get('token', '')}"
        elif auth_type == "basic":
            import base64
            credentials = base64.b64encode(
                f"{auth.get('username', '')}:{auth.get('password', '')}".encode()
            ).decode()
            merged_headers["Authorization"] = f"Basic {credentials}"

    for attempt in range(retries + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=merged_headers,
                params=params,
                json=json_data,
                data=data,
                timeout=timeout
            )

            # 尝试解析 JSON，失败则返回文本
            try:
                body = response.json()
            except (ValueError, Exception):
                body = response.text

            return {
                "status": "success",
                "status_code": response.status_code,
                "body": body,
                "headers": dict(response.headers),
                "timestamp": time.time()
            }

        except requests.exceptions.Timeout:
            last_error = f"请求超时 ({timeout}s)"
            logger.warning(f"[HttpRequest] {url} 超时 (第{attempt+1}次)")
        except requests.exceptions.ConnectionError as e:
            last_error = f"连接失败: {str(e)[:100]}"
            logger.warning(f"[HttpRequest] {url} 连接失败 (第{attempt+1}次)")
        except Exception as e:
            last_error = f"请求异常: {str(e)[:100]}"
            logger.error(f"[HttpRequest] {url} 异常: {e}")
            break  # 非网络错误不重试

        if attempt < retries:
            import asyncio
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return {
        "status": "failed",
        "error": last_error,
        "url": url,
        "attempts": retries + 1,
        "timestamp": time.time()
    }