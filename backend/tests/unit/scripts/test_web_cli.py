"""Web CLI单元测试"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestWebSearch:
    """测试 web_search 函数"""

    def test_web_search_no_api_key(self):
        """测试未配置API密钥的情况"""
        from cli.web import web_search

        with patch.dict("os.environ", {"BRAVE_API_KEY": ""}, clear=False):
            result = web_search("bitcoin")
            assert "未配置" in result
            assert "BRAVE_API_KEY" in result

    @patch("cli.web.httpx.Client")
    def test_web_search_success(self, mock_client_cls):
        """测试成功搜索"""
        from cli.web import web_search

        # 模拟API响应
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Bitcoin Price",
                        "url": "https://example.com/bitcoin",
                        "description": "Current Bitcoin price and market data",
                    },
                    {
                        "title": "Crypto News",
                        "url": "https://example.com/news",
                        "description": "Latest cryptocurrency news",
                    },
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = web_search("bitcoin", count=5, api_key="test_key")
        assert "Bitcoin Price" in result
        assert "https://example.com/bitcoin" in result

    @patch("cli.web.httpx.Client")
    def test_web_search_empty(self, mock_client_cls):
        """测试空搜索结果"""
        from cli.web import web_search

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"web": {"results": []}}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = web_search("nonexistent_topic_xyz", api_key="test_key")
        assert "未找到" in result

    @patch("cli.web.httpx.Client")
    def test_web_search_error(self, mock_client_cls):
        """测试异常处理"""
        from cli.web import web_search

        mock_client_cls.side_effect = Exception("网络错误")

        result = web_search("bitcoin", api_key="test_key")
        assert result.startswith("错误:")
        assert "网络错误" in result


class TestWebFetch:
    """测试 web_fetch 函数"""

    def test_web_fetch_invalid_url(self):
        """测试无效URL"""
        from cli.web import web_fetch

        result = web_fetch("not_a_url")
        data = json.loads(result)
        assert "error" in data
        assert "验证失败" in data["error"]

    @patch("cli.web.httpx.Client")
    def test_web_fetch_success_html(self, mock_client_cls):
        """测试成功获取HTML页面"""
        from cli.web import web_fetch

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test Page</title></head><body>Hello World</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.url = "https://example.com"
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = web_fetch("https://example.com")
        data = json.loads(result)
        assert data["status"] == 200
        assert "Test Page" in data["text"]

    @patch("cli.web.httpx.Client")
    def test_web_fetch_success_json(self, mock_client_cls):
        """测试成功获取JSON数据"""
        from cli.web import web_fetch

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_response.headers = {"content-type": "application/json"}
        mock_response.url = "https://api.example.com"
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = web_fetch("https://api.example.com")
        data = json.loads(result)
        assert data["status"] == 200
        assert data["extractor"] == "json"

    @patch("cli.web.httpx.Client")
    def test_web_fetch_error(self, mock_client_cls):
        """测试异常处理"""
        from cli.web import web_fetch

        mock_client_cls.side_effect = Exception("连接超时")

        result = web_fetch("https://example.com")
        data = json.loads(result)
        assert "error" in data
        assert "连接超时" in data["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
