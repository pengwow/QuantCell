"""
事件驱动回测引擎

基于 axon-quant 事件驱动架构的高性能回测引擎实现，
支持从 CSV/Parquet 加载数据、添加交易品种、运行策略等功能。

核心流程:
    1. 初始化 BacktestEngine（通过 axon_bridge 适配层）
    2. 添加交易品种（spot_instrument / swap_instrument）
    3. 加载 K 线数据
    4. 添加策略（注入引擎引用）
    5. 逐 bar 驱动：begin_bar → strategy.on_bar → engine.step()
    6. 提取回测结果

作者: QuantCell Team
版本: 3.0.0
日期: 2026-08-14
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


# 安全的浮点数转换
def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全地转换为浮点数"""
    try:
        if value is None:
            return default
        return float(value)
    except ValueError, TypeError:
        return default


from .base import BacktestEngineBase, EngineType


class EventDrivenBacktestEngine(BacktestEngineBase):
    """
    事件驱动回测引擎（基于 axon-quant）

    使用 axon_quant.BacktestEngine 作为底层撮合引擎，
    通过事件驱动模型处理订单提交、撮合和成交。

    回测流程:
        1. initialize(): 创建 BacktestEngine 实例
        2. add_venue(): 配置交易所（兼容接口）
        3. add_instrument(): 添加交易品种
        4. load_data_from_csv/parquet(): 加载 K 线数据
        5. add_strategy(): 添加策略（注入引擎引用）
        6. run_backtest(): 执行回测
        7. get_results(): 获取结果
        8. cleanup(): 清理资源

    Example:
        >>> config = {"initial_capital": 100000.0}
        >>> engine = EventDrivenBacktestEngine(config)
        >>> engine.initialize()
        >>> engine.add_instrument(instrument_dict)
        >>> engine.load_data_from_parquet("data.parquet", instrument_dict)
        >>> engine.add_strategy(strategy)
        >>> results = engine.run_backtest()
        >>> engine.cleanup()
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)

        # axon-quant BacktestEngine 实例
        self._engine: Any | None = None

        # 交易所和品种管理
        self._venue_name: str = "BINANCE"
        self._instruments: dict[str, dict] = {}

        # 策略和数据管理
        self._strategies: list[Any] = []
        self._dataframes: dict[str, pd.DataFrame] = {}

        # 资金费率数据（合约回测用）: {instrument_id: [(ts_ns, rate, mark_price), ...]}
        self._funding_events: dict[str, list[tuple]] = {}

        # 回测结果缓存
        self._backtest_result: Any | None = None

        # 订单 ID 计数器（用于生成唯一订单 ID）
        self._order_id_counter: int = 0

        # 累计统计
        self._total_fills: int = 0
        self._total_events: int = 0

        logger.debug("事件驱动回测引擎实例已创建")

    @property
    def engine_type(self) -> EngineType:
        return EngineType.EVENT_DRIVEN

    @property
    def engine(self) -> Any | None:
        """获取底层 BacktestEngine 实例"""
        return self._engine

    def initialize(self) -> None:
        """
        初始化回测引擎

        通过 axon_bridge 适配层创建并配置 BacktestEngine 实例。
        配置包括初始资金、种子流动性、自动再平衡等。
        """
        try:
            logger.info("开始初始化事件驱动回测引擎...")

            if not self._validate_config():
                msg = "引擎配置验证失败"
                raise ValueError(msg)

            from axon_bridge import EngineConfig, create_backtest_engine

            initial_capital = float(self._config.get("initial_capital", 100000.0))
            half_spread = float(self._config.get("half_spread", 0.01))
            depth_levels = int(self._config.get("depth_levels", 5))
            size_per_level = float(self._config.get("size_per_level", 1.0))
            auto_rebalance_threshold = float(self._config.get("auto_rebalance_threshold", 0.01))

            bridge_config = EngineConfig(
                initial_cash=initial_capital,
                half_spread=half_spread,
                depth_levels=depth_levels,
                size_per_level=size_per_level,
                auto_rebalance_threshold=auto_rebalance_threshold,
            )

            self._engine = create_backtest_engine(bridge_config)
            self._is_initialized = True

            logger.info(f"事件驱动回测引擎初始化完成 (initial_capital={initial_capital})")

        except Exception as e:
            logger.error(f"事件驱动回测引擎初始化失败: {e}")
            msg = f"引擎初始化失败: {e}"
            raise RuntimeError(msg) from e

    def add_venue(
        self,
        venue_name: str,
        oms_type: Any = None,
        account_type: Any = None,
        starting_capital: float = 100000.0,
        base_currency: str = "USD",
        default_leverage: Any = None,
    ) -> str:
        """
        添加交易所配置（兼容接口）

        axon-quant 中交易所概念已简化为撮合引擎配置，
        此方法保留用于向后兼容。

        Args:
            venue_name: 交易所名称
            oms_type: 未使用（兼容接口）
            account_type: 未使用（兼容接口）
            starting_capital: 初始资金
            base_currency: 基础货币代码
            default_leverage: 默认杠杆倍数

        Returns:
            str: 交易所名称
        """
        if not self._is_initialized:
            msg = "引擎未初始化，请先调用 initialize()"
            raise RuntimeError(msg)

        self._venue_name = venue_name
        logger.debug(f"交易所已配置: {venue_name}")
        return venue_name

    def add_instrument(self, instrument: dict[str, Any]) -> None:
        """
        添加交易品种

        Args:
            instrument: 品种字典（由 axon_bridge.create_spot_instrument 创建）
        """
        if not self._is_initialized:
            msg = "引擎未初始化，请先调用 initialize()"
            raise RuntimeError(msg)

        if not instrument:
            msg = "交易品种不能为空"
            raise ValueError(msg)

        instrument_id = self._instrument_id_from_dict(instrument)
        self._instruments[instrument_id] = instrument
        logger.debug(f"交易品种已添加: {instrument_id}")

    def add_funding_data(
        self,
        instrument: dict[str, Any],
        funding_df: pd.DataFrame,
    ) -> None:
        """
        添加资金费率数据（合约回测用）

        回测主循环中，当 bar 时间戳越过某条资金费率记录时，
        会通过 engine.push_funding() 推送给撮合引擎结算资金费用。

        Args:
            instrument: 品种字典（swap 类型）
            funding_df: 资金费率 DataFrame，索引为 DatetimeIndex，
                        需包含 funding_rate 列，可选 mark_price 列
        """
        if funding_df is None or funding_df.empty:
            return

        instrument_id = self._instrument_id_from_dict(instrument)

        from axon_bridge import to_ns_timestamp

        events = []
        has_mark = "mark_price" in funding_df.columns
        for ts, row in funding_df.iterrows():
            rate = float(row.get("funding_rate", 0.0))
            mark = float(row.get("mark_price", 0.0)) if has_mark else 0.0
            events.append((to_ns_timestamp(ts), rate, mark))

        # 按时间升序排列，便于回测中顺序消费
        events.sort(key=lambda x: x[0])
        self._funding_events[instrument_id] = events
        logger.info(f"资金费率数据已添加: {instrument_id}, 共{len(events)}条")

    def load_data_from_csv(
        self,
        csv_path: str | Path,
        instrument: dict[str, Any],
        timestamp_column: str = "timestamp",
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
        columns_mapping: dict[str, str] | None = None,
        sep: str = ";",
        decimal: str = ".",
    ) -> pd.DataFrame:
        """
        从 CSV 文件加载 K 线数据

        Args:
            csv_path: CSV 文件路径
            instrument: 品种字典
            timestamp_column: 时间戳列名
            timestamp_format: 时间戳格式
            columns_mapping: 列名映射字典
            sep: CSV 分隔符
            decimal: 小数点符号

        Returns:
            pd.DataFrame: 加载的 K 线数据
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            msg = f"CSV 文件不存在: {csv_path}"
            raise FileNotFoundError(msg)

        try:
            logger.info(f"开始从 CSV 加载数据: {csv_path}")

            df = pd.read_csv(csv_path, sep=sep, decimal=decimal, header=0, index_col=False)

            if columns_mapping:
                df = df.rename(columns=columns_mapping)

            if timestamp_column in df.columns:
                df[timestamp_column] = pd.to_datetime(df[timestamp_column], format=timestamp_format)
                df = df.rename(columns={timestamp_column: "timestamp"})

            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    msg = f"CSV 文件缺少必需的列: {col}"
                    raise ValueError(msg)

            instrument_id = self._instrument_id_from_dict(instrument)
            self._dataframes[instrument_id] = df
            self._instruments[instrument_id] = instrument

            logger.info(f"CSV 数据加载完成: {len(df)} 条 K 线")
            return df

        except Exception as e:
            logger.error(f"从 CSV 加载数据失败: {e}")
            msg = f"从 CSV 加载数据失败: {e}"
            raise RuntimeError(msg) from e

    def load_data_from_parquet(
        self,
        parquet_path: str | Path,
        instrument: dict[str, Any],
        timestamp_column: str = "timestamp",
    ) -> pd.DataFrame:
        """
        从 Parquet 文件加载 K 线数据

        Args:
            parquet_path: Parquet 文件路径
            instrument: 品种字典
            timestamp_column: 时间戳列名

        Returns:
            pd.DataFrame: 加载的 K 线数据
        """
        parquet_path = Path(parquet_path)
        if not parquet_path.exists():
            msg = f"Parquet 文件不存在: {parquet_path}"
            raise FileNotFoundError(msg)

        try:
            logger.info(f"开始从 Parquet 加载数据: {parquet_path}")

            df = pd.read_parquet(parquet_path)

            if timestamp_column in df.columns:
                df[timestamp_column] = pd.to_datetime(df[timestamp_column])
                df = df.rename(columns={timestamp_column: "timestamp"})

            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    msg = f"Parquet 文件缺少必需的列: {col}"
                    raise ValueError(msg)

            instrument_id = self._instrument_id_from_dict(instrument)
            self._dataframes[instrument_id] = df
            self._instruments[instrument_id] = instrument

            logger.info(f"Parquet 数据加载完成: {len(df)} 条 K 线")
            return df

        except Exception as e:
            logger.error(f"从 Parquet 加载数据失败: {e}")
            msg = f"从 Parquet 加载数据失败: {e}"
            raise RuntimeError(msg) from e

    def add_strategy(self, strategy: Any) -> None:
        """
        添加策略到引擎

        将引擎引用注入到策略中，使策略可以通过 submit_order() 方法提交订单。

        Args:
            strategy: EventDrivenStrategy 实例
        """
        if not self._is_initialized:
            msg = "引擎未初始化，请先调用 initialize()"
            raise RuntimeError(msg)

        if not strategy:
            msg = "策略不能为空"
            raise ValueError(msg)

        try:
            # 注入引擎引用
            strategy._engine_ref = self
            self._strategies.append(strategy)
            logger.debug("策略已添加")

        except Exception as e:
            logger.error(f"添加策略失败: {e}")
            msg = f"添加策略失败: {e}"
            raise RuntimeError(msg) from e

    def submit_order(
        self,
        order_dict: dict[str, Any],
        timestamp_ns: int,
    ) -> None:
        """
        提交订单或取消事件到引擎

        根据事件类型构建对应的事件字典，然后推送到 BacktestEngine 事件队列。
        此方法供 EventDrivenStrategy 及其子类调用。

        Args:
            order_dict: 订单/事件字典
            timestamp_ns: 事件时间戳（纳秒）
        """
        if not self._engine:
            msg = "引擎未初始化"
            raise RuntimeError(msg)

        from axon_bridge import build_order_submitted_event

        # 判断事件类型
        event_type = order_dict.get("type", "")

        if event_type == "order_cancelled":
            # 取消订单事件，已经是完整格式
            event = order_dict
        else:
            # 普通订单，需要构建 submitted 事件
            event = build_order_submitted_event(order_dict, timestamp_ns)

        self._engine.push_event(event)

    def run_backtest(self) -> dict[str, Any]:
        """
        运行回测

        逐根 K 线驱动引擎和策略:
            1. 调用所有策略的 on_start()
            2. 对每根 bar:
                a. engine.begin_bar(price, instrument)
                b. 调用所有策略的 on_bar(bar_data)
                c. engine.step() 执行事件队列中的事件
            3. 调用所有策略的 on_stop()
            4. 提取回测结果

        Returns:
            Dict[str, Any]: 回测结果字典
        """
        if not self._is_initialized:
            msg = "引擎未初始化，请先调用 initialize()"
            raise RuntimeError(msg)

        if not self._strategies:
            msg = "未添加策略，请先调用 add_strategy()"
            raise RuntimeError(msg)

        if not self._dataframes:
            msg = "未加载数据，请先调用 load_data_from_csv() 或 load_data_from_parquet()"
            raise RuntimeError(msg)

        try:
            logger.info("开始执行回测...")

            # 重置统计
            self._total_fills = 0
            self._total_events = 0
            self._order_id_counter = 0

            # 启动所有策略
            for strategy in self._strategies:
                strategy.on_start()

            # 计算总 bar 数用于进度显示
            total_bars = sum(len(df) for df in self._dataframes.values())
            processed = 0

            # 每个品种的资金费率消费指针（顺序推送，避免重复）
            funding_cursor: dict[str, int] = {k: 0 for k in self._funding_events}

            # 逐品种逐 bar 驱动
            for instrument_id, df in self._dataframes.items():
                instrument = self._instruments.get(instrument_id)
                if instrument is None:
                    logger.warning(f"跳过 {instrument_id}，品种未注册")
                    continue

                funding_list = self._funding_events.get(instrument_id, [])
                cursor = funding_cursor.get(instrument_id, 0)

                for idx in range(len(df)):
                    row = df.iloc[idx]
                    bar_close = float(row.get("close", 0))
                    bar_open = float(row.get("open", 0))
                    bar_high = float(row.get("high", 0))
                    bar_low = float(row.get("low", 0))
                    bar_volume = float(row.get("volume", 0))

                    # 转换时间戳
                    bar_ts = df.index[idx]
                    from axon_bridge import to_ns_timestamp

                    ts_ns = to_ns_timestamp(bar_ts)

                    # 关键步骤 0: 推送时间戳已到达的资金费率事件（合约结算）
                    while cursor < len(funding_list) and funding_list[cursor][0] <= ts_ns:
                        f_ts, f_rate, f_mark = funding_list[cursor]
                        # mark_price 缺失时回退使用当前 bar 收盘价
                        mark_price = f_mark if f_mark > 0 else bar_close
                        self._engine.push_funding(
                            instrument=instrument,
                            funding_rate=f_rate,
                            mark_price=mark_price,
                            timestamp_ns=f_ts,
                        )
                        cursor += 1
                    funding_cursor[instrument_id] = cursor

                    # 关键步骤 1: 通知引擎新 bar 开始
                    self._engine.begin_bar(bar_close, instrument)

                    # 构建 bar 数据字典
                    bar = {
                        "instrument_id": instrument_id,
                        "open": bar_open,
                        "high": bar_high,
                        "low": bar_low,
                        "close": bar_close,
                        "volume": bar_volume,
                        "timestamp": ts_ns,
                        "datetime": bar_ts,
                        "ts_event": ts_ns,
                    }

                    # 关键步骤 2: 通知策略处理 bar
                    for strategy in self._strategies:
                        strategy.on_bar(bar)

                    # 关键步骤 3: 执行事件队列中的所有事件
                    # 策略的 on_bar 可能通过 submit_order 推送了订单事件
                    # 需要调用 step() 来撮合这些订单
                    stats = self._engine.step()
                    if stats:
                        self._total_fills += getattr(stats, "fills", 0)
                        self._total_events += getattr(stats, "events_processed", 0)

                    processed += 1
                    if processed % 1000 == 0:
                        progress = (processed / total_bars) * 100
                        logger.info(f"回测进度: {processed}/{total_bars} bars ({progress:.1f}%)")

            # 停止所有策略
            for strategy in self._strategies:
                strategy.on_stop()

            # 获取最终结果
            results = self._process_results()

            logger.info(f"回测执行完成: fills={self._total_fills}, events={self._total_events}")
            return results

        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            import traceback

            logger.error(f"错误堆栈:\n{traceback.format_exc()}")
            msg = f"回测执行失败: {e}"
            raise RuntimeError(msg) from e

    def _process_results(self) -> dict[str, Any]:
        """
        从 BacktestEngine 提取回测结果

        调用 engine.run() 获取 RunResult，然后通过 axon_bridge 提取标准化结果。

        Returns:
            Dict[str, Any]: 标准化的回测结果
        """
        if not self._engine:
            return {}

        try:
            from axon_bridge import extract_run_result

            # 确保引擎完成
            if not self._engine.is_finished:
                result = self._engine.run()
            else:
                result = self._engine.run()  # run() 可多次调用

            if result is None:
                logger.warning("引擎返回结果为空")
                return {}

            # 使用适配层提取结果
            raw_results = extract_run_result(result)

            # 构建完整的结果字典
            results = {
                "trades": self._normalize_trades(raw_results.get("trades", [])),
                "positions": self._normalize_positions(raw_results.get("positions", [])),
                "equity_curve": self._normalize_equity_curve(raw_results.get("equity_curve", [])),
                "account": self._build_account_info(raw_results),
                "metrics": self._build_metrics(raw_results),
                "_raw": raw_results,
            }

            self._results = results
            return results

        except Exception as e:
            logger.error(f"处理回测结果失败: {e}")
            import traceback

            logger.error(f"错误堆栈:\n{traceback.format_exc()}")
            return {}

    def _normalize_trades(self, raw_trades: list) -> list[dict[str, Any]]:
        """标准化交易记录格式"""
        trades = []
        for i, trade in enumerate(raw_trades):
            if isinstance(trade, dict):
                ts = trade.get("ts", trade.get("timestamp", 0))
                formatted_time = ""
                timestamp_val = 0

                if isinstance(ts, (int, float)) and ts > 0:
                    if ts > 1e18:
                        ts_sec = int(ts / 1e9)
                    elif ts > 1e12:
                        ts_sec = int(ts / 1000)
                    else:
                        ts_sec = int(ts)
                    try:
                        dt = datetime.fromtimestamp(ts_sec, tz=UTC)
                        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError, OSError:
                        formatted_time = str(ts)
                    timestamp_val = ts_sec

                price = _safe_float(trade.get("price", trade.get("avg_px", 0)))
                quantity = _safe_float(trade.get("quantity", trade.get("qty", 0)))
                side = str(trade.get("side", "")).upper()
                direction = "买入" if side in ("BUY", "0") else "卖出" if side in ("SELL", "1") else side
                status = str(trade.get("status", "filled"))
                trade_id = str(trade.get("trade_id", trade.get("id", f"trade_{i}")))
                order_id = str(trade.get("order_id", trade.get("client_order_id", "")))
                instrument_id = str(trade.get("instrument_id", trade.get("symbol", "")))
                commission = str(trade.get("commission", trade.get("fees", "0")))

                trades.append(
                    {
                        "trade_id": trade_id,
                        "client_order_id": order_id,
                        "venue_order_id": "",
                        "position_id": str(trade.get("position_id", "")),
                        "symbol": instrument_id,
                        "side": side,
                        "direction": direction,
                        "quantity": quantity,
                        "price": price,
                        "volume": quantity * price,
                        "commission": commission,
                        "timestamp": timestamp_val,
                        "formatted_time": formatted_time,
                        "status": status,
                    }
                )
        return trades

    def _normalize_positions(self, raw_positions: list) -> list[dict[str, Any]]:
        """标准化持仓记录格式"""
        positions = []
        for pos in raw_positions:
            if isinstance(pos, dict):
                pos_id = str(pos.get("position_id", pos.get("id", "")))
                if not pos_id:
                    pos_id = f"POS_{len(positions)}"

                instrument_id = str(pos.get("instrument_id", pos.get("symbol", "")))
                quantity = _safe_float(pos.get("quantity", pos.get("qty", 0)))
                avg_px = _safe_float(pos.get("avg_price", pos.get("avg_px", 0)))
                realized_pnl = str(pos.get("realized_pnl", "0"))

                positions.append(
                    {
                        "position_id": pos_id,
                        "symbol": instrument_id,
                        "side": str(pos.get("side", "")),
                        "quantity": quantity,
                        "trade_quantity": abs(quantity),
                        "signed_quantity": quantity,
                        "avg_px_open": avg_px,
                        "avg_px_close": avg_px,
                        "realized_pnl": realized_pnl,
                        "opening_order_id": str(pos.get("opening_order_id", "")),
                        "closing_order_id": str(pos.get("closing_order_id", "")),
                        "trade_ids": [],
                        "ts_opened": pos.get("ts_opened", 0),
                        "ts_closed": pos.get("ts_closed", 0),
                        "duration_ns": pos.get("duration_ns", 0),
                    }
                )
        return positions

    def _normalize_equity_curve(self, raw_curve: list) -> list[dict[str, Any]]:
        """标准化权益曲线格式"""
        equity_curve = []
        for i, point in enumerate(raw_curve):
            if isinstance(point, dict):
                nav = _safe_float(point.get("nav", point.get("equity", 0)))
                equity_curve.append(
                    {
                        "timestamp": i,
                        "formatted_time": "",
                        "equity": nav,
                        "balance": nav,
                        "margin": 0.0,
                    }
                )
            elif isinstance(point, (int, float)):
                nav = _safe_float(point)
                equity_curve.append(
                    {
                        "timestamp": i,
                        "formatted_time": "",
                        "equity": nav,
                        "balance": nav,
                        "margin": 0.0,
                    }
                )
        return equity_curve

    def _build_account_info(self, raw_results: dict[str, Any]) -> dict[str, Any]:
        """构建账户信息"""
        final_nav = _safe_float(raw_results.get("final_nav", 0))
        nav_peak = _safe_float(raw_results.get("nav_peak", 0))
        total_fees = _safe_float(raw_results.get("total_fees", 0))

        return {
            "balance": final_nav,
            "margin": 0.0,
            "equity": final_nav,
            "initial_balance": nav_peak,
            "final_balance": final_nav,
            "max_balance": nav_peak,
            "min_balance": 0.0,
            "peak_equity": nav_peak,
            "trough_equity": 0.0,
            "total_commissions": total_fees,
        }

    def _build_metrics(self, raw_results: dict[str, Any]) -> dict[str, Any]:
        """构建绩效指标

        axon_quant 原始字段语义：
        - max_drawdown_pct: 百分比表示（例如 2.5 → 2.5%）
        - win_rate: 0~1 小数（自动 *100 转为百分比）
        - fills: 成交次数（单次交易可能对应多次成交）
        - trades: 已完成的交易记录列表；按 project_memory 必须优先使用 len(trades)
        - initial_cash / nav_peak: 初始资金（两者皆可取其一）
        """
        try:
            total_pnl = _safe_float(raw_results.get("total_pnl", 0))
            total_fees = _safe_float(raw_results.get("total_fees", 0))
            sharpe_ratio = _safe_float(raw_results.get("sharpe_ratio", 0))
            max_drawdown = _safe_float(raw_results.get("max_drawdown_pct", 0))
            win_rate = _safe_float(raw_results.get("win_rate", 0))

            # 胜率：若原始值为 0~1 区间的小数，自动 *100 转百分比表示
            if 0.0 < win_rate <= 1.0:
                win_rate = win_rate * 100.0

            # 交易笔数：按 project_memory 强制要求，优先使用 len(trades)
            raw_trades = raw_results.get("trades") or []
            if hasattr(raw_trades, "__len__") and len(raw_trades) > 0:
                total_trades = len(raw_trades)
            elif "total_trades" in raw_results:
                total_trades = int(raw_results["total_trades"])
            else:
                total_trades = int(raw_results.get("fills", 0))

            final_nav = _safe_float(raw_results.get("final_nav", 0))
            initial_cash = _safe_float(raw_results.get("initial_cash", raw_results.get("nav_peak", 0)))
            total_return = 0.0
            if initial_cash > 0:
                total_return = ((final_nav - initial_cash) / initial_cash) * 100

            winning_count = round(total_trades * win_rate / 100) if total_trades else 0
            losing_count = total_trades - winning_count

            return {
                "total_return": round(total_return, 2),
                "sharpe_ratio": round(sharpe_ratio, 4),
                "max_drawdown": round(max_drawdown, 2),
                "win_rate": round(win_rate, 2),
                "profit_factor": 0.0,
                "total_trades": total_trades,
                "total_closed_positions": 0,
                "winning_trades": winning_count,
                "losing_trades": losing_count,
                "total_pnl": round(total_pnl, 8),
                "initial_equity": round(initial_cash, 8),
                "final_equity": round(final_nav, 8),
                "total_fees": round(total_fees, 8),
            }
        except Exception as e:
            logger.warning(f"计算绩效指标失败: {e}")
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
                "total_closed_positions": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "initial_equity": 0.0,
                "final_equity": 0.0,
                "total_fees": 0.0,
            }

    def get_results(self) -> dict[str, Any]:
        """获取回测结果"""
        if not self._results:
            msg = "尚未执行回测，请先调用 run_backtest()"
            raise RuntimeError(msg)
        return self._results

    def cleanup(self) -> None:
        """清理引擎资源"""
        logger.info("开始清理回测引擎资源...")

        self._engine = None
        self._instruments.clear()
        self._dataframes.clear()
        self._strategies.clear()
        self._backtest_result = None
        self._order_id_counter = 0

        self._reset_state()
        logger.info("回测引擎资源清理完成")

    def get_venue(self, venue_name: str) -> str | None:
        """获取交易所名称"""
        return self._venue_name

    def get_instrument(self, instrument_id: str) -> dict | None:
        """获取品种信息"""
        return self._instruments.get(instrument_id)

    def get_strategies(self) -> list[Any]:
        """获取策略列表"""
        return self._strategies.copy()

    def get_data_count(self) -> int:
        """获取数据总数"""
        return sum(len(df) for df in self._dataframes.values())

    @staticmethod
    def _instrument_id_from_dict(instrument: dict) -> str:
        """从品种字典提取标识符"""
        if isinstance(instrument, dict):
            base = instrument.get("base", "")
            quote = instrument.get("quote", "")
            if base and quote:
                return f"{base}{quote}"
            return str(instrument)
        return str(instrument)
