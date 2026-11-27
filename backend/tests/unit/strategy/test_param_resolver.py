"""策略参数按标的覆盖解析（spec 2026-11-28 §3.2）。"""

import pytest

from strategy.param_resolver import normalize_symbol_key, resolve_strategy_params


def test_resolve_without_symbol_returns_base_copy():
    base = {"levels": 20}
    out = resolve_strategy_params(base, {"BTC/USDT": {"lower": 100.0}}, None)
    assert out == {"levels": 20}
    out["levels"] = 99  # 返回值是新 dict，不得修改入参
    assert base == {"levels": 20}


def test_resolve_merges_override_over_base():
    by_symbol = {"BTC/USDT": {"lower": 100.0, "levels": 12}}
    assert resolve_strategy_params({"levels": 20}, by_symbol, "BTC/USDT") == {
        "levels": 12,
        "lower": 100.0,
    }


def test_resolve_empty_values_do_not_override():
    by_symbol = {"BTC/USDT": {"lower": None, "levels": ""}}
    assert resolve_strategy_params({"levels": 20}, by_symbol, "BTC/USDT") == {"levels": 20}


def test_resolve_symbol_without_override_gets_base():
    assert resolve_strategy_params({"levels": 20}, {"BTC/USDT": {"lower": 1.0}}, "ETHUSDT") == {"levels": 20}


def test_resolve_handles_none_inputs():
    assert resolve_strategy_params(None, None, None) == {}
    assert resolve_strategy_params({"a": 1}, None, "BTCUSDT") == {"a": 1}


def test_normalize_symbol_key_uses_expand_symbol():
    assert normalize_symbol_key("BTCUSDT") == "BTC/USDT"
    assert normalize_symbol_key("btc/usdt") == "BTC/USDT"  # 已带分隔符：透传并大写
    assert normalize_symbol_key("ETH-USDT") == "ETH/USDT"


def test_resolve_looks_up_by_normalized_key():
    # 存储键与查询标的都要过同一规范化：存 "BTCUSDT" 也能按 "BTC/USDT" 查到
    by_symbol = {"BTCUSDT": {"lower": 100.0}}
    assert resolve_strategy_params({}, by_symbol, "BTC/USDT") == {"lower": 100.0}
