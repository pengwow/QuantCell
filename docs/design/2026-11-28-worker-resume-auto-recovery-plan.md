# Worker Resume 自动恢复（归档重启以交易所为准）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** live worker resume 对账守卫拒绝时，自动归档旧 journal 并 fresh start（adopt 交易所持仓与现金），含 24h 频次止损与审计 ndjson；Rust 侧仅锁错误前缀契约，零行为改动。

**Architecture:** 新 Python 模块 `backend/worker/resume_auto_recovery.py` 承载前缀判定、频次止损、best-effort 撤单、归档与审计；`StrategyManager._driver_live_thread_main` 的 except 分支挂钩（守卫拒绝 → 编排处置 → `driver.start` 重试）；Rust 侧把守卫拒绝错误前缀提取为常量并加测试断言（spec「明确不动」的唯一例外）。设计依据：`docs/design/2026-11-28-worker-resume-auto-recovery-design.md`（commit 66b38f3）。

**Tech Stack:** Python 3.12 + pytest（uv 管理）；ccxt（撤单经 `LiveTradeSync.exchange.exchange`）；Rust axon-worker（cargo test）；本期无前端代码改动。

**关键契约与锚点（已在规划期核实）：**

| 项 | 值 |
|---|---|
| Rust 守卫拒绝错误前缀 | `恢复守卫拒绝继续交易`，构造于 `axon_quant/crates/axon-worker/src/live_driver.rs` L444-446 `resume_attempt` 内 |
| 挂钩点 | `backend/worker/strategy_manager.py` `_driver_live_thread_main`（L1099）except 块（L1131-1138） |
| 报告落盘 | Rust 已先落 `journal.with_extension("reconcile.json")`（即 `worker_{id}.reconcile.json`，点分隔），Python 归档前 best-effort 读取 |
| 撤单通道 | `trade_sync.ccxt_symbol`（property）+ `trade_sync.exchange.exchange`（ccxt 实例）的 `fetch_open_orders` / `cancel_order`；`trade_sync=None` 时跳过 |
| 开关键 | `worker.resume_auto_recovery.enabled`，默认 True（`get_flag` 风格与 `worker.execution.execution_lock_enabled` 一致；即 spec 中的 `resume_auto_recovery_on`） |
| 审计文件 | `<QUANTCELL_DATA_DIR>/live/worker_{id}.auto_recovery.ndjson`，追加行 JSON：`{ts, worker_id, verdict, reconcile_report}`；24h 滑动窗口 ≥3 次触发止损 |
| 归档函数 | 现有 `StrategyManager.archive_journal_files(worker_id)`（journal 与 reconcile 报告移入 `archive/` 子目录，测试 `tests/unit/worker/test_journal_archive.py` 已覆盖） |

---

### Task 1: Rust 锁定守卫拒绝前缀契约（axon_quant 仓）

**Files:**
- Modify: `/Users/liupeng/workspace/quant/axon_quant/crates/axon-worker/src/live_driver.rs`（常量区 + `resume_attempt` format 处 + 文件底部新增测试模块）

说明：Python 侧按错误消息前缀识别「可自动恢复」，这是 Rust→Python 的弱契约。做法是最小重构：提取常量 + format! 引用 + 断言常量值的测试（行为零变化）。改 .rs 后必须按项目规则同步 .so 并跑契约门禁。

- [ ] **Step 1: 在文件常量区（`FANOUT_CHANNEL_CAPACITY` 附近）新增常量**

```rust
/// resume 守卫拒绝错误的固定前缀。QuantCell Python 侧
///（worker/resume_auto_recovery.py）按该前缀识别「可自动归档重启」，
/// 属跨语言弱契约：改前缀会静默破坏自动恢复。测试锁定。
const RESUME_GUARD_REJECT_PREFIX: &str = "恢复守卫拒绝继续交易";
```

- [ ] **Step 2: 修改 `resume_attempt` 中的错误构造（L444-446）**

原代码：

```rust
            return Err(format!(
                "恢复守卫拒绝继续交易，请人工核对持仓与资金后重试 resume: {reason}{retry}"
            ));
```

改为：

```rust
            return Err(format!(
                "{RESUME_GUARD_REJECT_PREFIX}，请人工核对持仓与资金后重试 resume: {reason}{retry}"
            ));
```

- [ ] **Step 3: 文件底部新增测试模块（若已有 `#[cfg(test)] mod tests` 则并入）**

```rust
#[cfg(test)]
mod tests {
    use super::RESUME_GUARD_REJECT_PREFIX;

    /// 锁定跨语言弱契约：Python worker/resume_auto_recovery.py 的
    /// RESUME_GUARD_PREFIX 必须与该值一致（自动恢复的触发开关）。
    #[test]
    fn resume_guard_reject_prefix_is_stable() {
        assert_eq!(RESUME_GUARD_REJECT_PREFIX, "恢复守卫拒绝继续交易");
    }
}
```

