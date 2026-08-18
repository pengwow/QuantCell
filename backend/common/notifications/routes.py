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

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required
from utils.logger import LogType, get_logger

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
    channels: list[str] = Field(default=[], description="发送渠道列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class SendSystemNotificationRequest(BaseModel):
    """发送系统通知请求"""

    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    level: NotificationLevel = Field(default=NotificationLevel.INFO, description="通知级别")
    channels: list[str] = Field(default=[], description="发送渠道列表")


class SendAlertRequest(BaseModel):
    """发送告警通知请求"""

    title: str = Field(..., description="告警标题")
    message: str = Field(..., description="告警内容")
    level: NotificationLevel = Field(default=NotificationLevel.WARNING, description="告警级别")
    channels: list[str] = Field(default=[], description="发送渠道列表")


class SendTaskNotificationRequest(BaseModel):
    """发送任务通知请求"""

    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    task_id: str | None = Field(default=None, description="任务ID")
    level: NotificationLevel = Field(default=NotificationLevel.INFO, description="通知级别")
    channels: list[str] = Field(default=[], description="发送渠道列表")


def parse_channels(channels: list[str]) -> list[NotificationChannel]:
    channel_map = {
        "email": NotificationChannel.EMAIL,
        "wecom": NotificationChannel.WECOM,
        "feishu": NotificationChannel.FEISHU,
        "websocket": NotificationChannel.WEBSOCKET,
    }
    return [ch for ch in (channel_map.get(c.lower()) for c in channels) if ch]


# ponytail: 全部改为 async def + await，避免 run_until_complete 死锁
@router.post("/send", response_model=ApiResponse)
@jwt_auth_required
async def send_notification(request: Request, data: SendNotificationRequest = Body(...)):
    try:
        logger.info(f"发送通知: {data.title}")
        channels = parse_channels(data.channels) if data.channels else None
        result = await notification_service.send_notification(
            title=data.title,
            content=data.content,
            level=data.level,
            category=data.category,
            channels=channels,
            metadata=data.metadata,
        )
        return ApiResponse(
            code=0 if result.get("success") else 500,
            message="通知发送成功" if result.get("success") else "通知发送失败",
            data=result,
        )
    except Exception as e:
        logger.error(f"发送通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system", response_model=ApiResponse)
@jwt_auth_required
async def send_system_notification(request: Request, data: SendSystemNotificationRequest = Body(...)):
    try:
        logger.info(f"发送系统通知: {data.title}")
        channels = parse_channels(data.channels) if data.channels else None
        result = await notification_service.send_system_notification(
            title=data.title,
            message=data.message,
            level=data.level,
            channels=channels,
        )
        return ApiResponse(
            code=0 if result.get("success") else 500,
            message="系统通知发送成功" if result.get("success") else "系统通知发送失败",
            data=result,
        )
    except Exception as e:
        logger.error(f"发送系统通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alert", response_model=ApiResponse)
@jwt_auth_required
async def send_alert(request: Request, data: SendAlertRequest = Body(...)):
    try:
        logger.info(f"发送告警通知: {data.title}")
        channels = parse_channels(data.channels) if data.channels else None
        result = await notification_service.send_alert(
            title=data.title,
            message=data.message,
            level=data.level,
            channels=channels,
        )
        return ApiResponse(
            code=0 if result.get("success") else 500,
            message="告警通知发送成功" if result.get("success") else "告警通知发送失败",
            data=result,
        )
    except Exception as e:
        logger.error(f"发送告警通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/task", response_model=ApiResponse)
@jwt_auth_required
async def send_task_notification(request: Request, data: SendTaskNotificationRequest = Body(...)):
    try:
        logger.info(f"发送任务通知: {data.title}")
        channels = parse_channels(data.channels) if data.channels else None
        result = await notification_service.send_task_notification(
            title=data.title,
            message=data.message,
            task_id=data.task_id,
            level=data.level,
            channels=channels,
        )
        return ApiResponse(
            code=0 if result.get("success") else 500,
            message="任务通知发送成功" if result.get("success") else "任务通知发送失败",
            data=result,
        )
    except Exception as e:
        logger.error(f"发送任务通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ApiResponse)
@jwt_auth_required
async def get_notification_status(request: Request):
    try:
        logger.info("获取通知渠道状态")
        status = notification_service.get_channel_status()
        enabled_channels = notification_service.get_enabled_channels()
        return ApiResponse(
            code=0,
            message="获取通知渠道状态成功",
            data={"channels": status, "enabled": [ch.value for ch in enabled_channels]},
        )
    except Exception as e:
        logger.error(f"获取通知渠道状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
