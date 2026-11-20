"""任务终态通知 Hub（spec §5）：五个异步任务域统一出口

任务模块只在「状态机终态翻转处」调用本模块，职责集中在这里：
1. upsert_async_task_record：写/翻 async_task_records 影子行
   （rl_train/factor_job 两域服务重启后补偿扫描的数据源；其余三域有自己的任务表）
2. notify_task_event：终态通知统一入口（仅接受 SUCCEEDED/FAILED/INTERRUPTED）
   - record_inbox_notification 落站内收件箱（source=task_type，前端过滤键）
   - 实时推送：协程上下文内调用走当前 running loop；工作线程调用走
     lifespan 绑定的主 loop（bind_event_loop）；两处都没有（独立脚本/回测
     进程）时静默跳过，只保留收件箱
   - FAILED/INTERRUPTED 追加企业微信/飞书外发（未配置渠道在渠道层自动失败，无害）

线程安全：公开函数均为同步函数、可在任意线程调用；收件箱与影子表各自
开会话落库，不跨线程共享 session；投递失败不影响收件箱落库结果。
本模块自包含：不 import 任何任务域模块，依赖方向是任务域 → 本 Hub 单向。
"""

import asyncio
import threading
import typing

from sqlalchemy import select

from common.notifications.models import (
    NotificationCategory,
    NotificationChannel,
    NotificationLevel,
    NotificationMessage,
)
from utils.db_session import use_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

TASK_STATUS_SUCCEEDED = "SUCCEEDED"
TASK_STATUS_FAILED = "FAILED"
TASK_STATUS_INTERRUPTED = "INTERRUPTED"
_TASK_STATUSES = (TASK_STATUS_SUCCEEDED, TASK_STATUS_FAILED, TASK_STATUS_INTERRUPTED)

# 终态 → (收件箱 level, 影子行 status)
_NOTIFICATION_TO_SHADOW = {
    TASK_STATUS_SUCCEEDED: (NotificationLevel.SUCCESS, "succeeded"),
    TASK_STATUS_FAILED: (NotificationLevel.ERROR, "failed"),
    TASK_STATUS_INTERRUPTED: (NotificationLevel.WARNING, "interrupted"),
}

_TASK_TYPE_LABELS = {
    "rl_train": "RL训练",
    "factor_job": "因子计算",
    "collector_task": "数据采集",
    "backtest": "回测",
    "research": "深度研究",
}

_STATUS_LABELS = {
    TASK_STATUS_SUCCEEDED: "已完成",
    TASK_STATUS_FAILED: "失败",
    TASK_STATUS_INTERRUPTED: "已中断",
}

# 影子表只服务这两个域：collector/backtest/research 有自己的任务表，
# 补偿扫描（任务 6）直接扫原表；这里写影子行反而制造双份事实源
_SHADOWED_TASK_TYPES = frozenset({"rl_train", "factor_job"})

_SUCCESS_CHANNELS: list[NotificationChannel] = [NotificationChannel.WEBSOCKET]
_FAILURE_CHANNELS: list[NotificationChannel] = [
    NotificationChannel.WEBSOCKET,
    NotificationChannel.WECOM,
    NotificationChannel.FEISHU,
]

# lifespan 启动时绑定，供工作线程投递实时消息/外发渠道
_bound_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def bind_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _bound_loop
    with _loop_lock:
        _bound_loop = loop


def upsert_async_task_record(
    task_type: str,
    task_id: str,
    status: str,
    *,
    name: str | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """写/翻影子行（注册态 queued/running 与终态翻转共用；失败仅记日志不阻塞主链路）"""
    try:
        # 函数内 import 原因：inbox_models 依赖 collector.db.models 的基类，顶层导入会触发
        # collector 包 __init__ 拉起 routes/task_manager，而 collector 侧任务管理器又顶层导入
        # 本模块，形成 common.notifications ↔ collector 的包初始化循环； collector 侧的
        # task_manager 自 2026-11-20 起也走本 Hub，运行期各模块均加载完毕，此处延迟导入无环。
        from common.notifications.inbox_models import AsyncTaskRecord

        with use_db_session() as db:
            row = (
                db.execute(
                    select(AsyncTaskRecord).where(
                        AsyncTaskRecord.task_type == task_type,
                        AsyncTaskRecord.task_id == task_id,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if row is None:
                row = AsyncTaskRecord(task_type=task_type, task_id=task_id, status=status)
                db.add(row)
            row.status = status
            if name is not None:
                row.name = name
            if error is not None:
                row.error = error
            if extra is not None:
                row.extra = extra
            db.commit()
    except Exception as e:  # 影子表缺失只影响补偿扫描，不允许拖垮任务本身
        logger.error(f"影子行 upsert 失败 task={task_type}/{task_id}: {e}")


def notify_task_event(
    task_type: str,
    task_id: str,
    status: str,
    *,
    name: str | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """任务终态统一通知入口（同步、线程安全）。

    仅接受终态三值；queued/running 作为非终态由埋点直接调
    upsert_async_task_record，不发通知。
    """
    if status not in _TASK_STATUSES:
        raise ValueError(f"任务通知仅支持终态 {_TASK_STATUSES}，收到 {status!r}")

    # 函数内 import 原因同 upsert_async_task_record：打破 common.notifications ↔ collector 包初始化环
    from common.notifications.inbox import record_inbox_notification

    label = _TASK_TYPE_LABELS.get(task_type, task_type)
    level, shadow_status = _NOTIFICATION_TO_SHADOW[status]

    if task_type in _SHADOWED_TASK_TYPES:
        upsert_async_task_record(task_type, task_id, shadow_status, name=name, error=error, extra=extra)

    display_name = name or task_id
    content = display_name
    if error:
        # 错误详情截断 500 字，防 IM/收件箱被长栈刷屏
        content = f"{display_name}\n{error[:500]}"
    title = f"{label}任务{_STATUS_LABELS[status]}"

    record_inbox_notification(title=title, content=content, level=level.value, source=task_type)

    message = NotificationMessage(
        title=title,
        content=content,
        level=level,
        category=NotificationCategory.TASK,
        metadata={
            "task_type": task_type,
            "task_id": task_id,
            "task_status": status,
            "name": name or "",
        },
    )
    _dispatch(message, _SUCCESS_CHANNELS if status == TASK_STATUS_SUCCEEDED else _FAILURE_CHANNELS)


def _dispatch(message: NotificationMessage, channels: list[NotificationChannel]) -> None:
    """实时投递调度：协程上下文走当前 loop；工作线程走绑定的主 loop；都没有则跳过"""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        running.create_task(_deliver(message, channels))
    elif _bound_loop is not None and _bound_loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(_deliver(message, channels), _bound_loop)
        fut.add_done_callback(_log_delivery_failure)


def _log_delivery_failure(fut: typing.Any) -> None:
    try:
        fut.result()
    except Exception as e:
        logger.error(f"任务通知实时投递失败(不影响收件箱): {e}")


async def _deliver(message: NotificationMessage, channels: list[NotificationChannel]) -> None:
    # service.py 反向 import 本模块链路会绕回 routes，顶层引入有循环依赖风险，延迟到调用时
    from common.notifications.service import notification_service

    try:
        await notification_service.send(message, channels=channels)
    except Exception as e:
        logger.error(f"任务通知渠道投递失败(不影响收件箱): {e}")