- [ ] **Step 4: 跑 Rust 测试确认通过**

Run: `cd /Users/liupeng/workspace/quant/axon_quant && cargo test -p axon-worker --locked --lib -- resume_guard_reject_prefix_is_stable`
Expected: `test result: ok`（1 passed）

- [ ] **Step 5: 同步 .so 到 backend 并跑契约门禁（项目铁律，缺一不可）**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend && uv sync --frozen --reinstall-package axon-quant
cd /Users/liupeng/workspace/quant/QuantCell/backend && uv run pytest tests/conformance/ -q
```

Expected: 契约测试全部 PASS

- [ ] **Step 6: 提交（在 axon_quant 仓）**

```bash
cd /Users/liupeng/workspace/quant/axon_quant && cargo fmt --all
git add crates/axon-worker/src/live_driver.rs
git commit -m "test: 锁定 resume 守卫拒绝错误前缀契约（QuantCell 自动恢复依赖）"
```

---

### Task 2: 新模块骨架 —— 前缀判定 + ndjson 审计（记录 / 窗口计数）

**Files:**
- Create: `backend/worker/resume_auto_recovery.py`
- Test: `backend/tests/unit/worker/test_resume_auto_recovery.py`

设计约束（spec §处置序列/§频次止损）：前缀常量与 Rust 侧一致；ndjson 追加式（O_APPEND 单行行为近似原子，进程内加 threading.Lock 防并发交织）；坏行容忍（半行写入 / 手改不炸）；读失败按 0 处理（审计文件不阻断重启链）。

- [ ] **Step 1: 写失败测试（新建测试文件）**

```python
"""worker.resume_auto_recovery 单元测试。

自动恢复 = resume 守卫拒绝后自动归档 journal 并以交易所为准 fresh start。
本测试文件只覆盖决策层（前缀/ndjson/开关止损/撤单/编排）；驱动线程挂钩的
行为验证见 Task 6 与 docs/testing/pages/strategy-worker.md 手工用例。
"""

import json
import time
from pathlib import Path

import pytest

from worker import resume_auto_recovery as rar


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "celldata"
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(d))
    return d


# ---------- 前缀判定 ----------


def test_is_resume_guard_reject_matches_rust_prefix():
    value = "恢复守卫拒绝继续交易，请人工核对持仓与资金后重试 resume: 持仓断裂（对账报告已落盘: x）"
    assert rar.is_resume_guard_reject(value)


def test_is_resume_guard_reject_rejects_other_errors():
    assert not rar.is_resume_guard_reject("journal 重演失败: bad entry")
    assert not rar.is_resume_guard_reject("")
    # 前缀必须出现在开头，中间匹配不算
    assert not rar.is_resume_guard_reject("error: 恢复守卫拒绝继续交易")


# ---------- ndjson 记录与计数 ----------


def test_recovery_log_path_honors_data_dir(data_dir):
    p = rar.recovery_log_path(901)
    assert p == data_dir / "live" / "worker_901.auto_recovery.ndjson"


def test_record_recovery_appends_one_json_row(data_dir):
    rar.record_recovery(901, {"position_breaks": 1})
    path = rar.recovery_log_path(901)
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["worker_id"] == 901
    assert row["verdict"] == "adopted"
    assert row["reconcile_report"] == {"position_breaks": 1}
    # RFC 3339：含时区偏移的可解析 ISO 串
    assert row["ts"].endswith("+00:00")


def test_recent_recovery_count_counts_rows_in_window(data_dir):
    a = rar.recovery_log_path(902)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(
        json.dumps({"ts": "2026-11-28T10:00:00+00:00", "worker_id": 902, "verdict": "adopted"}) + "\n"
        + json.dumps({"ts": "2026-11-27T11:00:00+00:00", "worker_id": 902, "verdict": "adopted"}) + "\n",
        encoding="utf-8",
    )
    # now 锚在 2026-11-28T12:00:00Z=1764321600：两行都在 24h 内
    assert rar.recent_recovery_count(902, now=1764321600.0) == 2


def test_recent_recovery_count_ignores_rows_outside_window(data_dir):
    a = rar.recovery_log_path(903)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(
        json.dumps({"ts": "2026-11-25T10:00:00+00:00", "worker_id": 903, "verdict": "adopted"}) + "\n",
        encoding="utf-8",
    )
    assert rar.recent_recovery_count(903, now=1764321600.0) == 0


