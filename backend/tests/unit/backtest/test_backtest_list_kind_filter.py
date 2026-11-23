"""get_result_list 的 kind 类型过滤与 strategy_kind 标注校验。

回测任务混合规则 / RL / LLM 三类策略，「类型」列与类型筛选共用同一条口径
（StrategyService._strategy_kind，与策略管理页同源）：

1. kind='rl' 只返回 rl_model:/rl_ensemble: 前缀任务（模型中心直发不落策略文件）
2. kind='rule' / kind='llm' 按策略文件 AST 判定（llm 的库内标识是参数 mode="llm"）
3. kind=None 不过滤，但每行仍带 strategy_kind（策略已删 → None，前端显示「—」）
4. 已删策略的任务不被任何 kind 筛中（不按名字猜类型），total 随过滤变化
"""

import json

from backtest.service import BacktestService
from strategy.service import StrategyService

RULE_SRC = '''"""规则策略探针"""


class RuleProbe:
    def on_bar(self, bar):
        return None
'''

LLM_SRC = '''"""LLM 策略探针"""


class LlmProbe:
    def on_bar(self, bar):
        mode = self.get_param("mode", "llm")
        return mode
'''


def _make_service(tmp_path) -> BacktestService:
    svc = BacktestService()
    svc.results_dir = tmp_path / "backtest_results"
    svc.results_dir.mkdir(parents=True, exist_ok=True)
    # 类型解析读策略文件：把 kind 服务指向临时策略目录，不碰真实 strategies/
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    (strategies_dir / "rule_probe.py").write_text(RULE_SRC, encoding="utf-8")
    (strategies_dir / "llm_probe.py").write_text(LLM_SRC, encoding="utf-8")
    kind_service = StrategyService()
    kind_service.strategy_dir = strategies_dir
    svc._kind_service = kind_service
    return svc


def _write_task(svc: BacktestService, task_id: str, strategy_name: str) -> None:
    tasks_dir = svc.results_dir.parent / "backtest_tasks"
    tasks_dir.mkdir(exist_ok=True)
    task = {
        "id": task_id,
        "strategy_name": strategy_name,
        "symbols": ["BTCUSDT"],
        "timeframes": ["1h"],
        "status": "completed",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    (tasks_dir / f"task_{task_id}.json").write_text(json.dumps(task), encoding="utf-8")


def _seed(svc: BacktestService) -> None:
    _write_task(svc, "rl1", "rl_model:m1")
    _write_task(svc, "rule1", "rule_probe")
    _write_task(svc, "llm1", "llm_probe")
    _write_task(svc, "gone", "deleted_strategy")


def test_kind_rl_returns_only_prefixed(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    rows, total = svc.get_result_list(kind="rl")
    assert total == 1
    assert [r["id"] for r in rows] == ["rl1"]
    assert rows[0]["strategy_kind"] == "rl"


def test_kind_rule_and_llm_use_strategy_files(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    rule_rows, rule_total = svc.get_result_list(kind="rule")
    assert rule_total == 1
    assert [r["id"] for r in rule_rows] == ["rule1"]
    assert rule_rows[0]["strategy_kind"] == "rule"

    llm_rows, llm_total = svc.get_result_list(kind="llm")
    assert llm_total == 1
    assert [r["id"] for r in llm_rows] == ["llm1"]
    assert llm_rows[0]["strategy_kind"] == "llm"


def test_no_kind_filter_annotates_all_rows(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    rows, total = svc.get_result_list()
    assert total == 4
    kinds = {r["id"]: r["strategy_kind"] for r in rows}
    assert kinds == {"rl1": "rl", "rule1": "rule", "llm1": "llm", "gone": None}


def test_deleted_strategy_not_matched_by_any_kind(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    for kind in ("rule", "rl", "llm"):
        rows, _total = svc.get_result_list(kind=kind)
        assert "gone" not in [r["id"] for r in rows]


def test_kind_filter_composes_with_status_and_keyword(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    rows, total = svc.get_result_list(kind="rule", keyword="RULE")
    assert total == 1 and [r["id"] for r in rows] == ["rule1"]

    _rows, total_miss = svc.get_result_list(kind="llm", keyword="RULE")
    assert total_miss == 0
