# -*- coding: utf-8 -*-
"""
Legacy 回测引擎适配器

包装现有的 backtest/service.py 中的回测逻辑，
提供与 BacktestEngineBase 兼容的接口。
"""

from typing import Any, Dict, Optional
from loguru import logger

from .base import BacktestEngineBase
from backtest.config.settings import EngineType


class LegacyEngine(BacktestEngineBase):
    """
    Legacy 回测引擎适配器

    包装现有的 BacktestService 回测逻辑，提供统一的引擎接口。
    使用 backtesting.py 库的 Backtest 类执行回测。

    Attributes:
        engine_type: 引擎类型标识为 LEGACY
        config: 引擎配置字典
        is_initialized: 引擎是否已初始化
        _service: BacktestService 实例
        _strategy_config: 策略配置
        _backtest_config: 回测配置
        _last_result: 最后一次回测结果
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Legacy 回测引擎

        Args:
            config: 引擎配置字典，包含回测参数、初始资金等
        """
        super().__init__(config)
        self._service = None
        self._strategy_config: Dict[str, Any] = {}
        self._backtest_config: Dict[str, Any] = {}
        self._last_result: Optional[Dict[str, Any]] = None
        self._task_id: Optional[str] = None

    @property
    def engine_type(self) -> EngineType:
        """
        引擎类型属性

        Returns:
            EngineType: 返回 LEGACY 引擎类型标识
        """
        return EngineType.LEGACY

    def _validate_config(self) -> bool:
        """
        验证配置有效性（重写父类方法）

        检查配置字典是否包含 Legacy 引擎必需的参数。

        Returns:
            bool: 配置是否有效
        """
        # 提取回测配置
        backtest_config = self._config.get("backtest_config", {})

        # 检查必需的回测参数
        required_keys = ['symbols']  # Legacy 引擎只需要 symbols
        for key in required_keys:
            if key not in backtest_config:
                # 兼容单货币对配置
                if key == 'symbols' and 'symbol' in backtest_config:
                    continue
                logger.error(f"配置缺少必需参数: {key}")
                return False

        # 检查策略配置
        strategy_config = self._config.get("strategy_config", {})
        if not strategy_config.get("strategy_name"):
            logger.error("配置缺少 strategy_name")
            return False

        return True

    def initialize(self) -> None:
        """
        初始化回测引擎

        执行引擎启动前的准备工作，包括：
        - 创建 BacktestService 实例
        - 验证配置有效性
        - 设置策略配置和回测配置

        Raises:
            RuntimeError: 初始化失败时抛出
        """
        try:
            logger.info("初始化 Legacy 回测引擎...")

            # 验证配置
            if not self._validate_config():
                raise RuntimeError("配置验证失败，缺少必需参数")

            # 导入并创建 BacktestService 实例
            # 在函数内部导入以避免循环依赖
            from backtest.service import BacktestService
            self._service = BacktestService()

            # 提取策略配置和回测配置
            self._strategy_config = self._config.get("strategy_config", {})
            self._backtest_config = self._config.get("backtest_config", {})

            # 验证策略配置
            if not self._strategy_config.get("strategy_name"):
                raise RuntimeError("策略配置中缺少 strategy_name")

            # 验证回测配置
            if not self._backtest_config.get("symbols"):
                # 兼容单货币对配置
                if self._backtest_config.get("symbol"):
                    self._backtest_config["symbols"] = [self._backtest_config["symbol"]]
                else:
                    raise RuntimeError("回测配置中缺少 symbols 或 symbol")

            self._is_initialized = True
            logger.info("Legacy 回测引擎初始化完成")

        except Exception as e:
            logger.error(f"Legacy 回测引擎初始化失败: {e}")
            logger.exception(e)
            raise RuntimeError(f"初始化失败: {str(e)}")

    def run_backtest(self) -> Dict[str, Any]:
        """
        执行回测

        使用 BacktestService 运行完整的回测流程，处理所有历史数据并生成交易记录。

        Returns:
            Dict[str, Any]: 回测结果字典，包含：
                - task_id: 回测任务ID
                - status: 回测状态
                - message: 状态消息
                - successful_currencies: 成功回测的货币对列表
                - failed_currencies: 失败回测的货币对列表
                - results: 详细的回测结果

        Raises:
            RuntimeError: 回测执行失败时抛出
        """
        if not self._is_initialized:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if self._service is None:
            raise RuntimeError("BacktestService 未创建")

        try:
            logger.info("开始执行 Legacy 回测...")

            # 调用 BacktestService 执行回测
            result = self._service.run_backtest(
                strategy_config=self._strategy_config,
                backtest_config=self._backtest_config
            )

            # 保存结果
            self._last_result = result
            self._task_id = result.get("task_id")

            logger.info(f"Legacy 回测执行完成，任务ID: {self._task_id}")
            return result

        except Exception as e:
            logger.error(f"Legacy 回测执行失败: {e}")
            logger.exception(e)
            raise RuntimeError(f"回测执行失败: {str(e)}")

    def get_results(self) -> Dict[str, Any]:
        """
        获取回测结果

        返回最近一次回测的完整结果。

        Returns:
            Dict[str, Any]: 回测结果字典，包含：
                - total_return: 总收益率
                - sharpe_ratio: 夏普比率
                - max_drawdown: 最大回撤
                - win_rate: 胜率
                - profit_factor: 盈亏比
                - trades: 完整交易记录

        Raises:
            RuntimeError: 尚未执行回测时抛出
        """
        if self._last_result is None:
            raise RuntimeError("尚未执行回测，请先调用 run_backtest()")

        # 返回保存的结果
        return self._last_result

    def cleanup(self) -> None:
        """
        清理资源

        释放引擎占用的所有资源，包括：
        - 关闭数据连接
        - 释放内存缓存
        - 重置内部状态

        此方法应在回测完成后调用，确保资源正确释放。
        """
        try:
            logger.info("清理 Legacy 回测引擎资源...")

            # 释放 BacktestService 引用
            self._service = None

            # 重置内部状态
            self._strategy_config = {}
            self._backtest_config = {}
            self._last_result = None
            self._task_id = None

            # 重置初始化状态
            self._is_initialized = False

            logger.info("Legacy 回测引擎资源已清理")

        except Exception as e:
            logger.warning(f"清理 Legacy 回测引擎资源时出错: {e}")
            logger.exception(e)

    def set_strategy_config(self, strategy_config: Dict[str, Any]) -> None:
        """
        设置策略配置

        Args:
            strategy_config: 策略配置字典，包含：
                - strategy_name: 策略名称
                - 其他策略参数
        """
        self._strategy_config = strategy_config
        logger.debug(f"策略配置已设置: {strategy_config.get('strategy_name')}")

    def set_backtest_config(self, backtest_config: Dict[str, Any]) -> None:
        """
        设置回测配置

        Args:
            backtest_config: 回测配置字典，包含：
                - symbols: 货币对列表
                - interval: 时间周期
                - start_time: 开始时间
                - end_time: 结束时间
                - initial_cash: 初始资金
                - commission: 手续费率
        """
        self._backtest_config = backtest_config
        logger.debug(f"回测配置已设置: {backtest_config.get('symbols')}")

    def analyze_result(self, backtest_id: str) -> Dict[str, Any]:
        """
        分析回测结果

        使用 BacktestService 分析指定的回测结果。

        Args:
            backtest_id: 回测ID

        Returns:
            Dict[str, Any]: 分析结果
        """
        if self._service is None:
            from backtest.service import BacktestService
            self._service = BacktestService()

        return self._service.analyze_backtest(backtest_id)

    def stop_backtest(self, task_id: str) -> Dict[str, Any]:
        """
        终止回测任务

        Args:
            task_id: 回测任务ID

        Returns:
            Dict[str, Any]: 终止结果
        """
        if self._service is None:
            from backtest.service import BacktestService
            self._service = BacktestService()

        return self._service.stop_backtest(task_id)
