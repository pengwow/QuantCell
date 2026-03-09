"""
策略生成API集成测试

测试AI策略生成相关的所有API端点，包括：
- 策略生成（同步/流式）
- 代码验证
- 历史记录管理
- 模板管理
- 性能统计
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime

from main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """模拟JWT认证"""
    with patch("utils.auth.decode_jwt_token") as mock_decode:
        mock_decode.return_value = {"sub": "test_user", "name": "Test User"}
        yield mock_decode


@pytest.fixture
def mock_should_refresh():
    """模拟不需要刷新token"""
    with patch("utils.auth.should_refresh_token") as mock_refresh:
        mock_refresh.return_value = False
        yield mock_refresh


@pytest.fixture
def auth_headers():
    """认证请求头"""
    return {"Authorization": "Bearer test_token"}


class TestStrategyGenerateAPI:
    """策略生成API测试类"""

    def test_generate_sync_success(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试同步生成策略成功"""
        with patch("ai_model.routes_strategy.create_strategy_generator") as mock_create:
            mock_generator = MagicMock()
            mock_generator.model_id = "gpt-4"
            mock_generator.generate_strategy.return_value = {
                "success": True,
                "code": "class TestStrategy:\n    pass",
                "raw_content": "这是一个测试策略",
                "metadata": {
                    "model": "gpt-4",
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "elapsed_time": 2.5,
                    "request_id": "req_123"
                }
            }
            mock_create.return_value = mock_generator

            response = client.post(
                "/api/ai-models/strategy/generate-sync",
                headers=auth_headers,
                json={
                    "requirement": "创建一个简单的测试策略",
                    "model_id": "gpt-4",
                    "temperature": 0.7
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "code" in data["data"]

    def test_generate_sync_no_config(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试未配置AI模型时的同步生成"""
        with patch("ai_model.routes_strategy.get_default_ai_config") as mock_config:
            mock_config.return_value = None

            response = client.post(
                "/api/ai-models/strategy/generate-sync",
                headers=auth_headers,
                json={"requirement": "创建一个简单的测试策略"}
            )

        assert response.status_code == 400
        data = response.json()
        assert "未配置默认AI模型" in str(data.get("detail", {}))

    def test_validate_code_success(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试代码验证成功"""
        response = client.post(
            "/api/ai-models/strategy/validate-code",
            headers=auth_headers,
            json={
                "code": "class TestStrategy:\n    def __init__(self):\n        pass",
                "language": "python"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert data["data"]["valid"] is True

    def test_validate_code_with_syntax_error(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试包含语法错误的代码验证"""
        response = client.post(
            "/api/ai-models/strategy/validate-code",
            headers=auth_headers,
            json={
                "code": "class TestStrategy:\n    def __init__(self):\n        pass\n    def broken(  # 缺少右括号",
                "language": "python"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["valid"] is False
        assert len(data["data"]["errors"]) > 0


class TestStrategyHistoryAPI:
    """策略历史记录API测试类"""

    def test_get_history_list_empty(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试获取空历史列表"""
        response = client.get(
            "/api/ai-models/strategy/history",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "list" in data["data"]
        assert data["data"]["list"] == []

    def test_get_history_list_with_pagination(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试分页获取历史列表"""
        response = client.get(
            "/api/ai-models/strategy/history?page=1&page_size=10",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "pagination" in data["data"]
        assert data["data"]["pagination"]["page"] == 1
        assert data["data"]["pagination"]["page_size"] == 10

    def test_get_history_list_with_filters(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试带筛选条件的历史列表"""
        response = client.get(
            "/api/ai-models/strategy/history?status=success&model_id=gpt-4",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_history_detail_not_found(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试获取不存在的历史详情"""
        response = client.get(
            "/api/ai-models/strategy/history/non_existent_id",
            headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "历史记录不存在" in str(data.get("detail", ""))

    def test_delete_history_not_found(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试删除不存在的历史记录"""
        response = client.delete(
            "/api/ai-models/strategy/history/non_existent_id",
            headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "历史记录不存在" in str(data.get("detail", ""))

    def test_regenerate_from_history_not_found(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试基于不存在的历史重新生成"""
        response = client.post(
            "/api/ai-models/strategy/history/non_existent_id/regenerate",
            headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "历史记录不存在" in str(data.get("detail", ""))


class TestStrategyTemplateAPI:
    """策略模板API测试类"""

    def test_get_template_list(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试获取模板列表"""
        response = client.get(
            "/api/ai-models/strategy/templates",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "list" in data["data"]
        assert "total" in data["data"]

    def test_get_template_list_with_category_filter(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试按分类筛选模板"""
        response = client.get(
            "/api/ai-models/strategy/templates?category=trend_following",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_template_list_with_tag_filter(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试按标签筛选模板"""
        response = client.get(
            "/api/ai-models/strategy/templates?tag=趋势",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_template_detail_success(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试获取模板详情成功"""
        response = client.get(
            "/api/ai-models/strategy/templates/tpl_001",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert data["data"]["id"] == "tpl_001"

    def test_get_template_detail_not_found(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试获取不存在的模板详情"""
        response = client.get(
            "/api/ai-models/strategy/templates/non_existent_tpl",
            headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "模板不存在" in str(data.get("detail", ""))

    def test_generate_from_template_success(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试基于模板生成策略成功"""
        response = client.post(
            "/api/ai-models/strategy/generate-from-template",
            headers=auth_headers,
            json={
                "template_id": "tpl_001",
                "variables": {
                    "strategy_name": "MyDualMAStrategy",
                    "fast_period": 10,
                    "slow_period": 20
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "code" in data["data"]

    def test_generate_from_template_not_found(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试基于不存在的模板生成"""
        response = client.post(
            "/api/ai-models/strategy/generate-from-template",
            headers=auth_headers,
            json={
                "template_id": "non_existent_tpl",
                "variables": {}
            }
        )

        assert response.status_code == 404
        data = response.json()
        assert "模板不存在" in str(data.get("detail", ""))

    def test_generate_from_template_incomplete_variables(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试模板变量未完全替换"""
        response = client.post(
            "/api/ai-models/strategy/generate-from-template",
            headers=auth_headers,
            json={
                "template_id": "tpl_001",
                "variables": {
                    "strategy_name": "TestStrategy"
                    # 缺少 fast_period 和 slow_period
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "模板变量未完全替换" in data["message"]


class TestStrategyStatsAPI:
    """策略统计API测试类"""

    def test_get_performance_stats(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试获取性能统计"""
        response = client.get(
            "/api/ai-models/strategy/stats",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        assert "total_generations" in data["data"]
        assert "success_rate" in data["data"]

    def test_get_performance_stats_with_days_param(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试带天数参数的性能统计"""
        response = client.get(
            "/api/ai-models/strategy/stats?days=7",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_performance_stats_invalid_days(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试无效的天数参数"""
        response = client.get(
            "/api/ai-models/strategy/stats?days=0",
            headers=auth_headers
        )

        assert response.status_code == 422


class TestStrategyValidateAPI:
    """策略验证API测试类"""

    def test_validate_strategy_code_success(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试策略代码验证成功"""
        with patch("ai_model.routes_strategy.StrategyGenerator") as mock_gen_class:
            mock_generator = MagicMock()
            mock_generator.validate_code.return_value = {
                "valid": True,
                "errors": []
            }
            mock_gen_class.return_value = mock_generator

            response = client.post(
                "/api/ai-models/strategy/validate",
                headers=auth_headers,
                json={
                    "code": "class TestStrategy:\n    def __init__(self):\n        pass"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["valid"] is True

    def test_validate_strategy_code_with_warnings(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试策略代码验证返回警告"""
        with patch("ai_model.routes_strategy.StrategyGenerator") as mock_gen_class:
            mock_generator = MagicMock()
            mock_generator.validate_code.return_value = {
                "valid": True,
                "errors": ["警告: 代码中未找到类定义"]
            }
            mock_gen_class.return_value = mock_generator

            response = client.post(
                "/api/ai-models/strategy/validate",
                headers=auth_headers,
                json={
                    "code": "def test_function():\n    pass"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]["warnings"]) > 0


class TestStrategyAPIAuth:
    """策略API认证测试类"""

    def test_unauthorized_access_generate_sync(self, client):
        """测试未授权访问同步生成接口"""
        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json={"requirement": "创建一个简单的测试策略"}
        )

        assert response.status_code == 401

    def test_unauthorized_access_history(self, client):
        """测试未授权访问历史列表"""
        response = client.get("/api/ai-models/strategy/history")

        assert response.status_code == 401

    def test_unauthorized_access_templates(self, client):
        """测试未授权访问模板列表"""
        response = client.get("/api/ai-models/strategy/templates")

        assert response.status_code == 401

    def test_unauthorized_access_stats(self, client):
        """测试未授权访问统计接口"""
        response = client.get("/api/ai-models/strategy/stats")

        assert response.status_code == 401

    def test_invalid_token_access(self, client):
        """测试无效令牌访问"""
        with patch("utils.auth.decode_jwt_token") as mock_decode:
            from utils.jwt_utils import TokenInvalidError
            mock_decode.side_effect = TokenInvalidError("Invalid token")

            response = client.get(
                "/api/ai-models/strategy/history",
                headers={"Authorization": "Bearer invalid_token"}
            )

        assert response.status_code == 401


class TestStrategyAPIEdgeCases:
    """策略API边界情况测试类"""

    def test_generate_sync_short_requirement(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试过短的需求描述"""
        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            headers=auth_headers,
            json={"requirement": "短"}
        )

        assert response.status_code == 422

    def test_generate_sync_long_requirement(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试超长的需求描述"""
        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            headers=auth_headers,
            json={"requirement": "a" * 5001}
        )

        assert response.status_code == 422

    def test_generate_sync_invalid_temperature(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试无效的温度参数"""
        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            headers=auth_headers,
            json={
                "requirement": "创建一个简单的测试策略",
                "temperature": 3.0  # 超出范围
            }
        )

        assert response.status_code == 422

    def test_validate_code_empty(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试空代码验证"""
        response = client.post(
            "/api/ai-models/strategy/validate-code",
            headers=auth_headers,
            json={"code": "", "language": "python"}
        )

        assert response.status_code == 422

    def test_validate_code_unsupported_language(self, client, mock_auth, mock_should_refresh, auth_headers):
        """测试不支持的编程语言"""
        response = client.post(
            "/api/ai-models/strategy/validate-code",
            headers=auth_headers,
            json={
                "code": "function test() { return 1; }",
                "language": "javascript"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]["warnings"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
