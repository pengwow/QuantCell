"""上游引擎契约门禁:崩溃恢复绑定 API 形态(conformance)。

钉住 axon-quant 0.22.0 `axon_worker` 绑定层的 Python 可见契约,
锁定 QuantCell live driver(M4.6 起接线)依赖的四组原语:
1. `Kernel.run(journal_path=...)` —— 首跑录制:外部输入(含逐 bar state)落
   journal,是崩溃恢复的材料来源;
2. `LiveRecovery(initial_cash, interval, ...).resume(path)` —— 重演恢复,返回
   `{positions, cash, fill_ids, open_order_ids, manifest}` 快照;构造参数必须与
   首跑内核一致,否则 `resume_replay` 的 manifest 逐字段校验拦截;
3. `reconcile(local, venue)` —— 三路对账,serde 契约字段
   {position_breaks, missing_fills, extra_fills, cash_break, frozen_instruments,
   ghost_orders, orphan_local_orders};
4. `resume_guard(report)` —— 恢复门禁:持仓/现金 break → ValueError 禁止
   自动续跑,仅成交差异 → 放行(告警人工核对由调用方负责)。

语义边界:纯行情 journal(无 venue 回报条目)重演后 ReplayGateway 只 ack
不成交 → 快照 positions 恒空、cash = 入金、fill_ids 恒空;带 venue 回报的
重演保真由 axon-quant 侧 tests/crash_recovery.rs 守护,此处钉 Python 侧
能看到的形状。

本目录是「引擎升级门禁」:axon-quant 升级时优先跑
(`uv run pytest tests/conformance/ -q`),全部通过再跑全量回归。
"""

from __future__ import annotations

import pytest
from axon_quant import worker

# 上游契约标记:断言钉住引擎绑定 API 契约,升级时最先受影响
pytestmark = [pytest.mark.upstream]

# Kernel(首跑)与 LiveRecovery(恢复)的共有参数必须逐字一致——
# 恢复配置漂移会被 manifest 逐字段校验拒绝,这里故意显式写出锁契约
_INITIAL_CASH = 100_000.0
_INTERVAL = "1m"
_SYMBOL = "BTC/USDT"
_NS = 1_700_000_000_000_000_000  # 固定基点,与墙上时钟无关
_BAR_STEP = 60_000_000_000  # 1m 间隔(纳秒)
_N_BARS = 5


def _bars(n: int = _N_BARS) -> dict[str, list[dict]]:
    """n 根 1m bar,价格匀速上行(纳秒时间戳)。"""
    return {
        _SYMBOL: [
            {
                "timestamp": _NS + i * _BAR_STEP,
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.5 + i,
                "close": 100.5 + i,
                "volume": 10.0,
            }
            for i in range(n)
        ]
    }


class AlwaysBuy:
    """决策必须确定的策略——重演保真成立的前提(同输入同输出)。"""

    def on_bar(self, bar: dict) -> dict:
        return {"action_type": "buy", "confidence": 0.8, "target_position": 0.1}


def _record_journal(tmp_path) -> str:
    """首跑录制:Kernel.run(journal_path=...) 生成临时 journal,返回路径。"""
    kernel = worker.Kernel(initial_cash=_INITIAL_CASH, interval=_INTERVAL)
    kernel.add_strategy(AlwaysBuy(), symbol=_SYMBOL)
    journal = str(tmp_path / "live.journal")
    result = kernel.run(bars_by_symbol=_bars(), journal_path=journal)
    assert result.n_bars == _N_BARS, "夹具前置条件:本次运行应消费全部 bar"
    return journal


def test_kernel_run_journal_path_records_manifest(tmp_path) -> None:
    """首跑录制产物可被 read_manifest 探查,journal_format 是当前格式版本。"""
    journal = _record_journal(tmp_path)
    manifest = worker.read_manifest(journal)
    assert manifest["journal_format"] == 1, "journal 头格式版本必须钉在 1"
    assert manifest["entries"] == _N_BARS, "每根 bar 一条行情事件,条目数应等于 bar 数"
    assert isinstance(manifest["code_version"], str)
    assert manifest["model_artifacts"] == []


