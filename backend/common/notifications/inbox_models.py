"""站内收件箱数据模型

统一通知服务（common/notifications/service.py::send_notification）在投递前落库一条，
配合 WebSocket 渠道实现前端铃铛/收件箱的可见性：
- notifications: 通知流水表
- notification_state: 全局已读水位单行表（单管理员自部署场景，无 user_id 隔离）

未读判定 = id > last_read_id（id 自增单调，水位记录"全部已读"时刻可见的最大通知 id）。
不用时间戳水位的原因：SQLite CURRENT_TIMESTAMP 只有秒精度，落库后立刻点已读会把
同秒落库的新通知误判为已读；id 水位严格无此问题。
"""

from datetime import UTC, datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from collector.db.models import TimezoneAwareBase


class InboxNotification(TimezoneAwareBase):
    """站内通知流水"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    title = Column(String(200), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    # 级别/来源直接存 NotificationLevel / NotificationCategory 的枚举字符串；
    # 未知值由前端按 info 样式兜底显示
    level = Column(String(20), nullable=False, default="info")
    source = Column(String(30), nullable=False, default="system")
    # 应用时钟 UTC 写入（TimezoneAwareBase.__setattr__ 把 aware 值统一转 UTC 存储）
    created_at = Column(DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC))


class NotificationState(TimezoneAwareBase):
    """收件箱全局状态（恒定单行，id=1）"""

    __tablename__ = "notification_state"

    id = Column(Integer, primary_key=True)
    # 全部已读时刻可见的最大通知 id；无行/None 视为全部未读
    last_read_id = Column(Integer)
