"""
回测引擎服务模块（基于 axon_quant 体系）

唯一回测路径：BaseStrategy → BacktestLoop → axon_quant BacktestEngine。
负责数据加载、因子特征注入与结果格式化，引擎交互统一走 BacktestLoop。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pandas as pd

from backtest.backtest_loop import BacktestLoop, clean_ohlcv_df
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

# 逐品种进度回调：参数为 (已完成品种数, 品种总数, 当前开始回测的品种)
# ponytail: 粒度只到品种级，单品种回测在引擎执行期间没有中间进度（需 Rust 引擎支持 bar 级回调）
SymbolProgressCallback = Callable[[int, int, str], None]


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

        # 多品种结果占位（单品种路径不赋值，保持 None）
        per_symbol_results: dict[str, dict[str, Any]] | None = None

        # 3. 执行回测 —— 唯一路径：BaseStrategy → BacktestLoop（ctx 注入 features/funding/account）
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
                trading_mode=trading_mode,
                funding_df=self._load_funding(symbol, trading_mode, time_range),
            )
            raw_results = self._convert_backtest_result(result)
            # 清洗后 K 线写入结果，供回放页 kline_data（只进结果 JSON，不入 DB）
            raw_results["klines"] = self._build_kline_records(clean_ohlcv_df(df), engine_config, time_range)
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
                    trading_mode=trading_mode,
                    funding_df=self._load_funding(sym, trading_mode, time_range),
                )
                result = self._convert_backtest_result(loop_result)
                per_symbol_results[sym] = result
                # 清洗后 K 线写入结果，供回放页 kline_data（只进结果 JSON，不入 DB）
                result["klines"] = self._build_kline_records(clean_ohlcv_df(df), engine_config, time_range)
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

    def _load_funding(self, symbol: str, trading_mode: str, time_range: str | None):
        """futures 模式加载资金费率 DataFrame 供 BacktestLoop 透传给引擎。"""
        if trading_mode != "futures":
            return None
        start = end = None
        if time_range:
            try:
                from utils.validation import parse_time_range

                s, e = parse_time_range(time_range)
                start = s.strftime("%Y-%m-%d") if s else None
                end = e.strftime("%Y-%m-%d") if e else None
            except Exception as exc:
                logger.warning(f"解析资金费率时间范围失败: {exc}")
        try:
            funding_df = self.provider.load_funding_rate(symbol, start=start, end=end)
            if funding_df is None or funding_df.empty:
                logger.warning(f"{symbol} 无资金费率数据，将不进行资金费用结算")
                return None
            return funding_df
        except Exception as exc:
            logger.warning(f"{symbol} 资金费率加载失败，跳过: {exc}")
            return None

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
