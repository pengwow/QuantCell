# -*- coding: utf-8 -*-
"""
axon_bridge: axon-quant 适配层

封装 axon-quant 库的核心 API，提供稳定的接口供业务代码使用。
所有与 axon-quant 的交互都通过此模块进行，避免在业务代码中直接依赖底层库。

主要功能:
- BacktestEngine 引擎创建和配置
- 交易品种创建（现货/合约）
- 订单构建（市价单/限价单）
- 事件构建和推送
- 结果提取和标准化

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


# ========== 延迟导入 axon_quant ==========
def _get_aq():
    """延迟导入 axon_quant 模块，避免启动时加载"""
    import axon_quant as aq
    return aq


# ========== 交易品种创建 ==========
def create_spot_instrument(base: str, quote: str) -> Dict[str, Any]:
    """
    创建现货交易品种

    Args:
        base: 基础货币代码 (如 "BTC")
        quote: 计价货币代码 (如 "USDT")

    Returns:
        Dict: 品种字典，包含 kind/base/quote 信息
    """
    aq = _get_aq()
    return aq.spot_instrument(base, quote)


def create_swap_instrument(
    base: str,
    quote: str,
    settle: str = "usd_margin",
    contract_size: float = 1.0,
) -> Dict[str, Any]:
    """
    创建永续合约交易品种（完全对应 axon-quant 0.11+ 新签名）

    Args:
        base: 基础币种(交易标的)，如 "BTC"
        quote: 计价币种，如 "USDT"
        settle: 结算方式 —— "usd_margin" (默认, U本位 USD 保证金)
                               或 "coin_margin" (币本位保证金)，大小写不敏感
        contract_size: 合约乘数，每张合约代表多少 base 币。
                       默认 1.0 即 1 张 = 1 BTC。
                       Binance BTCUSDT 永续默认 1，部分小币种合约 0.001 / 0.01 / 100 等。

    Returns:
        Dict: 品种字典，形如 {"kind": "swap", "base": "BTC", "quote": "USDT",
                             "settle": "usd_margin", "contract_size": 1.0, ...}
    """
    aq = _get_aq()
    return aq.swap_instrument(base, quote, settle=settle, contract_size=contract_size)


# ========== 订单创建 ==========
def create_market_order(
    symbol: str,
    side: str,
    quantity: float,
    order_id: int,
    instrument: Dict[str, Any],
) -> Dict[str, Any]:
    """
    创建市价订单字典

    Args:
        symbol: 交易对符号 (如 "BTCUSDT")
        side: 方向 ("Buy" / "Sell")
        quantity: 数量
        order_id: 订单 ID (整数)
        instrument: 品种字典

    Returns:
        Dict: 订单字典，包含所有必要字段
    """
    return {
        'id': order_id,
        'order_id': str(order_id),
        'symbol': symbol,
        'side': side,
        'type': 'market',
        'order_type': 'Market',
        'quantity': float(quantity),
        'price': 0.0,
        'tif': 'GTC',
        'status': 'New',
        'idempotency_key': f'order_{order_id:08d}',
        'instrument': instrument,
    }


def create_limit_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    order_id: int,
    instrument: Dict[str, Any],
    tif: str = 'GTC',
) -> Dict[str, Any]:
    """
    创建限价订单字典

    Args:
        symbol: 交易对符号
        side: 方向 ("Buy" / "Sell")
        quantity: 数量
        price: 限价
        order_id: 订单 ID (整数)
        instrument: 品种字典
        tif: 有效时间 ("GTC" / "IOC" / "FOK")

    Returns:
        Dict: 订单字典
    """
    return {
        'id': order_id,
        'order_id': str(order_id),
        'symbol': symbol,
        'side': side,
        'type': 'limit',
        'order_type': 'Limit',
        'quantity': float(quantity),
        'price': float(price),
        'tif': tif,
        'status': 'New',
        'idempotency_key': f'order_{order_id:08d}',
        'instrument': instrument,
    }


def create_cancel_order_event(
    order_id: int,
    instrument: Dict[str, Any],
    timestamp_ns: int,
) -> Dict[str, Any]:
    """
    创建取消订单事件字典

    Args:
        order_id: 订单 ID
        instrument: 品种字典
        timestamp_ns: 时间戳 (纳秒)

    Returns:
        Dict: 取消事件字典
    """
    return {
        'id': order_id,
        'type': 'order_cancelled',
        'timestamp_ns': timestamp_ns,
        'order': {
            'id': order_id,
            'order_id': str(order_id),
            'instrument': instrument,
        },
    }


# ========== 事件构建 ==========
def build_order_submitted_event(
    order_dict: Dict[str, Any],
    timestamp_ns: int,
) -> Dict[str, Any]:
    """
    构建订单提交事件

    Args:
        order_dict: 订单字典 (由 create_market_order / create_limit_order 创建)
        timestamp_ns: 时间戳 (纳秒)

    Returns:
        Dict: 事件字典，可直接用于 engine.push_event()
    """
    return {
        'id': order_dict['id'],
        'type': 'order_submitted',
        'timestamp_ns': timestamp_ns,
        'order': order_dict,
    }


# ========== BacktestEngine 配置 ==========
class EngineConfig:
    """
    回测引擎配置

    封装 BacktestEngine 的所有可配置项。

    Attributes:
        initial_cash: 初始资金
        half_spread: 种子流动性的半价差
        depth_levels: 种子流动性的深度层数
        size_per_level: 每层的订单大小
        auto_rebalance_threshold: 自动再平衡阈值
        funding_interval_ns: 资金费率结算间隔 (纳秒)
        funding_rate: 资金费率
    """

    def __init__(
        self,
        initial_cash: float = 100000.0,
        half_spread: float = 0.01,
        depth_levels: int = 5,
        size_per_level: float = 1.0,
        auto_rebalance_threshold: float = 0.01,
        funding_interval_ns: int = 8 * 3600 * 1_000_000_000,  # 8 小时
        funding_rate: float = 0.0001,
        mark_aware: bool = True,
    ):
        self.initial_cash = initial_cash
        self.half_spread = half_spread
        self.depth_levels = depth_levels
        self.size_per_level = size_per_level
        self.auto_rebalance_threshold = auto_rebalance_threshold
        self.funding_interval_ns = funding_interval_ns
        self.funding_rate = funding_rate
        self.mark_aware = mark_aware


# ========== 回测引擎工厂 ==========
def create_backtest_engine(config: Optional[EngineConfig] = None):
    """
    创建并配置回测引擎

    Args:
        config: 引擎配置，默认使用 EngineConfig 默认值

    Returns:
        BacktestEngine: 已配置的回测引擎实例
    """
    aq = _get_aq()
    cfg = config or EngineConfig()

    engine = aq.BacktestEngine(initial_cash=cfg.initial_cash)
    engine.with_seed_liquidity(
        half_spread=cfg.half_spread,
        depth_levels=cfg.depth_levels,
        size_per_level=cfg.size_per_level,
    )
    engine.with_auto_rebalance(threshold=cfg.auto_rebalance_threshold)

    return engine


def add_funding_schedule(
    engine,
    instrument: Dict[str, Any],
    interval_ns: int,
    fixed_rate: float,
    mark_aware: bool = True,
):
    """
    为引擎添加资金费率调度

    Args:
        engine: BacktestEngine 实例
        instrument: 品种字典
        interval_ns: 结算间隔 (纳秒)
        fixed_rate: 固定资金费率
        mark_aware: 是否使用标记感知
    """
    engine.with_funding_schedule(
        instrument=instrument,
        interval_ns=interval_ns,
        fixed_rate=fixed_rate,
        mark_aware=mark_aware,
    )


# ========== 结果提取 ==========
def extract_run_result(result: Any) -> Dict[str, Any]:
    """
    从 RunResult 提取回测结果

    Args:
        result: axon_quant.RunResult 实例 (由 engine.run() 返回)

    Returns:
        Dict: 标准化的结果字典
    """
    if result is None:
        return {}

    try:
        return {
            'final_nav': float(result.final_nav) if hasattr(result, 'final_nav') else 0.0,
            'nav_peak': float(result.nav_peak) if hasattr(result, 'nav_peak') else 0.0,
            'total_pnl': float(result.total_pnl) if hasattr(result, 'total_pnl') else 0.0,
            'total_fees': float(result.total_fees) if hasattr(result, 'total_fees') else 0.0,
            'total_funding_pnl': float(result.total_funding_pnl) if hasattr(result, 'total_funding_pnl') else 0.0,
            'trades': list(result.trades) if hasattr(result, 'trades') and result.trades else [],
            'positions': list(result.positions) if hasattr(result, 'positions') and result.positions else [],
            'equity_curve': list(result.equity_curve) if hasattr(result, 'equity_curve') and result.equity_curve else [],
            'events_processed': int(result.events_processed) if hasattr(result, 'events_processed') else 0,
            'fills': int(result.fills) if hasattr(result, 'fills') else 0,
            'orders_accepted': int(result.orders_accepted) if hasattr(result, 'orders_accepted') else 0,
            'orders_rejected': int(result.orders_rejected) if hasattr(result, 'orders_rejected') else 0,
            'sharpe_ratio': float(result.sharpe_ratio) if hasattr(result, 'sharpe_ratio') else 0.0,
            'max_drawdown_pct': float(result.max_drawdown_pct) if hasattr(result, 'max_drawdown_pct') else 0.0,
            'win_rate': float(result.win_rate) if hasattr(result, 'win_rate') else 0.0,
            'duration_secs': float(result.duration_secs) if hasattr(result, 'duration_secs') else 0.0,
        }
    except Exception as e:
        logger.error(f"提取回测结果失败: {e}")
        return {}


def extract_run_stats(stats: Any) -> Dict[str, Any]:
    """
    从 RunStats 提取统计信息

    Args:
        stats: axon_quant.RunStats 实例 (由 engine.step() 返回)

    Returns:
        Dict: 统计信息字典
    """
    if stats is None:
        return {}

    try:
        return {
            'events_processed': int(stats.events_processed) if hasattr(stats, 'events_processed') else 0,
            'fills': int(stats.fills) if hasattr(stats, 'fills') else 0,
            'orders_accepted': int(stats.orders_accepted) if hasattr(stats, 'orders_accepted') else 0,
            'orders_rejected': int(stats.orders_rejected) if hasattr(stats, 'orders_rejected') else 0,
            'orders_cancelled': int(stats.orders_cancelled) if hasattr(stats, 'orders_cancelled') else 0,
            'orders_modified': int(stats.orders_modified) if hasattr(stats, 'orders_modified') else 0,
            'pnl_peak': float(stats.pnl_peak) if hasattr(stats, 'pnl_peak') else 0.0,
            'total_pnl': float(stats.total_pnl) if hasattr(stats, 'total_pnl') else 0.0,
        }
    except Exception as e:
        logger.error(f"提取运行统计失败: {e}")
        return {}


# ========== 辅助函数 ==========
def to_ns_timestamp(ts: Any) -> int:
    """
    将时间戳转换为纳秒

    Args:
        ts: 时间戳，可以是 datetime、int、float 或字符串

    Returns:
        int: 纳秒时间戳
    """
    if isinstance(ts, (int, float)):
        if ts > 1e18:
            return int(ts)
        elif ts > 1e15:
            return int(ts * 1000)
        elif ts > 1e12:
            return int(ts * 1_000_000)
        elif ts > 1e9:
            return int(ts * 1_000_000_000)
        else:
            return int(ts * 1_000_000_000)
    elif hasattr(ts, 'timestamp'):
        return int(ts.timestamp() * 1_000_000_000)
    elif isinstance(ts, str):
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1_000_000_000)
        except (ValueError, TypeError):
            return 0
    return 0


def get_current_ns_timestamp() -> int:
    """获取当前时间的纳秒时间戳"""
    return int(time.time() * 1_000_000_000)


def get_instrument_id(instrument: Dict[str, Any]) -> str:
    """
    从品种字典获取标识符

    Args:
        instrument: 品种字典

    Returns:
        str: 品种标识符 (如 "BTCUSDT")
    """
    if isinstance(instrument, dict):
        base = instrument.get('base', '')
        quote = instrument.get('quote', '')
        if base and quote:
            return f"{base}{quote}"
        return str(instrument)
    return str(instrument)


# ========== 导出列表 ==========
__all__ = [
    'create_spot_instrument',
    'create_swap_instrument',
    'create_market_order',
    'create_limit_order',
    'create_cancel_order_event',
    'build_order_submitted_event',
    'create_backtest_engine',
    'add_funding_schedule',
    'EngineConfig',
    'extract_run_result',
    'extract_run_stats',
    'to_ns_timestamp',
    'get_current_ns_timestamp',
    'get_instrument_id',
]
