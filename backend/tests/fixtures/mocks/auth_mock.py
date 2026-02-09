"""
认证Mock模块

提供JWT认证相关的Mock对象和辅助函数
"""

from unittest.mock import Mock, patch
from typing import Dict, Any, Optional
import jwt
from datetime import datetime, timedelta, timezone

# 导入密钥管理器，确保测试使用与应用程序相同的密钥
from utils.secret_key_manager import get_secret_key


class MockJWTToken:
    """Mock JWT令牌生成器"""
    
    # 从配置系统动态获取密钥，确保与应用程序一致
    SECRET_KEY = get_secret_key()
    ALGORITHM = "HS256"
    
    @classmethod
    def create_valid_token(
        cls,
        user_id: str = "test_user_123",
        username: str = "test_user",
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        创建有效的测试令牌
        
        Args:
            user_id: 用户ID
            username: 用户名
            expires_delta: 过期时间增量
            
        Returns:
            str: JWT令牌字符串
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=1)
        
        expire = datetime.now(timezone.utc) + expires_delta
        
        payload = {
            "sub": user_id,
            "name": username,
            "exp": expire,
            "iat": datetime.now(timezone.utc)
        }
        
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
    
    @classmethod
    def create_expired_token(cls, user_id: str = "test_user_123") -> str:
        """
        创建已过期的测试令牌
        
        Args:
            user_id: 用户ID
            
        Returns:
            str: 已过期的JWT令牌
        """
        expire = datetime.now(timezone.utc) - timedelta(hours=1)
        
        payload = {
            "sub": user_id,
            "name": "test_user",
            "exp": expire,
            "iat": expire - timedelta(hours=1)
        }
        
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
    
    @classmethod
    def create_invalid_signature_token(cls) -> str:
        """
        创建签名无效的测试令牌
        
        Returns:
            str: 签名无效的JWT令牌
        """
        payload = {
            "sub": "test_user",
            "name": "test_user",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
        }
        
        # 使用错误的密钥签名
        return jwt.encode(payload, "wrong_secret_key", algorithm=cls.ALGORITHM)
    
    @classmethod
    def create_malformed_token(cls) -> str:
        """
        创建格式错误的测试令牌
        
        Returns:
            str: 格式错误的令牌
        """
        return "not.a.valid.jwt.token"
    
    @classmethod
    def decode_token(cls, token: str) -> Dict[str, Any]:
        """
        解码令牌（用于测试验证）
        
        Args:
            token: JWT令牌
            
        Returns:
            Dict[str, Any]: 解码后的payload
        """
        return jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
    
    @classmethod
    def create_invalid_token(cls) -> str:
        """
        创建无效的测试令牌（使用错误签名）
        
        Returns:
            str: 无效的JWT令牌
        """
        return cls.create_invalid_signature_token()
    
    @classmethod
    def create_token_with_claims(cls, claims: Dict[str, Any]) -> str:
        """
        创建带指定声明的测试令牌
        
        Args:
            claims: 要包含的声明字典
            
        Returns:
            str: JWT令牌
        """
        # 基础payload
        payload = {
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        # 合并自定义声明
        payload.update(claims)
        
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
    
    @classmethod
    def create_token_without_exp(cls) -> str:
        """
        创建无过期时间的测试令牌
        
        Returns:
            str: 无exp声明的JWT令牌
        """
        payload = {
            "sub": "test_user_123",
            "name": "test_user",
            "iat": datetime.now(timezone.utc)
        }
        
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
    
    @classmethod
    def create_near_expiration_token(cls, minutes_left: int = 5) -> str:
        """
        创建即将过期的测试令牌
        
        Args:
            minutes_left: 剩余分钟数
            
        Returns:
            str: 即将过期的JWT令牌
        """
        expire = datetime.now(timezone.utc) + timedelta(minutes=minutes_left)
        
        payload = {
            "sub": "test_user_123",
            "name": "test_user",
            "exp": expire,
            "iat": datetime.now(timezone.utc)
        }
        
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)


class MockAuthService:
    """Mock认证服务"""
    
    def __init__(self):
        self.valid_users = {
            "test_user_123": {
                "id": "test_user_123",
                "username": "test_user",
                "role": "user",
                "permissions": ["read", "write"]
            },
            "admin_user_123": {
                "id": "admin_user_123",
                "username": "admin",
                "role": "admin",
                "permissions": ["read", "write", "delete", "admin"]
            }
        }
    
    def validate_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        验证用户是否存在
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[Dict[str, Any]]: 用户信息或None
        """
        return self.valid_users.get(user_id)
    
    def check_permission(self, user_id: str, permission: str) -> bool:
        """
        检查用户权限
        
        Args:
            user_id: 用户ID
            permission: 权限名称
            
        Returns:
            bool: 是否有权限
        """
        user = self.valid_users.get(user_id)
        if not user:
            return False
        return permission in user.get("permissions", [])


def mock_jwt_auth_required(mocker, user_id: str = "test_user_123"):
    """
    Mock JWT认证装饰器
    
    Args:
        mocker: pytest mocker fixture
        user_id: 模拟的用户ID
        
    Returns:
        Mock: mock对象
    """
    mock_payload = {
        "sub": user_id,
        "name": "test_user"
    }
    
    return mocker.patch(
        "utils.auth.decode_jwt_token",
        return_value=mock_payload
    )


def mock_get_current_user(mocker, user_id: str = "test_user_123"):
    """
    Mock获取当前用户函数
    
    Args:
        mocker: pytest mocker fixture
        user_id: 模拟的用户ID
        
    Returns:
        Mock: mock对象
    """
    mock_user = {
        "sub": user_id,
        "name": "test_user"
    }
    
    return mocker.patch(
        "utils.auth.get_current_user",
        return_value=mock_user
    )
