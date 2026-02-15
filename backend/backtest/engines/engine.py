# -*- coding: utf-8 -*-
"""
回测引擎实现

基于高性能交易引擎框架的回测引擎实现，提供事件驱动回测能力。

包含:
    - Engine: 回测引擎实现类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# 交易引擎核心导入
from nautilus_trader.backtest.node import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestNode,
    BacktestRunConfig,
    BacktestVenueConfig,
)
from nautilus_trader.config import ImportableStrategyConfig, LoggingConfig
from nautilus_trader.model import Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from .base import BacktestEngineBase, EngineType


class Engine(BacktestEngineBase):
    """
    回测引擎实现类

    基于高性能交易引擎框架的事件驱动回测引擎。
    支持多品种、多策略、复杂订单类型和精细的撮合模拟。

    Attributes:
        engine_type: 引擎类型标识为 DEFAULT
        node: BacktestNode 实例，用于执行回测
        catalog: ParquetDataCatalog 数据目录实例
        run_config: BacktestRunConfig 回测运行配置
        results: 回测结果缓存

    Example:
        >>> config = {
        ...     "initial_capital": 100000.0,
        ...     "start_date": "2023-01-01",
        ...     "end_date": "2023-12-31",
        ...     "symbols": ["BTCUSDT"],
        ...     "catalog_path": "/path/to/catalog",
        ...     "strategy_config": {...}
        ... }
        >>> engine = Engine(config)
        >>> engine.initialize()
        >>> results = engine.run_backtest()
        >>> engine.cleanup()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化回测引擎

        Args:
            config: 引擎配置字典，包含:
                - initial_capital: 初始资金
                - start_date: 回测开始日期
                - end_date: 回测结束日期
                - symbols: 交易品种列表
                - catalog_path: 数据目录路径
                - strategy_config: 策略配置
                - venue_config: 交易场所配置（可选）
                - log_level: 日志级别（可选，默认 INFO）
        """
        super().__init__(config)

        # 交易引擎核心组件
        self._node: Optional[BacktestNode] = None
        self._catalog: Optional[ParquetDataCatalog] = None
        self._run_config: Optional[BacktestRunConfig] = None
        self._engine_config: Optional[BacktestEngineConfig] = None
        self._venue_config: Optional[BacktestVenueConfig] = None
        self._data_config: Optional[BacktestDataConfig] = None

        # 回测结果
        self._backtest_results: Optional[List[Any]] = None
        self._engine_instance: Optional[Any] = None

        logger.debug("Engine 实例已创建")

    @property
    def engine_type(self) -> EngineType:
        """
        引擎类型属性

        Returns:
            EngineType: 返回 EngineType.DEFAULT
        """
        return EngineType.DEFAULT

    def initialize(self) -> None:
        """
        初始化回测引擎

        执行引擎启动前的准备工作，包括:
        - 验证配置有效性
        - 加载数据目录 (ParquetDataCatalog)
        - 创建交易场所配置 (BacktestVenueConfig)
        - 创建数据配置 (BacktestDataConfig)
        - 创建引擎配置 (BacktestEngineConfig)
        - 组装回测运行配置 (BacktestRunConfig)
        - 初始化 BacktestNode

        Raises:
            RuntimeError: 初始化失败时抛出
            ValueError: 配置参数无效时抛出
        """
        try:
            logger.info("开始初始化回测引擎...")

            # 验证配置
            if not self._validate_config():
                raise ValueError("引擎配置验证失败")

            # 加载数据目录
            self._setup_catalog()

            # 创建交易场所配置
            self._setup_venue_config()

            # 创建数据配置
            self._setup_data_config()

            # 创建引擎配置
            self._setup_engine_config()

            # 组装回测运行配置
            self._setup_run_config()

            # 初始化 BacktestNode
            self._node = BacktestNode(configs=[self._run_config])

            self._is_initialized = True
            logger.info("回测引擎初始化完成")

        except Exception as e:
            logger.error(f"高级引擎初始化失败: {e}")
            raise RuntimeError(f"引擎初始化失败: {e}") from e

    def _setup_catalog(self) -> None:
        """
        设置数据目录

        从配置中加载 ParquetDataCatalog，用于读取回测所需的历史数据。

        Raises:
            ValueError: 数据目录路径无效或目录不存在时抛出
        """
        catalog_path = self._config.get("catalog_path")
        if not catalog_path:
            raise ValueError("配置缺少必需参数: catalog_path")

        catalog_path = Path(catalog_path)
        if not catalog_path.exists():
            raise ValueError(f"数据目录不存在: {catalog_path}")

        self._catalog = ParquetDataCatalog(str(catalog_path))
        logger.debug(f"数据目录已加载: {catalog_path}")

    def _setup_venue_config(self) -> None:
        """
        设置交易场所配置

        创建 BacktestVenueConfig，配置模拟交易所的参数，包括:
        - 交易所名称
        - OMS 类型
        - 账户类型
        - 基础货币
        - 初始资金

        配置可从 self._config 中的 venue_config 覆盖，或使用默认值。
        """
        # 从配置中获取 venue 配置或使用默认值
        venue_config = self._config.get("venue_config", {})

        # 获取初始资金
        initial_capital = self._config.get("initial_capital", 100000.0)
        base_currency = venue_config.get("base_currency", "USD")

        self._venue_config = BacktestVenueConfig(
            name=venue_config.get("name", "SIM"),
            oms_type=venue_config.get("oms_type", "NETTING"),
            account_type=venue_config.get("account_type", "MARGIN"),
            base_currency=base_currency,
            starting_balances=[f"{initial_capital} {base_currency}"],
        )
        logger.debug(f"交易场所配置已创建: {self._venue_config.name}")

    def _setup_data_config(self) -> None:
        """
        设置数据配置

        创建 BacktestDataConfig，配置回测所需的数据参数，包括:
        - 数据目录路径
        - 数据类型（Bar、QuoteTick、TradeTick 等）
        - 交易品种 ID
        - 开始/结束时间

        Raises:
            ValueError: 配置缺少必需参数时抛出
        """
        from nautilus_trader.model.data import Bar

        catalog_path = self._config.get("catalog_path")
        symbols = self._config.get("symbols", [])
        start_date = self._config.get("start_date")
        end_date = self._config.get("end_date")

        if not symbols:
            raise ValueError("配置缺少必需参数: symbols")

        # 构建 instrument_id
        # 假设 symbol 格式为 "BTCUSDT"，需要转换为 "BTCUSDT.SIM" 格式
        instrument_id = f"{symbols[0]}.SIM"

        self._data_config = BacktestDataConfig(
            catalog_path=catalog_path,
            data_cls=Bar,  # 默认使用 K线数据
            instrument_id=instrument_id,
            start_time=start_date,
            end_time=end_date,
        )
        logger.debug(f"数据配置已创建: {instrument_id}")

    def _setup_engine_config(self) -> None:
        """
        设置引擎配置

        创建 BacktestEngineConfig，配置回测引擎的核心参数，包括:
        - 策略列表
        - 日志配置
        - 其他引擎级设置

        Raises:
            ValueError: 策略配置无效时抛出
        """
        strategy_config = self._config.get("strategy_config")
        if not strategy_config:
            raise ValueError("配置缺少必需参数: strategy_config")

        # 获取日志级别
        log_level = self._config.get("log_level", "INFO")

        # 构建策略配置列表
        strategies = self._build_strategy_configs(strategy_config)

        self._engine_config = BacktestEngineConfig(
            strategies=strategies,
            logging=LoggingConfig(log_level=log_level),
        )
        logger.debug(f"引擎配置已创建，包含 {len(strategies)} 个策略")

    def _build_strategy_configs(
        self, strategy_config: Dict[str, Any]
    ) -> List[ImportableStrategyConfig]:
        """
        构建策略配置列表

        将内部策略配置转换为交易引擎的 ImportableStrategyConfig。

        Args:
            strategy_config: 内部策略配置字典，包含:
                - strategy_path: 策略类路径（如 "module:ClassName"）
                - config_path: 策略配置类路径（可选）
                - params: 策略参数字典

        Returns:
            List[ImportableStrategyConfig]: 交易引擎策略配置列表

        Raises:
            ValueError: 策略配置格式无效时抛出
        """
        strategy_path = strategy_config.get("strategy_path")
        if not strategy_path:
            raise ValueError("策略配置缺少必需参数: strategy_path")

        # 如果 strategy_path 不包含冒号，假设是简单的策略名称
        if ":" not in strategy_path:
            strategy_path = f"__main__:{strategy_path}"

        config_path = strategy_config.get("config_path", f"{strategy_path}Config")
        if ":" not in config_path:
            config_path = f"__main__:{config_path}"

        params = strategy_config.get("params", {})

        # 添加 instrument_id 到参数（如果未提供）
        symbols = self._config.get("symbols", [])
        if symbols and "instrument_id" not in params:
            params["instrument_id"] = f"{symbols[0]}.SIM"

        importable_config = ImportableStrategyConfig(
            strategy_path=strategy_path,
            config_path=config_path,
            config=params,
        )

        return [importable_config]

    def _setup_run_config(self) -> None:
        """
        组装回测运行配置

        将引擎配置、场所配置和数据配置组装为 BacktestRunConfig。

        Raises:
            RuntimeError: 前置配置未初始化时抛出
        """
        if not all([self._engine_config, self._venue_config, self._data_config]):
            raise RuntimeError("前置配置未初始化")

        self._run_config = BacktestRunConfig(
            engine=self._engine_config,
            venues=[self._venue_config],
            data=[self._data_config],
        )
        logger.debug("回测运行配置已组装完成")

    def run_backtest(self) -> Dict[str, Any]:
        """
        执行回测

        运行完整的回测流程，处理所有历史数据并生成交易记录。

        Returns:
            Dict[str, Any]: 回测结果字典，包含:
                - trades: 交易记录列表
                - equity_curve: 权益曲线
                - metrics: 绩效指标
                - positions: 持仓记录
                - orders: 订单记录
                - account: 账户记录

        Raises:
            RuntimeError: 回测执行失败时抛出
        """
        if not self._is_initialized:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not self._node:
            raise RuntimeError("BacktestNode 未初始化")

        try:
            logger.info("开始执行回测...")

            # 执行回测
            self._backtest_results = self._node.run()

            # 获取引擎实例用于后续查询
            if self._run_config:
                self._engine_instance = self._node.get_engine(self._run_config.id)

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

        将交易引擎的回测结果转换为内部标准格式。

        Returns:
            Dict[str, Any]: 标准格式的回测结果
        """
        if not self._engine_instance:
            return {}

        # 获取交易报告
        orders_df = self._engine_instance.trader.generate_order_fills_report()
        positions_df = self._engine_instance.trader.generate_positions_report()
        account_df = self._engine_instance.trader.generate_account_report(Venue("SIM"))

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

    def _convert_orders_to_trades(self, orders_df: Any) -> List[Dict[str, Any]]:
        """
        将订单数据转换为交易记录格式

        Args:
            orders_df: 交易引擎订单 DataFrame

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

    def _convert_positions(self, positions_df: Any) -> List[Dict[str, Any]]:
        """
        将持仓数据转换为标准格式

        Args:
            positions_df: 交易引擎持仓 DataFrame

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

    def _convert_account(self, account_df: Any) -> Dict[str, Any]:
        """
        将账户数据转换为标准格式

        Args:
            account_df: 交易引擎账户 DataFrame

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
        self, positions_df: Any, account_df: Any
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

    def _build_equity_curve(self, account_df: Any) -> List[Dict[str, Any]]:
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
        - 关闭数据连接
        - 释放内存缓存
        - 重置内部状态

        此方法应在回测完成后调用，确保资源正确释放。
        """
        logger.info("开始清理高级引擎资源...")

        # 释放 BacktestNode
        if self._node:
            try:
                # 交易引擎的 BacktestNode 没有显式的关闭方法
                # 但我们需要释放引用以便垃圾回收
                self._node = None
                logger.debug("BacktestNode 已释放")
            except Exception as e:
                logger.warning(f"释放 BacktestNode 时出错: {e}")

        # 释放数据目录
        if self._catalog:
            self._catalog = None
            logger.debug("数据目录已释放")

        # 重置状态
        self._reset_state()

        logger.info("高级引擎资源清理完成")

    def _reset_state(self) -> None:
        """
        重置引擎状态（内部方法）

        将引擎状态重置为初始状态，便于重新运行回测。
        """
        self._is_initialized = False
        self._results = {}
        self._backtest_results = None
        self._engine_instance = None
        self._run_config = None
        self._engine_config = None
        self._venue_config = None
        self._data_config = None
        logger.debug("引擎状态已重置")

    def get_node(self) -> Optional[BacktestNode]:
        """
        获取 BacktestNode 实例

        提供对底层 BacktestNode 的访问，用于高级用法。

        Returns:
            Optional[BacktestNode]: BacktestNode 实例，如果未初始化则返回 None
        """
        return self._node

    def get_engine_instance(self) -> Optional[Any]:
        """
        获取交易引擎实例

        提供对底层 BacktestEngine 的访问，用于查询详细回测数据。

        Returns:
            Optional[Any]: BacktestEngine 实例，如果未执行回测则返回 None
        """
        return self._engine_instance
