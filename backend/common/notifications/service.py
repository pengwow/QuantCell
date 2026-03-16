# -*- coding: utf-8 -*-
"""
通知服务

提供统一的通知发送接口,管理所有通知渠道
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.logger import get_logger, LogType

from .channels import (
    EmailChannel,
    FeishuChannel,
    WebSocketChannel,
    WeComChannel,
)
from .models import (
    NotificationCategory,
    NotificationChannel,
    NotificationConfig,
    NotificationHistory,
    NotificationLevel,
    NotificationMessage,
)

logger = get_logger(__name__, LogType.APPLICATION)


class NotificationService:
    """通知服务类

    提供统一的通知发送接口,管理所有通知渠道
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._channels = {
            NotificationChannel.EMAIL: EmailChannel(),
            NotificationChannel.WECOM: WeComChannel(),
            NotificationChannel.FEISHU: FeishuChannel(),
            NotificationChannel.WEBSOCKET: WebSocketChannel(),
        }
        self._config: Optional[NotificationConfig] = None
        self._config_cache_time: Optional[datetime] = None
        self._config_cache_ttl = 60  # 配置缓存时间(秒)

    def _load_config(self) -> NotificationConfig:
        """加载通知配置

        从系统配置中加载通知配置,带缓存机制

        Returns:
            NotificationConfig: 通知配置
        """
        now = datetime.now()

        # 检查缓存是否有效
        if (
            self._config is not None
            and self._config_cache_time is not None
            and (now - self._config_cache_time).seconds < self._config_cache_ttl
        ):
            return self._config

        try:
            # 延迟导入避免循环依赖
            from settings.models import SystemConfigBusiness as SystemConfig

            # 从系统配置读取通知配置
            config_data = {}

            # 读取各个渠道的配置
            for channel_id in ["email", "wecom", "feishu"]:
                config_json = SystemConfig.get(channel_id)
                if config_json:
                    try:
                        channel_config = json.loads(config_json)
                        config_data[channel_id] = channel_config
                    except json.JSONDecodeError:
                        logger.warning(f"解析{channel_id}配置失败")

            self._config = NotificationConfig.from_system_config(config_data)
            self._config_cache_time = now

            return self._config

        except Exception as e:
            logger.error(f"加载通知配置失败: {e}")
            return NotificationConfig()

    def reload_config(self):
        """重新加载配置

        清除缓存并重新加载配置
        """
        self._config = None
        self._config_cache_time = None
        logger.info("通知配置缓存已清除")

    async def send(
        self,
        message: NotificationMessage,
        channels: Optional[List[NotificationChannel]] = None,
    ) -> Dict[str, Any]:
        """发送通知

        Args:
            message: 通知消息
            channels: 指定发送渠道(可选,默认使用消息中指定的渠道或默认渠道)

        Returns:
            Dict: 发送结果,包含各渠道的发送状态
        """
        config = self._load_config()

        # 确定发送渠道
        target_channels = channels or message.channels or config.get_default_channels()

        if not target_channels:
            logger.warning("没有可用的通知渠道")
            return {"success": False, "error": "没有可用的通知渠道"}

        results = {
            "success": True,
            "message_id": message.id,
            "channels": {},
        }

        # 发送到各个渠道
        for channel_type in target_channels:
            channel = self._channels.get(channel_type)
            if not channel:
                results["channels"][channel_type.value] = {
                    "success": False,
                    "error": "未知的通知渠道",
                }
                continue

            try:
                if channel_type == NotificationChannel.EMAIL:
                    result = await channel.send(message, config.email)
                elif channel_type == NotificationChannel.WECOM:
                    result = await channel.send(message, config.wecom)
                elif channel_type == NotificationChannel.FEISHU:
                    result = await channel.send(message, config.feishu)
                elif channel_type == NotificationChannel.WEBSOCKET:
                    result = await channel.send(message, config.websocket)
                else:
                    result = {"success": False, "error": "未实现的通知渠道"}

                results["channels"][channel_type.value] = result

                if not result.get("success"):
                    results["success"] = False

            except Exception as e:
                logger.error(f"发送通知到{channel_type.value}失败: {e}")
                results["channels"][channel_type.value] = {
                    "success": False,
                    "error": str(e),
                }
                results["success"] = False

        return results

    async def send_notification(
        self,
        title: str,
        content: str,
        level: NotificationLevel = NotificationLevel.INFO,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        channels: Optional[List[NotificationChannel]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送通知(便捷方法)

        Args:
            title: 通知标题
            content: 通知内容
            level: 通知级别
            category: 通知分类
            channels: 发送渠道
            metadata: 附加元数据

        Returns:
            Dict: 发送结果
        """
        message = NotificationMessage(
            title=title,
            content=content,
            level=level,
            category=category,
            channels=channels or [],
            metadata=metadata or {},
        )
        return await self.send(message)

    async def send_system_notification(
        self,
        title: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        channels: Optional[List[NotificationChannel]] = None,
    ) -> Dict[str, Any]:
        """发送系统通知

        Args:
            title: 通知标题
            message: 通知内容
            level: 通知级别
            channels: 发送渠道

        Returns:
            Dict: 发送结果
        """
        return await self.send_notification(
            title=title,
            content=message,
            level=level,
            category=NotificationCategory.SYSTEM,
            channels=channels,
        )

    async def send_task_notification(
        self,
        title: str,
        message: str,
        task_id: Optional[str] = None,
        level: NotificationLevel = NotificationLevel.INFO,
        channels: Optional[List[NotificationChannel]] = None,
    ) -> Dict[str, Any]:
        """发送任务通知

        Args:
            title: 通知标题
            message: 通知内容
            task_id: 任务ID
            level: 通知级别
            channels: 发送渠道

        Returns:
            Dict: 发送结果
        """
        metadata = {"task_id": task_id} if task_id else {}
        return await self.send_notification(
            title=title,
            content=message,
            level=level,
            category=NotificationCategory.TASK,
            channels=channels,
            metadata=metadata,
        )

    async def send_alert(
        self,
        title: str,
        message: str,
        level: NotificationLevel = NotificationLevel.WARNING,
        channels: Optional[List[NotificationChannel]] = None,
    ) -> Dict[str, Any]:
        """发送告警通知

        Args:
            title: 告警标题
            message: 告警内容
            level: 告警级别
            channels: 发送渠道

        Returns:
            Dict: 发送结果
        """
        return await self.send_notification(
            title=title,
            content=message,
            level=level,
            category=NotificationCategory.ALERT,
            channels=channels,
        )

    async def send_trade_notification(
        self,
        title: str,
        message: str,
        trade_data: Optional[Dict[str, Any]] = None,
        channels: Optional[List[NotificationChannel]] = None,
    ) -> Dict[str, Any]:
        """发送交易通知

        Args:
            title: 通知标题
            message: 通知内容
            trade_data: 交易数据
            channels: 发送渠道

        Returns:
            Dict: 发送结果
        """
        return await self.send_notification(
            title=title,
            content=message,
            level=NotificationLevel.INFO,
            category=NotificationCategory.TRADE,
            channels=channels,
            metadata=trade_data,
        )

    async def test_channel(
        self, channel_type: NotificationChannel, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """测试通知渠道

        Args:
            channel_type: 渠道类型
            config: 渠道配置(可选,不传则使用系统配置)

        Returns:
            Dict: 测试结果
        """
        test_message = NotificationMessage(
            title="测试通知",
            content="这是一条测试消息,如果您收到此消息,说明通知配置正确。",
            level=NotificationLevel.INFO,
            category=NotificationCategory.SYSTEM,
        )

        try:
            if channel_type == NotificationChannel.EMAIL:
                from .models import EmailConfig

                email_config = EmailConfig(**config) if config else self._load_config().email
                channel = EmailChannel()
                return await channel.send(test_message, email_config)

            elif channel_type == NotificationChannel.WECOM:
                from .models import WeComConfig

                wecom_config = WeComConfig(**config) if config else self._load_config().wecom
                channel = WeComChannel()
                return await channel.send(test_message, wecom_config)

            elif channel_type == NotificationChannel.FEISHU:
                from .models import FeishuConfig

                feishu_config = FeishuConfig(**config) if config else self._load_config().feishu
                channel = FeishuChannel()
                return await channel.send(test_message, feishu_config)

            elif channel_type == NotificationChannel.WEBSOCKET:
                ws_config = self._load_config().websocket
                channel = WebSocketChannel()
                return await channel.send(test_message, ws_config)

            else:
                return {"success": False, "error": "未知的通知渠道"}

        except Exception as e:
            logger.error(f"测试通知渠道失败: {e}")
            return {"success": False, "error": str(e)}

    def get_enabled_channels(self) -> List[NotificationChannel]:
        """获取所有启用的通知渠道

        Returns:
            List[NotificationChannel]: 启用的渠道列表
        """
        config = self._load_config()
        return config.get_enabled_channels()

    def get_channel_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有渠道状态

        Returns:
            Dict: 各渠道的状态信息
        """
        config = self._load_config()
        return {
            "email": {
                "enabled": config.email.enabled,
                "is_default": config.email.is_default,
                "configured": bool(config.email.smtp_host and config.email.username),
            },
            "wecom": {
                "enabled": config.wecom.enabled,
                "is_default": config.wecom.is_default,
                "configured": bool(config.wecom.webhook_url),
            },
            "feishu": {
                "enabled": config.feishu.enabled,
                "is_default": config.feishu.is_default,
                "configured": bool(config.feishu.webhook_url),
            },
            "websocket": {
                "enabled": config.websocket.enabled,
                "is_default": config.websocket.is_default,
                "configured": True,
            },
        }


# 创建全局通知服务实例
notification_service = NotificationService()
