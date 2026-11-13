"""内核 vs TradingEnv 口径差异的四类归因（`attribute_engine_diff`）。

覆盖：
1. 两侧费率一致 → `cost.ok` 为 True，残差等于总差；
2. 费率不一致 → `cost.ok` 为 False 且带 `error`（这是 bug，不是口径差异）；
3. 两侧费率一致但成交笔数不同（绝对手续费不同）→ `cost.ok` 仍为 True；
4. 资金费只有内核建模；
5. 端到端：同一份 20 根 bar + 确定性动作跑两条真实口径，费率口径必须对齐。

不训练真模型、不请求网络：SB3 侧用固定输出的假模型。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from services.rl_service import RL_TRANSACTION_COST, attribute_engine_diff


def test_cost_must_match():
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0, "turnover": 100_000.0},
        kernel={"total_pnl": 1_200.0, "fees": 10.0, "turnover": 100_000.0},
    )

    assert report["cost"]["ok"] is True
    assert "error" not in report
    assert report["cost"]["diff"] == 0.0
    assert report["cost"]["trading_env_rate"] == pytest.approx(RL_TRANSACTION_COST)
    assert report["cost"]["kernel_rate"] == pytest.approx(RL_TRANSACTION_COST)
    assert report["total_pnl"]["diff"] == 200.0
    # 费率一致、无资金费、无单独测得的动作差 → 残差就是总差
    assert report["matching"]["residual"] == 200.0


def test_cost_mismatch_is_flagged():
    """同样的成交名义、两倍的手续费 → 费率口径不一致，必须报出来。"""
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0, "turnover": 100_000.0},
        kernel={"total_pnl": 1_190.0, "fees": 20.0, "turnover": 100_000.0},
    )

    assert report["cost"]["ok"] is False
    assert report["error"] == "成本模型不一致"
    assert report["cost"]["diff"] == pytest.approx(RL_TRANSACTION_COST)


def test_same_rate_different_fill_count_is_ok():
    """成交笔数不同导致 fees 不同，但 `fees / turnover` 相同 → 成本模型一致。

    这类差异属于撮合层（重平衡阈值 / 最小成交额），挂在 `matching` 上，
    不能污染成本模型判定。
    """
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0, "turnover": 100_000.0},
        kernel={"total_pnl": 1_010.0, "fees": 25.0, "turnover": 250_000.0},
    )

    assert report["cost"]["ok"] is True
    assert "error" not in report
    assert report["cost"]["trading_env_rate"] == pytest.approx(RL_TRANSACTION_COST)
    assert report["cost"]["kernel_rate"] == pytest.approx(RL_TRANSACTION_COST)
    assert report["cost"]["diff"] == pytest.approx(0.0, abs=1e-12)
    # 绝对手续费差 15 全部留在撮合残差里
    assert report["matching"]["residual"] == pytest.approx(25.0)


def test_rate_mismatch_is_flagged():
    """内核吃默认 0.001、训练用 0.0001 的典型漂移 → 必须判不一致。"""
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0, "turnover": 100_000.0},
        kernel={"total_pnl": 1_000.0, "fees": 100.0, "turnover": 100_000.0},
    )

    assert report["cost"]["ok"] is False
    assert report["error"] == "成本模型不一致"
    assert report["cost"]["kernel_rate"] == pytest.approx(0.001)
    assert report["cost"]["diff"] == pytest.approx(0.001 - RL_TRANSACTION_COST)


def test_funding_only_in_kernel():
    """TradingEnv 不建模资金费：内核的资金费单独成类，并从残差里扣掉。"""
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0, "turnover": 100_000.0},
        kernel={"total_pnl": 1_005.0, "fees": 10.0, "turnover": 100_000.0, "funding": 5.0},
    )

    assert report["cost"]["ok"] is True
    assert report["funding"] == {"kernel": 5.0}
    assert report["action"]["diff"] == 0.0
    # 总差 5 全部由资金费解释，撮合层没有剩余
    assert report["matching"]["residual"] == pytest.approx(0.0)


def test_e2e_kernel_vs_trading_env_attribution(monkeypatch, tmp_path):
    """端到端：同一份 20 根 bar、同一个确定性动作跑两条真实口径。

    费率同源（都来自 `RL_TRANSACTION_COST`）后，`cost.ok` 必须为 True —— 尽管
    内核逐 bar 重平衡、`TradingEnv` 有最小成交阈值，两边绝对手续费并不相等，
    那部分差异归 `matching`，不是成本模型不一致。
    """
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    import numpy as np

    from rl.evaluation import evaluate_model
    from services.rl_service import GymnasiumWrapper, RLService

    if GymnasiumWrapper is None:
        pytest.skip("gymnasium 不可用")

    n = 20
    # 时间列走 DatetimeIndex（与 `BacktestDataProvider` 产出同形）：`create_env`
    # 只看列、不看 index，会给 TradingEnv 补 `range(n)` 的整数时间戳
    data = pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [10.0] * n,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
    )

    class FixedModel:
        """确定性策略：每根 bar 都要求 20% 权益占比。"""

        def predict(self, obs, deterministic=True):
            return np.array([0.2], dtype=np.float32), None

    svc = RLService()
    monkeypatch.setattr(svc, "load_model", lambda path: FixedModel())

    kernel_result = svc._run_kernel_backtest(str(tmp_path / "demo_ppo.zip"), data, "BTCUSDT", "1h", 100_000.0)

    wrapped_env = GymnasiumWrapper(svc.create_env(data, initial_capital=100_000.0))
    try:
        metrics = evaluate_model(FixedModel(), wrapped_env, transaction_cost=RL_TRANSACTION_COST)
        # 累计手续费由环境 info 给出（evaluate_model 只回 PnL/风险指标）
        env_fees = float(wrapped_env._env.info["transaction_costs"])
    finally:
        wrapped_env.close()

    report = attribute_engine_diff(
        trading_env={"total_pnl": metrics.total_pnl, "fees": env_fees, "turnover": metrics.turnover},
        kernel={
            "total_pnl": kernel_result["total_pnl"],
            "fees": kernel_result["total_fees"],
            "funding": kernel_result["total_funding"],
            "turnover": kernel_result["turnover"],
        },
    )

    assert env_fees > 0.0, "固定 0.2 占比必须真的成交"
    assert kernel_result["num_trades"] >= 1
    # 对外口径（05e0d85d 覆盖回写）：symbol 回原始入参、data_bars 按清洗前行数计，
    # 而非设施回显的 BASE/QUOTE 归一化名与清洗后 bar 数
    assert kernel_result["symbol"] == "BTCUSDT"
    assert kernel_result["data_bars"] == n
    assert report["funding"]["kernel"] == 0.0, "现货口径没有资金费"
    assert report["total_pnl"]["diff"] == pytest.approx(kernel_result["total_pnl"] - metrics.total_pnl)
    # 四类归因自洽：-手续费差 + 资金费 + 动作差 + 残差 == 总差
    fees_diff = kernel_result["total_fees"] - env_fees
    assert report["total_pnl"]["diff"] == pytest.approx(
        -fees_diff + report["funding"]["kernel"] + report["action"]["diff"] + report["matching"]["residual"]
    )
    assert report["cost"]["ok"] is True
    assert report["cost"]["trading_env_rate"] == pytest.approx(RL_TRANSACTION_COST, abs=1e-12)
    assert report["cost"]["kernel_rate"] == pytest.approx(RL_TRANSACTION_COST, abs=1e-12)


def test_run_backtest_task_persists_result(monkeypatch, tmp_path):
    """任务化回测端到端：真 kernel 跑通并把结果按策略回测契约落盘。

    DB 任务行写在 routes 层、不在此范围；BacktestService 的目录重定向到
    tmp_path，避免污染 backend/data。断言三件套：返回摘要可用、任务文件
    状态 completed、结果 JSON 携带详情页所需的 equity_curve/klines/trades 契约。
    """
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    import numpy as np

    from backtest.data_provider import BacktestDataProvider
    from backtest.service import BacktestService
    from services.rl_service import RLService

    n = 30
    data = pd.DataFrame(
        {
            "open": [100.0 + i * 0.1 for i in range(n)],
            "high": [100.0 + i * 0.1 + 1.0 for i in range(n)],
            "low": [100.0 + i * 0.1 - 1.0 for i in range(n)],
            "close": [100.0 + i * 0.1 + 0.5 for i in range(n)],
            "volume": [10.0] * n,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
    )

    class FixedModel:
        """前 5 根 bar 持 20% 仓位、后 5 根清仓：制造至少一次 round-trip。"""

        step = 0

        def predict(self, obs, deterministic=True):
            self.step = (self.step + 1) % 10
            target = 0.2 if self.step < 5 else 0.0
            return np.array([target], dtype=np.float32), None

    svc = RLService()
    monkeypatch.setattr(svc, "load_model", lambda path: FixedModel())
    # resolve_saved_model_path 里 model_id 即文件 stem，落盘策略名可预测
    (tmp_path / "demo_ppo.zip").write_bytes(b"stub")
    monkeypatch.setattr(svc, "resolve_saved_model_path", lambda model_id: tmp_path / f"{model_id}.zip")
    monkeypatch.setattr(BacktestDataProvider, "load_klines", lambda self, *a, **k: data)

    def fake_init(self):
        from unittest.mock import MagicMock

        self.results_dir = tmp_path
        self.logger = MagicMock()

    monkeypatch.setattr(BacktestService, "__init__", fake_init)

    summary = svc.run_backtest_task("demo_ppo", "BTCUSDT", "1h", "spot", 100_000.0)

    # 返回摘要：给前端 modal 直接展示的聚合指标
    assert summary["task_id"]
    assert summary["strategy_name"] == "rl_model:demo_ppo"
    assert summary["engine"] == "kernel"
    assert summary["data_bars"] == n

    svc_bts = BacktestService()
    # 任务文件：状态 completed，strategy_name 带 rl_model: 前缀供列表页识别来源
    task = json.loads(svc_bts._get_task_file(summary["task_id"]).read_text(encoding="utf-8"))
    assert task["status"] == "completed"
    assert task["strategy_name"] == "rl_model:demo_ppo"

    # 结果文件：详情/回放页复用所需的字段齐全（entry 键 = {SYMBOL}_{interval}）
    result = svc_bts.get_result(summary["task_id"])
    assert result["status"] == "completed"
    entry = result["results"]["BTCUSDT_1h"]
    assert len(entry["equity_curve"]) == n
    assert entry["trades"], "固定 20% 占比必须产生 round-trip 交易"
    assert entry["klines"] and len(entry["klines"]) == n
    assert result["results"]["portfolio"]["metrics"], "列表摘要依赖 portfolio.metrics"
    # 列表页摘要口径：total_return / max_drawdown 必须能从结果 JSON 提取
    metrics_summary = svc_bts._metrics_summary_from_result(result)
    assert {"total_return", "max_drawdown"} <= set(metrics_summary)
