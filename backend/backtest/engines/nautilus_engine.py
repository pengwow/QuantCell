# -*- coding: utf-8 -*-
"""
NautilusTrader 回测引擎封装类

基于 NautilusTrader 框架的回测引擎实现，提供完整的回测功能支持。

包含:
    - NautilusBacktestEngine: NautilusTrader 回测引擎封装类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-23
"""

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from loguru import logger

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model import TraderId, Venue
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.trading.strategy import Strategy

from .base import BacktestEngineBase, EngineType


class NautilusBacktestEngine(BacktestEngineBase):
    """
    NautilusTrader 回测引擎封装类

    基于 NautilusTrader BacktestEngine 的事件驱动回测引擎。
    支持从 CSV/Parquet 加载数据、添加交易所、添加交易品种、运行策略等功能。

    Attributes:
        engine_type: 引擎类型标识为 EVENT_DRIVEN
        engine: NautilusTrader BacktestEngine 实例
        venues: 已添加的交易所字典
        instruments: 已添加的交易品种字典
        strategies: 已添加的策略列表
        data: 已加载的数据列表
        bar_types: 已定义的 BarType 字典

    Example:
        >>> config = {
        ...     "trader_id": "BACKTEST-001",
        ...     "log_level": "INFO",
        ...     "initial_capital": 100000.0,
        ...     "start_date": "2023-01-01",
        ...     "end_date": "2023-12-31",
        ... }
        >>> engine = NautilusBacktestEngine(config)
        >>> engine.initialize()
        >>> engine.add_venue("SIM", starting_capital=100000.0)
        >>> engine.add_instrument(instrument)
        >>> engine.load_data_from_csv("data.csv", bar_type, instrument)
        >>> engine.add_strategy(strategy)
        >>> results = engine.run_backtest()
        >>> engine.cleanup()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 NautilusTrader 回测引擎

        Args:
            config: 引擎配置字典，包含:
                - trader_id: 交易者ID（可选，默认 "BACKTEST-001"）
                - log_level: 日志级别（可选，默认 "INFO"）
                - initial_capital: 初始资金（可选，默认 100000.0）
                - start_date: 回测开始日期（可选）
                - end_date: 回测结束日期（可选）
                - cache_database: 缓存数据库配置（可选）
                - streaming: 流式配置（可选）
        """
        super().__init__(config)

        # NautilusTrader 核心组件
        self._engine: Optional[BacktestEngine] = None
        self._engine_config: Optional[BacktestEngineConfig] = None

        # 交易所和品种管理
        self._venues: Dict[str, Venue] = {}
        self._instruments: Dict[str, Instrument] = {}
        self._bar_types: Dict[str, BarType] = {}

        # 策略和数据管理
        self._strategies: List[Strategy] = []
        self._data: List[Any] = []

        # 回测结果缓存
        self._backtest_result: Optional[Any] = None

        logger.debug("NautilusBacktestEngine 实例已创建")

    @property
    def engine_type(self) -> EngineType:
        """
        引擎类型属性

        Returns:
            EngineType: 返回 EngineType.EVENT_DRIVEN
        """
        return EngineType.EVENT_DRIVEN

    @property
    def engine(self) -> Optional[BacktestEngine]:
        """
        获取底层 NautilusTrader BacktestEngine 实例

        Returns:
            Optional[BacktestEngine]: BacktestEngine 实例，如果未初始化则返回 None
        """
        return self._engine

    def initialize(self) -> None:
        """
        初始化回测引擎

        执行引擎启动前的准备工作，包括:
        - 验证配置有效性
        - 创建 BacktestEngineConfig 配置
        - 初始化 NautilusTrader BacktestEngine

        Raises:
            RuntimeError: 初始化失败时抛出
            ValueError: 配置参数无效时抛出
        """
        try:
            logger.info("开始初始化 NautilusTrader 回测引擎...")

            # 验证配置
            if not self._validate_config():
                raise ValueError("引擎配置验证失败")

            # 创建引擎配置
            self._setup_engine_config()

            # 初始化 BacktestEngine
            self._engine = BacktestEngine(config=self._engine_config)

            self._is_initialized = True
            logger.info("NautilusTrader 回测引擎初始化完成")

        except Exception as e:
            logger.error(f"NautilusTrader 回测引擎初始化失败: {e}")
            raise RuntimeError(f"引擎初始化失败: {e}") from e

    def _setup_engine_config(self) -> None:
        """
        设置 NautilusTrader 引擎配置

        创建 BacktestEngineConfig，配置回测引擎的核心参数，包括:
        - 交易者ID
        - 日志配置
        - 缓存数据库配置（可选）
        - 流式配置（可选）
        """
        # 获取配置参数
        trader_id_str = self._config.get("trader_id", "BACKTEST-001")
        log_level = self._config.get("log_level", "INFO")

        # 创建引擎配置
        self._engine_config = BacktestEngineConfig(
            trader_id=TraderId(trader_id_str),
            logging=LoggingConfig(log_level=log_level),
        )
        logger.debug(f"引擎配置已创建: trader_id={trader_id_str}, log_level={log_level}")

    def add_venue(
        self,
        venue_name: str,
        oms_type: OmsType = OmsType.NETTING,
        account_type: AccountType = AccountType.MARGIN,
        starting_capital: float = 100000.0,
        base_currency: str = "USD",
        default_leverage: Decimal = Decimal(1),
    ) -> Venue:
        """
        添加交易所配置

        向回测引擎添加一个模拟交易所，配置交易环境参数。

        Args:
            venue_name: 交易所名称（如 "SIM", "XCME", "NYSE" 等）
            oms_type: 订单管理系统类型（默认 NETTING）
            account_type: 账户类型（默认 MARGIN）
            starting_capital: 初始资金（默认 100000.0）
            base_currency: 基础货币代码（默认 "USD"）
            default_leverage: 默认杠杆倍数（默认 1，表示无杠杆）

        Returns:
            Venue: 创建的交易所标识符

        Raises:
            RuntimeError: 引擎未初始化时抛出
            ValueError: 交易所名称无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not venue_name:
            raise ValueError("交易所名称不能为空")

        try:
            # 创建交易所标识符
            venue = Venue(venue_name)

            # 创建初始资金
            currency = Currency.from_str(base_currency)
            starting_balances = [Money(starting_capital, currency)]

            # 添加交易所到引擎
            self._engine.add_venue(
                venue=venue,
                oms_type=oms_type,
                account_type=account_type,
                starting_balances=starting_balances,
                base_currency=currency,
                default_leverage=default_leverage,
            )

            # 缓存交易所
            self._venues[venue_name] = venue

            logger.debug(f"交易所已添加: {venue_name}, 初始资金: {starting_capital} {base_currency}")
            return venue

        except Exception as e:
            logger.error(f"添加交易所失败: {e}")
            raise RuntimeError(f"添加交易所失败: {e}") from e

    def add_instrument(self, instrument: Instrument) -> None:
        """
        添加交易品种

        向回测引擎添加一个交易品种定义。

        Args:
            instrument: 交易品种定义对象

        Raises:
            RuntimeError: 引擎未初始化时抛出
            ValueError: 交易品种无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not instrument:
            raise ValueError("交易品种不能为空")

        try:
            # 添加交易品种到引擎
            self._engine.add_instrument(instrument)

            # 缓存交易品种
            instrument_id_str = str(instrument.id)
            self._instruments[instrument_id_str] = instrument

            logger.debug(f"交易品种已添加: {instrument_id_str}")

        except Exception as e:
            logger.error(f"添加交易品种失败: {e}")
            raise RuntimeError(f"添加交易品种失败: {e}") from e

    def load_data_from_csv(
        self,
        csv_path: Union[str, Path],
        bar_type: BarType,
        instrument: Instrument,
        timestamp_column: str = "timestamp",
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
        columns_mapping: Optional[Dict[str, str]] = None,
        sep: str = ";",
        decimal: str = ".",
    ) -> List[Bar]:
        """
        从 CSV 文件加载 K 线数据

        读取 CSV 文件，将数据转换为 NautilusTrader Bar 对象，并添加到引擎。

        Args:
            csv_path: CSV 文件路径
            bar_type: K 线类型定义（如 BarType.from_str("EURUSD.SIM-1-MINUTE-LAST-EXTERNAL")）
            instrument: 交易品种定义
            timestamp_column: 时间戳列名（默认 "timestamp"）
            timestamp_format: 时间戳格式（默认 "%Y-%m-%d %H:%M:%S"）
            columns_mapping: 列名映射字典（如 {"timestamp_utc": "timestamp"}）
            sep: CSV 分隔符（默认 ";"）
            decimal: 小数点符号（默认 "."）

        Returns:
            List[Bar]: 加载的 K 线数据列表

        Raises:
            RuntimeError: 引擎未初始化时抛出
            FileNotFoundError: CSV 文件不存在时抛出
            ValueError: 数据格式无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

        try:
            logger.info(f"开始从 CSV 加载数据: {csv_path}")

            # 读取 CSV 文件
            df = pd.read_csv(csv_path, sep=sep, decimal=decimal, header=0, index_col=False)

            # 应用列名映射
            if columns_mapping:
                df = df.rename(columns=columns_mapping)

            # 重组 DataFrame 结构
            required_columns = ["open", "high", "low", "close", "volume"]
            available_columns = [col for col in required_columns if col in df.columns]

            if len(available_columns) < 4:  # 至少需要 OHLC
                raise ValueError(f"CSV 文件缺少必需的列，需要至少 OHLC，当前列: {df.columns.tolist()}")

            # 处理时间戳列
            if timestamp_column in df.columns:
                df[timestamp_column] = pd.to_datetime(df[timestamp_column], format=timestamp_format)
                df = df.rename(columns={timestamp_column: "timestamp"})

            # 设置时间戳为索引
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

            # 确保必需的列存在
            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    raise ValueError(f"CSV 文件缺少必需的列: {col}")

            # 使用 BarDataWrangler 转换数据
            wrangler = BarDataWrangler(bar_type, instrument)
            bars: List[Bar] = wrangler.process(df)

            # 添加数据到引擎
            self._engine.add_data(bars)
            self._data.extend(bars)

            # 缓存 BarType
            bar_type_str = str(bar_type)
            self._bar_types[bar_type_str] = bar_type

            logger.info(f"CSV 数据加载完成: {len(bars)} 条 K 线")
            return bars

        except Exception as e:
            logger.error(f"从 CSV 加载数据失败: {e}")
            raise RuntimeError(f"从 CSV 加载数据失败: {e}") from e

    def load_data_from_parquet(
        self,
        parquet_path: Union[str, Path],
        bar_type: BarType,
        instrument: Instrument,
        timestamp_column: str = "timestamp",
    ) -> List[Bar]:
        """
        从 Parquet 文件加载 K 线数据

        读取 Parquet 文件，将数据转换为 NautilusTrader Bar 对象，并添加到引擎。

        Args:
            parquet_path: Parquet 文件路径
            bar_type: K 线类型定义
            instrument: 交易品种定义
            timestamp_column: 时间戳列名（默认 "timestamp"）

        Returns:
            List[Bar]: 加载的 K 线数据列表

        Raises:
            RuntimeError: 引擎未初始化时抛出
            FileNotFoundError: Parquet 文件不存在时抛出
            ValueError: 数据格式无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        parquet_path = Path(parquet_path)
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet 文件不存在: {parquet_path}")

        try:
            logger.info(f"开始从 Parquet 加载数据: {parquet_path}")

            # 读取 Parquet 文件
            df = pd.read_parquet(parquet_path)

            # 处理时间戳列
            if timestamp_column in df.columns:
                df[timestamp_column] = pd.to_datetime(df[timestamp_column])
                df = df.rename(columns={timestamp_column: "timestamp"})

            # 设置时间戳为索引
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

            # 确保必需的列存在
            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    raise ValueError(f"Parquet 文件缺少必需的列: {col}")

            # 使用 BarDataWrangler 转换数据
            wrangler = BarDataWrangler(bar_type, instrument)
            bars: List[Bar] = wrangler.process(df)

            # 添加数据到引擎
            self._engine.add_data(bars)
            self._data.extend(bars)

            # 缓存 BarType
            bar_type_str = str(bar_type)
            self._bar_types[bar_type_str] = bar_type

            logger.info(f"Parquet 数据加载完成: {len(bars)} 条 K 线")
            return bars

        except Exception as e:
            logger.error(f"从 Parquet 加载数据失败: {e}")
            raise RuntimeError(f"从 Parquet 加载数据失败: {e}") from e

    def add_strategy(self, strategy: Strategy) -> None:
        """
        添加策略到引擎

        将交易策略添加到回测引擎中。

        Args:
            strategy: 策略实例，必须继承自 nautilus_trader.trading.strategy.Strategy

        Raises:
            RuntimeError: 引擎未初始化时抛出
            ValueError: 策略无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not strategy:
            raise ValueError("策略不能为空")

        if not isinstance(strategy, Strategy):
            raise ValueError("策略必须是 Strategy 类的实例")

        try:
            # 添加策略到引擎
            self._engine.add_strategy(strategy)
            self._strategies.append(strategy)

            logger.debug(f"策略已添加: {strategy.id}")

        except Exception as e:
            logger.error(f"添加策略失败: {e}")
            raise RuntimeError(f"添加策略失败: {e}") from e

    def run_backtest(self) -> Dict[str, Any]:
        """
        运行回测

        执行完整的回测流程，处理所有历史数据并生成交易记录。

        Returns:
            Dict[str, Any]: 回测结果字典，包含:
                - trades: 交易记录列表
                - equity_curve: 权益曲线
                - metrics: 绩效指标
                - positions: 持仓记录
                - orders: 订单记录
                - account: 账户记录

        Raises:
            RuntimeError: 引擎未初始化或未添加策略时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not self._strategies:
            raise RuntimeError("未添加策略，请先调用 add_strategy()")

        if not self._data:
            raise RuntimeError("未加载数据，请先调用 load_data_from_csv() 或 load_data_from_parquet()")

        try:
            logger.info("开始执行回测...")

            # 运行回测
            self._engine.run()

            # 处理并返回结果
            results = self._process_results()

            logger.info("回测执行完成")
            return results

        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            raise RuntimeError(f"回测执行失败: {e}") from e

    def _process_results(self) -> Dict[str, Any]:
        """
        处理回测结果

        将 NautilusTrader 的回测结果转换为内部标准格式。

        Returns:
            Dict[str, Any]: 标准格式的回测结果
        """
        if not self._engine:
            return {}

        try:
            # 获取交易报告
            orders_df = self._engine.trader.generate_order_fills_report()
            positions_df = self._engine.trader.generate_positions_report()

            # 获取账户报告（使用第一个添加的交易所）
            account_df = None
            if self._venues:
                first_venue = list(self._venues.values())[0]
                account_df = self._engine.trader.generate_account_report(first_venue)

            # 转换为标准格式
            results = {
                "trades": self._convert_orders_to_trades(orders_df),
                "positions": self._convert_positions(positions_df),
                "account": self._convert_account(account_df),
                "metrics": self._calculate_metrics(positions_df, account_df),
                "equity_curve": self._build_equity_curve(account_df),
            }

            self._results = results
            return results

        except Exception as e:
            logger.error(f"处理回测结果失败: {e}")
            return {}

    def _convert_orders_to_trades(self, orders_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        将订单数据转换为交易记录格式

        Args:
            orders_df: 订单 DataFrame

        Returns:
            List[Dict[str, Any]]: 交易记录列表
        """
        if orders_df is None or orders_df.empty:
            return []

        trades = []
        for _, row in orders_df.iterrows():
            trade = {
                "order_id": str(row.get("order_id", "")),
                "instrument_id": str(row.get("instrument_id", "")),
                "side": str(row.get("side", "")),
                "quantity": float(row.get("quantity", 0)),
                "price": float(row.get("price", 0)),
                "timestamp": str(row.get("timestamp", "")),
            }
            trades.append(trade)

        return trades

    def _convert_positions(self, positions_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        将持仓数据转换为标准格式

        Args:
            positions_df: 持仓 DataFrame

        Returns:
            List[Dict[str, Any]]: 持仓记录列表
        """
        if positions_df is None or positions_df.empty:
            return []

        positions = []
        for _, row in positions_df.iterrows():
            # 处理 PnL 字符串格式（如 "1,234.56 USD"）
            pnl_raw = row.get("realized_pnl", "0")
            if isinstance(pnl_raw, str):
                pnl = float(pnl_raw.replace(" USD", "").replace(",", ""))
            else:
                pnl = float(pnl_raw)

            position = {
                "position_id": str(row.get("position_id", "")),
                "instrument_id": str(row.get("instrument_id", "")),
                "side": str(row.get("side", "")),
                "quantity": float(row.get("quantity", 0)),
                "avg_px_open": float(row.get("avg_px_open", 0)),
                "avg_px_close": float(row.get("avg_px_close", 0)),
                "realized_pnl": pnl,
            }
            positions.append(position)

        return positions

    def _convert_account(self, account_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """
        将账户数据转换为标准格式

        Args:
            account_df: 账户 DataFrame

        Returns:
            Dict[str, Any]: 账户信息字典
        """
        if account_df is None or account_df.empty:
            return {}

        # 获取最后一行作为最终账户状态
        last_row = account_df.iloc[-1]

        return {
            "balance": float(last_row.get("balance", 0)),
            "margin": float(last_row.get("margin", 0)),
            "equity": float(last_row.get("equity", 0)),
            "timestamp": str(last_row.get("timestamp", "")),
        }

    def _calculate_metrics(
        self,
        positions_df: Optional[pd.DataFrame],
        account_df: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        计算绩效指标

        Args:
            positions_df: 持仓 DataFrame
            account_df: 账户 DataFrame

        Returns:
            Dict[str, Any]: 绩效指标字典
        """
        if positions_df is None or positions_df.empty:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
            }

        # 提取 PnL 数值
        pnls = []
        for _, row in positions_df.iterrows():
            pnl_raw = row.get("realized_pnl", "0")
            if isinstance(pnl_raw, str):
                pnl = float(pnl_raw.replace(" USD", "").replace(",", ""))
            else:
                pnl = float(pnl_raw)
            pnls.append(pnl)

        pnls = [p for p in pnls if p != 0]  # 过滤掉零值

        if not pnls:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
            }

        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]

        total_pnl = sum(pnls)
        win_rate = len(winning_trades) / len(pnls) * 100 if pnls else 0

        profit_factor = 0.0
        if losing_trades:
            gross_profit = sum(winning_trades) if winning_trades else 0
            gross_loss = abs(sum(losing_trades))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # 计算总收益率
        initial_capital = self._config.get("initial_capital", 100000.0)
        total_return = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

        return {
            "total_return": round(total_return, 2),
            "sharpe_ratio": 0.0,  # 需要更复杂的计算
            "max_drawdown": 0.0,  # 需要从权益曲线计算
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_trades": len(pnls),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "total_pnl": round(total_pnl, 2),
        }

    def _build_equity_curve(self, account_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        构建权益曲线

        Args:
            account_df: 账户 DataFrame

        Returns:
            List[Dict[str, Any]]: 权益曲线数据点列表
        """
        if account_df is None or account_df.empty:
            return []

        equity_curve = []
        for _, row in account_df.iterrows():
            point = {
                "timestamp": str(row.get("timestamp", "")),
                "equity": float(row.get("equity", 0)),
                "balance": float(row.get("balance", 0)),
                "margin": float(row.get("margin", 0)),
            }
            equity_curve.append(point)

        return equity_curve

    def get_results(self) -> Dict[str, Any]:
        """
        获取回测结果

        返回最近一次回测的完整结果。

        Returns:
            Dict[str, Any]: 回测结果字典，包含:
                - total_return: 总收益率
                - sharpe_ratio: 夏普比率
                - max_drawdown: 最大回撤
                - win_rate: 胜率
                - profit_factor: 盈亏比
                - trades: 完整交易记录

        Raises:
            RuntimeError: 尚未执行回测时抛出
        """
        if not self._results:
            raise RuntimeError("尚未执行回测，请先调用 run_backtest()")

        return self._results

    def cleanup(self) -> None:
        """
        清理资源

        释放引擎占用的所有资源，包括:
        - 调用 NautilusTrader BacktestEngine.dispose() 释放资源
        - 关闭数据连接
        - 释放内存缓存
        - 重置内部状态

        此方法应在回测完成后调用，确保资源正确释放。
        """
        logger.info("开始清理 NautilusTrader 回测引擎资源...")

        # 调用 NautilusTrader 引擎的 dispose 方法
        if self._engine:
            try:
                self._engine.dispose()
                logger.debug("NautilusTrader BacktestEngine 已释放")
            except Exception as e:
                logger.warning(f"释放 BacktestEngine 时出错: {e}")

        # 重置所有状态
        self._engine = None
        self._engine_config = None
        self._venues.clear()
        self._instruments.clear()
        self._bar_types.clear()
        self._strategies.clear()
        self._data.clear()
        self._backtest_result = None

        # 调用基类的状态重置
        self._reset_state()

        logger.info("NautilusTrader 回测引擎资源清理完成")

    def get_venue(self, venue_name: str) -> Optional[Venue]:
        """
        获取已添加的交易所

        Args:
            venue_name: 交易所名称

        Returns:
            Optional[Venue]: 交易所标识符，如果不存在则返回 None
        """
        return self._venues.get(venue_name)

    def get_instrument(self, instrument_id: str) -> Optional[Instrument]:
        """
        获取已添加的交易品种

        Args:
            instrument_id: 交易品种ID

        Returns:
            Optional[Instrument]: 交易品种定义，如果不存在则返回 None
        """
        return self._instruments.get(instrument_id)

    def get_bar_type(self, bar_type_str: str) -> Optional[BarType]:
        """
        获取已定义的 BarType

        Args:
            bar_type_str: BarType 字符串表示

        Returns:
            Optional[BarType]: BarType 对象，如果不存在则返回 None
        """
        return self._bar_types.get(bar_type_str)

    def get_strategies(self) -> List[Strategy]:
        """
        获取已添加的策略列表

        Returns:
            List[Strategy]: 策略列表
        """
        return self._strategies.copy()

    def get_data_count(self) -> int:
        """
        获取已加载的数据条数

        Returns:
            int: 数据条数
        """
        return len(self._data)
