# -*- coding: utf-8 -*-
"""
系统管理API路由模块

提供系统级别的API接口：
- 同步状态查询
- 手动触发同步
- 插件配置查询
- 健康检查等
"""

from fastapi import APIRouter
from loguru import logger

from services.symbol_sync import symbol_sync_manager
from utils.i18n import get_translation_dict, extract_lang

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/sync-status")
async def get_sync_status():
    """获取货币对同步状态

    Returns:
        dict: 同步状态信息
    """
    return {
        "code": 0,
        "message": "获取同步状态成功",
        "data": {
            "status": symbol_sync_manager.status.value,
            "is_syncing": symbol_sync_manager.is_syncing,
            "consecutive_failures": symbol_sync_manager.consecutive_failures,
            "last_sync_time": symbol_sync_manager.last_sync_time.isoformat() if symbol_sync_manager.last_sync_time else None,
            "has_symbols_data": symbol_sync_manager.check_symbols_exist()
        }
    }


@router.post("/sync-symbols")
async def trigger_sync_symbols(exchange: str = "binance"):
    """手动触发货币对同步

    Args:
        exchange: 交易所名称，默认为binance

    Returns:
        dict: 同步结果
    """
    result = await symbol_sync_manager.async_perform_sync(exchange=exchange)

    if result.get("success"):
        return {
            "code": 0,
            "message": "同步任务已启动",
            "data": result
        }
    else:
        return {
            "code": 500,
            "message": result.get("message", "同步失败"),
            "data": result
        }


@router.get("/config/plugin/{plugin_name}")
def get_plugin_config(plugin_name: str):
    """获取指定插件的所有配置

    Args:
        plugin_name: 插件名称

    Returns:
        dict: 包含插件配置的响应
    """
    try:
        logger.info(f"开始获取插件配置: {plugin_name}")

        # 导入系统配置业务逻辑
        from collector.db import SystemConfigBusiness as SystemConfig

        # 获取所有配置的详细信息
        all_configs = SystemConfig.get_all_with_details()

        # 过滤出与指定插件相关的配置
        plugin_configs = {}
        for key, config in all_configs.items():
            if config.get("plugin") == plugin_name:
                plugin_configs[key] = config["value"]

        logger.info(f"成功获取插件配置，共 {len(plugin_configs)} 项")

        return {"code": 0, "message": "获取插件配置成功", "data": plugin_configs}
    except Exception as e:
        logger.error(f"获取插件配置失败: {e}")
        return {"code": 500, "message": f"获取插件配置失败: {str(e)}", "data": {}}


@router.get("/health")
async def health_check():
    """系统健康检查

    Returns:
        dict: 健康状态
    """
    return {
        "code": 0,
        "message": "系统运行正常",
        "data": {
            "status": "healthy",
            "sync_status": symbol_sync_manager.status.value,
            "has_symbols_data": symbol_sync_manager.check_symbols_exist()
        }
    }
