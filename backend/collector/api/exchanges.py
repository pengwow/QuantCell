"""
交易所管理API路由

提供交易所配置和连接测试功能
"""

from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from collector.services.exchange_connection_service import (
    exchange_connection_service,
    ConnectionTestResult
)
from collector.schemas import ApiResponse


router = APIRouter(prefix="/exchanges", tags=["exchanges"])


class TestConnectionRequest(BaseModel):
    """测试连接请求模型"""
    exchange_name: str = Field(..., description="交易所名称 (binance, okx)")
    api_key: Optional[str] = Field(None, description="API密钥")
    secret_key: Optional[str] = Field(None, description="API密钥")
    api_passphrase: Optional[str] = Field(None, description="API密码（OKX需要）")
    proxy_url: Optional[str] = Field(None, description="代理URL")
    trading_mode: str = Field("spot", description="交易模式 (spot, future)")
    testnet: bool = Field(False, description="是否使用测试网络")


class TestConnectionResponse(BaseModel):
    """测试连接响应模型"""
    success: bool = Field(..., description="测试是否成功")
    status: str = Field(..., description="连接状态")
    message: str = Field(..., description="结果消息")
    response_time_ms: Optional[float] = Field(None, description="响应时间（毫秒）")
    details: dict = Field(default_factory=dict, description="详细测试信息")


@router.post("/test-connection", response_model=ApiResponse)
async def test_exchange_connection(request: TestConnectionRequest):
    """
    测试交易所连接

    验证交易所连接状态、API Key有效性及代理设置正确性

    - **exchange_name**: 交易所名称，支持 binance, okx
    - **api_key**: API密钥（可选，用于验证API认证）
    - **secret_key**: API密钥（可选，用于验证API认证）
    - **api_passphrase**: API密码（OKX需要）
    - **proxy_url**: 代理URL（可选）
    - **trading_mode**: 交易模式，spot 或 future
    - **testnet**: 是否使用测试网络

    返回结果包含：
    - success: 测试是否成功
    - status: 连接状态 (success, network_error, auth_error, permission_error, proxy_error, timeout_error, unknown_error)
    - message: 详细结果消息
    - response_time_ms: 响应时间
    - details: 详细测试信息
    """
    try:
        result = await exchange_connection_service.test_connection(
            exchange_name=request.exchange_name,
            api_key=request.api_key,
            secret_key=request.secret_key,
            api_passphrase=request.api_passphrase,
            proxy_url=request.proxy_url,
            trading_mode=request.trading_mode,
            testnet=request.testnet
        )

        return ApiResponse(
            code=0,
            message=result.message,
            data={
                "success": result.success,
                "status": result.status.value,
                "message": result.message,
                "response_time_ms": result.response_time_ms,
                "details": result.details
            }
        )

    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"测试连接时发生错误: {str(e)}",
            data=None
        )


@router.get("/supported", response_model=ApiResponse)
async def get_supported_exchanges():
    """
    获取支持的交易所列表

    返回当前支持连接测试的交易所列表
    """
    return ApiResponse(
        code=0,
        message="获取支持的交易所列表成功",
        data={
            "exchanges": exchange_connection_service.SUPPORTED_EXCHANGES
        }
    )
