"""因子特征构建 — 因子面板 → 逐品种、按 K 线原始时间戳索引的特征帧，供回测逐 bar 注入。

设计约束见 docs/superpowers/specs/2026-09-29-factor-backtest-integration-design.md：
- 特征帧索引统一归一为 datetime64[ns]（由落盘 timestamp 按量级自适应转换），
  与回测 K 线 _normalize_dataframe 后的 DatetimeIndex 同源对齐；
- 不做 merge/asof：因子值与 K 线同源 raw_map，行序天然一致；
- 截面 rank：1=当期因子值最高，并列同名次（method="min"），仅多品种时产出。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from factor.engine import (
    FactorExpressionError,
    _timestamps_to_datetime,
    evaluate_factor,
    load_raw_ohlcv,
)
from quality.parquet_provider import ParquetDataProvider
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


def build_feature_frames(
    factor_names: list[str],
    symbols: list[str],
    interval: str,
    candle_type: str,
    start: str | None,
    end: str | None,
    rank_factor: str | None = None,
    provider: ParquetDataProvider | None = None,
    custom_expressions: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    """构建逐品种特征帧。

    Args:
        factor_names: 因子库中的因子名（内置/自定义，必须全部可计算）
        symbols: 交易对列表
        interval/candle_type/start/end: 与回测 K 线同一取数口径
        rank_factor: 用于截面排名的因子；多品种时须在 factor_names 中
        provider/custom_expressions: 可注入，便于测试

    Returns:
        {symbol: DataFrame}，DataFrame 索引为该品种 K 线原始 timestamp 整数，
        列=因子名；多品种且 rank_factor 有效时追加 "cross_sectional_rank" 列。

    Raises:
        FactorExpressionError: 因子不存在/不支持/表达式非法，或 rank_factor 不在因子列表
    """
    if not factor_names:
        return {}
    custom_expressions = custom_expressions or {}
    if rank_factor is not None and rank_factor not in factor_names:
        # 排名因子缺失无法构造 cross_sectional_rank，直接失败而不是静默退化
        raise FactorExpressionError(f"截面排名因子 {rank_factor} 不在因子列表 {factor_names} 中")

    raw_map = load_raw_ohlcv(symbols, interval, candle_type, start, end, provider)

    # 逐品种逐因子求值；值顺序与 raw 行序一致（evaluate_factor 不重排）。
    # 帧索引统一归一为 datetime64[ns]：回测 K 线经 _normalize_dataframe 后也是
    # DatetimeIndex，BacktestLoop 据此做时间对齐；直接用原始整数在跨单位
    # （ns/us/ms）数据源间会错配。
    frames: dict[str, pd.DataFrame] = {}
    dt_by_symbol: dict[str, pd.DatetimeIndex] = {}
    for symbol, raw in raw_map.items():
        dt_index = _timestamps_to_datetime(raw["timestamp"])
        dt_by_symbol[symbol] = dt_index
        columns = {name: evaluate_factor(name, raw, custom_expressions).values for name in factor_names}
        frames[symbol] = pd.DataFrame(columns, index=dt_index)

    # 截面排名：宽表 datetime × symbol 上逐行 rank，再按各品种 datetime 索引写回
    if rank_factor is not None and len(raw_map) >= 2:
        wide = pd.DataFrame(
            {symbol: pd.Series(frames[symbol][rank_factor].values, index=dt_by_symbol[symbol]) for symbol in raw_map}
        )
        ranks = wide.rank(axis=1, ascending=False, method="min")
        for symbol in raw_map:
            frames[symbol]["cross_sectional_rank"] = ranks[symbol].reindex(dt_by_symbol[symbol]).values

    logger.info(
        f"因子特征帧构建完成: {len(factor_names)} 个因子 x {len(frames)} 个品种"
        + ("，含截面排名" if rank_factor and len(raw_map) >= 2 else "")
    )
    return frames


def attach_feature_frames(loaded_data: dict[str, Any], frames: dict[str, pd.DataFrame]) -> None:
    """把 {symbol: 特征帧} 回填到 EventDrivenBacktestService 的 loaded_data。

    loaded_data 的 key 形如 "BTCUSDT_1h"（symbol_timeframe），symbol 取最后一个
    下划线之前的部分（与 engine_service 的 key.rsplit("_", 1) 约定一致）。
    """
    for key, entry in loaded_data.items():
        symbol = key.rsplit("_", 1)[0]
        if symbol in frames:
            entry["feature_dataframe"] = frames[symbol]
