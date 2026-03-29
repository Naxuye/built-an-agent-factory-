# filename: skills/web_scraper.py
# version: v1.1, python>=3.11
# 职责：网页抓取封装，提取文本/链接/结构化数据
# ============================================================

import time
import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("Skills.WebScraper")


# ============================================================
# 对外接口
# ============================================================

async def call(
    url: str,
    extract: str = "text",
    selector: Optional[str] = None,
    timeout: int = 30,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    抓取网页内容。

    参数：
        url     : 目标网址
        extract : 提取模式
                    - "text"  : 提取纯文本（默认）
                    - "html"  : 返回原始 HTML
                    - "links" : 提取所有链接
                    - "select": 使用 CSS 选择器提取（需配合 selector 参数）
        selector: CSS 选择器（extract="select" 时使用）
        timeout : 超时秒数
        headers : 自定义请求头，如 User-Agent、Cookie、Referer 等
                  示例：{"Cookie": "session=xxx", "Referer": "https://example.com"}
                  注意：不需要手动设置 User-Agent，http_request skill 已自动注入

    返回：
        {"status": "success", "result": ..., "url": ..., "timestamp": ...}
        {"status": "failed", "error": "...", "timestamp": ...}
    """
    if not url:
        return {"status": "failed", "error": "url 不能为空", "timestamp": time.time()}

    from skills.http_request import call as http_call

    response = await http_call(
        url=url,
        method="GET",
        headers=headers,
        timeout=timeout,
        retries=1
    )

    if response["status"] != "success":
        return {
            "status": "failed",
            "error": response.get("error", "页面请求失败"),
            "url": url,
            "timestamp": time.time()
        }

    html_content = response.get("body", "")
    if not isinstance(html_content, str):
        html_content = str(html_content)

    try:
        if extract == "html":
            return {
                "status": "success",
                "result": html_content,
                "url": url,
                "timestamp": time.time()
            }

        elif extract == "text":
            text = _html_to_text(html_content)
            return {
                "status": "success",
                "result": text,
                "url": url,
                "timestamp": time.time()
            }

        elif extract == "links":
            links = _extract_links(html_content, url)
            return {
                "status": "success",
                "result": links,
                "url": url,
                "timestamp": time.time()
            }

        elif extract == "select":
            if not selector:
                return {"status": "failed", "error": "extract='select' 需要提供 selector 参数", "timestamp": time.time()}
            elements = _css_select(html_content, selector)
            return {
                "status": "success",
                "result": elements,
                "url": url,
                "selector": selector,
                "timestamp": time.time()
            }

        else:
            return {
                "status": "failed",
                "error": f"不支持的 extract 模式: {extract}，可选: text/html/links/select",
                "timestamp": time.time()
            }

    except Exception as e:
        logger.error(f"[WebScraper] 解析失败: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "url": url, "timestamp": time.time()}


# ============================================================
# 内部解析函数（纯正则实现，不依赖 bs4）
# ============================================================

def _html_to_text(html: str) -> str:
    """从 HTML 提取纯文本（正则实现，无外部依赖）"""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_links(html: str, base_url: str = "") -> List[Dict[str, str]]:
    """提取所有链接"""
    links = []
    pattern = r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
        href = match.group(1).strip()
        text = re.sub(r'<[^>]+>', '', match.group(2)).strip()

        if href.startswith('/') and base_url:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"

        if href and not href.startswith(('#', 'javascript:', 'mailto:')):
            links.append({"href": href, "text": text[:100]})

    return links


def _css_select(html: str, selector: str) -> List[str]:
    """
    简易 CSS 选择器（支持 tag、.class、#id）。
    如果环境有 bs4 则用 bs4，否则降级为正则。
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        elements = soup.select(selector)
        return [el.get_text(strip=True) for el in elements]
    except ImportError:
        logger.info("[WebScraper] bs4 不可用，降级为正则匹配")
        tag = selector.strip().split('.')[0].split('#')[0]
        if tag:
            pattern = rf'<{tag}[^>]*>(.*?)</{tag}>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            return [re.sub(r'<[^>]+>', '', m).strip() for m in matches]
        return []