# Pydantic模型定义，用于数据处理API的请求和响应

from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, Field

# 导入统一的ApiResponse模型
from common.schemas import ApiResponse

if TYPE_CHECKING:
    from datetime import datetime


class DataDownloadRequest(BaseModel):
    """数据下载请求模型

    Attributes:
        exchange: 交易所名称，目前支持'binance'
        save_dir: 数据保存目录，可选
        start: 开始时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        end: 结束时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
        interval: 时间间隔，如'1m', '5m', '15m', '30m', '1h', '4h', '1d'等
        max_workers: 最大工作线程数，默认1
        max_collector_count: 最大收集次数，默认2
        delay: 请求延迟时间（秒），默认0
        candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权），默认'spot'
        symbols: 交易对列表，如['BTCUSDT', 'ETHUSDT']，如果为None则获取全量交易对
        convert_to_qlib: 是否将数据转换为QLib格式，默认False
        qlib_dir: QLib数据保存目录，如果为None则自动生成
        data_write_to_db: 是否将数据写入数据库，如为None则从配置获取默认值
    """

    exchange: str = Field(
        default="binance",
        description="交易所名称，目前支持'binance'",
        json_schema_extra={"example": "binance"},
    )
    save_dir: str | None = Field(
        None,
        description="数据保存目录，可选",
        json_schema_extra={"example": "/data/crypto"},
    )
    start: str | None = Field(
        None,
        description="开始时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'",
        json_schema_extra={"example": "2023-01-01"},
    )
    end: str | None = Field(
        None,
        description="结束时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'",
        json_schema_extra={"example": "2023-12-31"},
    )
    interval: str = Field(
        default="1d",
        description="时间间隔，如'1m', '5m', '15m', '30m', '1h', '4h', '1d'等",
        json_schema_extra={"example": "1h"},
    )
    max_workers: int = Field(default=1, description="最大工作线程数，默认1", json_schema_extra={"example": 4})
    max_collector_count: int = Field(default=2, description="最大收集次数，默认2", json_schema_extra={"example": 3})
    delay: float = Field(
        default=0.0,
        description="请求延迟时间（秒），默认0",
        json_schema_extra={"example": 0.5},
    )
    candle_type: str = Field(
        default="spot",
        description="蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权），默认'spot'",
        json_schema_extra={"example": "spot"},
    )
    symbols: list[str] | None = Field(
        None,
        description="交易对列表，如['BTCUSDT', 'ETHUSDT']，如果为None则获取全量交易对",
        json_schema_extra={"example": ["BTCUSDT", "ETHUSDT"]},
    )
    convert_to_qlib: bool = Field(
        default=False,
        description="是否将数据转换为QLib格式，默认False",
        json_schema_extra={"example": False},
    )
    qlib_dir: str | None = Field(
        None,
        description="QLib数据保存目录，如果为None则自动生成",
        json_schema_extra={"example": "/data/qlib"},
    )
    data_write_to_db: bool | None = Field(
        default=None,
        description="是否将数据写入数据库，如为None则从配置获取默认值",
        json_schema_extra={"example": True},
    )


class ScheduledTaskCreate(BaseModel):
    """定时任务创建请求模型

    Attributes:
        name: 任务名称
        description: 任务描述
        task_type: 任务类型，如download_crypto
        cron_expression: CRON表达式
        interval: 时间间隔，如1h, 1d, 1w
        start_time: 开始执行时间
        end_time: 结束执行时间
        frequency_type: 频率类型：hourly, daily, weekly, monthly, cron, interval, date
        symbols: 交易对列表
        exchange: 交易所
        candle_type: 蜡烛图类型
        save_dir: 保存目录
        max_workers: 最大工作线程数
        incremental_enabled: 是否启用增量采集
        notification_enabled: 是否启用通知
        notification_type: 通知类型
        notification_email: 通知邮箱
        notification_webhook: 通知Webhook
    """

    name: str = Field(..., description="任务名称")
    description: str | None = Field(None, description="任务描述")
    task_type: str = Field(default="download_crypto", description="任务类型")
    cron_expression: str | None = Field(None, description="CRON表达式")
    interval: str | None = Field(None, description="时间间隔，如1h, 1d, 1w")
    start_time: datetime | None = Field(None, description="开始执行时间")
    end_time: datetime | None = Field(None, description="结束执行时间")
    frequency_type: str = Field(
        ...,
        description="频率类型：hourly, daily, weekly, monthly, cron, interval, date",
    )
    symbols: list[str] | None = Field(None, description="交易对列表")
    exchange: str | None = Field(None, description="交易所")
    candle_type: str = Field(default="spot", description="蜡烛图类型")
    save_dir: str | None = Field(None, description="保存目录")
    max_workers: int = Field(default=1, description="最大工作线程数")
    incremental_enabled: bool = Field(default=True, description="是否启用增量采集")
    notification_enabled: bool = Field(default=False, description="是否启用通知")
    notification_type: str | None = Field(None, description="通知类型")
    notification_email: str | None = Field(None, description="通知邮箱")
    notification_webhook: str | None = Field(None, description="通知Webhook")


class ScheduledTaskUpdate(BaseModel):
    """定时任务更新请求模型

    Attributes:
        name: 任务名称
        description: 任务描述
        status: 任务状态，如pending, running, completed, failed, paused
        cron_expression: CRON表达式
        interval: 时间间隔，如1h, 1d, 1w
        start_time: 开始执行时间
        end_time: 结束执行时间
        frequency_type: 频率类型：hourly, daily, weekly, monthly, cron, interval, date
        symbols: 交易对列表
        exchange: 交易所
        candle_type: 蜡烛图类型
        save_dir: 保存目录
        max_workers: 最大工作线程数
        incremental_enabled: 是否启用增量采集
        notification_enabled: 是否启用通知
        notification_type: 通知类型
        notification_email: 通知邮箱
        notification_webhook: 通知Webhook
    """

    name: str | None = Field(None, description="任务名称")
    description: str | None = Field(None, description="任务描述")
    status: str | None = Field(None, description="任务状态")
    cron_expression: str | None = Field(None, description="CRON表达式")
    interval: str | None = Field(None, description="时间间隔，如1h, 1d, 1w")
    start_time: datetime | None = Field(None, description="开始执行时间")
    end_time: datetime | None = Field(None, description="结束执行时间")
    frequency_type: str | None = Field(
        None,
        description="频率类型：hourly, daily, weekly, monthly, cron, interval, date",
    )
    symbols: list[str] | None = Field(None, description="交易对列表")
    exchange: str | None = Field(None, description="交易所")
    candle_type: str | None = Field(None, description="蜡烛图类型")
    save_dir: str | None = Field(None, description="保存目录")
    max_workers: int | None = Field(None, description="最大工作线程数")
    incremental_enabled: bool | None = Field(None, description="是否启用增量采集")
    notification_enabled: bool | None = Field(None, description="是否启用通知")
    notification_type: str | None = Field(None, description="通知类型")
    notification_email: str | None = Field(None, description="通知邮箱")
    notification_webhook: str | None = Field(None, description="通知Webhook")
