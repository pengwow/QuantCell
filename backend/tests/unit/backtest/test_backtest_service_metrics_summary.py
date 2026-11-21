"""BacktestService 列表页摘要指标（metrics_summary）行为校验。

回归背景：get_result_list 只透传任务元数据，不返回 total_return / max_drawdown，
首页「最近回测」显示 -%、回测记录表格显示 N/A。

锁住三件事：
1. 摘要从 results.portfolio.metrics 提取（所有回测模式的统一账户口径）
2. get_result_list 对无摘要的 completed 旧任务自动提取并回写任务文件（自愈，只发生一次）
3. failed 任务 / 结果文件缺失 → 指标为 None，前端保持 N/A
"""

import json

import pytest

from backtest.service import BacktestService


def _make_result(total_return: float, max_drawdown: float) -> dict:
    """构造与 engine_service._format_results 同构的最小结果（portfolio.metrics 是 {key, value} 数组）"""
    return {
        "status": "completed",
        "results": {
            "capital_mode": "shared",
            "portfolio": {
                "metrics": [
                    {"key": "total_return", "value": total_return},
                    {"key": "max_drawdown", "value": max_drawdown},
                    {"key": "sharpe_ratio", "value": 1.81},
                    {"key": "win_rate", "value": 54.0},
                    {"key": "total_trades", "value": 236},
                ]
            },
        },
    }


def _make_service(tmp_path) -> BacktestService:
    """服务实例指向临时目录，不碰真实 data/ 下的回测任务与结果"""
    svc = BacktestService()
    svc.results_dir = tmp_path / "backtest_results"
    svc.results_dir.mkdir(parents=True, exist_ok=True)
    return svc


