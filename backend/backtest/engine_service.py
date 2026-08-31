"""
回测引擎服务模块（基于 axon_quant 体系）

封装事件驱动回测引擎的初始化、数据加载、策略加载和执行流程。
将原本分散在 cli.py 和 service.py 中的引擎操作逻辑统一到此模块。

所有与 axon-quant 的交互都通过 axon_bridge 适配层进行。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

from datetime import datetime
from typing import Any

import pandas as pd

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


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
        if show_progress:
            pass

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

        # 2. 初始化引擎
        if show_progress:
            pass

        engine = self._initialize_engine(
            engine_config=engine_config,
            strategy_name=strategy_name,
            init_cash=init_cash,
            data_dict=data_dict,
        )

        # 3. 加载数据到引擎
        if show_progress:
            pass

        _instruments, bar_types = self._load_data_to_engine(
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

        # 4. 加载策略
        if show_progress:
            pass

        from backtest.strategy_loader_service import StrategyLoaderService

        # 构造策略必需的 instrument_ids / bar_types
        instrument_ids = []
        bar_types = []
        for s in symbols:
            for t in timeframes:
                instrument_ids.append({"symbol": s, "venue": "BINANCE"})
                bar_types.append(t)

        strategy = StrategyLoaderService.load_strategy(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            instrument_ids=instrument_ids,
            bar_types=bar_types,
        )

        if strategy is None:
            msg = f"无法加载策略: {strategy_name}"
            raise ValueError(msg)

        # 4. 执行回测（axon_quant 适配层）
        if show_progress:
            pass

        if len(symbols) == 1:
            # 单品种：直接调用 run_with_strategy
            first_key = next(iter(loaded_data.keys()))
            entry = loaded_data[first_key]
            df = entry["data"]
            parts = first_key.rsplit("_", 1)
            symbol = parts[0] if len(parts) > 1 else first_key

            # 末日单管理:CLI / 脚本传 force_liquidate 控制回测结束 EOD 平仓
            # True = 强制市价清仓(所有 PnL 转为已实现,适合日报/对账)
            force_liquidate = (engine_config or {}).get("force_liquidate", False)

            # 直接调用 BacktestLoop，传递特征数据
            result = engine.run(
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
            # 多品种：每个品种跑一次，结果合并
            force_liquidate = (engine_config or {}).get("force_liquidate", False)
            _SUM_KEYS = {
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
            _MIN_KEYS = {"data_start_ns"}
            _MAX_KEYS = {"data_end_ns"}
            aggregated_metrics: dict[str, Any] = {}
            per_symbol_results: dict[str, dict[str, Any]] = {}
            for key, entry in loaded_data.items():
                df = entry["data"]
                parts = key.rsplit("_", 1)
                sym = parts[0] if len(parts) > 1 else key
                loop_result = engine.run(
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
                for k, v in result.items():
                    if k in _SUM_KEYS and isinstance(v, (int, float)):
                        aggregated_metrics[k] = aggregated_metrics.get(k, 0) + v
                    elif k in _MIN_KEYS and isinstance(v, (int, float)):
                        cur = aggregated_metrics.get(k, v)
                        aggregated_metrics[k] = min(cur, v) if cur else v
                    elif k in _MAX_KEYS and isinstance(v, (int, float)):
                        cur = aggregated_metrics.get(k, v)
                        aggregated_metrics[k] = max(cur, v) if cur else v
            raw_results = aggregated_metrics

        # 5. 格式化结果
        if show_progress:
            pass

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
            # 多品种结果汇总
            formatted_results = self._format_results(
                results=raw_results,
                symbols=symbols,
                timeframe=timeframes[0] if timeframes else "15m",
                strategy_name=strategy_name,
                per_symbol_results=per_symbol_results,
            )

        logger.info("[EventDrivenBacktestService] 回测完成")

        return formatted_results

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
    def _parse_symbol(symbol: str) -> tuple:
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
        return symbol[:3].upper(), symbol[3:].upper() if len(symbol) > 3 else (
            symbol.upper(),
            "USDT",
        )

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
            tuple: (instruments字典, bar_types字典)
        """
        from decimal import Decimal

        bridge = _get_axon_bridge()

        instruments = {}
        bar_types = {}
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

            for col in required_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    df[col] = df[col].astype("float64")
                    nan_count = df[col].isna().sum()
                    if nan_count > 0:
                        logger.warning(f"{symbol} 的 {col} 列有 {nan_count} 个 NaN 值，将填充为 0.0")
                        df[col] = df[col].fillna(0.0)

            non_numeric_cols = df.select_dtypes(exclude=["number"]).columns.tolist()
            if non_numeric_cols:
                logger.error(f"发现非数值列: {non_numeric_cols}，将删除这些列")
                df = df.drop(columns=non_numeric_cols)

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

        return instruments, bar_types

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
        results.get("total_fees", 0.0)

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
