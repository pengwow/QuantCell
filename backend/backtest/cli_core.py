# -*- coding: utf-8 -*-
"""
回测CLI核心逻辑模块

提供回测CLI的核心功能，包括：
- 数据准备（检查完整性+自动下载）
- 策略加载
- 回测执行
- 结果分析
- 系统配置读取
"""

import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

# 添加策略目录到路径
backend_path = Path(__file__).resolve().parent.parent
strategies_dir = backend_path / 'strategies'
if str(strategies_dir) not in sys.path:
    sys.path.insert(0, str(strategies_dir))

from backtest.progress import ConsoleProgressBar, ProgressTracker
from backtest.result_analysis import output_results
from strategy.core import StrategyBase
from strategy.adapters import VectorBacktestAdapter, PortfolioBacktestAdapter
from utils.time_parser import parse_time_range, datetime_to_timestamp
from utils.validation import parse_symbols, parse_timeframes


class DownloadFailureType(Enum):
    """下载失败类型"""
    NO_DATA_AVAILABLE = "no_data_available"  # 数据源无可用数据
    NETWORK_ERROR = "network_error"          # 网络错误
    TIMEOUT = "timeout"                      # 超时
    UNKNOWN = "unknown"                      # 未知错误


@dataclass
class DataDownloadResult:
    """数据下载结果"""
    symbol: str
    timeframe: str
    success: bool
    failure_type: Optional[DownloadFailureType] = None
    failure_reason: Optional[str] = None
    data: Optional[pd.DataFrame] = None


class DataPreparationError(Exception):
    """数据准备异常"""
    pass


class StrategyLoadError(Exception):
    """策略加载异常"""
    pass


class BacktestExecutionError(Exception):
    """回测执行异常"""
    pass


