# 因子引擎单测：全部用合成 OHLCV，不依赖真实 parquet。
import numpy as np
import pandas as pd
import pytest

from factor.engine import (
    FACTOR_META,
    UNSUPPORTED_FACTORS,
    FactorExpressionError,
    _timestamps_to_datetime,
    evaluate_expression,
    evaluate_factor,
    load_factor_panel,
)


def _synth_df(n: int = 80, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n),
            "high": close + abs(rng.normal(0.5, 0.3, n)),
            "low": close - abs(rng.normal(0.5, 0.3, n)),
            "close": close,
            "volume": rng.uniform(100, 1000, n),
            "quote_volume": close * rng.uniform(100, 1000, n),
            "timestamp": np.arange(n, dtype="int64") * 3_600_000_000_000,
        }
    )


def test_builtin_meta_complete_and_unsupported():
    assert len(FACTOR_META) == 31
    assert UNSUPPORTED_FACTORS == {"pe", "pb", "roe", "roa", "profit_growth"}
    for _name, meta in FACTOR_META.items():
        assert {"category", "label", "expression", "supported"} <= set(meta)
        if meta["supported"]:
            assert meta["expression"].strip()
        assert "$" not in meta["expression"]  # 表达式只允许裸列名，不允许 $ 前缀


def test_price_and_amount():
    df = _synth_df()
    pd.testing.assert_series_equal(evaluate_factor("close", df), df["close"], check_names=False)
    pd.testing.assert_series_equal(evaluate_factor("amount", df), df["volume"] * df["close"], check_names=False)
    pd.testing.assert_series_equal(evaluate_factor("vwap", df), df["quote_volume"] / df["volume"], check_names=False)


def test_momentum_and_ma_and_std():
    df = _synth_df()
    pd.testing.assert_series_equal(
        evaluate_factor("momentum_5d", df), df["close"] / df["close"].shift(5) - 1, check_names=False
    )
    assert evaluate_factor("ma_20d", df).iloc[:19].isna().all()
    assert evaluate_factor("volatility_20d", df).iloc[:19].isna().all()


def test_rsi_range_and_bollinger():
    df = _synth_df(300)
    rsi = evaluate_factor("rsi_14d", df).dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()
    assert evaluate_factor("bollinger", df).iloc[:19].isna().all()


def test_macd_kdj_return_series():
    df = _synth_df(80)
    assert isinstance(evaluate_factor("macd", df), pd.Series)
    assert isinstance(evaluate_factor("kdj", df), pd.Series)


def test_unsupported_factor_raises():
    with pytest.raises(FactorExpressionError):
        evaluate_factor("pe", _synth_df())


@pytest.mark.parametrize(
    "expr",
    [
        "close / Ref(close, 5) - 1",
        "MA(close, 10) + Std(close, 10) * 0",
        "(close - open) * volume",
        "RSI(close, 14)",
        "MACD(close, 12, 26)",
        "KDJ(high, low, close, 9)",
        "BBANDS(close, 20, 2)",
    ],
)
def test_evaluate_expression_accepts(expr):
    df = _synth_df(300)
    assert isinstance(evaluate_expression(expr, df), pd.Series)


@pytest.mark.parametrize(
    "bad",
    [
        "$close",  # $ 前缀：拒绝（只接受裸列名）
        "__import__('os')",  # 拒绝内置名
        "close.open.__class__",  # 拒绝属性访问
        "unknown_col",  # 拒绝未授权列
        "Foo(close, 3)",  # 拒绝未授权函数
        "close +",  # 语法错误
        "Ref(close, close)",  # 窗口必须是整数常量
    ],
)
def test_evaluate_expression_rejects(bad):
    with pytest.raises(FactorExpressionError):
        evaluate_expression(bad, _synth_df())


class _FakeProvider:
    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        return _synth_df(80, seed=abs(hash(symbol)) % 100)


def test_load_factor_panel_multiindex():
    panel = load_factor_panel(
        ["BTCUSDT", "ETHUSDT"],
        "1h",
        "spot",
        None,
        None,
        "momentum_5d",
        {},
        provider=_FakeProvider(),
    )
    assert panel.index.names == ["datetime", "symbol"]
    assert set(panel.index.get_level_values("symbol")) == {"BTCUSDT", "ETHUSDT"}
    assert str(panel.index.get_level_values("datetime").dtype) == "datetime64[ns]"


def test_timestamps_to_datetime_unit_inference():
    # 真实落盘时间戳单位可能是 ns/us/ms/s（实测 Binance K 线为微秒），需按量级还原到同一时刻
    base = pd.Timestamp("2026-07-01 00:00:00")
    ns = int(base.value)
    cases = {
        "ns": [ns, ns + 3_600_000_000_000],
        "us": [ns // 1_000, ns // 1_000 + 3_600_000_000],
        "ms": [ns // 1_000_000, ns // 1_000_000 + 3_600_000],
        "s": [ns // 1_000_000_000, ns // 1_000_000_000 + 3_600],
    }
    for vals in cases.values():
        idx = _timestamps_to_datetime(pd.Series(vals, dtype="int64"))
        assert idx[0] == base
        assert idx[1] == base + pd.Timedelta(hours=1)

    # 已经是 datetime 的列应能原样解析
    idx = _timestamps_to_datetime(pd.Series(pd.to_datetime(["2026-07-01", "2026-07-02"])))
    assert idx[0] == base
