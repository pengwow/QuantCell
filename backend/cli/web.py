#!/usr/bin/env python3
"""
Web工具命令行工具

提供网页搜索、网页内容获取等功能。
此模块为薄封装层，核心逻辑调用外部API。

使用示例:
    # 搜索网页
    python scripts/web_cli.py search --query "Bitcoin price" --count 5

    # 获取网页内容
    python scripts/web_cli.py fetch --url "https://example.com"

环境变量:
    BRAVE_API_KEY: Brave Search API密钥（搜索功能需要）
"""

import sys
import os
import json
import html
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import httpx
import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 常量
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5

# 创建主应用
app = typer.Typer(
    name="web-cli",
    help="Web工具命令行工具",
    add_completion=False,
)


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


def _validate_url(url: str) -> Tuple[bool, str]:
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


def web_search(
    query: str,
    count: int = 5,
    api_key: Optional[str] = None,
    proxy: Optional[str] = None,
) -> str:
    """
    使用 Brave Search API 搜索网页

    Args:
        query: 搜索查询
        count: 结果数量 (1-10)
        api_key: Brave Search API密钥（可选，默认从环境变量读取）
        proxy: HTTP/SOCKS5代理地址（可选）

    Returns:
        str: 搜索结果或错误信息
    """
    # 获取API密钥
    key = api_key or os.environ.get("BRAVE_API_KEY", "")
    if not key:
        return "错误: Brave Search API key 未配置。请在环境变量中设置 BRAVE_API_KEY。"

    try:
        n = min(max(count, 1), 10)

        # 获取代理配置
        proxy_url = proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

        client_kwargs = {"timeout": 10.0}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        with httpx.Client(**client_kwargs) as client:
            r = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": n},
                headers={"Accept": "application/json", "X-Subscription-Token": key},
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
        logger.error(f"搜索失败: {e}")
        return f"错误: {e}"


def web_fetch(
    url: str,
    extract_mode: str = "markdown",
    max_chars: int = 50000,
    proxy: Optional[str] = None,
) -> str:
    """
    获取 URL 并提取可读内容

    Args:
        url: 要获取的 URL
        extract_mode: 提取模式：markdown 或 text
        max_chars: 最大提取字符数
        proxy: HTTP/SOCKS5代理地址（可选）

    Returns:
        str: JSON格式的网页内容或错误信息
    """
    is_valid, error_msg = _validate_url(url)
    if not is_valid:
        return json.dumps({"error": f"URL 验证失败: {error_msg}", "url": url}, ensure_ascii=False)

    try:
        # 获取代理配置
        proxy_url = proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

        client_kwargs = {
            "follow_redirects": True,
            "max_redirects": MAX_REDIRECTS,
            "timeout": 30.0,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        with httpx.Client(**client_kwargs) as client:
            r = client.get(url, headers={"User-Agent": USER_AGENT})
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
        logger.error(f"获取网页失败: {e}")
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


# ==================== CLI 命令 ====================

@app.command("search")
def cli_search(
    query: Annotated[str, typer.Argument(help="搜索查询")],
    count: Annotated[int, typer.Option("--count", "-n", help="结果数量 (1-10)")] = 5,
    api_key: Annotated[Optional[str], typer.Option("--api-key", "-k", help="Brave Search API密钥")] = None,
    proxy: Annotated[Optional[str], typer.Option("--proxy", "-p", help="代理地址")] = None,
):
    """搜索网页"""
    result = web_search(query, count, api_key, proxy)
    typer.echo(result)


@app.command("fetch")
def cli_fetch(
    url: Annotated[str, typer.Argument(help="要获取的 URL")],
    extract_mode: Annotated[str, typer.Option("--mode", "-m", help="提取模式：markdown/text")] = "markdown",
    max_chars: Annotated[int, typer.Option("--max-chars", help="最大提取字符数")] = 50000,
    proxy: Annotated[Optional[str], typer.Option("--proxy", "-p", help="代理地址")] = None,
):
    """获取网页内容"""
    result = web_fetch(url, extract_mode, max_chars, proxy)
    typer.echo(result)


if __name__ == "__main__":
    app()
