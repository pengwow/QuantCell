#!/usr/bin/env python3
"""
新闻资讯命令行工具

提供财经新闻获取、市场情绪查询等功能。
此模块为薄封装层，核心逻辑调用外部API。

使用示例:
    # 获取新闻
    python scripts/news_cli.py news --query bitcoin --count 10

    # 获取市场情绪
    python scripts/news_cli.py sentiment

环境变量:
    NEWSAPI_KEY: NewsAPI密钥（可选，不配置则返回提示信息）
"""

import sys
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import httpx
import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 创建主应用
app = typer.Typer(
    name="news-cli",
    help="新闻资讯命令行工具",
    add_completion=False,
)


def get_news(
    query: Optional[str] = None,
    category: str = "business",
    count: int = 5,
) -> str:
    """
    获取财经新闻

    Args:
        query: 搜索关键词，如 bitcoin, ethereum
        category: 新闻类别：business, technology, general
        count: 返回条数（1-20）

    Returns:
        str: 新闻列表或错误信息
    """
    api_key = os.environ.get("NEWSAPI_KEY", "")

    if not api_key:
        return (
            "新闻 API 未配置。请在环境变量中设置 NEWSAPI_KEY。\n\n"
            "或者访问以下网站获取最新资讯:\n"
            "- https://www.coindesk.com\n"
            "- https://cointelegraph.com\n"
            "- https://www.reuters.com/business/finance/"
        )

    try:
        # 同步请求
        params = {
            "apiKey": api_key,
            "category": category,
            "language": "en",
            "pageSize": min(count, 20),
        }
        if query:
            params["q"] = query
        else:
            params["q"] = "cryptocurrency"

        r = httpx.get(
            "https://newsapi.org/v2/everything",
            params=params,
            timeout=10.0
        )
        r.raise_for_status()

        data = r.json()
        articles = data.get("articles", [])

        if not articles:
            return "未找到相关新闻"

        lines = [f"最新新闻 ({query or 'cryptocurrency'}):\n"]
        for i, article in enumerate(articles[:count], 1):
            lines.append(f"{i}. {article.get('title', '')}")
            lines.append(f"   来源: {article.get('source', {}).get('name', 'N/A')}")
            lines.append(f"   时间: {article.get('publishedAt', 'N/A')[:10]}")
            lines.append(f"   链接: {article.get('url', 'N/A')}\n")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"获取新闻失败: {e}")
        return f"错误: 获取新闻失败: {e}"


def get_market_sentiment() -> str:
    """
    获取市场情绪指标（恐惧/贪婪指数）

    Returns:
        str: 市场情绪数据或错误信息
    """
    try:
        # 获取恐惧贪婪指数
        r = httpx.get(
            "https://api.alternative.me/fng/",
            timeout=10.0
        )
        r.raise_for_status()
        data = r.json()

        if data and "data" in data:
            latest = data["data"][0]
            value = latest.get("value", "N/A")
            classification = latest.get("value_classification", "N/A")
            timestamp = latest.get("timestamp", "N/A")

            return (
                f"加密货币恐惧 & 贪婪指数:\n"
                f"当前值: {value}\n"
                f"情绪: {classification}\n"
                f"更新时间: {timestamp}\n\n"
                f"指数解读:\n"
                f"0-24: 极度恐惧\n"
                f"25-49: 恐惧\n"
                f"50-74: 贪婪\n"
                f"75-100: 极度贪婪"
            )

        return "无法获取市场情绪数据"
    except Exception as e:
        logger.error(f"获取市场情绪失败: {e}")
        return f"错误: 获取市场情绪失败: {e}"


# ==================== CLI 命令 ====================

@app.command("news")
def cli_news(
    query: Annotated[Optional[str], typer.Option("--query", "-q", help="搜索关键词")] = None,
    category: Annotated[str, typer.Option("--category", "-c", help="新闻类别")] = "business",
    count: Annotated[int, typer.Option("--count", "-n", help="返回条数")] = 5,
):
    """获取财经新闻"""
    result = get_news(query, category, count)
    typer.echo(result)


@app.command("sentiment")
def cli_sentiment():
    """获取市场情绪（恐惧/贪婪指数）"""
    result = get_market_sentiment()
    typer.echo(result)


if __name__ == "__main__":
    app()
