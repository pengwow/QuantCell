"""回测 HTML 报告生成服务的单测。

monkeypatch 数据源（_load_backtest_meta / BacktestService.get_result），
归一化/组合视图/成交过滤走 BacktestService 真实实现，保证与详情页口径一致。
"""

import base64
import math

import pytest

from backtest import report_service as rs
from backtest.service import BacktestService

# 与真实结果一致的最小数据形态：equity 时间戳毫秒级、trade 契约字段齐全
_FAKE_META = {
    "strategy_name": "dual_ma",
    "backtest_config": {
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "interval": "15m",
        "start_time": "2025-01-01",
        "end_time": "2025-01-31",
        "initial_cash": 10000.0,
        "capital_mode": "per_symbol",
    },
    "status": "completed",
    "created_at": "2026-10-20T12:00:00",
}

_METRICS = [
    {"name": "总收益率", "key": "total_return", "value": 12.3456, "description": "总收益率", "type": "percentage"},
    {"name": "夏普比率", "key": "sharpe_ratio", "value": 1.5, "description": "夏普比率", "type": "number"},
]


def _fake_trade(symbol: str, i: int) -> dict:
    return {
        "trade_id": f"rt-{symbol}-{i}",
        "symbol": symbol,
        "timestamp": 1776755700 + i,
        "formatted_time": "2026-04-21 07:15:00",
        "entry_time": "2026-04-21T07:15:00.000Z",
        "exit_time": "2026-04-21T08:15:00.000Z",
        "exit_timestamp": 1776759300 + i,
        "entry_price": 76139.4,
        "exit_price": 75783.4,
        "size": 0.01,
        "pnl": -0.47,
        "return_pct": -0.06,
        "direction": "long",
        "entry_side": "buy",
        "exit_side": "sell",
        "status": "closed",
        "entry_fill_ids": [i],
        "exit_fill_ids": [i + 1],
        "fills": [],
    }


def _symbol_entry(symbol: str, trades: list, curve_ms: bool = True) -> dict:
    step = 60_000 if curve_ms else 60
    return {
        "symbol": symbol,
        "timeframe": "15m",
        "metrics": _METRICS,
        "trades": trades,
        "equity_curve": [{"timestamp": 1776729600000 + i * step, "equity": 10000.0 + i * 10} for i in range(5)],
        "factors": {},
    }


def _multi_results(trades_per_symbol: int = 3) -> dict:
    return {
        "results": {
            "strategy_name": "dual_ma",
            "symbols": ["BTC/USDT", "ETH/USDT"],
            "timeframe": "15m",
            "capital_mode": "per_symbol",
            "portfolio": {
                "metrics": _METRICS,
                "equity_curve": _symbol_entry("BTC/USDT", [], curve_ms=False)["equity_curve"],
            },
            "results_by_symbol": {
                "BTC/USDT": _symbol_entry("BTC/USDT", [_fake_trade("BTC/USDT", i) for i in range(trades_per_symbol)]),
                "ETH/USDT": _symbol_entry("ETH/USDT", [_fake_trade("ETH/USDT", i) for i in range(trades_per_symbol)]),
            },
        }
    }


@pytest.fixture
def patched_sources(monkeypatch):
    """替换报告的数据源：任务元信息 + 结果 JSON（均不打数据库/文件）。"""

    def install(meta=_FAKE_META, result_obj=_multi_results()):
        monkeypatch.setattr(rs, "_load_backtest_meta", lambda bid: meta)
        monkeypatch.setattr(BacktestService, "get_result", lambda self, rid: result_obj)

    return install


def test_render_portfolio_report_contains_core_sections(patched_sources):
    """多品种缺省 symbol → 组合视角报告：图内嵌 base64、多品种摘要、成交 symbol 可见。"""
    patched_sources()
    html = rs.render_backtest_report("abc12345-0000")

    assert html.lstrip().lower().startswith("<!doctype html") or "<html" in html.lower()
    assert "量化回测报告" in html
    assert "dual_ma" in html
    assert "data:image/png;base64," in html
    # 组合视角标记 + 各品种成交 symbol 拼进了成交明细
    assert "组合（全部品种）" in html
    assert "BTC/USDT" in html
    assert "ETH/USDT" in html
    # 资金使用方式中文标签
    assert "独立资金池" in html
    # 权益曲线图是合法 PNG（base64 可解码且带 PNG 魔数）
    img = html.split("data:image/png;base64,", 1)[1].split('"', 1)[0]
    assert base64.b64decode(img).startswith(b"\x89PNG")


