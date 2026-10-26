"""规则/LLM 策略 paper 装配冒烟测试（统一内核接入）。

真实 PaperDriver + RustStrategyAdapter 全链路：mock 收市 K 线经
`_paper_pump_round` 同步驱动，BaseStrategy 的 buy 决策应产生真实成交
（positions 出现品种、权益偏离初始资金），并验证装配期参数校验。
"""

import pytest
from axon_quant import Action, ActionType

from strategy.base import BaseStrategy, StrategyConfig
from worker.strategy_manager import StrategyManager

INITIAL_CASH = 100_000.0

# 两根已收市的 1h K 线行（binance 原始格式，openTime 远早于 now → 必然已收市）
_CLOSED_KLINES = [
    ["1700000000000", "50000.0", "50100.0", "49900.0", "50050.0", "10.0"],
    ["1700003600000", "50050.0", "50300.0", "50000.0", "50200.0", "12.0"],
]


class _BuyOnceStrategy(BaseStrategy):
    """最小规则策略：首根 bar 建目标 10% 组合的多头，之后 hold。"""

    def __init__(self):
        super().__init__(StrategyConfig(name="buy_once_smoke", symbol="BTCUSDT"))
        self._bars = 0

    def on_bar(self, bar, ctx=None):
        self._bars += 1
        if self._bars == 1:
            return Action(ActionType.Buy, 0.8, 0.1, "buy_once_smoke", 0)
        return Action(ActionType.Hold, 0.0, 0.0, "buy_once_smoke", 0)


def test_rule_paper_driver_assembly_and_fill(monkeypatch):
    """装配期校验 → 真实引擎驱动两根已收市 K 线 → buy 决策产生成交。"""
    mgr = StrategyManager(max_workers=1)

    # 周期白名单：装配期直接拒绝
    with pytest.raises(ValueError, match="不支持时间周期"):
        mgr._assemble_rule_paper_driver(1, _BuyOnceStrategy(), {}, "2h", ["BTCUSDT"])

    driver = mgr._assemble_rule_paper_driver(
        1, _BuyOnceStrategy(), {"initial_capital": INITIAL_CASH}, "1h", ["BTCUSDT"]
    )
    monkeypatch.setattr(StrategyManager, "_paper_fetch_klines", lambda self, *args, **kwargs: _CLOSED_KLINES)
    try:
        driver.start()
        seen: dict[str, int] = {}
        mgr._paper_pump_round(1, driver, ["BTC/USDT"], "1h", seen, limit=2)

        snap = driver.snapshot()
        # buy 10% notional → positions 必须出现 BTC 数量
        assert any(qty > 0 for qty in snap["positions"].values()), snap["positions"]
        # 成交（手续费 + 浮盈亏）必须让权益偏离初始资金；空账本则原样返回 100000
        assert abs(snap["equity"] - INITIAL_CASH) > 1.0, snap["equity"]
        # 重叠窗口重拉不重复喂：去重后持仓不变（幂等）
        mgr._paper_pump_round(1, driver, ["BTC/USDT"], "1h", seen, limit=2)
        snap2 = driver.snapshot()
        assert snap2["positions"] == snap["positions"]
    finally:
        driver.shutdown()
        mgr.shutdown()
