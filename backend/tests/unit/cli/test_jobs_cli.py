"""jobs CLI 测试：config 只读渲染 + selftest 入口编排。

真 spawn 子进程池的自检（约 10~20s）由 tests/integration/backtest/test_backtest_job_pool.py
覆盖，这里只锁输出/调用契约，不跑真池。
"""

import pytest
from typer.testing import CliRunner

from cli import jobs as jobs_cli


@pytest.fixture
def runner():
    return CliRunner()


def test_jobs_config_renders_gray_switch_and_both_pools(runner, monkeypatch):
    """config 输出灰度开关 / 绑核区间 / 两池并发，且只为两个池各取一次资源。"""
    monkeypatch.setattr(jobs_cli, "pool_enabled", lambda: True)
    monkeypatch.setattr(jobs_cli, "resolve_cores", lambda: [2, 3, 4, 5])
    asked: list[str] = []

    def fake_pool_resources(kind: str):
        asked.append(kind)
        return {"backtest": (2, [2, 3]), "hpo": (2, [4, 5])}[kind]

    monkeypatch.setattr(jobs_cli, "pool_resources", fake_pool_resources)

    result = runner.invoke(jobs_cli.app, ["config"])

    assert result.exit_code == 0, result.output
    assert asked == ["backtest", "hpo"]
    assert "pool_enabled : True" in result.stdout
    assert "[2, 3, 4, 5]" in result.stdout
    assert "回测池 并发/绑核" in result.stdout
    assert "2 / [2, 3]" in result.stdout
    assert "HPO 池 并发/绑核" in result.stdout
    assert "2 / [4, 5]" in result.stdout


def test_jobs_config_unbound_cores_falls_back_to_os(runner, monkeypatch):
    """未配置绑核时显示「交 OS 调度」，池绑核用 `-` 占位。"""
    monkeypatch.setattr(jobs_cli, "pool_enabled", lambda: False)
    monkeypatch.setattr(jobs_cli, "resolve_cores", lambda: [])
    monkeypatch.setattr(jobs_cli, "pool_resources", lambda kind: (3, []))

    result = runner.invoke(jobs_cli.app, ["config"])

    assert result.exit_code == 0, result.output
    assert "pool_enabled : False" in result.stdout
    assert "（未绑定，交 OS 调度）" in result.stdout
    assert "3 / -" in result.stdout


def test_jobs_selftest_wires_checks_and_exits_zero(runner, monkeypatch):
    """selftest 依次跑三段检查，全通过时打印汇总并 exit 0（检查函数打桩，不起进程池）。"""
    called: list[str] = []

    def fake_check(name: str):
        def run(record):
            called.append(name)
            record(name, True)

        return run

    for fn_name in ("_check_parallel", "_check_reject_and_cancel", "_check_shutdown"):
        monkeypatch.setattr(jobs_cli, fn_name, fake_check(fn_name))

    result = runner.invoke(jobs_cli.app, ["selftest"])

    assert result.exit_code == 0, result.output
    assert called == ["_check_parallel", "_check_reject_and_cancel", "_check_shutdown"]
    assert result.stdout.count("[PASS]") == 3
    assert "自检通过" in result.stdout
