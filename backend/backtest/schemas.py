# 回测服务API数据模型

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """
    API响应通用模型
    """
    code: int = Field(..., description="响应码，0表示成功，非0表示失败")
    message: str = Field(..., description="响应消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="响应数据")


class BacktestListRequest(BaseModel):
    """
    获取回测列表请求模型
    """
    pass


class BacktestRunRequest(BaseModel):
    """
    执行回测请求模型
    """
    strategy_config: Dict[str, Any] = Field(..., description="策略配置")
    backtest_config: Dict[str, Any] = Field(..., description="回测配置")


class BacktestAnalyzeRequest(BaseModel):
    """
    分析回测结果请求模型
    """
    backtest_id: str = Field(..., description="回测ID")


class BacktestDeleteRequest(BaseModel):
    """
    删除回测结果请求模型
    """
    backtest_id: str = Field(..., description="回测ID")


class StrategyUploadRequest(BaseModel):
    """
    上传策略文件请求模型
    """
    strategy_name: str = Field(..., description="策略名称")
    file_content: str = Field(..., description="策略文件内容")


class StrategyConfigRequest(BaseModel):
    """
    创建策略配置请求模型
    """
    strategy_name: str = Field(..., description="策略名称")
    params: Dict[str, Any] = Field(..., description="策略参数")


class BacktestReplayRequest(BaseModel):
    """
    获取回放数据请求模型
    """
    backtest_id: str = Field(..., description="回测ID")


class MetricItem(BaseModel):
    """
    回测指标项模型
    """
    name: str = Field(..., description="指标名称")
    value: Any = Field(..., description="指标值")
    cn_name: str = Field(..., description="中文名称")
    en_name: str = Field(..., description="英文名称")
    description: str = Field(..., description="指标描述")


class TradeItem(BaseModel):
    """
    交易记录项模型
    """
    EntryTime: str = Field(..., description="入场时间")
    ExitTime: str = Field(..., description="出场时间")
    Duration: str = Field(..., description="持仓时间")
    Direction: str = Field(..., description="交易方向")
    EntryPrice: float = Field(..., description="入场价格")
    ExitPrice: float = Field(..., description="出场价格")
    Size: float = Field(..., description="仓位大小")
    PnL: float = Field(..., description="盈亏金额")
    ReturnPct: float = Field(..., description="收益率")
    Tag: Optional[str] = Field(None, description="标签")


class EquityPoint(BaseModel):
    """
    资金曲线点模型
    """
    datetime: str = Field(..., description="时间")
    Equity: float = Field(..., description="权益")
    Drawdown: float = Field(..., description="回撤")


class KlineItem(BaseModel):
    """
    K线数据项模型
    """
    time: str = Field(..., description="时间")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")


class TradeSignal(BaseModel):
    """
    交易信号模型
    """
    time: str = Field(..., description="时间")
    type: str = Field(..., description="信号类型")
    price: float = Field(..., description="价格")
    size: float = Field(..., description="大小")
    trade_id: str = Field(..., description="交易ID")


class ReplayData(BaseModel):
    """
    回放数据模型
    """
    kline_data: List[KlineItem] = Field(..., description="K线数据")
    trade_signals: List[TradeSignal] = Field(..., description="交易信号")
    equity_data: List[EquityPoint] = Field(..., description="资金曲线数据")


class BacktestResult(BaseModel):
    """
    回测结果响应模型
    """
    task_id: str = Field(..., description="回测任务ID")
    status: str = Field(..., description="回测状态")
    message: str = Field(..., description="回测消息")
    strategy_name: str = Field(..., description="策略名称")
    backtest_config: Dict[str, Any] = Field(..., description="回测配置")
    metrics: List[MetricItem] = Field(..., description="回测指标")
    trades: List[TradeItem] = Field(..., description="交易记录")
    equity_curve: List[EquityPoint] = Field(..., description="资金曲线")
    strategy_data: List[Dict[str, Any]] = Field(..., description="策略数据")


class BacktestListItem(BaseModel):
    """
    回测列表项模型
    """
    id: str = Field(..., description="回测ID")
    strategy_name: str = Field(..., description="策略名称")
    created_at: str = Field(..., description="创建时间")
    status: str = Field(..., description="回测状态")


class StrategyConfig(BaseModel):
    """
    策略配置模型
    """
    strategy_name: str = Field(..., description="策略名称")
    params: Dict[str, Any] = Field(..., description="策略参数")


class BacktestConfig(BaseModel):
    """
    回测配置模型
    """
    symbol: str = Field(default="BTCUSDT", description="交易对")
    interval: str = Field(default="1d", description="时间周期")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(..., description="结束时间")
    initial_cash: float = Field(default=10000.0, description="初始资金")
    commission: float = Field(default=0.001, description="手续费率")
    exclusive_orders: bool = Field(default=True, description="是否排他订单")
