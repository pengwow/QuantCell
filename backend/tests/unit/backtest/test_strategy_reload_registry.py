"""策略重复加载：list_all 触发包路径注册后，load_strategy 仍能重新 import 同一策略。

回归背景：@register 对重名抛错，而 list_all 与 load_strategy 会用两个不同的模块名
导入同一策略文件，导致「列过策略后启动必失败」。
"""

from backtest.strategy_loader_service import StrategyLoaderService
from strategy.loader import StrategyLoader


def _load(name: str):
    return StrategyLoaderService.load_strategy(
        strategy_name=name,
        strategy_params={"mode": "heuristic"},
        instrument_ids=[{"symbol": "BTCUSDT"}],
        bar_types=["BTCUSDT-1h"],
        run_mode=None,
    )


def test_load_twice_after_list_all():
    # list_all 会把 templates 模块以包路径导入并执行注册
    StrategyLoader.list_all()

    first = _load("cascade_signal")
    second = _load("cascade_signal")

    assert type(first).__name__ == "CascadeSignalStrategy"
    assert type(second).__name__ == "CascadeSignalStrategy"
    # 两次加载是独立实例，不能共享状态
    assert first is not second
