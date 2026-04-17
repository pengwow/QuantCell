"""Web 工具 - 搜索和获取网页内容"""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import Tool

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5


def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体"""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """规范化空白字符"""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """验证 URL"""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"只允许 http/https，得到 '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "缺少域名"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """使用 Brave Search API 搜索网页"""

    name = "web_search"
    description = "搜索网页。返回标题、URL 和摘要。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "count": {"type": "integer", "description": "结果数量 (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }

    def __init__(self, api_key: str | None = None, max_results: int = 5, proxy: str | None = None):
        self._init_api_key = api_key
        self.max_results = max_results
        self.proxy = proxy

    @property
    def api_key(self) -> str:
        """运行时解析 API key"""
        return self._init_api_key or os.environ.get("BRAVE_API_KEY", "")

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        if not self.api_key:
            return (
                "错误: Brave Search API key 未配置。请在环境变量中设置 BRAVE_API_KEY。"
            )

        try:
            n = min(max(count or self.max_results, 1), 10)
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                    timeout=10.0
                )
                r.raise_for_status()

            results = r.json().get("web", {}).get("results", [])[:n]
            if not results:
                return f"未找到结果: {query}"

            lines = [f"搜索结果: {query}\n"]
            for i, item in enumerate(results, 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"错误: {e}"


class WebFetchTool(Tool):
    """获取并提取网页内容"""

    name = "web_fetch"
    description = "获取 URL 并提取可读内容（HTML → markdown/文本）。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的 URL"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }

    def __init__(self, max_chars: int = 50000, proxy: str | None = None):
        self.max_chars = max_chars
        self.proxy = proxy

    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        max_chars = maxChars or self.max_chars
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL 验证失败: {error_msg}", "url": url}, ensure_ascii=False)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0,
                proxy=self.proxy,
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                # 简化版 HTML 到文本转换
                text = _normalize(_strip_tags(r.text))
                title_match = re.search(r"<title[^>]*>([^<]*)</title>", r.text, re.I)
                title = title_match.group(1).strip() if title_match else ""
                text = f"# {title}\n\n{text}" if title else text
                extractor = "html"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return json.dumps({
                "url": url,
                "finalUrl": str(r.url),
                "status": r.status_code,
                "extractor": extractor,
                "truncated": truncated,
                "length": len(text),
                "text": text
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)
