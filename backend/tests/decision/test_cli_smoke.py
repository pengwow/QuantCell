"""decision eval CLI 端到端冒烟：fixture CSV → 报告 JSON。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cli.decision import app

FIXTURES = Path(__file__).parent / "fixtures" / "sample_bars.csv"


def test_eval_command_smoke():
    # min-samples 高于 train 段 36 条，固定 recommendation=None，不依赖 stub 推荐结果
    result = CliRunner().invoke(
        app,
        ["eval", "--csv", str(FIXTURES), "--min-samples", "100"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["success"] is True
    assert data["samples"] == 60
    assert data["advisory_only"] is True
    assert data["recommendation"] is None
    assert data["data_fingerprint"]["csv_sha256"] is not None
    assert set(data["metrics"]["confusion"]) == {"buy", "sell", "hold"}
