"""回测 HTML 报告生成服务

把回测结果（结果 JSON + 任务信息）渲染成一份自包含 HTML 报告：
概览配置 → 核心指标 → 权益/回撤曲线图 → 成交明细 → 因子归因（如有）。

设计约定：
- 报告为单文件 HTML（PNG 图 base64 内嵌），双击即可离线打开，可浏览器打印为 PDF。
- 图内文字统一用英文（matplotlib 不内置中文字体，跨环境渲染中文会出现豆腐块），
  中文叙述全部放在 HTML 层。
- 归一化口径复用 BacktestService 的 staticmethod（extract_symbol_entries /
  build_portfolio_view / filter_contract_trades），保证与详情页数据一致。
"""

import base64
import io
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import matplotlib

# 报告在请求线程里生成，无显示设备。use("Agg") 必须在 pyplot 导入前调用；
# 若 pyplot 已被其他模块先行导入则 backend 已定，忽略失败即可（无 DISPLAY 环境默认也是 Agg）。
try:
    matplotlib.use("Agg")
except Exception:
    pass
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader, select_autoescape

from utils.logger import LogType, get_logger

from .service import BacktestService

logger = get_logger(__name__, LogType.APPLICATION)

# 成交明细截断阈值：几千条成交会使 HTML 达数 MB 且表格渲染卡顿，
# 报告保留最近可读规模，完整数据仍在详情页/结果 JSON 里
_TRADES_LIMIT = 200

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# ====================== 数据收集 ======================


def _load_backtest_meta(backtest_id: str) -> dict:
    """从数据库读任务元信息（策略名/配置/状态/创建时间）。

    与详情路由的读取逻辑同源；models/db_session 沿用函数内 import，
    依赖数据库连接初始化时机。
    """
    import json

    from backtest.models import BacktestTask
    from utils.db_session import get_db_session

    with get_db_session() as db:
        task = db.query(BacktestTask).filter_by(id=backtest_id).first()
        if not task:
            raise ValueError(f"回测任务不存在: {backtest_id}")
        backtest_config = {}
        if task.backtest_config:
            try:
                backtest_config = json.loads(task.backtest_config)
            except Exception as e:
                logger.warning(f"解析回测配置失败: {e}")
        return {
            "strategy_name": task.strategy_name,
            "backtest_config": backtest_config,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }


def _metrics_dict(metrics: list | None) -> dict[str, float]:
    """[{key, value}] → {key: value}，缺省空 dict。"""
    return {m.get("key"): m.get("value") for m in (metrics or []) if isinstance(m, dict) and m.get("key")}


def _collect_report_data(backtest_id: str, symbol: str | None) -> dict:
    """汇总报告所需全部数据，口径对齐详情接口（组合视图/单品种分支一致）。"""
    svc = BacktestService()
    meta = _load_backtest_meta(backtest_id)

    json_result = svc.get_result(backtest_id)
    if not isinstance(json_result, dict):
        raise ValueError(f"回测结果文件不存在: {backtest_id}")

    results = json_result.get("results") or {}
    entries = svc.extract_symbol_entries(results)
    if not entries:
        raise ValueError(f"回测结果中无品种数据: {backtest_id}")

    is_multi = len(entries) > 1
    use_portfolio = is_multi and (symbol in (None, "all"))
    if use_portfolio:
        view = svc.build_portfolio_view(results)
        metrics, trades, equity_curve = view["metrics"], view["trades"], view["equity_curve"]
        view_symbol = "all"
    else:
        entry = entries.get(symbol) if symbol else None
        if entry is None and symbol:
            logger.warning(f"结果中未找到品种 {symbol}，回退到第一个品种")
        if entry is None:
            entry = next(iter(entries.values()), {})
        metrics, trades = entry.get("metrics") or [], entry.get("trades") or []
        equity_curve = entry.get("equity_curve") or []
        view_symbol = entry.get("symbol") or symbol

    # 仅保留 round-trip 契约成交；旧结果无契约字段时展示占位说明
    contract_trades = svc.filter_contract_trades(trades)
    # 旧版引擎判定要覆盖组合视角：build_portfolio_view 返回的 trades 已是过滤后
    # 的契约记录，需回溯各品种原始 trades 总数才能发现「有成交但非契约」的场景
    raw_trades_count = sum(len(e.get("trades") or []) for e in entries.values()) if use_portfolio else len(trades)

    # 多品种摘要：逐品种抽取贡献类指标（与品种视角前端卡片同源字段）
    symbols_summary = [
        {
            "symbol": sym,
            **{k: _metrics_dict(e.get("metrics")).get(k) for k in ("total_return", "total_pnl", "total_trades")},
        }
        for sym, e in entries.items()
    ]

    return {
        **meta,
        "backtest_id": backtest_id,
        "view_symbol": view_symbol,
        "is_portfolio": use_portfolio,
        "capital_mode": (meta.get("backtest_config") or {}).get("capital_mode", "per_symbol"),
        "metrics": metrics,
        "equity_curve": equity_curve,
        "factors": (entries.get(view_symbol) or {}).get("factors") if not use_portfolio else {},
        "trades_total": len(trades),
        "legacy_trades": raw_trades_count > 0 and not contract_trades,
        "trades_shown": contract_trades[:_TRADES_LIMIT],
        "trades_truncated": len(contract_trades) > _TRADES_LIMIT,
        "symbols_summary": symbols_summary if is_multi else [],
        "skipped_symbols": results.get("skipped_symbols") or {},
    }


