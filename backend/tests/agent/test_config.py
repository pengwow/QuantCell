"""配置管理测试 - ToolParamManager 和相关组件"""

import pytest
from unittest.mock import MagicMock, patch

from agent.config.manager import ToolParamManager, mask_sensitive_value


class TestMaskSensitiveValue:
    """测试敏感信息脱敏"""

    def test_mask_short_value(self):
        """测试短值脱敏"""
        result = mask_sensitive_value("abc", show_chars=4)
        assert result == "***"

    def test_mask_long_value(self):
        """测试长值脱敏"""
        result = mask_sensitive_value("abcdefghijklmnop", show_chars=4)
        assert result == "abcd************"
        assert len(result) == 16

    def test_mask_none_value(self):
        """测试None值脱敏"""
        result = mask_sensitive_value(None)
        assert result == "未配置"

    def test_mask_empty_value(self):
        """测试空值脱敏"""
        result = mask_sensitive_value("")
        assert result == "未配置"

    def test_mask_exact_length(self):
        """测试精确长度脱敏"""
        result = mask_sensitive_value("1234", show_chars=4)
        assert result == "****"

    def test_mask_custom_show_chars(self):
        """测试自定义显示字符数"""
        result = mask_sensitive_value("1234567890", show_chars=2)
        assert result == "12********"


class TestToolParamManager:
    """测试 ToolParamManager"""

    @pytest.fixture
    def mock_db(self):
        """Mock数据库会话"""
        with patch('agent.config.manager._get_db_session') as mock:
            mock_db = MagicMock()
            mock.return_value = (mock_db, MagicMock)
            yield mock_db

    def test_get_tool_params(self, mock_db):
        """测试获取工具参数"""
        # Mock数据库返回
        mock_config = MagicMock()
        mock_config.value = "test-value"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
        
        # Mock模板
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "api_key": {
                    "type": "string",
                    "sensitive": True,
                    "default": "",
                    "env_key": "TEST_API_KEY",
                    "description": "Test API key",
                }
            }
            
            params = ToolParamManager.get_tool_params("test_tool")
            
            assert "api_key" in params
            # 脱敏后的值应该是前4个字符 + 星号
            assert params["api_key"]["value"].startswith("test")
            assert params["api_key"]["configured"] is True
            assert params["api_key"]["source"] == "database"
            assert params["api_key"]["sensitive"] is True

    def test_get_tool_params_include_sensitive(self, mock_db):
        """测试获取工具参数（包含敏感信息）"""
        mock_config = MagicMock()
        mock_config.value = "secret-key-12345"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
        
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "api_key": {
                    "type": "string",
                    "sensitive": True,
                    "default": "",
                    "env_key": None,
                    "description": "Test API key",
                }
            }
            
            params = ToolParamManager.get_tool_params("test_tool", include_sensitive=True)
            
            assert params["api_key"]["value"] == "secret-key-12345"

    def test_get_tool_params_from_env(self, mock_db, monkeypatch):
        """测试从环境变量获取参数"""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        monkeypatch.setenv("TEST_API_KEY", "env-key-value")
        
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "api_key": {
                    "type": "string",
                    "sensitive": False,
                    "default": "",
                    "env_key": "TEST_API_KEY",
                    "description": "Test API key",
                }
            }
            
            params = ToolParamManager.get_tool_params("test_tool")
            
            assert params["api_key"]["value"] == "env-key-value"
            assert params["api_key"]["source"] == "environment"

    def test_get_tool_params_from_default(self, mock_db, monkeypatch):
        """测试获取默认参数"""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        monkeypatch.delenv("TEST_API_KEY", raising=False)
        
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "api_key": {
                    "type": "string",
                    "sensitive": False,
                    "default": "default-key",
                    "env_key": "TEST_API_KEY",
                    "description": "Test API key",
                }
            }
            
            params = ToolParamManager.get_tool_params("test_tool")
            
            assert params["api_key"]["value"] == "default-key"
            assert params["api_key"]["source"] == "default"

    def test_set_tool_param(self, mock_db):
        """测试设置工具参数"""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "api_key": {
                    "type": "string",
                    "sensitive": True,
                    "default": "",
                    "env_key": None,
                    "description": "Test API key",
                }
            }
            
            with patch('agent.config.tool_params.ToolParamResolver.validate') as mock_validate:
                mock_validate.return_value = (True, "")
                
                result = ToolParamManager.set_tool_param("test_tool", "api_key", "new-key")
                
                assert result is True
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()

    def test_set_tool_param_invalid(self, mock_db):
        """测试设置无效参数"""
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = None
            
            with pytest.raises(ValueError) as exc_info:
                ToolParamManager.set_tool_param("test_tool", "api_key", "new-key")
            
            assert "未知参数" in str(exc_info.value)

    def test_delete_tool_param(self, mock_db):
        """测试删除工具参数"""
        mock_config = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
        
        result = ToolParamManager.delete_tool_param("test_tool", "api_key")
        
        assert result is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_batch_update(self, mock_db):
        """测试批量更新"""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "param1": {"type": "string", "sensitive": False, "default": "", "env_key": None, "description": ""},
                "param2": {"type": "string", "sensitive": False, "default": "", "env_key": None, "description": ""},
            }
            
            with patch('agent.config.tool_params.ToolParamResolver.validate') as mock_validate:
                mock_validate.return_value = (True, "")
                
                result = ToolParamManager.batch_update("test_tool", {
                    "param1": "value1",
                    "param2": "value2",
                })
                
                assert "param1" in result["updated"]
                assert "param2" in result["updated"]
                assert result["errors"] == []

    def test_export_config(self, mock_db):
        """测试导出配置"""
        mock_config = MagicMock()
        mock_config.value = "test-value"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
        
        with patch('agent.config.templates.get_all_tools') as mock_tools:
            mock_tools.return_value = {
                "test_tool": {
                    "api_key": {
                        "type": "string",
                        "sensitive": True,
                        "default": "",
                        "env_key": None,
                        "description": "Test API key",
                    }
                }
            }
            
            config = ToolParamManager.export_config("test_tool")
            
            assert "export_time" in config
            assert "version" in config
            assert "tools" in config
            assert "test_tool" in config["tools"]

    def test_import_config(self, mock_db):
        """测试导入配置"""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        
        with patch('agent.config.templates.get_tool_template') as mock_template:
            mock_template.return_value = {
                "api_key": {"type": "string", "sensitive": True, "default": "", "env_key": None, "description": ""},
            }
            
            with patch('agent.config.tool_params.ToolParamResolver.validate') as mock_validate:
                mock_validate.return_value = (True, "")
                
                imported, skipped, errors = ToolParamManager.import_config({
                    "tools": {
                        "test_tool": {
                            "api_key": "imported-key",
                        }
                    }
                })
                
                assert imported == 1
                assert skipped == 0
                assert errors == []


