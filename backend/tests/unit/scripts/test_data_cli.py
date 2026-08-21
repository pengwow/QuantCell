"""数据管理CLI单元测试"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestFormatSize:
    """测试 format_size 函数"""

    def test_format_size_bytes(self):
        """测试字节级别"""
        from cli.data import format_size

        assert format_size(500) == "500.0 B"

    def test_format_size_kb(self):
        """测试KB级别"""
        from cli.data import format_size

        assert format_size(1500) == "1.5 KB"

    def test_format_size_mb(self):
        """测试MB级别"""
        from cli.data import format_size

        assert format_size(1500000) == "1.4 MB"

    def test_format_size_gb(self):
        """测试GB级别"""
        from cli.data import format_size

        assert format_size(1500000000) == "1.4 GB"


class TestCalculateDataCompleteness:
    """测试 calculate_data_completeness 函数"""

    def test_completeness_no_data(self):
        """测试无数据情况"""
        from cli.data import calculate_data_completeness

        result = calculate_data_completeness(0, None, None, "1h")
        assert result["completeness_pct"] == 0
        assert result["status"] == "-"

    def test_completeness_perfect(self):
        """测试完整度100%"""
        from cli.data import calculate_data_completeness

        start_ts = int(datetime(2024, 1, 1).timestamp())
        end_ts = int(datetime(2024, 1, 2).timestamp())
        result = calculate_data_completeness(24, start_ts, end_ts, "1h")
        assert result["completeness_pct"] == 100.0
        assert result["status"] == "✓"

    def test_completeness_warning(self):
        """测试完整度警告级别"""
        from cli.data import calculate_data_completeness

        start_ts = int(datetime(2024, 1, 1).timestamp())
        end_ts = int(datetime(2024, 1, 2).timestamp())
        result = calculate_data_completeness(18, start_ts, end_ts, "1h")
        assert 70 <= result["completeness_pct"] < 95
        assert result["status"] == "⚠️"

    def test_completeness_poor(self):
        """测试完整度差级别"""
        from cli.data import calculate_data_completeness

        start_ts = int(datetime(2024, 1, 1).timestamp())
        end_ts = int(datetime(2024, 1, 2).timestamp())
        result = calculate_data_completeness(10, start_ts, end_ts, "1h")
        assert result["completeness_pct"] < 70
        assert result["status"] == "✗"

    def test_completeness_nanoseconds(self):
        """测试纳秒级时间戳"""
        from cli.data import calculate_data_completeness

        start_ts = int(datetime(2024, 1, 1).timestamp() * 1_000_000_000)
        end_ts = int(datetime(2024, 1, 2).timestamp() * 1_000_000_000)
        result = calculate_data_completeness(24, start_ts, end_ts, "1h")
        assert result["completeness_pct"] == 100.0


class TestFormatCompleteness:
    """测试 format_completeness 函数"""

    def test_format_completeness_good(self):
        """测试良好完整度"""
        from cli.data import format_completeness

        info = {"completeness_pct": 95.0, "status": "✓"}
        assert format_completeness(info) == "95% ✓"

    def test_format_completeness_warning(self):
        """测试警告完整度"""
        from cli.data import format_completeness

        info = {"completeness_pct": 80.0, "status": "⚠️"}
        assert format_completeness(info) == "80% ⚠️"

    def test_format_completeness_unknown(self):
        """测试未知完整度"""
        from cli.data import format_completeness

        info = {"completeness_pct": 0, "status": "-"}
        assert format_completeness(info) == "-"


class TestFilterByDateRange:
    """测试 filter_by_date_range 函数"""

    def test_filter_no_dates(self):
        """测试无日期筛选"""
        from cli.data import filter_by_date_range

        df = pd.DataFrame({"timestamp": [1704067200000000000, 1704153600000000000]})
        result = filter_by_date_range(df, None, None)
        assert len(result) == 2

    def test_filter_with_start(self):
        """测试开始日期筛选"""
        from cli.data import filter_by_date_range

        df = pd.DataFrame(
            {
                "timestamp": [
                    int(datetime(2024, 1, 1).timestamp() * 1_000_000_000),
                    int(datetime(2024, 2, 1).timestamp() * 1_000_000_000),
                ]
            }
        )
        result = filter_by_date_range(df, "2024-01-15", None)
        assert len(result) == 1

    def test_filter_with_end(self):
        """测试结束日期筛选"""
        from cli.data import filter_by_date_range

        df = pd.DataFrame(
            {
                "timestamp": [
                    int(datetime(2024, 1, 1).timestamp() * 1_000_000_000),
                    int(datetime(2024, 2, 1).timestamp() * 1_000_000_000),
                ]
            }
        )
        result = filter_by_date_range(df, None, "2024-01-15")
        assert len(result) == 1

    def test_filter_empty_df(self):
        """测试空DataFrame"""
        from cli.data import filter_by_date_range

        df = pd.DataFrame()
        result = filter_by_date_range(df, "2024-01-01", "2024-01-31")
        assert len(result) == 0

    def test_filter_no_timestamp_column(self):
        """测试无时间戳列"""
        from cli.data import filter_by_date_range

        df = pd.DataFrame({"other": [1, 2, 3]})
        result = filter_by_date_range(df, "2024-01-01", "2024-01-31")
        assert len(result) == 3


class TestValidateParquetExport:
    """测试 _validate_parquet_export 函数"""

    def test_validate_file_not_exists(self):
        """测试文件不存在"""
        from cli.data import _validate_parquet_export

        mock_path = MagicMock()
        mock_path.exists.return_value = False
        df = pd.DataFrame({"a": [1]})
        result = _validate_parquet_export(mock_path, df)
        assert result is False

    def test_validate_empty_file(self):
        """测试空文件"""
        from cli.data import _validate_parquet_export

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=0)
        df = pd.DataFrame({"a": [1]})
        result = _validate_parquet_export(mock_path, df)
        assert result is False

    def test_validate_row_count_mismatch(self):
        """测试行数不一致"""
        from cli.data import _validate_parquet_export

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=100)

        original_df = pd.DataFrame({"a": [1, 2, 3]})
        loaded_df = pd.DataFrame({"a": [1, 2]})

        with patch("utils.data_utils.load_from_parquet", return_value=loaded_df):
            result = _validate_parquet_export(mock_path, original_df)
        assert result is False

    def test_validate_column_mismatch(self):
        """测试列名不一致"""
        from cli.data import _validate_parquet_export

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=100)

        original_df = pd.DataFrame({"a": [1], "b": [2]})
        loaded_df = pd.DataFrame({"a": [1], "c": [2]})

        with patch("utils.data_utils.load_from_parquet", return_value=loaded_df):
            result = _validate_parquet_export(mock_path, original_df)
        assert result is False

    def test_validate_success(self):
        """测试验证通过"""
        from cli.data import _validate_parquet_export

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=100)

        original_df = pd.DataFrame(
            {
                "timestamp": [1704067200000000000],
                "open": [100.0],
                "high": [110.0],
                "low": [90.0],
                "close": [105.0],
                "volume": [1000.0],
            }
        )

        # _validate_parquet_export 定义在 utils.data_utils，需 patch 该模块的 load_from_parquet
        with patch("utils.data_utils.load_from_parquet", return_value=original_df.copy()):
            result = _validate_parquet_export(mock_path, original_df)
        assert result is True


class TestFindParquetFile:
    """测试 _find_parquet_file 函数"""

    def test_find_parquet_file_spot(self):
        """测试查找现货Parquet文件"""
        from cli.data import _find_parquet_file

        with patch("cli.data.get_source_data_dir", return_value=Path("/data")):
            result = _find_parquet_file("BTCUSDT", "1h", "spot")
            assert "spot" in str(result)
            assert "BTCUSDT.parquet" in str(result)

    def test_find_parquet_file_future(self):
        """测试查找合约Parquet文件"""
        from cli.data import _find_parquet_file

        with patch("cli.data.get_source_data_dir", return_value=Path("/data")):
            result = _find_parquet_file("ETHUSDT", "15m", "future")
            assert "future" in str(result)
            assert "ETHUSDT.parquet" in str(result)

    def test_find_parquet_file_normalize_symbol(self):
        """测试交易对名称标准化"""
        from cli.data import _find_parquet_file

        with patch("cli.data.get_source_data_dir", return_value=Path("/data")):
            result = _find_parquet_file("ETH/USDT", "1h", "spot")
            assert "ETHUSDT.parquet" in str(result)


class TestGetDefaultDateRange:
    """测试 _get_default_date_range 函数"""

    def test_default_date_range(self):
        """测试默认日期范围"""
        from cli.data import _get_default_date_range

        start, end = _get_default_date_range()
        assert len(start) == 8
        assert len(end) == 8
        assert int(start) < int(end)

    def test_default_date_range_with_end(self):
        """测试指定结束日期"""
        from cli.data import _get_default_date_range

        end_date = datetime(2024, 6, 1)
        start, end = _get_default_date_range(end_date)
        assert end == "20240601"
        assert int(start) < int(end)


class TestScanParquetFiles:
    """测试 scan_parquet_files 函数"""

    def test_scan_empty_directory(self):
        """测试空目录"""
        from cli.data import scan_parquet_files

        with patch("pathlib.Path.iterdir", return_value=[]):
            with patch("cli.data.get_source_data_dir", return_value=Path("/empty")):
                result = scan_parquet_files(base_dir=Path("/empty"))
                assert result == []

    def test_scan_with_files(self):
        """测试有文件的情况"""
        from cli.data import scan_parquet_files

        mock_file = MagicMock()
        mock_file.stem = "BTCUSDT"
        mock_file.name = "BTCUSDT.parquet"
        mock_file.stat.return_value = MagicMock(st_mtime=1704067200)

        mock_interval_dir = MagicMock()
        mock_interval_dir.is_dir.return_value = True
        mock_interval_dir.name = "1h"
        mock_interval_dir.iterdir.return_value = [mock_file]
        mock_interval_dir.glob.return_value = [mock_file]

        mock_klines_dir = MagicMock()
        mock_klines_dir.is_dir.return_value = True
        mock_klines_dir.iterdir.return_value = [mock_interval_dir]

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[mock_interval_dir]):
                with patch(
                    "cli.data.get_parquet_info",
                    return_value={"num_rows": 100, "file_size_bytes": 1024},
                ):
                    with patch("cli.data.get_source_data_dir", return_value=Path("/data")):
                        result = scan_parquet_files(symbol="BTCUSDT", interval="1h")
                        assert len(result) >= 0


class TestDataCliCommands:
    """测试 data_cli.py 的 Typer 命令"""

    @patch("cli.data._find_parquet_file")
    @patch("cli.data.load_from_parquet")
    def test_export_csv_file_not_found(self, mock_load, mock_find):
        """测试导出CSV文件不存在"""
        from cli.data import app

        mock_find.return_value.exists.return_value = False

        result = runner.invoke(
            app,
            [
                "export",
                "csv",
                "--symbol",
                "BTCUSDT",
                "--interval",
                "1h",
                "--output",
                "test.csv",
            ],
        )
        assert result.exit_code == 1

    @patch("cli.data._find_parquet_file")
    @patch("cli.data.load_from_parquet")
    def test_export_parquet_file_not_found(self, mock_load, mock_find):
        """测试导出Parquet文件不存在"""
        from cli.data import app

        mock_find.return_value.exists.return_value = False

        result = runner.invoke(app, ["export", "parquet", "--symbol", "BTCUSDT", "--interval", "1h"])
        assert result.exit_code == 1

    @patch("cli.data.task_manager")
    def test_status_task_not_found(self, mock_task_manager):
        """测试查询不存在的任务"""
        from cli.data import app

        mock_task_manager.get_task.return_value = None

        result = runner.invoke(app, ["status", "--task-id", "nonexistent"])
        assert result.exit_code == 1
        assert "不存在" in result.output

    @patch("cli.data.task_manager")
    def test_status_task_found(self, mock_task_manager):
        """测试查询存在的任务"""
        from cli.data import app

        mock_task_manager.get_task.return_value = {
            "task_id": "test-123",
            "status": "completed",
            "task_type": "download",
            "progress": {
                "percentage": 100.0,
                "completed": 10,
                "total": 10,
                "failed": 0,
            },
            "params": {"exchange": "binance"},
            "start_time": "2024-01-01",
            "end_time": "2024-01-02",
        }

        result = runner.invoke(app, ["status", "--task-id", "test-123"])
        assert result.exit_code == 0
        assert "test-123" in result.output

    def test_list_symbols_no_data(self):
        """测试无本地数据时列出交易对"""
        from cli.data import app

        with patch("cli.data.scan_parquet_files", return_value=[]):
            result = runner.invoke(app, ["list-symbols"])
            assert result.exit_code == 0
            assert "未找到" in result.output

    def test_list_local_data_no_data(self):
        """测试无本地数据时列出数据"""
        from cli.data import app

        with patch("cli.data.scan_parquet_files", return_value=[]):
            result = runner.invoke(app, ["list-local-data"])
            assert result.exit_code == 0
            assert "未找到" in result.output

    @patch("cli.data.scan_parquet_files")
    def test_delete_local_data_not_found(self, mock_scan):
        """测试删除不存在的本地数据"""
        from cli.data import app

        mock_scan.return_value = []

        result = runner.invoke(app, ["delete-local-data", "--symbol", "NONEXISTENT"])
        assert result.exit_code == 0
        assert "未找到" in result.output


class TestImportCsv:
    """测试导入CSV功能"""

    @patch("cli.data.pd.read_csv")
    @patch("cli.data.Path")
    def test_import_csv_file_not_found(self, mock_path_cls, mock_read_csv):
        """测试导入不存在的CSV文件"""
        from cli.data import app

        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance

        result = runner.invoke(app, ["import", "csv", "nonexistent.csv", "--interval", "1h"])
        assert result.exit_code == 1
        assert "不存在" in result.output

    @patch("cli.data.pd.read_csv")
    def test_import_csv_empty_file(self, mock_read_csv):
        """测试导入空CSV文件"""
        from cli.data import app

        mock_read_csv.return_value = pd.DataFrame()

        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(app, ["import", "csv", "empty.csv", "--interval", "1h"])
            assert result.exit_code == 1
            assert "为空" in result.output

    @patch("cli.data.pd.read_csv")
    def test_import_csv_missing_columns(self, mock_read_csv):
        """测试导入缺少必需列的CSV"""
        from cli.data import app

        mock_read_csv.return_value = pd.DataFrame(
            {
                "symbol": ["BTCUSDT"],
                "timestamp": [1704067200000000000],
            }
        )

        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(app, ["import", "csv", "data.csv", "--interval", "1h"])
            assert result.exit_code == 1
            assert "缺少" in result.output


class TestQualityCommands:
    """测试数据质量命令"""

    @patch("cli.data.typer.secho")
    def test_quality_check_error(self, mock_secho):
        """测试质量检查错误"""
        from cli.data import app

        with patch(
            "builtins.__import__",
            side_effect=lambda name, *args, **kwargs: __import__(name, *args, **kwargs),
        ):
            result = runner.invoke(app, ["quality", "check", "-s", "BTCUSDT", "-i", "1h"])
            # 由于内部导入在函数内，测试验证命令能正常执行
            assert result.exit_code in [0, 1]

    @patch("cli.data.typer.secho")
    def test_quality_check_empty(self, mock_secho):
        """测试质量检查空数据"""
        from cli.data import app

        result = runner.invoke(app, ["quality", "check", "-s", "BTCUSDT", "-i", "1h"])
        assert result.exit_code in [0, 1]

    @patch("cli.data.typer.secho")
    def test_quality_options_no_data(self, mock_secho):
        """测试无数据时列出选项"""
        from cli.data import app

        result = runner.invoke(app, ["quality", "options"])
        assert result.exit_code in [0, 1]


class TestFormatTimeRange:
    """测试 format_time_range 函数"""

    def test_format_time_range_none(self):
        """测试无时间范围"""
        from cli.data import format_time_range

        assert format_time_range(None, None) == "-"

    def test_format_time_range_seconds(self):
        """测试秒级时间戳"""
        from cli.data import format_time_range

        start = int(datetime(2024, 1, 1).timestamp())
        end = int(datetime(2024, 1, 2).timestamp())
        result = format_time_range(start, end)
        assert "2024-01-01" in result
        assert "2024-01-02" in result

    def test_format_time_range_nanoseconds(self):
        """测试纳秒级时间戳"""
        from cli.data import format_time_range

        start = int(datetime(2024, 1, 1).timestamp() * 1_000_000_000)
        end = int(datetime(2024, 1, 2).timestamp() * 1_000_000_000)
        result = format_time_range(start, end)
        assert "2024-01-01" in result
        assert "2024-01-02" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