def _write_task(svc: BacktestService, task_id: str, status: str, result: dict | None = None) -> None:
    tasks_dir = svc.results_dir.parent / "backtest_tasks"
    tasks_dir.mkdir(exist_ok=True)
    task = {
        "id": task_id,
        "strategy_name": "dual_ma",
        "symbols": ["BTCUSDT"],
        "timeframes": ["1h"],
        "status": status,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    (tasks_dir / f"task_{task_id}.json").write_text(json.dumps(task), encoding="utf-8")
    if result is not None:
        (svc.results_dir / f"result_{task_id}.json").write_text(json.dumps(result), encoding="utf-8")


def test_get_result_list_self_heals_missing_summary(tmp_path) -> None:
    """旧 completed 任务无摘要：列表接口从结果 JSON 提取并回写，返回值带指标"""
    svc = _make_service(tmp_path)
    _write_task(svc, "t1", "completed", result=_make_result(-3.94, 4.75))

    rows, _total = svc.get_result_list()
    assert rows[0]["total_return"] == pytest.approx(-3.94)
    assert rows[0]["max_drawdown"] == pytest.approx(4.75)

    # 自愈回写：任务文件带上 metrics_summary，后续列表零大结果文件 IO
    task_file = svc.results_dir.parent / "backtest_tasks" / "task_t1.json"
    task = json.loads(task_file.read_text(encoding="utf-8"))
    assert task["metrics_summary"]["total_return"] == pytest.approx(-3.94)


def test_failed_task_and_missing_result_yield_none(tmp_path) -> None:
    """failed 任务（无结果文件）→ 指标为 None，前端显示 N/A"""
    svc = _make_service(tmp_path)
    _write_task(svc, "t2", "failed")

    rows, _total = svc.get_result_list()
    assert rows[0]["total_return"] is None
    assert rows[0]["max_drawdown"] is None


def test_get_inline_summary_uses_v2_without_result_io(tmp_path) -> None:
    """任务文件已是 v2 摘要（含 metrics 字典）→ 直出，不读结果 JSON"""
    svc = _make_service(tmp_path)
    _write_task_full(
        svc,
        "s1",
        "completed",
        metrics_summary={
            "total_return": 1.0,
            "max_drawdown": 2.0,
            "metrics": {"total_return": 1.0, "sharpe_ratio": 2.5},
        },
    )
    # 结果文件故意放干扰值：若被读取会覆盖任务文件 v2
    (svc.results_dir / "result_s1.json").write_text(json.dumps(_make_result(99.0, 99.0)), encoding="utf-8")

    data = svc.get_inline_summary("s1")
    assert data is not None
    assert data["metrics"]["total_return"] == 1.0
    assert data["metrics"]["sharpe_ratio"] == 2.5
    assert data["strategy_name"] == "dual_ma"
    assert data["symbols"] == ["BTCUSDT"]


def test_get_inline_summary_upgrades_v1_and_persists(tmp_path) -> None:
    """旧 v1 摘要（只有两键）→ 从结果 JSON 重建完整指标并回写任务文件（一次性慢路径）"""
    svc = _make_service(tmp_path)
    _write_task_full(
        svc,
        "s2",
        "completed",
        metrics_summary={"total_return": 12.4, "max_drawdown": 8.3},
    )
    (svc.results_dir / "result_s2.json").write_text(json.dumps(_make_result(12.4, 8.3)), encoding="utf-8")

    data = svc.get_inline_summary("s2")
    assert data["metrics"]["sharpe_ratio"] == 1.81
    assert data["metrics"]["total_trades"] == 236

    # 回写后任务文件升级为 v2，后续请求零大结果文件 IO
    task_file = svc.results_dir.parent / "backtest_tasks" / "task_s2.json"
    persisted = json.loads(task_file.read_text(encoding="utf-8"))
    assert persisted["metrics_summary"]["metrics"]["sharpe_ratio"] == 1.81


def test_get_inline_summary_failed_and_missing(tmp_path) -> None:
    """failed 任务（无结果文件）→ metrics 退化为 v1 两键；任务文件缺失 → None"""
    svc = _make_service(tmp_path)
    _write_task_full(svc, "s3", "failed", metrics_summary={"total_return": None, "max_drawdown": None})
    data = svc.get_inline_summary("s3")
    assert data is not None
    assert data["metrics"] == {}

    # 无指标摘要的 failed 任务同样空 dict（不渲染假 0）
    _write_task_full(svc, "s4", "failed")
    assert svc.get_inline_summary("s4")["metrics"] == {}

    assert svc.get_inline_summary("no_such_task") is None


def test_write_metrics_summary_persists_to_task_file(tmp_path) -> None:
    """回测完成时写入的摘要落到任务文件（run_backtest 的落盘链路）"""
    svc = _make_service(tmp_path)
    _write_task(svc, "t3", "running")

    svc._write_metrics_summary("t3", {"total_return": 1.5, "max_drawdown": 2.5})

    task_file = svc.results_dir.parent / "backtest_tasks" / "task_t3.json"
    task = json.loads(task_file.read_text(encoding="utf-8"))
    assert task["metrics_summary"] == {"total_return": 1.5, "max_drawdown": 2.5}


def _write_task_full(
    svc: BacktestService,
    task_id: str,
    status: str,
    strategy_name: str = "dual_ma",
    metrics_summary: dict | None = None,
    created_at: str = "2026-01-01T00:00:00",
) -> None:
    """带策略名/摘要/创建时间的任务文件（真分页/筛选/排序用例的数据源）"""
    tasks_dir = svc.results_dir.parent / "backtest_tasks"
    tasks_dir.mkdir(exist_ok=True)
    task = {
        "id": task_id,
        "strategy_name": strategy_name,
        "symbols": ["BTCUSDT"],
        "timeframes": ["1h"],
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
    }
    if metrics_summary is not None:
        task["metrics_summary"] = metrics_summary
    (tasks_dir / f"task_{task_id}.json").write_text(json.dumps(task), encoding="utf-8")


def test_get_result_list_pagination_filter_sort(tmp_path) -> None:
    """真分页回归：total 全量计数、offset 切片、筛选/排序发生在服务端、无值记录垫底"""
    svc = _make_service(tmp_path)
    _write_task_full(
        svc,
        "a",
        "completed",
        strategy_name="dual_ma",
        metrics_summary={"total_return": 5.0, "max_drawdown": 3.0},
        created_at="2026-01-03T00:00:00",
    )
    _write_task_full(
        svc,
        "b",
        "completed",
        strategy_name="macd",
        metrics_summary={"total_return": -2.0, "max_drawdown": 8.0},
        created_at="2026-01-02T00:00:00",
    )
    _write_task_full(svc, "c", "failed", strategy_name="grid", created_at="2026-01-01T00:00:00")
    _write_task_full(svc, "d", "in_progress", strategy_name="grid", created_at="2026-01-04T00:00:00")

    # total 全量计数，offset 切片按默认 created_at desc 顺序
    rows, total = svc.get_result_list(limit=2, offset=0)
    assert total == 4 and len(rows) == 2
    rows2, total2 = svc.get_result_list(limit=2, offset=2)
    assert total2 == 4 and [r["id"] for r in rows2] == ["b", "c"]

    # 排序：total_return 有值参与升降序，无值（failed）始终垫底；
    # 垫底组内次序固定为 created_at 倒序（d 比 c 新），不依赖文件枚举顺序
    rows_desc, _ = svc.get_result_list(sort_by="total_return", sort_order="desc")
    assert [r["id"] for r in rows_desc] == ["a", "b", "d", "c"]
    rows_asc, _ = svc.get_result_list(sort_by="total_return", sort_order="asc")
    assert [r["id"] for r in rows_asc] == ["b", "a", "d", "c"]

    # 状态过滤：'running' 语义上匹配 running/in_progress
    rows_status, total_status = svc.get_result_list(status_filter="running")
    assert total_status == 1 and rows_status[0]["id"] == "d"

    # 关键字对策略名不区分大小写
    rows_kw, total_kw = svc.get_result_list(keyword="DUAL")
    assert total_kw == 1 and rows_kw[0]["id"] == "a"


def _make_equity_curve(n: int = 500, start: float = 1000.0, step: float = 0.5) -> list[dict]:
    """构造结果 JSON 的 portfolio.equity_curve 同构数据（ms 时间戳 + equity）"""
    return [
        {"timestamp": 1777593600000 + i * 900_000, "equity": start + i * step, "balance": start + i * step}
        for i in range(n)
    ]


def test_get_inline_summary_equity_sampled_and_persisted(tmp_path) -> None:
    """completed 旧任务首次摘要：附带降采样权益点并回写任务文件，二次调用直出"""
    svc = _make_service(tmp_path)
    _write_task_full(svc, "e1", "completed")
    result = _make_result(3.2, 1.1)
    result["results"]["portfolio"]["equity_curve"] = _make_equity_curve()
    (svc.results_dir / "result_e1.json").write_text(json.dumps(result), encoding="utf-8")

    data = svc.get_inline_summary("e1")
    equity = data["equity"]
    assert 2 <= len(equity) <= 200
    assert equity[0] == [1777593600000.0, 1000.0]
    assert equity[-1] == [1777593600000.0 + 499 * 900_000, 1000.0 + 499 * 0.5]

    # 回写：任务文件带 equity_sampled，二次调用与首次一致（走任务文件）
    task_file = svc.results_dir.parent / "backtest_tasks" / "task_e1.json"
    persisted = json.loads(task_file.read_text(encoding="utf-8"))
    assert persisted["equity_sampled"] == equity
    assert svc.get_inline_summary("e1")["equity"] == equity


def test_get_inline_summary_equity_absent_for_running(tmp_path) -> None:
    """running 任务即使结果文件有曲线也不给 equity（行内无该形态）"""
    svc = _make_service(tmp_path)
    _write_task_full(svc, "e2", "running")
    result = _make_result(0.0, 0.0)
    result["results"]["portfolio"]["equity_curve"] = _make_equity_curve(10)
    (svc.results_dir / "result_e2.json").write_text(json.dumps(result), encoding="utf-8")

    data = svc.get_inline_summary("e2")
    assert data is not None
    assert "equity" not in data


def test_sample_equity_curve_skips_garbage_points(tmp_path) -> None:
    """曲线里的非 dict / 缺值 / 非数点被剔除，不产生 NaN"""
    curve = [
        "garbage",
        {"timestamp": 1, "equity": 10.0},
        {"equity": 11.0},
        {"timestamp": 3, "equity": "nope"},
        {"timestamp": 4.0, "equity": 12.5},
    ]
    sampled = BacktestService._sample_equity_curve(curve)
    assert sampled == [[1.0, 10.0], [4.0, 12.5]]
    assert BacktestService._sample_equity_curve(None) == []


def test_get_result_list_filters_by_created_date(tmp_path) -> None:
    """创建日期过滤含端点：按 created_at 前 10 位日粒度比较"""
    svc = _make_service(tmp_path)
    for task_id, day in (("d1", "2026-05-01"), ("d2", "2026-05-02"), ("d3", "2026-05-03")):
        _write_task_full(svc, task_id, "completed", created_at=f"{day}T12:00:00")

    rows, total = svc.get_result_list(start_time="2026-05-02", end_time="2026-05-02")
    assert total == 1 and [r["id"] for r in rows] == ["d2"]

    # 端点含入：止日为 05-03 时含 d3
    rows3, total3 = svc.get_result_list(end_time="2026-05-03")
    assert total3 == 3 and [r["id"] for r in rows3] == ["d3", "d2", "d1"]

    # 起日为 05-02 时排除 d1
    rows2, total2 = svc.get_result_list(start_time="2026-05-02")
    assert total2 == 2 and [r["id"] for r in rows2] == ["d3", "d2"]
