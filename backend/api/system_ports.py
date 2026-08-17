# -*- coding: utf-8 -*-
"""
系统端口配置 API

提供当前系统所有服务的端口配置查询接口，
支持前端动态获取后端端口地址。
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime
import os

from utils.logger import get_logger, LogType
from core.port_manager import PortManager, PORT_RANGES

logger = get_logger(__name__, LogType.SYSTEM)

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/ports")
async def get_system_ports():
    """
    获取当前系统所有服务的端口配置

    返回所有服务的端口号、PID、启动时间等信息。
    前端可使用此接口动态更新 API 和 WebSocket 连接地址。

    Returns:
        dict: 包含所有服务端口配置的字典

    Example:
        {
            "code": 0,
            "message": "success",
            "data": {
                "fastapi": {"port": 8000, "service": "HTTP API Server"},
                "metadata": {
                    "pid": 12345,
                    "start_time": "2026-05-13T10:30:00Z",
                    "last_updated": "2026-05-13T10:30:00Z",
                    "config_file": "/path/to/port_config.json"
                }
            }
        }
    """
    try:
        all_ports = PortManager().get_all_ports()

        service_descriptions = {
            "fastapi": "HTTP API Server",
        }

        result = {}
        for service_name, port in all_ports.items():
            result[service_name] = {
                "port": port,
                "service": service_descriptions.get(service_name, "Unknown Service"),
            }

        metadata = {
            "pid": os.getpid(),
            "start_time": datetime.now().isoformat() + "Z",
            "last_updated": datetime.now().isoformat() + "Z",
            "config_file": str(PortManager().config_path),
        }

        logger.debug(f"[SystemPorts] 返回端口配置: {result}")

        return {
            "code": 0,
            "message": "success",
            "data": {
                **result,
                "metadata": metadata,
            },
        }

    except Exception as e:
        logger.error(f"[SystemPorts] 获取端口配置失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get port configuration: {str(e)}"
        )


@router.get("/ports/{service_name}")
async def get_service_port(service_name: str):
    """
    获取指定服务的端口配置

    Args:
        service_name: 服务名称 (fastapi)

    Returns:
        dict: 指定服务的端口配置

    Raises:
        HTTPException: 服务名称无效时返回 404
    """
    valid_services = ["fastapi"]

    if service_name not in valid_services:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid service name: {service_name}. Valid services: {valid_services}"
        )

    try:
        port = PortManager().get_port(service_name)

        service_descriptions = {
            "fastapi": "HTTP API Server",
        }

        return {
            "code": 0,
            "message": "success",
            "data": {
                "service": service_name,
                "port": port,
                "description": service_descriptions.get(service_name),
            }
        }

    except Exception as e:
        logger.error(f"[SystemPorts] 获取服务 {service_name} 端口失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get port for {service_name}: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    健康检查端点

    简单的健康检查，确认端口管理服务正常工作。

    Returns:
        dict: 健康状态
    """
    return {
        "status": "healthy",
        "service": "port-manager",
        "timestamp": datetime.now().isoformat() + "Z",
        "version": "1.0.0",
    }