def test_recent_recovery_count_tolerates_bad_lines_and_missing_file(data_dir):
    a = rar.recovery_log_path(904)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text("not-json\n\n{\"ts\":\"2026-11-28T10:00:00+00:00\"}\n", encoding="utf-8")
    assert rar.recent_recovery_count(904, now=1764321600.0) == 1
    assert rar.recent_recovery_count(999) == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v`
Expected: FAIL，`ModuleNotFoundError: ... 'worker' has no attribute 'resume_auto_recovery'`（collection error）

- [ ] **Step 3: 实现（新建 `backend/worker/resume_auto_recovery.py`）**

```python
"""resume 对账守卫拒绝后的自动恢复（归档重启，以交易所为准）。

设计见 docs/design/2026-11-28-worker-resume-auto-recovery-design.md：
Rust resume_guard 拒绝 →（开关开 & 24h 内未满 3 次）→ best-effort 撤单 →
归档 journal → fresh start（adopt 交易所持仓与现金）。本模块只做决策与
处置编排，驱动线程挂钩见 strategy_manager._driver_live_thread_main；
运行期漂移仍由周期对账兜底（worker.reconciliation.*），本模块不重复其职责。
"""

import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 与 Rust live_driver.rs 的 RESUME_GUARD_REJECT_PREFIX 一致（弱契约，Rust
# 侧有测试断言锁定）。Rust 改前缀时两侧必须同步改。
RESUME_GUARD_PREFIX = "恢复守卫拒绝继续交易"

# 频次止损：24h 滑动窗口内满 3 次即停（spec §频次止损）
_WINDOW_S = 24 * 3600
_WINDOW_LIMIT = 3

# 同 worker 可能有多线程并发恢复场景（重启竞态），追加写加进程内锁防行交织。
# ponytail: O_APPEND 单行 <PIPE_BUF 已近似原子，锁只对齐同进程顺序，够用
_ndjson_lock = threading.Lock()


def is_resume_guard_reject(error_message: str) -> bool:
    """识别 Rust resume_guard 拒绝错误（按固定前缀，避免解析中文全文）。"""
    return error_message.startswith(RESUME_GUARD_PREFIX)


def recovery_log_path(worker_id: int) -> Path:
    """频次止损审计文件路径（与 journal 同属 live 目录，但文件独立于归档）。"""
    data_dir = os.environ.get("QUANTCELL_DATA_DIR")
    base = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"
    return base / "live" / f"worker_{worker_id}.auto_recovery.ndjson"


def record_recovery(worker_id: int, reconcile_report: dict[str, Any] | None = None) -> None:
    """追加一条自动恢复审计记录（ndjson 一行）。写失败只告警不抛：审计缺失
    不应让 worker 起不来。"""
    path = recovery_log_path(worker_id)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "worker_id": worker_id,
        "verdict": "adopted",
        "reconcile_report": reconcile_report,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _ndjson_lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        logger.warning(f"自动恢复审计写入失败（忽略）: worker_id={worker_id}, error={e}")


def recent_recovery_count(worker_id: int, *, now: float | None = None) -> int:
    """24h 滑动窗口内的自动恢复次数。文件缺失/不可读/坏行一律跳过：审计
    文件只服务于止损计数，任何读异常都不能阻断重启链。"""
    path = recovery_log_path(worker_id)
    if not path.is_file():
        return 0
    now = time.time() if now is None else now
    count = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 坏行容忍：半行写入或手改
                try:
                    ts = datetime.fromisoformat(str(row.get("ts"))).timestamp()
                except ValueError:
                    continue
                if now - ts <= _WINDOW_S:
                    count += 1
    except OSError:
        return 0
    return count
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v`
Expected: PASS（7 个用例全绿）

- [ ] **Step 5: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && git add backend/worker/resume_auto_recovery.py backend/tests/unit/worker/test_resume_auto_recovery.py && git commit -m "feat: worker resume 自动恢复模块（前缀判定 + ndjson 审计）"
```

---

### Task 3: 自动恢复总闸 —— 开关 + 频次止损

**Files:**
- Modify: `backend/worker/resume_auto_recovery.py`（文件末尾追加）
- Modify: `backend/tests/unit/worker/test_resume_auto_recovery.py`（末尾追加用例）

开关走 `utils.config_manager.get_flag`（键 `worker.resume_auto_recovery.enabled`，默认 True），与 strategy_manager 现有旗标读取同风格（函数内 import，注释原因同上——config_manager 顶层拉 collector.db 有循环 import 风险）。

- [ ] **Step 1: 追加失败测试**

