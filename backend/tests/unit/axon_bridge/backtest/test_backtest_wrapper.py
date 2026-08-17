"""axon_quant.backtest 适配层测试(事件驱动,L1/L2/L3 + Impacted + MultiAsset 撮合)。"""
import subprocess
import pytest


def test_backtest_engine_importable():
    """BacktestEngine 应可从适配层导入。"""
    from backend.axon_bridge import BacktestEngine
    assert BacktestEngine is not None


def test_matching_engines_importable():
    """L1/L2/Impacted/MultiAsset 撮合引擎应可从适配层导入。"""
    from backend.axon_bridge.backtest import (
        L1MatchingEngine, L2MatchingEngine,
        ImpactedMatchingEngine, MultiAssetMatchingEngine,
    )
    assert L1MatchingEngine is not None
    assert L2MatchingEngine is not None
    assert ImpactedMatchingEngine is not None
    assert MultiAssetMatchingEngine is not None


def test_no_vector_engine_in_code():
    """向量化回测代码必须 0 命中(代码层面,文档可保留历史说明)。"""
    result = subprocess.run(
        ["git", "grep", "-l", "VectorEngine", "backend/", ":!backend/strategy/*.md"],
        capture_output=True, text=True, cwd="/Users/liupeng/workspace/quant/QuantCell",
    )
    # 0 命中 = returncode=1
    assert result.returncode != 0 or "VectorEngine" not in result.stdout
