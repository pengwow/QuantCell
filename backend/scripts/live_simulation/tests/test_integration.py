"""
集成测试

测试整个模拟测试系统的集成。
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from ..main import SimulationEngine
from ..config import SimulationConfig, DataConfig, PushConfig, QuantCellConfig, WorkerConfig


class TestSimulationEngine:
    """测试模拟引擎"""
    
    @pytest.fixture
    def temp_data_dir(self):
        """创建临时数据目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建示例数据
            data = {
                "timestamp": pd.date_range("2024-01-01", periods=100, freq="1min"),
                "open": [100.0 + i * 0.1 for i in range(100)],
                "high": [101.0 + i * 0.1 for i in range(100)],
                "low": [99.0 + i * 0.1 for i in range(100)],
                "close": [100.5 + i * 0.1 for i in range(100)],
                "volume": [1000 + i * 10 for i in range(100)],
            }
            df = pd.DataFrame(data)
            df.to_csv(Path(tmpdir) / "BTCUSDT_1m.csv", index=False)
            yield tmpdir
    
    @pytest.fixture
    def sample_config(self, temp_data_dir):
        """创建示例配置"""
        return SimulationConfig(
            name="test_simulation",
            data=DataConfig(
                source_type="file",
                file_path=temp_data_dir,
                symbols=["BTCUSDT"],
                intervals=["1m"],
            ),
            push=PushConfig(
                speed=10.0,  # 10倍速
                realtime=False,
            ),
            quantcell=QuantCellConfig(
                host="localhost",
                port=8000,
            ),
            workers=[
                WorkerConfig(
                    strategy_path="scripts/live_simulation/strategies/test_strategy.py",
                    strategy_class="TestStrategy",
                    symbols=["BTCUSDT"],
                )
            ],
            duration_hours=0.01,  # 很短的测试时间
        )
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, sample_config):
        """测试引擎初始化"""
        engine = SimulationEngine(sample_config)
        
        await engine.initialize()
        
        assert engine.state.value == "idle"
        assert engine.metrics.total_data_points == 100
        assert len(engine.worker_manager._workers) == 1
    
    @pytest.mark.asyncio
    async def test_data_loading(self, sample_config):
        """测试数据加载"""
        engine = SimulationEngine(sample_config)
        await engine.initialize()
        
        summary = engine.data_loader.get_data_summary()
        
        assert summary["total_points"] == 100
        assert "BTCUSDT_1m" in summary["data_points"]
    
    @pytest.mark.asyncio
    async def test_worker_registration(self, sample_config):
        """测试Worker注册"""
        engine = SimulationEngine(sample_config)
        await engine.initialize()
        
        workers = list(engine.worker_manager._workers.keys())
        
        assert len(workers) == 1
        assert "worker_0" in workers


class TestEndToEnd:
    """端到端测试"""
    
    @pytest.mark.asyncio
    async def test_data_pusher_flow(self):
        """测试数据推送流程"""
        from ..data_pusher import create_data_pusher
        from ..models import KlineData
        from ..config import PushConfig

        config = PushConfig(speed=100.0, batch_size=10)
        pusher = create_data_pusher(config)
        
        # 创建测试数据
        data = [
            KlineData(
                symbol="BTCUSDT",
                timestamp=datetime(2024, 1, 1, 0, i, 0),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
            )
            for i in range(50)
        ]
        
        pusher.load_data(data)
        
        # 注册测试处理器
        received = []
        def handler(msg):
            received.append(msg)
        
        pusher.register_handler(handler)
        
        # 启动推送
        await pusher.start()
        
        # 等待推送完成
        await asyncio.sleep(0.5)
        
        # 停止
        await pusher.stop()
        
        # 验证
        assert len(received) > 0
        assert pusher.get_state().value == "stopped"


class TestConfiguration:
    """配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = SimulationConfig()
        
        assert config.name == "simulation"
        assert config.push.speed == 1.0
        assert config.quantcell.host == "localhost"
    
    def test_config_validation(self):
        """测试配置验证"""
        from pydantic import ValidationError
        
        # 无效的数据源类型
        with pytest.raises(ValidationError):
            DataConfig(source_type="invalid")
        
        # 无效的推送速度
        with pytest.raises(ValidationError):
            PushConfig(speed=-1.0)