```python
# ---------- 总闸：开关 + 频次止损 ----------


def test_should_auto_recover_disabled_by_flag(data_dir, monkeypatch):
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default: False)
    ok, reason = rar.should_auto_recover(910)
    assert ok is False
    assert "开关" in reason


def test_should_auto_recover_blocked_after_three_in_window(data_dir):
    a = rar.recovery_log_path(911)
    a.parent.mkdir(parents=True, exist_ok=True)
    ts_row = json.dumps({"ts": "2026-11-28T10:00:00+00:00", "worker_id": 911, "verdict": "adopted"})
    a.write_text("\n".join([ts_row] * 3) + "\n", encoding="utf-8")
    ok, reason = rar.should_auto_recover(911, now=1764321600.0)
    assert ok is False
    assert "24h" in reason or "止损" in reason


def test_should_auto_recover_allowed_by_default(data_dir, monkeypatch):
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default: default)
    ok, reason = rar.should_auto_recover(912)
    assert ok is True
    assert reason == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v -k should_auto_recover`
Expected: FAIL，`AttributeError: ... has no attribute 'should_auto_recover'`

- [ ] **Step 3: 实现（追加到模块末尾）**

```python
def should_auto_recover(worker_id: int, *, now: float | None = None) -> tuple[bool, str]:
    """自动恢复总闸：开关 + 频次止损。返回（是否允许，拒绝原因）。

    拒绝原因用于 wlog 交代理由（不是人工确认门——只限制自动化冷却，
    用户仍可手工点「归档并启动」）。
    """
    # 函数内 import 与 strategy_manager 同口径：config_manager 顶层拉
    # collector.db，防 worker.__init__ 循环链在部分入口被点爆
    from utils.config_manager import get_flag

    if not get_flag("worker.resume_auto_recovery.enabled", True):
        return False, "自动恢复开关关闭（worker.resume_auto_recovery.enabled）"
    if recent_recovery_count(worker_id, now=now) >= _WINDOW_LIMIT:
        return False, f"自动恢复止损：24h 内已自动归档重启 {_WINDOW_LIMIT} 次，需人工排查漂移根因"
    return True, ""
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v`
Expected: PASS（10 个用例全绿）

- [ ] **Step 5: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && git add backend/worker/resume_auto_recovery.py backend/tests/unit/worker/test_resume_auto_recovery.py && git commit -m "feat: 自动恢复总闸（开关 + 24h 频次止损）"
```

---

### Task 4: best-effort 撤单

**Files:**
- Modify: `backend/worker/resume_auto_recovery.py`
- Modify: `backend/tests/unit/worker/test_resume_auto_recovery.py`

撤单通道（规划期已核实）：`LiveTradeSync.ccxt_symbol`（property，`worker/live_trade_sync.py` L172-175）+ `LiveTradeSync.exchange.exchange`（ccxt 实例）的 `fetch_open_orders` / `cancel_order`。spec 语义：best-effort，任何失败只告警继续（归档 adopt 与人工路径暴露面相同，撤单只是增强，网关验证不到的挂单差额由止损与运行期对账兜底）。

- [ ] **Step 1: 追加失败测试**

```python
# ---------- best-effort 撤单 ----------

from types import SimpleNamespace
from unittest.mock import MagicMock


def _fake_trade_sync(open_orders=None, raises=False):
    ccxt = MagicMock()
    if raises:
        ccxt.fetch_open_orders.side_effect = RuntimeError("network down")
    else:
        ccxt.fetch_open_orders.return_value = open_orders or []
    ts = SimpleNamespace(exchange=SimpleNamespace(exchange=ccxt), ccxt_symbol="ETH/USDT:USDT")
    return ts, ccxt


def test_cancel_skips_without_trade_sync():
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(None, wlog)
    wlog.info.assert_called_once()


def test_cancel_fetches_and_cancels_all_orders():
    ts, ccxt = _fake_trade_sync(open_orders=[{"id": "1"}, {"id": "2"}])
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(ts, wlog)
    ccxt.fetch_open_orders.assert_called_once_with("ETH/USDT:USDT")
    assert ccxt.cancel_order.call_args_list == [
        (("1", "ETH/USDT:USDT"),),
        (("2", "ETH/USDT:USDT"),),
    ]


def test_cancel_swallows_fetch_failure():
    ts, _ = _fake_trade_sync(raises=True)
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(ts, wlog)  # 不抛即通过
    wlog.warning.assert_called()


