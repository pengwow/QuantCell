import json
import uuid
from datetime import datetime, timedelta
from loguru import logger
from collector.db.database import SessionLocal, init_database_config
from collector.db.models import BacktestResult, BacktestTask
from strategy.service import StrategyService

class DemoService:
    """
    演示数据服务
    用于生成和管理演示用的策略和回测数据
    """
    
    DEMO_STRATEGY_NAME = "MACD_Demo_Strategy"
    DEMO_TAG = "demo"
    
    DEMO_STRATEGY_CONTENT = """
from backtesting import Strategy
from backtesting.lib import crossover
import talib

class MACD_Demo_Strategy(Strategy):
    '''
    MACD演示策略
    
    这是一个用于演示系统的MACD策略，仅用于展示功能。
    '''
    
    # 定义参数
    fast_period = 12
    slow_period = 26
    signal_period = 9
    
    def init(self):
        # 计算MACD
        close = self.data.Close
        self.macd, self.signal, self.hist = self.I(talib.MACD, close, self.fast_period, self.slow_period, self.signal_period)
    
    def next(self):
        # 简单的金叉死叉逻辑
        if crossover(self.macd, self.signal):
            self.buy()
        elif crossover(self.signal, self.macd):
            self.sell()
"""

    def __init__(self):
        self.strategy_service = StrategyService()
        init_database_config()

    def ensure_demo_data(self):
        """
        确保演示数据存在
        如果不存在则自动生成
        """
        try:
            logger.info("开始检查演示数据...")
            
            # 1. 检查并创建演示策略
            self._ensure_demo_strategy()
            
            # 2. 检查并创建演示回测结果
            self._ensure_demo_backtest_result()
            
            logger.info("演示数据检查完成")
        except Exception as e:
            logger.error(f"检查演示数据失败: {e}")
            logger.exception(e)

    def _ensure_demo_strategy(self):
        """确保演示策略存在"""
        # 检查策略是否存在且包含demo标签
        strategy_list = self.strategy_service.get_strategy_list(source="db")
        demo_strategy = next((s for s in strategy_list if s["name"] == self.DEMO_STRATEGY_NAME), None)
        
        if not demo_strategy:
            logger.info(f"演示策略 {self.DEMO_STRATEGY_NAME} 不存在，正在创建...")
            success = self.strategy_service.upload_strategy_file(
                strategy_name=self.DEMO_STRATEGY_NAME,
                file_content=self.DEMO_STRATEGY_CONTENT,
                description="系统自动生成的演示策略",
                tags=[self.DEMO_TAG]
            )
            if success:
                logger.info(f"演示策略 {self.DEMO_STRATEGY_NAME} 创建成功")
            else:
                logger.error(f"演示策略 {self.DEMO_STRATEGY_NAME} 创建失败")
        else:
            # 检查是否有demo标签，如果没有则更新
            if self.DEMO_TAG not in demo_strategy.get("tags", []):
                logger.info(f"演示策略 {self.DEMO_STRATEGY_NAME} 缺少demo标签，正在更新...")
                tags = demo_strategy.get("tags", [])
                tags.append(self.DEMO_TAG)
                self.strategy_service.upload_strategy_file(
                    strategy_name=self.DEMO_STRATEGY_NAME,
                    file_content=self.DEMO_STRATEGY_CONTENT, # 重新上传内容
                    description=demo_strategy.get("description"),
                    tags=tags,
                    id=None # 会根据name自动更新
                )

    def _ensure_demo_backtest_result(self):
        """确保演示回测结果存在"""
        db = SessionLocal()
        try:
            # 检查是否存在关联该策略的演示回测任务
            # 我们通过查找特定的task_id或者result_id来判断，或者查询metrics中包含特定标识
            # 这里简单起见，我们查询策略名为DEMO_STRATEGY_NAME的最近一条结果
            
            existing_result = db.query(BacktestResult).filter_by(strategy_name=self.DEMO_STRATEGY_NAME).first()
            
            if not existing_result:
                logger.info(f"演示回测结果不存在，正在生成...")
                
                # 生成模拟数据
                task_id = f"demo_task_{uuid.uuid4()}"
                result_id = f"demo_result_{uuid.uuid4()}"
                
                # 创建对应的任务记录
                task = BacktestTask(
                    id=task_id,
                    strategy_name=self.DEMO_STRATEGY_NAME,
                    backtest_config=json.dumps({
                        "symbols": ["BTC/USDT"],
                        "start_time": "2024-01-01",
                        "end_time": "2024-02-01",
                        "interval": "15m",
                        "commission": 0.001,
                        "initial_cash": 100000
                    }),
                    status="completed",
                    result_id=result_id,
                    completed_at=datetime.now()
                )
                db.add(task)
                
                # 创建结果记录
                # 这里构造一些好看的假数据
                metrics = {
                    "Start": "2024-01-01 00:00:00",
                    "End": "2024-02-01 00:00:00",
                    "Duration": "31 days",
                    "Exposure Time [%]": 85.5,
                    "Equity Final [$]": 115000.0,
                    "Equity Peak [$]": 118000.0,
                    "Return [%]": 15.0,
                    "Buy & Hold Return [%]": 5.0,
                    "Return (Ann.) [%]": 350.0,
                    "Volatility (Ann.) [%]": 45.0,
                    "Sharpe Ratio": 2.5,
                    "Sortino Ratio": 4.8,
                    "Calmar Ratio": 8.5,
                    "Max. Drawdown [%]": -5.2,
                    "Avg. Drawdown [%]": -2.1,
                    "Max. Drawdown Duration": "5 days",
                    "Avg. Drawdown Duration": "2 days",
                    "# Trades": 50,
                    "Win Rate [%]": 65.0,
                    "Best Trade [%]": 8.5,
                    "Worst Trade [%]": -3.2,
                    "Avg. Trade [%]": 1.2,
                    "Max. Trade Duration": "2 days",
                    "Avg. Trade Duration": "8 hours",
                    "Profit Factor": 2.1,
                    "Expectancy [%]": 1.5,
                    "SQN": 3.2
                }
                
                # 简化的资金曲线数据
                equity_curve = [
                    {"time": "2024-01-01", "equity": 100000},
                    {"time": "2024-01-10", "equity": 105000},
                    {"time": "2024-01-20", "equity": 102000},
                    {"time": "2024-02-01", "equity": 115000}
                ]
                
                # 简化的交易记录
                trades = [
                    {
                        "Size": 1,
                        "EntryBar": 10,
                        "ExitBar": 20,
                        "EntryPrice": 40000,
                        "ExitPrice": 42000,
                        "PnL": 2000,
                        "ReturnPct": 0.05,
                        "EntryTime": "2024-01-02 10:00",
                        "ExitTime": "2024-01-03 14:00",
                        "Duration": "1 day 4 hours"
                    }
                ]

                result = BacktestResult(
                    id=result_id,
                    task_id=task_id,
                    strategy_name=self.DEMO_STRATEGY_NAME,
                    metrics=json.dumps(metrics),
                    trades=json.dumps(trades),
                    equity_curve=json.dumps(equity_curve),
                    strategy_data=json.dumps({})
                )
                db.add(result)
                
                db.commit()
                logger.info(f"演示回测结果创建成功: {result_id}")
            else:
                logger.info(f"演示回测结果已存在")
                
        except Exception as e:
            db.rollback()
            logger.error(f"创建演示回测结果失败: {e}")
            logger.exception(e)
        finally:
            db.close()

    def clean_demo_data(self):
        """
        清理演示数据
        删除所有tags包含demo的策略及关联的回测结果
        """
        try:
            logger.info("开始清理演示数据...")
            
            # 1. 查找所有demo策略
            strategy_list = self.strategy_service.get_strategy_list(source="db")
            demo_strategies = [s for s in strategy_list if self.DEMO_TAG in s.get("tags", [])]
            
            if not demo_strategies:
                logger.info("未发现演示策略")
                return

            db = SessionLocal()
            try:
                for strategy in demo_strategies:
                    name = strategy["name"]
                    logger.info(f"正在删除演示策略: {name}")
                    
                    # 删除关联的回测结果和任务
                    # 先查任务
                    tasks = db.query(BacktestTask).filter_by(strategy_name=name).all()
                    for task in tasks:
                        # 删除结果
                        db.query(BacktestResult).filter_by(task_id=task.id).delete()
                        # 删除任务
                        db.delete(task)
                    
                    # 删除策略 (通过service删除，会同时删除文件和DB记录)
                    self.strategy_service.delete_strategy(name)
                
                db.commit()
                logger.info(f"成功清理 {len(demo_strategies)} 个演示策略及其数据")
                
            except Exception as db_e:
                db.rollback()
                logger.error(f"数据库清理失败: {db_e}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"清理演示数据失败: {e}")
            logger.exception(e)
