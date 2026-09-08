"""rl.lifecycle 单元测试。

策略：
- 用 FakeRLService 替换 rl.lifecycle.RLService，避免真实训练/回测/真实数据源
- 用 FakeTime 控制 retrain 的 model_name 后缀与 run_loop 的 sleep

覆盖：
- _make_train_config / _to_metrics（纯函数）
- evaluate_and_decide（三种重训练触发条件 + keep）
- run_initial_training / run_backtest / retrain / run_once / run_loop
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import rl.lifecycle as lifecycle_mod
from rl.lifecycle import LifecycleConfig, ModelMetrics, RLLifecycle
from services.rl_service import RLTrainConfig

INITIAL_MODEL = "/models/BTCUSDT_v1.zip"
RETRAIN_MODEL = "/models/BTCUSDT_retrain_1234567890.zip"


class FakeTime:
    """可控的 time 替代品：固定 now、记录 sleep 调用。"""

    def __init__(self, at: float = 1234567890.0, sleep_raises: type[Exception] | None = None):
        self._at = at
        self._raises = sleep_raises
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self._at

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        if self._raises is not None:
            raise self._raises()


class FakeRLService:
    """按 RLService.train/run_backtest 使用方式实现的假服务。

    train 返回基于 model_name 推断的固定路径；run_backtest 按模型路径返回预置指标。
    """

    def __init__(
        self,
        bt_by_path: dict[str, dict] | None = None,
        default_bt: dict | None = None,
    ):
        self._bt_by_path = bt_by_path or {}
        self._default_bt = default_bt or {}
        self.train_calls: list[RLTrainConfig] = []
        self.bt_calls: list[tuple[str, str, str, dict]] = []

    def train(self, config: RLTrainConfig):
        self.train_calls.append(config)
        model_path = f"/models/{config.model_name}.zip"
        return SimpleNamespace(model_path=model_path, model_id=config.model_name)

    def run_backtest(self, model_path: str, symbol: str = "", interval: str = "1h", **kwargs):
        self.bt_calls.append((model_path, symbol, interval, kwargs))
        return self._bt_by_path.get(model_path, self._default_bt.copy())


def _bt(**overrides) -> dict:
    """默认回测指标字典，可覆盖任意字段。"""
    base = {
        "total_pnl": 1000.0,
        "num_trades": 50,
        "win_rate": 0.6,
        "sharpe_ratio": 1.5,
        "max_drawdown_pct": -2.0,
        "initial_capital": 100_000.0,
    }
    base.update(overrides)
    return base


def _new_lifecycle(
    monkeypatch,
    fake: FakeRLService | None = None,
    config: LifecycleConfig | None = None,
) -> RLLifecycle:
    """构造已注入 FakeRLService 的 RLLifecycle。"""
    fake = fake or FakeRLService()
    monkeypatch.setattr(lifecycle_mod, "RLService", lambda: fake)
    return RLLifecycle(config or LifecycleConfig())


# ==================== 纯函数 ====================


def test_make_train_config_maps_fields():
    lc = RLLifecycle(LifecycleConfig(symbol="ETHUSDT", interval="15m", algorithm="sac", reward_type="sharpe"))

    cfg = lc._make_train_config(999, "ETHUSDT_v2")

    assert isinstance(cfg, RLTrainConfig)
    assert cfg.algorithm == "sac"
    assert cfg.symbol == "ETHUSDT"
    assert cfg.interval == "15m"
    assert cfg.total_timesteps == 999
    assert cfg.reward_type == "sharpe"
    assert cfg.model_name == "ETHUSDT_v2"


def test_to_metrics_maps_fields_and_computes_portfolio_value():
    m = RLLifecycle._to_metrics("m1", _bt())

    assert m.model_name == "m1"
    assert m.total_pnl == 1000.0
    assert m.num_trades == 50
    assert m.win_rate == 0.6
    assert m.sharpe_ratio == 1.5
    assert m.max_drawdown_pct == -2.0
    assert m.portfolio_value == 101_000.0


def test_to_metrics_empty_dict_uses_defaults():
    m = RLLifecycle._to_metrics("m1", {})

    assert m.total_pnl == 0.0
    assert m.num_trades == 0
    assert m.win_rate == 0.0
    assert m.portfolio_value == 100_000.0


# ==================== evaluate_and_decide ====================


def test_evaluate_decide_keep_when_all_thresholds_ok():
    lc = RLLifecycle(LifecycleConfig(min_trades=10, max_drawdown_pct=5.0, min_sharpe=0.5))
    metrics = ModelMetrics(model_name="m", num_trades=20, sharpe_ratio=1.0, max_drawdown_pct=-3.0)
    assert lc.evaluate_and_decide(metrics) == "keep"


def test_evaluate_decide_retrain_when_trades_below_min():
    lc = RLLifecycle(LifecycleConfig(min_trades=10, max_drawdown_pct=5.0, min_sharpe=0.5))
    metrics = ModelMetrics(model_name="m", num_trades=2, sharpe_ratio=1.0, max_drawdown_pct=0.0)
    assert lc.evaluate_and_decide(metrics) == "retrain"


def test_evaluate_decide_retrain_when_drawdown_exceeds():
    lc = RLLifecycle(LifecycleConfig(min_trades=10, max_drawdown_pct=5.0, min_sharpe=0.5))
    # 回撤阈值用绝对值判断，正负都要触发
    assert (
        lc.evaluate_and_decide(ModelMetrics(model_name="m", num_trades=20, sharpe_ratio=1.0, max_drawdown_pct=-6.0))
        == "retrain"
    )
    assert (
        lc.evaluate_and_decide(ModelMetrics(model_name="m", num_trades=20, sharpe_ratio=1.0, max_drawdown_pct=6.0))
        == "retrain"
    )


def test_evaluate_decide_retrain_when_sharpe_below_min():
    lc = RLLifecycle(LifecycleConfig(min_trades=10, max_drawdown_pct=5.0, min_sharpe=0.5))
    metrics = ModelMetrics(model_name="m", num_trades=20, sharpe_ratio=0.2, max_drawdown_pct=0.0)
    assert lc.evaluate_and_decide(metrics) == "retrain"


# ==================== 训练 / 回测（Mock） ====================


def test_run_initial_training_returns_model_path(monkeypatch):
    fake = FakeRLService()
    lc = _new_lifecycle(monkeypatch, fake)

    path = lc.run_initial_training()

    assert path == INITIAL_MODEL
    cfg = fake.train_calls[0]
    assert cfg.symbol == "BTCUSDT"
    assert cfg.total_timesteps == 30_000
    assert cfg.model_name == "BTCUSDT_v1"


def test_run_backtest_passes_config_and_returns_metrics(monkeypatch):
    fake = FakeRLService(default_bt=_bt())
    lc = _new_lifecycle(monkeypatch, fake)

    result = lc.run_backtest(INITIAL_MODEL)

    assert fake.bt_calls[0][0] == INITIAL_MODEL
    assert fake.bt_calls[0][1] == "BTCUSDT"
    assert fake.bt_calls[0][2] == "1h"
    assert fake.bt_calls[0][3]["reward_type"] == "pnl"
    assert result["sharpe_ratio"] == 1.5


# ==================== retrain / run_once / run_loop ====================


def test_retrain_returns_new_model_when_better(monkeypatch):
    fake = FakeRLService(
        bt_by_path={
            INITIAL_MODEL: _bt(sharpe_ratio=0.5),
            RETRAIN_MODEL: _bt(sharpe_ratio=1.2),
        }
    )
    monkeypatch.setattr(lifecycle_mod, "time", FakeTime())
    lc = _new_lifecycle(monkeypatch, fake)

    new_path = lc.retrain(INITIAL_MODEL)

    assert new_path == RETRAIN_MODEL
    # 新模型一例 train；旧模型与新模型共回测两次
    assert len(fake.train_calls) == 1
    assert fake.train_calls[0].total_timesteps == 10_000
    assert len(fake.bt_calls) == 2


def test_retrain_keeps_old_model_when_not_better(monkeypatch):
    fake = FakeRLService(
        bt_by_path={
            INITIAL_MODEL: _bt(sharpe_ratio=1.2),
            RETRAIN_MODEL: _bt(sharpe_ratio=0.4),
        }
    )
    monkeypatch.setattr(lifecycle_mod, "time", FakeTime())
    lc = _new_lifecycle(monkeypatch, fake)

    assert lc.retrain(INITIAL_MODEL) == INITIAL_MODEL


def test_run_once_keep_flow(monkeypatch):
    fake = FakeRLService(default_bt=_bt())
    lc = _new_lifecycle(monkeypatch, fake)

    summary = lc.run_once()

    assert summary["decision"] == "keep"
    assert summary["model_path"] == INITIAL_MODEL
    assert summary["backtest"]["sharpe_ratio"] == 1.5
    # keep 分支：train 一次 + 回测一次
    assert len(fake.train_calls) == 1
    assert len(fake.bt_calls) == 1


def test_run_once_retrain_flow_when_metrics_poor(monkeypatch):
    fake = FakeRLService(
        bt_by_path={
            INITIAL_MODEL: _bt(num_trades=0, sharpe_ratio=0.3, max_drawdown_pct=-8.0),
            RETRAIN_MODEL: _bt(num_trades=80, sharpe_ratio=1.5, max_drawdown_pct=-1.0),
        }
    )
    monkeypatch.setattr(lifecycle_mod, "time", FakeTime())
    lc = _new_lifecycle(monkeypatch, fake)

    summary = lc.run_once()

    assert summary["decision"] == "retrain"
    assert summary["model_path"] == RETRAIN_MODEL
    assert summary["backtest"]["sharpe_ratio"] == 1.5
    # 初训 + 重训 两次 train；初次回测 + 新旧对比两次 + 最终一次
    assert len(fake.train_calls) == 2
    assert len(fake.bt_calls) == 4


def test_run_loop_iterates_and_sleeps_interval(monkeypatch):
    class _StopLoop(Exception):
        pass

    fake_time = FakeTime(sleep_raises=_StopLoop)
    monkeypatch.setattr(lifecycle_mod, "time", fake_time)
    fake = FakeRLService(default_bt=_bt())
    lc = _new_lifecycle(monkeypatch, fake)

    with pytest.raises(_StopLoop):
        lc.run_loop()

    # 跑完一轮后，按配置的间隔 sleep（默认 24h）
    assert fake_time.sleep_calls == [24 * 3600]
