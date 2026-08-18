"""
JWT工具模块单元测试

测试 jwt_utils 模块的令牌生成、验证、刷新等功能。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-09
"""

from datetime import timedelta
from unittest.mock import patch

import pytest

from utils.jwt_utils import (
    JWTError,
    TokenDecodeError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRefreshError,
    create_jwt_token,
    decode_jwt_token,
    generate_guest_tokens,
    generate_tokens,
    get_token_remaining_time,
    refresh_jwt_token,
    should_refresh_token,
    verify_jwt_token,
)


@pytest.fixture
def mock_secret_key():
    """Mock secret key for testing"""
    with patch("utils.jwt_utils.get_secret_key") as mock:
        mock.return_value = "test-secret-key-for-testing-purposes"
        yield mock


@pytest.fixture
def mock_jwt_secret():
    """直接设置测试用的secret key"""
    original_key = None
    try:
        import utils.jwt_utils as jwt_module

        original_key = jwt_module.JWT_SECRET_KEY
        jwt_module.JWT_SECRET_KEY = "test-secret-key-for-testing-purposes"
        jwt_module.JWT_ALGORITHM = "HS256"
        yield "test-secret-key-for-testing-purposes"
    finally:
        if original_key:
            jwt_module.JWT_SECRET_KEY = original_key