def test_resume_replay_snapshot_contract(tmp_path) -> None:
    """重演快照形状:{positions, cash, fill_ids, manifest},manifest 内含 entries。

    纯行情 journal 下快照相量恒为:持仓空、现金 = 入金、无成交
    (ReplayGateway 只 ack,见模块 docstring 语义边界)。
    """
    journal = _record_journal(tmp_path)
    recovery = worker.LiveRecovery(initial_cash=_INITIAL_CASH, interval=_INTERVAL)
    recovery.add_strategy(AlwaysBuy(), symbol=_SYMBOL)
    snap = recovery.resume(journal)

    assert set(snap) == {
        "positions",
        "cash",
        "fill_ids",
        "manifest",
        "open_order_ids",
    }, "快照键集合漂移"
    assert snap["positions"] == {}
    assert snap["cash"] == _INITIAL_CASH
    assert snap["fill_ids"] == []
    assert snap["manifest"]["entries"] == _N_BARS
    assert snap["manifest"]["journal_format"] == 1


def test_reconcile_report_contract(tmp_path) -> None:
    """对账 report 键集合与 serde 字段形状;持仓 break 带 instrument/local/venue。"""
    journal = _record_journal(tmp_path)
    recovery = worker.LiveRecovery(initial_cash=_INITIAL_CASH, interval=_INTERVAL)
    recovery.add_strategy(AlwaysBuy(), symbol=_SYMBOL)
    local = recovery.resume(journal)

    # 本地无仓 vs 交易所有仓 → 必然产生持仓 break 并冻结该品种
    venue = {"positions": {_SYMBOL: 1.5}, "cash": _INITIAL_CASH, "fill_ids": []}
    report = worker.reconcile(local, venue)

    assert set(report) == {
        "position_breaks",
        "missing_fills",
        "extra_fills",
        "cash_break",
        "frozen_instruments",
        # 交易所在外订单（venue 有 local 无）与本地幽灵挂单（local 有 venue 无）
        "ghost_orders",
        "orphan_local_orders",
    }, "ReconcileReport serde 字段漂移"
    assert report["position_breaks"], "有持仓差异时 position_breaks 不得为空"
    brk = report["position_breaks"][0]
    assert set(brk) == {"instrument", "local", "venue"}
    assert brk["instrument"] == _SYMBOL
    assert brk["venue"] == 1.5 and brk["local"] == 0.0
    assert report["frozen_instruments"] == [_SYMBOL]
    assert report["cash_break"] is None, "现金一致时 cash_break 必须是 None"


def test_resume_guard_semantics(tmp_path) -> None:
    """门禁三分支:干净放行 / 持仓 break 拒绝 / 仅成交差异放行(告警责任在调用方)。"""
    journal = _record_journal(tmp_path)
    recovery = worker.LiveRecovery(initial_cash=_INITIAL_CASH, interval=_INTERVAL)
    recovery.add_strategy(AlwaysBuy(), symbol=_SYMBOL)
    local = recovery.resume(journal)

    clean = worker.reconcile(local, {"positions": {}, "cash": _INITIAL_CASH, "fill_ids": []})
    worker.resume_guard(clean)  # 不抛即通过

    broken = worker.reconcile(local, {"positions": {_SYMBOL: 1.0}, "cash": _INITIAL_CASH, "fill_ids": []})
    with pytest.raises(ValueError, match="恢复门禁"):
        worker.resume_guard(broken)

    fills_only = worker.reconcile(local, {"positions": {}, "cash": _INITIAL_CASH, "fill_ids": ["v-1"]})
    worker.resume_guard(fills_only)  # 仅成交差异 → 放行
