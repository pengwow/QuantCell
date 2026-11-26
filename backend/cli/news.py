#!/usr/bin/env python3
"""
新闻与市场情绪 CLI

提供新闻搜索（NewsAPI）和市场情绪指数查询功能。
"""

import os
import sys
from datetime import datetime

import httpx
import typer

backend_path = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(help="新闻与市场情绪工具")


class NewsError(Exception):
    """失败信号：命令层捕获后写 stderr 并以非 0 退出。

    agent 工具仍按字符串返回值使用，只有 CLI 传 raise_on_error=True。
    """


def get_news(
    query: str,
    category: str = "general",
    count: int = 10,
    *,
    raise_on_error: bool = False,
) -> str:
    """从 NewsAPI 获取新闻"""
    api_key = os.environ.get("NEWSAPI_KEY", "")

    if not api_key:
        msg = "错误: 未配置 NEWSAPI_KEY 环境变量"
        if raise_on_error:
            raise NewsError(msg)
        return msg

    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": count,
            "language": "en",
            "apiKey": api_key,
        }

        if category and category != "general":
            params["category"] = category

        response = httpx.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        if not articles:
            return f"未找到关于 '{query}' 的新闻"

        lines = [f"新闻列表 ({len(articles)} 条):\n"]
        for i, article in enumerate(articles, 1):
            title = article.get("title", "无标题")
            source = article.get("source", {}).get("name", "未知来源")
            published = article.get("publishedAt", "")
            link = article.get("url", "")
            description = article.get("description", "")

            lines.append(f"{i}. [{source}] {title}")
            lines.append(f"   时间: {published}")
            lines.append(f"   链接: {link}")
            if description:
                lines.append(f"   描述: {description}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        msg = f"错误: {e}"
        if raise_on_error:
            raise NewsError(msg) from e
        return msg


def get_market_sentiment(*, raise_on_error: bool = False) -> str:
    """获取市场情绪指数（恐惧与贪婪指数）"""
    try:
        url = "https://api.alternative.me/fng/"
        params = {
            "limit": 1,
            "format": "json",
        }

        response = httpx.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not data or "data" not in data or not data["data"]:
            return "无法获取市场情绪数据"

        item = data["data"][0]
        value = item.get("value", "N/A")
        classification = item.get("value_classification", "N/A")
        timestamp = item.get("timestamp", "")

        try:
            dt = datetime.fromtimestamp(int(timestamp))
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError):
            time_str = str(timestamp)

        result = f"市场情绪指数 (恐惧与贪婪指数):\n  数值: {value}\n  分类: {classification}\n  时间: {time_str}"

        return result
    except Exception as e:
        msg = f"错误: {e}"
        if raise_on_error:
            raise NewsError(msg) from e
        return msg


@app.command("news")
def cli_news(
    query: str = typer.Argument(..., help="搜索关键词"),
    category: str = typer.Option("general", "--category", "-c", help="新闻分类"),
    count: int = typer.Option(10, "--count", "-n", help="返回条数"),
):
    """获取相关新闻"""
    try:
        result = get_news(query, category, count, raise_on_error=True)
    except NewsError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    typer.echo(result)


@app.command("sentiment")
def cli_sentiment():
    """获取市场情绪指数"""
    try:
        result = get_market_sentiment(raise_on_error=True)
    except NewsError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    typer.echo(result)


if __name__ == "__main__":
    app()
