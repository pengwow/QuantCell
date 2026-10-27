"""BacktestLoop 特征逐 bar 注入测试：SpyStrategy 记录每根 bar 看到的特征与截面 rank。"""

import numpy as np
import pandas as pd

from backtest.backtest_loop import BacktestLoop
from strategy import Action, BaseStrategy, StrategyConfig


class SpyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(StrategyConfig(name="spy", symbol="BTCUSDT"))
        self.records: list[tuple[int, dict, int]] = []

    def on_bar(self, bar: dict, ctx) -> Action:
        rank = int(bar.get("cross_sectional_rank", 0))
        self.records.append((bar["timestamp"], dict(ctx.features), rank))
        return Action(
            action_type="hold",
            confidence=0.0,
            target_position=0.0,
            model_id="spy",
            inference_time_us=0,
        )


def _ohlcv(n: int = 40) -> pd.DataFrame:
    close = 100 + np.arange(n) * 0.5
    hour_ns = 3_600_000_000_000
    return pd.DataFrame(
        {
            "timestamp": [hour_ns * (i + 1) for i in range(n)],
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": [1000.0] * n,
        }
    )


def _feature_frame(df: pd.DataFrame, with_rank: bool = True) -> pd.DataFrame:
    # 前 10 根 NaN（热身），之后给随 bar 递增的因子值
    vals = [np.nan] * 10 + [float(i) for i in range(len(df) - 10)]
    data = {"momentum_5d": vals}
    if with_rank:
        data["cross_sectional_rank"] = [np.nan] * 10 + [1.0] * (len(df) - 10)
    return pd.DataFrame(data, index=df["timestamp"].values)


def test_features_injected_bar_by_bar_and_aligned_by_timestamp():
    df = _ohlcv()
    feat = _feature_frame(df)
    spy = SpyStrategy()

    BacktestLoop(initial_cash=100_000.0).run(spy, df, symbol="BTCUSDT", feature_dataframe=feat)

    assert len(spy.records) == len(df)
    # 热身期：因子不注入、rank 为默认 0
    for _ts, features, rank in spy.records[:10]:
        assert "momentum_5d" not in features
        assert rank == 0
    # 有效行：特征值与帧一致、时间戳精确不错位
    for (ts, features, rank), expected_ts in zip(spy.records[10:], df["timestamp"].tolist()[10:], strict=False):
        assert ts == expected_ts
        assert features["momentum_5d"] == float(feat.loc[expected_ts, "momentum_5d"])
        assert rank == 1


def test_no_feature_dataframe_means_empty_features():
    df = _ohlcv()
    spy = SpyStrategy()
    BacktestLoop(initial_cash=100_000.0).run(spy, df, symbol="BTCUSDT")
    assert all(features == {} for _, features, _ in spy.records)
    assert all(rank == 0 for _, _, rank in spy.records)


def test_feature_frame_without_rank_column():
    df = _ohlcv()
    feat = _feature_frame(df, with_rank=False)
    spy = SpyStrategy()
    BacktestLoop(initial_cash=100_000.0).run(spy, df, symbol="BTCUSDT", feature_dataframe=feat)
    # 因子正常注入；无 rank 列时 bar 不带真实排名（默认 0）
    assert "momentum_5d" in spy.records[-1][1]
    assert spy.records[-1][2] == 0


def test_features_aligned_when_data_is_datetime_index():
    # 生产主路径：_normalize_dataframe 把 timestamp 列 set_index 为 DatetimeIndex，
    # 特征帧同样是 DatetimeIndex；两者必须按纳秒时间键精确对齐
    df = _ohlcv()
    dt_index = pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
    df_dt = df.drop(columns=["timestamp"]).set_index(dt_index)
    feat = pd.DataFrame(
        {
            "momentum_5d": [np.nan] * 10 + [float(i) for i in range(len(df_dt) - 10)],
            "cross_sectional_rank": [np.nan] * 10 + [1.0] * (len(df_dt) - 10),
        },
        index=dt_index,
    )
    spy = SpyStrategy()
    BacktestLoop(initial_cash=100_000.0).run(spy, df_dt, symbol="BTCUSDT", feature_dataframe=feat)

    assert len(spy.records) == len(df_dt)
    for _ts, features, rank in spy.records[:10]:
        assert "momentum_5d" not in features
        assert rank == 0
    last_ts, last_features, last_rank = spy.records[-1]
    assert last_features["momentum_5d"] == float(len(df_dt) - 11)
    assert last_rank == 1
    assert last_ts == int(pd.Timestamp(dt_index[-1]).timestamp() * 1_000_000_000)


def test_futures_mode_uses_swap_instrument_with_funding(monkeypatch):
    """futures 模式构造 swap 品种并按 bar 时间戳匹配后调用 push_funding 结算。

    引擎无 add_funding_data 方法，改为在 bar 循环内命中 funding 时刻时逐事件 push。
    """
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import backtest.backtest_loop as bl

    push_calls: list[tuple] = []

    fake_engine = MagicMock()
    fake_engine.pending_events = 0
    # 链式配置 API 必须把 engine 本体传回去，否则后续方法打在未配置的 mock 上
    fake_engine.with_seed.return_value = fake_engine
    fake_engine.with_seed_liquidity.return_value = fake_engine
    fake_engine.with_auto_rebalance.return_value = fake_engine
    fake_engine.run.return_value = SimpleNamespace(
        total_pnl=0.0,
        fills=0,
        final_nav=100_000.0,
        nav_peak=100_000.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        orders_accepted=0,
        orders_rejected=0,
        events_processed=0,
        duration_secs=0.0,
        total_fees=0.0,
        sharpe_ratio=0.0,
        bar_nav_curve=[],
        bar_balance_curve=[],
        fills_detail=[],
        positions={},
    )

    def _fake_push(instrument, funding_rate, mark_price, timestamp_ns):
        push_calls.append((instrument, funding_rate, mark_price, timestamp_ns))

    fake_engine.push_funding.side_effect = _fake_push
    monkeypatch.setattr(bl, "_NativeBacktestEngine", MagicMock(return_value=fake_engine))

    ohlcv = _ohlcv(5)
    # funding 事件对齐第 1、3 根 bar 的时间戳，确保 push_funding 被精确匹配调用
    funding_ts = ohlcv["timestamp"].iloc[[0, 2]].tolist()
    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0002], "mark_price": [100.5, 101.5]},
        index=pd.to_datetime(funding_ts),
    )

    bl.BacktestLoop(initial_cash=100_000.0).run(
        SpyStrategy(),
        ohlcv,
        symbol="BTCUSDT",
        trading_mode="futures",
        funding_df=funding_df,
    )

    # 旧 add_funding_data 已废弃(引擎无此方法),不应被调用
    fake_engine.add_funding_data.assert_not_called()
    # 命中 2 个 funding 时刻
    assert len(push_calls) == 2
    for instrument, _rate, _mark, _ts in push_calls:
        assert instrument["kind"] == "swap"
        assert instrument["base"] == "BTC"
        assert instrument["quote"] == "USDT"
    # 校验按 bar 时间戳精确匹配
    assert [ts for _, _, _, ts in push_calls] == funding_ts