class TestToolParamValidator:
    """测试参数验证器"""

    def test_validate_string(self):
        """测试字符串验证"""
        from agent.config.manager import ToolParamValidator
        
        with patch('agent.config.tool_params.ToolParamResolver.validate') as mock_validate:
            mock_validate.return_value = (True, "")
            
            is_valid, error = ToolParamValidator.validate("test_tool", "param", "value")
            
            assert is_valid is True
            assert error == ""

    def test_validate_invalid(self):
        """测试无效参数验证"""
        from agent.config.manager import ToolParamValidator
        
        with patch('agent.config.tool_params.ToolParamResolver.validate') as mock_validate:
            mock_validate.return_value = (False, "Invalid parameter")
            
            is_valid, error = ToolParamValidator.validate("test_tool", "param", "invalid")
            
            assert is_valid is False
            assert error == "Invalid parameter"


class TestConfigSchemas:
    """测试配置数据结构"""

    def test_param_template_item(self):
        """测试参数模板项"""
        from agent.config.schemas import ParamTemplateItem
        
        item = ParamTemplateItem(
            type="string",
            required=True,
            sensitive=False,
            default="test",
            env_key="TEST_KEY",
            description="Test parameter",
        )
        
        assert item.type == "string"
        assert item.required is True
        assert item.sensitive is False
        assert item.default == "test"
        assert item.env_key == "TEST_KEY"
        assert item.description == "Test parameter"

    def test_tool_param_template(self):
        """测试工具参数模板"""
        from agent.config.schemas import ToolParamTemplate, ParamTemplateItem
        
        template = ToolParamTemplate(
            name="test_tool",
            description="Test tool",
            params={
                "api_key": ParamTemplateItem(
                    type="string",
                    required=True,
                    sensitive=True,
                )
            }
        )
        
        assert template.name == "test_tool"
        assert template.description == "Test tool"
        assert "api_key" in template.params

    def test_param_value_info(self):
        """测试参数值信息"""
        from agent.config.schemas import ParamValueInfo
        
        info = ParamValueInfo(
            value="test-value",
            configured=True,
            source="database",
            sensitive=False,
            type="string",
            description="Test parameter",
        )
        
        assert info.value == "test-value"
        assert info.configured is True
        assert info.source == "database"
        assert info.sensitive is False

    def test_tool_params_response(self):
        """测试工具参数响应"""
        from agent.config.schemas import ToolParamsResponse, ParamValueInfo
        
        response = ToolParamsResponse(
            tool_name="test_tool",
            params={
                "api_key": ParamValueInfo(
                    value="****",
                    configured=True,
                    source="database",
                    sensitive=True,
                )
            }
        )
        
        assert response.tool_name == "test_tool"
        assert "api_key" in response.params

    def test_batch_update_request(self):
        """测试批量更新请求"""
        from agent.config.schemas import BatchUpdateRequest
        
        request = BatchUpdateRequest(
            params={"param1": "value1", "param2": "value2"},
            overwrite=True,
        )
        
        assert request.params["param1"] == "value1"
        assert request.overwrite is True

    def test_import_export_result(self):
        """测试导入导出结果"""
        from agent.config.schemas import ImportExportResult
        
        result = ImportExportResult(
            imported=5,
            skipped=2,
            errors=["Error 1", "Error 2"],
        )
        
        assert result.imported == 5
        assert result.skipped == 2
        assert len(result.errors) == 2