# ====================== 图表 ======================


def _ts_to_seconds(ts: float | None) -> float | None:
    """兼容秒/毫秒/微秒/纳秒时间戳 → 秒。

    实测引擎产出的 equity_curve.timestamp 为毫秒级，直接 fromtimestamp 会
    year out of range，故按量级归一（各量级阈值间隔 1000 倍，秒级恒 < 1e11）。
    """
    if ts is None:
        return None
    n = abs(int(ts))
    if n >= 1e17:
        return float(ts) / 1e9
    if n >= 1e14:
        return float(ts) / 1e6
    if n >= 1e11:
        return float(ts) / 1e3
    return float(ts)


def _forward_fill(values: list) -> list[float]:
    """缺失值沿用上一个真实值（首点缺失记 NaN），保证绘图线连续。

    合并后的组合曲线已做前向填充，但单品种视角/旧结果可能缺 balance 键。
    """
    out: list[float] = []
    last: float | None = None
    for v in values:
        if v is not None:
            last = float(v)
        out.append(float("nan") if last is None else last)
    return out


def _equity_chart_base64(equity_curve: list) -> str | None:
    """权益 + 存款 + 回撤双面板 PNG（base64 data URI）。数据点不足 2 时返回 None。"""
    points = [p for p in equity_curve if isinstance(p, dict) and p.get("equity") is not None]
    if len(points) < 2:
        return None

    seconds = [_ts_to_seconds(p.get("timestamp")) for p in points]
    times = [datetime.fromtimestamp(s, tz=UTC) if s is not None else None for s in seconds]
    equities = [float(p["equity"]) for p in points]
    # 无时间戳的兜底点退化为序号轴（正常引擎产出都有 timestamp）
    xs, labels = [], []
    last_dt = None
    for i, t in enumerate(times):
        last_dt = t or last_dt
        xs.append(last_dt or i)
    labels = xs

    fig, (ax_eq, ax_dd) = plt.subplots(
        2, 1, figsize=(10, 4.2), dpi=110, sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    ax_eq.plot(labels, equities, color="#2563eb", linewidth=1.2, label="Net Value")
    # 存款（balance）：存在则同图叠加基准线，净值高于它即浮盈（图内文字用英文）
    balances = [p.get("balance") for p in points]
    if any(b is not None for b in balances):
        ax_eq.plot(labels, _forward_fill(balances), color="#6b7280", linewidth=1.0, linestyle="--", label="Deposit")
        ax_eq.legend(loc="upper left", fontsize=8)
    ax_eq.set_ylabel("Net Value")
    ax_eq.grid(True, alpha=0.3)
    ax_eq.margins(x=0)

    # underwater 曲线：相对历史峰值的回撤百分比
    peak = equities[0]
    drawdowns = []
    for v in equities:
        peak = max(peak, v)
        drawdowns.append((v / peak - 1.0) * 100.0 if peak > 0 else 0.0)
    ax_dd.fill_between(labels, drawdowns, 0, color="#dc2626", alpha=0.4)
    ax_dd.plot(labels, drawdowns, color="#dc2626", linewidth=0.9)
    ax_dd.set_ylabel("Drawdown %")
    ax_dd.grid(True, alpha=0.3)
    ax_dd.margins(x=0)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ====================== 渲染 ======================


def _build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_config_rows(backtest_config: dict, view_symbol: str, capital_mode: str) -> list[tuple[str, str]]:
    """报告「回测配置」区块的键值行（模板不感知 config 具体键名）。"""
    cfg = backtest_config or {}
    symbols = cfg.get("symbols") or ([view_symbol] if view_symbol else [])
    mode_label = {"shared": "共享资金池（单账户）", "per_symbol": "独立资金池（每品种各一份初始资金）"}.get(
        capital_mode, capital_mode or "—"
    )
    rows = [
        ("交易品种", "、".join(symbols) or "—"),
        ("K线周期", cfg.get("interval") or "—"),
        ("时间范围", f"{cfg.get('start_time') or '—'} ~ {cfg.get('end_time') or '—'}"),
        ("初始资金", cfg.get("initial_cash", "—")),
        ("资金使用方式", mode_label),
    ]
    for extra in ("candle_type", "market_type"):
        if cfg.get(extra):
            rows.append((extra, cfg[extra]))
    return rows


def render_backtest_report(backtest_id: str, symbol: str | None = None) -> str:
    """渲染回测报告 HTML。

    Raises:
        ValueError: 任务/结果不存在或无品种数据（路由层转 404）
    """
    data = _collect_report_data(backtest_id, symbol)
    data["config_rows"] = build_config_rows(
        data.get("backtest_config") or {}, data["view_symbol"], data["capital_mode"]
    )
    data["equity_img"] = _equity_chart_base64(data["equity_curve"])
    data["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    html = _build_env().get_template("backtest_report.html.j2").render(**data)
    logger.info(f"回测报告渲染完成 backtest_id={backtest_id} symbol={symbol or 'all'}")
    return html


def report_filename(backtest_id: str) -> str:
    """Content-Disposition 用的下载文件名（RFC 5987 需 percent-encode）。"""
    date = datetime.now().strftime("%Y%m%d")
    return quote(f"回测报告_{backtest_id[:8]}_{date}.html")
