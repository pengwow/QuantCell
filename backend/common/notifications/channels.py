# -*- coding: utf-8 -*-
"""
通知渠道实现

实现各种通知渠道的发送逻辑:
- EmailChannel: SMTP邮件发送
- WeComChannel: 企业微信群机器人
- FeishuChannel: 飞书群机器人
- WebSocketChannel: WebSocket实时推送
"""

import json
import re
import ssl
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from utils.logger import get_logger, LogType
from .models import (
    EmailConfig,
    FeishuConfig,
    NotificationChannel,
    NotificationMessage,
    WeComConfig,
    WebSocketConfig,
)

logger = get_logger(__name__, LogType.APPLICATION)


class BaseChannel(ABC):
    """通知渠道基类"""

    def __init__(self, channel_type: NotificationChannel):
        self.channel_type = channel_type

    @abstractmethod
    async def send(self, message: NotificationMessage, config: Any) -> Dict[str, Any]:
        """发送通知

        Args:
            message: 通知消息
            config: 渠道配置

        Returns:
            Dict: 发送结果,包含success, response, error等字段
        """
        pass

    @abstractmethod
    def validate_config(self, config: Any) -> bool:
        """验证配置是否有效

        Args:
            config: 渠道配置

        Returns:
            bool: 配置是否有效
        """
        pass


