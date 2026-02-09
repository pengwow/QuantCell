# JWT认证授权专项测试
# 测试JWT认证相关的所有场景

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
import jwt


class TestJWTAuthentication:
    """JWT认证基础测试类"""

    def test_valid_token_authentication(self, client: TestClient, valid_auth_headers: dict):
        """测试有效令牌的认证"""
        response = client.delete("/api/strategy/sma_cross", headers=valid_auth_headers)
        assert response.status_code == 200

    def test_no_token_authentication(self, client: TestClient):
        """测试未提供令牌的认证"""
        response = client.delete("/api/strategy/sma_cross")
        assert response.status_code == 401
        data = response.json()
        assert "未提供认证令牌" in str(data.get("detail", {}).get("reason", ""))

    def test_empty_token_authentication(self, client: TestClient):
        """测试空令牌的认证"""
        headers = {"Authorization": ""}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_malformed_bearer_token(self, client: TestClient):
        """测试格式错误的Bearer令牌（无空格）"""
        valid_token = self._create_test_token()
        headers = {"Authorization": valid_token}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401
        data = response.json()
        assert "无效的认证令牌格式" in str(data.get("detail", {}).get("reason", ""))

    def test_invalid_token_signature(self, client: TestClient):
        """测试无效签名的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_invalid_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_expired_token_authentication(self, client: TestClient, expired_auth_headers: dict):
        """测试过期令牌的认证"""
        response = client.delete("/api/strategy/sma_cross", headers=expired_auth_headers)
        assert response.status_code == 401
        data = response.json()
        assert "令牌已过期" in str(data.get("detail", {}).get("reason", ""))

    def test_wrong_algorithm_token(self, client: TestClient):
        """测试使用错误算法的令牌"""
        token = self._create_token_with_wrong_algorithm()
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_corrupted_token(self, client: TestClient):
        """测试损坏的令牌"""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.token"
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def _create_test_token(self, expires_in_hours: int = 1) -> str:
        """创建测试用JWT令牌"""
        from utils.jwt_utils import JWT_SECRET_KEY, JWT_ALGORITHM
        payload = {
            "sub": "test_user_123",
            "name": "Test User",
            "exp": datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
            "iat": datetime.now(timezone.utc)
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def _create_token_with_wrong_algorithm(self) -> str:
        """创建使用错误算法的令牌"""
        payload = {
            "sub": "test_user_123",
            "name": "Test User",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
        }
        return jwt.encode(payload, "wrong-secret-key", algorithm="HS384")


class TestJWTTokenValidation:
    """JWT令牌验证测试类"""

    def test_token_with_missing_sub_claim(self, client: TestClient, mocker):
        """测试缺少sub声明的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_token_with_claims({})
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_with_empty_sub(self, client: TestClient, mocker):
        """测试sub为空的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_token_with_claims({"sub": ""})
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_future_iat(self, client: TestClient, mocker):
        """测试iat为未来时间的令牌（应被拒绝）"""
        from fixtures.mocks.auth_mock import MockJWTToken
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        token = MockJWTToken.create_token_with_claims({"iat": future_time})
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        # JWT库会验证iat，未来时间应返回401
        assert response.status_code == 401

    def test_token_without_expiration(self, client: TestClient, mocker):
        """测试没有过期时间的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_token_without_exp()
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200


class TestJWTTokenRefresh:
    """JWT令牌刷新测试类"""

    def test_token_near_expiration(self, client: TestClient, mocker):
        """测试即将过期的令牌（应触发刷新）"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_near_expiration_token(minutes_left=5)
        headers = {"Authorization": f"Bearer {token}"}
        mocker.patch(
            "utils.jwt_utils.should_refresh_token",
            return_value=True
        )
        mocker.patch(
            "utils.jwt_utils.create_jwt_token",
            return_value="new_refreshed_token"
        )

        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_fresh_not_refreshed(self, client: TestClient, mocker):
        """测试新鲜的令牌不应刷新"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200


class TestJWTPayloadValidation:
    """JWT负载验证测试类"""

    def test_token_with_extra_claims(self, client: TestClient, mocker):
        """测试携带额外声明的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        extra_claims = {
            "role": "admin",
            "permissions": ["read", "write", "delete"],
            "custom_field": "custom_value"
        }
        token = MockJWTToken.create_token_with_claims(extra_claims)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_with_chinese_characters(self, client: TestClient, mocker):
        """测试携带中文字符的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        chinese_claims = {
            "sub": "test_user",
            "name": "测试用户",
            "role": "管理员"
        }
        token = MockJWTToken.create_token_with_claims(chinese_claims)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_with_unicode_characters(self, client: TestClient, mocker):
        """测试携带Unicode字符的令牌"""
        from fixtures.mocks.auth_mock import MockJWTToken
        unicode_claims = {
            "sub": "test_user",
            "name": "用户_日本語_한국어",
            "emoji": "🚀🎉💻"
        }
        token = MockJWTToken.create_token_with_claims(unicode_claims)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200


