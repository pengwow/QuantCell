# API路由
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List
from loguru import logger

# 创建API路由实例
realtime_router = APIRouter(prefix="/api/realtime", tags=["realtime-engine"])

# 全局实例引用
from loguru import logger

realtime_engine = None

logger.info(f"初始化routes模块，realtime_engine初始值: {realtime_engine}")


def setup_routes(engine):
    """
    设置路由，注入实时引擎实例
    
    Args:
        engine: 实时引擎实例
    """
    global realtime_engine
    logger.info(f"setup_routes被调用，传入的engine: {engine}")
    realtime_engine = engine
    logger.info(f"setup_routes执行后，realtime_engine: {realtime_engine}")


@realtime_router.get("/status", response_model=Dict[str, Any])
async def get_realtime_status():
    """
    获取实时引擎状态
    
    Returns:
        Dict[str, Any]: 实时引擎状态
    """
    try:
        if not realtime_engine:
            return {
                "status": "stopped",
                "connected": False,
                "message": "实时引擎未初始化"
            }
        
        status = realtime_engine.get_status()
        return status
    
    except Exception as e:
        logger.error(f"获取实时引擎状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.post("/start", response_model=Dict[str, Any])
async def start_realtime_engine():
    """
    启动实时引擎
    
    Returns:
        Dict[str, Any]: 启动结果
    """
    try:
        logger.info(f"start_realtime_engine被调用，当前realtime_engine: {realtime_engine}")
        if not realtime_engine:
            logger.error("start_realtime_engine: realtime_engine为None")
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "success": False
            }
        
        success = await realtime_engine.start()
        return {
            "code": 0 if success else 1,
            "message": "实时引擎启动成功" if success else "实时引擎启动失败",
            "success": success
        }
    
    except Exception as e:
        logger.error(f"启动实时引擎失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.post("/stop", response_model=Dict[str, Any])
async def stop_realtime_engine():
    """
    停止实时引擎
    
    Returns:
        Dict[str, Any]: 停止结果
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "success": False
            }
        
        success = await realtime_engine.stop()
        return {
            "code": 0 if success else 1,
            "message": "实时引擎停止成功" if success else "实时引擎停止失败",
            "success": success
        }
    
    except Exception as e:
        logger.error(f"停止实时引擎失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.post("/restart", response_model=Dict[str, Any])
async def restart_realtime_engine():
    """
    重启实时引擎
    
    Returns:
        Dict[str, Any]: 重启结果
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "success": False
            }
        
        success = await realtime_engine.restart()
        return {
            "code": 0 if success else 1,
            "message": "实时引擎重启成功" if success else "实时引擎重启失败",
            "success": success
        }
    
    except Exception as e:
        logger.error(f"重启实时引擎失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.get("/config", response_model=Dict[str, Any])
async def get_realtime_config():
    """
    获取实时引擎配置
    
    Returns:
        Dict[str, Any]: 实时引擎配置
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "data": {}
            }
        
        config = realtime_engine.get_config()
        return {
            "code": 0,
            "message": "获取配置成功",
            "data": config
        }
    
    except Exception as e:
        logger.error(f"获取实时引擎配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.post("/config", response_model=Dict[str, Any])
async def update_realtime_config(request: Request, config: Dict[str, Any]):
    """
    更新实时引擎配置
    
    Args:
        config: 配置字典
    
    Returns:
        Dict[str, Any]: 更新结果
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "success": False
            }
        
        success = realtime_engine.update_config(config)
        return {
            "code": 0 if success else 1,
            "message": "配置更新成功" if success else "配置更新失败",
            "success": success
        }
    
    except Exception as e:
        logger.error(f"更新实时引擎配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.post("/subscribe", response_model=Dict[str, Any])
async def subscribe_channels(channels: List[str]):
    """
    订阅频道
    
    Args:
        channels: 频道列表
    
    Returns:
        Dict[str, Any]: 订阅结果
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "success": False
            }
        
        success = await realtime_engine.subscribe(channels)
        return {
            "code": 0 if success else 1,
            "message": "订阅成功" if success else "订阅失败",
            "success": success
        }
    
    except Exception as e:
        logger.error(f"订阅频道失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.post("/unsubscribe", response_model=Dict[str, Any])
async def unsubscribe_channels(channels: List[str]):
    """
    取消订阅频道
    
    Args:
        channels: 频道列表
    
    Returns:
        Dict[str, Any]: 取消订阅结果
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "success": False
            }
        
        success = await realtime_engine.unsubscribe(channels)
        return {
            "code": 0 if success else 1,
            "message": "取消订阅成功" if success else "取消订阅失败",
            "success": success
        }
    
    except Exception as e:
        logger.error(f"取消订阅频道失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.get("/symbols", response_model=Dict[str, Any])
async def get_available_symbols():
    """
    获取可用交易对
    
    Returns:
        Dict[str, Any]: 可用交易对
    """
    try:
        if not realtime_engine:
            return {
                "code": 1,
                "message": "实时引擎未初始化",
                "data": []
            }
        
        symbols = realtime_engine.get_available_symbols()
        return {
            "code": 0,
            "message": "获取可用交易对成功",
            "data": symbols
        }
    
    except Exception as e:
        logger.error(f"获取可用交易对失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.get("/data-types", response_model=Dict[str, Any])
async def get_supported_data_types():
    """
    获取支持的数据类型
    
    Returns:
        Dict[str, Any]: 支持的数据类型
    """
    try:
        # 返回支持的数据类型
        return {
            "code": 0,
            "message": "获取支持的数据类型成功",
            "data": [
                "kline",
                "depth",
                "aggTrade",
                "trade",
                "ticker",
                "miniTicker",
                "bookTicker"
            ]
        }
    
    except Exception as e:
        logger.error(f"获取支持的数据类型失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@realtime_router.get("/intervals", response_model=Dict[str, Any])
async def get_supported_intervals():
    """
    获取支持的时间间隔
    
    Returns:
        Dict[str, Any]: 支持的时间间隔
    """
    try:
        # 返回支持的时间间隔
        return {
            "code": 0,
            "message": "获取支持的时间间隔成功",
            "data": [
                "1m",
                "3m",
                "5m",
                "15m",
                "30m",
                "1h",
                "2h",
                "4h",
                "6h",
                "8h",
                "12h",
                "1d",
                "3d",
                "1w",
                "1M"
            ]
        }
    
    except Exception as e:
        logger.error(f"获取支持的时间间隔失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))