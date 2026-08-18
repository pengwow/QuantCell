"""Web 工具 - 薄封装，调用CLI层"""

from typing import Any

from agent.config.tool_params import ToolParamResolver

from .base import Tool


class WebSearchTool(Tool):
    """使用 Brave Search API 搜索网页"""

    name = "web_search"
    description = "搜索网页。返回标题、URL 和摘要。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "count": {
                "type": "integer",
                "description": "结果数量 (1-10)",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    }

    param_template = {
        "api_key": {
            "type": "string",
            "required": True,
            "sensitive": True,
            "default": "",
            "env_key": "BRAVE_API_KEY",
            "description": "Brave Search API 密钥",
        },
        "max_results": {
            "type": "integer",
            "required": False,
            "default": 5,
            "env_key": None,
            "description": "最大搜索结果数量 (1-10)",
            "validation": {"min": 1, "max": 10},
        },
        "proxy": {
            "type": "string",
            "required": False,
            "default": None,
            "env_key": None,
            "description": "HTTP/SOCKS5代理地址 (如 http://127.0.0.1:7890)",
        },
    }

    def __init__(self, api_key: str | None = None, max_results: int = 5, proxy: str | None = None):
        self._manual_api_key = api_key
        self._manual_max_results = max_results
        self._manual_proxy = proxy

    @property
    def api_key(self) -> str:
        """API Key - 优先级：构造函数参数 > 数据库/环境变量/默认值"""
        if self._manual_api_key:
            return self._manual_api_key
        return ToolParamResolver.resolve(self.name, "api_key") or ""

    @property
    def max_results(self) -> int:
        """最大结果数"""
        if self._manual_max_results != 5:
            return self._manual_max_results
        return ToolParamResolver.resolve(self.name, "max_results") or 5

    @property
    def proxy(self) -> str | None:
        """代理设置"""
        if self._manual_proxy is not None:
            return self._manual_proxy
        return ToolParamResolver.resolve(self.name, "proxy")

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        from cli.web import web_search

        return web_search(
            query,
            count=count or self.max_results,
            api_key=self.api_key,
            proxy=self.proxy,
        )


class WebFetchTool(Tool):
    """获取并提取网页内容"""

    name = "web_fetch"
    description = "获取 URL 并提取可读内容（HTML → markdown/文本）。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的 URL"},
            "extractMode": {
                "type": "string",
                "enum": ["markdown", "text"],
                "default": "markdown",
            },
            "maxChars": {"type": "integer", "minimum": 100},
        },
        "required": ["url"],
    }

    param_template = {
        "max_chars": {
            "type": "integer",
            "required": False,
            "default": 50000,
            "env_key": None,
            "description": "最大提取字符数",
        },
        "proxy": {
            "type": "string",
            "required": False,
            "default": None,
            "env_key": None,
            "description": "HTTP/SOCKS5代理地址 (如 http://127.0.0.1:7890)",
        },
    }

    def __init__(self, max_chars: int = 50000, proxy: str | None = None):
        self._manual_max_chars = max_chars
        self._manual_proxy = proxy

    @property
    def max_chars(self) -> int:
        """最大字符数"""
        if self._manual_max_chars != 50000:
            return self._manual_max_chars
        return ToolParamResolver.resolve(self.name, "max_chars") or 50000

    @property
    def proxy(self) -> str | None:
        """代理设置"""
        if self._manual_proxy is not None:
            return self._manual_proxy
        return ToolParamResolver.resolve(self.name, "proxy")

    async def execute(
        self,
        url: str,
        extractMode: str = "markdown",
        maxChars: int | None = None,
        **kwargs: Any,
    ) -> str:
        from cli.web import web_fetch

        return web_fetch(
            url,
            extract_mode=extractMode,
            max_chars=maxChars or self.max_chars,
            proxy=self.proxy,
        )
