# 回测服务
# 实现策略回测和回测结果分析功能

import sys
import os
import json
import uuid
import concurrent.futures
from pathlib import Path
import pandas as pd
from datetime import datetime

from loguru import logger
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 导入现有模块
from collector.services.data_service import DataService
from strategy.service import StrategyService
from i18n.utils import load_translations
from config_manager import get_config
from utils.timezone import format_datetime


class BacktestService:
    """
    回测服务类，用于执行策略回测和分析回测结果
    """
    
    def __init__(self):
        """初始化回测服务"""
        # 策略服务实例 - 使用独立的策略模块
        self.strategy_service = StrategyService()
        
        # 回测结果保存路径
        self.backtest_result_dir = Path(project_root) / "backend" / "backtest" / "results"
        self.backtest_result_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据服务实例
        self.data_service = DataService()
        
        # 数据管理器实例，用于管理多时间周期数据
        from .data_manager import DataManager
        self.data_manager = DataManager(self.data_service)
        
        # 需要翻译的指标键列表
        self.metric_keys = [
            'Start', 'End', 'Duration', 'Exposure Time [%]', 'Equity Final [$]', 
            'Equity Peak [$]', 'Commissions [$]', 'Return [%]', 'Return (Ann.) [%]', 
            'Buy & Hold Return [%]', 'Volatility (Ann.) [%]', 'CAGR [%]', 'Sharpe Ratio', 
            'Sortino Ratio', 'Calmar Ratio', 'Alpha [%]', 'Beta', 'Max. Drawdown [%]', 
            'Avg. Drawdown [%]', 'Profit Factor', 'Win Rate [%]', 'Expectancy [%]', 
            '# Trades', 'Best Trade [%]', 'Worst Trade [%]', 'Avg. Trade [%]', 
            'Max. Trade Duration', 'Avg. Trade Duration', 'Max. Drawdown Duration', 
            'Avg. Drawdown Duration', 'SQN', 'Kelly Criterion'
        ]

    def _sanitize_for_json(self, data):
        """
        递归清理数据，使其可以被JSON序列化
        处理 NaT, NaN, Infinity, Timestamp 等
        """
        import numpy as np
        if isinstance(data, dict):
            return {k: self._sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_for_json(item) for item in data]
        elif isinstance(data, (pd.Timestamp, datetime)):
            if pd.isna(data):
                return None
            return data.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(data, pd.Timedelta):
            if pd.isna(data):
                return None
            return str(data)
        elif pd.isna(data):  # Checks for NaN, NaT, None
            return None
        elif isinstance(data, float):
            if np.isinf(data):
                return None
            return data
        # Handle numpy types if necessary
        if isinstance(data, (np.integer, np.int64, np.int32)):
            return int(data)
        if isinstance(data, (np.floating, np.float64, np.float32)):
            if np.isnan(data) or np.isinf(data):
                return None
            return float(data)
            
        return data
    
    def get_strategy_list(self):
        """
        获取所有支持的策略类型列表
        
        :return: 策略类型列表
        """
        try:
            # 调用策略服务获取策略列表
            strategies = self.strategy_service.get_strategy_list()
            
            # 只返回策略名称列表，保持原有接口兼容性
            strategy_names = [strategy["name"] for strategy in strategies]
            
            logger.info(f"获取策略列表成功，共 {len(strategy_names)} 个策略")
            return strategy_names
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            logger.exception(e)
            return []
    
    def load_strategy_from_file(self, strategy_name):
        """
        从文件中加载策略类
        
        :param strategy_name: 策略名称
        :return: 策略类
        """
        try:
            # 调用策略服务加载策略
            strategy_class = self.strategy_service.load_strategy(strategy_name)
            
            if strategy_class:
                logger.info(f"成功加载策略: {strategy_name}")
                return strategy_class
            else:
                logger.error(f"加载策略失败: {strategy_name}")
                return None
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            logger.exception(e)
            return None
    
    def upload_strategy_file(self, strategy_name, file_content):
        """
        上传策略文件
        
        :param strategy_name: 策略名称
        :param file_content: 文件内容
        :return: 是否上传成功
        """
        try:
            # 调用策略服务上传策略文件
            success = self.strategy_service.upload_strategy_file(strategy_name, file_content)
            
            if success:
                logger.info(f"策略文件上传成功: {strategy_name}")
            else:
                logger.error(f"策略文件上传失败: {strategy_name}")
            
            return success
        except Exception as e:
            logger.error(f"策略文件上传失败: {e}")
            logger.exception(e)
            return False
    
    def run_single_backtest(self, strategy_config, backtest_config, task_id):
        """
        执行单个货币对的回测
        
        :param strategy_config: 策略配置
        :param backtest_config: 回测配置，包含单个货币对信息
        :param task_id: 回测任务ID，所有货币对共享同一个task_id
        :return: 单个货币对的回测结果数据，不直接保存到数据库
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            import json
            
            # 初始化数据库连接
            init_database_config()
            db = SessionLocal()
            
            # 创建带有数据库会话的DataService和DataManager
            # 注意：在多线程环境中，必须为每个线程创建独立的数据库会话
            local_data_service = DataService(db)
            from .data_manager import DataManager
            local_data_manager = DataManager(local_data_service)
            
            strategy_name = strategy_config.get("strategy_name")
            symbol = backtest_config.get("symbol", "BTCUSDT")
            logger.info(f"开始回测，策略名称: {strategy_name}, 货币对: {symbol}, task_id: {task_id}")
            
            # 加载策略类
            strategy_class = self.load_strategy_from_file(strategy_name)
            if not strategy_class:
                return {
                    "symbol": symbol,
                    "task_id": task_id,
                    "status": "failed",
                    "message": f"策略加载失败: {strategy_name}"
                }
            
            # 获取回测配置
            interval = backtest_config.get("interval", "1d")
            start_time = backtest_config.get("start_time")
            end_time = backtest_config.get("end_time")
            
            logger.info(f"回测配置: {symbol}, {interval}, {start_time} to {end_time}")
            
            # 预加载多种时间周期的数据
            local_data_manager.preload_data(
                symbol=symbol,
                base_interval=interval,
                start_time=start_time,
                end_time=end_time,
                preload_intervals=['1m', '5m', '15m', '30m', '1h', '4h', '1d']  # 预加载常用周期
            )
            
            # 获取主周期K线数据
            logger.info(f"获取主周期 {interval} 的K线数据")
            
            # 使用数据服务获取K线数据
            result = local_data_service.get_kline_data(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time
            )
            
            kline_data = result.get("kline_data", [])
            
            if not kline_data:
                logger.error(f"未获取到K线数据: {symbol}, {interval}, {start_time} to {end_time}")
                return {
                    "symbol": symbol,
                    "task_id": task_id,
                    "status": "failed",
                    "message": f"未获取到货币对 {symbol} 的K线数据"
                }
                
            # Convert to DataFrame
            candles = pd.DataFrame(kline_data)
            
            # 转换数据格式为backtesting.py所需格式
            candles.rename(columns={
                'open': 'Open',
                'close': 'Close',
                'high': 'High',
                'low': 'Low',
                'volume': 'Volume'
            }, inplace=True)
            
            # 设置时间索引
            if 'timestamp' in candles.columns:
                candles['datetime'] = pd.to_datetime(candles['timestamp'], unit='ms')
                candles.set_index('datetime', inplace=True)
            elif 'datetime' in candles.columns:
                candles.set_index('datetime', inplace=True)
            elif 'open_time' in candles.columns:
                candles['open_time'] = pd.to_datetime(candles['open_time'])
                candles.set_index('open_time', inplace=True)
            
            # 初始化回测
            initial_cash = backtest_config.get("initial_cash", 10000)
            commission = backtest_config.get("commission", 0.001)
            
            # Check if initial cash is sufficient for the asset price
            # Find max close price to ensure we can cover at least one unit if needed, 
            # though backtesting.py handles this, explicit check avoids warning.
            max_price = candles['Close'].max()
            if max_price > initial_cash:
                logger.warning(f"Initial cash ({initial_cash}) is lower than max price ({max_price}). Increasing cash to avoid warnings.")
                initial_cash = max_price * 1.1 # Add 10% buffer
            
            # 为数据添加交易对符号属性
            candles.symbol = symbol
            
            # 自定义回测运行器，用于在策略实例化后设置数据管理器
            class CustomBacktest(Backtest):
                def run(self, **kwargs):
                    # 执行父类的run方法
                    result = super().run(**kwargs)
                    # 获取策略实例并设置数据管理器
                    if hasattr(result, '_strategy'):
                        strategy_instance = result['_strategy']
                        if hasattr(strategy_instance, 'set_data_manager'):
                            strategy_instance.set_data_manager(local_data_manager)
                    return result
            
            bt = CustomBacktest(
                candles, 
                strategy_class, 
                cash=initial_cash,
                commission=commission,
                exclusive_orders=True
            )
            
            # 执行回测
            stats = bt.run()
            
            # 获取策略数据
            strategy_data = []
            if '_strategy' in stats:
                strategy_instance = stats['_strategy']
                if hasattr(strategy_instance, 'data'):
                    # Try to access underlying DataFrame
                    # In some versions of backtesting.py, it might be .df or accessible via converting to dataframe
                    try:
                        df = None
                        if hasattr(strategy_instance.data, 'df'):
                            df = strategy_instance.data.df
                        elif isinstance(strategy_instance.data, pd.DataFrame):
                            df = strategy_instance.data
                        
                        if df is not None:
                            # 重要：保留时间索引作为一个字段
                            df_copy = df.copy()
                            df_copy.reset_index(inplace=True)
                            
                            # 重命名索引列为datetime
                            if 'index' in df_copy.columns:
                                df_copy.rename(columns={'index': 'datetime'}, inplace=True)
                            elif df_copy.index.name and df_copy.index.name not in df_copy.columns:
                                # 如果索引有名称且不是datetime，重命名为datetime
                                first_col = df_copy.columns[0]
                                if first_col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
                                    df_copy.rename(columns={first_col: 'datetime'}, inplace=True)
                            
                            # 如果还是没有datetime列，假设第一列是时间
                            if 'datetime' not in df_copy.columns and len(df_copy.columns) > 0:
                                first_col = df_copy.columns[0]
                                df_copy.rename(columns={first_col: 'datetime'}, inplace=True)
                            
                            strategy_data = df_copy.to_dict('records')
                    except Exception as e:
                        logger.warning(f"Failed to extract strategy data: {e}")
                        logger.exception(e)

            # 获取交易记录
            trades = []
            if '_trades' in stats:
                trades = stats['_trades'].to_dict('records')
                for trade in trades:
                    for key, value in trade.items():
                        if isinstance(value, pd.Timestamp):
                            trade[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(value, pd.Timedelta):
                            trade[key] = str(value)
                    # 添加交易方向
                    if trade.get('Size', 0) > 0:
                        trade['Direction'] = '多单'
                    else:
                        trade['Direction'] = '空单'
            
            # 翻译回测结果
            translated_metrics = self.translate_backtest_results(stats)
            
            # 生成回测ID - 使用UUID替代原有格式，避免URL路径问题
            backtest_id = str(uuid.uuid4())
            
            # 准备资金曲线数据，保留时间索引
            equity_df = stats['_equity_curve'].copy()
            equity_df.reset_index(inplace=True)
            # 重命名索引列为datetime，以匹配前端期望
            if 'index' in equity_df.columns:
                equity_df.rename(columns={'index': 'datetime'}, inplace=True)
            elif 'time' in equity_df.columns:
                equity_df.rename(columns={'time': 'datetime'}, inplace=True)
            # 如果索引有名称但不是index或time，它会自动成为列名，我们确保它是datetime
            # backtesting.py通常使用datetime索引，所以reset_index后通常是index或原名
            # 这里做一个通用处理：找到第一个列（原索引）并重命名为datetime
            if 'datetime' not in equity_df.columns and len(equity_df.columns) > 0:
                # 假设第一列是时间
                equity_df.rename(columns={equity_df.columns[0]: 'datetime'}, inplace=True)
            
            equity_curve_data = equity_df.to_dict('records')
            
            # 构建回测结果数据，不直接保存到数据库
            result_data = {
                "id": backtest_id,
                "symbol": symbol,
                "task_id": task_id,
                "status": "success",
                "message": "回测完成",
                "strategy_name": strategy_name,
                "backtest_config": backtest_config,
                "metrics": self._sanitize_for_json(translated_metrics),
                "trades": self._sanitize_for_json(trades),
                "equity_curve": self._sanitize_for_json(equity_curve_data),
                "strategy_data": self._sanitize_for_json(strategy_data)
            }
            
            logger.info(f"回测完成，策略: {strategy_name}, 货币对: {symbol}, 回测ID: {backtest_id}, task_id: {task_id}")
            return result_data
        except Exception as e:
            logger.error(f"回测失败: {e}")
            logger.exception(e)
            symbol = backtest_config.get("symbol", "BTCUSDT")
            return {
                "symbol": symbol,
                "task_id": task_id,
                "status": "failed",
                "message": str(e)
            }
    
    def merge_backtest_results(self, results):
        """
        合并多个货币对的回测结果
        
        :param results: 各货币对的回测结果字典，格式为 {symbol: result}
        :return: 合并后的回测结果
        """
        try:
            logger.info(f"开始合并回测结果，共 {len(results)} 个货币对")
            
            # 提取第一个成功的回测结果作为基础
            base_result = None
            for symbol, result in results.items():
                if result["status"] == "success":
                    base_result = result
                    break
            
            if not base_result:
                logger.error("所有货币对回测失败，无法合并结果")
                return {
                    "status": "failed",
                    "message": "所有货币对回测失败",
                    "currencies": results
                }
            
            # 计算整体统计指标
            total_trades = 0
            successful_currencies = []
            returns = []
            max_drawdowns = []
            sharpe_ratios = []
            sortino_ratios = []
            calmar_ratios = []
            win_rates = []
            profit_factors = []
            total_equity = 0
            total_initial_cash = 0
            
            # 收集所有成功回测的结果
            successful_results = {}
            for symbol, result in results.items():
                if result["status"] == "success":
                    successful_currencies.append(symbol)
                    successful_results[symbol] = result
                    
                    # 统计交易次数
                    trade_count = len(result["trades"])
                    total_trades += trade_count
                    logger.info(f"货币对 {symbol} 交易次数: {trade_count}")
                    
                    # 提取关键指标
                    # 首先获取初始资金
                    initial_cash = result.get("backtest_config", {}).get("initial_cash", 10000)
                    total_initial_cash += initial_cash
                    logger.info(f"货币对 {symbol} 初始资金: ${initial_cash}")
                    
                    logger.info(f"开始提取货币对 {symbol} 的指标")
                    
                    # 标记是否找到最终权益指标
                    found_equity_final = False
                    
                    for metric in result["metrics"]:
                        # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                        metric_key = metric.get("key", metric.get("name", ""))
                        metric_name = metric.get("name", "")
                        metric_value = metric.get("value")
                        
                        logger.debug(f"检查指标: key={metric_key}, name={metric_name}, value={metric_value}, type={type(metric_value)}")
                        
                        if metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率":
                            if isinstance(metric_value, (int, float)):
                                returns.append(metric_value)
                                logger.debug(f"货币对 {symbol} 收益率: {metric_value}%")
                        elif metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤":
                            if isinstance(metric_value, (int, float)):
                                max_drawdowns.append(metric_value)
                                logger.debug(f"货币对 {symbol} 最大回撤: {metric_value}%")
                        elif metric_key == "Sharpe Ratio" or metric_name == "Sharpe Ratio" or metric_name == "夏普比率":
                            if isinstance(metric_value, (int, float)):
                                sharpe_ratios.append(metric_value)
                                logger.debug(f"货币对 {symbol} 夏普比率: {metric_value}")
                        elif metric_key == "Sortino Ratio" or metric_name == "Sortino Ratio" or metric_name == "索提诺比率":
                            if isinstance(metric_value, (int, float)):
                                sortino_ratios.append(metric_value)
                                logger.debug(f"货币对 {symbol} 索提诺比率: {metric_value}")
                        elif metric_key == "Calmar Ratio" or metric_name == "Calmar Ratio" or metric_name == "卡尔玛比率":
                            if isinstance(metric_value, (int, float)):
                                calmar_ratios.append(metric_value)
                                logger.debug(f"货币对 {symbol} 卡尔玛比率: {metric_value}")
                        elif metric_key == "Win Rate [%]" or metric_name == "Win Rate [%]" or metric_name == "胜率":
                            if isinstance(metric_value, (int, float)):
                                win_rates.append(metric_value)
                                logger.debug(f"货币对 {symbol} 胜率: {metric_value}%")
                        elif metric_key == "Profit Factor" or metric_name == "Profit Factor" or metric_name == "盈利因子":
                            if isinstance(metric_value, (int, float)):
                                profit_factors.append(metric_value)
                                logger.debug(f"货币对 {symbol} 盈利因子: {metric_value}")
                        elif metric_key == "Equity Final [$]" or metric_name == "最终权益":
                            if isinstance(metric_value, (int, float)):
                                total_equity += metric_value
                                found_equity_final = True
                                logger.info(f"货币对 {symbol} 最终权益: ${metric_value}")
                            else:
                                logger.warning(f"货币对 {symbol} 最终权益值不是数字: {metric_value}, 类型: {type(metric_value)}")
                    
                    # 如果没有找到最终权益指标，尝试使用收益率和初始资金计算
                    if not found_equity_final:
                        logger.warning(f"货币对 {symbol} 未找到最终权益指标，尝试使用收益率计算")
                        # 查找总收益率指标
                        for metric in result["metrics"]:
                            metric_key = metric.get("key", metric.get("name", ""))
                            metric_name = metric.get("name", "")
                            metric_value = metric.get("value")
                            
                            if (metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率") and isinstance(metric_value, (int, float)):
                                # 使用收益率和初始资金计算最终权益
                                calculated_equity = initial_cash * (1 + metric_value / 100)
                                total_equity += calculated_equity
                                logger.info(f"货币对 {symbol} 使用收益率计算最终权益: ${calculated_equity}")
                                break
                    
                    logger.info(f"货币对 {symbol} 处理完成，累计总权益: ${total_equity}")
                    logger.debug(f"货币对 {symbol} 初始资金: ${initial_cash}")
            
            logger.info(f"成功回测的货币对数量: {len(successful_currencies)}/{len(results)}")
            
            # 计算平均值
            avg_return = sum(returns) / len(returns) if returns else 0
            avg_max_drawdown = sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0
            avg_sharpe = sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0
            avg_sortino = sum(sortino_ratios) / len(sortino_ratios) if sortino_ratios else 0
            avg_calmar = sum(calmar_ratios) / len(calmar_ratios) if calmar_ratios else 0
            avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            avg_profit_factor = sum(profit_factors) / len(profit_factors) if profit_factors else 0
            
            # 计算总收益率
            total_return = ((total_equity - total_initial_cash) / total_initial_cash) * 100 if total_initial_cash > 0 else 0
            
            # 生成合并后的回测ID
            merged_backtest_id = str(uuid.uuid4())
            
            # 合并资金曲线
            def merge_equity_curves(currency_results):
                """
                合并多个货币对的资金曲线
                
                :param currency_results: 成功货币对的回测结果字典
                :return: 合并后的资金曲线
                """
                try:
                    # 收集所有时间戳和对应权益值
                    time_equity_map = {}
                    
                    for symbol, result in currency_results.items():
                        if result.get("status") == "success" and "equity_curve" in result:
                            equity_curve = result["equity_curve"]
                            for equity_data in equity_curve:
                                # 提取时间戳
                                timestamp = equity_data.get("datetime") or equity_data.get("time") or equity_data.get("timestamp")
                                if timestamp:
                                    # 提取权益值
                                    equity = equity_data.get("Equity") or equity_data.get("equity") or 0
                                    if timestamp not in time_equity_map:
                                        time_equity_map[timestamp] = 0
                                    time_equity_map[timestamp] += equity
                    
                    # 按时间戳排序并构建合并后的资金曲线
                    merged_curve = []
                    for timestamp in sorted(time_equity_map.keys()):
                        merged_curve.append({
                            "datetime": timestamp,
                            "Equity": time_equity_map[timestamp]
                        })
                    
                    logger.info(f"资金曲线合并完成，共 {len(merged_curve)} 个时间点")
                    return merged_curve
                except Exception as e:
                    logger.error(f"合并资金曲线失败: {e}")
                    logger.exception(e)
                    return []
            
            # 执行资金曲线合并
            merged_equity_curve = merge_equity_curves(successful_results)
            
            # 构建合并后的回测结果
            merged_result = {
                "task_id": merged_backtest_id,
                "status": "success",
                "message": "多货币对回测完成",
                "strategy_name": base_result.get("strategy_name", "Unknown"),
                "backtest_config": base_result.get("backtest_config", {}),
                "summary": {
                    "total_currencies": len(results),
                    "successful_currencies": len(successful_currencies),
                    "failed_currencies": len(results) - len(successful_currencies),
                    "total_trades": total_trades,
                    "average_trades_per_currency": round(total_trades / len(successful_currencies), 2) if successful_currencies else 0,
                    "total_initial_cash": round(total_initial_cash, 2),
                    "total_equity": round(total_equity, 2),
                    "total_return": round(total_return, 2),
                    "average_return": round(avg_return, 2),
                    "average_max_drawdown": round(avg_max_drawdown, 2),
                    "average_sharpe_ratio": round(avg_sharpe, 2),
                    "average_sortino_ratio": round(avg_sortino, 2),
                    "average_calmar_ratio": round(avg_calmar, 2),
                    "average_win_rate": round(avg_win_rate, 2),
                    "average_profit_factor": round(avg_profit_factor, 2)
                },
                "currencies": results,
                "merged_equity_curve": merged_equity_curve,  # 合并后的资金曲线
                "successful_currencies": successful_currencies,
                "failed_currencies": [symbol for symbol, result in results.items() if result["status"] != "success"]
            }
            
            logger.info(f"回测结果合并完成，共 {len(successful_currencies)} 个货币对回测成功")
            logger.info(f"合并后总收益率: {round(total_return, 2)}%，总交易次数: {total_trades}")
            return merged_result
        except Exception as e:
            logger.error(f"合并回测结果失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": f"合并回测结果失败: {str(e)}",
                "currencies": results
            }
    
    def run_backtest(self, strategy_config, backtest_config):
        """
        执行回测，支持多货币对并行回测
        
        :param strategy_config: 策略配置
        :param backtest_config: 回测配置，包含symbols列表
        :return: 回测结果，单个货币对返回BacktestResult，多个货币对返回MultiBacktestResult
        """
        db = None
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            import json
            
            # 初始化数据库连接
            init_database_config()
            db = SessionLocal()
            
            # 从配置中获取货币对列表
            symbols = backtest_config.get("symbols", ["BTCUSDT"])
            strategy_name = strategy_config.get("strategy_name", "Unknown")
            
            logger.info(f"=== 开始回测任务 ===")
            logger.info(f"策略名称: {strategy_name}")
            logger.info(f"回测货币对: {symbols}")
            logger.info(f"回测周期: {backtest_config.get('interval', '1d')}")
            logger.info(f"回测时间范围: {backtest_config.get('start_time')} 至 {backtest_config.get('end_time')}")
            logger.info(f"初始资金: {backtest_config.get('initial_cash', 10000)}")
            logger.info(f"手续费率: {backtest_config.get('commission', 0.001)}")
            
            # 生成唯一的task_id
            task_id = str(uuid.uuid4())
            
            # 创建回测任务记录
            from datetime import datetime, timezone
            task = BacktestTask(
                id=task_id,
                strategy_name=strategy_name,
                backtest_config=json.dumps(backtest_config),
                status="in_progress",
                started_at=datetime.now(timezone.utc)
            )
            db.add(task)
            db.commit()
            
            # 限制线程数量，避免系统过载
            cpu_count = os.cpu_count() or 1
            max_workers = min(len(symbols), cpu_count * 2)
            logger.info(f"使用线程池执行回测，最大线程数: {max_workers}")
            logger.info(f"CPU核心数: {cpu_count}")
            
            # 使用线程池并行执行回测
            results = {}
            completed_count = 0
            failed_count = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有回测任务
                future_to_symbol = {}
                for symbol in symbols:
                    # 复制配置，替换货币对
                    single_config = backtest_config.copy()
                    single_config["symbol"] = symbol
                    del single_config["symbols"]
                    
                    logger.info(f"提交回测任务: {symbol}, task_id: {task_id}")
                    future = executor.submit(
                        self.run_single_backtest,
                        strategy_config,
                        single_config,
                        task_id  # 传递task_id
                    )
                    future_to_symbol[future] = symbol
                
                # 收集回测结果
                total_futures = len(future_to_symbol)
                for future in concurrent.futures.as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        result = future.result(timeout=3600)  # 1小时超时
                        results[symbol] = result
                        completed_count += 1
                        logger.info(f"回测完成 [{completed_count}/{total_futures}]: {symbol}, 状态: {result.get('status')}")
                        if result.get('status') == 'success':
                            # 记录关键指标
                            for metric in result.get('metrics', []):
                                if metric['name'] == 'Return [%]':
                                    logger.info(f"货币对 {symbol} 收益率: {metric['value']}%")
                                    break
                    except concurrent.futures.TimeoutError:
                        logger.error(f"回测超时 [{completed_count + failed_count + 1}/{total_futures}]: {symbol}")
                        results[symbol] = {
                            "symbol": symbol,
                            "task_id": task_id,
                            "status": "failed",
                            "message": "回测超时"
                        }
                        failed_count += 1
                    except Exception as e:
                        logger.error(f"回测失败 [{completed_count + failed_count + 1}/{total_futures}]: {symbol}, 错误: {e}")
                        logger.exception(e)
                        results[symbol] = {
                            "symbol": symbol,
                            "task_id": task_id,
                            "status": "failed",
                            "message": str(e)
                        }
                        failed_count += 1
            
            logger.info(f"=== 所有回测任务执行完毕 ===")
            logger.info(f"总货币对数量: {len(symbols)}")
            logger.info(f"成功数量: {completed_count - failed_count}")
            logger.info(f"失败数量: {failed_count}")
            logger.info(f"完成率: {(completed_count / len(symbols)) * 100:.2f}%")
            
            # 保存每个货币对的回测结果到数据库
            successful_results = []
            failed_results = []
            for symbol, result in results.items():
                if result.get('status') == 'success':
                    successful_results.append(symbol)
                    # 创建回测结果记录
                    backtest_result = BacktestResult(
                        id=result['id'],
                        task_id=task_id,
                        strategy_name=strategy_name,
                        symbol=symbol,
                        metrics=json.dumps(result['metrics']),
                        trades=json.dumps(result['trades']),
                        equity_curve=json.dumps(result['equity_curve']),
                        strategy_data=json.dumps(result['strategy_data'])
                    )
                    db.add(backtest_result)
                    # 保存回测结果到文件
                    self.save_backtest_result(result['id'], result)
                else:
                    failed_results.append(symbol)
            
            # 更新回测任务状态
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            # 设置结果ID为第一个成功的回测结果ID（兼容旧版本）
            if successful_results:
                first_success_result = results[successful_results[0]]
                task.result_id = first_success_result['id']
            db.commit()
            
            # 合并回测结果
            logger.info("=== 开始合并回测结果 ===")
            merged_result = self.merge_backtest_results(results)
            merged_result['task_id'] = task_id
            logger.info("=== 回测任务全部完成 ===")
            
            # 保存合并后的回测结果到文件系统
            self.save_backtest_result(task_id, merged_result)
            
            # 构建响应结果
            response = {
                "task_id": task_id,
                "status": "completed",
                "message": f"回测完成，共 {len(symbols)} 个货币对，{len(successful_results)} 个成功，{len(failed_results)} 个失败",
                "successful_currencies": successful_results,
                "failed_currencies": failed_results,
                "results": merged_result
            }
            
            return response
        except Exception as e:
            if db:
                db.rollback()
            logger.error(f"回测任务执行失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
        finally:
            if db:
                db.close()
    
    def translate_backtest_results(self, stats):
        """
        翻译回测结果为多语言
        
        :param stats: 回测结果
        :return: 翻译后的回测结果
        """
        # 获取当前语言设置
        language = get_config("language", "zh-CN")
        # 加载翻译
        trans = load_translations(language)
        
        translated_metrics = []
        for key, value in stats.items():
            if key in ['_strategy', '_equity_curve', '_trade_list', '_trades']:
                continue
            
            # 获取翻译
            name = trans.get(key, key)
            desc = trans.get(f"{key}.desc", name)
            
            # 处理特殊类型的值
            metric_type = 'string'  # 默认类型
            if isinstance(value, pd.Timestamp):
                value = value.strftime('%Y-%m-%d %H:%M:%S')
                metric_type = 'datetime'
            elif isinstance(value, pd.Timedelta):
                value = str(value)
                metric_type = 'duration'
            elif isinstance(value, (pd.Series, pd.DataFrame)):
                continue  # 跳过复杂数据结构
            elif isinstance(value, (int, float)):
                # 根据指标名称判断是否为百分比
                if '[%]' in key:
                    metric_type = 'percentage'
                elif '[$]' in key:
                    metric_type = 'currency'
                else:
                    metric_type = 'number'
            
            translated_metrics.append({
                'name': name,
                'key': key,  # 添加原始key用于前端识别
                'value': value,
                'description': desc,
                'type': metric_type  # 添加类型字段
            })
        
        return translated_metrics
    
    def analyze_backtest(self, backtest_id):
        """
        分析回测结果
        
        :param backtest_id: 回测ID
        :return: 分析结果
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestResult
            import json
            
            logger.info(f"开始分析回测结果，回测ID: {backtest_id}")
            
            # 首先尝试从文件系统加载回测结果（优先获取合并后的多货币对结果）
            result = self.load_backtest_result(backtest_id)
            
            if result:
                logger.info(f"从文件系统加载回测结果成功，回测ID: {backtest_id}")
                return {
                    "status": "success",
                    "message": "回测结果分析完成",
                    **result
                }
            
            # 如果文件系统中没有找到，再尝试从数据库加载
            logger.warning(f"回测结果在文件系统中不存在，尝试从数据库加载，回测ID: {backtest_id}")
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            
            try:
                # 从数据库中获取回测结果
                result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                
                if not result_record:
                    return {
                        "status": "failed",
                        "message": f"回测结果不存在: {backtest_id}"
                    }
                
                # 构建回测结果
                result = {
                    "task_id": result_record.id,
                    "status": "success",
                    "message": "回测完成",
                    "strategy_name": result_record.strategy_name,
                    "backtest_config": {},  # 从回测任务中获取，这里简化处理
                    "metrics": json.loads(result_record.metrics),
                    "trades": json.loads(result_record.trades),
                    "equity_curve": json.loads(result_record.equity_curve),
                    "strategy_data": json.loads(result_record.strategy_data)
                }
                
                # 获取回测配置
                from collector.db.models import BacktestTask
                task = db.query(BacktestTask).filter_by(id=result_record.task_id).first()
                if task:
                    result["backtest_config"] = json.loads(task.backtest_config)
                
                logger.info(f"回测结果分析完成，回测ID: {backtest_id}")
                return {
                    "status": "success",
                    "message": "回测结果分析完成",
                    **result
                }
            except Exception as db_e:
                logger.error(f"从数据库获取回测结果失败: {db_e}")
                logger.exception(db_e)
                return {
                    "status": "failed",
                    "message": f"从数据库获取回测结果失败: {str(db_e)}"
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"回测结果分析失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def save_backtest_result(self, backtest_id, result):
        """
        保存回测结果
        
        :param backtest_id: 回测ID
        :param result: 回测结果
        :return: 是否保存成功
        """
        try:
            # 保存回测结果文件
            result_path = self.backtest_result_dir / f"{backtest_id}.json"
            
            with open(result_path, "w") as f:
                json.dump(result, f, indent=4, default=str, ensure_ascii=False)
            
            logger.info(f"回测结果保存成功，回测路径: {result_path}")
            return True
        except Exception as e:
            logger.error(f"回测结果保存失败: {e}")
            logger.exception(e)
            return False
    
    def load_backtest_result(self, backtest_id):
        """
        加载回测结果
        
        :param backtest_id: 回测ID
        :return: 回测结果
        """
        try:
            # 加载回测结果文件
            result_path = self.backtest_result_dir / f"{backtest_id}.json"
            if not result_path.exists():
                logger.error(f"回测结果文件不存在: {result_path}")
                return None
            
            with open(result_path, "r", encoding="utf-8") as f:
                backtest_result = json.load(f)
            
            logger.info(f"回测结果加载成功，回测路径: {result_path}")
            return backtest_result
        except Exception as e:
            logger.error(f"回测结果加载失败: {e}")
            logger.exception(e)
            return None
    
    def delete_backtest_result(self, backtest_id):
        """
        删除回测结果
        
        :param backtest_id: 回测ID
        :return: 是否删除成功
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask, BacktestResult
            
            success = False
            
            # 先从数据库中删除回测结果
            try:
                # 初始化数据库配置
                init_database_config()
                db = SessionLocal()
                
                try:
                    # 删除回测结果记录
                    result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                    if result_record:
                        db.delete(result_record)
                        logger.info(f"从数据库删除回测结果记录成功，回测ID: {backtest_id}")
                    
                    # 删除回测任务记录
                    task = db.query(BacktestTask).filter_by(id=backtest_id).first()
                    if task:
                        db.delete(task)
                        logger.info(f"从数据库删除回测任务记录成功，回测ID: {backtest_id}")
                        success = True
                    
                    db.commit()
                except Exception as db_e:
                    db.rollback()
                    logger.error(f"从数据库删除回测结果失败: {db_e}")
                    logger.exception(db_e)
                finally:
                    db.close()
            except Exception as db_init_e:
                logger.error(f"初始化数据库失败，无法从数据库删除回测结果: {db_init_e}")
                logger.exception(db_init_e)
            
            # 然后从文件系统中删除回测结果文件
            try:
                result_path = self.backtest_result_dir / f"{backtest_id}.json"
                if result_path.exists():
                    result_path.unlink()
                    logger.info(f"从文件系统删除回测结果文件成功，回测路径: {result_path}")
                    success = True
                else:
                    logger.warning(f"回测结果文件不存在，回测ID: {backtest_id}")
            except Exception as file_e:
                logger.error(f"从文件系统删除回测结果文件失败: {file_e}")
                logger.exception(file_e)
            
            return success
        except Exception as e:
            logger.error(f"删除回测结果失败: {e}")
            logger.exception(e)
            return False
    
    def list_backtest_results(self):
        """
        列出所有回测结果
        
        :return: 回测结果列表
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import BacktestTask
            import json
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            
            try:
                # 从数据库中获取回测任务列表
                tasks = db.query(BacktestTask).order_by(BacktestTask.created_at.desc()).all()
                
                backtest_list = []
                for task in tasks:
                    try:
                        # 提取关键信息
                        backtest_info = {
                            "id": task.id,
                            "strategy_name": task.strategy_name,
                            "created_at": format_datetime(task.created_at),
                            "status": task.status
                        }

                        # 首先尝试从文件系统加载合并后的回测结果
                        logger.info(f"尝试从文件系统加载回测结果，任务ID: {task.id}")
                        file_result = self.load_backtest_result(task.id)
                        if file_result:
                            logger.info(f"文件系统加载成功，任务ID: {task.id}")
                            # 从合并结果中提取指标
                            if "summary" in file_result:
                                logger.info(f"回测结果包含summary字段，任务ID: {task.id}")
                                # 多货币对回测结果
                                if "total_return" in file_result["summary"]:
                                    logger.info(f"summary中包含total_return: {file_result['summary']['total_return']}, 任务ID: {task.id}")
                                    # 只有当total_return不是-100.0时才使用它
                                    if float(file_result["summary"]["total_return"]) != -100.0:
                                        backtest_info["total_return"] = round(float(file_result["summary"]["total_return"]), 2)
                                if "average_max_drawdown" in file_result["summary"]:
                                    logger.info(f"summary中包含average_max_drawdown: {file_result['summary']['average_max_drawdown']}, 任务ID: {task.id}")
                                    backtest_info["max_drawdown"] = round(float(file_result["summary"]["average_max_drawdown"]), 2)
                            
                            # 检查是否需要从metrics或currencies部分提取指标
                            if not backtest_info.get("total_return") or not backtest_info.get("max_drawdown"):
                                if "metrics" in file_result:
                                    logger.info(f"回测结果包含metrics字段，任务ID: {task.id}")
                                    # 单个货币对回测结果
                                    for metric in file_result["metrics"]:
                                        # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                                        metric_key = metric.get("key", metric.get("name", ""))
                                        metric_name = metric.get("name", "")
                                        
                                        if not backtest_info.get("total_return") and (metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率"):
                                            logger.info(f"找到Return [%]指标: {metric['value']}, 任务ID: {task.id}")
                                            backtest_info["total_return"] = round(float(metric["value"]), 2)
                                        elif not backtest_info.get("max_drawdown") and (metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤"):
                                            logger.info(f"找到Max. Drawdown [%]指标: {metric['value']}, 任务ID: {task.id}")
                                            backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
                                        
                                        # 如果已经找到total_return和max_drawdown，就跳出循环
                                        if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                            break
                                elif "currencies" in file_result:
                                    logger.info(f"回测结果包含currencies字段，任务ID: {task.id}")
                                    # 从currencies部分的回测结果中提取指标
                                    for symbol, currency_result in file_result["currencies"].items():
                                        if currency_result.get("status") == "success" and "metrics" in currency_result:
                                            logger.info(f"尝试从货币对 {symbol} 的回测结果中提取指标，任务ID: {task.id}")
                                            for metric in currency_result["metrics"]:
                                                # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                                                metric_key = metric.get("key", metric.get("name", ""))
                                                metric_name = metric.get("name", "")
                                                
                                                if not backtest_info.get("total_return") and (metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率"):
                                                    logger.info(f"找到Return [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                    backtest_info["total_return"] = round(float(metric["value"]), 2)
                                                elif not backtest_info.get("max_drawdown") and (metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤"):
                                                    logger.info(f"找到Max. Drawdown [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                    backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
                                                
                                                # 如果已经找到total_return和max_drawdown，就跳出循环
                                                if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                                    break
                                            
                                            # 如果已经找到total_return和max_drawdown，就跳出循环
                                            if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                                break
                        else:
                            logger.warning(f"文件系统加载失败，任务ID: {task.id}")
                            # 如果文件系统加载失败，尝试从数据库获取
                            if task.status == "completed" and task.result_id:
                                logger.info(f"尝试从数据库获取回测结果，任务ID: {task.id}, result_id: {task.result_id}")
                                from collector.db.models import BacktestResult
                                result = db.query(BacktestResult).filter_by(id=task.result_id).first()
                                if result and result.metrics:
                                    logger.info(f"数据库加载成功，任务ID: {task.id}")
                                    try:
                                        metrics = json.loads(result.metrics)
                                        for metric in metrics:
                                            # 同时检查指标的key和name字段，确保在不同语言设置下都能找到正确的指标
                                            metric_key = metric.get("key", metric.get("name", ""))
                                            metric_name = metric.get("name", "")
                                            
                                            if metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率":
                                                logger.info(f"找到Return [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                backtest_info["total_return"] = round(float(metric["value"]), 2)
                                            elif metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤":
                                                logger.info(f"找到Max. Drawdown [%]指标: {metric['value']}, 任务ID: {task.id}")
                                                backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
                                    except Exception as e:
                                        logger.warning(f"解析回测结果指标失败: {task.id}, 错误: {e}")
                                else:
                                    logger.warning(f"数据库中未找到回测结果，任务ID: {task.id}")

                        backtest_list.append(backtest_info)
                    except Exception as e:
                        logger.error(f"解析回测任务记录失败: {task.id}, 错误: {e}")
                
                logger.info(f"从数据库获取回测结果列表成功，共 {len(backtest_list)} 个回测结果")
                return backtest_list
            except Exception as db_e:
                logger.error(f"从数据库获取回测结果列表失败: {db_e}")
                logger.exception(db_e)
                # 如果数据库查询失败，回退到从文件系统读取
                return self._list_backtest_results_from_files()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"获取回测结果列表失败: {e}")
            logger.exception(e)
            # 如果初始化数据库失败，回退到从文件系统读取
            return self._list_backtest_results_from_files()
    
    def _list_backtest_results_from_files(self):
        """
        从文件系统中列出所有回测结果（回退方案）
        
        :return: 回测结果列表
        """
        try:
            # 获取所有回测结果文件
            result_files = list(self.backtest_result_dir.glob("*.json"))
            backtest_list = []
            
            for file in result_files:
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        result = json.load(f)
                    
                    # 提取关键信息
                    backtest_info = {
                        "id": file.stem,
                        "strategy_name": result.get("strategy_name", "未知策略"),
                        "created_at": file.stem.split("_")[-1] if "_" in file.stem else file.stem,
                        "status": result.get("status", "未知状态")
                    }

                    # 优先处理多货币对回测结果
                    if "summary" in result:
                        # 多货币对回测结果
                        if "total_return" in result["summary"]:
                            # 只有当total_return不是-100.0时才使用它
                            if float(result["summary"]["total_return"]) != -100.0:
                                backtest_info["total_return"] = round(float(result["summary"]["total_return"]), 2)
                        if "average_max_drawdown" in result["summary"]:
                            backtest_info["max_drawdown"] = round(float(result["summary"]["average_max_drawdown"]), 2)
                    
                    # 检查是否需要从metrics或currencies部分提取指标
                    if not backtest_info.get("total_return") or not backtest_info.get("max_drawdown"):
                        if "metrics" in result:
                            for metric in result["metrics"]:
                                if not backtest_info.get("total_return") and (metric.get("key") == "Return [%]" or metric.get("name") == "Return [%]" or metric.get("name") == "总收益率"):
                                    backtest_info["total_return"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                elif not backtest_info.get("max_drawdown") and (metric.get("key") == "Max. Drawdown [%]" or metric.get("name") == "Max. Drawdown [%]" or metric.get("name") == "最大回撤"):
                                    backtest_info["max_drawdown"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                
                                # 如果已经找到total_return和max_drawdown，就跳出循环
                                if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                    break
                        if "currencies" in result:
                            for symbol, currency_result in result["currencies"].items():
                                if currency_result.get("status") == "success" and "metrics" in currency_result:
                                    for metric in currency_result["metrics"]:
                                        if not backtest_info.get("total_return") and (metric.get("key") == "Return [%]" or metric.get("name") == "Return [%]" or metric.get("name") == "总收益率"):
                                            backtest_info["total_return"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                        elif not backtest_info.get("max_drawdown") and (metric.get("key") == "Max. Drawdown [%]" or metric.get("name") == "Max. Drawdown [%]" or metric.get("name") == "最大回撤"):
                                            backtest_info["max_drawdown"] = round(float(metric["value"]), 2) if isinstance(metric["value"], (int, float)) else metric["value"]
                                        
                                        # 如果已经找到total_return和max_drawdown，就跳出循环
                                        if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                            break
                                    
                                    # 如果已经找到total_return和max_drawdown，就跳出循环
                                    if backtest_info.get("total_return") and backtest_info.get("max_drawdown"):
                                        break

                    backtest_list.append(backtest_info)
                except Exception as e:
                    logger.error(f"解析回测结果文件失败: {file}, 错误: {e}")
            
            # 按创建时间排序
            backtest_list.sort(key=lambda x: x["created_at"], reverse=True)
            
            logger.info(f"从文件系统获取回测结果列表成功，共 {len(backtest_list)} 个回测结果")
            return backtest_list
        except Exception as e:
            logger.error(f"从文件系统获取回测结果列表失败: {e}")
            logger.exception(e)
            return []
    
    def get_replay_data(self, backtest_id, symbol=None):
        """
        获取回放数据
        
        :param backtest_id: 回测ID
        :param symbol: 可选，指定货币对，用于多货币对回测结果
        :return: 回放数据
        """
        try:
            # 加载回测结果
            result = self.load_backtest_result(backtest_id)
            if not result:
                return {
                    "status": "failed",
                    "message": f"回测结果不存在: {backtest_id}"
                }
            
            # 处理多货币对回测结果
            target_result = result
            if symbol and "currencies" in result:
                # 多货币对回测结果，根据symbol选择对应的结果
                if symbol in result["currencies"]:
                    target_result = result["currencies"][symbol]
                else:
                    return {
                        "status": "failed",
                        "message": f"货币对 {symbol} 不存在于回测结果中"
                    }
            
            # 准备回放数据
            replay_data = {
                "kline_data": [],
                "trade_signals": [],
                "equity_data": [],
                "metadata": {
                    "symbol": target_result.get("backtest_config", {}).get("symbol", "BTCUSDT"),
                    "interval": target_result.get("backtest_config", {}).get("interval", "15m"),
                    "strategy_name": target_result.get("strategy_name", "未知策略")
                }
            }
            
            # 从策略数据中提取K线数据
            if "strategy_data" in target_result:
                for data in target_result["strategy_data"]:
                    # 尝试多种时间字段名
                    time_value = None
                    
                    # 检查常见的时间字段
                    for time_field in ["datetime", "Open_time", "open_time", "timestamp", "time", "date"]:
                        if time_field in data and data[time_field]:
                            time_value = data[time_field]
                            break
                    
                    # 如果没有找到时间字段，跳过该数据项
                    if not time_value:
                        logger.warning(f"策略数据中缺失时间字段: {list(data.keys())}")
                        continue
                    
                    # 转换为毫秒级时间戳
                    timestamp = None
                    if isinstance(time_value, (int, float)):
                        # 如果是数值类型，假设已经是时间戳
                        # 判断是秒级还是毫秒级
                        if time_value > 10000000000:  # 毫秒级时间戳（大于2001年）
                            timestamp = int(time_value)
                        else:  # 秒级时间戳
                            timestamp = int(time_value * 1000)
                    else:
                        # 如果是字符串或datetime类型，转换为毫秒级时间戳
                        from datetime import datetime
                        try:
                            if isinstance(time_value, str):
                                dt = datetime.fromisoformat(time_value.replace(' ', 'T'))
                            else:
                                dt = time_value
                            timestamp = int(dt.timestamp() * 1000)
                        except Exception as e:
                            logger.warning(f"无法转换时间字段: {time_value}, 错误: {e}")
                            continue
                    
                    # 构建K线数据项（与collector的klines接口格式保持一致）
                    kline_item = {
                        "timestamp": timestamp,
                        "open": float(data.get("Open", 0)),
                        "close": float(data.get("Close", 0)),
                        "high": float(data.get("High", 0)),
                        "low": float(data.get("Low", 0)),
                        "volume": float(data.get("Volume", 0)),
                        "turnover": 0.0  # 回测数据中没有成交额信息，保持为0
                    }
                    replay_data["kline_data"].append(kline_item)
            
            # 从交易记录中提取交易信号
            if "trades" in target_result:
                for trade in target_result["trades"]:
                    signal_item = {
                        "time": trade.get("EntryTime", ""),
                        "type": "buy" if trade.get("Direction") == "多单" else "sell",
                        "price": trade.get("EntryPrice", 0),
                        "size": abs(trade.get("Size", 0)),
                        "trade_id": trade.get("ID", "")
                    }
                    replay_data["trade_signals"].append(signal_item)
            
            # 从资金曲线中提取权益数据
            if "equity_curve" in target_result:
                for equity in target_result["equity_curve"]:
                    equity_item = {
                        "time": equity.get("datetime", ""),
                        "equity": equity.get("Equity", 0)
                    }
                    replay_data["equity_data"].append(equity_item)
            
            logger.info(f"获取回放数据成功，回测ID: {backtest_id}")
            return {
                "status": "success",
                "message": "获取回放数据成功",
                "data": replay_data
            }
        except Exception as e:
            logger.error(f"获取回放数据失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def get_backtest_symbols(self, backtest_id):
        """
        获取回测包含的所有货币对信息
        
        :param backtest_id: 回测ID
        :return: 货币对列表及相关元数据
        """
        try:
            logger.info(f"开始获取回测货币对列表，回测ID: {backtest_id}")
            
            # 首先尝试从文件系统加载回测结果（优先获取合并后的多货币对结果）
            result = self.load_backtest_result(backtest_id)
            
            # 如果文件系统中没有找到，再尝试从数据库加载
            if not result:
                logger.warning(f"回测结果在文件系统中不存在，尝试从数据库加载，回测ID: {backtest_id}")
                from collector.db.database import SessionLocal, init_database_config
                from collector.db.models import BacktestResult
                import json
                
                # 初始化数据库配置
                init_database_config()
                db = SessionLocal()
                
                try:
                    # 从数据库中获取回测结果
                    result_record = db.query(BacktestResult).filter_by(id=backtest_id).first()
                    
                    if not result_record:
                        return {
                            "status": "failed",
                            "message": f"回测结果不存在: {backtest_id}"
                        }
                    else:
                        # 从数据库中获取回测结果
                        result = {
                            "task_id": result_record.id,
                            "status": "success",
                            "message": "回测完成",
                            "strategy_name": result_record.strategy_name,
                            "backtest_config": {},  # 从回测任务中获取
                            "metrics": json.loads(result_record.metrics),
                            "trades": json.loads(result_record.trades),
                            "equity_curve": json.loads(result_record.equity_curve),
                            "strategy_data": json.loads(result_record.strategy_data)
                        }
                        
                        # 获取回测配置
                        from collector.db.models import BacktestTask
                        task = db.query(BacktestTask).filter_by(id=result_record.task_id).first()
                        if task:
                            result["backtest_config"] = json.loads(task.backtest_config)
                except Exception as db_e:
                    logger.error(f"从数据库获取回测结果失败: {db_e}")
                    logger.exception(db_e)
                    return {
                        "status": "failed",
                        "message": f"从数据库获取回测结果失败: {str(db_e)}"
                    }
                finally:
                    db.close()
            
            if not result:
                return {
                    "status": "failed",
                    "message": f"回测结果不存在: {backtest_id}"
                }
            
            symbols = []
            
            # 处理多货币对回测结果
            if "currencies" in result:
                # 多货币对回测结果，返回所有货币对
                for symbol, currency_result in result["currencies"].items():
                    symbols.append({
                        "symbol": symbol,
                        "status": currency_result.get("status", "success"),
                        "message": currency_result.get("message", "回测成功")
                    })
            else:
                # 单货币对回测结果，返回单一货币对
                symbol = result.get("backtest_config", {}).get("symbol", "BTCUSDT")
                symbols.append({
                    "symbol": symbol,
                    "status": result.get("status", "success"),
                    "message": result.get("message", "回测成功")
                })
            
            logger.info(f"获取回测货币对列表成功，回测ID: {backtest_id}, 货币对数量: {len(symbols)}")
            return {
                "status": "success",
                "message": "获取回测货币对列表成功",
                "data": {
                    "symbols": symbols,
                    "total": len(symbols)
                }
            }
        except Exception as e:
            logger.error(f"获取回测货币对列表失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }
    
    def create_executor_config(self, executor_type, params):
        """
        创建执行器配置
        
        :param executor_type: 执行器类型
        :param params: 执行器参数
        :return: 执行器配置
        """
        try:
            # 执行器类型映射
            executor_classes = {
                "simulator": "qlib.backtest.executor.SimulatorExecutor",
                "nested": "qlib.backtest.executor.NestedExecutor"
            }
            
            # 获取执行器类路径
            executor_class = executor_classes.get(executor_type)
            if not executor_class:
                logger.error(f"不支持的执行器类型: {executor_type}")
                return None
            
            # 创建执行器配置
            executor_config = {
                "class": executor_class,
                "module_path": None,
                "kwargs": params
            }
            
            logger.info(f"执行器配置创建成功，执行器类型: {executor_type}")
            return executor_config
        except Exception as e:
            logger.error(f"执行器配置创建失败: {e}")
            logger.exception(e)
            return None
