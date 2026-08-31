"""
KlineFileManager 单元测试
"""

import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from utils.kline_file_manager import KlineFileManager


@pytest.fixture
def temp_dir():
    """创建临时测试目录"""
    dir_path = Path(tempfile.mkdtemp())
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def sample_df():
    """创建示例K线数据"""
    return pd.DataFrame(
        {
            "timestamp": [1704067200000, 1704153600000, 1704240000000],
            "open": [42000.0, 42500.0, 42800.0],
            "high": [43000.0, 43200.0, 43500.0],
            "low": [41500.0, 42000.0, 42500.0],
            "close": [42500.0, 42800.0, 43000.0],
            "volume": [1000.5, 1200.3, 950.8],
        }
    )


class TestKlineFileManagerInit:
    """测试初始化功能"""

    def test_init_with_default_base_dir(self):
        manager = KlineFileManager()
        assert manager.base_dir.name == "source"

    def test_init_with_custom_base_dir(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)
        assert manager.base_dir == temp_dir

    def test_base_dir_is_path_object(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)
        assert isinstance(manager.base_dir, Path)


class TestSaveKlines:
    """测试保存功能"""

    def test_save_spot_klines(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        result = manager.save_klines(df=sample_df, symbol="BTCUSDT", interval="1h", market_type="spot")

        assert result is True
        expected_path = temp_dir / "crypto" / "spot" / "klines" / "BTCUSDT" / "1h" / "2024-01.parquet"
        assert expected_path.exists()

    def test_save_future_klines(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        result = manager.save_klines(df=sample_df, symbol="ETHUSDT", interval="15m", market_type="future")

        assert result is True
        expected_path = temp_dir / "crypto" / "future" / "klines" / "ETHUSDT" / "15m" / "2024-01.parquet"
        assert expected_path.exists()

    def test_save_empty_dataframe(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        result = manager.save_klines(empty_df, "BTCUSDT", "1h")

        assert result is False

    def test_save_none_dataframe(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        result = manager.save_klines(None, "BTCUSDT", "1h")

        assert result is False

    def test_save_creates_monthly_files(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        # 创建跨月数据
        df_cross_months = pd.DataFrame(
            {
                "timestamp": [1704067200000, 1706745600000],  # 2024-01 和 2024-02
                "open": [42000.0, 43000.0],
                "high": [43000.0, 44000.0],
                "low": [41500.0, 42500.0],
                "close": [42500.0, 43500.0],
                "volume": [1000.5, 1100.6],
            }
        )

        result = manager.save_klines(df_cross_months, "BTCUSDT", "1h")

        assert result is True

        # 验证两个文件都创建
        jan_file = temp_dir / "crypto" / "spot" / "klines" / "BTCUSDT" / "1h" / "2024-01.parquet"
        feb_file = temp_dir / "crypto" / "spot" / "klines" / "BTCUSDT" / "1h" / "2024-02.parquet"

        assert jan_file.exists()
        assert feb_file.exists()


class TestLoadKlines:
    """测试加载功能"""

    def test_load_existing_data(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        # 先保存数据
        manager.save_klines(sample_df, "BTCUSDT", "1h")

        # 加载数据
        loaded_df = manager.load_klines(symbol="BTCUSDT", interval="1h", market_type="spot")

        assert len(loaded_df) == 3
        assert list(loaded_df.columns) == [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

    def test_load_nonexistent_symbol(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        loaded_df = manager.load_klines(symbol="NONEXISTENT", interval="1h")

        assert loaded_df.empty

    def test_load_nonexistent_interval(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        # 保存1h数据
        manager.save_klines(sample_df, "BTCUSDT", "1h")

        # 尝试加载不存在的周期
        loaded_df = manager.load_klines("BTCUSDT", "15m")

        assert loaded_df.empty

    def test_load_with_time_range(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        # 创建多天数据
        df_multi_day = pd.DataFrame(
            {
                "timestamp": [
                    1704067200000,  # 2024-01-01
                    1704153600000,  # 2024-01-02
                    1704240000000,  # 2024-01-03
                    1704326400000,  # 2024-01-04
                ],
                "open": [42000.0, 42500.0, 42800.0, 43000.0],
                "high": [43000.0, 43200.0, 43500.0, 43800.0],
                "low": [41500.0, 42000.0, 42500.0, 42800.0],
                "close": [42500.0, 42800.0, 43000.0, 43300.0],
                "volume": [1000.5, 1200.3, 950.8, 1050.2],
            }
        )

        manager.save_klines(df_multi_day, "BTCUSDT", "1h")

        # 加载时间范围内的数据
        loaded_df = manager.load_klines(
            symbol="BTCUSDT",
            interval="1h",
            start_time="2024-01-02T00:00:00",
            end_time="2024-01-03T23:59:59",
        )

        # 应该只加载第2和第3条记录（索引1和2）
        assert len(loaded_df) == 2


class TestAppendKlines:
    """测试追加功能"""

    def test_append_to_existing_file(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        # 第一次保存
        df1 = pd.DataFrame(
            {
                "timestamp": [1704067200000],
                "open": [42000.0],
                "high": [43000.0],
                "low": [41500.0],
                "close": [42500.0],
                "volume": [1000.5],
            }
        )
        manager.save_klines(df1, "BTCUSDT", "1h")

        # 追加数据
        df2 = pd.DataFrame(
            {
                "timestamp": [1704240000000],
                "open": [43000.0],
                "high": [43500.0],
                "low": [42500.0],
                "close": [43200.0],
                "volume": [1500.7],
            }
        )
        result = manager.append_klines(df2, "BTCUSDT", "1h")

        assert result is True

        # 验证合并后的数据
        loaded = manager.load_klines("BTCUSDT", "1h")
        assert len(loaded) == 2

    def test_append_empty_dataframe(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        empty_df = pd.DataFrame()
        result = manager.append_klines(empty_df, "BTCUSDT", "1h")

        assert result is False  # 空DataFrame应返回失败


class TestQueryFunctions:
    """测试查询功能"""

    def test_get_available_symbols(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        # 保存多个品种的数据
        manager.save_klines(sample_df, "BTCUSDT", "1h")
        manager.save_klines(sample_df, "ETHUSDT", "1h")

        symbols = manager.get_available_symbols(market_type="spot")

        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert len(symbols) == 2

    def test_get_available_intervals(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        # 保存不同周期的数据
        manager.save_klines(sample_df, "BTCUSDT", "1h")
        manager.save_klines(sample_df, "BTCUSDT", "15m")

        intervals = manager.get_available_intervals("BTCUSDT", market_type="spot")

        assert "1h" in intervals
        assert "15m" in intervals
        assert len(intervals) == 2

    def test_get_date_range(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        # 创建跨月数据
        df_cross_months = pd.DataFrame(
            {
                "timestamp": [1704067200000, 1706745600000],
                "open": [42000.0, 43000.0],
                "high": [43000.0, 44000.0],
                "low": [41500.0, 42500.0],
                "close": [42500.0, 43500.0],
                "volume": [1000.5, 1100.6],
            }
        )

        manager.save_klines(df_cross_months, "BTCUSDT", "1h")

        date_range = manager.get_date_range("BTCUSDT", "1h")

        assert date_range is not None
        assert date_range[0] == "2024-01"
        assert date_range[1] == "2024-02"


class TestDeleteKlines:
    """测试删除功能"""

    def test_delete_existing_data(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        # 先保存数据
        manager.save_klines(sample_df, "BTCUSDT", "1h")

        # 验证文件存在
        data_dir = temp_dir / "crypto" / "spot" / "klines" / "BTCUSDT" / "1h"
        assert data_dir.exists()

        # 删除数据
        result = manager.delete_klines("BTCUSDT", "1h")

        assert result is True
        assert not data_dir.exists()

    def test_delete_nonexistent_data(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        result = manager.delete_klines("NONEXISTENT", "1h")

        assert result is False


class TestStorageStats:
    """测试存储统计功能"""

    def test_get_storage_stats_empty(self, temp_dir):
        manager = KlineFileManager(base_dir=temp_dir)

        stats = manager.get_storage_stats()

        assert stats["total_files"] == 0
        assert stats["total_size_mb"] == 0.0
        assert stats["exists"]
        assert len(stats["symbols"]) == 0

    def test_get_storage_stats_with_data(self, temp_dir, sample_df):
        manager = KlineFileManager(base_dir=temp_dir)

        # 保存一些数据
        manager.save_klines(sample_df, "BTCUSDT", "1h")
        manager.save_klines(sample_df, "ETHUSDT", "15m")

        stats = manager.get_storage_stats()

        assert stats["total_files"] >= 2
        assert stats["total_size_mb"] > 0
        assert "BTCUSDT" in stats["symbols"]
        assert "ETHUSDT" in stats["symbols"]


class TestGlobalInstance:
    """测试全局单例"""

    def test_get_kline_file_manager_returns_instance(self):
        from utils.kline_file_manager import get_kline_file_manager

        manager1 = get_kline_file_manager()
        manager2 = get_kline_file_manager()

        # 应该返回同一个实例
        assert manager1 is manager2

    def test_global_instance_has_correct_type(self):
        from utils.kline_file_manager import get_kline_file_manager

        manager = get_kline_file_manager()

        assert isinstance(manager, KlineFileManager)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