def test_cancel_swallows_per_order_failure():
    ts, ccxt = _fake_trade_sync(open_orders=[{"id": "1"}])
    ccxt.cancel_order.side_effect = RuntimeError("order gone")
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(ts, wlog)  # 不抛即通过
    wlog.warning.assert_called()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v -k cancel`
Expected: FAIL，`AttributeError: ... has no attribute 'best_effort_cancel_open_orders'`

- [ ] **Step 3: 实现（追加到模块末尾）**

```python
def best_effort_cancel_open_orders(trade_sync: Any, wlog: Any) -> None:
    """撤掉该 worker 品种的全部在挂单（best-effort，任何失败不抛出）。

    撤单走 LiveTradeSync 内已构造好的 ccxt 实例（凭证/symbol/连接复用）；
    trade_sync 为 None（LiveTradeSync 构造失败）时整体跳过——归档 adopt 的
    暴露面与人工归档路径相同，撤单只是增强屏障，不构成处置前置条件。
    """
    if trade_sync is None:
        wlog.info("自动恢复撤单跳过：无 trade_sync 成交同步通道")
        return
    ccxt = getattr(getattr(trade_sync, "exchange", None), "exchange", None)
    if ccxt is None:
        wlog.warning("自动恢复撤单跳过：trade_sync 未持有 ccxt 实例")
        return
    symbol = trade_sync.ccxt_symbol
    try:
        orders = ccxt.fetch_open_orders(symbol) or []
    except Exception as e:
        wlog.warning(f"自动恢复撤单失败（继续归档处置）: symbol={symbol}, error={e}")
        return
    for order in orders:
        try:
            ccxt.cancel_order(order.get("id"), symbol)
        except Exception as e:
            wlog.warning(
                f"自动恢复单笔撤单失败（继续）: symbol={symbol}, "
                f"order_id={order.get('id')}, error={e}"
            )
    wlog.info(f"自动恢复撤单完成: symbol={symbol}, 处理挂单数={len(orders)}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v`
Expected: PASS（14 个用例全绿）

- [ ] **Step 5: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && git add backend/worker/resume_auto_recovery.py backend/tests/unit/worker/test_resume_auto_recovery.py && git commit -m "feat: 自动恢复 best-effort 撤单（ccxt fetch_open_orders + cancel_order）"
```

---

### Task 5: 处置编排 `try_auto_recover`

**Files:**
- Modify: `backend/worker/resume_auto_recovery.py`
- Modify: `backend/tests/unit/worker/test_resume_auto_recovery.py`

编排顺序（spec §处置序列，顺序即契约）：前缀判定 → 总闸（开关+止损）→ 撤单 → 归档 → 追加审计 ndjson → 返回 True。归档函数由调用方注入（线程侧传 `self.archive_journal_files`，测试传 fake），归档失败返回 False 放弃自动恢复（journal 未动，人工路径期待原状）。

- [ ] **Step 1: 追加失败测试**

```python
# ---------- 处置编排 ----------


def test_try_auto_recover_rejects_non_guard_error():
    calls: list[str] = []
    ok = rar.try_auto_recover(
        920, "journal 重演失败: x", None, MagicMock(), archive_fn=lambda wid: calls.append("archive") or []
    )
    assert ok is False
    assert calls == []


def test_try_auto_recover_honors_gate(monkeypatch):
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default: False)
    ok = rar.try_auto_recover(
        921,
        rar.RESUME_GUARD_PREFIX + "，xxxx",
        None,
        MagicMock(),
        archive_fn=lambda wid: [],
    )
    assert ok is False


def test_try_auto_recover_runs_cancel_before_archive_and_records(data_dir):
    calls: list[str] = []
    ts, ccxt = _fake_trade_sync(open_orders=[{"id": "9"}])

    def _cancel(order_id, symbol):
        calls.append("cancel")

    ccxt.cancel_order.side_effect = _cancel
    wlog = MagicMock()

    def _archive(worker_id: int) -> list[dict]:
        calls.append("archive")
        return [{"from": "a.jsonl", "to": "archive/a.jsonl"}]

    ok = rar.try_auto_recover(922, rar.RESUME_GUARD_PREFIX + "：持仓不一致", ts, wlog, archive_fn=_archive)
    assert ok is True
    assert calls == ["cancel", "archive"]  # 顺序契约：先撤单后归档
    row = json.loads(rar.recovery_log_path(922).read_text(encoding="utf-8").strip())
    assert row["verdict"] == "adopted"
    assert row["reconcile_report"] is None  # 未提供 journal_path


def test_try_auto_recover_records_reconcile_report(data_dir, tmp_path):
    journal = tmp_path / "worker_923.jsonl"
    journal.write_text("{}", encoding="utf-8")
    journal.with_suffix(".reconcile.json").write_text('{"position_breaks": 1}', encoding="utf-8")
    ok = rar.try_auto_recover(
        923, rar.RESUME_GUARD_PREFIX + "：x", None, MagicMock(),
        archive_fn=lambda wid: [], journal_path=str(journal),
    )
    assert ok is True
    row = json.loads(rar.recovery_log_path(923).read_text(encoding="utf-8").strip())
    assert row["reconcile_report"] == {"position_breaks": 1}


