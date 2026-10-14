"""
回测引擎服务模块（基于 axon_quant 体系）

封装事件驱动回测引擎的初始化、数据加载、策略加载和执行流程。
将原本分散在 cli.py 和 service.py 中的引擎操作逻辑统一到此模块。

所有与 axon-quant 的交互都通过 axon_bridge 适配层进行。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

# 逐品种进度回调：参数为 (已完成品种数, 品种总数, 当前开始回测的品种)
# ponytail: 粒度只到品种级，单品种回测在引擎执行期间没有中间进度（需 Rust 引擎支持 bar 级回调）
SymbolProgressCallback = Callable[[int, int, str], None]


def _get_axon_bridge():
    """延迟导入 axon_bridge"""
    import axon_bridge

    return axon_bridge


class EventDrivenBacktestService:
    """
    事件驱动回测引擎服务（基于 axond 体系）

    封装事件驱动引擎的完整生命周期管理：
    1. 数据加载（通过 BacktestDataProvider）
    2. 引擎初始化（BacktestEngine）
    3. 数据转换并加载到引擎
    4. 策略加载和实例化
    5. 回测执行
    6. 结果格式化

    使用示例：
        from backtest.data_provider import BacktestDataProvider
        from backtest.engine_service import EventDrivenBacktestService

        provider = BacktestDataProvider()
        service = EventDrivenBacktestService(provider)

        results = service.run_backtest(
            strategy_name="sma_crossover",
            strategy_params={"fast_period": 10},
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            engine_config={"initial_capital": 100000}
        )
    """

    def __init__(self, data_provider):
        """
        初始化引擎服务

        Args:
            data_provider: BacktestDataProvider 实例
        """
        self.provider = data_provider

    def run_backtest(
        self,
        strategy_name: str,
        strategy_params: dict[str, Any],
        symbols: list[str],
        timeframes: list[str],
        engine_config: dict | None = None,
        show_progress: bool = False,
        data_type: str = "kline",
        market: str = "spot",
        factor_names: list[str] | None = None,
        on_symbol_progress: SymbolProgressCallback | None = None,
    ) -> dict:
        """
        执行完整的事件驱动回测流程

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_config: 引擎配置（可选），支持 trading_mode: "spot"/"futures"
            show_progress: 是否显示进度
            data_type: 数据类型 (kline/aggTrades/fundingRate/bookDepth 等)
            market: 市场类型 (spot/um/cm)
            factor_names: 参与回测的因子名称列表（可选）
            on_symbol_progress: 逐品种进度回调，每个品种开跑前以
                (已完成品种数, 品种总数, 当前品种) 触发（可选）

        Returns:
            dict: 格式化的回测结果
        """
        logger.info(
            f"[EventDrivenBacktestService] 开始执行回测: {strategy_name}, data_type={data_type}, market={market}"
        )

        # 解析默认配置
        init_cash = (engine_config or {}).get("initial_capital", 10000)
        base_currency = (engine_config or {}).get("base_currency", "USDT")
        leverage = (engine_config or {}).get("leverage", 1.0)
        time_range = (engine_config or {}).get("time_range")
        # 交易模式: spot(现货) / futures(永续合约)
        trading_mode = (engine_config or {}).get("trading_mode", "spot")
        candle_type = "future" if trading_mode == "futures" else "spot"

        # 1. 加载数据
        if data_type == "kline":
            # K线数据：使用原有加载逻辑
            data_dict, _ = self.provider.load_multiple(
                symbols=symbols,
                timeframes=timeframes,
                candle_type=candle_type,
                time_range=time_range,
                auto_download=False,
                show_progress=show_progress,
            )
            # 转换为统一格式
            loaded_data: dict[str, Any] = {}
            for key, df in data_dict.items():
                loaded_data[key] = {
                    "data": df,
                    "features": None,
                    "feature_dataframe": None,
                    "data_type": "kline",
                }
        else:
            # 非K线数据：通过适配器加载
            adapter_dict, _ = self.provider.load_multiple_data(
                symbols=symbols,
                timeframes=timeframes,
                data_type=data_type,
                market=market,
                time_range=time_range,
                show_progress=show_progress,
            )
            loaded_data: dict[str, Any] = {}
            for key, result in adapter_dict.items():
                loaded_data[key] = {
                    "data": result.data,
                    "features": result.metadata.get("features_dict"),
                    "feature_dataframe": result.features,
                    "data_type": data_type,
                }

        if not loaded_data:
            msg = "没有成功加载任何数据，回测无法继续"
            raise ValueError(msg)

        # 因子特征帧：回测后用于详情页因子分析（时序、归因、交易时点因子值）
        feature_frames: dict[str, pd.DataFrame] | None = None

        # 因子特征：用因子库预计算逐品种特征帧并回填，BacktestLoop 逐 bar 注入
        if factor_names and data_type == "kline":
            from factor.features import attach_feature_frames, build_feature_frames

            f_start = f_end = None
            if time_range:
                try:
                    from utils.validation import parse_time_range

                    f_start_dt, f_end_dt = parse_time_range(time_range)
                    f_start = f_start_dt.strftime("%Y-%m-%d")
                    f_end = f_end_dt.strftime("%Y-%m-%d")
                except Exception as e:
                    logger.warning(f"因子取数时间范围解析失败，改用全量数据: {e}")

            rank_factor = (strategy_params or {}).get("factor_name") or factor_names[0]
            frames = build_feature_frames(
                factor_names=factor_names,
                symbols=symbols,
                interval=timeframes[0],
                candle_type=candle_type,
                start=f_start,
                end=f_end,
                rank_factor=rank_factor if len(symbols) >= 2 else None,
            )
            feature_frames = frames
            attach_feature_frames(loaded_data, frames)

        # 2. 加载策略（先判断策略基类，决定走共享引擎还是逐品种独立回测）
        from backtest.strategy_loader_service import StrategyLoaderService

        instrument_ids = [{"symbol": s, "venue": "BINANCE"} for s in symbols for _ in timeframes]
        bar_types = list(timeframes) * len(symbols)

        strategy = StrategyLoaderService.load_strategy(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            instrument_ids=instrument_ids,
            bar_types=bar_types,
        )

        if strategy is None:
            msg = f"无法加载策略: {strategy_name}"
            raise ValueError(msg)

        from strategy.base import BaseStrategy

        is_event_driven = not isinstance(strategy, BaseStrategy)

        # 多品种结果占位（单品种路径不赋值，保持 None）
        per_symbol_results: dict[str, dict[str, Any]] | None = None

        # Rust RunResult.trades 不携带 instrument 信息，事件驱动策略在单次组合
        # 回测后无法按品种拆分成交；多品种时改为逐品种独立回测（各自独立账户、
        # 相同初始资金）再聚合，与 BaseStrategy 多品种路径语义一致
        if is_event_driven and len(symbols) > 1:
            raw_results, per_symbol_results = self._run_event_driven_per_symbol(
                engine_config=engine_config,
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                symbols=symbols,
                timeframes=timeframes,
                data_dict=data_dict,
                init_cash=init_cash,
                base_currency=base_currency,
                leverage=leverage,
                trading_mode=trading_mode,
                time_range=time_range,
                on_symbol_progress=on_symbol_progress,
            )
        else:
            # 3. 初始化引擎
            engine = self._initialize_engine(
                engine_config=engine_config,
                strategy_name=strategy_name,
                init_cash=init_cash,
                data_dict=data_dict,
            )

            # 3.1 加载数据到引擎
            _instruments, bar_types, cleaned_data = self._load_data_to_engine(
                engine=engine,
                data_dict=data_dict,
                symbols=symbols,
                timeframes=timeframes,
                base_currency=base_currency,
                leverage=leverage,
                init_cash=init_cash,
                trading_mode=trading_mode,
                time_range=time_range,
            )

            # 4. 执行回测 —— 按策略基类选执行引擎
            #    BaseStrategy 模板 → BacktestLoop（支持 ctx 注入 features/funding/account）
            #    EventDrivenStrategy 旧版 → EventDrivenBacktestEngine（add_strategy + run_backtest）
            if is_event_driven:
                # —— EventDrivenStrategy 单品种路径 ——
                # 数据和 instrument 已在 _load_data_to_engine 注入引擎，
                # 这里只需 add_strategy + run_backtest()
                if on_symbol_progress:
                    on_symbol_progress(0, 1, symbols[0])
                engine.add_strategy(strategy)
                result_dict = engine.run_backtest()  # dict: {trades, positions, equity_curve, account, metrics}
                # 转成统一 dict 格式供 ResultFormatterService.format_axon_results 消费
                raw_results = self._event_engine_result_to_dict(result_dict, symbols)
                # 清洗后的 K 线写入结果，供回放页 kline_data 使用（只进结果 JSON，不入 DB）
                tf0 = timeframes[0] if timeframes else "1h"
                kline_df = cleaned_data.get(f"{symbols[0]}_{tf0}")
                if kline_df is not None:
                    raw_results["klines"] = self._build_kline_records(kline_df, engine_config, time_range)
                per_symbol_results = {}
            else:
                # —— BaseStrategy 路径 —— 用 BacktestLoop
                from backtest.backtest_loop import BacktestLoop

                loop = BacktestLoop(initial_cash=init_cash)
                force_liquidate = (engine_config or {}).get("force_liquidate", False)

                if len(symbols) == 1:
                    first_key = next(iter(loaded_data.keys()))
                    entry = loaded_data[first_key]
                    df = entry["data"]
                    parts = first_key.rsplit("_", 1)
                    symbol = parts[0] if len(parts) > 1 else first_key
                    if on_symbol_progress:
                        on_symbol_progress(0, 1, symbol)
                    result = loop.run(
                        strategy=strategy,
                        data=df,
                        symbol=symbol,
                        force_liquidate=force_liquidate,
                        features=entry.get("features"),
                        feature_dataframe=entry.get("feature_dataframe"),
                        data_type=entry.get("data_type", "kline"),
                    )
                    raw_results = self._convert_backtest_result(result)
                else:
                    aggregated_metrics: dict[str, Any] = {}
                    per_symbol_results = {}
                    loaded_entries = list(loaded_data.items())
                    for idx, (key, entry) in enumerate(loaded_entries):
                        df = entry["data"]
                        parts = key.rsplit("_", 1)
                        sym = parts[0] if len(parts) > 1 else key
                        if on_symbol_progress:
                            on_symbol_progress(idx, len(loaded_entries), sym)
                        loop_result = loop.run(
                            strategy=strategy,
                            data=df,
                            symbol=sym,
                            force_liquidate=force_liquidate,
                            features=entry.get("features"),
                            feature_dataframe=entry.get("feature_dataframe"),
                            data_type=entry.get("data_type", "kline"),
                        )
                        result = self._convert_backtest_result(loop_result)
                        per_symbol_results[sym] = result
                        self._accumulate_symbol_metrics(result, aggregated_metrics)
                    raw_results = aggregated_metrics

        # 4.5 构建因子分析载荷（仅当配置了 factor_names 且特征帧可用时）
        if factor_names and feature_frames:
            factors_payload = self._build_factors_payload(
                feature_frames=feature_frames,
                loaded_data=loaded_data,
                raw_results=raw_results,
                per_symbol_results=per_symbol_results,
                factor_names=factor_names,
                strategy_params=strategy_params or {},
                symbols=symbols,
            )
            if len(symbols) == 1:
                raw_results["factors"] = factors_payload.get(symbols[0], {})
            elif per_symbol_results:
                for sym in symbols:
                    if sym in per_symbol_results and sym in factors_payload:
                        per_symbol_results[sym]["factors"] = factors_payload[sym]

        # 5. 格式化结果
        if len(symbols) == 1:
            # axon 引擎结果格式（final_nav/total_pnl/...）,
            # 与 event 格式（metrics/trades/...）不同,必须用 format_axon_results
            # 否则 metrics 字段全部为 0
            from backtest.result_formatter_service import ResultFormatterService

            formatted_results = ResultFormatterService.format_axon_results(
                results=raw_results,
                symbol=symbols[0],
                timeframe=timeframes[0] if timeframes else "1h",
                strategy_name=strategy_name,
            )
        else:
            # 多品种结果汇总（多品种路径下 per_symbol_results 必为 dict）
            formatted_results = self._format_results(
                results=raw_results,
                symbols=symbols,
                timeframe=timeframes[0] if timeframes else "15m",
                strategy_name=strategy_name,
                per_symbol_results=per_symbol_results or {},
            )

        logger.info("[EventDrivenBacktestService] 回测完成")

        return formatted_results

    def _run_event_driven_per_symbol(
        self,
        *,
        engine_config: dict | None,
        strategy_name: str,
        strategy_params: dict[str, Any] | None,
        symbols: list[str],
        timeframes: list[str],
        data_dict: dict[str, pd.DataFrame],
        init_cash: float,
        base_currency: str,
        leverage: float,
        trading_mode: str,
        time_range: str | None,
        on_symbol_progress: SymbolProgressCallback | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """事件驱动策略多品种：逐品种独立回测后聚合。

        Rust RunResult.trades 不携带 instrument，无法在单次组合回测后按品种
        拆分成交，因此每个品种用独立引擎/账户和全新策略实例（on_bar 策略有
        内部 K 线缓存）各跑一遍，初始资金相同，最后聚合，口径与 BaseStrategy
        多品种路径一致。

        Returns:
            (aggregated_metrics, per_symbol_results)
        """
        from backtest.strategy_loader_service import StrategyLoaderService

        tf = timeframes[0] if timeframes else "1h"
        per_symbol_results: dict[str, dict[str, Any]] = {}

        for idx, symbol in enumerate(symbols):
            key = f"{symbol}_{tf}"
            sym_df = data_dict.get(key)
            if sym_df is None:
                logger.warning(f"跳过 {key}，数据未加载")
                continue

            # 每个品种开跑前通知外部（已完成 idx 个，共 len(symbols) 个）
            if on_symbol_progress:
                on_symbol_progress(idx, len(symbols), symbol)
            # 每个品种一个全新引擎（独立账户）
            sym_engine = self._initialize_engine(
                engine_config=engine_config,
                strategy_name=strategy_name,
                init_cash=init_cash,
                data_dict={key: sym_df},
            )
            _, _, sym_cleaned = self._load_data_to_engine(
                engine=sym_engine,
                data_dict={key: sym_df},
                symbols=[symbol],
                timeframes=[tf],
                base_currency=base_currency,
                leverage=leverage,
                init_cash=init_cash,
                trading_mode=trading_mode,
                time_range=time_range,
            )

            # 全新策略实例，避免上个品种的 on_bar 内部状态串到下个品种
            sym_strategy = StrategyLoaderService.load_strategy(
                strategy_name=strategy_name,
                strategy_params=strategy_params or {},
                instrument_ids=[{"symbol": symbol, "venue": "BINANCE"}],
                bar_types=[tf],
            )
            if sym_strategy is None:
                msg = f"无法加载策略: {strategy_name}"
                raise ValueError(msg)

            sym_engine.add_strategy(sym_strategy)
            sym_result = self._event_engine_result_to_dict(sym_engine.run_backtest(), [symbol])

            kline_df = sym_cleaned.get(key)
            if kline_df is not None:
                sym_result["klines"] = self._build_kline_records(kline_df, engine_config, time_range)

            per_symbol_results[symbol] = sym_result

        if not per_symbol_results:
            msg = "没有任何品种成功完成回测"
            raise ValueError(msg)

        aggregated: dict[str, Any] = {}
        for sym_result in per_symbol_results.values():
            self._accumulate_symbol_metrics(sym_result, aggregated)
        return aggregated, per_symbol_results

    def _build_kline_records(
        self,
        kline_df: pd.DataFrame,
        engine_config: dict | None,
        time_range: str | None,
    ) -> list[dict[str, Any]]:
        """清洗后 K 线按回测区间裁剪并转 records（回放页 kline_data）。

        区间解析兼容 time_range 字符串和 start_time/end_time 两种 config 风格；
        裁剪结果为空（时区/格式异常）时回退全量。
        """
        k_start = k_end = None
        try:
            from utils.validation import parse_time_range

            if time_range:
                k_start, k_end = parse_time_range(time_range)
            else:
                s = (engine_config or {}).get("start_time")
                e = (engine_config or {}).get("end_time")
                if s and e:
                    k_start, k_end = s, e
        except Exception as e2:
            logger.warning(f"回放 K 线区间解析失败，使用全量数据: {e2}")

        if k_start and k_end:
            # df.index 是 UTC tz-aware，naive 端点需先 localize，否则比较报 TypeError
            k0, k1 = pd.Timestamp(k_start), pd.Timestamp(k_end)
            k0 = k0.tz_localize("UTC") if k0.tz is None else k0.tz_convert("UTC")
            k1 = k1.tz_localize("UTC") if k1.tz is None else k1.tz_convert("UTC")
            clipped = kline_df.loc[(kline_df.index >= k0) & (kline_df.index <= k1)]
            # 比较结果为空（时区/格式异常），回退全量
            kline_df = clipped if not clipped.empty else kline_df

        return self._klines_to_records(kline_df)

    @staticmethod
    def _accumulate_symbol_metrics(result: dict[str, Any], aggregated: dict[str, Any]) -> None:
        """把单品种结果的标量指标累加进聚合 dict（原地修改）。

        累加类求和，起止时间分别取 min/max；trades/positions 等嵌套字段跳过。
        """
        sum_keys = {
            "total_pnl",
            "orders_accepted",
            "orders_rejected",
            "fills",
            "total_orders",
            "total_fees",
            "events_processed",
            "duration_secs",
            "trade_count",
            "bar_count",
        }
        min_keys = {"data_start_ns"}
        max_keys = {"data_end_ns"}

        for k, v in result.items():
            if not isinstance(v, (int, float)):
                continue
            if k in sum_keys:
                aggregated[k] = aggregated.get(k, 0) + v
            elif k in min_keys:
                cur = aggregated.get(k)
                aggregated[k] = v if cur is None else min(cur, v)
            elif k in max_keys:
                cur = aggregated.get(k)
                aggregated[k] = v if cur is None else max(cur, v)

    def _build_factors_payload(
        self,
        feature_frames: dict[str, pd.DataFrame],
        loaded_data: dict[str, Any],
        raw_results: dict[str, Any],
        per_symbol_results: dict[str, dict[str, Any]] | None,
        factor_names: list[str],
        strategy_params: dict[str, Any],
        symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        """从特征帧构建因子分析载荷（列式时序 + 交易时点因子值 + 归因）。

        返回 {symbol: {names, thresholds, time_series, trade_factors, attribution}}。
        任一环节失败时该 symbol 条目为 {}，不阻断回测主流程。
        """
        from factor.attribution import compute_factor_attribution

        payload: dict[str, dict[str, Any]] = {}

        for key, entry in loaded_data.items():
            parts = key.rsplit("_", 1)
            symbol = parts[0] if len(parts) > 1 else key
            feat_df = entry.get("feature_dataframe")
            if feat_df is None or feat_df.empty:
                continue

            try:
                # ① 列式紧凑时序：共享 timestamps + 每因子一列值
                idx = feat_df.index
                ts_ms = (pd.to_datetime(idx, utc=True).tz_convert("UTC").asi8 // 1_000_000).tolist()
                formatted = pd.to_datetime(idx, utc=True).strftime("%Y-%m-%d %H:%M:%S").tolist()

                time_series: dict[str, Any] = {
                    "timestamps": ts_ms,
                    "formatted_times": formatted,
                }
                for col in feat_df.columns:
                    time_series[col] = [None if pd.isna(v) else float(v) for v in feat_df[col]]

                # ② 交易时点因子值：按 trade timestamp 在特征帧中 lookup
                # 单品种用 raw_results.trades；多品种用 per_symbol_results[symbol].trades
                if len(symbols) == 1 or not per_symbol_results:
                    trades = raw_results.get("trades", [])
                else:
                    trades = per_symbol_results.get(symbol, {}).get("trades", [])
                trade_factors = self._trade_factors_lookup(feat_df, trades)

                # ③ 归因：取该品种的收盘价计算 forward returns
                closes = self._extract_closes(entry.get("data"), idx)
                attribution = compute_factor_attribution(feat_df, closes) if closes is not None else {}

                payload[symbol] = {
                    "names": list(feat_df.columns),
                    "thresholds": self._extract_thresholds(strategy_params),
                    "time_series": time_series,
                    "trade_factors": trade_factors,
                    "attribution": attribution,
                }
            except Exception as e:
                logger.warning(f"品种 {symbol} 因子载荷构建失败: {e}")
                payload[symbol] = {}

        return payload

    @staticmethod
    def _trade_factors_lookup(feat_df: pd.DataFrame, trades: list[dict]) -> list[dict[str, Any]]:
        """按每笔 trade 的 timestamp 在特征帧中查找最接近的 bar 的因子值。"""
        if not trades:
            return []

        # 特征帧索引转毫秒，用于快速查找
        idx_ms = pd.to_datetime(feat_df.index, utc=True).tz_convert("UTC").asi8 // 1_000_000
        result: list[dict[str, Any]] = []
        for trade in trades:
            ts = trade.get("timestamp")
            if ts is None:
                result.append({})
                continue
            # 后端 trade timestamp 可能是秒级或毫秒级，统一转毫秒
            ts_ms = int(ts) if int(ts) > 10_000_000_000 else int(ts) * 1000
            # 找 <= ts_ms 的最大索引位置
            pos = int(idx_ms.searchsorted(ts_ms, side="right")) - 1
            if pos < 0 or pos >= len(idx_ms):
                result.append({})
                continue
            row = feat_df.iloc[pos]
            entry: dict[str, Any] = {
                "timestamp": int(idx_ms[pos]),
                "formatted_time": pd.to_datetime(feat_df.index[pos], utc=True).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for col in feat_df.columns:
                v = row[col]
                entry[col] = None if pd.isna(v) else float(v)
            result.append(entry)
        return result

    @staticmethod
    def _extract_closes(data: Any, idx: pd.Index) -> pd.Series | None:
        """从 loaded_data 的 data（DataFrame）中提取收盘价序列，对齐到 feat_df 索引。

        特征帧索引是 naive datetime64[ns]（factor.engine._timestamps_to_datetime），
        K 线数据索引是 UTC tz-aware DatetimeIndex，必须统一时区再求交集，
        否则 intersection 为空导致归因无法计算。
        """
        if data is None or not isinstance(data, pd.DataFrame) or "close" not in data.columns:
            return None
        try:
            closes = data["close"].copy()
            # 统一到 UTC tz-aware
            if closes.index.tz is None:
                closes.index = closes.index.tz_localize("UTC")
            else:
                closes.index = closes.index.tz_convert("UTC")
            feat_idx = pd.DatetimeIndex(idx)
            if feat_idx.tz is None:
                feat_idx = feat_idx.tz_localize("UTC")
            else:
                feat_idx = feat_idx.tz_convert("UTC")
            common = closes.index.intersection(feat_idx)
            if len(common) < 2:
                return None
            return closes.loc[common]
        except Exception:
            return None

    @staticmethod
    def _extract_thresholds(strategy_params: dict[str, Any]) -> dict[str, dict[str, float]]:
        """从策略参数提取因子阈值（buy_threshold/sell_threshold）。"""
        factor_name = strategy_params.get("factor_name")
        if not factor_name:
            return {}
        thresholds: dict[str, dict[str, float]] = {}
        entry: dict[str, float] = {}
        if "buy_threshold" in strategy_params:
            entry["buy"] = float(strategy_params["buy_threshold"])
        if "sell_threshold" in strategy_params:
            entry["sell"] = float(strategy_params["sell_threshold"])
        if entry:
            thresholds[factor_name] = entry
        return thresholds

    def _convert_backtest_result(self, result) -> dict:
        """将 BacktestResult 对象转换为字典格式（兼容原有 API）"""
        return {
            "initial_capital": result.final_nav - result.total_pnl,
            "final_nav": result.final_nav,
            "total_pnl": result.total_pnl,
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "nav_peak": result.nav_peak,
            "orders_accepted": result.orders_accepted,
            "orders_rejected": result.orders_rejected,
            "fills": result.fills,
            "total_orders": result.total_orders,
            "events_processed": result.events_processed,
            "duration_secs": result.duration_secs,
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_fees": result.total_fees,
            "trade_count": len(result.trade_records),
            "trades": list(result.trade_records),
            "equity_curve": list(result.equity_curve),
            "data_start_ns": result.data_start_ns,
            "data_end_ns": result.data_end_ns,
            "bar_count": result.bar_count,
        }

    @staticmethod
    def _klines_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
        """清洗后的 K 线 DataFrame → JSON 友好的 list[dict]（回放页 kline_data）

        klinecharts 要求毫秒时间戳，同时附 formatted_time 便于排障。
        """
        import json as _json

        out = df.reset_index()
        out.columns = [str(c).lower() for c in out.columns]
        time_col = "timestamp" if "timestamp" in out.columns else out.columns[0]
        ts = pd.to_datetime(out[time_col], utc=True)
        # klinecharts 要求毫秒；先统一到 ms 精度再取整数值，
        # 避免 astype("int64") 直接取原 dtype(usize/ns/s) 单位漂移
        out[time_col] = ts.dt.as_unit("ms").astype("int64").tolist()
        out["formatted_time"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
        # to_dict 后 ndarray 不利于 JSON 序列化，先转 records 再 round-trip 保证纯 JSON 类型
        return _json.loads(out.to_json(orient="records", date_format="iso"))

    @staticmethod
    def _event_engine_result_to_dict(result_dict: dict, symbols: list[str]) -> dict[str, Any]:
        """把 EventDrivenBacktestEngine.run_backtest() 的嵌套结果拍平成 BacktestLoop 风格

        run_backtest 返回 {account, metrics, trades, equity_curve, positions} 嵌套结构；
        BacktestResult 风格是扁平 {final_nav, total_pnl, max_drawdown, ...}。
        ResultFormatterService.format_axon_results 吃后者。
        """
        account = result_dict.get("account", {}) or {}
        metrics = result_dict.get("metrics", {}) or {}

        # metrics 里已带 final_nav / total_pnl 等核心字段，优先用它们；
        # 缺失时回退 account 子字段
        final_nav = metrics.get("final_nav") or account.get("final_balance") or 0.0
        nav_peak = metrics.get("nav_peak") or account.get("peak_equity") or 0.0
        total_pnl = metrics.get("total_pnl", 0.0)
        total_fees = metrics.get("total_fees", 0.0)

        return {
            "initial_capital": (nav_peak or final_nav) - total_pnl,
            "final_nav": final_nav,
            "total_pnl": total_pnl,
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
            "nav_peak": nav_peak,
            "orders_accepted": metrics.get("orders_accepted", 0),
            "orders_rejected": metrics.get("orders_rejected", 0),
            "fills": metrics.get("fills", 0),
            "total_orders": metrics.get("total_orders", 0),
            "events_processed": metrics.get("events_processed", 0),
            "duration_secs": metrics.get("duration_secs", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "total_fees": total_fees,
            "trade_count": len(result_dict.get("trades", [])),
            "trades": list(result_dict.get("trades", [])),
            "positions": list(result_dict.get("positions", [])),
            "equity_curve": list(result_dict.get("equity_curve", [])),
            "data_start_ns": metrics.get("data_start_ns"),
            "data_end_ns": metrics.get("data_end_ns"),
            "bar_count": metrics.get("bar_count", 0),
        }

    def _initialize_engine(
        self,
        engine_config: dict | None,
        strategy_name: str,
        init_cash: float,
        data_dict: dict[str, pd.DataFrame],
    ):
        """
        初始化回测循环（直接使用 BacktestLoop，不再通过中间包装层）

        Args:
            engine_config: 引擎配置字典
            strategy_name: 策略名称
            init_cash: 初始资金
            data_dict: 品种 -> K线 DataFrame，用于无 time_range 时推导回测时间范围

        Returns:
            BacktestLoop: 已初始化的回测循环实例
        """
        try:
            from backtest.engines.event_engine import EventDrivenBacktestEngine

            config = engine_config or {}
            time_range = config.get("time_range")

            # 解析时间范围
            if time_range:
                from utils.validation import parse_time_range

                start_dt, end_dt = parse_time_range(time_range)
                start_date = start_dt.strftime("%Y-%m-%d") if start_dt else "2023-01-01"
                end_date = end_dt.strftime("%Y-%m-%d") if end_dt else "2023-12-31"
            else:
                first_key = next(iter(data_dict.keys()))
                first_df = data_dict[first_key]
                if len(first_df) > 0:
                    first_idx = first_df.index[0]
                    last_idx = first_df.index[-1]
                    start_date = str(first_idx)[:10] if first_idx is not None else "2023-01-01"
                    end_date = str(last_idx)[:10] if last_idx is not None else "2023-12-31"
                else:
                    start_date = "2023-01-01"
                    end_date = "2023-12-31"

            full_config = {
                "trader_id": f"BACKTEST-{strategy_name.upper()}",
                "log_level": config.get("log_level", "INFO"),
                "initial_capital": init_cash,
                "start_date": start_date,
                "end_date": end_date,
            }

            engine = EventDrivenBacktestEngine(full_config)
            engine.initialize()

            logger.info("[EventDrivenBacktestService] 引擎初始化完成")
            return engine

        except Exception as e:
            logger.error(f"[EventDrivenBacktestService] 引擎初始化失败: {e}")
            raise

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str]:
        """
        解析交易对符号，提取基础货币和计价货币

        Args:
            symbol: 交易对符号（如 "BTCUSDT", "BTC/USDT", "BTC-USDT"）

        Returns:
            tuple: (base, quote) 如 ("BTC", "USDT")
        """
        for sep in ["/", "-", "_"]:
            if sep in symbol:
                parts = symbol.split(sep)
                return parts[0].upper(), parts[1].upper()
        if len(symbol) > 3:
            return symbol[:3].upper(), symbol[3:].upper()
        # 短符号(如 "ETH")直接视为 base,quote 兜底 USDT;
        # 不能返回嵌套 tuple,否则 base, quote = ... 解包时 quote 是 tuple
        return symbol.upper(), "USDT"

    def _load_data_to_engine(
        self,
        engine,
        data_dict: dict[str, pd.DataFrame],
        symbols: list[str],
        timeframes: list[str],
        base_currency: str,
        leverage: float,
        init_cash: float,
        trading_mode: str = "spot",
        time_range: str | None = None,
    ):
        """
        加载数据到引擎并创建交易品种

        根据 trading_mode 使用 axon_bridge 创建现货或永续合约品种，
        合约模式下同时加载资金费率数据用于资金费用结算。

        Args:
            engine: 已初始化的引擎实例
            data_dict: 数据字典
            symbols: 品种列表
            timeframes: 时间周期列表
            base_currency: 基础货币
            leverage: 杠杆倍数
            init_cash: 初始资金
            trading_mode: 交易模式 ("spot" / "futures")
            time_range: 时间范围字符串（用于资金费率筛选）

        Returns:
            tuple: (instruments字典, bar_types字典, 清洗后的K线DataFrame字典)
        """
        from decimal import Decimal

        bridge = _get_axon_bridge()

        instruments = {}
        bar_types = {}
        cleaned_data: dict[str, pd.DataFrame] = {}
        is_futures = trading_mode == "futures"

        # 创建交易所（简单配置）
        engine.add_venue(
            venue_name="BINANCE",
            starting_capital=init_cash,
            base_currency=base_currency,
            default_leverage=Decimal(str(leverage)),
        )

        # 解析资金费率筛选的时间范围
        funding_start = funding_end = None
        if is_futures and time_range:
            try:
                from utils.validation import parse_time_range

                start_dt, end_dt = parse_time_range(time_range)
                funding_start = start_dt.strftime("%Y-%m-%d") if start_dt else None
                funding_end = end_dt.strftime("%Y-%m-%d") if end_dt else None
            except Exception as e:
                logger.warning(f"解析资金费率时间范围失败: {e}")

        # 为每个品种创建 instrument 并加载数据
        for symbol in symbols:
            timeframe = timeframes[0]
            key = f"{symbol}_{timeframe}"

            if key not in data_dict:
                logger.warning(f"跳过 {key}，数据未加载")
                continue

            df = data_dict[key]

            # 根据交易模式创建品种：现货 / 永续合约
            base, quote = self._parse_symbol(symbol)
            if is_futures:
                # 永续合约：U本位结算，合约乘数默认 1（1张=1个base币）
                instrument = bridge.create_swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)
            else:
                instrument = bridge.create_spot_instrument(base, quote)
            engine.add_instrument(instrument)
            instruments[symbol] = instrument

            # 合约模式：加载资金费率数据用于资金费用结算
            if is_futures:
                try:
                    funding_df = self.provider.load_funding_rate(symbol, start=funding_start, end=funding_end)
                    if not funding_df.empty:
                        engine.add_funding_data(instrument, funding_df)
                    else:
                        logger.warning(f"{symbol} 无资金费率数据，将不进行资金费用结算")
                except Exception as e:
                    logger.warning(f"{symbol} 资金费率加载失败，跳过: {e}")

            # 处理 DataFrame
            df = df.copy()
            required_cols = ["open", "high", "low", "close", "volume"]
            df.columns = [col.lower() for col in df.columns]

            cols_to_keep = [c for c in required_cols if c in df.columns]
            if "timestamp" in df.columns:
                cols_to_keep.insert(0, "timestamp")

            df = df[cols_to_keep]

            if not isinstance(df.index, pd.DatetimeIndex) and "timestamp" in df.columns:
                df = df.set_index("timestamp")
                df.drop(columns=["timestamp"], errors="ignore", inplace=True)

            if len(df) > 0:
                try:
                    df.index = pd.to_datetime(df.index, utc=True)
                except Exception as e:
                    logger.warning(f"时间戳转换警告: {e}")
                    df.index = pd.to_datetime(df.index.astype(str), utc=True)

            # 乱序/重复时间戳防御: 事件驱动引擎要求 bar 按时间单调递增,
            # 统一排序并去重(保留最后一条),避免乱序 bar 导致回测资金曲线失真
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]

            for col in required_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    # Inf 转 NaN 后统一清洗,否则 Inf 进入指标计算会产出 NaN 指标
                    df[col] = df[col].replace([np.inf, -np.inf], np.nan)
                    df[col] = df[col].astype("float64")
                    nan_count = df[col].isna().sum()
                    if nan_count > 0:
                        logger.warning(f"{symbol} 的 {col} 列有 {nan_count} 个 NaN/Inf 值，将填充为 0.0")
                        df[col] = df[col].fillna(0.0)

            non_numeric_cols = df.select_dtypes(exclude=["number"]).columns.tolist()
            if non_numeric_cols:
                logger.error(f"发现非数值列: {non_numeric_cols}，将删除这些列")
                df = df.drop(columns=non_numeric_cols)

            # 保存清洗后的 K 线，供结果注入 klines（回放页数据源）
            cleaned_data[key] = df

            bar_type_str = f"{symbol}-{timeframe}"
            bar_types[symbol] = bar_type_str

            # 通过引擎的 load_data_from_parquet 方法加载数据
            # 先保存为临时 parquet 文件再加载
            import os
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                df.to_parquet(tmp_path, index=True)
                engine.load_data_from_parquet(tmp_path, instrument)
                logger.info(f"成功加载 {symbol} 的 {len(df)} 条K线数据")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        logger.info(f"共加载 {len(instruments)} 个品种")

        return instruments, bar_types, cleaned_data

    def _format_results(
        self,
        results: dict,
        symbols: list[str],
        timeframe: str,
        strategy_name: str,
        per_symbol_results: dict,
    ) -> dict:
        """汇总多品种回测结果

        Args:
            results: 跨品种聚合后的指标(PnL/fills/fees 累加,data_start 取 min 等)
            per_symbol_results: 每个品种单独的原始结果,用于 results_by_symbol[k].metrics
                填单品种 metrics(否则 output_results 显示的"贡献盈亏"是聚合 PnL)
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称

        Returns:
            多品种汇总 dict
        """
        from backtest.result_formatter_service import ResultFormatterService

        # 计算 portfolio-level 指标(从 per_symbol_results 重算,不能简单 sum 百分比类)
        n = len(per_symbol_results)
        total_pnl = results.get("total_pnl", 0.0)
        total_trades = results.get("trade_count", 0)
        total_fills = results.get("fills", 0)

        # initial_equity / final_equity:每品种独立资金池(每 run 都 initial_cash 起步)
        # 假设所有品种用同一 initial_cash,从第一个结果读
        first_sym = symbols[0] if symbols else None
        first_result = per_symbol_results.get(first_sym, {}) if first_sym else {}
        initial_cash_per_symbol = first_result.get("initial_capital", 100000.0)
        initial_equity = initial_cash_per_symbol * n  # N 个独立资金池
        final_equity = initial_equity + total_pnl
        # total_return:百分比
        total_return = (total_pnl / initial_equity * 100.0) if initial_equity > 0 else 0.0

        # win_rate:跨品种重新统计(从 per_symbol 各自的 wins / trades_count 算)
        # 没 trade records 数据时 fallback 到 fills 兜底(撮合成交笔数 = 交易笔数近似)
        winning_trades = 0
        losing_trades = 0
        for r in per_symbol_results.values():
            sym_trades = r.get("trades", [])
            if sym_trades:
                # 有 trade records(开平仓配对)
                for t in sym_trades:
                    pnl = t.get("pnl", 0) if isinstance(t, dict) else 0
                    if pnl > 0:
                        winning_trades += 1
                    elif pnl < 0:
                        losing_trades += 1
            else:
                # 没 trade records,fallback 到 per-symbol 的 win_rate * fills 估算
                sym_wr = r.get("win_rate", 0.0)
                sym_fills = r.get("fills", 0)
                winning_trades += int(sym_wr * sym_fills)
        win_rate = winning_trades / total_trades * 100.0 if total_trades > 0 else 0.0

        # max_drawdown:取最大回撤品种的 pct(独立资金池不该 sum)
        max_dd_pct = 0.0
        for r in per_symbol_results.values():
            sym_dd = r.get("max_drawdown_pct", 0.0)
            if sym_dd > max_dd_pct:
                max_dd_pct = sym_dd

        # sharpe_ratio:per-symbol 加权平均(按交易笔数加权,更接近 portfolio 真实夏普)
        # 简单实现:n=1 时直接用,否则用 fills 加权
        if n == 1:
            sharpe_ratio = first_result.get("sharpe_ratio", 0.0)
        else:
            if total_fills > 0:
                sharpe_ratio = (
                    sum(r.get("sharpe_ratio", 0.0) * r.get("fills", 0) for r in per_symbol_results.values())
                    / total_fills
                )
            else:
                sharpe_ratio = sum(r.get("sharpe_ratio", 0.0) for r in per_symbol_results.values()) / n

        # 填充 results 的 portfolio-level 字段,让 output_results 能读到
        # (原本只有 sum/min/max 字段,initial_equity/win_rate 等需显式计算)
        results["initial_equity"] = initial_equity
        results["final_equity"] = final_equity
        results["total_return"] = total_return
        results["win_rate"] = win_rate
        results["max_drawdown"] = max_dd_pct  # 用 pct 字段(百分比,单位一致)
        results["sharpe_ratio"] = sharpe_ratio

        return {
            "strategy_name": strategy_name,
            "symbols": symbols,
            "timeframe": timeframe,
            "is_multi_symbol": True,
            "results_by_symbol": {
                symbol: ResultFormatterService.format_axon_results(
                    results=per_symbol_results.get(symbol, {}),
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_name=strategy_name,
                ).get(f"{symbol}_{timeframe}", {})
                for symbol in symbols
            },
            # portfolio 级别的 metrics 使用聚合数据格式化
            "portfolio": ResultFormatterService.format_axon_results(
                results={**results, "trades": [], "equity_curve": []},
                symbol=symbols[0] if symbols else "PORTFOLIO",
                timeframe=timeframe,
                strategy_name=strategy_name,
            ).get("portfolio", {}),
            # 保留 _meta 和 account 信息
            "_meta": {
                "engine": "axon",
                "strategy": strategy_name,
                "timestamp": int(datetime.now().timestamp()),
                "formatted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "account": {
                "starting_balance": initial_equity,
                "final_nav": final_equity,
                "total_pnl": total_pnl,
            },
        }
