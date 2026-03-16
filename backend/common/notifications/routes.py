 # -*- coding: utf-8 -*-
"""
通知模块API路由

提供通知发送、状态查询等RESTful API端点

路由前缀:
    - /api/notifications: 通知管理

包含端点:
    - POST /api/notifications/send: 发送通知
    - POST /api/notifications/system: 发送系统通知
    - POST /api/notifications/alert: 发送告警通知
    - POST /api/notifications/task: 发送任务通知
    - GET /api/notifications/status: 获取通知渠道状态

标签: notifications

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-16
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required_sync
from utils.logger import get_logger, LogType

from .models import NotificationCategory, NotificationChannel, NotificationLevel
from .service import notification_service

logger = get_logger(__name__, LogType.APPLICATION)

# 创建API路由实例
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class SendNotificationRequest(BaseModel):
    """发送通知请求"""
    title: str = Field(..., description="通知标题")
    content: str = Field(..., description="通知内容")
    level: NotificationLevel = Field(default=NotificationLevel.INFO, description="通知级别")
    category: NotificationCategory = Field(default=NotificationCategory.SYSTEM, description="通知分类")
    channels: List[str] = Field(default=[], description="发送渠道列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class SendSystemNotificationRequest(BaseModel):
    """发送系统通知请求"""
    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    level: NotificationLevel = Field(default=NotificationLevel.INFO, description="通知级别")
    channels: List[str] = Field(default=[], description="发送渠道列表")


class SendAlertRequest(BaseModel):
    """发送告警通知请求"""
    title: str = Field(..., description="告警标题")
    message: str = Field(..., description="告警内容")
    level: NotificationLevel = Field(default=NotificationLevel.WARNING, description="告警级别")
    channels: List[str] = Field(default=[], description="发送渠道列表")


class SendTaskNotificationRequest(BaseModel):
    """发送任务通知请求"""
    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    level: NotificationLevel = Field(default=NotificationLevel.INFO, description="通知级别")
    channels: List[str] = Field(default=[], description="发送渠道列表")


def parse_channels(channels: List[str]) -> List[NotificationChannel]:
    """解析渠道字符串列表为NotificationChannel枚举列表
    
    Args:
        channels: 渠道字符串列表
        
    Returns:
        List[NotificationChannel]: 渠道枚举列表
    """
    channel_map = {
        "email": NotificationChannel.EMAIL,
        "wecom": NotificationChannel.WECOM,
        "feishu": NotificationChannel.FEISHU,
        "websocket": NotificationChannel.WEBSOCKET,
    }
    
    result = []
    for ch in channels:
        channel = channel_map.get(ch.lower())
        if channel:
            result.append(channel)
    return result


@router.post("/send", response_model=ApiResponse)
@jwt_auth_required_sync
def send_notification(request: Request, data: SendNotificationRequest = Body(...)):
    """发送通用通知
    
    发送通知到指定的渠道
    
    Args:
        request: FastAPI请求对象
        data: 通知数据
        
    Returns:
        ApiResponse: 发送结果
    """
    import asyncio
    
    try:
        logger.info(f"发送通知: {data.title}")
        
        # 解析渠道
        channels = parse_channels(data.channels) if data.channels else None
        
        # 异步发送通知
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            notification_service.send_notification(
                title=data.title,
                content=data.content,
                level=data.level,
                category=data.category,
                channels=channels,
                metadata=data.metadata,
            )
        )
        
        if result.get("success"):
            return ApiResponse(
                code=0,
                message="通知发送成功",
                data=result
            )
        else:
            return ApiResponse(
                code=500,
                message="通知发送失败",
                data=result
            )
            
    except Exception as e:
        logger.error(f"发送通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system", response_model=ApiResponse)
@jwt_auth_required_sync
def send_system_notification(request: Request, data: SendSystemNotificationRequest = Body(...)):
    """发送系统通知
    
    发送系统级别的通知
    
    Args:
        request: FastAPI请求对象
        data: 通知数据
        
    Returns:
        ApiResponse: 发送结果
    """
    import asyncio
    
    try:
        logger.info(f"发送系统通知: {data.title}")
        
        # 解析渠道
        channels = parse_channels(data.channels) if data.channels else None
        
        # 异步发送通知
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            notification_service.send_system_notification(
                title=data.title,
                message=data.message,
                level=data.level,
                channels=channels,
            )
        )
        
        if result.get("success"):
            return ApiResponse(
                code=0,
                message="系统通知发送成功",
                data=result
            )
        else:
            return ApiResponse(
                code=500,
                message="系统通知发送失败",
                data=result
            )
            
    except Exception as e:
        logger.error(f"发送系统通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alert", response_model=ApiResponse)
@jwt_auth_required_sync
def send_alert(request: Request, data: SendAlertRequest = Body(...)):
    """发送告警通知
    
    发送告警级别的通知
    
    Args:
        request: FastAPI请求对象
        data: 告警数据
        
    Returns:
        ApiResponse: 发送结果
    """
    import asyncio
    
    try:
        logger.info(f"发送告警通知: {data.title}")
        
        # 解析渠道
        channels = parse_channels(data.channels) if data.channels else None
        
        # 异步发送通知
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            notification_service.send_alert(
                title=data.title,
                message=data.message,
                level=data.level,
                channels=channels,
            )
        )
        
        if result.get("success"):
            return ApiResponse(
                code=0,
                message="告警通知发送成功",
                data=result
            )
        else:
            return ApiResponse(
                code=500,
                message="告警通知发送失败",
                data=result
            )
            
    except Exception as e:
        logger.error(f"发送告警通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/task", response_model=ApiResponse)
@jwt_auth_required_sync
def send_task_notification(request: Request, data: SendTaskNotificationRequest = Body(...)):
    """发送任务通知
    
    发送任务相关的通知
    
    Args:
        request: FastAPI请求对象
        data: 任务通知数据
        
    Returns:
        ApiResponse: 发送结果
    """
    import asyncio
    
    try:
        logger.info(f"发送任务通知: {data.title}")
        
        # 解析渠道
        channels = parse_channels(data.channels) if data.channels else None
        
        # 异步发送通知
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            notification_service.send_task_notification(
                title=data.title,
                message=data.message,
                task_id=data.task_id,
                level=data.level,
                channels=channels,
            )
        )
        
        if result.get("success"):
            return ApiResponse(
                code=0,
                message="任务通知发送成功",
                data=result
            )
        else:
            return ApiResponse(
                code=500,
                message="任务通知发送失败",
                data=result
            )
            
    except Exception as e:
        logger.error(f"发送任务通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ApiResponse)
@jwt_auth_required_sync
def get_notification_status(request: Request):
    """获取通知渠道状态
    
    获取所有通知渠道的当前状态
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        ApiResponse: 渠道状态信息
    """
    try:
        logger.info("获取通知渠道状态")
        
        status = notification_service.get_channel_status()
        enabled_channels = notification_service.get_enabled_channels()
        
        return ApiResponse(
            code=0,
            message="获取通知渠道状态成功",
            data={
                "channels": status,
                "enabled": [ch.value for ch in enabled_channels],
            }
        )
        
    except Exception as e:
        logger.error(f"获取通知渠道状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