def test_try_auto_recover_aborts_when_archive_fails(data_dir):
    wlog = MagicMock()

    def _boom(worker_id: int) -> list[dict]:
        raise RuntimeError("mv 失败")

    ok = rar.try_auto_recover(924, rar.RESUME_GUARD_PREFIX + "：x", None, wlog, archive_fn=_boom)
    assert ok is False
    assert not rar.recovery_log_path(924).exists()  # 归档失败不记审计
    wlog.error.assert_called()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v -k try_auto_recover`
Expected: FAIL，`AttributeError: ... has no attribute 'try_auto_recover'`

- [ ] **Step 3: 实现（追加到模块末尾）**

```python
def _load_reconcile_report(journal_path: str | None) -> dict[str, Any] | None:
    """守卫拒绝时 Rust 已把报告落盘到 journal 旁（worker_N.reconcile.json）；
    归档前读一份进审计。读不到（落盘失败/路径异常）记 None，不阻断处置。"""
    if not journal_path:
        return None
    try:
        report_path = Path(journal_path).with_suffix(".reconcile.json")
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def try_auto_recover(
    worker_id: int,
    error_message: str,
    trade_sync: Any,
    wlog: Any,
    *,
    archive_fn: Callable[[int], list[dict]],
    journal_path: str | None = None,
    now: float | None = None,
) -> bool:
    """守卫拒绝后的自动处置编排。True = 已归档，调用方应立即 driver.start 重启。

    顺序即契约（spec §处置序列）：判定 → 总闸 → 撤单 → 归档 → 审计。
    返回 False 的所有情况（非守卫错误/开关关/止损命中/归档失败）都已 wlog
    说明，调用方走原有失败路径落 worker error 状态。
    """
    if not is_resume_guard_reject(error_message):
        return False
    ok, reason = should_auto_recover(worker_id, now=now)
    if not ok:
        wlog.warning(f"resume 对账不一致未自动恢复: worker_id={worker_id}, 原因=({reason})")
        return False
    report = _load_reconcile_report(journal_path)
    report_path = Path(journal_path).with_suffix(".reconcile.json") if journal_path else None
    wlog.warning(
        f"resume 对账不一致（可自动恢复），开始处置: worker_id={worker_id}, "
        f"报告路径={report_path or '未落盘'}, "
        f"reconcile_report={json.dumps(report, ensure_ascii=False, default=str)[:500] if report else '无'}"
    )
    best_effort_cancel_open_orders(trade_sync, wlog)
    try:
        moved = archive_fn(worker_id)
    except Exception as e:
        wlog.error(f"journal 归档失败，放弃自动恢复（保留现场人工处置）: worker_id={worker_id}, error={e}")
        return False
    wlog.info(f"journal 已归档: worker_id={worker_id}, files={moved}")
    record_recovery(worker_id, report)
    return True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v`
Expected: PASS（19 个用例全绿）

- [ ] **Step 5: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && git add backend/worker/resume_auto_recovery.py backend/tests/unit/worker/test_resume_auto_recovery.py && git commit -m "feat: 自动恢复处置编排 try_auto_recover（判定→止损→撤单→归档→审计）"
```

---

### Task 6: 驱动线程挂钩（strategy_manager）

**Files:**
- Modify: `backend/worker/strategy_manager.py`（顶部 import 区 + `_driver_live_thread_main` except 块 L1131-1138 + 新增私有方法）
- Modify: `backend/tests/unit/worker/test_resume_auto_recovery.py`（追加挂钩用例）

挂钩语义：except 分支先问 `try_auto_recover`（传入 `self.archive_journal_files`）。False → 原有两行错误路径**原样保留**（旧行为不动的兜底）；True → `driver.start` fresh start（journal 已归档，Rust 走 start+adopt），成功后发前端可见事件文案，失败落 error。`_mark_rl_live_error` 的完整复发处置（registry/DB/事件）不动。

- [ ] **Step 1: 追加失败测试（挂钩行为只测到「方法返回」级别，不做整线程 tick 循环验证——恢复成功的全程链路由 docs/testing 手工用例覆盖）**

