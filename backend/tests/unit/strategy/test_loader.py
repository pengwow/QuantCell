"""StrategyLoader 测试。"""

import pytest

from strategy.loader import StrategyLoader


def test_loader_lists_all_templates():
    """loader.list_all() 返回所有内置策略。"""
    names = StrategyLoader.list_all()
    assert len(names) >= 9, f"期望至少 9 个模板, 实际 {len(names)}: {names}"


def test_loader_get_dual_ma():
    cls = StrategyLoader.get("dual_ma")
    assert cls.__name__ == "DualMA"


def test_loader_get_llm_signal():
    cls = StrategyLoader.get("llm_signal")
    assert cls.__name__ == "LLMSignalStrategy"


def test_loader_get_trend_follow():
    cls = StrategyLoader.get("trend_follow")
    assert cls.__name__ == "TrendFollow"


def test_loader_get_all_templates():
    expected = {
        "dual_ma",
        "llm_signal",
        "trend_follow",
        "grid",
        "mean_reversion",
        "momentum",
        "funding_arbitrage",
        "cross_sectional",
        "mean_reversion_rl",
        "sma_crossover",
    }
    actual = set(StrategyLoader.list_all())
    assert expected.issubset(actual)


def test_loader_unknown_raises():
    with pytest.raises(ValueError):
        StrategyLoader.get("nonexistent")


def test_loader_has():
    assert StrategyLoader.has("dual_ma") is True
    assert StrategyLoader.has("ghost") is False
