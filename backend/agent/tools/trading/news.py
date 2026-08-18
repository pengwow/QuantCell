"""新闻工具 - 薄封装，调用CLI层"""

from typing import Any

from ..base import Tool


class GetNewsTool(Tool):
    """获取财经新闻"""

    name = "get_news"
    description = "获取加密货币或金融市场的最新新闻。使用 NewsAPI 或类似服务。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如 bitcoin, ethereum",
            },
            "category": {
                "type": "string",
                "description": "新闻类别",
                "enum": ["business", "technology", "general"],
                "default": "business",
            },
            "count": {
                "type": "integer",
                "description": "返回条数",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
            },
        },
        "required": [],
    }

    async def execute(
        self,
        query: str | None = None,
        category: str = "business",
        count: int = 5,
        **kwargs: Any,
    ) -> str:
        from cli.news import get_news

        return get_news(query, category, count)


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
        from cli.news import get_market_sentiment

        return get_market_sentiment()
