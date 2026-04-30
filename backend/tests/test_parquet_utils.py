# -*- coding: utf-8 -*-
"""
Parquet 工具函数单元测试

测试 utils/parquet_utils.py 模块的所有核心功能。
"""

import os
import pytest
import pandas as pd
from pathlib import Path


@pytest.fixture
def sample_kline_data():
    """生成测试用的 K线 数据"""
    return pd.DataFrame({
        'timestamp': [1704067200000, 1704067260000, 1704067320000],
        'open': [42000.0, 42300.0, 42200.0],
        'high': [42500.0, 42400.0, 42350.0],
        'low': [41800.0, 42100.0, 42000.0],
        'close': [42300.0, 42200.0, 42150.0],
        'volume': [1000.5, 800.2, 950.8]
    })


class TestSaveToParquet:
    """测试 save_to_parquet 函数"""

    def test_save_basic(self, tmp_path, sample_kline_data):
        """测试基本保存功能"""
        from utils.parquet_utils import save_to_parquet

        file_path = tmp_path / "test.parquet"
        result = save_to_parquet(sample_kline_data, file_path)

        assert result is True
        assert file_path.exists()

    def test_save_empty_dataframe(self, tmp_path):
        """测试保存空DataFrame"""
        from utils.parquet_utils import save_to_parquet

        df = pd.DataFrame()
        file_path = tmp_path / "empty.parquet"
        result = save_to_parquet(df, file_path)

        assert result is False

    def test_save_none_dataframe(self, tmp_path):
        """测试保存None DataFrame"""
        from utils.parquet_utils import save_to_parquet

        file_path = tmp_path / "none.parquet"
        result = save_to_parquet(None, file_path)

        assert result is False

    def test_save_creates_directory(self, sample_kline_data):
        """测试自动创建目录"""
        from utils.parquet_utils import save_to_parquet

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_path = Path(tmp_dir) / "nested" / "dir" / "test.parquet"
            result = save_to_parquet(sample_kline_data, nested_path)

            assert result is True
            assert nested_path.exists()


class TestLoadFromParquet:
    """测试 load_from_parquet 函数"""

    def test_load_basic(self, tmp_path, sample_kline_data):
        """测试基本加载功能"""
        from utils.parquet_utils import save_to_parquet, load_from_parquet

        # 先保存
        file_path = tmp_path / "test.parquet"
        save_to_parquet(sample_kline_data, file_path)

        # 再加载
        loaded_df = load_from_parquet(file_path)

        assert len(loaded_df) == 3
        assert list(loaded_df.columns) == list(sample_kline_data.columns)

    def test_load_nonexistent_file(self, tmp_path):
        """测试加载不存在的文件"""
        from utils.parquet_utils import load_from_parquet

        nonexistent_path = tmp_path / "nonexistent.parquet"
        loaded_df = load_from_parquet(nonexistent_path)

        assert loaded_df.empty

    def test_load_specific_columns(self, tmp_path, sample_kline_data):
        """测试只加载指定列"""
        from utils.parquet_utils import save_to_parquet, load_from_parquet

        # 先保存
        file_path = tmp_path / "test.parquet"
        save_to_parquet(sample_kline_data, file_path)

        # 只加载 close 列
        loaded_df = load_from_parquet(file_path, columns=['close'])

        assert len(loaded_df) == 3
        assert list(loaded_df.columns) == ['close']


