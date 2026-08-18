from typing import TYPE_CHECKING

from utils.logger import LogType, get_logger

from . import crud

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__, LogType.APPLICATION)


# 时间窗口 → 大致天数（用于 trade_history_chart 的 days 参数）
_WINDOW_TO_DAYS = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "all": 365,
}


def _window_to_days(window: str) -> int:
    """将窗口字符串映射为天数；非法值默认 30"""
    return _WINDOW_TO_DAYS.get(window, 30)


def _compute_max_drawdown(cumulative_pnl: list) -> float:
    """根据累计收益曲线计算最大回撤（百分比，正数）

    最大回撤 = max(peak - trough) / peak * 100
    """
    if not cumulative_pnl or len(cumulative_pnl) < 2:
        return 0.0

    max_dd = 0.0
    peak = cumulative_pnl[0]
    for value in cumulative_pnl:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / abs(peak) * 100
            if drawdown > max_dd:
                max_dd = drawdown
    return max_dd


def _compute_sharpe_ratio(daily_pnl: list, risk_free_rate: float = 0.0) -> float:
    """根据每日盈亏计算年化 Sharpe Ratio（简化版）

    公式：sqrt(252) * (mean(daily_pnl) - rf) / std(daily_pnl)
    """
    if not daily_pnl or len(daily_pnl) < 2:
        return 0.0

    import math

    n = len(daily_pnl)
    mean = sum(daily_pnl) / n
    variance = sum((x - mean) ** 2 for x in daily_pnl) / n
    std = math.sqrt(variance)

    if std == 0:
        return 0.0

    return math.sqrt(252) * (mean - risk_free_rate) / std


class TradingStatsService:
    def __init__(self, db: Session):
        self.db = db

    def get_trading_summary(self, worker_id: int, window: str | None = "30d") -> dict:
        """获取交易汇总，支持时间窗口过滤"""
        from .routes import _resolve_window

        start_time = _resolve_window(window or "30d")
        return crud.get_trading_summary(self.db, worker_id, start_time=start_time)

    def get_overview(self, worker_id: int, window: str | None = "30d") -> dict:
        """获取总览（Overview）数据：聚合指标 + 累计收益曲线 + 盈亏分布

        一次性返回前端总览 tab 所需的全部数据，避免多次轮询。
        """
        from .routes import _resolve_window
        from .schemas import OverviewMetrics

        start_time = _resolve_window(window or "30d")
        window_key = window or "30d"

        # 1. 汇总指标（含 max_drawdown / sharpe_ratio 扩展计算）
        summary = crud.get_trading_summary(self.db, worker_id, start_time=start_time)

        # 计算净收益（实现已实现盈亏口径 = total_pnl）
        net_profit = summary.get("total_pnl", 0.0)

        # max_drawdown / sharpe_ratio 从累计收益曲线反推
        history = self.get_trade_history_chart(worker_id, days=_window_to_days(window_key))
        max_drawdown = _compute_max_drawdown(history.get("cumulative_pnl", []))
        sharpe_ratio = _compute_sharpe_ratio(history.get("daily_pnl", []))

        # 收益率近似 = total_pnl / max(abs(initial_cash), 1)，保留 0.0 占位
        return_rate = 0.0

        metrics = OverviewMetrics(
            total_pnl=summary.get("total_pnl", 0.0),
            total_profit=summary.get("total_profit", 0.0),
            total_loss=summary.get("total_loss", 0.0),
            net_profit=net_profit,
            return_rate=return_rate,
            total_trades=summary.get("total_trades", 0),
            winning_trades=summary.get("winning_trades", 0),
            losing_trades=summary.get("losing_trades", 0),
            win_rate=summary.get("win_rate", 0.0),
            profit_factor=summary.get("profit_factor", 0.0),
            profit_loss_ratio=summary.get("profit_factor", 0.0),
            average_profit=summary.get("average_profit", 0.0),
            average_loss=summary.get("average_loss", 0.0),
            largest_profit=summary.get("largest_profit", 0.0),
            largest_loss=summary.get("largest_loss", 0.0),
            max_drawdown=round(max_drawdown, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            total_volume=summary.get("total_volume", 0.0),
            total_fees=summary.get("total_fees", 0.0),
            trading_days=summary.get("trading_days", 0),
            daily_average_trades=summary.get("daily_average_trades", 0.0),
            window=window_key,
        )

        # 2. 盈亏分布
        pnl_distribution = self.get_pnl_distribution(worker_id)

        return {
            "metrics": metrics.model_dump(),
            "cumulative_pnl_series": history,
            "pnl_distribution": pnl_distribution,
            "window": window_key,
        }

    def get_position_summary(self, worker_id: int) -> dict:
        from .models import WorkerPosition

        positions = (
            self.db.query(WorkerPosition)
            .filter(WorkerPosition.worker_id == worker_id, WorkerPosition.status == "OPEN")
            .all()
        )

        total_positions = len(positions)
        long_positions = sum(1 for p in positions if p.side == "LONG")
        short_positions = sum(1 for p in positions if p.side == "SHORT")
        total_value = sum(p.quantity * (p.current_price or p.entry_price or 0) for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl or 0 for p in positions)
        total_margin_used = sum(p.margin_used or 0 for p in positions)

        return {
            "total_positions": total_positions,
            "long_positions": long_positions,
            "short_positions": short_positions,
            "total_value": round(total_value, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_margin_used": round(total_margin_used, 2),
            "positions": [p.to_dict() for p in positions],
        }

    def get_pnl_distribution(self, worker_id: int) -> dict:
        return crud.get_pnl_distribution(self.db, worker_id)

    def get_trade_history_chart(self, worker_id: int, days: int = 30) -> dict:
        return crud.get_trade_history_chart(self.db, worker_id, days)
