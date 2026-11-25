"""P4-2 风控建议层单测：指标计算 / 阈值分级 / 红线（无写路径）/ 复盘 section 并入。

纯函数用合成收益序列直接喂，不依赖库与真实数据目录。
"""

import ast
import inspect

import services.risk_advisory as ra

# ---------- 纯指标 ----------


def test_ewma_volatility_and_var_reasonable():
    calm = [0.001, -0.001] * 10
    wild = [0.05, -0.06, 0.07, -0.08] * 2

    assert ra.ewma_volatility(calm) < ra.ewma_volatility(wild)
    assert ra.parametric_var95(calm) < ra.parametric_var95(wild)
    assert ra.ewma_volatility([]) == 0.0
    assert ra.parametric_var95([0.01]) == 0.0


def test_max_drawdown_tracks_peak_to_trough():
    assert ra.max_drawdown([0.05, -0.10, 0.02]) > 0.0
    assert ra.max_drawdown([0.01] * 5) == 0.0
    # 连续下跌 20 天 × -2% → 约 33% 回撤
    assert 0.30 < ra.max_drawdown([-0.02] * 20) < 0.36


def test_nominal_concentration_uses_book_value():
    pct, symbol, book = ra.nominal_concentration(
        [
            {"symbol": "BTCUSDT", "quantity": 2.0, "current_price": 100.0},
            {"symbol": "ETHUSDT", "quantity": 1.0, "current_price": 100.0},
        ]
    )
    assert symbol == "BTCUSDT"
    assert book == 300.0
    assert round(pct, 2) == 66.67


def test_severity_tiers():
    assert ra._severity(0.01, 0.03, 0.06) is None
    assert ra._severity(0.025, 0.03, 0.06) == "info"  # ≥ 80% warn
    assert ra._severity(0.03, 0.03, 0.06) == "warn"
    assert ra._severity(0.06, 0.03, 0.06) == "crit"


# ---------- 触发场景 ----------


def test_high_volatility_triggers_advisory_with_suggested_cap():
    result = ra.assess_worker(
        worker_id=1,
        worker_name="w-vol",
        returns=[0.05, -0.06, 0.07, -0.08] * 2,
        equity=100_000.0,
    )

    by_metric = {a["metric"]: a for a in result["advisories"]}
    assert by_metric["volatility"]["severity"] in ("warn", "crit")
    assert by_metric["volatility"]["suggested_notional_cap"] < 100_000.0
    assert by_metric["volatility"]["suggested_ratio"] < 1.0
    assert "建议名义敞口上限" in by_metric["volatility"]["reason"]


def test_deep_drawdown_triggers_advisory():
    result = ra.assess_worker(
        worker_id=2,
        worker_name="w-dd",
        returns=[-0.02] * 20,
        equity=50_000.0,
    )

    by_metric = {a["metric"]: a for a in result["advisories"]}
    assert "drawdown" in by_metric
    assert by_metric["drawdown"]["severity"] == "crit"
    assert result["metrics"]["max_drawdown"] > 0.30


def test_concentration_over_limit_triggers_advisory():
    result = ra.assess_worker(
        worker_id=3,
        worker_name="w-conc",
        returns=[0.0] * 5,
        positions=[{"symbol": "BTCUSDT", "quantity": 10.0, "current_price": 100.0}],
        equity=100_000.0,
    )

    by_metric = {a["metric"]: a for a in result["advisories"]}
    assert by_metric["concentration"]["severity"] == "crit"
    assert by_metric["concentration"]["suggested_notional_cap"] == 600.0  # 1000 × 60%
    assert "BTCUSDT" in by_metric["concentration"]["reason"]


def test_healthy_state_yields_no_advisory():
    result = ra.assess_worker(
        worker_id=4,
        worker_name="w-healthy",
        returns=[0.001, -0.001] * 10,
        positions=[
            {"symbol": "BTCUSDT", "quantity": 1.0, "current_price": 100.0},
            {"symbol": "ETHUSDT", "quantity": 1.0, "current_price": 100.0},
            {"symbol": "SOLUSDT", "quantity": 1.0, "current_price": 100.0},
        ],
        equity=100_000.0,
    )

    assert result["advisories"] == []
    assert result["metrics"]["concentration_pct"] == 33.33


def test_collect_advisories_aggregates_and_offline_safe():
    """无权益基数（worker 未配置 initial_capital）时跳过波动类，不抛异常。"""
    section = ra.collect_risk_advisories([])

    assert section == {
        "window_days": ra.WINDOW_DAYS,
        "workers": [],
        "advisories": [],
        "count": 0,
        "max_severity": None,
    }


def test_severity_order_covers_all_levels():
    assert ra.SEVERITY_ORDER == {"info": 0, "warn": 1, "crit": 2}


# ---------- 红线：绝不引用硬规则写路径 ----------

FORBIDDEN_WRITE_NAMES = {
    "push_risk_control",
    "apply_risk_config",
    "resolve_risk_settings",
    "set_risk_config",
    "update_risk_config",
    "set_risk_enabled",
    "update_risk_pnl",
    "reset_risk_daily",
    "risk_status_snapshot",
    "RiskPnlFeeder",
}


def test_module_imports_no_risk_config_write_path():
    """静态断言：模块不 import worker.risk_config，也不引用其任何写函数。

    docstring 里说明红线时会**提到**这些名字（字符串常量，不是 ast.Name），
    所以用 AST 而不是文本搜索，避免误报。
    """
    tree = ast.parse(inspect.getsource(ra))

    imported_modules: list[str] = []
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)

    assert all("risk_config" not in module for module in imported_modules)
    assert "__import__" not in referenced
    assert not (FORBIDDEN_WRITE_NAMES & referenced)


def test_no_write_or_mutation_helpers_exported():
    """对外只暴露评估/查询函数，没有任何 apply/push/update 入口。"""
    public = {name for name in dir(ra) if not name.startswith("_")}
    assert not {n for n in public if any(v in n.lower() for v in ("apply", "push", "update", "write", "set_"))}
