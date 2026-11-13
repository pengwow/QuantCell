"""get_result_list 的 source 来源过滤行为校验。

RL 模型回测任务 strategy_name 带 rl_model:X / rl_ensemble:X 前缀；模型中心
「RL 回测历史」Tab 依赖 source='rl' 只取这两类任务。锁四件事：
1. source='rl' 只返回两种 RL 前缀的任务行
2. 缺省（source=None）返回全量，普通策略不受影响
3. source 与 keyword 可叠加（两个条件都命中的行才返回）
4. 非 'rl' 的值忽略不过滤（OpenAPI description 写明语义，不做白名单报错）
"""

import json

from backtest.service import BacktestService


def _make_service(tmp_path) -> BacktestService:
    """服务实例指向临时目录，不碰真实 data/ 下的回测任务与结果"""
    svc = BacktestService()
    svc.results_dir = tmp_path / "backtest_results"
    svc.results_dir.mkdir(parents=True, exist_ok=True)
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
    _write_task(svc, "rl2", "rl_ensemble:e1")
    _write_task(svc, "plain", "dual_ma")


def test_source_rl_returns_only_rl_prefixed(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    rows, total = svc.get_result_list(source="rl")
    assert total == 2
    assert sorted(r["id"] for r in rows) == ["rl1", "rl2"]


def test_source_none_keeps_all(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    _rows, total = svc.get_result_list()
    assert total == 3


def test_source_composes_with_keyword(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    rows, total = svc.get_result_list(source="rl", keyword="m1")
    # 关键字仅命中 rl_model:m1 的行（rl2 的 ensemble id 不含 'm1'）
    assert total == 1 and rows[0]["id"] == "rl1"


def test_source_other_values_ignored(tmp_path) -> None:
    svc = _make_service(tmp_path)
    _seed(svc)

    _rows, total = svc.get_result_list(source="unknown")
    assert total == 3