class CLICore:
    """CLI核心逻辑类"""

    def __init__(self, verbose: bool = False, detail: bool = False, standalone_mode: bool = True):
        """
        初始化CLI核心

        参数：
            verbose: 是否显示详细日志
            detail: 是否显示详细交易输出（买入/卖出/持仓更新等）
            standalone_mode: 是否使用独立模式（不依赖FastAPI服务）
        """
        self.verbose = verbose
        self.detail = detail
        self.standalone_mode = standalone_mode
        self.results_dir = backend_path / 'backtest' / 'results'
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化独立下载器
        if standalone_mode:
            from backtest.data_downloader import BacktestDataDownloader
            self.downloader = BacktestDataDownloader(standalone_mode=True)
        
    def prepare_data(
        self,
        symbols: List[str],
        timeframes: List[str],
        time_range: Optional[str],
        trading_mode: str,
        auto_download: bool = True,
        show_progress: bool = True
    ) -> Tuple[Dict[str, pd.DataFrame], List[DataDownloadResult]]:
        """
        准备回测数据，自动检查完整性并下载缺失数据
        
        参数：
            symbols: 货币对列表
            timeframes: 时间周期列表
            time_range: 时间范围字符串（YYYYMMDD-YYYYMMDD）
            trading_mode: 交易模式（spot/futures/perpetual）
            auto_download: 是否自动下载缺失数据
            show_progress: 是否显示进度
            
        返回：
            Tuple[Dict[str, pd.DataFrame], List[DataDownloadResult]]: 
                (成功加载的数据字典, 所有下载结果列表)
            
        异常：
            DataPreparationError: 数据准备失败
        """
        from backtest.data_integrity import DataIntegrityChecker
        
        # 解析时间范围
        start_date, end_date = parse_time_range(time_range)
        
        # 初始化检查器和下载器
        checker = DataIntegrityChecker()
        
        # 使用独立下载器（如果已初始化）
        if not hasattr(self, 'downloader') or self.downloader is None:
            from backtest.data_downloader import BacktestDataDownloader
            self.downloader = BacktestDataDownloader(standalone_mode=self.standalone_mode)
        
        data_dict = {}
        download_results: List[DataDownloadResult] = []
        total_tasks = len(symbols) * len(timeframes)
        current_task = 0
        
        # 创建进度条
        progress_bar = None
        if show_progress:
            progress_bar = ConsoleProgressBar(total=total_tasks, desc="数据准备")
        
        try:
            for symbol in symbols:
                for timeframe in timeframes:
                    current_task += 1
                    key = f"{symbol}_{timeframe}"
                    
                    if show_progress and progress_bar:
                        progress_bar.update(0, f"检查 {key}")
                    else:
                        logger.info(f"[{current_task}/{total_tasks}] 准备数据: {key}")
                    
                    try:
                        # 检查数据完整性
                        if start_date and end_date:
                            integrity_result = checker.check_data_completeness(
                                symbol=symbol,
                                interval=timeframe,
                                start_time=start_date,
                                end_time=end_date,
                                market_type='crypto',
                                crypto_type=trading_mode
                            )
                            
                            # 如果数据不完整且允许自动下载
                            if not integrity_result.is_complete and auto_download:
                                if show_progress and progress_bar:
                                    progress_bar.update(0, f"下载 {key} 缺失数据...")
                                else:
                                    logger.info(f"  发现数据缺失，开始下载...")
                                
                                download_success, _ = self.downloader.ensure_data_complete(
                                    symbol=symbol,
                                    interval=timeframe,
                                    start_time=start_date,
                                    end_time=end_date,
                                    market_type='crypto',
                                    crypto_type=trading_mode
                                )
                                
                                if not download_success:
                                    logger.warning(f"  警告: {key} 数据下载失败或仍不完整")
                        
                        # 从数据库加载数据
                        df = self._load_klines_from_db(
                            symbol=symbol,
                            timeframe=timeframe,
                            start_date=start_date,
                            end_date=end_date,
                            trading_mode=trading_mode
                        )
                        
                        if df is not None and not df.empty:
                            data_dict[key] = df
                            download_results.append(DataDownloadResult(
                                symbol=symbol,
                                timeframe=timeframe,
                                success=True,
                                data=df
                            ))
                            logger.info(f"  ✓ 成功加载 {key}: {len(df)} 条数据")
                        else:
                            # 数据为空，判断失败类型
                            failure_type = self._determine_failure_type(symbol, trading_mode)
                            failure_reason = f"无法获取 {symbol} {timeframe} 的数据"
                            
                            if failure_type == DownloadFailureType.NO_DATA_AVAILABLE:
                                failure_reason = f"数据源无可用数据: {symbol}"
                                logger.warning(f"  ⚠️ {failure_reason}")
                            else:
                                logger.warning(f"  ✗ 未找到 {key} 的数据")
                            
                            download_results.append(DataDownloadResult(
                                symbol=symbol,
                                timeframe=timeframe,
                                success=False,
                                failure_type=failure_type,
                                failure_reason=failure_reason
                            ))
                        
                    except Exception as e:
                        # 处理异常
                        failure_type = DownloadFailureType.UNKNOWN
                        failure_reason = str(e)
                        
                        download_results.append(DataDownloadResult(
                            symbol=symbol,
                            timeframe=timeframe,
                            success=False,
                            failure_type=failure_type,
                            failure_reason=failure_reason
                        ))
                        logger.error(f"  ✗ 处理 {key} 时发生错误: {e}")
                    
                    if show_progress and progress_bar:
                        progress_bar.update(1)
            
            if show_progress and progress_bar:
                progress_bar.finish("数据准备完成")
            
            return data_dict, download_results
            
        except Exception as e:
            raise DataPreparationError(f"数据准备失败: {e}")
    
    def _load_klines_from_db(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        trading_mode: str
    ) -> Optional[pd.DataFrame]:
        """
        从数据库加载K线数据
        
        参数：
            symbol: 货币对
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
            trading_mode: 交易模式
            
        返回：
            Optional[pd.DataFrame]: K线数据DataFrame
        """
        from collector.db.connection import get_db_connection
        from collector.db.models import CryptoSpotKline, CryptoFutureKline
        
        try:
            conn = get_db_connection()
            
            # 标准化symbol格式（去除/）
            normalized_symbol = symbol.replace('/', '')
            
            # 选择数据表
            if trading_mode == 'spot':
                KlineModel = CryptoSpotKline
            elif trading_mode in ['futures', 'perpetual']:
                KlineModel = CryptoFutureKline
            else:
                raise ValueError(f"不支持的交易模式: {trading_mode}")
            
            # 构建查询条件
            conditions = f"symbol = '{normalized_symbol}' AND interval = '{timeframe}'"
            if start_date:
                start_timestamp = datetime_to_timestamp(start_date)
                conditions += f" AND CAST(timestamp AS INTEGER) >= {start_timestamp}"
            if end_date:
                end_timestamp = datetime_to_timestamp(end_date)
                conditions += f" AND CAST(timestamp AS INTEGER) <= {end_timestamp}"
            
            # 生成SQL
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {KlineModel.__tablename__}
                WHERE {conditions}
                ORDER BY timestamp ASC
            """
            
            # 执行查询
            cursor = conn.cursor()
            cursor.execute(query)
            klines = cursor.fetchall()
            
            # 转换为DataFrame
            if klines:
                df = pd.DataFrame(
                    klines, 
                    columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
                )
                # 时间戳转换
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float) / 1000, unit='s')
                df.set_index('timestamp', inplace=True)
                return df
            else:
                return None
                
        except Exception as e:
            logger.error(f"加载K线数据失败: {symbol} {timeframe}, 错误: {e}")
            return None
    
    def _determine_failure_type(
        self,
        symbol: str,
        trading_mode: str = 'spot'
    ) -> DownloadFailureType:
        """
        判断下载失败类型
        
        通过检查数据库中的symbol列表确认是否为数据源无数据
        
        参数：
            symbol: 货币对
            trading_mode: 交易模式
            
        返回：
            DownloadFailureType: 失败类型
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import CryptoSymbol
            
            # 初始化数据库
            init_database_config()
            db = SessionLocal()
            
            # 标准化symbol格式（去除/）
            normalized_symbol = symbol.replace('/', '')
            
            try:
                # 查询数据库中是否存在该symbol
                symbol_record = db.query(CryptoSymbol).filter(
                    CryptoSymbol.symbol == normalized_symbol,
                    CryptoSymbol.exchange == 'binance',
                    CryptoSymbol.is_active == True
                ).first()
                
                # 如果数据库中没有该symbol记录，说明数据源无此资产
                if symbol_record is None:
                    return DownloadFailureType.NO_DATA_AVAILABLE
                
                # 如果symbol存在但被标记为inactive，也可能是无数据
                if not symbol_record.is_active:
                    return DownloadFailureType.NO_DATA_AVAILABLE
                
                # 其他情况认为是网络或未知错误
                return DownloadFailureType.UNKNOWN
                
            finally:
                db.close()
            
        except Exception:
            # 如果无法判断，返回未知
            return DownloadFailureType.UNKNOWN
    
    def load_strategy(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any]
    ) -> StrategyBase:
        """
        加载策略
        
        参数：
            strategy_name: 策略名称（文件名，不含.py后缀）
            strategy_params: 策略参数
            
        返回：
            StrategyBase: 策略实例
            
        异常：
            StrategyLoadError: 策略加载失败
        """
        try:
            # 清除模块缓存
            if strategy_name in sys.modules:
                del sys.modules[strategy_name]
            
            # 检查策略文件
            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                raise StrategyLoadError(f"策略文件不存在: {strategy_file}")
            
            # 导入策略模块
            module = importlib.import_module(strategy_name)
            
            # 查找策略类
            strategy_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj != StrategyBase:
                    strategy_class = obj
                    logger.info(f"找到策略类: {name}")
                    break
            
            if strategy_class is None:
                raise StrategyLoadError(f"在模块 {strategy_name} 中找不到策略类")
            
            # 创建策略实例
            strategy = strategy_class(strategy_params)
            logger.info(f"成功加载策略: {strategy_class.__name__}")
            
            return strategy
            
        except Exception as e:
            raise StrategyLoadError(f"加载策略失败: {e}")
    
    def run_backtest(
        self,
        strategy: StrategyBase,
        data_dict: Dict[str, pd.DataFrame],
        config: Dict[str, Any],
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        执行回测
        
        参数：
            strategy: 策略实例
            data_dict: 数据字典
            config: 回测配置
            show_progress: 是否显示进度
            
        返回：
            Dict[str, Any]: 回测结果
            
        异常：
            BacktestExecutionError: 回测执行失败
        """
        try:
            # 使用投资组合适配器，实现多交易对共享资金池
            adapter = PortfolioBacktestAdapter(strategy)
            
            if show_progress:
                print(f"\n开始投资组合回测，交易对数量: {len(data_dict)}")
                print(f"初始总资金: {config.get('init_cash', 100000.0):.2f}")
                print("-" * 70)
            
            # 执行投资组合回测（所有交易对共享资金池）
            results = adapter.run_backtest(
                data=data_dict,
                init_cash=config.get('init_cash', 100000.0),
                fees=config.get('fees', 0.001),
                slippage=config.get('slippage', 0.0001),
                position_size_pct=config.get('position_size_pct', 0.1),
                verbose=self.detail
            )
            
            # 为每个交易对添加元数据
            for key in data_dict.keys():
                if key in results:
                    results[key]['symbol'], results[key]['timeframe'] = key.split('_')
                    results[key]['trading_mode'] = config.get('trading_mode', 'spot')
            
            # 添加投资组合汇总信息
            if 'portfolio' in results:
                portfolio = results['portfolio']
                metrics = portfolio.get('metrics', {})
                
                if show_progress:
                    print(f"\n{'=' * 70}")
                    print("投资组合回测完成")
                    print(f"{'=' * 70}")
                    print(f"最终总权益: {metrics.get('final_equity', 0):.2f}")
                    print(f"总收益率: {metrics.get('total_return', 0):.2f}%")
                    print(f"总交易次数: {metrics.get('total_trades', 0)}")
                    print(f"胜率: {metrics.get('win_rate', 0):.2f}%")
                    print(f"最大回撤: {metrics.get('max_drawdown', 2):.2f}%")
                    print(f"夏普比率: {metrics.get('sharpe_ratio', 0):.4f}")
                    print(f"{'=' * 70}")
            
            return results
            
        except Exception as e:
            raise BacktestExecutionError(f"回测执行失败: {e}")
    
    def save_to_database(
        self,
        results: Dict[str, Any],
        strategy_name: str,
        config: Dict[str, Any]
    ) -> bool:
        """
        保存回测结果到数据库
        
        参数：
            results: 回测结果
            strategy_name: 策略名称
            config: 回测配置
            
        返回：
            bool: 是否成功
        """
        try:
            from collector.db.database import init_database_config, SessionLocal
            from collector.db.models import BacktestTask, BacktestResult
            from sqlalchemy import func
            
            # 初始化数据库
            init_database_config()
            db = SessionLocal()
            
            try:
                # 保存投资组合整体结果
                if 'portfolio' in results:
                    portfolio = results['portfolio']
                    portfolio_metrics = portfolio.get('metrics', {})
                    
                    task_id = f"{strategy_name}_portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # 获取所有交易对
                    symbols = [k for k in results.keys() if k != 'portfolio']
                    
                    backtest_config = {
                        'symbols': symbols,
                        'start_time': config.get('time_range', '').split('-')[0] if config.get('time_range') else None,
                        'end_time': config.get('time_range', '').split('-')[1] if config.get('time_range') else None,
                        'initial_cash': config.get('init_cash', 100000.0),
                        'commission': config.get('fees', 0.001),
                        'slippage': config.get('slippage', 0.0001),
                        'trading_mode': config.get('trading_mode', 'spot'),
                        'strategy_params': config.get('strategy_params', {}),
                        'is_portfolio': True
                    }
                    
                    task = BacktestTask(
                        id=task_id,
                        strategy_name=strategy_name,
                        backtest_config=json.dumps(backtest_config, ensure_ascii=False),
                        status='completed',
                        completed_at=func.now()
                    )
                    db.add(task)
                    
                    result_record = BacktestResult(
                        id=f"{task_id}_result",
                        task_id=task_id,
                        strategy_name=strategy_name,
                        symbol='PORTFOLIO',
                        metrics=json.dumps(portfolio_metrics, ensure_ascii=False, default=str),
                        trades=json.dumps(portfolio.get('trades', []), ensure_ascii=False, default=str),
                        equity_curve=json.dumps(portfolio.get('equity_curve', []), ensure_ascii=False, default=str),
                        strategy_data=json.dumps({}, ensure_ascii=False, default=str)
                    )
                    db.add(result_record)
                    task.result_id = result_record.id
                    
                    logger.info(f"  ✓ 已保存投资组合整体回测结果")
                
                # 保存各交易对的结果
                for key, result in results.items():
                    if key == 'portfolio':
                        continue
                    
                    symbol, timeframe = key.split('_')
                    
                    task_id = f"{strategy_name}_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    backtest_config = {
                        'symbols': [symbol],
                        'interval': timeframe,
                        'start_time': config.get('time_range', '').split('-')[0] if config.get('time_range') else None,
                        'end_time': config.get('time_range', '').split('-')[1] if config.get('time_range') else None,
                        'initial_cash': config.get('init_cash', 100000.0),
                        'commission': config.get('fees', 0.001),
                        'slippage': config.get('slippage', 0.0001),
                        'trading_mode': config.get('trading_mode', 'spot'),
                        'strategy_params': config.get('strategy_params', {}),
                        'is_portfolio_component': True
                    }
                    
                    task = BacktestTask(
                        id=task_id,
                        strategy_name=strategy_name,
                        backtest_config=json.dumps(backtest_config, ensure_ascii=False),
                        status='completed',
                        completed_at=func.now()
                    )
                    db.add(task)
                    
                    result_record = BacktestResult(
                        id=f"{task_id}_result",
                        task_id=task_id,
                        strategy_name=strategy_name,
                        symbol=symbol,
                        metrics=json.dumps(result.get('metrics', {}), ensure_ascii=False, default=str),
                        trades=json.dumps(result.get('trades', []), ensure_ascii=False, default=str),
                        equity_curve=json.dumps(result.get('equity_curve', []), ensure_ascii=False, default=str),
                        strategy_data=json.dumps(result.get('strategy_data', []), ensure_ascii=False, default=str)
                    )
                    db.add(result_record)
                    task.result_id = result_record.id
                    
                    logger.info(f"  ✓ 已保存 {symbol} {timeframe} 的回测结果")
                
                # 提交事务
                db.commit()
                logger.info(f"✓ 成功将回测结果保存到数据库")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"保存到数据库失败: {e}")
                return False
            finally:
                db.close()
                
        except ImportError as e:
            logger.error(f"无法导入数据库模块: {e}")
            return False
        except Exception as e:
            logger.error(f"保存到数据库时发生错误: {e}")
            return False


def get_system_config() -> Dict[str, Any]:
    """
    从系统配置表读取默认值
    
    返回：
        Dict[str, Any]: 包含默认交易模式和时间周期的字典
    """
    try:
        from collector.db.connection import get_db_connection
        
        conn = get_db_connection()
        
        # 读取交易模式默认值
        trading_mode_config = conn.execute(
            "SELECT value FROM system_config WHERE key = 'default_trading_mode'"
        ).fetchone()
        default_trading_mode = trading_mode_config[0] if trading_mode_config else 'spot'
        
        # 读取时间周期默认值
        timeframes_config = conn.execute(
            "SELECT value FROM system_config WHERE key = 'default_timeframes'"
        ).fetchone()
        default_timeframes = timeframes_config[0].split(',') if timeframes_config else ['1h']
        
        return {
            'default_trading_mode': default_trading_mode,
            'default_timeframes': default_timeframes
        }
        
    except Exception as e:
        logger.warning(f"从系统配置读取默认值失败: {e}")
        return {
            'default_trading_mode': 'spot',
            'default_timeframes': ['1h']
        }


def get_symbols_from_data_pool(pool_name: str) -> List[str]:
    """
    从数据池获取自选组合的货币对列表
    
    参数：
        pool_name: 自选组合名称
        
    返回：
        List[str]: 货币对列表
        
    异常：
        ValueError: 如果自选组合不存在或获取失败
    """
    try:
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import DataPool, DataPoolAsset
        
        # 初始化数据库
        init_database_config()
        db = SessionLocal()
        
        try:
            # 查询自选组合
            pool = db.query(DataPool).filter_by(name=pool_name).first()
            if not pool:
                raise ValueError(f"自选组合不存在: {pool_name}")
            
            # 获取该组合下的所有资产
            assets = db.query(DataPoolAsset).filter_by(pool_id=pool.id).all()
            symbols = [asset.asset_id for asset in assets]
            
            if not symbols:
                logger.warning(f"自选组合 '{pool_name}' 中没有货币对")
                return []
            
            logger.info(f"从自选组合 '{pool_name}' 获取到 {len(symbols)} 个货币对: {symbols}")
            return symbols
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"从自选组合获取货币对失败: {pool_name}, 错误: {e}")
        raise ValueError(f"从自选组合获取货币对失败: {e}")


def generate_test_data(
    n_steps: int = 1000,
    base_price: float = 50000.0,
    volatility: float = 0.001
) -> pd.DataFrame:
    """
    生成测试数据
    
    参数：
        n_steps: 数据步数
        base_price: 基础价格
        volatility: 波动率
        
    返回：
        pd.DataFrame: OHLC数据
    """
    np.random.seed(42)
    
    # 生成价格数据
    price_changes = np.random.normal(0, volatility, n_steps)
    prices = base_price * (1 + np.cumsum(price_changes))
    
    # 生成日期
    dates = pd.date_range('2024-01-01', periods=n_steps, freq='H')
    
    # 创建OHLC数据
    df = pd.DataFrame({
        'Open': prices,
        'High': prices * 1.002,
        'Low': prices * 0.998,
        'Close': prices,
        'Volume': np.random.uniform(100, 1000, n_steps)
    }, index=dates)
    
    return df
