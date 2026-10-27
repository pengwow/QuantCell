"""paper 泵轮 → 风控当日盈亏回灌的接线段测试。

只钉住「泵轮末尾把权益差值喂给驱动」这一段：真实 RiskPnlFeeder +
mock 驱动，行情拉取与快照推送均打桩，不启动线程。
"""

from unittest.mock import MagicMock

from worker.risk_config import RiskPnlFeeder
from worker.strategy_manager import StrategyManager


def test_pump_round_feeds_equity_delta(monkeypatch):
    """连续两轮：首轮建基线不喂，次轮按权益差值回灌当日亏损"""
    mgr = StrategyManager(max_workers=1)
    driver = MagicMock()
    # 两轮快照：首轮 10000（基线），次轮 9850 → 应回灌 -150
    driver.snapshot.side_effect = [
        {"equity": 10_000.0, "positions": {}},
        {"equity": 9_850.0, "positions": {}},
    ]
    monkeypatch.setattr(StrategyManager, "_paper_fetch_klines", lambda *a, **k: [])
    monkeypatch.setattr(StrategyManager, "_push_kernel_snapshot", staticmethod(lambda *a, **k: None))

    feeder = RiskPnlFeeder(driver, daily_scoped=False)
    try:
        mgr._paper_pump_round(1, driver, ["BTC/USDT"], "1h", {}, limit=2, pnl_feeder=feeder)
        driver.update_risk_pnl.assert_not_called()
        mgr._paper_pump_round(1, driver, ["BTC/USDT"], "1h", {}, limit=2, pnl_feeder=feeder)
        driver.update_risk_pnl.assert_called_once_with(-150.0)
    finally:
        mgr.shutdown()


def test_pump_round_without_feeder_skips_risk(monkeypatch):
    """未装配风控时泵轮不碰风控回灌（opt-in 行为不变）"""
    mgr = StrategyManager(max_workers=1)
    driver = MagicMock()
    driver.snapshot.return_value = {"equity": 10_000.0, "positions": {}}
    monkeypatch.setattr(StrategyManager, "_paper_fetch_klines", lambda *a, **k: [])
    monkeypatch.setattr(StrategyManager, "_push_kernel_snapshot", staticmethod(lambda *a, **k: None))

    try:
        mgr._paper_pump_round(1, driver, ["BTC/USDT"], "1h", {}, limit=2)
        driver.update_risk_pnl.assert_not_called()
        driver.snapshot.assert_called_once()
    finally:
        mgr.shutdown()
