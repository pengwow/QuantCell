"""axon_bridge 0.6.0 多 leg 适配层测试。"""


def test_spot_instrument_exported():
    """axon_bridge.spot_instrument 可用。"""
    from axon_bridge import spot_instrument

    inst = spot_instrument("BTC", "USDT")
    assert inst["kind"] == "spot"
    assert inst["base"] == "BTC"
    assert inst["quote"] == "USDT"


def test_swap_instrument_exported():
    """axon_bridge.swap_instrument 可用。"""
    from axon_bridge import swap_instrument

    inst = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)
    assert inst["kind"] == "swap"
    assert inst["base"] == "BTC"
    assert inst["quote"] == "USDT"
    assert inst["settle"] == "usd_margin"
    assert inst["contract_size"] == 1.0


def test_limit_order_exported():
    """axon_bridge.limit_order 可用,接受 instrument dict。"""
    from axon_bridge import limit_order, spot_instrument

    spot = spot_instrument("BTC", "USDT")
    order = limit_order(1, spot, "Buy", 50000.0, 0.1)
    assert order["id"] == 1
    assert order["side"] == "Buy"
    assert order["instrument"]["kind"] == "spot"


def test_push_funding_helper_maybe_push_triggers():
    """PushFundingHelper 在 funding window 内调 push_funding。"""
    from unittest.mock import MagicMock

    from axon_quant.backtest import BacktestEngine

    from axon_bridge import PushFundingHelper, swap_instrument

    engine = MagicMock(spec=BacktestEngine)
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000  # 2024-07-01 00:00 UTC
    history = {funding_ts_ms: 0.0003}
    helper = PushFundingHelper(history)

    # ts_ms 落点在 [funding_ts - 8h, funding_ts] 范围 → 推
    cur_ts_ms = funding_ts_ms  # 精确 = funding_ts
    helper.maybe_push(perp, 50000.0, cur_ts_ms * 1_000_000, engine)
    assert engine.push_funding.called, "应触发 push_funding"
    args = engine.push_funding.call_args[0]
    assert args[1] == 0.0003  # funding_rate
    assert args[2] == 50000.0  # mark_price
    assert args[3] == funding_ts_ms * 1_000_000  # timestamp_ns


def test_push_funding_helper_window_injection():
    """ts_ms 落点在 [funding_ts - 8h, funding_ts] 范围 → 推。"""
    from unittest.mock import MagicMock

    from axon_bridge import PushFundingHelper, swap_instrument

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000
    history = {funding_ts_ms: 0.0005}
    helper = PushFundingHelper(history)

    # 5h 之前 (在 8h window 内) → 推
    cur_ts_ms = funding_ts_ms - 5 * 3600 * 1000
    helper.maybe_push(perp, 50000.0, cur_ts_ms * 1_000_000, engine)
    assert engine.push_funding.called, "8h window 内应触发 push_funding"


def test_push_funding_helper_no_double_push():
    """重复 ts_ms 不重复 push。"""
    from unittest.mock import MagicMock

    from axon_bridge import PushFundingHelper, swap_instrument

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000
    history = {funding_ts_ms: 0.0003}
    helper = PushFundingHelper(history)

    helper.maybe_push(perp, 50000.0, funding_ts_ms * 1_000_000, engine)
    call_count_1 = engine.push_funding.call_count

    # 同一 funding_ts 再次调用 → 不重复
    helper.maybe_push(perp, 50000.0, funding_ts_ms * 1_000_000, engine)
    call_count_2 = engine.push_funding.call_count
    assert call_count_1 == call_count_2, f"重复调用应不重复 push: {call_count_1} vs {call_count_2}"


def test_push_funding_helper_outside_window_no_push():
    """ts_ms 落点在 [funding_ts - 8h, funding_ts] 之外 → 不推。"""
    from unittest.mock import MagicMock

    from axon_bridge import PushFundingHelper, swap_instrument

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000
    history = {funding_ts_ms: 0.0003}
    helper = PushFundingHelper(history)

    # 9h 之前 (在 8h window 外) → 不推
    cur_ts_ms = funding_ts_ms - 9 * 3600 * 1000
    helper.maybe_push(perp, 50000.0, cur_ts_ms * 1_000_000, engine)
    assert not engine.push_funding.called, "8h window 外应不触发 push_funding"


def test_push_funding_helper_empty_history():
    """空 funding_history → 不推。"""
    from unittest.mock import MagicMock

    from axon_bridge import PushFundingHelper, swap_instrument

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    helper = PushFundingHelper({})
    helper.maybe_push(perp, 50000.0, 1719792000000000000, engine)
    assert not engine.push_funding.called
