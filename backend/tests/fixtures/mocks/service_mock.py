"""
服务层Mock模块

提供服务层的Mock对象
"""

from unittest.mock import Mock, MagicMock
from typing import Dict, Any, List, Optional


class MockStrategyService:
    """Mock策略服务"""
    
    def __init__(self):
        self.strategies = {
            "sma_cross": {
                "name": "sma_cross",
                "file_name": "sma_cross.py",
                "file_path": "/backend/strategies/sma_cross.py",
                "description": "基于SMA交叉的策略",
                "version": "1.0.0",
                "params": [
                    {
                        "name": "n1",
                        "type": "int",
                        "default": 10,
                        "description": "短期移动平均线周期"
                    },
                    {
                        "name": "n2",
                        "type": "int",
                        "default": 20,
                        "description": "长期移动平均线周期"
                    }
                ],
                "source": "files"
            }
        }
    
    def get_strategy_list(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取策略列表"""
        strategies = list(self.strategies.values())
        if source:
            strategies = [s for s in strategies if s.get("source") == source]
        return strategies
    
    def get_strategy_detail(self, strategy_name: str, file_content: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取策略详情"""
        return self.strategies.get(strategy_name)
    
    def upload_strategy_file(self, strategy_name: str, file_content: str, 
                           version: Optional[str] = None, description: Optional[str] = None,
                           tags: Optional[List[str]] = None, strategy_id: Optional[int] = None) -> bool:
        """上传策略文件"""
        self.strategies[strategy_name] = {
            "name": strategy_name,
            "file_name": f"{strategy_name}.py",
            "file_path": f"/backend/strategies/{strategy_name}.py",
            "description": description or "",
            "version": version or "1.0.0",
            "params": [],
            "source": "files"
        }
        return True
    
    def load_strategy(self, strategy_name: str) -> Optional[Any]:
        """加载策略类"""
        if strategy_name in self.strategies:
            return Mock()  # 返回策略类的mock
        return None
    
    def delete_strategy(self, strategy_name: str) -> bool:
        """删除策略"""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            return True
        return False


class MockBacktestService:
    """Mock回测服务"""
    
    def __init__(self):
        self.backtests = {}
        self.running_tasks = {}
    
    def list_backtest_results(self) -> List[Dict[str, Any]]:
        """获取回测结果列表"""
        return [
            {
                "id": "bt_1234567890",
                "strategy_name": "sma_cross",
                "symbol": "BTCUSDT",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00"
            }
        ]
    
    def run_backtest(self, strategy_config: Dict[str, Any], 
                    backtest_config: Dict[str, Any]) -> Dict[str, Any]:
        """执行回测"""
        task_id = f"bt_{hash(str(strategy_config) + str(backtest_config))}"
        return {
            "task_id": task_id,
            "status": "completed",
            "message": "回测完成"
        }
    
    def stop_backtest(self, task_id: str) -> Dict[str, Any]:
        """终止回测"""
        if task_id in self.running_tasks:
            return {"status": "success", "message": "回测已终止"}
        return {"status": "error", "message": "任务不存在"}
    
    def analyze_backtest(self, backtest_id: str) -> Dict[str, Any]:
        """分析回测结果"""
        return {
            "status": "success",
            "backtest_id": backtest_id,
            "metrics": {
                "total_return": 0.15,
                "sharpe_ratio": 1.2,
                "max_drawdown": 0.05
            }
        }
    
    def delete_backtest_result(self, backtest_id: str) -> bool:
        """删除回测结果"""
        return True
    
    def get_backtest_symbols(self, backtest_id: str) -> Dict[str, Any]:
        """获取回测货币对列表"""
        return {
            "status": "success",
            "data": {
                "symbols": [
                    {"symbol": "BTCUSDT", "status": "success", "message": "回测成功"},
                    {"symbol": "ETHUSDT", "status": "success", "message": "回测成功"}
                ],
                "total": 2
            }
        }
    
    def get_replay_data(self, backtest_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取回测回放数据"""
        return {
            "status": "success",
            "data": {
                "kline_data": [
                    {
                        "timestamp": 1609459200000,
                        "open": 50000.0,
                        "high": 51000.0,
                        "low": 49000.0,
                        "close": 50500.0,
                        "volume": 1000.0
                    }
                ],
                "trade_signals": [
                    {
                        "time": "2024-01-01 10:00:00",
                        "type": "buy",
                        "price": 50000.0,
                        "size": 1.0,
                        "trade_id": "trade_001"
                    }
                ],
                "equity_data": [
                    {"time": "2024-01-01 00:00:00", "equity": 10000.0}
                ]
            }
        }
    
    def upload_strategy_file(self, strategy_name: str, file_content: str) -> bool:
        """上传策略文件"""
        return True


class MockSystemConfig:
    """Mock系统配置"""
    
    _configs = {}
    
    @classmethod
    def get(cls, key: str) -> Optional[str]:
        """获取配置值"""
        config = cls._configs.get(key)
        if config and config.get("is_sensitive"):
            return "******"
        return config.get("value") if config else None
    
    @classmethod
    def get_with_details(cls, key: str) -> Optional[Dict[str, Any]]:
        """获取配置详情"""
        config = cls._configs.get(key)
        if config and config.get("is_sensitive"):
            config = config.copy()
            config["value"] = "******"
        return config
    
    @classmethod
    def get_all_with_details(cls) -> Dict[str, Dict[str, Any]]:
        """获取所有配置详情"""
        result = {}
        for key, config in cls._configs.items():
            result[key] = config.copy()
            if config.get("is_sensitive"):
                result[key]["value"] = "******"
        return result
    
    @classmethod
    def set(cls, key: str, value: str, description: str = "", 
            plugin: Optional[str] = None, name: Optional[str] = None,
            is_sensitive: bool = False) -> bool:
        """设置配置"""
        cls._configs[key] = {
            "key": key,
            "value": value,
            "description": description,
            "plugin": plugin,
            "name": name or key,
            "is_sensitive": is_sensitive
        }
        return True
    
    @classmethod
    def delete(cls, key: str) -> bool:
        """删除配置"""
        if key in cls._configs:
            del cls._configs[key]
            return True
        return False
    
    @classmethod
    def clear(cls):
        """清除所有配置"""
        cls._configs.clear()


# 预设测试配置
MockSystemConfig.set("test_key", "test_value", "测试配置")
MockSystemConfig.set("api_key", "secret_api_key", "API密钥", is_sensitive=True)
