# -*- coding: utf-8 -*-
"""
通知模块

提供统一的通知服务,支持多种通知渠道:
- 邮件通知 (SMTP)
- 企业微信 (WeCom)
- 飞书 (Feishu)
- WebSocket 实时推送

使用示例:
    from common.notifications import NotificationService, NotificationChannel
    
    # 发送系统通知
    await NotificationService.send_system_notification(
        title="任务完成",
        message="回测任务已成功完成",
        channels=[NotificationChannel.EMAIL, NotificationChannel.WEBSOCKET]
    )
    
    # 发送告警通知
    await NotificationService.send_alert(
        title="系统告警",
        message="CPU使用率超过90%",
        level=NotificationLevel.WARNING
    )
"""

from .models import (
    NotificationCategory,
    NotificationChannel,
    NotificationLevel,
    NotificationMessage,
    NotificationConfig,
    EmailConfig,
    WeComConfig,
    FeishuConfig,
    NotificationHistory,
)
from .service import NotificationService, notification_service
from .channels import EmailChannel, WeComChannel, FeishuChannel, WebSocketChannel

__all__ = [
    # 枚举类型
    "NotificationCategory",
    "NotificationChannel",
    "NotificationLevel",
    # 数据模型
    "NotificationMessage",
    "NotificationConfig",
    "EmailConfig",
    "WeComConfig",
    "FeishuConfig",
    "NotificationHistory",
    # 服务类
    "NotificationService",
    "notification_service",
    # 渠道实现
    "EmailChannel",
    "WeComChannel",
    "FeishuChannel",
    "WebSocketChannel",
]
