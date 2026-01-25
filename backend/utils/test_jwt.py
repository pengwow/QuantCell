# JWT测试模块
# 提供JWT令牌生成的测试接口

from fastapi import APIRouter, HTTPException
from loguru import logger

from .jwt_utils import generate_tokens

# 创建测试API路由实例
router = APIRouter(prefix="/api/test/jwt", tags=["test-jwt"])


@router.post("/generate-token")
def generate_test_token(user_id: str = "test_user", user_name: str = "测试用户"):
    """生成测试用JWT令牌
    
    用于测试JWT认证功能，生成访问令牌和刷新令牌
    
    Args:
        user_id: 测试用户ID
        user_name: 测试用户名称
    
    Returns:
        dict: 包含访问令牌和刷新令牌的字典
    """
    try:
        logger.info(f"生成测试JWT令牌，用户ID: {user_id}, 用户名称: {user_name}")
        
        # 生成令牌
        tokens = generate_tokens(user_id, user_name)
        
        logger.info(f"成功生成测试JWT令牌，用户ID: {user_id}")
        
        return {
            "code": 0,
            "message": "测试JWT令牌生成成功",
            "data": tokens
        }
    except Exception as e:
        logger.error(f"生成测试JWT令牌失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
