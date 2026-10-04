"""factor CLI 测试（CliRunner，store 全部隔离到 tmp，档案钩子打桩）。"""

import json

import pytest
from typer.testing import CliRunner

from cli import factor as factor_cli


@pytest.fixture
def runner():
    # click 8.2+ 默认 stdout/stderr 分离：模块日志走 stderr，不污染 stdout 的 JSON 断言
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path, monkeypatch):
    """表达式/代码/合成三个 JSON store 全部指向 tmp。"""
    # 与真实 CLI 入口一致：抑制 INFO 日志，避免其进入 stdout 干扰 JSON 断言
    monkeypatch.setenv("CLI_MODE", "1")
    monkeypatch.setenv("QC_FACTOR_EXPR_STORE", str(tmp_path / "expr.json"))
    monkeypatch.setenv("QC_FACTOR_CODE_STORE", str(tmp_path / "code.json"))
    monkeypatch.setenv("QC_FACTOR_COMPOSITE_STORE", str(tmp_path / "comp.json"))
    # 档案 DB 钩子不参与 CLI 单测（路由层已覆盖），打桩避免写开发库
    monkeypatch.setattr(factor_cli, "_catalog_after_add", lambda name: None)
    monkeypatch.setattr(factor_cli, "_catalog_after_delete", lambda name: None)
    # 会话内 logger 单例可能已按 INFO 初始化（env 来不及）：直接重定向到真实 stderr，
    # 结束后还原 stdout/INFO
    import sys as _sys

    from loguru import logger as _l

    from utils.logger import LoggerConfig

    _l.remove()
    handler_id = _l.add(_sys.__stderr__, level="WARNING", format=LoggerConfig.COMPAT_FORMAT)
    yield
    _l.remove(handler_id)
    from utils.logger import set_log_level

    set_log_level("INFO")


VALID_CODE = 'factor = df["close"].pct_change(5)'