class EmailChannel(BaseChannel):
    """邮件通知渠道"""

    def __init__(self):
        super().__init__(NotificationChannel.EMAIL)

    def validate_config(self, config: EmailConfig) -> bool:
        """验证邮件配置"""
        if not config.smtp_host:
            logger.warning("邮件配置无效: SMTP服务器地址为空")
            return False
        if not config.username:
            logger.warning("邮件配置无效: 用户名为空")
            return False
        if not config.password:
            logger.warning("邮件配置无效: 密码为空")
            return False
        return True

    async def send(
        self,
        message: NotificationMessage,
        config: EmailConfig,
        recipient: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送邮件通知

        Args:
            message: 通知消息
            config: 邮件配置
            recipient: 收件人邮箱(可选,默认使用配置中的收件人)

        Returns:
            Dict: 发送结果
        """
        if not self.validate_config(config):
            return {"success": False, "error": "邮件配置无效"}

        try:
            # 构建邮件内容
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.title
            msg["From"] = f"{config.sender_name or config.sender_email or config.username} <{config.sender_email or config.username}>"

            # 确定收件人
            to_email = recipient or config.recipient_email or config.sender_email
            if not to_email:
                return {"success": False, "error": "收件人邮箱未配置"}
            msg["To"] = to_email

            # 添加HTML内容
            html_content = self._build_html_content(message)
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # 添加纯文本内容
            text_content = f"{message.title}\n\n{message.content}"
            msg.attach(MIMEText(text_content, "plain", "utf-8"))

            # 配置SSL上下文
            ssl_context = ssl.create_default_context()
            if config.ignore_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # 根据安全设置选择连接方式
            if config.security == "starttls":
                await aiosmtplib.send(
                    msg,
                    hostname=config.smtp_host,
                    port=config.smtp_port or 587,
                    username=config.username,
                    password=config.password,
                    start_tls=True,
                    tls_context=ssl_context,
                )
            elif config.security == "none":
                await aiosmtplib.send(
                    msg,
                    hostname=config.smtp_host,
                    port=config.smtp_port or 25,
                    username=config.username,
                    password=config.password,
                    use_tls=False,
                )
            else:  # ssl (默认)
                await aiosmtplib.send(
                    msg,
                    hostname=config.smtp_host,
                    port=config.smtp_port or 465,
                    username=config.username,
                    password=config.password,
                    use_tls=True,
                    tls_context=ssl_context,
                )

            logger.info(f"邮件发送成功: {message.title} -> {to_email}")
            return {"success": True, "response": f"邮件已发送至 {to_email}"}

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return {"success": False, "error": str(e)}

    def _build_html_content(self, message: NotificationMessage) -> str:
        """构建HTML格式的邮件内容"""
        level_colors = {
            "info": "#1890ff",
            "success": "#52c41a",
            "warning": "#faad14",
            "error": "#f5222d",
            "critical": "#cf1322",
        }
        color = level_colors.get(message.level.value, "#1890ff")

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .header {{ background: {color}; color: white; padding: 20px; }}
                .header h1 {{ margin: 0; font-size: 20px; }}
                .content {{ padding: 20px; line-height: 1.6; color: #333; }}
                .footer {{ padding: 15px 20px; background: #f8f8f8; font-size: 12px; color: #999; border-top: 1px solid #eee; }}
                .meta {{ margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{message.title}</h1>
                </div>
                <div class="content">
                    {message.content.replace(chr(10), '<br>')}
                    <div class="meta">
                        <p><strong>级别:</strong> {message.level.value.upper()}</p>
                        <p><strong>分类:</strong> {message.category.value}</p>
                        <p><strong>时间:</strong> {message.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                </div>
                <div class="footer">
                    本邮件由 QuantCell 系统自动发送
                </div>
            </div>
        </body>
        </html>
        """


class WeComChannel(BaseChannel):
    """企业微信通知渠道"""

    def __init__(self):
        super().__init__(NotificationChannel.WECOM)

    def validate_config(self, config: WeComConfig) -> bool:
        """验证企业微信配置"""
        if not config.webhook_url:
            logger.warning("企业微信配置无效: Webhook地址为空")
            return False
        return True

    async def send(
        self, message: NotificationMessage, config: WeComConfig
    ) -> Dict[str, Any]:
        """发送企业微信通知

        Args:
            message: 通知消息
            config: 企业微信配置

        Returns:
            Dict: 发送结果
        """
        if not self.validate_config(config):
            return {"success": False, "error": "企业微信配置无效"}

        try:
            # 构建消息体
            if config.use_custom_format and config.message_format:
                # 使用自定义格式
                payload = self._apply_message_template(
                    config.message_format, message
                )
            else:
                # 使用默认格式
                payload = {
                    "msgtype": "text",
                    "text": {"content": f"{message.title}\n\n{message.content}"},
                }

            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    result = await response.json()

                    if result.get("errcode") == 0:
                        logger.info(f"企业微信发送成功: {message.title}")
                        return {"success": True, "response": result}
                    else:
                        error_msg = result.get("errmsg", "未知错误")
                        logger.error(f"企业微信发送失败: {error_msg}")
                        return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"企业微信发送失败: {e}")
            return {"success": False, "error": str(e)}

    def _apply_message_template(
        self, template: str, message: NotificationMessage
    ) -> Dict[str, Any]:
        """应用消息模板

        Args:
            template: 模板字符串(JSON格式)
            message: 消息对象

        Returns:
            Dict: 解析后的消息体
        """
        # 替换变量
        template = template.replace("${NOTIFIER_SUBJECT}", message.title)
        template = template.replace("${NOTIFIER_MESSAGE}", message.content)
        template = template.replace("${NOTIFIER_LEVEL}", message.level.value)
        template = template.replace("${NOTIFIER_CATEGORY}", message.category.value)
        template = template.replace(
            "${NOTIFIER_TIME}", message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        )

        try:
            return json.loads(template)
        except json.JSONDecodeError:
            # 如果模板不是有效的JSON,返回默认格式
            return {
                "msgtype": "text",
                "text": {"content": f"{message.title}\n\n{message.content}"},
            }


