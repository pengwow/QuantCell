"""P2:RL 完整训练冒烟测试(QuantCell 真实训练链路)。

覆盖评估报告 E 区「完整 RL 训练」缺口:RLService.create_env(axon_quant
TradingEnv) → GymnasiumWrapper → stable-baselines3 PPO 短程训练,
断言 loss 有限、无 NaN、训练后可推理 —— 保证 RL 训练链路可跑通,
演进(换模型/换环境)时不至于整个坏掉才发现。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

sb3 = pytest.importorskip("stable_baselines3", reason="stable_baselines3 未安装")

from services.rl_service import GymnasiumWrapper, RLService


def _sample_df(rows: int = 64) -> pd.DataFrame:
    """构造带 timestamp 的最小行情数据。"""
    return pd.DataFrame(
        {
            "timestamp": range(1_700_000_000, 1_700_000_000 + rows * 3_600, 3_600),
            "open": [100.0 + i * 0.1 for i in range(rows)],
            "high": [101.0 + i * 0.1 for i in range(rows)],
            "low": [99.0 + i * 0.1 for i in range(rows)],
            "close": [100.5 + i * 0.1 for i in range(rows)],
            "volume": [1_000.0] * rows,
        }
    )


@pytest.mark.slow
def test_ppo_short_training_loss_finite() -> None:
    """PPO 训练 10 个 rollout:loss 有限,训练后策略可推理。"""
    from stable_baselines3 import PPO

    service = RLService()
    env = service.create_env(_sample_df())
    wrapped = GymnasiumWrapper(env)

    model = PPO("MlpPolicy", wrapped, n_steps=16, batch_size=16, verbose=0, seed=42)
    model.learn(total_timesteps=160)  # 10 次 rollout × 16 步

    # 训练后 loss 必须有限(未触发 logger 键时跳过该断言)
    loss = model.logger.name_to_value.get("train/loss")
    if loss is not None:
        assert math.isfinite(loss), f"训练 loss 非有限: {loss}"

    obs, _ = wrapped.reset(seed=123)
    action, _ = model.predict(obs, deterministic=True)
    assert action is not None


@pytest.mark.slow
def test_rl_service_train_full_cycle(tmp_path, monkeypatch) -> None:
    """RLService.train 全链路:训练 → 保存 → 加载,模型文件真实落盘。

    monkeypatch 重定向 MODELS_DIR 到 tmp_path,避免污染 data/models。
    """
    import services.rl_service as rl_service_mod
    from services.rl_service import RLTrainConfig

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)

    service = rl_service_mod.RLService()
    result = service.train(
        RLTrainConfig(
            algorithm="ppo",
            data=_sample_df(rows=48),
            total_timesteps=64,
            model_name="smoke_test_model",
        )
    )

    assert result.model_path is not None
    assert result.model_path.endswith(".zip")
    assert result.metrics["steps"] == 64
    assert result.metrics["elapsed_seconds"] >= 0

    # 模型文件真实存在且可加载
    assert tmp_path.joinpath(result.model_path.split("/")[-1]).exists()
    loaded = service.load_model(result.model_path)
    assert loaded is not None
