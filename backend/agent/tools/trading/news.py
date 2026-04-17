"""新闻工具 - 获取财经新闻和市场资讯"""

import os
from typing import Any

import httpx

from ..base import Tool


class GetNewsTool(Tool):
    """获取财经新闻"""

    name = "get_news"
    description = "获取加密货币或金融市场的最新新闻。使用 NewsAPI 或类似服务。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，如 bitcoin, ethereum"},
            "category": {"type": "string", "description": "新闻类别", "enum": ["business", "technology", "general"], "default": "business"},
            "count": {"type": "integer", "description": "返回条数", "minimum": 1, "maximum": 20, "default": 5},
        },
        "required": [],
    }

    async def execute(
        self,
        query: str | None = None,
        category: str = "business",
        count: int = 5,
        **kwargs: Any
    ) -> str:
        api_key = os.environ.get("NEWSAPI_KEY", "")
        
        if not api_key:
            # 返回模拟数据或错误信息
            return (
                "新闻 API 未配置。请在环境变量中设置 NEWSAPI_KEY。\n\n"
                "或者访问以下网站获取最新资讯:\n"
                "- https://www.coindesk.com\n"
                "- https://cointelegraph.com\n"
                "- https://www.reuters.com/business/finance/"
            )

        try:
            async with httpx.AsyncClient() as client:
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

                r = await client.get(
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
            return f"错误: 获取新闻失败: {e}"


class GetMarketSentimentTool(Tool):
    """获取市场情绪"""

    name = "get_market_sentiment"
    description = "获取当前市场情绪指标（恐惧/贪婪指数等）。"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        try:
            # 获取恐惧贪婪指数
            async with httpx.AsyncClient() as client:
                r = await client.get(
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
            return f"错误: 获取市场情绪失败: {e}"