```python
# ---------- 驱动线程挂钩 ----------

import threading

import worker.strategy_manager as sm_module
from worker.strategy_manager import StrategyManager


def _guard_error(_path: str) -> None:
    raise RuntimeError(f"{rar.RESUME_GUARD_PREFIX}，请人工核对持仓与资金后重试 resume: x")


@pytest.fixture
def hooked_manager(monkeypatch):
    """绕过 __init__ 的 StrategyManager；不真启 log sink，_mark_rl_live_error 换收集器。"""
    manager = object.__new__(StrategyManager)
    manager._kernel_runs = {}
    monkeypatch.setattr(sm_module, "start_worker_log_sink", lambda wid: None)
    errors: list[str] = []
    monkeypatch.setattr(manager, "_mark_rl_live_error", lambda wid, msg: errors.append(msg))
    return manager, errors


def _journal_file(tmp_path: Path) -> Path:
    journal = tmp_path / "worker_930.jsonl"
    journal.write_text('{"t":1}\n', encoding="utf-8")
    return journal


def test_live_thread_falls_back_to_error_when_gate_rejects(hooked_manager, tmp_path, monkeypatch):
    manager, errors = hooked_manager
    journal = _journal_file(tmp_path)
    monkeypatch.setattr(sm_module.resume_auto_recovery, "try_auto_recover", lambda *a, **k: False)

    driver = SimpleNamespace(connect=lambda: None, resume=_guard_error, start=lambda p: None)
    manager._driver_live_thread_main(930, driver, str(journal), threading.Event(), None)

    assert len(errors) == 1
    assert "实盘连接/恢复失败" in errors[0]
    assert 930 not in manager._kernel_runs


def test_live_thread_retries_start_after_auto_recover_then_errors(hooked_manager, tmp_path, monkeypatch):
    """自动恢复已归档但 fresh start 失败：落「自动恢复后启动失败」并退出线程。"""
    manager, errors = hooked_manager
    journal = _journal_file(tmp_path)
    monkeypatch.setattr(
        sm_module.resume_auto_recovery, "try_auto_recover",
        lambda *a, **k: True,  # 归档/撤单/审计已由 Task 5 单测覆盖
    )

    def _start_boom(_path: str) -> None:
        raise RuntimeError("start 失败：交易所不可达")

    driver = SimpleNamespace(connect=lambda: None, resume=_guard_error, start=_start_boom)
    manager._driver_live_thread_main(931, driver, str(journal), threading.Event(), None)

    assert len(errors) == 1
    assert "自动恢复后启动失败" in errors[0]
    assert 931 not in manager._kernel_runs


def test_live_thread_passes_archive_fn_from_manager(hooked_manager, tmp_path, monkeypatch):
    """挂钩必须传 self.archive_journal_files（而不是模块内另起炉灶）。"""
    manager, errors = hooked_manager
    journal = _journal_file(tmp_path)
    captured: dict[str, object] = {}

    def _fake_try(worker_id, error_message, trade_sync, wlog, *, archive_fn, journal_path=None, now=None):
        captured["archive_fn"] = archive_fn
        captured["journal_path"] = journal_path
        return False

    monkeypatch.setattr(sm_module.resume_auto_recovery, "try_auto_recover", _fake_try)
    driver = SimpleNamespace(connect=lambda: None, resume=_guard_error, start=lambda p: None)
    manager._driver_live_thread_main(932, driver, str(journal), threading.Event(), None)
    assert captured["archive_fn"] == manager.archive_journal_files
    assert captured["journal_path"] == str(journal)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py -v -k live_thread`
Expected: FAIL——当前 except 块不走 `try_auto_recover`，`test_live_thread_passes_archive_fn_from_manager` 的 captured 为空断言失败

- [ ] **Step 3: 修改 `backend/worker/strategy_manager.py` 顶部 import 区（`from . import crud, execution_lock` 下一行）**

```python
from . import resume_auto_recovery
```

- [ ] **Step 4: 替换 `_driver_live_thread_main` 的 except 块（L1131-1138）**

原代码：

```python
        except Exception as e:
            wlog.error(
                f"[StrategyManager] 实盘连接/恢复失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            self._mark_rl_live_error(worker_id, f"实盘连接/恢复失败: {e}")
            # 线程已死，原地清掉运行态，避免残留条目让后续 stop/restart 摸到僵尸驱动
            self._kernel_runs.pop(worker_id, None)
            return
```

改为：

```python
        except Exception as e:
            # P-恢复：对账守卫拒绝（恢复守卫拒绝继续交易）走自动恢复——归档旧
            # journal 并以交易所为准 fresh start；其余异常/总闸拒绝保持原失败路径
            if not resume_auto_recovery.try_auto_recover(
                worker_id,
                str(e),
                trade_sync,
                wlog,
                archive_fn=self.archive_journal_files,
                journal_path=str(journal),
            ):
                wlog.error(
                    f"[StrategyManager] 实盘连接/恢复失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
                )
                self._mark_rl_live_error(worker_id, f"实盘连接/恢复失败: {e}")
                # 线程已死，原地清掉运行态，避免残留条目让后续 stop/restart 摸到僵尸驱动
                self._kernel_runs.pop(worker_id, None)
                return
            if not self._restart_after_auto_recover(worker_id, driver, journal, wlog):
                return
```

- [ ] **Step 5: 新增私有方法 `_restart_after_auto_recover`（紧随 `_mark_rl_live_error` 方法之后）**

