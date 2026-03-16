# -*- coding: utf-8 -*-
"""
通知模块数据模型

定义通知相关的数据模型,包括消息、配置、历史记录等
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NotificationChannel(str, Enum):
    """通知渠道类型"""
    EMAIL = "email"
    WECOM = "wecom"
    FEISHU = "feishu"
    WEBSOCKET = "websocket"


class NotificationLevel(str, Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationCategory(str, Enum):
    """通知分类"""
    SYSTEM = "system"
    TASK = "task"
    ALERT = "alert"
    TRADE = "trade"
    SECURITY = "security"


class NotificationMessage(BaseModel):
    """通知消息模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="消息唯一ID")
    title: str = Field(..., description="消息标题")
    content: str = Field(..., description="消息内容")
    level: NotificationLevel = Field(default=NotificationLevel.INFO, description="通知级别")
    category: NotificationCategory = Field(default=NotificationCategory.SYSTEM, description="通知分类")
    channels: List[NotificationChannel] = Field(default=[], description="目标通知渠道")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EmailConfig(BaseModel):
    """邮件通知配置"""
    smtp_host: str = Field(default="", description="SMTP服务器地址")
    smtp_port: int = Field(default=465, description="SMTP服务器端口")
    security: str = Field(default="ssl", description="连接安全性: ssl, starttls, none")
    ignore_ssl: bool = Field(default=False, description="是否忽略SSL证书错误")
    username: str = Field(default="", description="用户名")
    password: str = Field(default="", description="密码")
    sender_email: str = Field(default="", description="发件人邮箱")
    sender_name: str = Field(default="", description="发件人名称")
    recipient_email: str = Field(default="", description="默认收件人邮箱")
    enabled: bool = Field(default=False, description="是否启用")
    is_default: bool = Field(default=False, description="是否为默认渠道")


class WeComConfig(BaseModel):
    """企业微信通知配置"""
    webhook_url: str = Field(default="", description="群机器人Webhook地址")
    use_custom_format: bool = Field(default=False, description="是否使用自定义格式")
    message_format: str = Field(
        default='{"msgtype": "text", "text": {"content": "${NOTIFIER_SUBJECT}\\n\\n${NOTIFIER_MESSAGE}"}}',
        description="消息格式模板"
    )
    enabled: bool = Field(default=False, description="是否启用")
    is_default: bool = Field(default=False, description="是否为默认渠道")


class FeishuConfig(BaseModel):
    """飞书通知配置"""
    webhook_url: str = Field(default="", description="群机器人Webhook地址")
    use_custom_format: bool = Field(default=False, description="是否使用自定义格式")
    message_format: str = Field(
        default='{"msg_type": "text", "content": {"text": "${NOTIFIER_SUBJECT}\\n\\n${NOTIFIER_MESSAGE}"}}',
        description="消息格式模板"
    )
    enabled: bool = Field(default=False, description="是否启用")
    is_default: bool = Field(default=False, description="是否为默认渠道")


class WebSocketConfig(BaseModel):
    """WebSocket通知配置"""
    enabled: bool = Field(default=True, description="是否启用")
    is_default: bool = Field(default=True, description="是否为默认渠道")
    broadcast_all: bool = Field(default=True, description="是否广播给所有连接")
    topic_prefix: str = Field(default="notification", description="主题前缀")


class NotificationConfig(BaseModel):
    """通知总配置"""
    email: EmailConfig = Field(default_factory=EmailConfig, description="邮件配置")
    wecom: WeComConfig = Field(default_factory=WeComConfig, description="企业微信配置")
    feishu: FeishuConfig = Field(default_factory=FeishuConfig, description="飞书配置")
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig, description="WebSocket配置")
    
    @classmethod
    def from_system_config(cls, config_data: Dict[str, Any]) -> "NotificationConfig":
        """从系统配置数据解析通知配置"""
        result = cls()
        
        # 解析邮件配置
        if "email" in config_data:
            email_data = config_data["email"]
            if isinstance(email_data, str):
                try:
                    email_data = json.loads(email_data)
                except json.JSONDecodeError:
                    email_data = {}
            if isinstance(email_data, dict):
                result.email = EmailConfig(
                    smtp_host=email_data.get("smtpHost", ""),
                    smtp_port=int(email_data.get("smtpPort", 465)),
                    security=email_data.get("security", "ssl"),
                    ignore_ssl=email_data.get("ignoreSSL", False),
                    username=email_data.get("username", ""),
                    password=email_data.get("password", ""),
                    sender_email=email_data.get("senderEmail", ""),
                    sender_name=email_data.get("senderName", ""),
                    recipient_email=email_data.get("recipientEmail", ""),
                    enabled=email_data.get("enabled", False),
                    is_default=email_data.get("isDefault", False),
                )
        
        # 解析企业微信配置
        if "wecom" in config_data:
            wecom_data = config_data["wecom"]
            if isinstance(wecom_data, str):
                try:
                    wecom_data = json.loads(wecom_data)
                except json.JSONDecodeError:
                    wecom_data = {}
            if isinstance(wecom_data, dict):
                config = wecom_data.get("config", wecom_data)
                result.wecom = WeComConfig(
                    webhook_url=config.get("webhookUrl", ""),
                    use_custom_format=config.get("useCustomFormat", False),
                    message_format=config.get("messageFormat", result.wecom.message_format),
                    enabled=wecom_data.get("enabled", False),
                    is_default=wecom_data.get("isDefault", False),
                )
        
        # 解析飞书配置
        if "feishu" in config_data:
            feishu_data = config_data["feishu"]
            if isinstance(feishu_data, str):
                try:
                    feishu_data = json.loads(feishu_data)
                except json.JSONDecodeError:
                    feishu_data = {}
            if isinstance(feishu_data, dict):
                config = feishu_data.get("config", feishu_data)
                result.feishu = FeishuConfig(
                    webhook_url=config.get("webhookUrl", ""),
                    use_custom_format=config.get("useCustomFormat", False),
                    message_format=config.get("messageFormat", result.feishu.message_format),
                    enabled=feishu_data.get("enabled", False),
                    is_default=feishu_data.get("isDefault", False),
                )
        
        return result
    
    def get_enabled_channels(self) -> List[NotificationChannel]:
        """获取所有启用的通知渠道"""
        channels = []
        if self.email.enabled:
            channels.append(NotificationChannel.EMAIL)
        if self.wecom.enabled:
            channels.append(NotificationChannel.WECOM)
        if self.feishu.enabled:
            channels.append(NotificationChannel.FEISHU)
        if self.websocket.enabled:
            channels.append(NotificationChannel.WEBSOCKET)
        return channels
    
    def get_default_channels(self) -> List[NotificationChannel]:
        """获取默认的通知渠道"""
        channels = []
        if self.email.is_default:
            channels.append(NotificationChannel.EMAIL)
        if self.wecom.is_default:
            channels.append(NotificationChannel.WECOM)
        if self.feishu.is_default:
            channels.append(NotificationChannel.FEISHU)
        if self.websocket.is_default:
            channels.append(NotificationChannel.WEBSOCKET)
        return channels


class NotificationHistory(BaseModel):
    """通知历史记录"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="记录ID")
    message_id: str = Field(..., description="关联的消息ID")
    channel: NotificationChannel = Field(..., description="发送渠道")
    status: str = Field(..., description="发送状态: pending, sent, failed")
    response: Optional[str] = Field(default=None, description="渠道响应")
    error: Optional[str] = Field(default=None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    sent_at: Optional[datetime] = Field(default=None, description="发送时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
