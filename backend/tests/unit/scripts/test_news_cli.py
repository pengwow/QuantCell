"""新闻CLI单元测试"""

import pytest
from unittest.mock import patch, MagicMock


class TestGetNews:
    """测试 get_news 函数"""

    def test_get_news_no_api_key(self):
        """测试未配置API密钥的情况"""
        from scripts.news_cli import get_news

        with patch.dict("os.environ", {"NEWSAPI_KEY": ""}, clear=False):
            result = get_news("bitcoin")
            assert "未配置" in result
            assert "NEWSAPI_KEY" in result

    @patch("scripts.news_cli.httpx.get")
    def test_get_news_success(self, mock_get):
        """测试成功获取新闻"""
        from scripts.news_cli import get_news

        # 模拟API响应
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "articles": [
                {
                    "title": "Bitcoin Price Surges",
                    "source": {"name": "CoinDesk"},
                    "publishedAt": "2024-01-15T10:00:00Z",
                    "url": "https://example.com/news1",
                },
                {
                    "title": "Crypto Market Update",
                    "source": {"name": "Reuters"},
                    "publishedAt": "2024-01-15T09:00:00Z",
                    "url": "https://example.com/news2",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict("os.environ", {"NEWSAPI_KEY": "test_key"}, clear=False):
            result = get_news("bitcoin", "business", 5)
            assert "Bitcoin Price Surges" in result
            assert "CoinDesk" in result

    @patch("scripts.news_cli.httpx.get")
    def test_get_news_empty(self, mock_get):
        """测试空新闻结果"""
        from scripts.news_cli import get_news

        mock_response = MagicMock()
        mock_response.json.return_value = {"articles": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict("os.environ", {"NEWSAPI_KEY": "test_key"}, clear=False):
            result = get_news("nonexistent_topic")
            assert "未找到" in result

    @patch("scripts.news_cli.httpx.get")
    def test_get_news_error(self, mock_get):
        """测试异常处理"""
        from scripts.news_cli import get_news

        mock_get.side_effect = Exception("网络错误")

        with patch.dict("os.environ", {"NEWSAPI_KEY": "test_key"}, clear=False):
            result = get_news("bitcoin")
            assert result.startswith("错误:")
            assert "网络错误" in result


class TestGetMarketSentiment:
    """测试 get_market_sentiment 函数"""

    @patch("scripts.news_cli.httpx.get")
    def test_get_market_sentiment_success(self, mock_get):
        """测试成功获取市场情绪"""
        from scripts.news_cli import get_market_sentiment

        # 模拟API响应
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "value": "65",
                    "value_classification": "Greed",
                    "timestamp": "1234567890",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = get_market_sentiment()
        assert "65" in result
        assert "Greed" in result

    @patch("scripts.news_cli.httpx.get")
    def test_get_market_sentiment_empty(self, mock_get):
        """测试空市场情绪数据"""
        from scripts.news_cli import get_market_sentiment

        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = get_market_sentiment()
        assert "无法获取" in result

    @patch("scripts.news_cli.httpx.get")
    def test_get_market_sentiment_error(self, mock_get):
        """测试异常处理"""
        from scripts.news_cli import get_market_sentiment

        mock_get.side_effect = Exception("API错误")

        result = get_market_sentiment()
        assert result.startswith("错误:")
        assert "API错误" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