class FeishuChannel(BaseChannel):
    """飞书通知渠道"""

    def __init__(self):
        super().__init__(NotificationChannel.FEISHU)

    def validate_config(self, config: FeishuConfig) -> bool:
        """验证飞书配置"""
        if not config.webhook_url:
            logger.warning("飞书配置无效: Webhook地址为空")
            return False
        return True

    async def send(
        self, message: NotificationMessage, config: FeishuConfig
    ) -> Dict[str, Any]:
        """发送飞书通知

        Args:
            message: 通知消息
            config: 飞书配置

        Returns:
            Dict: 发送结果
        """
        if not self.validate_config(config):
            return {"success": False, "error": "飞书配置无效"}

        try:
            # 构建消息体
            if config.use_custom_format and config.message_format:
                # 使用自定义格式
                payload = self._apply_message_template(
                    config.message_format, message
                )
            else:
                # 使用默认格式
                payload = {
                    "msg_type": "text",
                    "content": {"text": f"{message.title}\n\n{message.content}"},
                }

            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    result = await response.json()

                    if result.get("code") == 0:
                        logger.info(f"飞书发送成功: {message.title}")
                        return {"success": True, "response": result}
                    else:
                        error_msg = result.get("msg", "未知错误")
                        logger.error(f"飞书发送失败: {error_msg}")
                        return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"飞书发送失败: {e}")
            return {"success": False, "error": str(e)}

    def _apply_message_template(
        self, template: str, message: NotificationMessage
    ) -> Dict[str, Any]:
        """应用消息模板

        Args:
            template: 模板字符串(JSON格式)
            message: 消息对象

        Returns:
            Dict: 解析后的消息体
        """
        # 替换变量
        template = template.replace("${NOTIFIER_SUBJECT}", message.title)
        template = template.replace("${NOTIFIER_MESSAGE}", message.content)
        template = template.replace("${NOTIFIER_LEVEL}", message.level.value)
        template = template.replace("${NOTIFIER_CATEGORY}", message.category.value)
        template = template.replace(
            "${NOTIFIER_TIME}", message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        )

        try:
            return json.loads(template)
        except json.JSONDecodeError:
            # 如果模板不是有效的JSON,返回默认格式
            return {
                "msg_type": "text",
                "content": {"text": f"{message.title}\n\n{message.content}"},
            }


class WebSocketChannel(BaseChannel):
    """WebSocket通知渠道"""

    def __init__(self):
        super().__init__(NotificationChannel.WEBSOCKET)
        self._manager = None

    def _get_manager(self):
        """获取WebSocket管理器(延迟导入避免循环依赖)"""
        if self._manager is None:
            from websocket.manager import manager
            self._manager = manager
        return self._manager

    def validate_config(self, config: WebSocketConfig) -> bool:
        """验证WebSocket配置"""
        return config.enabled

    async def send(
        self,
        message: NotificationMessage,
        config: WebSocketConfig,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送WebSocket通知

        Args:
            message: 通知消息
            config: WebSocket配置
            client_id: 指定客户端ID(可选)

        Returns:
            Dict: 发送结果
        """
        if not self.validate_config(config):
            return {"success": False, "error": "WebSocket通知未启用"}

        try:
            manager = self._get_manager()

            # 构建WebSocket消息
            ws_message = {
                "type": "notification",
                "id": message.id,
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": {
                    "title": message.title,
                    "content": message.content,
                    "level": message.level.value,
                    "category": message.category.value,
                    "metadata": message.metadata,
                    "created_at": message.created_at.isoformat(),
                },
            }

            # 确定主题
            topic = f"{config.topic_prefix}.{message.category.value}"

            # 发送消息
            if client_id:
                # 发送给指定客户端
                await manager.send_personal_message(ws_message, client_id)
                logger.info(f"WebSocket通知发送成功(指定客户端): {message.title}")
            elif config.broadcast_all:
                # 广播给所有订阅了该主题的客户端
                await manager.broadcast(ws_message, topic)
                logger.info(f"WebSocket通知广播成功: {message.title}")
            else:
                # 广播给所有客户端
                await manager.broadcast(ws_message, None)
                logger.info(f"WebSocket通知全局广播成功: {message.title}")

            return {"success": True, "response": "WebSocket消息已发送"}

        except Exception as e:
            logger.error(f"WebSocket通知发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def broadcast_to_topic(
        self, message: NotificationMessage, topic: str
    ) -> Dict[str, Any]:
        """广播到指定主题

        Args:
            message: 通知消息
            topic: 主题名称

        Returns:
            Dict: 发送结果
        """
        try:
            manager = self._get_manager()

            ws_message = {
                "type": "notification",
                "id": message.id,
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": {
                    "title": message.title,
                    "content": message.content,
                    "level": message.level.value,
                    "category": message.category.value,
                    "metadata": message.metadata,
                    "created_at": message.created_at.isoformat(),
                },
            }

            await manager.broadcast(ws_message, topic)
            logger.info(f"WebSocket通知主题广播成功: {topic}")
            return {"success": True, "response": f"已广播到主题: {topic}"}

        except Exception as e:
            logger.error(f"WebSocket主题广播失败: {e}")
            return {"success": False, "error": str(e)}
