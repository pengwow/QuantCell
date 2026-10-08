"""Jev 决策预研 CLI：离线评测入口。

仅做参数解析与编排调用，业务逻辑在 decision.evaluation.evaluator。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from typer import Option

from cli._common import echo_error, echo_json, handle_errors
from decision.cascade import RuleFallback
from decision.client import ReplayDecisionClient, StubDecisionClient
from decision.evaluation.dataset import load_bars_csv
from decision.evaluation.evaluator import EvalConfig, run_evaluation

app = typer.Typer(
    name="decision",
    help="Jev 决策预研工具（离线评测）",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


@app.callback()
def _main() -> None:
    """Jev 决策预研命令组。"""


@app.command("eval")
@handle_errors
def eval_cmd(
    csv: Annotated[Path, Option("--csv", exists=True, readable=True, help="K 线 CSV 路径")],
    mode: Annotated[str, Option("--mode", help="决策后端: stub | replay")] = "stub",
    fixtures: Annotated[
        Path | None, Option("--fixtures", exists=True, readable=True, help="replay 模式的录制 JSONL")
    ] = None,
    window: Annotated[int, Option("--window", help="特征窗口 bar 数")] = 20,
    horizon: Annotated[int, Option("--horizon", help="标签前瞻 bar 数")] = 1,
    cost_threshold: Annotated[float, Option("--cost-threshold", help="双边成本阈值（标签口径）")] = 0.002,
    open_threshold: Annotated[float, Option("--open-threshold", help="开仓置信门控")] = 0.80,
    hold_threshold: Annotated[float, Option("--hold-threshold", help="观望置信门控")] = 0.70,
    fallback_cost_usd: Annotated[float, Option("--fallback-cost-usd", help="单次兜底决策成本")] = 0.002,
    min_samples: Annotated[int, Option("--min-samples", help="阈值推荐的最小样本门槛")] = 50,
    symbol: Annotated[str, Option("--symbol")] = "BTCUSDT",
    bar_type: Annotated[str, Option("--bar-type")] = "1h",
    out: Annotated[Path | None, Option("--out", help="报告 JSON 输出路径")] = None,
    trace: Annotated[Path | None, Option("--trace", help="逐样本 trace JSONL 输出路径")] = None,
) -> None:
    """对 K 线 CSV 跑级联决策离线评测，输出汇总报告 JSON。"""
    if mode == "stub":
        client = StubDecisionClient()
    elif mode == "replay":
        if fixtures is None:
            echo_error("replay 模式必须通过 --fixtures 提供录制 JSONL")
        client = ReplayDecisionClient.from_jsonl(fixtures)
    else:
        echo_error(f"未知 --mode: {mode}（支持 stub | replay）")

    config = EvalConfig(
        bars=load_bars_csv(csv),
        client=client,
        fallback=RuleFallback(),
        window=window,
        horizon=horizon,
        cost_threshold=cost_threshold,
        open_threshold=open_threshold,
        hold_threshold=hold_threshold,
        fallback_cost_usd=fallback_cost_usd,
        min_samples=min_samples,
        symbol=symbol,
        bar_type=bar_type,
        csv_path=csv,
        fixtures_path=fixtures,
    )
    report, records = run_evaluation(config)

    if out is not None:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if trace is not None:
        trace.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
    echo_json(report)
