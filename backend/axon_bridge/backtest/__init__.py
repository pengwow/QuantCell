"""axon_quant.backtest 适配层 — 事件驱动回测,QuantCell 唯一回测来源。

⚠️ QuantCell 自身不实现任何回测逻辑(不保留 VectorEngine / NumPy 向量化)。
本模块仅做直传重导出,业务在 services/backtest_service.py 包装。

axon_quant 0.6.0 提供:
- 5 档撮合:
  - L1MatchingEngine           价格优先
  - L2MatchingEngine           多档订单簿
  - ImpactedMatchingEngine     含市场冲击
  - MultiAssetMatchingEngine   多资产并行
- 多 leg 回测(0.5.0+):
  - spot_instrument / swap_instrument   品种工厂
  - BacktestEngine.set_target_position  记录每 leg 目标位
  - BacktestEngine.push_funding         引擎层累加 funding_pnl
  - BacktestEngine.push_mark            mark 价缓存
  - BacktestEngine.with_auto_rebalance  bar 末自动 rebalance
"""
from axon_quant import (  # noqa: F401
    BacktestEngine,
    BacktestError,
)
from axon_quant.backtest import (  # noqa: F401
    L1MatchingEngine,
    L2MatchingEngine,
    ImpactedMatchingEngine,
    ImpactedMatchingEngineBuilder,
    MultiAssetMatchingEngine,
)

# —— axon_quant 0.6.0 多 leg API 重导出 ——
# Instrument dict 工厂:把"symbol 字符串"升级为"品种 dict"
from axon_quant.backtest import (  # noqa: F401
    spot_instrument,
    swap_instrument,
    limit_order,
    InstrumentDict,
)


class PushFundingHelper:
    """funding fixture → engine.push_funding 调度器。

    ponytail: funding fixture 是 dict[ts_ms, rate],
             engine.push_funding 接受 (instrument, rate, mark, ts_ns)
             转换 + 重复时间防御一次过
             8h window 兼容: ts_ms 落点在 [funding_ts - 8h, funding_ts] 都触发
    """

    WINDOW_MS = 8 * 3600 * 1000  # 8h funding 周期

    def __init__(self, funding_history: dict):
        self.funding_history = funding_history
        self._last_pushed_ts_ms: int = -1

    def maybe_push(self, perp, mark: float, ts_ns: int, engine) -> None:
        """ts_ms 落点在 funding fixture 某个 key 附近 8h 窗口 → 推 funding。

        Args:
            perp: swap instrument (engine.push_funding 第一个参数)
            mark: 当前 mark 价
            ts_ns: 当前 bar 时间戳 (纳秒)
            engine: BacktestEngine 实例
        """
        if not self.funding_history:
            return
        ts_ms = ts_ns // 1_000_000
        for funding_ts_ms, rate in self.funding_history.items():
            if funding_ts_ms - self.WINDOW_MS <= ts_ms <= funding_ts_ms:
                # 重复时间防御
                if funding_ts_ms > self._last_pushed_ts_ms:
                    engine.push_funding(perp, rate, mark, funding_ts_ms * 1_000_000)
                    self._last_pushed_ts_ms = funding_ts_ms
                return  # 只推最近的 funding 事件
