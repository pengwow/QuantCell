# -*- coding: utf-8 -*-
"""RL 数据模型"""

from pydantic import BaseModel, Field


class RLTrainConfig(BaseModel):
    """RL 训练配置"""
    symbol: str = Field(..., description="交易对符号，如 BTCUSDT")
    algorithm: str = Field(default="ppo", description="算法 (ppo/sac/a2c)")
    timesteps: int = Field(default=10_000, description="训练步数")
    learning_rate: float = Field(default=3e-4, description="学习率")
    action_space: str = Field(default="discrete", description="动作空间 (discrete/continuous)")
    reward: str = Field(default="pnl", description="奖励函数 (pnl/sharpe/sortino)")
    initial_capital: float = Field(default=100_000, description="初始资金")
    transaction_cost: float = Field(default=0.001, description="交易费率")
    interval: str = Field(default="1h", description="K线周期")
    lookback_days: int = Field(default=90, description="回看天数")
    output_name: str | None = Field(default=None, description="模型输出名称")