class TestCreateJWTToken:
    """测试 create_jwt_token 函数"""

    def test_create_token_with_default_expiry(self, mock_jwt_secret):
        """测试创建带默认过期时间的令牌"""
        token = create_jwt_token({"sub": "user123", "name": "Test"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_with_custom_expiry(self, mock_jwt_secret):
        """测试创建带自定义过期时间的令牌"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(hours=1))
        assert isinstance(token, str)

    def test_create_refresh_token(self, mock_jwt_secret):
        """测试创建刷新令牌"""
        token = create_jwt_token({"sub": "user123"}, refresh=True)
        payload = decode_jwt_token(token)
        assert payload.get("refresh") is True

    def test_token_contains_jti(self, mock_jwt_secret):
        """测试令牌包含唯一标识符"""
        token = create_jwt_token({"sub": "user123"})
        payload = decode_jwt_token(token)
        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_token_contains_expiry(self, mock_jwt_secret):
        """测试令牌包含过期时间"""
        token = create_jwt_token({"sub": "user123"})
        payload = decode_jwt_token(token)
        assert "exp" in payload
        assert isinstance(payload["exp"], int)


class TestDecodeJWTToken:
    """测试 decode_jwt_token 函数"""

    def test_decode_valid_token(self, mock_jwt_secret):
        """测试解码有效令牌"""
        token = create_jwt_token({"sub": "user123", "name": "Test User"})
        payload = decode_jwt_token(token)
        assert payload["sub"] == "user123"
        assert payload["name"] == "Test User"

    def test_decode_expired_token(self, mock_jwt_secret):
        """测试解码过期令牌"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(TokenExpiredError, match="令牌已过期"):
            decode_jwt_token(token)

    def test_decode_invalid_token(self, mock_jwt_secret):
        """测试解码无效令牌"""
        with pytest.raises((TokenDecodeError, TokenInvalidError)):
            decode_jwt_token("invalid.token.string")

    def test_decode_malformed_token(self, mock_jwt_secret):
        """测试解码格式错误的令牌"""
        with pytest.raises((TokenDecodeError, TokenInvalidError)):
            decode_jwt_token("not-a-jwt")


class TestVerifyJWTToken:
    """测试 verify_jwt_token 函数"""

    def test_verify_valid_token(self, mock_jwt_secret):
        """测试验证有效令牌"""
        token = create_jwt_token({"sub": "user123"})
        assert verify_jwt_token(token) is True

    def test_verify_expired_token(self, mock_jwt_secret):
        """测试验证过期令牌"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(seconds=-1))
        assert verify_jwt_token(token) is False

    def test_verify_invalid_token(self, mock_jwt_secret):
        """测试验证无效令牌"""
        assert verify_jwt_token("invalid.token") is False
        assert verify_jwt_token("") is False


class TestRefreshJWTToken:
    """测试 refresh_jwt_token 函数"""

    def test_refresh_valid_refresh_token(self, mock_jwt_secret):
        """测试刷新有效刷新令牌"""
        refresh_token = create_jwt_token({"sub": "user123"}, refresh=True)
        new_token = refresh_jwt_token(refresh_token)
        assert isinstance(new_token, str)
        assert new_token != refresh_token

        new_payload = decode_jwt_token(new_token)
        assert new_payload["sub"] == "user123"
        assert new_payload.get("refresh") is not True

    def test_refresh_access_token_fails(self, mock_jwt_secret):
        """测试刷新访问令牌失败"""
        access_token = create_jwt_token({"sub": "user123"}, refresh=False)
        with pytest.raises(TokenRefreshError, match="无效的刷新令牌"):
            refresh_jwt_token(access_token)

    def test_refresh_expired_token_fails(self, mock_jwt_secret):
        """测试刷新过期令牌失败"""
        expired_refresh = create_jwt_token({"sub": "user123", "refresh": True}, expires_delta=timedelta(seconds=-1))
        with pytest.raises((TokenExpiredError, TokenRefreshError)):
            refresh_jwt_token(expired_refresh)

    def test_refresh_token_missing_user_id(self, mock_jwt_secret):
        """测试刷新缺少用户ID的令牌"""
        refresh_token = create_jwt_token({}, refresh=True)
        with pytest.raises(TokenRefreshError, match="缺少用户信息"):
            refresh_jwt_token(refresh_token)


class TestGetTokenRemainingTime:
    """测试 get_token_remaining_time 函数"""

    def test_get_remaining_time(self, mock_jwt_secret):
        """测试获取令牌剩余时间"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(hours=1))
        remaining = get_token_remaining_time(token)
        assert remaining > 0
        assert remaining <= 3600

    def test_expired_token_returns_negative_one(self, mock_jwt_secret):
        """测试过期令牌返回-1"""
        expired_token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(seconds=-1))
        remaining = get_token_remaining_time(expired_token)
        assert remaining == -1

    def test_invalid_token_returns_negative_one(self, mock_jwt_secret):
        """测试无效令牌返回-1"""
        assert get_token_remaining_time("invalid") == -1


class TestShouldRefreshToken:
    """测试 should_refresh_token 函数"""

    def test_token_near_expiry_should_refresh(self, mock_jwt_secret):
        """测试接近过期的令牌应该刷新"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(minutes=5))
        assert should_refresh_token(token, threshold_minutes=10) is True

    def test_token_not_near_expiry_should_not_refresh(self, mock_jwt_secret):
        """测试远离过期的令牌不应该刷新"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(hours=1))
        assert should_refresh_token(token, threshold_minutes=10) is False

    def test_expired_token_should_not_refresh(self, mock_jwt_secret):
        """测试过期令牌不应该刷新"""
        expired_token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(seconds=-1))
        assert should_refresh_token(expired_token) is False

    def test_custom_threshold(self, mock_jwt_secret):
        """测试自定义阈值"""
        token = create_jwt_token({"sub": "user123"}, expires_delta=timedelta(minutes=15))
        assert should_refresh_token(token, threshold_minutes=20) is True
        assert should_refresh_token(token, threshold_minutes=10) is False


class TestGenerateTokens:
    """测试 generate_tokens 函数"""

    def test_generate_user_tokens(self, mock_jwt_secret):
        """测试生成用户令牌"""
        tokens = generate_tokens("user123", "Test User", "user")
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert "is_guest" not in tokens

    def test_access_token_payload(self, mock_jwt_secret):
        """测试访问令牌包含正确数据"""
        tokens = generate_tokens("user123", "Test User", "user")
        access_payload = decode_jwt_token(tokens["access_token"])
        assert access_payload["sub"] == "user123"
        assert access_payload["name"] == "Test User"
        assert access_payload["role"] == "user"
        assert access_payload.get("refresh") is not True

    def test_refresh_token_payload(self, mock_jwt_secret):
        """测试刷新令牌包含正确数据"""
        tokens = generate_tokens("user123", "Test User", "user")
        refresh_payload = decode_jwt_token(tokens["refresh_token"])
        assert refresh_payload["sub"] == "user123"
        assert refresh_payload["role"] == "user"
        assert refresh_payload["refresh"] is True

    def test_default_role(self, mock_jwt_secret):
        """测试默认角色为user"""
        tokens = generate_tokens("user456", "Another User")
        access_payload = decode_jwt_token(tokens["access_token"])
        assert access_payload["role"] == "user"