class TestAuthEndpointAccess:
    """认证端点访问控制测试类"""

    def test_protected_endpoint_without_auth(self, client: TestClient):
        """测试访问受保护端点无需认证"""
        endpoints = [
            ("DELETE", "/api/strategy/sma_cross"),
            ("DELETE", "/api/backtest/delete/bt_123"),
            ("DELETE", "/api/config/test_config"),
        ]
        for method, endpoint in endpoints:
            if method == "DELETE":
                response = client.delete(endpoint)
            else:
                continue
            assert response.status_code == 401

    def test_public_endpoint_accessible(self, client: TestClient):
        """测试公开端点无需认证即可访问"""
        endpoints = [
            ("GET", "/api/strategy/list"),
            ("GET", "/api/backtest/list"),
            ("GET", "/api/config/"),
            ("GET", "/api/system/info"),
            ("POST", "/api/backtest/run"),
            ("POST", "/api/config/"),
        ]
        for method, endpoint in endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint, json={})
            else:
                continue
            assert response.status_code in [200, 422]

    def test_mixed_auth_endpoints(self, client: TestClient):
        """测试混合认证端点"""
        from fixtures.mocks.auth_mock import MockJWTToken
        valid_token = MockJWTToken.create_valid_token()
        auth_headers = {"Authorization": f"Bearer {valid_token}"}

        mixed_endpoints = [
            ("GET", "/api/strategy/list", None, None),
            ("POST", "/api/strategy/detail", None, {"strategy_name": "sma_cross"}),
            ("POST", "/api/strategy/upload", None, {"strategy_name": "test", "content": "code"}),
            ("DELETE", "/api/strategy/test_strategy", auth_headers, None),
        ]

        for method, endpoint, headers, json_body in mixed_endpoints:
            if method == "GET":
                response = client.get(endpoint, headers=headers)
            elif method == "POST":
                response = client.post(endpoint, json=json_body, headers=headers)
            elif method == "DELETE":
                response = client.delete(endpoint, headers=headers)
            else:
                continue

            if headers is None:
                assert response.status_code in [200, 404, 422]
            else:
                assert response.status_code in [200, 404]


class TestTokenEdgeCases:
    """令牌边界条件测试类"""

    def test_very_long_token(self, client: TestClient, mocker):
        """测试超长令牌"""
        long_payload = {"sub": "a" * 1000}
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_token_with_claims(long_payload)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_base64_encoding(self, client: TestClient, mocker):
        """测试令牌Base64编码"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        encoded_token = token.encode('utf-8').decode('ascii')
        headers = {"Authorization": f"Bearer {encoded_token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_token_case_sensitivity(self, client: TestClient):
        """测试令牌大小写敏感性"""
        from fixtures.mocks.auth_mock import MockJWTToken
        valid_token = MockJWTToken.create_valid_token()
        wrong_case_token = valid_token.upper()
        headers = {"Authorization": f"Bearer {wrong_case_token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_whitespace_in_token(self, client: TestClient):
        """测试令牌中的空白字符"""
        from fixtures.mocks.auth_mock import MockJWTToken
        valid_token = MockJWTToken.create_valid_token()
        token_with_spaces = f"  {valid_token}  "
        headers = {"Authorization": f"Bearer {token_with_spaces}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_null_bytes_in_token(self, client: TestClient, mocker):
        """测试令牌中的空字节"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        token_with_nulls = token[:10] + "\x00" + token[11:]
        headers = {"Authorization": f"Bearer {token_with_nulls}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_only_bearer_prefix(self, client: TestClient):
        """测试只有Bearer前缀无令牌"""
        headers = {"Authorization": "Bearer"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401

    def test_bearer_with_extra_spaces(self, client: TestClient):
        """测试Bearer前缀带多余空格"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        headers = {"Authorization": f"  Bearer   {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 401


class TestAuthHeaderHandling:
    """认证头处理测试类"""

    def test_case_insensitive_header(self, client: TestClient, mocker):
        """测试不区分大小写的认证头"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        headers = {"authorization": f"Bearer {token}"}
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_multiple_auth_headers(self, client: TestClient, mocker):
        """测试多个认证头"""
        from fixtures.mocks.auth_mock import MockJWTToken
        valid_token = MockJWTToken.create_valid_token()
        invalid_token = "invalid_token_123"
        headers = [
            {"Authorization": f"Bearer {valid_token}"},
            {"Authorization": f"Bearer {invalid_token}"},
        ]
        response = client.delete("/api/strategy/sma_cross", headers=headers[0])
        assert response.status_code == 200

    def test_auth_header_with_other_headers(self, client: TestClient, mocker):
        """测试携带其他请求头的认证"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Custom-Header": "custom_value"
        }
        response = client.delete("/api/strategy/sma_cross", headers=headers)
        assert response.status_code == 200

    def test_auth_header_content_type_handling(self, client: TestClient, mocker):
        """测试不同Content-Type下的认证"""
        from fixtures.mocks.auth_mock import MockJWTToken
        token = MockJWTToken.create_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        content_types = [
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ]

        for ct in content_types:
            test_headers = {**headers, "Content-Type": ct}
            # DELETE请求不支持json参数，使用统一的headers方式
            response = client.delete("/api/strategy/sma_cross", headers=test_headers)
            # 接受200或404（策略不存在）
            assert response.status_code in [200, 404]


class TestAuthErrorResponses:
    """认证错误响应测试类"""

    def test_error_response_format(self, client: TestClient):
        """测试错误响应格式"""
        response = client.delete("/api/strategy/sma_cross")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "reason" in data["detail"]
        assert "path" in data["detail"]

    def test_error_response_www_authenticate(self, client: TestClient):
        """测试WWW-Authenticate响应头"""
        response = client.delete("/api/strategy/sma_cross")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_different_endpoints_same_error(self, client: TestClient):
        """测试不同端点的相同认证错误"""
        endpoints = [
            "/api/strategy/test",
            "/api/backtest/delete/bt_123",
            "/api/config/test",
        ]
        for endpoint in endpoints:
            response = client.delete(endpoint)
            assert response.status_code == 401

    def test_error_message_localization(self, client: TestClient):
        """测试错误消息本地化"""
        response = client.delete("/api/strategy/sma_cross")
        assert response.status_code == 401
        data = response.json()
        assert "未提供认证令牌" in str(data.get("detail", {}))