```python
    def _restart_after_auto_recover(self, worker_id: int, driver: Any, journal: Path, wlog: Any) -> bool:
        """自动恢复后的 fresh start（journal 已归档，Rust 走 start+adopt 以
        交易所持仓与现金重锚）。返回 False 表示重启失败已落 error，线程退出。"""
        try:
            driver.start(str(journal))
        except Exception as e:
            wlog.error(
                f"[StrategyManager] 自动恢复后 fresh start 失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            self._mark_rl_live_error(worker_id, f"实盘自动恢复后启动失败: {e}")
            self._kernel_runs.pop(worker_id, None)
            return False
        # 前端事件文案（spec §前端呈现）：per-worker 日志面板 + 错误日志通道可见
        wlog.warning("[StrategyManager] 对账不一致，已归档并按交易所为准自动重建（fresh start adopt）")
        return True
```

- [ ] **Step 6: 跑测试确认通过（本文件全部 + worker 存量回归）**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/test_resume_auto_recovery.py tests/unit/worker/test_journal_archive.py tests/unit/worker/test_worker_lifecycle.py -v`
Expected: PASS（无回归）

- [ ] **Step 7: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && git add backend/worker/strategy_manager.py backend/tests/unit/worker/test_resume_auto_recovery.py && git commit -m "feat: live 驱动线程挂钩自动恢复（守卫拒绝→归档→fresh start adopt）"
```

---

### Task 7: docs/testing 同步 + 全量回归收尾

**Files:**
- Modify: `docs/testing/pages/strategy-worker.md`（追加验证项 + 历史雷区；无新路由，MANIFEST 不动）
- 无代码改动

- [ ] **Step 1: 向 `docs/testing/pages/strategy-worker.md` 末尾追加验证项（若该页有「验收标准」类小节则并入对应小节，格式对齐 `pages/home.md` 的打勾风格）**

```markdown
## Resume 自动恢复（以交易所为准）

- [ ] 开关验证：`worker.resume_auto_recovery.enabled` 置 false（系统配置表）→ 制造切换为 error 的 live worker（如改端口/断网启动）→ worker 落「实盘连接/恢复失败」错误，行为与旧版本一致，不触发归档
- [ ] 正常路径验证（testnet）：live worker 正常交易中断电/重启 → resume 对账通过时不触发自动恢复（对账一致本来就不会拒绝）
- [ ] 止损验证：手工向 `backend/data/live/worker_{id}.auto_recovery.ndjson` 追加 3 行（`{"ts":"<当前 UTC ISO>","worker_id":N,"verdict":"adopted"}`）→ 启动一个 resume 守卫拒绝的 worker（有真实对账差异）→ 不自动归档，落错误 + 日志出现「需人工排查漂移根因」
- [ ] 审计验证：自动恢复成功后 `worker_{id}.auto_recovery.ndjson` 多一行，`verdict` 为 `adopted`，`reconcile_report` 含 `position_breaks` 或 `cash_break`
- [ ] 前端文案验证：恢复成功的 worker 日志面板出现「对账不一致，已归档并按交易所为准自动重建（fresh start adopt）」，worker 状态回到 running
```

- [ ] **Step 2: 在同一文件「历史雷区」栏追加一条（若无该栏则新建）**

```markdown
- 2026-11-28：worker_3 实盘重启触发 Rust resume_guard 拒绝（venue 宕机期间成交 4 笔、journal 漏记，现金差≈手续费+资金费）。人工归档是正解但每次都要手点，已在 `_driver_live_thread_main` 挂钩自动恢复：归档 → fresh start（adopt）。注意守卫拒绝错误的前缀「恢复守卫拒绝继续交易」是 Rust 接口契约（axon_quant 有测试锁定），改前缀必须两侧同步。
```

- [ ] **Step 3: 覆盖检查 + 全量 worker 单测**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && node docs/testing/check-coverage.mjs
cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/worker/ -q
```

Expected: check-coverage 全绿（无新路由，MANIFEST 不增量）；worker 单测全绿（含 test_journal_archive / test_worker_lifecycle / test_core_service / test_funding_close_recon 等存量）

- [ ] **Step 4: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell && git add docs/testing/pages/strategy-worker.md && git commit -m "docs: 新增 Resume 自动恢复验证项与历史雷区记录"
```

---

## 验证对照（计划 ↔ spec 测试计划）

| spec 测试计划 | 计划落点 |
|---|---|
| 错误前缀判定 | Task 1（Rust 常量+断言）+ Task 2（`is_resume_guard_reject` 3 用例） |
| 处置序列顺序（撤单→归档→审计） | Task 5 `test_try_auto_recover_runs_cancel_before_archive_and_records`（calls 顺序断言） |
| ndjson 频次达标不自动 | Task 3 `test_should_auto_recover_blocked_after_three_in_window` + Task 5 gate 用例 |
| 开关关闭等同现状 | Task 3 flag 用例 + Task 6 `test_live_thread_falls_back_to_error_when_gate_rejects` |
| docs/testing 页面 + check-coverage | Task 7 |