class TestGenerateGuestTokens:
    """测试 generate_guest_tokens 函数"""

    def test_generate_guest_tokens(self, mock_jwt_secret):
        """测试生成访客令牌"""
        tokens = generate_guest_tokens()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens.get("is_guest") is True

    def test_guest_access_token_payload(self, mock_jwt_secret):
        """测试访客访问令牌包含正确数据"""
        tokens = generate_guest_tokens()
        access_payload = decode_jwt_token(tokens["access_token"])
        assert access_payload["sub"].startswith("guest_")
        assert access_payload["name"] == "访客"
        assert access_payload["role"] == "guest"

    def test_guest_refresh_token_payload(self, mock_jwt_secret):
        """测试访客刷新令牌"""
        tokens = generate_guest_tokens()
        refresh_payload = decode_jwt_token(tokens["refresh_token"])
        assert refresh_payload["role"] == "guest"
        assert refresh_payload["refresh"] is True

    def test_guest_tokens_different_each_time(self, mock_jwt_secret):
        """测试每次生成的访客令牌不同"""
        tokens1 = generate_guest_tokens()
        tokens2 = generate_guest_tokens()
        assert tokens1["access_token"] != tokens2["access_token"]
        assert tokens1["refresh_token"] != tokens2["refresh_token"]


class TestJWTExceptions:
    """测试JWT异常类"""

    def test_jwt_error_inheritance(self):
        """测试异常继承关系"""
        assert issubclass(TokenExpiredError, JWTError)
        assert issubclass(TokenInvalidError, JWTError)
        assert issubclass(TokenDecodeError, JWTError)
        assert issubclass(TokenRefreshError, JWTError)

    def test_exception_messages(self):
        """测试异常消息"""
        with pytest.raises(TokenExpiredError, match="令牌已过期"):
            msg = "令牌已过期"
            raise TokenExpiredError(msg)


class TestTokenSecurity:
    """测试令牌安全性"""

    def test_different_secrets_produce_different_tokens(self):
        """测试不同密钥生成不同令牌"""
        import utils.jwt_utils as jwt_module

        original_key = jwt_module.JWT_SECRET_KEY

        try:
            jwt_module.JWT_SECRET_KEY = "secret-key-1"
            token1 = create_jwt_token({"sub": "user123"})

            jwt_module.JWT_SECRET_KEY = "secret-key-2"
            token2 = create_jwt_token({"sub": "user123"})

            assert token1 != token2

            jwt_module.JWT_SECRET_KEY = "secret-key-1"
            assert verify_jwt_token(token1) is True
            assert verify_jwt_token(token2) is False
        finally:
            jwt_module.JWT_SECRET_KEY = original_key

    def test_token_tampering_detection(self, mock_jwt_secret):
        """测试令牌篡改检测"""
        token = create_jwt_token({"sub": "user123", "role": "user"})
        parts = token.split(".")
        tampered = parts[0] + ".tampered." + parts[2]
        assert verify_jwt_token(tampered) is False


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_data_payload(self, mock_jwt_secret):
        """测试空数据载荷"""
        token = create_jwt_token({})
        payload = decode_jwt_token(token)
        assert "sub" not in payload

    def test_special_characters_in_data(self, mock_jwt_secret):
        """测试数据中包含特殊字符"""
        token = create_jwt_token(
            {
                "sub": "user123",
                "name": "Test User <script>alert('xss')</script>",
                "email": "test@example.com",
            }
        )
        payload = decode_jwt_token(token)
        assert "<script>" in payload["name"]

    def test_unicode_in_data(self, mock_jwt_secret):
        """测试数据中包含Unicode"""
        token = create_jwt_token({"sub": "user123", "name": "测试用户", "locale": "中文"})
        payload = decode_jwt_token(token)
        assert payload["name"] == "测试用户"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
