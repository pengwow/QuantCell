"""model 场景单测：JSON 配置解析/限额 clamp、WF 指标组装、OOS 口径、judge 硬门、注册表入库。

evaluate 的训练路径用 stub RLTrainResult 守编排契约；另留一个 SB3 可用时的最小
真实训练 smoke（2 折 × 300 步），防止场景参数与 RLTrainConfig 契约脱节。
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import research.scenarios.model as model_scenario_module
import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化（与 research 测试同口径）
from collector.db.database import Base
from research import service
from research.models import ResearchSession, ResearchTrial
from research.scenarios.model import ModelScenario, ModelTask
from services.rl_service import RLTrainResult

CFG = {"symbols": ["BTCUSDT"], "interval": "1h", "candle_type": "spot", "start": "2026-01-01", "end": "2026-06-01"}


def _synth_ohlcv(n: int = 200) -> pd.DataFrame:
    rows = []
    ts = 1_700_000_000_000_000_000
    price = 100.0
    for _ in range(n):
        o = price
        price += 0.5
        rows.append({"timestamp": ts, "open": o, "high": price + 0.2, "low": o - 0.2, "close": price, "volume": 100.0})
        ts += 3_600_000_000_000
    return pd.DataFrame(rows)


def _wf_result(
    mean_sharpe: float = 1.2, mean_pnl: float = 50.0, trades: int = 8, last_sharpe: float | None = 1.0
) -> RLTrainResult:
    """构造 WF 输出结构的 stub：aggregate.mean / folds[-1].oos_metrics 与 walk_forward_rl 对齐。"""
    oos = {"sharpe_ratio": last_sharpe, "total_pnl": mean_pnl, "num_trades": max(trades - 1, 0)}
    return RLTrainResult(
        model_id="rl_model_ppo_1",
        model_path="/tmp/fake-model.zip",
        metrics={"steps": 3000, "algorithm": "ppo"},
        walk_forward={
            "folds": [
                {"fold": 0, "oos_metrics": {"sharpe_ratio": 1.4, "total_pnl": 60.0, "num_trades": trades}},
                {"fold": 1, "oos_metrics": oos},
            ],
            "aggregate": {
                "mean": {
                    "sharpe_ratio": mean_sharpe,
                    "total_pnl": mean_pnl,
                    "num_trades": trades,
                    "win_rate": 0.5,
                    "max_drawdown_pct": 5.0,
                },
                "std": {"sharpe_ratio": 0.2},
                "n_valid_folds": 2,
            },
        },
    )


# ---------- build_tasks ----------


def test_build_tasks_parses_array_and_skips_bad_items():
    def llm(system, user, stage=None):
        content = (
            '[{"name": "a", "description": "d", "params": {"algorithm": "ppo"}}, "garbage", '
            '{"name": "b", "description": "d2"}]'
        )
        return content, {"total_tokens": 10}

    tasks, usage = ModelScenario().build_tasks(llm_call=llm, hypothesis="h", context="c", n=2)
    assert [t.name for t in tasks] == ["a", "b"]
    assert usage["total_tokens"] == 10
    assert isinstance(tasks[0], ModelTask)


# ---------- _parse_params：校验与限额 clamp ----------

VALID = json.dumps(
    {
        "algorithm": "ppo",
        "total_timesteps": 5_000,
        "features": ["close", "volume"],
        "reward_type": "sharpe",
        "wf_splits": 2,
    }
)


def test_parse_params_ok():
    params = ModelScenario()._parse_params(VALID, {"close", "volume", "open"})
    assert params["algorithm"] == "ppo" and params["features"] == ["close", "volume"]


def test_parse_params_rejects_bad_algorithm_and_features():
    with pytest.raises(ValueError, match="algorithm"):
        ModelScenario()._parse_params(VALID.replace("ppo", "lstm"), {"close"})
    with pytest.raises(ValueError, match="features"):
        ModelScenario()._parse_params(VALID, {"close"})  # volume 列不存在


def test_parse_params_clamps_to_scene_limits():
    over = json.dumps({"algorithm": "sac", "total_timesteps": 999_999, "features": ["close"], "wf_splits": 9})
    params = ModelScenario()._parse_params(over, {"close"})
    assert params["total_timesteps"] == 20_000
    assert params["wf_splits"] == 3
    under = json.dumps({"algorithm": "sac", "total_timesteps": 5, "features": ["close"], "wf_splits": 1})
    params = ModelScenario()._parse_params(under, {"close"})
    assert params["total_timesteps"] == 1_000 and params["wf_splits"] == 2


def test_parse_params_rejects_non_object():
    # LLM 输出数组或纯文字时必须抛错触发 repair，不能静默取第一条
    with pytest.raises(ValueError):
        ModelScenario()._parse_params("[]", {"close"})
    with pytest.raises(ValueError):
        ModelScenario()._parse_params("没有 json", {"close"})


# ---------- evaluate：编排契约（stub 训练） ----------


def test_evaluate_builds_analysis_from_train_result(monkeypatch):
    configs = []

    class _StubRLService:
        def train(self, config):
            configs.append(config)
            return _wf_result()

    # evaluate 是函数内延迟 import，必须 patch 到源模块符号
    import services.rl_service as rl_module

    monkeypatch.setattr(rl_module, "RLService", _StubRLService)
    monkeypatch.setattr(rl_module, "RLTrainConfig", dict)

    analysis = ModelScenario().evaluate(VALID, {"BTC/USDT": _synth_ohlcv()}, CFG)
    train = analysis["train"]
    assert train["sharpe_ratio"] == 1.2 and train["trades"] == 8
    assert train["model_id"] == "rl_model_ppo_1"
    assert analysis["per_symbol"]["BTC/USDT"]["train"]["sharpe_ratio"] == 1.2
    assert analysis["last_fold"]["sharpe_ratio"] == 1.0
    # 无 train_factor：因子相关性去重在 loop 里自动跳过
    assert "train_factor" not in analysis


def test_evaluate_rejects_empty_raw_map():
    with pytest.raises(ValueError, match="行情"):
        ModelScenario().evaluate(VALID, {}, CFG)


# ---------- oos 口径（WF 最末折） ----------


def _analysis_with_last(last_sharpe: float, mean_sharpe: float = 1.2):
    return {
        "train": {"sharpe_ratio": mean_sharpe, "n_valid_folds": 2},
        "last_fold": {"sharpe_ratio": last_sharpe, "total_pnl": 1.0},
    }


def test_oos_flags():
    sc = ModelScenario()
    _, flag, _ = sc.oos_metrics(_analysis_with_last(-0.5), {"sharpe_ratio": 1.2}, {})
    assert flag == "sign_flip"
    _, flag, note = sc.oos_metrics(_analysis_with_last(0.2), {"sharpe_ratio": 1.2}, {})
    assert flag == "weak" and "last_fold" in note
    _, flag, note = sc.oos_metrics(_analysis_with_last(1.0), {"sharpe_ratio": 1.2}, {})
    assert flag == "ok" and "wf_mean" in note
    # 无有效折：不拦截（与 strategy 的 test 段未启用同口径）
    _, flag, _ = sc.oos_metrics({"train": {}}, {}, {})
    assert flag is None


# ---------- judge 硬门（用户拍板②A） ----------


def _judge(**kw):
    base = {"metrics": {"sharpe_ratio": 1.2, "trades": 8}, "oos_flag": "ok"}
    base.update(kw)
    return ModelScenario().judge(**base)


def test_judge_default_pass_and_fail():
    assert _judge()["decision"] is True
    assert _judge(metrics={"sharpe_ratio": 0.5, "trades": 8})["decision"] is False
    assert _judge(metrics={"sharpe_ratio": 1.2, "trades": 2})["decision"] is False
    assert _judge(oos_flag="sign_flip")["decision"] is False


def test_judge_cfg_overrides():
    out = _judge(cfg={"sharpe_floor": 1.5, "min_trades": 10}, metrics={"sharpe_ratio": 1.2, "trades": 8})
    assert out["decision"] is False
    assert out["gates"]["sharpe"]["floor"] == 1.5 and out["gates"]["trades"]["floor"] == 10


# ---------- promote（注册表入库，幂等） ----------


@pytest.fixture()
def promote_env(monkeypatch, tmp_path):
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[ResearchSession.__table__, ResearchTrial.__table__])
    db = sessionmaker(bind=eng)()

    @contextlib.contextmanager
    def fake_db():
        yield db

    registered: list[dict] = []

    class _StubRegistry:
        def register_model(self, *, name, model_path, metadata, metrics):
            registered.append({"name": name, "model_path": model_path, "metadata": metadata, "metrics": metrics})
            return "v1"

    monkeypatch.setattr(model_scenario_module, "ModelRegistryService", _StubRegistry)
    monkeypatch.setattr(model_scenario_module, "get_db_session", fake_db)
    return db, registered


def _seed_model_trial(db, **metric_extra):
    session = service.create_session(
        db, owner_id="u1", name="m-test", mode="deep", scenario="model", config={}, n_candidates=1
    )
    service.set_session_status(db, session, "running")
    metrics = {
        "sharpe_ratio": 1.2,
        "total_pnl": 50.0,
        "trades": 8,
        "win_rate": 0.5,
        "n_valid_folds": 2,
        "algorithm": "ppo",
        "total_timesteps": 5_000,
        "wf_splits": 2,
        "features": ["close", "volume"],
        "reward_type": "sharpe",
        "model_path": "/tmp/fake-model.zip",
        **metric_extra,
    }
    return service.add_trial(
        db,
        session.id,
        {
            "loop_idx": 1,
            "candidate_idx": 1,
            "status": "judged",
            "hypothesis": "动量 RL",
            "code": VALID,
            "code_hash": "stub",
            "metrics_json": json.dumps(metrics),
        },
    )


def test_promote_registers_and_records_trial(promote_env):
    db, registered = promote_env
    trial = _seed_model_trial(db)

    name = ModelScenario().promote(service.trial_to_dict(trial))
    assert name == f"rs_{trial.session_id}_{trial.id}"

    reg = registered[0]
    assert reg["model_path"] == "/tmp/fake-model.zip"
    assert reg["metadata"]["algorithm"] == "ppo"  # 来自 trial.code 解析回填的 train 段
    assert reg["metrics"]["sharpe_ratio"] == 1.2

    db.refresh(trial)
    assert trial.promoted_factor_name == name


def test_promote_is_idempotent(promote_env):
    db, registered = promote_env
    trial = _seed_model_trial(db)
    sc = ModelScenario()

    first = sc.promote(service.trial_to_dict(trial))
    second = sc.promote(service.trial_to_dict(service.get_trial_row(db, trial.id)))
    assert first == second and len(registered) == 1


def test_promote_rejects_missing_artifact(promote_env):
    db, _ = promote_env
    trial = _seed_model_trial(db, model_path="")
    with pytest.raises(ValueError, match="model_path"):
        ModelScenario().promote(service.trial_to_dict(trial))


# ---------- 真实训练 smoke（SB3 可用时执行） ----------


def test_evaluate_real_training_smoke():
    """最小配额真跑一遍：守评估链路与 RLTrainConfig 字段契约不受 stub 失真影响。"""
    pytest.importorskip("stable_baselines3")
    code = json.dumps(
        {"algorithm": "ppo", "total_timesteps": 300, "features": ["close"], "reward_type": "pnl", "wf_splits": 2}
    )
    analysis = ModelScenario().evaluate(code, {"BTC/USDT": _synth_ohlcv(120)}, CFG)
    assert analysis["train"]["n_valid_folds"] >= 1
    # 训练产物落盘且路径真实存在，promote 才有的可注册
    assert Path(str(analysis["train"]["model_path"])).exists()
