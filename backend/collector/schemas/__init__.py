# Pydantic模型定义，用于数据处理API的请求和响应

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """API响应统一模型
    
    Attributes:
        code: 响应状态码，0表示成功，非0表示失败
        message: 响应消息，描述操作结果
        data: 响应数据，可选
        timestamp: 响应时间戳
    """
    code: int = Field(..., description="响应状态码，0表示成功，非0表示失败")
    message: str = Field(..., description="响应消息，描述操作结果")
    data: Optional[dict | list] = Field(None, description="响应数据，可选")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间戳")


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
    exchange: str = Field(default="binance", description="交易所名称，目前支持'binance'")
    save_dir: Optional[str] = Field(None, description="数据保存目录，可选")
    start: Optional[str] = Field(None, description="开始时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'")
    end: Optional[str] = Field(None, description="结束时间，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'")
    interval: str = Field(default="1d", description="时间间隔，如'1m', '5m', '15m', '30m', '1h', '4h', '1d'等")
    max_workers: int = Field(default=1, description="最大工作线程数，默认1")
    max_collector_count: int = Field(default=2, description="最大收集次数，默认2")
    delay: float = Field(default=0.0, description="请求延迟时间（秒），默认0")
    candle_type: str = Field(default="spot", description="蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权），默认'spot'")
    symbols: Optional[List[str]] = Field(None, description="交易对列表，如['BTCUSDT', 'ETHUSDT']，如果为None则获取全量交易对")
    convert_to_qlib: bool = Field(default=False, description="是否将数据转换为QLib格式，默认False")
    qlib_dir: Optional[str] = Field(None, description="QLib数据保存目录，如果为None则自动生成")
    data_write_to_db: Optional[bool] = Field(default=True, description="是否将数据写入数据库，如为None则从配置获取默认值")


class DataConvertRequest(BaseModel):
    """数据转换请求模型
    
    Attributes:
        csv_dir: CSV数据目录
        qlib_dir: QLib数据保存目录
        freq: 交易频率，如"day"、"1min"等
        date_field_name: CSV中的日期字段名称
        file_suffix: CSV文件后缀
        symbol_field_name: CSV中的交易对字段名称
        include_fields: 要转换的字段列表，逗号分隔
        max_workers: 最大工作线程数
        limit_nums: 限制转换的文件数量，用于调试
    """
    csv_dir: str = Field(..., description="CSV数据目录")
    qlib_dir: str = Field(..., description="QLib数据保存目录")
    freq: str = Field(default="day", description="交易频率，如'day'、'1min'等")
    date_field_name: str = Field(default="date", description="CSV中的日期字段名称")
    file_suffix: str = Field(default=".csv", description="CSV文件后缀")
    symbol_field_name: str = Field(default="symbol", description="CSV中的交易对字段名称")
    include_fields: str = Field(default="date,open,high,low,close,volume", description="要转换的字段列表，逗号分隔")
    max_workers: int = Field(default=16, description="最大工作线程数")
    limit_nums: Optional[int] = Field(None, description="限制转换的文件数量，用于调试")


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
    description: Optional[str] = Field(None, description="任务描述")
    task_type: str = Field(default="download_crypto", description="任务类型")
    cron_expression: Optional[str] = Field(None, description="CRON表达式")
    interval: Optional[str] = Field(None, description="时间间隔，如1h, 1d, 1w")
    start_time: Optional[datetime] = Field(None, description="开始执行时间")
    end_time: Optional[datetime] = Field(None, description="结束执行时间")
    frequency_type: str = Field(..., description="频率类型：hourly, daily, weekly, monthly, cron, interval, date")
    symbols: Optional[List[str]] = Field(None, description="交易对列表")
    exchange: Optional[str] = Field(None, description="交易所")
    candle_type: str = Field(default="spot", description="蜡烛图类型")
    save_dir: Optional[str] = Field(None, description="保存目录")
    max_workers: int = Field(default=1, description="最大工作线程数")
    incremental_enabled: bool = Field(default=True, description="是否启用增量采集")
    notification_enabled: bool = Field(default=False, description="是否启用通知")
    notification_type: Optional[str] = Field(None, description="通知类型")
    notification_email: Optional[str] = Field(None, description="通知邮箱")
    notification_webhook: Optional[str] = Field(None, description="通知Webhook")


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
    name: Optional[str] = Field(None, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    status: Optional[str] = Field(None, description="任务状态")
    cron_expression: Optional[str] = Field(None, description="CRON表达式")
    interval: Optional[str] = Field(None, description="时间间隔，如1h, 1d, 1w")
    start_time: Optional[datetime] = Field(None, description="开始执行时间")
    end_time: Optional[datetime] = Field(None, description="结束执行时间")
    frequency_type: Optional[str] = Field(None, description="频率类型：hourly, daily, weekly, monthly, cron, interval, date")
    symbols: Optional[List[str]] = Field(None, description="交易对列表")
    exchange: Optional[str] = Field(None, description="交易所")
    candle_type: Optional[str] = Field(None, description="蜡烛图类型")
    save_dir: Optional[str] = Field(None, description="保存目录")
    max_workers: Optional[int] = Field(None, description="最大工作线程数")
    incremental_enabled: Optional[bool] = Field(None, description="是否启用增量采集")
    notification_enabled: Optional[bool] = Field(None, description="是否启用通知")
    notification_type: Optional[str] = Field(None, description="通知类型")
    notification_email: Optional[str] = Field(None, description="通知邮箱")
    notification_webhook: Optional[str] = Field(None, description="通知Webhook")
