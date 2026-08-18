"""自定义奖励函数

所有奖励函数签名统一：
    (prev_portfolio, current_portfolio, action, step, info) -> float

TradingEnv 内置奖励: pnl / sharpe / sortino
自定义奖励: 通过 reward_fn 参数传入 TradingEnvWrapper
"""

import numpy as np


def pnl_with_trade_penalty(
    prev_portfolio: float,
    current_portfolio: float,
    action: int,
    step: int,
    info: dict,
    trade_penalty: float = 5.0,
) -> float:
    """PnL + 交易惩罚

    每笔交易扣 trade_penalty 分，减少过度交易
    """
    pnl = current_portfolio - prev_portfolio
    cost = info.get("transaction_costs", 0)
    # 归一化 PnL（按初始资金百分比）
    initial = info.get("initial_capital", 100_000)
    reward = (pnl / initial) * 100

    # 交易惩罚（每次交易扣分）
    if action != 0:
        reward -= trade_penalty * (cost / initial * 100)

    return reward


def risk_adjusted_reward(
    prev_portfolio: float,
    current_portfolio: float,
    action: int,
    step: int,
    info: dict,
    dd_penalty: float = 2.0,
    trade_penalty: float = 3.0,
) -> float:
    """风险调整奖励：收益 - 回撤惩罚 - 交易惩罚

    - 收益项：对数收益率
    - 回撤惩罚：当前回撤越大惩罚越重
    - 交易惩罚：每次交易扣分
    """
    initial = info.get("initial_capital", 100_000)
    pnl = current_portfolio - initial

    # 对数收益率（更稳定）
    reward = np.log(current_portfolio / initial) * 100 if current_portfolio > 0 and initial > 0 else -10.0

    # 回撤惩罚（基于 PnL 负值）
    if pnl < 0:
        reward -= abs(pnl / initial) * 100 * dd_penalty

    # 交易惩罚
    if action != 0:
        cost = info.get("transaction_costs", 0)
        reward -= trade_penalty * (cost / initial * 100)

    return reward


def hold_friendly_reward(
    prev_portfolio: float,
    current_portfolio: float,
    action: int,
    step: int,
    info: dict,
    hold_bonus: float = 0.01,
    trade_penalty: float = 2.0,
    loss_penalty: float = 1.5,
) -> float:
    """鼓励持仓不动的奖励

    - hold 动作给小额正奖励
    - 交易扣分
    - 亏损时加倍惩罚
    """
    pnl = current_portfolio - prev_portfolio
    initial = info.get("initial_capital", 100_000)

    # 基础 PnL 奖励
    reward = (pnl / initial) * 100

    # hold 奖励
    if action == 0:
        reward += hold_bonus

    # 交易惩罚
    if action != 0:
        cost = info.get("transaction_costs", 0)
        reward -= trade_penalty * (cost / initial * 100)

    # 亏损加倍惩罚
    if pnl < 0:
        reward *= loss_penalty

    return reward


# 奖励函数注册表
REWARD_FUNCTIONS = {
    "pnl_with_trade_penalty": pnl_with_trade_penalty,
    "risk_adjusted": risk_adjusted_reward,
    "hold_friendly": hold_friendly_reward,
}
