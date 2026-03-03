"""市场数据API路由

提供货币对列表和市场行情数据的API接口
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from collector.services.market_data_service import market_data_service
from common.schemas import ApiResponse

router = APIRouter(prefix="/data/crypto", tags=["market-data"])


class MarketDataRequest(BaseModel):
    """市场数据请求体"""
    symbols: List[str]
    exchange: str = "binance"
    force_refresh: bool = False


@router.get("/symbols", response_model=ApiResponse)
async def get_symbols(
    exchange: str = Query("binance", description="交易所名称"),
    limit: int = Query(100, ge=1, le=1000, description="分页大小"),
    offset: int = Query(0, ge=0, description="偏移量"),
    sync: bool = Query(False, description="是否强制同步交易所数据")
):
    """获取货币对列表
    
    优先从数据库读取，如果数据库为空或sync=true则从交易所同步
    
    Args:
        exchange: 交易所名称，默认binance
        limit: 分页大小，默认100
        offset: 偏移量，默认0
        sync: 是否强制同步，默认False
        
    Returns:
        ApiResponse: 包含货币对列表的响应
    """
    try:
        # 如果需要同步，先从交易所获取
        if sync:
            await market_data_service.sync_symbols(exchange)
        
        # 从数据库获取
        result = await market_data_service.get_symbols_from_db(
            exchange=exchange,
            limit=limit,
            offset=offset
        )
        
        return ApiResponse(
            code=0,
            message="获取货币对列表成功",
            data=result
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"获取货币对列表失败: {str(e)}",
            data=None
        )


@router.post("/market-data", response_model=ApiResponse)
async def get_market_data(request: MarketDataRequest):
    """获取市场数据
    
    根据指定的货币对列表获取24小时行情数据
    优先从数据库缓存读取，过期则从交易所获取
    
    Args:
        request: 包含symbols列表、exchange名称和force_refresh标志
        
    Returns:
        ApiResponse: 包含市场数据列表的响应
    """
    try:
        if not request.symbols:
            return ApiResponse(
                code=400,
                message="symbols列表不能为空",
                data=None
            )
        
        # 限制每次请求的最大数量
        if len(request.symbols) > 100:
            return ApiResponse(
                code=400,
                message="每次最多查询100个货币对",
                data=None
            )
        
        result = await market_data_service.get_market_data(
            symbols=request.symbols,
            exchange=request.exchange,
            force_refresh=request.force_refresh
        )
        
        return ApiResponse(
            code=0,
            message="获取市场数据成功",
            data=result
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"获取市场数据失败: {str(e)}",
            data=None
        )


@router.post("/sync-symbols", response_model=ApiResponse)
async def sync_symbols(exchange: str = "binance"):
    """手动同步货币对列表
    
    从交易所获取所有货币对并保存到数据库
    
    Args:
        exchange: 交易所名称，默认binance
        
    Returns:
        ApiResponse: 同步结果
    """
    try:
        symbols = await market_data_service.sync_symbols(exchange)
        return ApiResponse(
            code=0,
            message=f"成功同步{len(symbols)}个货币对",
            data={"count": len(symbols)}
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"同步货币对失败: {str(e)}",
            data=None
        )
