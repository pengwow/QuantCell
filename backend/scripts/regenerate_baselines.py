"""重新生成 9 策略模板的 baseline 报告。

调用 axon_quant 0.10.0 multi-leg API 跑回测,输出到
data/source/backtest_baselines/ 替换旧版基线报告。

新基线特征:
- 走 BacktestEngine 事件驱动(不再手写仓位状态机)
- 多 leg API(spot + perp,spot_symbol 默认 None 表示单 perp)
- funding_arbitrage 走多腿路径
- 报告含 total_funding_pnl / total_fees / max_drawdown_pct 字段(引擎层累计)
- sharpe_ratio 走 bar_nav_curve 重算
- 0.10.0 修复 funding dispatch 时机,同 bar push_funding 无需 ts+1 偏移
- llm_signal: 基于 axon_quant MarketSignal 的 AI 信号模板(默认 heuristic=双均线,可注入 llm_provider)

ponytail:每个策略跑通即得基线,用作 regression baseline
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# backend 根目录加 path (scripts dir + parent)
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import pandas as pd  # noqa: E402

from backtest.baseline import BaselineBacktestService, make_synthetic_kline  # noqa: E402


# 9 策略模板 + 配置
STRATEGIES = [
    {
        "name": "dual_ma",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "llm_signal",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "trend_follow",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "mean_reversion",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "mean_reversion_rl",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "momentum",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "grid",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "cross_sectional",
        "symbol": "BTCUSDT",
        "spot_symbol": None,
        "funding_csv": None,
    },
    {
        "name": "funding_arbitrage",
        "symbol": "BTCUSDT-PERP",
        "spot_symbol": "BTCUSDT",
        "funding_csv": "_auto_",  # 自动生成 funding CSV
    },
]


def _make_funding_csv(tmpdir: Path) -> str:
    """生成 funding CSV: 每 8h 一个 0.0005 费率事件,覆盖 7 天。

    0.0005 高于 funding_arbitrage 默认 entry_threshold(0.0003),
    便于 min_hold_bars=8 在 1h bar 上命中入场。
    """
    csv_path = tmpdir / "funding.csv"
    base_ts_ms = int(pd.Timestamp("2024-07-01T00:00:00").timestamp() * 1000)
    interval_ms = 8 * 3600 * 1000  # 8h
    n_events = (24 * 7) // 8  # 21 events for 7 days
    rows = ["funding_time_ms,funding_rate"]
    for i in range(n_events):
        rows.append(f"{base_ts_ms + i * interval_ms},0.0005")
    csv_path.write_text("\n".join(rows))
    return str(csv_path)


def _resolve_baseline_output_dir() -> Path:
    """解析 baseline 输出目录: 总是项目根的 data/source/backtest_baselines。

    ponytail: 脚本可能在 backend/ 或项目根跑; 统一锚到项目根,
             这样 git 跟踪路径稳定 (data/source/backtest_baselines/...)
    """
    # scripts/ 父目录的父目录 = 项目根
    project_root = Path(__file__).resolve().parent.parent.parent
    out = project_root / "data" / "source" / "backtest_baselines"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _make_funding_csv_yearly(tmpdir: Path) -> str:
    """生成 1 年 funding CSV: 每 8h 一个 0.0005 费率事件,覆盖 1 年 (365 天)。

    0.0005 高于 funding_arbitrage 默认 entry_threshold(0.0003),
    便于 min_hold_bars=8 在 1h bar 上命中入场。
    """
    csv_path = tmpdir / "funding_yearly.csv"
    base_ts_ms = int(pd.Timestamp("2024-07-01T00:00:00").timestamp() * 1000)
    interval_ms = 8 * 3600 * 1000  # 8h
    n_events = (24 * 365) // 8  # 1095 events for 1 year
    rows = ["funding_time_ms,funding_rate"]
    for i in range(n_events):
        rows.append(f"{base_ts_ms + i * interval_ms},0.0005")
    csv_path.write_text("\n".join(rows))
    return str(csv_path)


def regenerate_all_baselines() -> int:
    """跑 8 策略模板,输出到 default output_dir。

    生成 2 个周期:
    - 7 天 (2024-07-01~2024-07-08): 168 根 1h bar
    - 1 年 (2024-07-01~2025-07-01): 8784 根 1h bar

    Returns: 0 = 全部成功, 1 = 至少 1 个失败
    """
    output_dir = _resolve_baseline_output_dir()

    fail_count = 0
    # 7 天 + 1 年 周期
    periods = [
        ("2024-07-01", "2024-07-08", 168, "funding.csv", _make_funding_csv),
        ("2024-07-01", "2025-07-01", 8784, "funding_yearly.csv", _make_funding_csv_yearly),
    ]
    for start, end, n_bars, _csv_name, csv_factory in periods:
        df = make_synthetic_kline(n=n_bars, start_price=50000.0, seed=42)
        print(f"\n### period {start} ~ {end} ({n_bars} bars) ###")
        for cfg in STRATEGIES:
            name = cfg["name"]
            print(f"\n=== {name} ===")
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = Path(tmp)
                funding_csv = None
                if cfg["funding_csv"] == "_auto_":
                    funding_csv = csv_factory(tmpdir)

                try:
                    svc = BaselineBacktestService(
                        strategy_name=name,
                        symbol=cfg["symbol"],
                        start=start,
                        end=end,
                        output_dir=output_dir,
                        data=df,
                        funding_history_path=funding_csv,
                        spot_symbol=cfg["spot_symbol"],
                    )
                    t0 = time.time()
                    report = svc.run()
                    dt = time.time() - t0
                    print(
                        f"  ✓ total_pnl={report.total_pnl:.4f} "
                        f"funding_pnl={report.total_funding_pnl:.4f} "
                        f"trades={report.total_trades} "
                        f"sharpe={report.sharpe_ratio:.4f} "
                        f"({dt:.2f}s)"
                    )
                except Exception as e:
                    print(f"  ✗ {name} failed: {type(e).__name__}: {e}")
                    fail_count += 1
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(regenerate_all_baselines())
