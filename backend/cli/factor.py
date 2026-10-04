#!/usr/bin/env python3
"""
因子研究命令行工具

覆盖 Web 端因子分析的完整能力：因子列表/明细、本地品种、单因子分析、
多因子对比、表达式/代码/合成因子管理、LLM 挖掘、分析快照与因子档案。

使用方式:
    uv run python -m cli.factor list
    uv run python -m cli.factor analyze momentum_20d -s BTCUSDT -s ETHUSDT
    uv run python -m cli.factor mine -s BTCUSDT -s ETHUSDT --candidates 4 --rounds 2 -o mine.json
    uv run python -m cli.factor code add my_alpha --file alpha.py
    uv run python -m cli.factor composite add my_comp --spec composite_spec.json

设计约定：
- 直接在进程内调用 FactorService（不经 HTTP），与 Web 端同一份研究口径；
- 默认 rich 文本输出，--json 输出完整结构化结果，-o/--output 落文件；
- 管理类写操作后同步因子档案 DB（与 HTTP 路由相同钩子，失败仅告警）。
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# 必须在 import 业务模块（utils.logger 首次配置）前设置：CLI 模式下降级到 WARNING，
# 避免 import 期 INFO 日志污染 stdout，保证 --json 输出可被直接解析
os.environ.setdefault("CLI_MODE", "1")

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="因子研究（分析/对比/代码因子/合成因子/LLM 挖掘/快照）")
expression_app = typer.Typer(help="自定义表达式因子管理")
code_app = typer.Typer(help="代码因子管理（沙箱执行）")
composite_app = typer.Typer(help="合成因子管理")
snapshot_app = typer.Typer(help="因子分析快照")
app.add_typer(expression_app, name="expression")
app.add_typer(code_app, name="code")
app.add_typer(composite_app, name="composite")
app.add_typer(snapshot_app, name="snapshot")

console = Console()


# ----------------------------- 基础辅助 -----------------------------


def _service():
    """惰性构造 FactorService；store 路径支持环境变量覆盖（测试/自定义数据目录）。"""
    from factor.code_store import CodeFactorStore
    from factor.composite_store import CompositeFactorStore
    from factor.factor_store import FactorStore
    from factor.service import FactorService

    expr_path = os.environ.get("QC_FACTOR_EXPR_STORE")
    code_path = os.environ.get("QC_FACTOR_CODE_STORE")
    comp_path = os.environ.get("QC_FACTOR_COMPOSITE_STORE")
    return FactorService(
        factor_store=FactorStore(Path(expr_path)) if expr_path else None,
        code_store=CodeFactorStore(Path(code_path)) if code_path else None,
        composite_store=CompositeFactorStore(Path(comp_path)) if comp_path else None,
    )


def _fail(message: str) -> None:
    console.print(f"[red]✗ {message}[/red]")
    raise typer.Exit(code=1)


def _parse_horizons(text: str | None) -> list[int] | None:
    if not text:
        return None
    parts = [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
    if len(parts) > 20:
        _fail("衰减滞后最多 20 个")
    hs: list[int] = []
    for p in parts:
        if not p.isdigit():
            _fail(f"衰减滞后必须是正整数：{p}")
        n = int(p)
        if not 1 <= n <= 120:
            _fail(f"衰减滞后必须在 1-120：{p}")
        hs.append(n)
    return hs


def _jsonable(obj: Any) -> Any:
    """把 numpy/pandas/日期对象转成 JSON 原生类型；NaN/Inf 归一为 None。"""
    import numpy as np
    import pandas as pd

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _emit(data: Any, as_json: bool, output: str | None) -> None:
    """结构化结果输出：--json 打到 stdout；-o 落文件（文本摘要由调用方另行打印）。"""
    payload = json.dumps(_jsonable(data), ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        console.print(f"[green]✓[/green] 结果已写入 {output}")
    # -o 但未显式 --json：仅落文件，由调用方打印文本摘要
    if as_json or not output:
        typer.echo(payload)


def _read_code(code: str | None, file: Path | None) -> str:
    if bool(code) == bool(file):
        _fail("代码必须且只能通过 --code 或 --file 之一提供")
    if file:
        if not file.exists():
            _fail(f"代码文件不存在：{file}")
        return file.read_text(encoding="utf-8")
    return code or ""


def _catalog_after_add(name: str) -> None:
    """因子入库后同步档案（与 HTTP 路由同模式，失败只告警）。"""
    try:
        from factor.catalog_service import FactorCatalogService
        from utils.db_session import get_db_session

        svc = _service()
        with get_db_session() as db:
            catalog = FactorCatalogService()
            catalog.sync_builtins(db)
            details = [d for d in svc.get_factor_details() if d["name"] == name]
            if details:
                catalog.upsert_custom(db, details[0])
    except Exception as exc:
        console.print(f"[yellow]⚠ 因子档案建档失败（不影响因子保存）：{exc}[/yellow]")


def _catalog_after_delete(name: str) -> None:
    try:
        from factor.catalog_service import FactorCatalogService
        from utils.db_session import get_db_session

        with get_db_session() as db:
            FactorCatalogService().on_factor_deleted(db, name)
    except Exception as exc:
        console.print(f"[yellow]⚠ 因子档案清理失败（因子已删除）：{exc}[/yellow]")


# ----------------------------- 列表与明细 -----------------------------


@app.command("list")
def list_factors(
    kind: str = typer.Option("all", "--kind", help="all|builtin|expression|code|composite"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
):
    """列出全部因子（内置 + 表达式 + 代码 + 合成）。"""
    svc = _service()
    details = svc.get_factor_details()
    if kind != "all":
        details = [d for d in details if d.get("kind") == kind or d.get("category", "").endswith(kind)]
    if as_json:
        typer.echo(json.dumps({"factors": _jsonable(details)}, ensure_ascii=False, indent=2))
        return
    if not details:
        console.print("(无因子)")
        return
    table = Table(title=f"因子列表（{len(details)}）")
    table.add_column("名称", style="cyan")
    table.add_column("说明")
    table.add_column("类型")
    table.add_column("可计算", justify="center")
    for d in details:
        kind_label = {
            "builtin": "内置",
            "expression": "表达式",
            "code": "代码",
            "composite": "合成",
        }.get(d.get("kind", "builtin"), d.get("kind", ""))
        table.add_row(
            d.get("name", ""),
            d.get("label", ""),
            kind_label,
            "✓" if d.get("supported") else "✗",
        )
    console.print(table)


@app.command("get")
def get_factor(
    name: str = typer.Argument(..., help="因子名称"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
):
    """查看单个因子明细（表达式/代码/合成规格不直接回显敏感内容，仅元信息）。"""
    svc = _service()
    detail = next((d for d in svc.get_factor_details() if d["name"] == name), None)
    if detail is None:
        _fail(f"因子不存在：{name}")
    if as_json:
        typer.echo(json.dumps(_jsonable(detail), ensure_ascii=False, indent=2))
    else:
        for k in ("name", "label", "kind", "category", "description", "supported"):
            if k in detail:
                console.print(f"[dim]{k}[/dim]: {detail[k]}")
        expr = svc.get_factor_expression(name)
        if expr:
            console.print(f"[dim]expression[/dim]: {expr}")


@app.command("instruments")
def list_instruments(
    candle_type: str = typer.Option("spot", "--candle-type", help="spot | future"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
):
    """扫描本地 parquet，列出可分析品种与可用周期。"""
    from quality.parquet_provider import ParquetDataProvider

    symbols = ParquetDataProvider().list_available_symbols(candle_type=candle_type)
    if as_json:
        typer.echo(json.dumps({"symbols": _jsonable(symbols)}, ensure_ascii=False, indent=2))
        return
    if not symbols:
        console.print("(本地无可用品种数据)")
        return
    table = Table(title=f"{candle_type} 品种（{len(symbols)}）")
    table.add_column("品种", style="cyan")
    table.add_column("可用周期")
    for s in symbols:
        table.add_row(s.get("symbol", ""), "、".join(s.get("intervals", [])))
    console.print(table)


# ----------------------------- 分析与对比 -----------------------------


def _print_analyze_summary(result: dict[str, Any]) -> None:
    ic = result.get("ic", {})
    insp = result.get("inspection") or {}
    ic_stats = insp.get("ic_stats") or {}
    console.print(f"[bold]{result.get('factor_name')}[/bold] | 样本 {result.get('bar_count')} 根")
    table = Table(show_header=False, box=None)
    table.add_column("指标", style="dim")
    table.add_column("值")
    rows = [
        ("IC 均值", ic.get("mean")),
        ("ICIR", ic.get("ir")),
        ("IC 胜率", ic.get("positive_rate")),
        ("多空收益", result.get("long_short_return")),
        ("单调性 Spearman", (result.get("monotonicity") or {}).get("spearman")),
        ("稳定性(自相关)", (result.get("stability") or {}).get("mean_autocorr")),
        ("覆盖率", insp.get("coverage")),
        ("换手率", insp.get("turnover")),
        ("年化 IR", ic_stats.get("annualized_ir")),
        ("t-stat", ic_stats.get("t_stat")),
        ("NW t-stat", ic_stats.get("nw_t_stat")),
    ]
    for k, v in rows:
        if v is None:
            sv = "—"
        elif k in ("IC 胜率", "覆盖率"):
            sv = f"{v * 100:.1f}%"
        else:
            sv = f"{v:.4f}"
        table.add_row(k, sv)
    console.print(table)

    groups = result.get("groups") or []
    if groups:
        gtable = Table(title="分组平均前瞻收益")
        gtable.add_column("分组")
        gtable.add_column("平均收益", justify="right")
        for g in groups:
            gtable.add_row(f"G{g.get('group')}", f"{g.get('mean_forward_return', 0):.6f}")
        console.print(gtable)

    decay = insp.get("decay") or []
    if decay:
        dtable = Table(title="IC 衰减")
        dtable.add_column("lag", justify="right")
        dtable.add_column("Spearman", justify="right")
        dtable.add_column("Pearson", justify="right")
        for d in decay:
            sp = f"{d['spearman']:.4f}" if d.get("spearman") is not None else "—"
            pe = f"{d['pearson']:.4f}" if d.get("pearson") is not None else "—"
            dtable.add_row(str(d.get("lag")), sp, pe)
        console.print(dtable)


@app.command("analyze")
def analyze(
    factor_name: str = typer.Argument(..., help="因子名称（内置/表达式/代码/合成）"),
    symbols: list[str] = typer.Option(..., "--symbol", "-s", help="品种，可多次指定"),
    interval: str = typer.Option("1h", "--interval", "-i", help="K 线周期"),
    candle_type: str = typer.Option("spot", "--candle-type", help="spot | future"),
    start: str | None = typer.Option(None, "--start", help="开始时间 YYYY-MM-DD"),
    end: str | None = typer.Option(None, "--end", help="结束时间 YYYY-MM-DD"),
    method: str = typer.Option("spearman", "--method", help="spearman | pearson"),
    groups: int = typer.Option(5, "--groups", min=2, max=10),
    window: int = typer.Option(20, "--window", min=5, max=252),
    forward: int = typer.Option(1, "--forward", min=1, max=120),
    horizons: str | None = typer.Option(None, "--horizons", help="衰减滞后，逗号分隔，如 1,2,3,5,10"),
    cost_bps: float = typer.Option(0.0, "--cost-bps", help="单边成本 bp，10=0.1%"),
    as_json: bool = typer.Option(False, "--json", help="输出完整 JSON"),
    output: str | None = typer.Option(None, "--output", "-o", help="JSON 结果写入文件"),
):
    """一站式单因子分析：IC/ICIR/分组多空/单调性/稳定性/深度审查。"""
    from factor.service import FactorError as SvcFactorError
    from factor.service import FactorNotFoundError as SvcNotFoundError

    try:
        result = _service().analyze(
            factor_name=factor_name,
            symbols=symbols,
            interval=interval,
            candle_type=candle_type,
            start=start,
            end=end,
            method=method,
            n_groups=groups,
            window=window,
            forward=forward,
            horizons=_parse_horizons(horizons),
            cost_bps=cost_bps,
        )
    except (SvcFactorError, SvcNotFoundError) as exc:
        _fail(str(exc))
    if as_json or output:
        _emit(result, as_json, output)
    if not as_json:
        _print_analyze_summary(result)


@app.command("compare")
def compare(
    factor_names: list[str] = typer.Argument(..., help="2-5 个因子名称"),
    symbols: list[str] = typer.Option(..., "--symbol", "-s", help="品种，可多次指定"),
    interval: str = typer.Option("1h", "--interval", "-i"),
    candle_type: str = typer.Option("spot", "--candle-type"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    method: str = typer.Option("spearman", "--method"),
    groups: int = typer.Option(5, "--groups", min=2, max=10),
    window: int = typer.Option(20, "--window", min=5, max=252),
    forward: int = typer.Option(1, "--forward", min=1, max=120),
    horizons: str | None = typer.Option(None, "--horizons"),
    cost_bps: float = typer.Option(0.0, "--cost-bps"),
    as_json: bool = typer.Option(False, "--json"),
    output: str | None = typer.Option(None, "--output", "-o"),
):
    """多因子横向对比（共用参数，IC 时序按时间轴对齐）。"""
    if not 2 <= len(factor_names) <= 5:
        _fail("对比因子数量必须为 2-5 个")
    from factor.service import FactorError as SvcFactorError
    from factor.service import FactorNotFoundError as SvcNotFoundError

    try:
        data = _service().compare_factors(
            factor_names=factor_names,
            symbols=symbols,
            interval=interval,
            candle_type=candle_type,
            start=start,
            end=end,
            method=method,
            n_groups=groups,
            window=window,
            forward=forward,
            horizons=_parse_horizons(horizons),
            cost_bps=cost_bps,
        )
    except (SvcFactorError, SvcNotFoundError) as exc:
        _fail(str(exc))
    if as_json or output:
        _emit(data, as_json, output)
    if not as_json:
        table = Table(title="因子对比")
        table.add_column("因子", style="cyan")
        table.add_column("IC 均值", justify="right")
        table.add_column("ICIR", justify="right")
        table.add_column("年化IR", justify="right")
        table.add_column("t-stat", justify="right")
        table.add_column("覆盖率", justify="right")
        table.add_column("换手率", justify="right")

        def f4(v):
            return "—" if v is None else f"{v:.4f}"

        for r in data.get("factors") or data.get("rows") or []:
            cov = r.get("coverage")
            table.add_row(
                f"{r.get('label') or r.get('factor_name')} ({r.get('factor_name')})",
                f4(r.get("ic_mean")),
                f4(r.get("ic_ir")),
                f4(r.get("annualized_ir")),
                f4(r.get("t_stat")),
                f"{cov * 100:.1f}%" if cov is not None else "—",
                f4(r.get("turnover")),
            )
        console.print(table)


# ----------------------------- 表达式因子 -----------------------------


@expression_app.command("validate")
def validate_expression(
    expression: str = typer.Option(..., "--expr", "-e", help="因子表达式"),
):
    """验证表达式是否可计算。"""
    try:
        ok = _service().validate_factor_expression(expression)
    except Exception as exc:
        _fail(f"表达式无效：{exc}")
    if ok:
        console.print("[green]✓ 表达式验证通过[/green]")
    else:
        _fail("表达式验证失败")


@expression_app.command("add")
def add_expression(
    name: str = typer.Option(..., "--name", "-n"),
    expression: str = typer.Option(..., "--expr", "-e"),
):
    """新增自定义表达式因子（保存后同步因子档案）。"""
    try:
        ok = _service().add_factor(name, expression)
    except Exception as exc:
        _fail(str(exc))
    if not ok:
        _fail("表达式因子保存失败")
    _catalog_after_add(name)
    console.print(f"[green]✓[/green] 表达式因子 {name} 已保存")


@expression_app.command("delete")
def delete_expression(name: str = typer.Argument(...)):
    """删除自定义表达式因子。"""
    if not _service().delete_factor(name):
        _fail(f"因子不存在：{name}")
    _catalog_after_delete(name)
    console.print(f"[green]✓[/green] 表达式因子 {name} 已删除")


# ----------------------------- 代码因子 -----------------------------


@code_app.command("validate")
def validate_code(
    code: str | None = typer.Option(None, "--code", help="内联代码"),
    file: Path | None = typer.Option(None, "--file", "-f", help="代码文件"),
):
    """校验代码因子（AST 静态策略 + 沙箱合成数据执行）。"""
    from factor.sandbox import SandboxError

    src = _read_code(code, file)
    try:
        _service()._sandbox.validate(src)
    except SandboxError as exc:
        _fail(f"代码校验失败（{type(exc).__name__}）：{exc}")
    console.print("[green]✓ 代码校验通过[/green]")


@code_app.command("add")
def add_code(
    name: str = typer.Option(..., "--name", "-n"),
    code: str | None = typer.Option(None, "--code"),
    file: Path | None = typer.Option(None, "--file", "-f"),
    description: str = typer.Option("", "--description", "-d"),
):
    """新增代码因子（沙箱校验 + 规范化代码 hash 去重后入库）。"""
    from factor.sandbox import SandboxError

    src = _read_code(code, file)
    try:
        _service().save_code_factor(name, src, description, provenance={"source": "cli_manual"})
    except SandboxError as exc:
        _fail(f"代码被沙箱拒绝：{exc}")
    except Exception as exc:
        _fail(str(exc))
    _catalog_after_add(name)
    console.print(f"[green]✓[/green] 代码因子 {name} 已保存")


@code_app.command("delete")
def delete_code(name: str = typer.Argument(...)):
    """删除代码因子。"""
    from factor.service import FactorNotFoundError

    try:
        _service().delete_code_factor(name)
    except FactorNotFoundError as exc:
        _fail(str(exc))
    except Exception as exc:
        _fail(str(exc))
    _catalog_after_delete(name)
    console.print(f"[green]✓[/green] 代码因子 {name} 已删除")


# ----------------------------- 合成因子 -----------------------------


@composite_app.command("add")
def add_composite(
    name: str = typer.Option(..., "--name", "-n"),
    spec: Path = typer.Option(..., "--spec", help="合成规格 JSON（挖掘结果 composite 块结构）"),
    description: str = typer.Option("", "--description", "-d"),
):
    """新增合成因子。

    spec JSON 结构：{"constituents":[{"code","weight","ts_stats"}],
    "train_window":{"start","end","interval","candle_type"}}。
    可由 `factor mine -o result.json` 的 composite 块整理得到。
    """
    from factor.sandbox import SandboxError

    if not spec.exists():
        _fail(f"规格文件不存在：{spec}")
    try:
        payload = json.loads(spec.read_text(encoding="utf-8"))
        constituents = payload["constituents"]
        train_window = payload["train_window"]
        _service().save_composite(
            name,
            description or payload.get("description", ""),
            codes=[c["code"] for c in constituents],
            weights=[float(c["weight"]) for c in constituents],
            ts_stats_list=[c["ts_stats"] for c in constituents],
            train_window=train_window,
            provenance={"source": "cli_composite"},
        )
    except SandboxError as exc:
        _fail(f"成分代码被沙箱拒绝：{exc}")
    except KeyError as exc:
        _fail(f"规格缺少字段：{exc}")
    except Exception as exc:
        _fail(str(exc))
    _catalog_after_add(name)
    console.print(f"[green]✓[/green] 合成因子 {name} 已保存（{len(constituents)} 个成分）")


@composite_app.command("delete")
def delete_composite(name: str = typer.Argument(...)):
    """删除合成因子。"""
    from factor.service import FactorNotFoundError

    try:
        _service().delete_composite(name)
    except FactorNotFoundError as exc:
        _fail(str(exc))
    except Exception as exc:
        _fail(str(exc))
    _catalog_after_delete(name)
    console.print(f"[green]✓[/green] 合成因子 {name} 已删除")


# ----------------------------- LLM 挖掘 -----------------------------


def _resolve_llm_config(model_id: str | None) -> dict[str, Any]:
    from ai_model.config_utils import get_default_provider_and_models

    result = get_default_provider_and_models()
    if not result:
        _fail("未配置默认 AI 模型，请先在模型管理中配置提供商与 API Key")
    provider = result["provider"]
    api_key = provider.get("api_key")
    if not api_key:
        _fail("默认 AI 模型缺少 API Key")
    enabled = result.get("enabled_models") or []
    if model_id:
        model_name = next((m.get("name") for m in enabled if m.get("id") == model_id), model_id)
    elif enabled:
        model_name = enabled[0].get("name", "")
    else:
        _fail("没有启用的 AI 模型")
    return {"api_key": api_key, "base_url": provider.get("api_host"), "model": model_name}


@app.command("mine")
def mine(
    symbols: list[str] = typer.Option(..., "--symbol", "-s", help="品种，可多次指定"),
    interval: str = typer.Option("1h", "--interval", "-i"),
    candle_type: str = typer.Option("spot", "--candle-type"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    candidates: int = typer.Option(3, "--candidates", min=1, max=20, help="每轮候选数"),
    rounds: int = typer.Option(2, "--rounds", min=1, max=10, help="反思轮数"),
    top_k: int = typer.Option(5, "--top-k", min=1, max=20),
    temperature: float = typer.Option(0.8, "--temperature", min=0.0, max=2.0),
    model_id: str | None = typer.Option(None, "--model-id", help="指定模型（默认第一个启用模型）"),
    test_ratio: float = typer.Option(0.3, "--test-ratio", min=0.0, max=0.5, help="样本外比例，0 关闭"),
    wf_folds: int = typer.Option(0, "--wf-folds", min=0, max=6, help="walk-forward 折数，0=单次切分"),
    dedup_corr: float = typer.Option(0.9, "--dedup-corr", min=0.0, max=1.0, help="相关性去重阈值，0 关闭"),
    compose: bool = typer.Option(True, "--compose/--no-compose", help="是否自动合成 best 因子"),
    output: str | None = typer.Option(None, "--output", "-o", help="完整结果 JSON 写入文件"),
    as_json: bool = typer.Option(False, "--json", help="stdout 输出完整 JSON（默认输出摘要）"),
):
    """LLM 因子挖掘（并发生成 → 沙箱执行 → 去重 → OOS/WF 复核 → 合成）。"""
    from axon_bridge.llm import create_llm_backend
    from factor.llm_miner import LLMMineParams, run_llm_mining

    cfg = _resolve_llm_config(model_id)
    backend = create_llm_backend(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        temperature=temperature,
        max_tokens=16384,
        timeout_secs=180,
    )
    params = LLMMineParams(
        symbols=symbols,
        interval=interval,
        candle_type=candle_type,
        start=start,
        end=end,
        n_candidates=candidates,
        n_rounds=rounds,
        top_k=top_k,
        temperature=temperature,
        model_id=model_id,
        model_name=cfg["model"],
        test_ratio=test_ratio,
        wf_folds=wf_folds,
        dedup_corr=dedup_corr,
        compose=compose,
    )

    def _progress(pct: float, _stage: str, message: str) -> None:
        # 进度走 stderr，不污染 --json 的 stdout
        typer.secho(f"[{pct:5.1f}%] {message}", err=True)

    try:
        result = run_llm_mining(params, backend=backend, progress=_progress)
    except Exception as exc:
        _fail(f"挖掘失败：{exc}")

    if output:
        Path(output).write_text(json.dumps(_jsonable(result), ensure_ascii=False, indent=2), encoding="utf-8")
    if as_json:
        typer.echo(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
    else:
        stats = result.get("stats", {})
        console.print(
            f"[bold]挖掘完成[/bold]：生成 {stats.get('generated')}，成功 {stats.get('succeeded')}，"
            f"重复 {stats.get('redundant', 0)}，失败 {stats.get('failed')}"
        )
        table = Table(title="最佳因子")
        table.add_column("#", justify="right")
        table.add_column("hash", style="cyan")
        table.add_column("fitness", justify="right")
        table.add_column("train IC", justify="right")
        table.add_column("OOS IC", justify="right")
        table.add_column("OOS", justify="center")
        for i, row in enumerate(result.get("best", []), 1):
            m = row.get("metrics") or {}
            o = row.get("metrics_oos") or {}
            table.add_row(
                str(i),
                (row.get("code_hash") or "")[:10],
                f"{m.get('fitness', 0):.3f}" if m.get("fitness") is not None else "—",
                f"{m['ic_mean']:.4f}" if m.get("ic_mean") is not None else "—",
                f"{o['ic_mean']:.4f}" if o.get("ic_mean") is not None else "—",
                row.get("oos_flag") or "—",
            )
        console.print(table)
        comp = result.get("composite")
        if comp and not comp.get("error"):
            weights = [f"{c['weight']:+.3f}" for c in comp.get("constituents", [])]
            console.print(
                f"[green]合成因子[/green]：{comp.get('n')} 成分，权重 [{', '.join(weights)}]，"
                f"train IC {(comp.get('metrics') or {}).get('ic_mean', 0):.4f}，"
                f"OOS 判定 {comp.get('oos_flag')}"
            )
        elif comp and comp.get("error"):
            console.print(f"[yellow]合成未完成：{comp['error']}[/yellow]")
        if output:
            console.print(f"[green]✓[/green] 完整结果已写入 {output}")


# ----------------------------- 快照与档案 -----------------------------


@snapshot_app.command("save")
def snapshot_save(
    factor_name: str = typer.Option(..., "--factor", "-f"),
    symbols: list[str] = typer.Option(..., "--symbol", "-s"),
    interval: str = typer.Option("1h", "--interval", "-i"),
    candle_type: str = typer.Option("spot", "--candle-type"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    method: str = typer.Option("spearman", "--method"),
    groups: int = typer.Option(5, "--groups"),
    window: int = typer.Option(20, "--window"),
    forward: int = typer.Option(1, "--forward"),
    horizons: str | None = typer.Option(None, "--horizons"),
    cost_bps: float = typer.Option(0.0, "--cost-bps"),
):
    """收藏一次分析快照（服务端按参数重算并归档 parquet）。"""
    from factor.catalog_service import CatalogError, FactorCatalogService
    from utils.db_session import get_db_session

    params = {
        "factor_name": factor_name,
        "instruments": symbols,
        "interval": interval,
        "candle_type": candle_type,
        "start_time": start,
        "end_time": end,
        "method": method,
        "n_groups": groups,
        "window": window,
        "forward": forward,
        "horizons": _parse_horizons(horizons),
        "cost_bps": cost_bps,
    }
    try:
        with get_db_session() as db:
            summary = FactorCatalogService().save_snapshot(db, params)
    except CatalogError as exc:
        _fail(str(exc))
    except Exception as exc:
        _fail(f"快照保存失败：{exc}")
    console.print(f"[green]✓[/green] 快照已保存：{_jsonable(summary)}")


@snapshot_app.command("list")
def snapshot_list(
    factor_name: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", min=1, max=500),
    as_json: bool = typer.Option(False, "--json"),
):
    """查询因子快照历史。"""
    from factor.catalog_service import FactorCatalogService
    from utils.db_session import get_db_session

    try:
        with get_db_session() as db:
            items = FactorCatalogService().list_snapshots(db, factor_name, limit=limit)
    except Exception as exc:
        _fail(f"快照查询失败：{exc}")
    if as_json:
        typer.echo(json.dumps({"snapshots": _jsonable(items)}, ensure_ascii=False, indent=2))
        return
    if not items:
        console.print("(无快照)")
        return
    table = Table(title=f"{factor_name} 快照（{len(items)}）")
    table.add_column("ID", justify="right")
    table.add_column("时间")
    table.add_column("IC", justify="right")
    table.add_column("bar", justify="right")
    for it in items:
        metrics = it.get("metrics") or {}
        table.add_row(
            str(it.get("id")),
            str(it.get("created_at", "")),
            f"{metrics.get('ic_mean', 0):.4f}" if metrics.get("ic_mean") is not None else "—",
            str(metrics.get("bar_count", "—")),
        )
    console.print(table)


@snapshot_app.command("delete")
def snapshot_delete(snapshot_id: int = typer.Argument(...)):
    """删除快照（连同 parquet 归档）。"""
    from factor.catalog_service import FactorCatalogService
    from utils.db_session import get_db_session

    try:
        with get_db_session() as db:
            FactorCatalogService().delete_snapshot(db, snapshot_id)
    except Exception as exc:
        _fail(f"快照删除失败：{exc}")
    console.print(f"[green]✓[/green] 快照 {snapshot_id} 已删除")


@app.command("catalog")
def catalog(as_json: bool = typer.Option(False, "--json")):
    """查看因子档案（分类/生命周期/快照数/最近指标）。"""
    from sqlalchemy import func

    from factor.catalog_service import FactorCatalogService
    from factor.models import FactorCatalog, FactorSnapshot
    from utils.db_session import get_db_session

    try:
        with get_db_session() as db:
            FactorCatalogService().sync_builtins(db)
            rows = db.query(FactorCatalog).order_by(FactorCatalog.is_builtin.desc(), FactorCatalog.name).all()
            counts = dict(
                db.query(FactorSnapshot.factor_name, func.count(FactorSnapshot.id))
                .group_by(FactorSnapshot.factor_name)
                .all()
            )
    except Exception as exc:
        _fail(f"档案查询失败：{exc}")
    items = [
        {
            "name": r.name,
            "label": r.label,
            "category": r.category,
            "builtin": r.is_builtin,
            "lifecycle_status": r.lifecycle_status,
            "last_metrics": json.loads(r.last_metrics) if r.last_metrics else None,
            "snapshot_count": counts.get(r.name, 0),
        }
        for r in rows
    ]
    if as_json:
        typer.echo(json.dumps({"factors": _jsonable(items)}, ensure_ascii=False, indent=2))
        return
    table = Table(title=f"因子档案（{len(items)}）")
    table.add_column("名称", style="cyan")
    table.add_column("分类")
    table.add_column("生命周期")
    table.add_column("快照", justify="right")
    for it in items:
        table.add_row(
            it["name"],
            it["category"] or "—",
            it["lifecycle_status"] or "—",
            str(it["snapshot_count"]),
        )
    console.print(table)


if __name__ == "__main__":
    app()