class TestAppendToParquet:
    """测试 append_to_parquet 函数"""

    def test_append_to_new_file(self, tmp_path, sample_kline_data):
        """测试追加到新文件（等同于创建）"""
        from utils.parquet_utils import append_to_parquet, load_from_parquet

        file_path = tmp_path / "test.parquet"
        result = append_to_parquet(sample_kline_data, file_path)

        assert result is True
        loaded_df = load_from_parquet(file_path)
        assert len(loaded_df) == 3

    def test_append_to_existing_file(self, tmp_path, sample_kline_data):
        """测试追加到已存在的文件"""
        from utils.parquet_utils import append_to_parquet, load_from_parquet

        file_path = tmp_path / "test.parquet"

        # 第一次保存
        append_to_parquet(sample_kline_data, file_path)

        # 追加新数据
        new_data = pd.DataFrame({
            'timestamp': [1704067380000],
            'open': [42150.0],
            'high': [42200.0],
            'low': [42050.0],
            'close': [42180.0],
            'volume': [750.3]
        })
        append_to_parquet(new_data, file_path)

        # 验证合并后的数据
        loaded_df = load_from_parquet(file_path)
        assert len(loaded_df) == 4

    def test_append_deduplication(self, tmp_path, sample_kline_data):
        """测试追加时的去重功能"""
        from utils.parquet_utils import append_to_parquet, load_from_parquet

        file_path = tmp_path / "test.parquet"

        # 第一次保存
        append_to_parquet(sample_kline_data, file_path)

        # 追加包含重复时间戳的数据
        duplicate_data = pd.DataFrame({
            'timestamp': [1704067200000, 1704067380000],  # 第一个时间戳重复
            'open': [42001.0, 42150.0],  # 相同时间戳，不同价格
            'high': [42501.0, 42200.0],
            'low': [41801.0, 42050.0],
            'close': [42301.0, 42180.0],
            'volume': [1001.5, 750.3]
        })
        append_to_parquet(duplicate_data, file_path)

        # 验证去重后的数据（应该保留最新的，即4条记录）
        loaded_df = load_from_parquet(file_path)
        assert len(loaded_df) == 4


class TestConvertCsvToParquet:
    """测试 CSV 到 Parquet 的转换"""

    def test_convert_basic(self, tmp_path, sample_kline_data):
        """测试基本转换功能"""
        from utils.parquet_utils import convert_csv_to_parquet, load_from_parquet

        # 创建 CSV 文件
        csv_path = tmp_path / "test.csv"
        sample_kline_data.to_csv(csv_path, index=False)

        # 转换为 Parquet
        parquet_path = tmp_path / "test.parquet"
        result = convert_csv_to_parquet(csv_path, parquet_path)

        assert result is True
        assert parquet_path.exists()

        # 验证转换后的数据
        loaded_df = load_from_parquet(parquet_path)
        assert len(loaded_df) == 3

    def test_convert_nonexistent_csv(self, tmp_path):
        """测试转换不存在的CSV文件"""
        from utils.parquet_utils import convert_csv_to_parquet

        csv_path = tmp_path / "nonexistent.csv"
        parquet_path = tmp_path / "output.parquet"
        result = convert_csv_to_parquet(csv_path, parquet_path)

        assert result is False


class TestGetParquetInfo:
    """测试获取 Parquet 文件信息"""

    def test_get_info_basic(self, tmp_path, sample_kline_data):
        """测试基本信息获取"""
        from utils.parquet_utils import save_to_parquet, get_parquet_info

        file_path = tmp_path / "test.parquet"
        save_to_parquet(sample_kline_data, file_path)

        info = get_parquet_info(file_path)

        assert info['num_rows'] == 3
        assert info['num_columns'] == 6
        assert 'file_size_bytes' in info
        assert 'file_size_mb' in info

    def test_get_info_nonexistent(self, tmp_path):
        """测试获取不存在文件的信息"""
        from utils.parquet_utils import get_parquet_info

        nonexistent_path = tmp_path / "nonexistent.parquet"
        info = get_parquet_info(nonexistent_path)

        assert info == {}


