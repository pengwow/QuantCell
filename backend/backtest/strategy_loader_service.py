"""
策略加载服务模块

从策略文件加载和实例化策略类，支持多种策略类型：
- 策略接口（StrategyBase）
- 事件驱动策略（StrategyAdapter/axon_quantStrategy）
- 传统回测策略

提供统一的策略加载接口，支持单品种和多品种场景。
"""

import importlib
import sys
from typing import Any, Dict, Optional
from pathlib import Path
from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class StrategyLoadError(Exception):
    """策略加载异常"""
    pass


class StrategyLoaderService:
    """
    策略加载服务
    
    负责从策略文件中查找、加载和实例化策略类。
    支持多种策略基类和配置模式。
    
    使用示例：
        # 加载事件驱动策略（多品种）
        strategy = StrategyLoaderService.load_event_strategy_multi(
            "sma_cross_axon",
            params={"fast_period": 10, "slow_period": 30},
            bar_types={"BTCUSDT": bar_type},
            instruments={"BTCUSDT": instrument}
        )
        
        # 加载默认引擎策略
        strategy = StrategyLoaderService.load_strategy("sma_cross_strategy", params={})
    """
    
    @staticmethod
    def load_strategy(strategy_name: str, strategy_params: dict):
        """
        加载默认引擎使用的策略
        
        Args:
            strategy_name: 策略名称（文件名，不含.py后缀）
            strategy_params: 策略参数字典
            
        Returns:
            Strategy: 策略实例
            
        Raises:
            StrategyLoadError: 当策略加载失败时
        """
        try:
            from pathlib import Path
            
            backend_path = Path(__file__).resolve().parent.parent
            strategies_dir = backend_path / 'strategies'
            
            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))
            
            if strategy_name in sys.modules:
                del sys.modules[strategy_name]
            
            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                raise StrategyLoadError(f"策略文件不存在: {strategy_file}")
            
            module = importlib.import_module(strategy_name)
            
            from strategy.core import StrategyBase
            
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj != StrategyBase:
                    strategy_class = obj
                    logger.info(f"找到默认引擎策略类: {name}")
                    
                    if hasattr(strategy_class, 'model_fields'):
                        config_class = getattr(module, f"{strategy_name}Config", None)
                        if config_class:
                            config = config_class(**strategy_params)
                            return strategy_class(config)
                    
                    return strategy_class(**strategy_params)
            
            raise StrategyLoadError(f"在模块 {strategy_name} 中找不到策略类")
            
        except Exception as e:
            logger.error(f"加载默认引擎策略失败: {e}")
            raise StrategyLoadError(f"加载策略失败: {e}") from e
    
    @staticmethod
    def load_event_strategy(
        strategy_name: str,
        strategy_params: dict,
        bar_type,
        instrument_id
    ):
        """
        加载事件驱动策略（单品种版本）
        
        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            bar_type: BarType对象
            instrument_id: InstrumentId对象
            
        Returns:
            Strategy: 策略实例或None
        """
        try:
            backend_path = Path(__file__).resolve().parent.parent
            strategies_dir = backend_path / 'strategies'
            
            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))
            
            if strategy_name in sys.modules:
                del sys.modules[strategy_name]
            
            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.info(f"策略文件不存在: {strategy_file}")
                return None
            
            module = importlib.import_module(strategy_name)
            
            strategy_class = None
            config_class = None
            
            EventDrivenStrategy = None
            EventDrivenStrategyConfig = None
            
            try:
                from backtest.strategies.strategy import Strategy, StrategyConfig
                EventDrivenStrategy = Strategy
                EventDrivenStrategyConfig = StrategyConfig
            except ImportError:
                try:
                    from backend.backtest.strategies.strategy import Strategy, StrategyConfig
                    EventDrivenStrategy = Strategy
                    EventDrivenStrategyConfig = StrategyConfig
                except ImportError:
                    from axon_quant.trading.strategy import Strategy
                    EventDrivenStrategy = Strategy
                    EventDrivenStrategyConfig = None
            
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type):
                    if issubclass(obj, EventDrivenStrategy) and obj != EventDrivenStrategy:
                        strategy_class = obj
                        logger.info(f"找到策略类: {name}")
                    elif EventDrivenStrategyConfig and issubclass(obj, EventDrivenStrategyConfig) and obj != EventDrivenStrategyConfig:
                        config_class = obj
                        logger.info(f"找到配置类: {name}")
            
            if strategy_class is None:
                logger.info(f"在模块 {strategy_name} 中找不到事件驱动策略类")
                return None
            
            if config_class:
                config_params = strategy_params.copy()
                config_params['instrument_ids'] = [instrument_id]
                config_params['bar_types'] = [bar_type]
                config = config_class(**config_params)
                strategy = strategy_class(config)
            else:
                strategy_params['instrument_ids'] = [instrument_id]
                strategy_params['bar_types'] = [bar_type]
                strategy = strategy_class(**strategy_params)
            
            logger.info(f"成功加载事件驱动策略: {strategy_class.__name__}")
            return strategy
            
        except Exception as e:
            logger.error(f"加载事件驱动策略失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def load_event_strategy_multi(
        strategy_name: str,
        strategy_params: dict,
        bar_types: dict,
        instruments: dict
    ):
        """
        加载支持多品种的事件驱动策略
        
        支持两种策略类型：
        1. 策略接口（StrategyBase）：使用 StrategyAdapter 包装
        2. 传统策略接口（Strategy/StrategyAdapter）：直接使用
        
        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            bar_types: 品种到BarType的映射字典
            instruments: 品种到Instrument的映射字典
            
        Returns:
            Strategy: 策略实例或None
        """
        try:
            backend_path = Path(__file__).resolve().parent.parent
            strategies_dir = backend_path / 'strategies'
            
            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))
            
            if strategy_name in sys.modules:
                del sys.modules[strategy_name]
            
            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.info(f"策略文件不存在: {strategy_file}")
                return None
            
            module = importlib.import_module(strategy_name)
            
            strategy_class = None
            config_class = None
            is_core_strategy = False
            
            StrategyBase = None
            StrategyConfig = None
            
            try:
                from strategy.core import StrategyBase as CoreStrategyBase, StrategyConfig as CoreStrategyConfig
                StrategyBase = CoreStrategyBase
                StrategyConfig = CoreStrategyConfig
            except ImportError as e:
                logger.error(f"导入 strategy.core 失败: {e}")
                StrategyBase = None
                StrategyConfig = None
            
            EventDrivenStrategy = None
            EventDrivenStrategyConfig = None
            
            try:
                from backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig as AdapterStrategyConfig
                EventDrivenStrategy = StrategyAdapter
                EventDrivenStrategyConfig = AdapterStrategyConfig
            except ImportError as e:
                try:
                    from backend.backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig as AdapterStrategyConfig
                    EventDrivenStrategy = StrategyAdapter
                    EventDrivenStrategyConfig = AdapterStrategyConfig
                except ImportError as e:
                    logger.error(f"导入 backtest.strategies.strategy_adapter 失败: {e}")
                    try:
                        from axon_quant.trading.strategy import Strategy
                        EventDrivenStrategy = Strategy
                    except ImportError:
                        EventDrivenStrategy = object
                    EventDrivenStrategyConfig = None
            
            try:
                from axon_quant.trading.strategy import Strategy as axon_quantStrategy
                from axon_quant.trading.config import StrategyConfig as axon_quantStrategyConfig
            except ImportError:
                axon_quantStrategy = object
                axon_quantStrategyConfig = None
            
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type):
                    if StrategyBase and issubclass(obj, StrategyBase) and obj != StrategyBase:
                        strategy_class = obj
                        is_core_strategy = True
                        logger.info(f"找到策略类(接口): {name}")
                    elif issubclass(obj, EventDrivenStrategy) and obj != EventDrivenStrategy:
                        strategy_class = obj
                        is_core_strategy = False
                        logger.info(f"找到策略类: {name}")
                    elif issubclass(obj, axon_quantStrategy) and obj != axon_quantStrategy:
                        strategy_class = obj
                        is_core_strategy = False
                        logger.info(f"找到策略类(axon_quant): {name}")
                    
                    if StrategyConfig and issubclass(obj, StrategyConfig) and obj != StrategyConfig:
                        config_class = obj
                        logger.info(f"找到配置类: {name}")
                    elif EventDrivenStrategyConfig and issubclass(obj, EventDrivenStrategyConfig) and obj != EventDrivenStrategyConfig:
                        config_class = obj
                        logger.info(f"找到配置类: {name}")
                    elif issubclass(obj, axon_quantStrategyConfig) and obj != axon_quantStrategyConfig:
                        config_class = obj
                        logger.info(f"找到配置类(axon_quant): {name}")
            
            if strategy_class is None:
                logger.info(f"在模块 {strategy_name} 中找不到策略类")
                return None
            
            instrument_ids_list = []
            for inst in instruments.values():
                instrument_ids_list.append(inst.id)
            bar_types_list = list(bar_types.values())
            
            config = None
            if config_class:
                config_params = strategy_params.copy()
                
                config_param_names = StrategyLoaderService._get_class_param_names(config_class)
                
                if 'instrument_ids' in config_param_names:
                    config_params['instrument_ids'] = instrument_ids_list
                elif 'instrument_id' in config_param_names:
                    config_params['instrument_id'] = instrument_ids_list[0] if instrument_ids_list else None
                
                if 'bar_types' in config_param_names:
                    config_params['bar_types'] = bar_types_list
                elif 'bar_type' in config_param_names:
                    config_params['bar_type'] = bar_types_list[0] if bar_types_list else None
                
                config = config_class(**config_params)
                user_strategy = strategy_class(config)
            else:
                strategy_params_copy = strategy_params.copy()
                
                strategy_param_names = StrategyLoaderService._get_class_param_names(strategy_class)
                
                if 'instrument_ids' in strategy_param_names:
                    strategy_params_copy['instrument_ids'] = instrument_ids_list
                elif 'instrument_id' in strategy_param_names:
                    strategy_params_copy['instrument_id'] = instrument_ids_list[0] if instrument_ids_list else None
                
                if 'bar_types' in strategy_param_names:
                    strategy_params_copy['bar_types'] = bar_types_list
                elif 'bar_type' in strategy_param_names:
                    strategy_params_copy['bar_type'] = bar_types_list[0] if bar_types_list else None
                
                user_strategy = strategy_class(**strategy_params_copy)
            
            if is_core_strategy:
                logger.info(f"检测到策略接口，创建回测适配策略")
                strategy = StrategyLoaderService._create_backtest_adapter(
                    user_strategy, config, strategy_class, bar_types_list, instrument_ids_list
                )
            else:
                strategy = user_strategy
                logger.info(f"成功加载事件驱动策略: {strategy_class.__name__}（支持 {len(instruments)} 个品种）")
            
            return strategy
            
        except Exception as e:
            logger.error(f"加载事件驱动策略失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def _get_class_param_names(cls) -> list:
        """获取类的构造函数参数名列表"""
        param_names = []
        
        if hasattr(cls, 'model_fields'):
            param_names = list(cls.model_fields.keys())
        elif hasattr(cls, '__fields__'):
            param_names = list(cls.__fields__.keys())
        elif hasattr(cls, '__annotations__'):
            param_names = list(cls.__annotations__.keys())
        else:
            import inspect
            sig = inspect.signature(cls.__init__)
            param_names = list(sig.parameters.keys())
        
        return param_names
    
    @staticmethod
    def _create_backtest_adapter(
        user_strategy,
        config,
        user_strategy_class,
        bar_types_list,
        instrument_ids_list
    ):
        """
        创建回测适配器策略（包装策略接口）
        
        当用户策略继承自 StrategyBase 时，需要使用 StrategyAdapter 进行包装，
        使其兼容事件驱动引擎。
        """
        from backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig as AdapterStrategyConfig
        
        config_to_use = None
        if config is not None:
            config_to_use = config
        elif hasattr(user_strategy, '_config') and user_strategy._config is not None:
            config_to_use = user_strategy._config
        elif hasattr(user_strategy, 'config') and user_strategy.config is not None:
            config_to_use = user_strategy.config
        
        if config_to_use is None:
            raise ValueError("无法找到有效的策略配置对象")
        
        if isinstance(config_to_use, AdapterStrategyConfig):
            adapter_config = config_to_use
        else:
            adapter_config = AdapterStrategyConfig(
                instrument_ids=config_to_use.instrument_ids,
                bar_types=config_to_use.bar_types,
                trade_size=config_to_use.trade_size,
                log_level=config_to_use.log_level,
            )
        
        class BacktestStrategyAdapter(StrategyAdapter, user_strategy_class):
            """回测用的策略适配器"""
            
            def __init__(self, adapter_config, user_strategy_instance):
                StrategyAdapter.__init__(self, adapter_config)
                self._config = user_strategy_instance._config
                self._strategy_is_running = False
                self.bars_processed = 0
                self.start_time = None
                self.end_time = None
                self._init_user_strategy_state(self._config)
                self._user_strategy_instance = user_strategy_instance
            
            def _init_user_strategy_state(self, config):
                self.prices = {}
                self.fast_sma = {}
                self.slow_sma = {}
                self.prev_fast_sma = {}
                self.prev_slow_sma = {}
                for instrument_id in config.instrument_ids:
                    self.prices[instrument_id] = []
                    self.fast_sma[instrument_id] = 0.0
                    self.slow_sma[instrument_id] = 0.0
                    self.prev_fast_sma[instrument_id] = 0.0
                    self.prev_slow_sma[instrument_id] = 0.0
            
            def on_start(self) -> None:
                StrategyAdapter.on_start(self)
                user_strategy_class.on_start(self)
            
            def on_bar(self, bar) -> None:
                self.bars_processed += 1
                unified_bar = self._to_unified_bar(bar)
                user_strategy_class.on_bar(self, unified_bar)
            
            def on_stop(self) -> None:
                user_strategy_class.on_stop(self)
                StrategyAdapter.on_stop(self)
        
        strategy = BacktestStrategyAdapter(adapter_config, user_strategy)
        logger.info(f"成功加载策略: {user_strategy_class.__name__}（支持 {len(instrument_ids_list)} 个品种）")
        
        return strategy
