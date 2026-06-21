# -*- coding: utf-8 -*-
"""AxonDataAdapter 数据适配器测试"""
import pytest
import pandas as pd
import importlib.util
import os


def _load_adapter_module():
    """直接加载 adapter 模块，避免通过 __init__.py 触发其他模块导入"""
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    spec = importlib.util.spec_from_file_location(
        "axon_data_adapter",
        os.path.join(backend_dir, "backtest", "adapters", "axon_data_adapter.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sample_csv(tmp_path):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"], utc=True),
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [99.0, 100.0, 101.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000.0, 2000.0, 3000.0],
    })
    path = tmp_path / "BTCUSDT_1h.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def sample_parquet(tmp_path):
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [99.0, 100.0],
        "close": [103.0, 104.0],
        "volume": [1000.0, 2000.0],
    }, index=pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True))
    path = tmp_path / "BTCUSDT_1h.parquet"
    df.to_parquet(path)
    return str(path)


class TestAxonDataAdapter:
    def test_load_bars_from_csv(self, sample_csv):
        mod = _load_adapter_module()
        adapter = mod.AxonDataAdapter()
        df = adapter.load_bars_from_csv(sample_csv)
        assert len(df) == 3
        assert "open" in df.columns
        assert "close" in df.columns

    def test_load_bars_from_csv_normalizes_columns(self, sample_csv):
        mod = _load_adapter_module()
        adapter = mod.AxonDataAdapter()
        df = adapter.load_bars_from_csv(sample_csv)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in df.columns

    def test_load_bars_from_parquet(self, sample_parquet):
        mod = _load_adapter_module()
        adapter = mod.AxonDataAdapter()
        df = adapter.load_bars_from_parquet(sample_parquet)
        assert len(df) == 2
        assert "open" in df.columns

    def test_load_bars_from_csv_missing_file(self):
        mod = _load_adapter_module()
        adapter = mod.AxonDataAdapter()
        with pytest.raises(FileNotFoundError):
            adapter.load_bars_from_csv("/nonexistent/path.csv")

    def test_load_multiple(self, sample_csv):
        mod = _load_adapter_module()
        adapter = mod.AxonDataAdapter()
        data = adapter.load_multiple(
            symbols=["BTCUSDT"],
            data_dir=os.path.dirname(sample_csv),
            file_pattern="{symbol}_1h.csv",
        )
        assert "BTCUSDT" in data
        assert len(data["BTCUSDT"]) == 3

    def test_load_multiple_missing_symbol(self, sample_csv):
        mod = _load_adapter_module()
        adapter = mod.AxonDataAdapter()
        data = adapter.load_multiple(
            symbols=["BTCUSDT", "ETHUSDT"],
            data_dir=os.path.dirname(sample_csv),
            file_pattern="{symbol}_1h.csv",
        )
        assert "BTCUSDT" in data
        assert "ETHUSDT" not in data
