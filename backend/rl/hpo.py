# -*- coding: utf-8 -*-
"""PPO 超参数优化 — 使用 Optuna

搜索空间：
- learning_rate: [1e-5, 1e-3]
- n_steps: [512, 2048, 4096]
- batch_size: [32, 64, 128, 256]
- n_epochs: [3, 5, 10]
- gamma: [0.95, 0.99, 0.999]
- gae_lambda: [0.9, 0.95, 0.98]
- clip_range: [0.1, 0.2, 0.3]
- ent_coef: [0.0, 0.01, 0.02]

使用：python -m rl.hpo --symbol BTCUSDT --trials 30 --timesteps 10000
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def create_env(df, initial_capital=100_000, transaction_cost=0.001, warmup=20):
    """创建自定义交易环境"""
    import gymnasium as gym

    class TradingEnv(gym.Env):
        def __init__(self):
            super().__init__()
            self._df = df.values
            self._close_idx = list(df.columns).index("Close")
            self._init = initial_capital
            self._tc = transaction_cost
            self._warmup = warmup
            self.action_space = gym.spaces.Discrete(3)
            self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(12,), dtype=np.float32)
            self._reset()

        def _reset(self):
            self._step = self._warmup
            self._pos = 0
            self._rets = [0.0] * self._warmup
            self._lc = self._df[self._warmup - 1, self._close_idx]
            self._port = self._init
            self._pp = self._init
            self._trades = 0
            self._entry = 0.0
            self._hold_count = 0

        def _obs(self):
            c = self._df[self._step, self._close_idx]
            r = (c - self._lc) / self._lc if self._lc > 0 else 0
            self._lc = c
            self._rets.append(r)
            if len(self._rets) > 50:
                self._rets.pop(0)
            vol = np.std(self._rets[-20:]) if len(self._rets) > 1 else 0
            sma = np.mean(self._rets[-10:]) if len(self._rets) >= 10 else 0
            rsi = 50.0
            if len(self._rets) > 14:
                g = np.array(self._rets[-14:])
                up = np.mean(g[g > 0]) if np.any(g > 0) else 0
                dn = -np.mean(g[g < 0]) if np.any(g < 0) else 0
                rsi = 100 - 100 / (1 + up / dn) if dn > 0 else (100 if up > 0 else 50)
            return np.array([r, vol, sma, sma, sma, (rsi - 50) / 50, 0, 0, 0, 0, vol, r], dtype=np.float32)

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self._reset()
            return self._obs(), {}

        def step(self, action):
            c = self._df[self._step, self._close_idx]
            pc = self._df[self._step - 1, self._close_idx]
            chg = c - pc

            if action == 1 and self._pos == 0:
                self._pos = 1
                self._entry = c
                self._port -= c * 0.1 * self._tc
                self._trades += 1
                self._hold_count = 0
            elif action == 2 and self._pos == 1:
                profit = (c - self._entry) * (self._port * 0.1 / self._entry)
                fee = c * (self._port * 0.1 / c) * self._tc
                self._port += profit - fee
                self._pos = 0
                self._trades += 1

            if self._pos == 1:
                self._port += chg * (self._port * 0.1 / self._entry)
                self._hold_count += 1

            pnl = (self._port - self._pp) / self._init * 100
            trade_bonus = 0.1 if action != 0 else 0
            hold_penalty = -0.05 * self._hold_count if self._hold_count > 20 else 0
            reward = pnl + trade_bonus + hold_penalty
            self._pp = self._port
            self._step += 1

            done = self._step >= len(self._df)
            trunc = self._port <= 0
            obs = self._obs() if not done else np.zeros(12, dtype=np.float32)
            return obs, reward, done, trunc, {"portfolio_value": self._port, "trades": self._trades}

    return TradingEnv()


def objective(trial, df_train, df_val, n_timesteps):
    """Optuna 目标函数"""
    from stable_baselines3 import PPO

    # 超参数搜索空间
    learning_rate = trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True)
    n_steps = trial.suggest_categorical("n_steps", [512, 1024, 2048, 4096])
    batch_size = trial.suggest_categorical("batch_size", [32, 64, 128, 256])
    n_epochs = trial.suggest_categorical("n_epochs", [3, 5, 10])
    gamma = trial.suggest_float("gamma", 0.95, 0.999, step=0.01)
    gae_lambda = trial.suggest_float("gae_lambda", 0.9, 0.98, step=0.01)
    clip_range = trial.suggest_float("clip_range", 0.1, 0.3, step=0.05)
    ent_coef = trial.suggest_float("ent_coef", 0.0, 0.02, step=0.005)

    # 创建训练环境
    env = create_env(df_train)

    try:
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            ent_coef=ent_coef,
            verbose=0,
            device="cpu",
        )
        model.learn(total_timesteps=n_timesteps)

        # 在验证集上评估
        val_env = create_env(df_val)
        obs, _ = val_env.reset()
        total_reward = 0
        for _ in range(len(df_val)):
            a, _ = model.predict(obs, deterministic=True)
            obs, r, term, trunc, info = val_env.step(a)
            total_reward += r
            if term or trunc:
                break

        portfolio = info.get("portfolio_value", 100_000)
        trades = info.get("trades", 0)
        sharpe = total_reward / (np.std([total_reward]) + 1e-8)

        # 综合评分：收益率 + 夏普 - 过度交易惩罚
        pnl_pct = (portfolio - 100_000) / 100_000 * 100
        trade_penalty = -trades * 0.1 if trades > 50 else 0
        score = pnl_pct + trade_penalty

        return score

    except Exception as e:
        logger.error(f"Trial failed: {e}")
        return -1000


def run_hpo(symbol: str, n_trials: int = 30, n_timesteps: int = 10000, output_dir: str = None):
    """运行超参数优化"""
    import optuna
    from rl.service import RLService

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # 加载数据
    svc = RLService()
    df = svc._fetch_market_data(symbol, "15m", 90)

    # 分割训练/验证集（80/20）
    split = int(len(df) * 0.8)
    df_train = df.head(split)
    df_val = df.tail(len(df) - split)

    print(f"数据: 训练 {len(df_train)} 根, 验证 {len(df_val)} 根")
    print(f"超参数优化: {n_trials} trials, 每 trial {n_timesteps} 步")

    # 创建 Optuna study
    study = optuna.create_study(
        direction="maximize",
        study_name=f"ppo_{symbol}",
        storage=f"sqlite:///{output_dir or 'data'}/hpo_study.db" if output_dir else None,
        load_if_exists=True,
    )

    # 运行优化
    start = time.time()
    study.optimize(
        lambda trial: objective(trial, df_train, df_val, n_timesteps),
        n_trials=n_trials,
        show_progress_bar=True,
    )
    elapsed = time.time() - start

    # 输出结果
    print(f"\n{'='*60}")
    print(f"超参数优化完成 ({elapsed:.1f}s)")
    print(f"{'='*60}")
    print(f"最佳得分: {study.best_value:.4f}")
    print(f"最佳参数:")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")

    # 用最佳参数训练最终模型
    print(f"\n使用最佳参数训练最终模型...")
    env = create_env(df_train)
    from stable_baselines3 import PPO

    bp = study.best_params
    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=bp["learning_rate"],
        n_steps=bp["n_steps"],
        batch_size=bp["batch_size"],
        n_epochs=bp["n_epochs"],
        gamma=bp["gamma"],
        gae_lambda=bp["gae_lambda"],
        clip_range=bp["clip_range"],
        ent_coef=bp["ent_coef"],
        verbose=1,
        device="cpu",
    )
    model.learn(total_timesteps=n_timesteps * 2)

    # 保存模型
    output_path = Path(output_dir or "data/rl_models") / f"{symbol}_ppo_hpo.zip"
    model.save(str(output_path))
    print(f"模型已保存: {output_path}")

    # 最终评估
    val_env = create_env(df_val)
    obs, _ = val_env.reset()
    for _ in range(len(df_val)):
        a, _ = model.predict(obs, deterministic=True)
        obs, r, term, trunc, info = val_env.step(a)
        if term or trunc:
            break

    print(f"\n最终评估:")
    print(f"  PnL: ${info['portfolio_value'] - 100_000:.2f}")
    print(f"  Trades: {info['trades']}")

    return study.best_params, model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPO 超参数优化")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对")
    parser.add_argument("--trials", type=int, default=30, help="优化轮数")
    parser.add_argument("--timesteps", type=int, default=10000, help="每轮训练步数")
    parser.add_argument("--output", default=None, help="输出目录")
    args = parser.parse_args()

    run_hpo(args.symbol, args.trials, args.timesteps, args.output)
