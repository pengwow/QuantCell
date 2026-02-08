"""
验证器集合
包含各种具体的验证器实现
"""

from ..core.registry import registry

# 导入收益率验证器
from .returns_validator import (
    TotalReturnValidator,
    AnnualizedReturnValidator,
    DailyReturnsValidator,
    CumulativeReturnsValidator,
)

# 导入信号验证器
from .signals_validator import (
    SignalCountValidator,
    SignalTimingValidator,
    SignalTypeValidator,
    SignalPriceValidator,
)

# 导入持仓验证器
from .positions_validator import (
    PositionQuantityValidator,
    PositionValueValidator,
    PositionChangeTimingValidator,
)

# 导入资金验证器
from .equity_validator import (
    EquityCurveValidator,
    DrawdownValidator,
    CashBalanceValidator,
)

# 导入交易验证器
from .trades_validator import (
    TradeCountValidator,
    TradePnLValidator,
    TradeFeeValidator,
    TradeTimingValidator,
)

# 导入指标验证器
from .metrics_validator import (
    SharpeRatioValidator,
    MaxDrawdownValidator,
    WinRateValidator,
    ProfitFactorValidator,
)

# 注册所有验证器
registry.register("total_return", TotalReturnValidator)
registry.register("annualized_return", AnnualizedReturnValidator)
registry.register("daily_returns", DailyReturnsValidator)
registry.register("cumulative_returns", CumulativeReturnsValidator)

registry.register("signal_count", SignalCountValidator)
registry.register("signal_timing", SignalTimingValidator)
registry.register("signal_type", SignalTypeValidator)
registry.register("signal_price", SignalPriceValidator)

registry.register("position_quantity", PositionQuantityValidator)
registry.register("position_value", PositionValueValidator)
registry.register("position_change_timing", PositionChangeTimingValidator)

registry.register("equity_curve", EquityCurveValidator)
registry.register("drawdown", DrawdownValidator)
registry.register("cash_balance", CashBalanceValidator)

registry.register("trade_count", TradeCountValidator)
registry.register("trade_pnl", TradePnLValidator)
registry.register("trade_fee", TradeFeeValidator)
registry.register("trade_timing", TradeTimingValidator)

registry.register("sharpe_ratio", SharpeRatioValidator)
registry.register("max_drawdown", MaxDrawdownValidator)
registry.register("win_rate", WinRateValidator)
registry.register("profit_factor", ProfitFactorValidator)

__all__ = [
    # 收益率验证器
    "TotalReturnValidator",
    "AnnualizedReturnValidator",
    "DailyReturnsValidator",
    "CumulativeReturnsValidator",
    # 信号验证器
    "SignalCountValidator",
    "SignalTimingValidator",
    "SignalTypeValidator",
    "SignalPriceValidator",
    # 持仓验证器
    "PositionQuantityValidator",
    "PositionValueValidator",
    "PositionChangeTimingValidator",
    # 资金验证器
    "EquityCurveValidator",
    "DrawdownValidator",
    "CashBalanceValidator",
    # 交易验证器
    "TradeCountValidator",
    "TradePnLValidator",
    "TradeFeeValidator",
    "TradeTimingValidator",
    # 指标验证器
    "SharpeRatioValidator",
    "MaxDrawdownValidator",
    "WinRateValidator",
    "ProfitFactorValidator",
]
