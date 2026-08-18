"""策略生成API路由单元测试

测试策略生成API端点、请求参数验证、认证失败场景和流式响应
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# 添加backend目录到Python路径
# 使用绝对路径
test_file = Path(__file__).resolve()
backend_dir = test_file.parent.parent.parent.parent  # tests/unit/ai_model -> tests/unit -> tests -> backend
sys.path.insert(0, str(backend_dir))

# mock数据库模块，避免导入链触发重型依赖
# 注意：worker 模块不再 mock，因为 share/routes.py 需要导入 worker.dependencies，
# 而 worker 模块已移除旧交易引擎依赖，可正常导入
_MOCK_MODULES = {
    "settings.models": MagicMock(),
    "collector.db.database": MagicMock(),
    "collector.db.models": MagicMock(),
}
for _name, _mock in _MOCK_MODULES.items():
    sys.modules.setdefault(_name, _mock)

import ai_model.routes_strategy
from main import app

# 清理mock条目和被污染的模块，避免影响后续测试文件的收集
# 不清理ai_model和ai_model.routes_strategy（本测试需要它们）
_KEEP_MODULES = {
    "ai_model",
    "ai_model.routes_strategy",
    "ai_model.routes",
    "ai_model.schemas_strategy",
    "ai_model.config_utils",
    "ai_model.prompts",
    "ai_model.strategy_generator",
    "ai_model.thinking_chain",
    "ai_model.performance_monitor",
}
for _mod_name in [*list(_MOCK_MODULES.keys()), "main"]:
    sys.modules.pop(_mod_name, None)
# 清理因mock collector.db.database而使用了mock Base的模块
for _mod_name in list(sys.modules.keys()):
    if _mod_name in _KEEP_MODULES:
        continue
    if _mod_name.startswith(
        (
            "strategy.",
            "backtest.",
            "settings.",
            "collector.",
            "system.",
            "factor.",
            "worker.",
        )
    ):
        sys.modules.pop(_mod_name, None)
for _mod_name in ["strategy", "backtest", "settings", "collector", "system", "factor"]:
    sys.modules.pop(_mod_name, None)

# 创建测试客户端
client = TestClient(app)


class TestGenerateStrategyStream:
    """测试流式生成策略端点 /generate"""

    @pytest.fixture
    def valid_request_data(self):
        """有效的请求数据"""
        return {
            "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
            "model_id": "gpt-4",
            "temperature": 0.7,
            "template_vars": {"strategy_name": "DualMAStrategy", "symbol": "BTC/USDT"},
        }

    def test_generate_stream_missing_requirement(self):
        """测试缺少必需参数 requirement"""
        request_data = {"model_id": "gpt-4"}

        response = client.post(
            "/api/ai-models/strategy/generate",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_generate_stream_requirement_too_short(self):
        """测试 requirement 长度太短"""
        request_data = {"requirement": "短描述"}

        response = client.post(
            "/api/ai-models/strategy/generate",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_generate_stream_invalid_temperature(self):
        """测试无效的 temperature 参数"""
        request_data = {
            "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
            "temperature": 3.0,  # 超出范围 0-2
        }

        response = client.post(
            "/api/ai-models/strategy/generate",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422


class TestGenerateStrategySync:
    """测试同步生成策略端点 /generate-sync"""

    @pytest.fixture
    def valid_request_data(self):
        """有效的请求数据"""
        return {
            "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
            "model_id": "gpt-4",
            "temperature": 0.7,
        }

    def test_generate_sync_missing_requirement(self):
        """测试缺少必需参数"""
        request_data = {"model_id": "gpt-4"}

        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_generate_sync_requirement_too_short(self):
        """测试 requirement 长度太短"""
        request_data = {"requirement": "短描述"}

        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422


class TestValidateStrategyCode:
    """测试验证策略代码端点 /validate"""

    @pytest.fixture
    def valid_code_data(self):
        """有效的代码数据"""
        return {"code": "class MyStrategy:\n    def __init__(self):\n        pass"}

    def test_validate_code_empty_code(self):
        """测试空代码验证"""
        request_data = {"code": ""}

        response = client.post(
            "/api/ai-models/strategy/validate",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        # 空代码应被请求验证拒绝（min_length=1）
        assert response.status_code == 422


class TestRequestValidation:
    """测试请求参数验证"""

    def test_requirement_min_length(self):
        """测试 requirement 最小长度验证"""
        request_data = {"requirement": "太短"}

        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_requirement_max_length(self):
        """测试 requirement 最大长度验证"""
        request_data = {
            "requirement": "x" * 5001  # 超过最大长度5000
        }

        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_requirement_whitespace_only(self):
        """测试 requirement 仅包含空白字符"""
        request_data = {"requirement": "   \n\t  "}

        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json=request_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_temperature_range(self):
        """测试 temperature 范围验证"""
        # 测试小于0
        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json={
                "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
                "temperature": -0.1,
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 422

        # 测试大于2
        response = client.post(
            "/api/ai-models/strategy/generate-sync",
            json={
                "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
                "temperature": 2.1,
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 422

    def test_code_required_for_validate(self):
        """测试验证端点 code 字段必填"""
        response = client.post(
            "/api/ai-models/strategy/validate",
            json={},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422


class TestAuthentication:
    """测试认证相关场景"""

    def test_missing_authorization_header(self):
        """测试缺少认证头"""
        # 在非debug模式下测试
        with patch("utils.auth.IS_DEBUG_MODE", False):
            response = client.post(
                "/api/ai-models/strategy/generate-sync",
                json={"requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出"},
            )

            assert response.status_code == 401

    def test_invalid_authorization_format(self):
        """测试无效的认证格式"""
        with patch("utils.auth.IS_DEBUG_MODE", False):
            response = client.post(
                "/api/ai-models/strategy/generate-sync",
                json={"requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出"},
                headers={"Authorization": "InvalidFormat"},
            )

            assert response.status_code == 401

    def test_expired_token(self):
        """测试过期的令牌"""
        with patch("utils.auth.IS_DEBUG_MODE", False), patch("utils.auth.decode_jwt_token") as mock_decode:
            from utils.jwt_utils import TokenExpiredError

            mock_decode.side_effect = TokenExpiredError("Token expired")

            response = client.post(
                "/api/ai-models/strategy/generate-sync",
                json={"requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出"},
                headers={"Authorization": "Bearer expired_token"},
            )

            assert response.status_code == 401

    def test_invalid_token(self):
        """测试无效的令牌"""
        with patch("utils.auth.IS_DEBUG_MODE", False), patch("utils.auth.decode_jwt_token") as mock_decode:
            from utils.jwt_utils import TokenInvalidError

            mock_decode.side_effect = TokenInvalidError("Invalid token")

            response = client.post(
                "/api/ai-models/strategy/generate-sync",
                json={"requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出"},
                headers={"Authorization": "Bearer invalid_token"},
            )

            assert response.status_code == 401

    def test_debug_mode_skips_auth(self):
        """测试debug模式跳过认证"""
        with patch("utils.auth.IS_DEBUG_MODE", True):
            # mock 实际被调用的配置获取函数，返回 None 模拟未配置AI模型
            with patch("ai_model.routes_strategy.get_default_provider_and_models") as mock_get_config:
                mock_get_config.return_value = None

                response = client.post(
                    "/api/ai-models/strategy/generate-sync",
                    json={"requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出"},
                )

                # 应该返回400（未配置AI模型），而不是401（未认证）
                assert response.status_code == 400
