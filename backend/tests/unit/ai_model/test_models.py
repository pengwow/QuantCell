"""
AI模型配置业务逻辑层单元测试

测试AIModelBusiness类的CRUD操作和API密钥处理功能
"""

import pytest
from unittest.mock import MagicMock, patch

from ai_model.models import AIModelBusiness


class TestAIModelBusiness:
    """AIModelBusiness单元测试类"""

    def test_mask_api_key_short(self):
        """测试短API密钥脱敏"""
        result = AIModelBusiness._mask_api_key("short")
        assert result == "********"

    def test_mask_api_key_normal(self):
        """测试正常API密钥脱敏"""
        api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"
        result = AIModelBusiness._mask_api_key(api_key)
        assert result == "sk-a...3456"
        assert "..." in result

    def test_mask_api_key_empty(self):
        """测试空API密钥脱敏"""
        result = AIModelBusiness._mask_api_key("")
        assert result == "********"

    def test_create_ai_model(self):
        """测试创建AI模型配置 - 模拟完整流程"""
        # 由于循环导入问题，这里只测试_to_dict方法
        mock_model = MagicMock()
        mock_model.id = 1
        mock_model.provider = "openai"
        mock_model.name = "Test Config"
        mock_model.api_key = "sk-test123"
        mock_model.api_host = "https://api.openai.com"
        mock_model.models = '["gpt-4", "gpt-3.5-turbo"]'
        mock_model.is_default = True
        mock_model.is_enabled = True
        mock_model.created_at = None
        mock_model.updated_at = None

        result = AIModelBusiness._to_dict(mock_model)

        assert result is not None
        assert result["provider"] == "openai"
        assert result["name"] == "Test Config"
        assert result["models"] == ["gpt-4", "gpt-3.5-turbo"]
        assert result["is_default"] is True

    @patch("ai_model.models.AIModelBusiness._get_db")
    @patch("ai_model.models.AIModelBusiness._to_dict")
    def test_get_by_id(self, mock_to_dict, mock_get_db):
        """测试根据ID获取配置"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果
        mock_model = MagicMock()
        mock_model.id = 1
        mock_model.provider = "openai"
        mock_model.name = "Test Config"
        mock_model.api_key = "sk-test123"
        mock_model.api_host = "https://api.openai.com"
        mock_model.models = '["gpt-4"]'
        mock_model.is_default = False
        mock_model.is_enabled = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model

        # 模拟_to_dict返回值
        mock_to_dict.return_value = {
            "id": 1,
            "provider": "openai",
            "name": "Test Config",
            "api_host": "https://api.openai.com",
            "models": ["gpt-4"],
            "is_default": False,
            "is_enabled": True,
        }

        result = AIModelBusiness.get_by_id(1)

        assert result is not None
        assert result["id"] == 1
        assert result["provider"] == "openai"

    @patch("ai_model.models.AIModelBusiness._get_db")
    def test_get_by_id_not_found(self, mock_get_db):
        """测试获取不存在的配置"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果为空
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AIModelBusiness.get_by_id(999)

        assert result is None

    @patch("ai_model.models.AIModelBusiness._get_db")
    @patch("ai_model.models.AIModelBusiness._to_dict")
    def test_update_ai_model(self, mock_to_dict, mock_get_db):
        """测试更新AI模型配置"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果
        mock_model = MagicMock()
        mock_model.id = 1
        mock_model.provider = "openai"
        mock_model.name = "Old Name"
        mock_model.api_key = "sk-old123"
        mock_model.api_host = None
        mock_model.models = None
        mock_model.is_default = False
        mock_model.is_enabled = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model
        mock_db.query.return_value.filter.return_value.update.return_value = None

        # 模拟_to_dict返回值
        mock_to_dict.return_value = {
            "id": 1,
            "provider": "openai",
            "name": "New Name",
            "api_host": "https://api.openai.com",
            "models": ["gpt-4"],
            "is_default": False,
            "is_enabled": True,
        }

        result = AIModelBusiness.update(
            model_id=1,
            name="New Name",
            api_host="https://api.openai.com",
            models=["gpt-4"],
        )

        assert result is not None
        assert result["name"] == "New Name"
        assert result["api_host"] == "https://api.openai.com"

    @patch("ai_model.models.AIModelBusiness._get_db")
    def test_delete_ai_model(self, mock_get_db):
        """测试删除AI模型配置"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果
        mock_model = MagicMock()
        mock_model.id = 1

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model

        result = AIModelBusiness.delete(1)

        assert result is True
        mock_db.delete.assert_called_once_with(mock_model)
        mock_db.commit.assert_called_once()

    @patch("ai_model.models.AIModelBusiness._get_db")
    def test_delete_ai_model_not_found(self, mock_get_db):
        """测试删除不存在的配置"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果为空
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = AIModelBusiness.delete(999)

        assert result is False

    @patch("ai_model.models.AIModelBusiness._get_db")
    @patch("ai_model.models.AIModelBusiness._to_dict")
    def test_list_ai_models(self, mock_to_dict, mock_get_db):
        """测试获取配置列表"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果
        mock_model1 = MagicMock()
        mock_model1.id = 1
        mock_model1.provider = "openai"
        mock_model1.name = "Config 1"

        mock_model2 = MagicMock()
        mock_model2.id = 2
        mock_model2.provider = "anthropic"
        mock_model2.name = "Config 2"

        mock_db.query.return_value.count.return_value = 2
        mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            mock_model1, mock_model2
        ]

        # 模拟_to_dict返回值
        mock_to_dict.side_effect = [
            {"id": 1, "provider": "openai", "name": "Config 1"},
            {"id": 2, "provider": "anthropic", "name": "Config 2"},
        ]

        result = AIModelBusiness.list(page=1, limit=10)

        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["page"] == 1
        assert result["limit"] == 10

    @patch("ai_model.models.AIModelBusiness._get_db")
    def test_get_api_key(self, mock_get_db):
        """测试获取API密钥"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果
        mock_model = MagicMock()
        mock_model.api_key = "sk-secret123"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model

        result = AIModelBusiness.get_api_key(1)

        assert result == "sk-secret123"

    @patch("ai_model.models.AIModelBusiness._get_db")
    def test_update_models(self, mock_get_db):
        """测试更新模型列表"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 模拟查询结果
        mock_model = MagicMock()
        mock_model.id = 1
        mock_model.models = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model

        result = AIModelBusiness.update_models(1, ["gpt-4", "gpt-3.5-turbo"])

        assert result is True
        assert mock_model.models == '["gpt-4", "gpt-3.5-turbo"]'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
