#!/usr/bin/env python3
"""
双向交易向量引擎
支持多空双向交易、做空风险控制、合约交易模式
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class PositionSide(Enum):
    """持仓方向"""
    NONE = 0
    LONG = 1
    SHORT = -1


@dataclass
class Position:
    """持仓信息"""
    side: PositionSide
    size: float
    entry_price: float
    margin: float
    unrealized_pnl: float = 0.0
    
    @property
    def is_long(self) -> bool:
        return self.side == PositionSide.LONG
    
    @property
    def is_short(self) -> bool:
        return self.side == PositionSide.SHORT
    
    @property
    def is_open(self) -> bool:
        return self.side != PositionSide.NONE and self.size > 0


@dataclass
class RiskControlConfig:
    """风险控制配置"""
    max_position_size: float = 1.0  # 最大仓位比例
    max_leverage: float = 1.0  # 最大杠杆倍数
    stop_loss_pct: float = 0.0  # 止损比例
    take_profit_pct: float = 0.0  # 止盈比例
    margin_call_threshold: float = 0.8  # 爆仓线
    maintenance_margin_rate: float = 0.005  # 维持保证金率


class BidirectionalVectorEngine:
    """
    双向交易向量引擎
    
    特性:
    1. 支持多空双向交易
    2. 支持杠杆交易
    3. 做空风险控制（爆仓、保证金）
    4. 合约交易模式支持
    """
    
    def __init__(self, risk_config: Optional[RiskControlConfig] = None):
        """
        初始化双向向量引擎
        
        Args:
            risk_config: 风险控制配置
        """
        self.risk_config = risk_config or RiskControlConfig()
        self.position: Position = Position(PositionSide.NONE, 0.0, 0.0, 0.0)
        self.cash: float = 0.0
        self.margin_used: float = 0.0
        self.trades: list = []
        
    def run_backtest(
        self,
        price: np.ndarray,
        long_entries: np.ndarray,
        long_exits: np.ndarray,
        short_entries: np.ndarray,
        short_exits: np.ndarray,
        init_cash: float = 100000.0,
        fees: float = 0.001,
        slippage: float = 0.0001,
        leverage: float = 1.0,
        enable_short: bool = True
    ) -> Dict[str, Any]:
        """
        运行双向回测
        
        Args:
            price: 价格数组
            long_entries: 多头入场信号
            long_exits: 多头出场信号
            short_entries: 空头入场信号
            short_exits: 空头出场信号
            init_cash: 初始资金
            fees: 手续费率
            slippage: 滑点
            leverage: 杠杆倍数
            enable_short: 是否启用做空
        
        Returns:
            Dict: 回测结果
        """
        n = len(price)
        self.cash = init_cash
        self.position = Position(PositionSide.NONE, 0.0, 0.0, 0.0)
        self.trades = []
        
        # 记录历史
        cash_history = np.zeros(n)
        position_history = np.zeros(n)
        margin_history = np.zeros(n)
        equity_history = np.zeros(n)
        
        for i in range(n):
            current_price = price[i]
            
            # 更新持仓盈亏
            self._update_position_pnl(current_price)
            
            # 检查风险控制
            if self._check_risk_control(current_price):
                # 触发风险控制，强制平仓
                self._force_close_position(current_price, i, fees, slippage)
            
            # 处理信号
            if long_entries[i] and self.position.side != PositionSide.LONG:
                # 多头入场信号
                self._open_long_position(current_price, i, fees, slippage, leverage)
            
            elif long_exits[i] and self.position.side == PositionSide.LONG:
                # 多头出场信号
                self._close_long_position(current_price, i, fees, slippage)
            
            elif enable_short and short_entries[i] and self.position.side != PositionSide.SHORT:
                # 空头入场信号
                self._open_short_position(current_price, i, fees, slippage, leverage)
            
            elif enable_short and short_exits[i] and self.position.side == PositionSide.SHORT:
                # 空头出场信号
                self._close_short_position(current_price, i, fees, slippage)
            
            # 记录历史
            cash_history[i] = self.cash
            position_history[i] = self.position.size if self.position.is_long else -self.position.size
            margin_history[i] = self.margin_used
            equity_history[i] = self._calculate_equity(current_price)
        
        # 计算指标
        final_equity = equity_history[-1]
        total_return = (final_equity - init_cash) / init_cash * 100
        max_drawdown = self._calculate_max_drawdown(equity_history)
        sharpe = self._calculate_sharpe_ratio(equity_history)
        
        return {
            'Start Value': init_cash,
            'Equity Final [$]': final_equity,
            'Return [%]': total_return,
            'Max. Drawdown [%]': max_drawdown,
            'Sharpe Ratio': sharpe,
            '# Trades': len(self.trades),
            'Win Rate [%]': self._calculate_win_rate(),
            '_cash_history': cash_history,
            '_position_history': position_history,
            '_equity_history': equity_history,
            '_trades': self.trades,
        }
    
    def _open_long_position(
        self,
        price: float,
        step: int,
        fees: float,
        slippage: float,
        leverage: float
    ):
        """开多仓"""
        # 如果有空仓，先平空仓
        if self.position.is_short:
            self._close_short_position(price, step, fees, slippage)
        
        # 计算开仓数量
        exec_price = price * (1 + slippage)
        available_cash = self.cash * self.risk_config.max_position_size
        margin = available_cash / leverage
        position_size = (available_cash / exec_price) * leverage
        
        # 检查资金
        if self.cash < margin:
            logger.warning(f"资金不足，无法开多仓: 需要保证金={margin:.2f}, 可用={self.cash:.2f}")
            return
        
        # 开仓
        self.cash -= margin
        self.margin_used += margin
        self.position = Position(
            side=PositionSide.LONG,
            size=position_size,
            entry_price=exec_price,
            margin=margin
        )
        
        trade_fees = position_size * exec_price * fees
        
        self.trades.append({
            'step': step,
            'type': 'entry_long',
            'price': exec_price,
            'size': position_size,
            'margin': margin,
            'fees': trade_fees,
            'leverage': leverage,
        })
        
        logger.debug(f"开多仓: 价格={exec_price:.2f}, 数量={position_size:.4f}, 保证金={margin:.2f}")
    
    def _close_long_position(
        self,
        price: float,
        step: int,
        fees: float,
        slippage: float
    ):
        """平多仓"""
        if not self.position.is_long:
            return
        
        exec_price = price * (1 - slippage)
        position_value = self.position.size * exec_price
        trade_fees = position_value * fees
        
        # 计算盈亏
        pnl = (exec_price - self.position.entry_price) * self.position.size - trade_fees
        
        # 平仓
        self.cash += self.position.margin + pnl
        self.margin_used -= self.position.margin
        
        self.trades.append({
            'step': step,
            'type': 'exit_long',
            'price': exec_price,
            'size': self.position.size,
            'pnl': pnl,
            'fees': trade_fees,
        })
        
        logger.debug(f"平多仓: 价格={exec_price:.2f}, 盈亏={pnl:.2f}")
        
        self.position = Position(PositionSide.NONE, 0.0, 0.0, 0.0)
    
    def _open_short_position(
        self,
        price: float,
        step: int,
        fees: float,
        slippage: float,
        leverage: float
    ):
        """开空仓（做空）"""
        # 如果有多仓，先平多仓
        if self.position.is_long:
            self._close_long_position(price, step, fees, slippage)
        
        # 计算开仓数量
        exec_price = price * (1 - slippage)
        available_cash = self.cash * self.risk_config.max_position_size
        margin = available_cash / leverage
        position_size = (available_cash / exec_price) * leverage
        
        # 检查资金
        if self.cash < margin:
            logger.warning(f"资金不足，无法开空仓: 需要保证金={margin:.2f}, 可用={self.cash:.2f}")
            return
        
        # 开仓（做空）
        self.cash -= margin
        self.margin_used += margin
        self.position = Position(
            side=PositionSide.SHORT,
            size=position_size,
            entry_price=exec_price,
            margin=margin
        )
        
        trade_fees = position_size * exec_price * fees
        
        self.trades.append({
            'step': step,
            'type': 'entry_short',
            'price': exec_price,
            'size': position_size,
            'margin': margin,
            'fees': trade_fees,
            'leverage': leverage,
        })
        
        logger.debug(f"开空仓: 价格={exec_price:.2f}, 数量={position_size:.4f}, 保证金={margin:.2f}")
    
    def _close_short_position(
        self,
        price: float,
        step: int,
        fees: float,
        slippage: float
    ):
        """平空仓（平做空）"""
        if not self.position.is_short:
            return
        
        exec_price = price * (1 + slippage)
        position_value = self.position.size * exec_price
        trade_fees = position_value * fees
        
        # 计算盈亏（做空：价格下跌盈利）
        pnl = (self.position.entry_price - exec_price) * self.position.size - trade_fees
        
        # 平仓
        self.cash += self.position.margin + pnl
        self.margin_used -= self.position.margin
        
        self.trades.append({
            'step': step,
            'type': 'exit_short',
            'price': exec_price,
            'size': self.position.size,
            'pnl': pnl,
            'fees': trade_fees,
        })
        
        logger.debug(f"平空仓: 价格={exec_price:.2f}, 盈亏={pnl:.2f}")
        
        self.position = Position(PositionSide.NONE, 0.0, 0.0, 0.0)
    
    def _update_position_pnl(self, current_price: float):
        """更新持仓盈亏"""
        if not self.position.is_open:
            return
        
        if self.position.is_long:
            self.position.unrealized_pnl = (current_price - self.position.entry_price) * self.position.size
        else:
            self.position.unrealized_pnl = (self.position.entry_price - current_price) * self.position.size
    
    def _check_risk_control(self, current_price: float) -> bool:
        """检查风险控制条件"""
        if not self.position.is_open:
            return False
        
        # 检查止损
        if self.risk_config.stop_loss_pct > 0:
            loss_pct = abs(self.position.unrealized_pnl) / (self.position.size * self.position.entry_price)
            if loss_pct >= self.risk_config.stop_loss_pct:
                logger.warning(f"触发止损: 亏损比例={loss_pct:.2%}")
                return True
        
        # 检查爆仓（做空时价格上涨可能爆仓）
        if self.position.is_short:
            price_change = (current_price - self.position.entry_price) / self.position.entry_price
            if price_change >= self.risk_config.margin_call_threshold:
                logger.warning(f"触发爆仓: 价格变化={price_change:.2%}")
                return True
        
        return False
    
    def _force_close_position(self, price: float, step: int, fees: float, slippage: float):
        """强制平仓"""
        if self.position.is_long:
            self._close_long_position(price, step, fees, slippage)
        elif self.position.is_short:
            self._close_short_position(price, step, fees, slippage)
    
    def _calculate_equity(self, current_price: float) -> float:
        """计算当前权益"""
        self._update_position_pnl(current_price)
        return self.cash + self.margin_used + self.position.unrealized_pnl
    
    def _calculate_max_drawdown(self, equity_history: np.ndarray) -> float:
        """计算最大回撤"""
        peak = np.maximum.accumulate(equity_history)
        drawdown = (equity_history - peak) / peak
        return np.abs(np.min(drawdown)) * 100
    
    def _calculate_sharpe_ratio(self, equity_history: np.ndarray) -> float:
        """计算夏普比率"""
        returns = np.diff(equity_history) / equity_history[:-1]
        if len(returns) < 2:
            return 0.0
        std = np.std(returns, ddof=1)
        if std == 0 or np.isnan(std):
            return 0.0
        return np.mean(returns) / std * np.sqrt(252)
    
    def _calculate_win_rate(self) -> float:
        """计算胜率"""
        completed_trades = [t for t in self.trades if t['type'].startswith('exit')]
        if not completed_trades:
            return 0.0
        wins = sum(1 for t in completed_trades if t.get('pnl', 0) > 0)
        return wins / len(completed_trades) * 100
