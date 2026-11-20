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

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

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
    # 逐行已读/处理标记（迁移 48 起生效；read_at IS NULL 即未读）
    # processed_at 语义仅任务类通知使用：单条已读的瞬间置一次，用于「已读即归档任务」
    read_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)


class NotificationState(TimezoneAwareBase):
    """收件箱全局状态（恒定单行，id=1）"""

    __tablename__ = "notification_state"

    id = Column(Integer, primary_key=True)
    # 全部已读时刻可见的最大通知 id；无行/None 视为全部未读
    last_read_id = Column(Integer)


# 「异步任务域」五类：与 inbox.py 的已读即归档、task_notices.py 的任务通知接线共用
TASK_TYPES = (
    "rl_train",
    "factor_job",
    "collector_task",
    "backtest",
    "research",
)


class AsyncTaskRecord(TimezoneAwareBase):
    """异步任务终态影子表（补偿扫描数据源）

    五个异步任务域注册时写 queued、开工翻 running、终态 upsert 终态值。
    服务重启后 compensate_interrupted_tasks() 据此把残留 queued/running 的行
    判定为「重启前被中断」。collector/backtest/research 自身有任务表，不写这里
    （补偿直接扫原表）；仅 rl_train/factor_job 两域以本表为补偿依据。
    """

    __tablename__ = "async_task_records"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    task_type = Column(String(32), nullable=False, index=True)  # TASK_TYPES 之一
    # 各域自己的 task_id（uuid），跨域不加唯一（域内唯一即可，域内以 (task_type, task_id) 定位）
    task_id = Column(String(64), nullable=False, index=True, unique=True)
    # queued / running / succeeded / failed / cancelled
    status = Column(String(32), nullable=False)
    name = Column(String(200), nullable=False, default="")
    extra = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    # TimezoneAwareBase 无自动时间列，显式声明（aware 值经 __setattr__ 统一转 UTC）
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
