"""Funding arbitrage 端到端自检。

运行:
    cd /Users/liupeng/workspace/quant/QuantCell && backend/.venv/bin/python scripts/check_funding_arb.py

功能:
- 加载 BTCUSDT 合成 K 线 (200 根 1h, 覆盖 8 天)
- 加载 funding_history_btcusdt_sample.csv
- 跑 BaselineBacktestService with funding_arbitrage 策略
- 断言:
  1. 运行完成 (不抛异常)
  2. baseline report 写入 data/source/backtest_baselines/
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让脚本可独立 import backend 包
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backtest.baseline import BaselineBacktestService, make_synthetic_kline  # noqa: E402


def main() -> int:
    fixtures = BACKEND_ROOT / "tests" / "fixtures" / "funding_history_btcusdt_sample.csv"
    output_dir = BACKEND_ROOT.parent / "data" / "source" / "backtest_baselines"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Funding Arbitrage 自检")
    print("=" * 60)
    print(f"funding fixture: {fixtures}")
    print(f"output dir:      {output_dir}")
    print()

    # 1. 跑 baseline
    df = make_synthetic_kline(n=200, start_price=50000.0)
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
        funding_history_path=str(fixtures),
        output_dir=output_dir,
    )
    try:
        report = svc.run()
    except Exception as e:
        print(f"X baseline.run 失败: {e}", file=sys.stderr)
        return 1

    # 2. 断言报告
    print("OK baseline run 完成")
    print(f"  total_pnl     = {report.total_pnl:.4f}")
    print(f"  sharpe_ratio  = {report.sharpe_ratio:.4f}")
    print(f"  max_drawdown  = {report.max_drawdown:.4f}")
    print(f"  win_rate      = {report.win_rate:.2%}")
    print(f"  total_trades  = {report.total_trades}")
    print()

    json_path = output_dir / "funding_arbitrage_BTCUSDT_2024-07-01_2024-07-08.json"
    md_path = output_dir / "funding_arbitrage_BTCUSDT_2024-07-01_2024-07-08.md"
    assert json_path.exists(), f"missing {json_path}"
    assert md_path.exists(), f"missing {md_path}"
    print(f"OK baseline 报告写入: {json_path.name}, {md_path.name}")
    print()
    print("=" * 60)
    print("OK check_funding_arb 全部断言通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
