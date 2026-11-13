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
    - GET /api/notifications/inbox: 站内收件箱列表（游标分页 + 未读数）
    - POST /api/notifications/inbox/read-all: 站内收件箱全部已读
    - DELETE /api/notifications/inbox/read: 清空收件箱已读（保留未读）
    - DELETE /api/notifications/inbox/{id}: 删除单条站内通知

标签: notifications

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-16
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from utils.auth import get_current_user
from utils.logger import LogType, get_logger
from utils.rbac import is_guest_user

from . import inbox
from .models import NotificationCategory, NotificationChannel, NotificationLevel
from .service import notification_service

logger = get_logger(__name__, LogType.APPLICATION)

# 创建API路由实例
router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


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
async def send_notification(
    data: SendNotificationRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
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
async def send_system_notification(
    data: SendSystemNotificationRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
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
async def send_alert(
    data: SendAlertRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
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
async def send_task_notification(
    data: SendTaskNotificationRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
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


@router.get("/inbox", response_model=ApiResponse)
async def list_inbox_notifications(
    http_request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    before_id: int | None = Query(default=None, description="游标：取 id 小于该值的更旧一页"),
    current_user: dict = Depends(get_current_user),
):
    """站内收件箱列表（按 id 倒序游标分页，携带全局未读数）"""
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权查看站内收件箱")
    try:
        data = inbox.list_inbox_notifications(limit=limit, before_id=before_id)
        return ApiResponse(code=0, message="获取站内收件箱成功", data=data)
    except Exception as e:
        logger.error(f"获取站内收件箱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inbox/read-all", response_model=ApiResponse)
async def mark_inbox_read(
    http_request: Request,
    current_user: dict = Depends(get_current_user),
):
    """站内收件箱全部已读（推送全局已读水位到当前时间）"""
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权操作站内收件箱")
    try:
        inbox.mark_inbox_read()
        return ApiResponse(code=0, message="站内收件箱已全部标记为已读", data={"ok": True})
    except Exception as e:
        logger.error(f"站内收件箱全部已读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注意：固定路径 /inbox/read 必须注册在 /inbox/{notification_id} 之前，
# 否则 "read" 会被当作路径参数解析后 int 校验失败返回 422
@router.delete("/inbox/read", response_model=ApiResponse)
async def clear_read_inbox_notifications(
    http_request: Request,
    current_user: dict = Depends(get_current_user),
):
    """清空收件箱已读通知（保留未读，物理删除）"""
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权操作站内收件箱")
    try:
        deleted, unread_count = inbox.clear_read_notifications()
        return ApiResponse(
            code=0, message="已清空全部已读通知", data={"deleted": deleted, "unread_count": unread_count}
        )
    except Exception as e:
        logger.error(f"清空收件箱已读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inbox/{notification_id}", response_model=ApiResponse)
async def delete_inbox_notification(
    http_request: Request,
    notification_id: int,
    current_user: dict = Depends(get_current_user),
):
    """删除单条站内通知（物理删除）"""
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权操作站内收件箱")
    try:
        unread_count = inbox.delete_notification(notification_id)
        if unread_count is None:
            raise HTTPException(status_code=404, detail="通知不存在或已删除")
        return ApiResponse(code=0, message="通知已删除", data={"ok": True, "unread_count": unread_count})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除站内通知失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ApiResponse)
async def get_notification_status(current_user: dict = Depends(get_current_user)):
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
