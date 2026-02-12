"""
数据加载模块测试
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from ..data_loader import FileDataSource, DataLoader
from ..config import DataConfig
from ..models import KlineData


class TestFileDataSource:
    """测试文件数据源"""
    
    @pytest.fixture
    def temp_data_dir(self):
        """创建临时数据目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def sample_csv_data(self, temp_data_dir):
        """创建示例CSV数据"""
        data = {
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="1min"),
            "open": [100.0 + i * 0.1 for i in range(100)],
            "high": [101.0 + i * 0.1 for i in range(100)],
            "low": [99.0 + i * 0.1 for i in range(100)],
            "close": [100.5 + i * 0.1 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
        }
        df = pd.DataFrame(data)
        file_path = temp_data_dir / "BTCUSDT_1m.csv"
        df.to_csv(file_path, index=False)
        return file_path
    
    @pytest.mark.asyncio
    async def test_validate_existing_directory(self, temp_data_dir):
        """测试验证存在的目录"""
        source = FileDataSource(temp_data_dir)
        assert await source.validate() is True
    
    @pytest.mark.asyncio
    async def test_validate_non_existing_directory(self):
        """测试验证不存在的目录"""
        source = FileDataSource("/non/existing/path")
        assert await source.validate() is False
    
    @pytest.mark.asyncio
    async def test_load_csv_data(self, temp_data_dir, sample_csv_data):
        """测试加载CSV数据"""
        source = FileDataSource(temp_data_dir)
        
        data = await source.load_data("BTCUSDT", "1m")
        
        assert len(data) == 100
        assert isinstance(data[0], KlineData)
        assert data[0].symbol == "BTCUSDT"
        assert data[0].interval == "1m"
    
    @pytest.mark.asyncio
    async def test_load_data_with_time_filter(self, temp_data_dir, sample_csv_data):
        """测试带时间过滤的数据加载"""
        source = FileDataSource(temp_data_dir)
        
        start_time = datetime(2024, 1, 1, 0, 30)
        end_time = datetime(2024, 1, 1, 0, 50)
        
        data = await source.load_data("BTCUSDT", "1m", start_time, end_time)
        
        assert len(data) > 0
        assert all(d.timestamp >= start_time for d in data)
        assert all(d.timestamp <= end_time for d in data)


class TestDataLoader:
    """测试数据加载器"""
    
    @pytest.fixture
    def temp_data_dir(self):
        """创建临时数据目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建示例数据
            data = {
                "timestamp": pd.date_range("2024-01-01", periods=50, freq="1min"),
                "open": [100.0] * 50,
                "high": [101.0] * 50,
                "low": [99.0] * 50,
                "close": [100.5] * 50,
                "volume": [1000] * 50,
            }
            df = pd.DataFrame(data)
            df.to_csv(Path(tmpdir) / "BTCUSDT_1m.csv", index=False)
            yield tmpdir
    
    @pytest.mark.asyncio
    async def test_initialize_file_source(self, temp_data_dir):
        """测试初始化文件数据源"""
        config = DataConfig(
            source_type="file",
            file_path=temp_data_dir,
            symbols=["BTCUSDT"],
            intervals=["1m"],
        )
        
        loader = DataLoader(config)
        await loader.initialize()
        
        assert loader._source is not None
    
    @pytest.mark.asyncio
    async def test_load_all_data(self, temp_data_dir):
        """测试加载所有数据"""
        config = DataConfig(
            source_type="file",
            file_path=temp_data_dir,
            symbols=["BTCUSDT"],
            intervals=["1m"],
        )
        
        loader = DataLoader(config)
        await loader.initialize()
        
        data = await loader.load_all_data()
        
        assert "BTCUSDT_1m" in data
        assert len(data["BTCUSDT_1m"]) == 50
    
    @pytest.mark.asyncio
    async def test_get_data_summary(self, temp_data_dir):
        """测试获取数据摘要"""
        config = DataConfig(
            source_type="file",
            file_path=temp_data_dir,
            symbols=["BTCUSDT"],
            intervals=["1m"],
        )
        
        loader = DataLoader(config)
        await loader.initialize()
        await loader.load_all_data()
        
        summary = loader.get_data_summary()
        
        assert summary["total_symbols"] == 1
        assert summary["total_intervals"] == 1
        assert summary["total_points"] == 50
