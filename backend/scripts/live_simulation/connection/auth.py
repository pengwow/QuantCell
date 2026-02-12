"""
认证管理模块

处理与QuantCell框架的身份验证。
"""

import hashlib
import hmac
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class AuthToken:
    """认证令牌"""
    token: str
    expires_at: datetime
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


class AuthManager:
    """认证管理器"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self._token: Optional[AuthToken] = None
        
    def generate_signature(self, timestamp: int, method: str = "GET", path: str = "/") -> str:
        """
        生成请求签名
        
        Args:
            timestamp: 时间戳（毫秒）
            method: HTTP方法
            path: 请求路径
            
        Returns:
            签名字符串
        """
        if not self.api_secret:
            raise ValueError("API secret not provided")
            
        message = f"{timestamp}{method}{path}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return signature
        
    def generate_auth_headers(self, method: str = "GET", path: str = "/") -> Dict[str, str]:
        """
        生成认证请求头
        
        Args:
            method: HTTP方法
            path: 请求路径
            
        Returns:
            请求头字典
        """
        if not self.api_key:
            raise ValueError("API key not provided")
            
        timestamp = int(time.time() * 1000)
        signature = self.generate_signature(timestamp, method, path)
        
        return {
            "X-API-KEY": self.api_key,
            "X-TIMESTAMP": str(timestamp),
            "X-SIGNATURE": signature,
        }
        
    def create_auth_message(self) -> Dict[str, Any]:
        """
        创建WebSocket认证消息
        
        Returns:
            认证消息字典
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials not provided")
            
        timestamp = int(time.time() * 1000)
        signature = self.generate_signature(timestamp, "WS", "/ws")
        
        return {
            "type": "auth",
            "timestamp": timestamp,
            "data": {
                "api_key": self.api_key,
                "signature": signature,
            }
        }
        
    def verify_signature(self, signature: str, timestamp: int, method: str = "GET", path: str = "/") -> bool:
        """
        验证签名
        
        Args:
            signature: 待验证的签名
            timestamp: 时间戳
            method: HTTP方法
            path: 请求路径
            
        Returns:
            签名是否有效
        """
        expected_signature = self.generate_signature(timestamp, method, path)
        return hmac.compare_digest(signature, expected_signature)
        
    def set_credentials(self, api_key: str, api_secret: str):
        """设置API凭证"""
        self.api_key = api_key
        self.api_secret = api_secret
        
    def clear_credentials(self):
        """清除API凭证"""
        self.api_key = None
        self.api_secret = None
        self._token = None
        
    def has_credentials(self) -> bool:
        """检查是否有API凭证"""
        return self.api_key is not None and self.api_secret is not None


class SimpleAuthManager(AuthManager):
    """简单认证管理器（用于测试）"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        super().__init__(api_key or "test_key", api_secret or "test_secret")
        
    def generate_signature(self, timestamp: int, method: str = "GET", path: str = "/") -> str:
        """生成简单签名（仅用于测试）"""
        if not self.api_secret:
            return ""
        return hashlib.md5(f"{self.api_secret}{timestamp}".encode()).hexdigest()
