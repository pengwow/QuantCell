# 数据相关的Pydantic模型定义

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


class DataInfoResponse(BaseModel):
    """数据信息响应模型
    
    Attributes:
        qlib_dir: QLib数据目录
        data_loaded: 数据是否已加载
        calendars: 交易日历信息
        instruments: 成分股信息
        features: 特征信息
        total_instruments: 总成分股数量
        total_features: 总特征数量
    """
    qlib_dir: Optional[str] = Field(None, description="QLib数据目录")
    data_loaded: bool = Field(..., description="数据是否已加载")
    calendars: Dict[str, List[str]] = Field(default_factory=dict, description="交易日历信息")
    instruments: Dict[str, List[str]] = Field(default_factory=dict, description="成分股信息")
    features: Dict[str, List[str]] = Field(default_factory=dict, description="特征信息")
    total_instruments: int = Field(default=0, description="总成分股数量")
    total_features: int = Field(default=0, description="总特征数量")


class CalendarInfoResponse(BaseModel):
    """交易日历信息响应模型
    
    Attributes:
        freq: 频率
        dates: 日期列表
        count: 日期数量
    """
    freq: str = Field(..., description="频率")
    dates: List[str] = Field(default_factory=list, description="日期列表")
    count: int = Field(default=0, description="日期数量")


class InstrumentInfoResponse(BaseModel):
    """成分股信息响应模型
    
    Attributes:
        index_name: 指数名称
        symbols: 股票列表
        count: 股票数量
    """
    index_name: str = Field(..., description="指数名称")
    symbols: List[str] = Field(default_factory=list, description="股票列表")
    count: int = Field(default=0, description="股票数量")


class FeatureInfoResponse(BaseModel):
    """特征信息响应模型
    
    Attributes:
        symbol: 股票代码
        features: 特征列表
        count: 特征数量
    """
    symbol: str = Field(..., description="股票代码")
    features: List[str] = Field(default_factory=list, description="特征列表")
    count: int = Field(default=0, description="特征数量")


class LoadDataRequest(BaseModel):
    """加载数据请求模型
    
    空的请求模型，不需要任何参数
    """
    pass


class SymbolFeaturesResponse(BaseModel):
    """股票特征响应模型
    
    Attributes:
        symbol: 股票代码
        features: 特征列表
        count: 特征数量
    """
    symbol: str = Field(..., description="股票代码")
    features: List[str] = Field(default_factory=list, description="特征列表")
    count: int = Field(default=0, description="特征数量")


class DataResponse(BaseModel):
    """数据响应模型，用于返回具体的特征数据
    
    Attributes:
        symbol: 股票代码
        feature: 特征名称
        data: 特征数据，格式为{日期: 值}
        count: 数据数量
    """
    symbol: str = Field(..., description="股票代码")
    feature: str = Field(..., description="特征名称")
    data: Dict[str, float] = Field(default_factory=dict, description="特征数据，格式为{日期: 值}")
    count: int = Field(default=0, description="数据数量")


class DownloadCryptoRequest(BaseModel):
    """下载加密货币数据请求模型
    
    Attributes:
        symbols: 品种列表
        interval: 时间间隔列表
        start: 开始时间
        end: 结束时间
        exchange: 交易所
        max_workers: 最大工作线程数
        candle_type: 蜡烛图类型
        save_dir: 保存目录
        update_mode: bool = False,  # 更新模式，设置为true时只下载缺失的数据
    """
    symbols: List[str] = Field(..., description="品种列表")
    interval: List[str] = Field(..., description="时间间隔列表")
    start: Optional[str] = Field(None, description="开始时间")
    end: Optional[str] = Field(None, description="结束时间")
    exchange: str = Field(default="binance", description="交易所")
    max_workers: int = Field(default=1, description="最大工作线程数")
    candle_type: str = Field(default="spot", description="蜡烛图类型")
    save_dir: Optional[str] = Field(None, description="保存目录，如果不提供则从系统配置中读取data_download_dir")
    update_mode: bool = Field(default=False, description="更新模式，设置为true时只下载缺失的数据")


class TaskStatusResponse(BaseModel):
    """任务状态响应模型
    
    Attributes:
        task_id: 任务ID
        status: 任务状态（pending, running, completed, failed）
        progress: 任务进度百分比
        total: 总任务数
        completed: 已完成任务数
        failed: 失败任务数
        current: 当前处理的项目
        created_at: 任务创建时间
        updated_at: 任务更新时间
        error: 错误信息
    """
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态（pending, running, completed, failed）")
    progress: float = Field(..., description="任务进度百分比")
    total: int = Field(..., description="总任务数")
    completed: int = Field(..., description="已完成任务数")
    failed: int = Field(..., description="失败任务数")
    current: Optional[str] = Field(None, description="当前处理的项目")
    created_at: datetime = Field(..., description="任务创建时间")
    updated_at: datetime = Field(..., description="任务更新时间")
    error: Optional[str] = Field(None, description="错误信息")


class TaskProgressResponse(BaseModel):
    """任务进度响应模型
    
    Attributes:
        task_id: 任务ID
        progress: 任务进度百分比
        total: 总任务数
        completed: 已完成任务数
        failed: 失败任务数
        current: 当前处理的项目
    """
    task_id: str = Field(..., description="任务ID")
    progress: float = Field(..., description="任务进度百分比")
    total: int = Field(..., description="总任务数")
    completed: int = Field(..., description="已完成任务数")
    failed: int = Field(..., description="失败任务数")
    current: Optional[str] = Field(None, description="当前处理的项目")


class TaskResponse(BaseModel):
    """任务响应模型，用于返回任务创建结果
    
    Attributes:
        task_id: 任务ID
        status: 任务状态
        message: 任务创建消息
    """
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="任务创建消息")
