#!/usr/bin/env python3
"""
Web 搜索与抓取 CLI

提供网页搜索（Brave Search API）和网页内容抓取功能。
"""

import json
import os
import sys

import httpx
import typer

backend_path = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(help="Web 搜索与抓取工具")


def web_search(query: str, count: int = 10, api_key: str | None = None) -> str:
    """使用 Brave Search API 进行网页搜索"""
    if api_key is None:
        api_key = os.environ.get("BRAVE_API_KEY", "")

    if not api_key:
        return "错误: 未配置 BRAVE_API_KEY 环境变量"

    try:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params = {
            "q": query,
            "count": count,
        }

        with httpx.Client() as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("web", {}).get("results", [])
        if not results:
            return f"未找到关于 '{query}' 的搜索结果"

        lines = [f"搜索结果 ({len(results)} 条):\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            link = r.get("url", "")
            description = r.get("description", "")
            lines.append(f"{i}. {title}")
            lines.append(f"   链接: {link}")
            if description:
                lines.append(f"   描述: {description}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


def web_fetch(url: str) -> str:
    """抓取指定 URL 的内容并提取文本"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return json.dumps({"error": "URL 验证失败: 无效的 URL 格式"}, ensure_ascii=False)

    try:
        with httpx.Client() as client:
            response = client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            status_code = response.status_code
            final_url = str(response.url)

            result = {
                "status": status_code,
                "url": final_url,
                "content_type": content_type,
            }

            if "json" in content_type:
                try:
                    data = response.json()
                    result["extractor"] = "json"
                    result["data"] = data
                except Exception:
                    result["extractor"] = "text"
                    result["text"] = response.text
            elif "html" in content_type:
                text = response.text
                result["extractor"] = "html"
                result["text"] = text
                result["text_preview"] = text[:2000] if len(text) > 2000 else text
            else:
                result["extractor"] = "text"
                result["text"] = response.text

            return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.command("search")
def cli_search(
    query: str = typer.Argument(..., help="搜索关键词"),
    count: int = typer.Option(10, "--count", "-n", help="返回结果数量"),
    api_key: str | None = typer.Option(None, "--api-key", help="Brave API Key"),
):
    """使用 Brave Search API 搜索网页"""
    result = web_search(query, count, api_key)
    typer.echo(result)


@app.command("fetch")
def cli_fetch(
    url: str = typer.Argument(..., help="要抓取的 URL"),
):
    """抓取指定 URL 的内容"""
    result = web_fetch(url)
    typer.echo(result)


if __name__ == "__main__":
    app()
