"""
QuantCell连接模块

提供与QuantCell框架的WebSocket连接和认证功能。
"""

from .quantcell_client import QuantCellClient
from .auth import AuthManager

__all__ = ["QuantCellClient", "AuthManager"]