def test_list_builtin(runner):
    result = runner.invoke(factor_cli.app, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    names = [f["name"] for f in data["factors"]]
    assert len(names) > 10  # 内置因子 30+


def test_get_missing_factor_exits_1(runner):
    result = runner.invoke(factor_cli.app, ["get", "no_such_factor_xyz"])
    assert result.exit_code == 1
    assert "不存在" in result.stdout


def test_expression_add_get_delete(runner):
    result = runner.invoke(
        factor_cli.app,
        ["expression", "add", "--name", "cli_expr_x", "--expr", "close / open - 1"],
    )
    assert result.exit_code == 0, result.stdout
    result = runner.invoke(factor_cli.app, ["get", "cli_expr_x"])
    assert result.exit_code == 0
    assert "close / open - 1" in result.stdout
    result = runner.invoke(factor_cli.app, ["expression", "delete", "cli_expr_x"])
    assert result.exit_code == 0


def test_expression_validate_bad_syntax(runner):
    result = runner.invoke(factor_cli.app, ["expression", "validate", "--expr", "not valid ((("])
    assert result.exit_code == 1


def test_expression_add_builtin_name_rejected(runner):
    # add_factor 不在入库时做语法校验（延迟到计算期），但内置名禁止覆盖
    result = runner.invoke(
        factor_cli.app,
        ["expression", "add", "--name", "momentum_20d", "--expr", "close/open"],
    )
    assert result.exit_code == 1
    assert "内置" in result.stdout


def test_code_validate_accept_and_reject(runner):
    result = runner.invoke(factor_cli.app, ["code", "validate", "--code", VALID_CODE])
    assert result.exit_code == 0, result.stdout
    result = runner.invoke(factor_cli.app, ["code", "validate", "--code", "import os\nfactor = 1"])
    assert result.exit_code == 1
    assert "校验失败" in result.stdout


def test_code_validate_requires_exactly_one_source(runner):
    result = runner.invoke(factor_cli.app, ["code", "validate"])
    assert result.exit_code == 1


def test_code_add_file_then_delete(runner, tmp_path):
    f = tmp_path / "alpha.py"
    f.write_text(VALID_CODE + "\n", encoding="utf-8")
    result = runner.invoke(
        factor_cli.app,
        ["code", "add", "--name", "cli_code_x", "--file", str(f), "-d", "测试代码因子"],
    )
    assert result.exit_code == 0, result.stdout
    result = runner.invoke(factor_cli.app, ["list", "--kind", "code"])
    assert "cli_code_x" in result.stdout
    result = runner.invoke(factor_cli.app, ["code", "delete", "cli_code_x"])
    assert result.exit_code == 0


def test_composite_add_spec_then_delete(runner, tmp_path):
    spec = {
        "constituents": [
            {"code": VALID_CODE, "weight": 0.6, "ts_stats": {"SYN01": {"mean": 0.0, "std": 1.0}}},
            {
                "code": 'factor = df["volume"].pct_change(3)',
                "weight": -0.4,
                "ts_stats": {"SYN01": {"mean": 0.0, "std": 1.0}},
            },
        ],
        "train_window": {
            "start": "2026-01-01T00:00:00",
            "end": "2026-02-01T00:00:00",
            "interval": "1h",
            "candle_type": "spot",
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    result = runner.invoke(
        factor_cli.app,
        ["composite", "add", "--name", "cli_comp_x", "--spec", str(spec_path)],
    )
    assert result.exit_code == 0, result.stdout
    result = runner.invoke(factor_cli.app, ["list", "--kind", "composite"])
    assert "cli_comp_x" in result.stdout
    result = runner.invoke(factor_cli.app, ["composite", "delete", "cli_comp_x"])
    assert result.exit_code == 0


def test_composite_add_missing_spec_field(runner, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"constituents": []}), encoding="utf-8")
    result = runner.invoke(factor_cli.app, ["composite", "add", "--name", "x", "--spec", str(bad)])
    assert result.exit_code == 1


class _StubService:
    """打桩 compare_factors，锁定 CLI 读取的结果键名（服务返回 factors 而非 rows）。"""

    def compare_factors(self, **kwargs):
        return {
            "factors": [
                {
                    "factor_name": "f1",
                    "label": "因子一",
                    "ic_mean": 0.05,
                    "ic_ir": 0.8,
                    "annualized_ir": 1.5,
                    "t_stat": 2.3,
                    "coverage": 0.9,
                    "turnover": 0.1,
                }
            ],
            "ic_series": {},
        }


def test_compare_renders_factors_rows(runner, monkeypatch):
    monkeypatch.setattr(factor_cli, "_service", lambda: _StubService())
    result = runner.invoke(factor_cli.app, ["compare", "f1", "f2", "-s", "BTCUSDT"])
    assert result.exit_code == 0, result.stdout
    assert "因子一" in result.stdout
    assert "0.0500" in result.stdout


def test_compare_requires_2_to_5(runner):
    result = runner.invoke(factor_cli.app, ["compare", "only_one", "-s", "BTCUSDT"])
    assert result.exit_code == 1
    assert "2-5" in result.stdout


def test_instruments_json(runner):
    result = runner.invoke(factor_cli.app, ["instruments", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "symbols" in data


def test_analyze_unknown_factor(runner):
    result = runner.invoke(factor_cli.app, ["analyze", "ghost_factor", "-s", "BTCUSDT"])
    assert result.exit_code == 1
    assert "不存在" in result.stdout


def test_horizons_validation(runner):
    result = runner.invoke(
        factor_cli.app,
        ["analyze", "momentum_20d", "-s", "BTCUSDT", "--horizons", "a,b"],
    )
    assert result.exit_code == 1


def test_analyze_real_data_smoke(runner):
    """本地存在 BTCUSDT 1h parquet 时跑一次真实分析（无数据则 skip）。"""
    from quality.parquet_provider import ParquetDataProvider

    symbols = {s["symbol"] for s in ParquetDataProvider().list_available_symbols("spot")}
    if "BTCUSDT" not in symbols:
        pytest.skip("本地无 BTCUSDT parquet 数据")
    result = runner.invoke(
        factor_cli.app,
        ["analyze", "momentum_20d", "-s", "BTCUSDT", "-i", "1h", "--window", "20"],
    )
    assert result.exit_code == 0, result.stdout
    assert "IC 均值" in result.stdout