class TestLoadKlineDataAuto:
    """测试智能加载函数（自动识别格式）"""

    def test_load_parquet_auto(self, tmp_path, sample_kline_data):
        """测试自动加载 Parquet 文件"""
        from utils.parquet_utils import save_to_parquet, load_kline_data_auto

        file_path = tmp_path / "data.parquet"
        save_to_parquet(sample_kline_data, file_path)

        # 使用 .parquet 后缀加载
        loaded_df = load_kline_data_auto(file_path)
        assert len(loaded_df) == 3

    def test_load_csv_fallback(self, tmp_path, sample_kline_data):
        """测试回退到 CSV 格式加载"""
        from utils.parquet_utils import load_kline_data_auto

        csv_path = tmp_path / "data.csv"
        sample_kline_data.to_csv(csv_path, index=False)

        # 使用 .csv 后缀加载
        loaded_df = load_kline_data_auto(csv_path)
        assert len(loaded_df) == 3

    def test_load_auto_detect(self, tmp_path, sample_kline_data):
        """测试无后缀时自动检测格式"""
        from utils.parquet_utils import save_to_parquet, load_kline_data_auto

        # 只创建 Parquet 文件
        parquet_path = tmp_path / "data.parquet"
        save_to_parquet(sample_kline_data, parquet_path)

        # 不带后缀的路径，应该自动检测到 Parquet
        base_path = tmp_path / "data"
        loaded_df = load_kline_data_auto(base_path)
        assert len(loaded_df) == 3


class TestListParquetFiles:
    """测试列出 Parquet 文件"""

    def test_list_files(self, tmp_path, sample_kline_data):
        """测试列出文件功能"""
        from utils.parquet_utils import save_to_parquet, list_parquet_files

        # 创建多个 Parquet 文件
        for i in range(3):
            file_path = tmp_path / f"file_{i}.parquet"
            save_to_parquet(sample_kline_data, file_path)

        files = list_parquet_files(tmp_path)
        assert len(files) == 3

    def test_list_empty_directory(self, tmp_path):
        """测试空目录"""
        from utils.parquet_utils import list_parquet_files

        files = list_parquet_files(tmp_path)
        assert files == []

    def test_list_nonexistent_directory(self):
        """测试不存在的目录"""
        from utils.parquet_utils import list_parquet_files

        files = list_parquet_files(Path("/nonexistent/directory"))
        assert files == []


class TestBatchConvert:
    """测试批量转换功能"""

    def test_batch_convert(self, tmp_path, sample_kline_data):
        """测试批量转换 CSV 到 Parquet"""
        from utils.parquet_utils import batch_convert_csv_to_parquet, list_parquet_files

        # 创建多个 CSV 文件
        for i in range(3):
            csv_path = tmp_path / f"file_{i}.csv"
            sample_kline_data.to_csv(csv_path, index=False)

        # 批量转换
        stats = batch_convert_csv_to_parquet(tmp_path)

        assert stats['total'] == 3
        assert stats['success'] == 3
        assert stats['failed'] == 0

        # 验证 Parquet 文件已创建
        parquet_files = list_parquet_files(tmp_path)
        assert len(parquet_files) == 3


class TestDataIntegrity:
    """测试数据完整性"""

    def test_roundtrip_preserves_data(self, tmp_path, sample_kline_data):
        """测试保存-加载数据完整性"""
        from utils.parquet_utils import save_to_parquet, load_from_parquet

        original_df = sample_kline_data.copy()

        # 保存并加载
        file_path = tmp_path / "roundtrip.parquet"
        save_to_parquet(original_df, file_path)
        loaded_df = load_from_parquet(file_path)

        # 验证行数和列数
        assert len(loaded_df) == len(original_df)
        assert list(loaded_df.columns) == list(original_df.columns)

        # 验证数值精度（允许微小误差）
        for col in ['open', 'high', 'low', 'close', 'volume']:
            assert (loaded_df[col] - original_df[col]).abs().max() < 0.001

    def test_timestamp_type(self, tmp_path, sample_kline_data):
        """测试时间戳类型保持为整数"""
        from utils.parquet_utils import save_to_parquet, load_from_parquet

        file_path = tmp_path / "timestamp_test.parquet"
        save_to_parquet(sample_kline_data, file_path)
        loaded_df = load_from_parquet(file_path)

        # timestamp 应该是 int64 类型
        assert loaded_df['timestamp'].dtype == 'int64'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
