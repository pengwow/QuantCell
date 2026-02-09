# JWT工具模块
# 实现JWT令牌的生成、验证、刷新等功能

import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import jwt
from loguru import logger

# 导入密钥管理器
from utils.secret_key_manager import get_secret_key

# 默认JWT配置
# JWT_SECRET_KEY 从配置文件动态加载，首次启动时自动生成
JWT_SECRET_KEY = get_secret_key()
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 访问令牌过期时间（分钟）
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7  # 刷新令牌过期时间（天）
JWT_ALGORITHM = "HS256"  # 加密算法


class JWTError(Exception):
    """JWT相关错误的基础类"""
    pass


class TokenExpiredError(JWTError):
    """令牌过期错误"""
    pass


class TokenInvalidError(JWTError):
    """令牌无效错误"""
    pass


class TokenDecodeError(JWTError):
    """令牌解码错误"""
    pass


class TokenRefreshError(JWTError):
    """令牌刷新错误"""
    pass


def create_jwt_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    refresh: bool = False
) -> str:
    """生成JWT令牌
    
    Args:
        data: 要包含在令牌中的数据
        expires_delta: 令牌过期时间
        refresh: 是否为刷新令牌
    
    Returns:
        str: 生成的JWT令牌
    """
    to_encode = data.copy()
    
    # 设置过期时间
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        if refresh:
            expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4()), "refresh": refresh})
    
    # 生成令牌
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """解码JWT令牌
    
    Args:
        token: 要解码的JWT令牌
    
    Returns:
        Dict[str, Any]: 令牌中的payload数据
    
    Raises:
        TokenExpiredError: 令牌已过期
        TokenDecodeError: 令牌解码失败
        TokenInvalidError: 令牌无效
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("令牌已过期")
    except jwt.DecodeError:
        raise TokenDecodeError("令牌解码失败")
    except jwt.InvalidTokenError:
        raise TokenInvalidError("令牌无效")


def verify_jwt_token(token: str) -> bool:
    """验证JWT令牌有效性
    
    Args:
        token: 要验证的JWT令牌
    
    Returns:
        bool: 令牌是否有效
    """
    try:
        decode_jwt_token(token)
        return True
    except JWTError:
        return False


def refresh_jwt_token(refresh_token: str) -> str:
    """刷新JWT访问令牌
    
    Args:
        refresh_token: 刷新令牌
    
    Returns:
        str: 新的访问令牌
    
    Raises:
        TokenRefreshError: 刷新令牌无效或已过期
    """
    try:
        # 解码刷新令牌
        payload = decode_jwt_token(refresh_token)
        
        # 验证是否为刷新令牌
        if not payload.get("refresh"):
            raise TokenRefreshError("无效的刷新令牌")
        
        # 从刷新令牌中提取用户信息
        user_id = payload.get("sub")
        if not user_id:
            raise TokenRefreshError("刷新令牌中缺少用户信息")
        
        # 生成新的访问令牌
        new_access_token = create_jwt_token(data={"sub": user_id})
        return new_access_token
    except JWTError as e:
        logger.error(f"刷新令牌失败: {e}")
        raise TokenRefreshError(f"刷新令牌失败: {str(e)}")


def get_token_remaining_time(token: str) -> float:
    """获取令牌剩余有效时间（秒）
    
    Args:
        token: JWT令牌
    
    Returns:
        float: 令牌剩余有效时间（秒），负数表示已过期
    """
    try:
        payload = decode_jwt_token(token)
        exp = payload.get("exp")
        if not exp:
            return 0
        
        # 计算剩余时间（秒）
        remaining = exp - time.time()
        return remaining
    except TokenExpiredError:
        return -1
    except JWTError:
        return -1


def should_refresh_token(token: str, threshold_minutes: int = 10) -> bool:
    """判断是否应该刷新令牌
    
    Args:
        token: JWT令牌
        threshold_minutes: 剩余时间阈值（分钟），当令牌剩余时间小于此值时需要刷新
    
    Returns:
        bool: 是否需要刷新令牌
    """
    remaining_seconds = get_token_remaining_time(token)
    return remaining_seconds > 0 and remaining_seconds < (threshold_minutes * 60)


def generate_tokens(user_id: str, user_name: str) -> Dict[str, str]:
    """生成访问令牌和刷新令牌
    
    Args:
        user_id: 用户ID
        user_name: 用户名称
    
    Returns:
        Dict[str, str]: 包含访问令牌和刷新令牌的字典
    """
    # 生成访问令牌
    access_token = create_jwt_token(data={"sub": user_id, "name": user_name})
    
    # 生成刷新令牌
    refresh_token = create_jwt_token(
        data={"sub": user_id, "name": user_name},
        refresh=True
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