def test_render_metrics_formatting(patched_sources):
    """percentage 指标补 %，常规指标保留数值。"""
    patched_sources()
    html = rs.render_backtest_report("abc12345-0000")
    assert "12.35%" in html  # round(2) + %
    assert "1.5" in html


def test_render_single_symbol_view(patched_sources):
    """指定品种 → 单品种视角（非组合）。"""
    patched_sources()
    html = rs.render_backtest_report("abc12345-0000", symbol="ETH/USDT")
    assert "数据视角：ETH/USDT" in html
    assert "组合（全部品种）" not in html


def test_render_empty_equity_curve_no_img(patched_sources, monkeypatch):
    """权益点不足 2 → 无内嵌图，显示占位提示。"""
    result = _multi_results()
    for e in result["results"]["results_by_symbol"].values():
        e["equity_curve"] = [{"timestamp": 1776729600000, "equity": 10000.0}]
    patched_sources(result_obj=result)
    html = rs.render_backtest_report("abc12345-0000")
    assert "data:image/png;base64," not in html
    assert "无法绘图" in html


def test_render_legacy_trades_placeholder(patched_sources):
    """旧版引擎 trades（无契约字段）→ 占位说明而非空表。"""
    result = _multi_results()
    for e in result["results"]["results_by_symbol"].values():
        e["trades"] = [{"price": 100.0, "quantity": 1.0, "realized_pnl": 1.0}]
    patched_sources(result_obj=result)
    html = rs.render_backtest_report("abc12345-0000")
    assert "旧版引擎产出" in html
    assert "买入开多" not in html


def test_render_trades_truncated_to_200(patched_sources):
    """超过 200 笔契约成交 → 截断提示，表格只渲染 200 行。"""
    result = _multi_results(trades_per_symbol=130)  # 2 品种 × 130 = 260
    patched_sources(result_obj=result)
    html = rs.render_backtest_report("abc12345-0000")
    assert "仅展示前 200 笔" in html
    # 成交表每行都有一个方向 tag；200 行被渲染（260 被截断）
    rows = html.count('<span class="tag long">买入开多</span>') + html.count('<span class="tag short">卖出开空</span>')
    assert rows == 200


def test_missing_task_raises_value_error(monkeypatch):
    """任务不存在 → ValueError（路由层转 404）。"""
    monkeypatch.setattr(rs, "_load_backtest_meta", lambda bid: (_ for _ in ()).throw(ValueError("回测任务不存在")))
    monkeypatch.setattr(BacktestService, "get_result", lambda self, rid: _multi_results())
    with pytest.raises(ValueError):
        rs.render_backtest_report("no-such-id")


def test_missing_result_raises_value_error(monkeypatch):
    """结果 JSON 不存在 → ValueError。"""
    monkeypatch.setattr(rs, "_load_backtest_meta", lambda bid: _FAKE_META)
    monkeypatch.setattr(BacktestService, "get_result", lambda self, rid: None)
    with pytest.raises(ValueError, match="结果文件"):
        rs.render_backtest_report("abc12345-0000")


def test_report_filename_encoded(patched_sources):
    """下载文件名为 percent-encode 的 .html（RFC 5987 扩展头要求）。"""
    name = rs.report_filename("abc12345-6789-0000")
    assert name.endswith(".html")
    assert "回测报告" not in name  # 中文必须被编码
    assert name.startswith("%E5%9B%9E%E6%B5%8B")  # "回测" 的 UTF-8 percent-encode


def test_ts_to_seconds_normalizes_units():
    """秒/毫秒/微秒/纳秒统一归一到秒。"""
    assert rs._ts_to_seconds(1776755700) == 1776755700
    assert rs._ts_to_seconds(1776755700000) == 1776755700.0
    assert rs._ts_to_seconds(1776755700000000) == 1776755700.0
    assert rs._ts_to_seconds(1776755700000000000) == 1776755700.0
    assert rs._ts_to_seconds(None) is None


def test_forward_fill_carries_last_known_value():
    """存款线缺失点沿用上一个真实值，首点缺失记 NaN（绘图断线）。"""
    out = rs._forward_fill([None, 1.0, None, 2.0])

    assert math.isnan(out[0]), "首点缺失应为 NaN"
    assert out[1:] == [1.0, 1.0, 2.0], f"got {out[1:]}"
