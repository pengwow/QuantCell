"""
结果格式化服务模块（基于 axond 体系）

负责将回测引擎的原始结果转换为QuantCell标准格式，
包括单品种和多品种场景的结果格式化、绩效指标计算等。
支持 axond 回测引擎和事件驱动引擎的结果格式化。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from datetime import datetime

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class ResultFormatterService:
    """
    回测结果格式化服务

    提供统一的结果格式化接口，支持：
    - 单品种事件驱动结果格式化
    - 多品种事件驱动结果格式化
    - 时间周期转换
    - 绩效指标计算

    使用示例：
        formatted = ResultFormatterService.format_event_results(
            results=raw_results,
            symbol="BTCUSDT",
            timeframe="1h",
            strategy_name="sma_cross"
        )
    """

    @staticmethod
    def convert_timeframe_to_event(timeframe: str) -> str:
        """
        将时间周期转换为事件驱动引擎格式

        Args:
            timeframe: 时间周期字符串（如 1h, 15m, 1d）

        Returns:
            str: 事件驱动引擎格式（如 1-HOUR, 15-MINUTE, 1-DAY）
        """
        mapping = {
            "1m": "1-MINUTE",
            "3m": "3-MINUTE",
            "5m": "5-MINUTE",
            "15m": "15-MINUTE",
            "30m": "30-MINUTE",
            "1h": "1-HOUR",
            "2h": "2-HOUR",
            "4h": "4-HOUR",
            "6h": "6-HOUR",
            "8h": "8-HOUR",
            "12h": "12-HOUR",
            "1d": "1-DAY",
            "3d": "3-DAY",
            "1w": "1-WEEK",
            "1M": "1-MONTH",
        }

        return mapping.get(timeframe, "1-HOUR")

    @staticmethod
    def format_event_results(results: dict, symbol: str, timeframe: str, strategy_name: str) -> dict:
        """
        格式化事件驱动回测结果为QuantCell标准格式（单品种版本）

        Args:
            results: 事件驱动回测原始结果
            symbol: 品种符号
            timeframe: 时间周期
            strategy_name: 策略名称

        Returns:
            dict: 格式化的回测结果
        """
        key = f"{symbol}_{timeframe}"

        formatted = {
            key: {
                "symbol": symbol,
                "timeframe": timeframe,
                "metrics": results.get("metrics", {}),
                "trades": results.get("trades", []),
                "positions": results.get("positions", []),
                "equity_curve": results.get("equity_curve", []),
            }
        }

        # 添加全局账户信息
        formatted["account"] = results.get("account", {})

        # 添加投资组合汇总（单品种时与品种结果相同）
        formatted["portfolio"] = {
            "metrics": results.get("metrics", {}),
            "trades": results.get("trades", []),
            "equity_curve": results.get("equity_curve", []),
        }

        # 添加元数据
        now = datetime.now()
        formatted["_meta"] = {
            "engine": "event",
            "strategy": strategy_name,
            "timestamp": int(now.timestamp()),
            "formatted_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return formatted

    @staticmethod
    def format_event_results_multi(
        results: dict,
        symbols: list[str],
        timeframe: str,
        strategy_name: str,
        instruments: dict,
    ) -> dict:
        """
        格式化多品种事件驱动回测结果（修复版）

        核心改进：
        1. 从 results['trades'] 和 results['positions'] 提取数据（而非 portfolio）
        2. 使用字典的 'symbol' 字段进行过滤（修复 hasattr 问题）
        3. 为每个品种独立计算 metrics

        Args:
            results: 事件驱动回测原始结果（来自 EventDrivenBacktestEngine._process_results()）
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称
            instruments: Instrument映射

        Returns:
            dict: 格式化的多品种回测结果
        """
        formatted = {}

        # ✅ 从正确的位置提取全局数据
        all_trades = results.get("trades", [])  # 来自 _process_results()
        all_positions = results.get("positions", [])  # 来自 _process_results()
        account = results.get("account", {})  # 账户信息
        global_metrics = results.get("metrics", {})  # 全局指标
        equity_curve = results.get("equity_curve", [])  # 权益曲线

        logger.info(f"[format_event_results_multi] 开始格式化，共 {len(symbols)} 个品种")
        logger.info(f"[format_event_results_multi] 总交易数: {len(all_trades)}, 总持仓数: {len(all_positions)}")

        # 为每个品种提取单独结果
        for symbol in symbols:
            key = f"{symbol}_{timeframe}"

            # ✅ 正确过滤：使用字典的 'symbol' 字段（修复 hasattr 问题）
            symbol_trades = [t for t in all_trades if isinstance(t, dict) and t.get("symbol") == symbol]
            symbol_positions = [p for p in all_positions if isinstance(p, dict) and p.get("symbol") == symbol]

            logger.debug(f"[{key}] 过滤结果: trades={len(symbol_trades)}, positions={len(symbol_positions)}")

            # ✅ 为每个品种独立计算 metrics
            symbol_metrics = ResultFormatterService.calculate_symbol_metrics(
                trades=symbol_trades, positions=symbol_positions, account=account
            )

            # ✅ 构建该品种的权益曲线（基于该品种的持仓变化）
            symbol_equity_curve = ResultFormatterService._extract_symbol_equity_curve(
                global_equity_curve=equity_curve,
                symbol=symbol,
                positions=symbol_positions,
            )

            formatted[key] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "metrics": symbol_metrics,  # ✅ 独立计算
                "trades": symbol_trades,  # ✅ 已正确过滤
                "positions": symbol_positions,  # ✅ 已正确过滤
                "equity_curve": symbol_equity_curve,  # ✅ 独立提取或使用全局
            }

        # 添加全局账户信息
        formatted["account"] = account

        # 添加投资组合汇总（包含所有品种的数据）
        formatted["portfolio"] = {
            "metrics": global_metrics,  # 使用全局计算的指标
            "trades": all_trades,  # 所有交易
            "positions": all_positions,  # 所有持仓
            "equity_curve": equity_curve,  # 全局权益曲线
        }

        # 添加元数据
        now = datetime.now()
        formatted["_meta"] = {
            "engine": "event",
            "strategy": strategy_name,
            "symbols_count": len(symbols),
            "timestamp": int(now.timestamp()),
            "formatted_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

        logger.info(f"[ResultFormatterService] 多品种结果格式化完成，共 {len(symbols)} 个品种")

        return formatted

    @staticmethod
    def _extract_symbol_equity_curve(global_equity_curve: list[dict], symbol: str, positions: list[dict]) -> list[dict]:
        """
        提取单个品种的权益曲线

        如果无法按品种分离，则返回全局权益曲线（因为所有品种共享同一账户）

        Args:
            global_equity_curve: 全局权益曲线
            symbol: 品种名称
            positions: 该品种的持仓列表

        Returns:
            List[Dict]: 权益曲线数据
        """
        # 当前实现：返回全局权益曲线
        # TODO: 未来可以基于持仓价值变化计算每个品种的贡献
        return global_equity_curve

    @staticmethod
    def calculate_symbol_metrics(trades, positions, account):
        """
        计算单品种绩效指标（支持字典和对象两种格式）

        Args:
            trades: 交易记录列表（字典或对象）
            positions: 持仓记录列表
            account: 账户信息（字典或对象）

        Returns:
            dict: 绩效指标字典
        """

        # ✅ 辅助函数：安全获取属性/键值（支持 dict 和 object）
        def get_attr_or_get(obj, attr, default=0):
            """安全获取属性值，兼容字典和对象"""
            if isinstance(obj, dict):
                return obj.get(attr, default)
            else:
                return getattr(obj, attr, default)

        metrics = {}

        try:
            if not trades or len(trades) == 0:
                return {
                    "total_return": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                    "total_pnl": 0.0,
                }

            # ✅ 使用安全的属性访问方法
            total_pnl = sum(get_attr_or_get(t, "pnl", get_attr_or_get(t, "realized_pnl", 0)) for t in trades)
            winning_trades = [t for t in trades if (get_attr_or_get(t, "pnl", 0) > 0)]
            losing_trades = [t for t in trades if (get_attr_or_get(t, "pnl", 0) <= 0)]

            win_rate = len(winning_trades) / len(trades) * 100 if trades else 0

            total_wins = sum(get_attr_or_get(t, "pnl", 0) for t in winning_trades)
            total_losses = abs(sum(get_attr_or_get(t, "pnl", 0) for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

            # ✅ 使用安全的属性访问方法
            initial_balance = get_attr_or_get(
                account,
                "starting_balance",
                get_attr_or_get(account, "initial_balance", 10000),
            )
            final_balance = get_attr_or_get(account, "balance", initial_balance) + total_pnl
            total_return = ((final_balance - initial_balance) / initial_balance) * 100

            metrics = {
                "total_return": round(total_return, 2),
                "total_pnl": round(total_pnl, 8),  # PnL保留8位精度
                "total_trades": len(trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": round(win_rate, 2),
                "profit_factor": round(profit_factor, 4),  # 盈亏比保留4位
            }

        except Exception as e:
            logger.warning(f"[ResultFormatterService] 计算单品种指标失败: {e}")

        return metrics

    @staticmethod
    def calculate_portfolio_metrics(trades, positions, equity_curve, symbols, account):
        """
        计算组合级别绩效指标

        Args:
            trades: 所有交易记录
            positions: 所有持仓记录
            equity_curve: 权益曲线数据
            symbols: 品种列表
            account: 账户信息

        Returns:
            dict: 组合级别绩效指标
        """
        from statistics import mean

        metrics = {}

        try:
            if not trades or len(trades) == 0:
                return {
                    "total_return": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "avg_trade_return": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                }

            total_pnl = sum(getattr(t, "pnl", getattr(t, "realized_pnl", 0)) for t in trades)
            winning_trades = [t for t in trades if (getattr(t, "pnl", 0) > 0)]
            losing_trades = [t for t in trades if (getattr(t, "pnl", 0) <= 0)]

            win_rate = len(winning_trades) / len(trades) * 100 if trades else 0

            trade_returns = [getattr(t, "pnl", 0) for t in trades]
            avg_trade = mean(trade_returns) if trade_returns else 0

            total_wins = sum(getattr(t, "pnl", 0) for t in winning_trades)
            total_losses = abs(sum(getattr(t, "pnl", 0) for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

            initial_balance = getattr(account, "starting_balance", 10000)
            final_balance = getattr(account, "balance", initial_balance) + total_pnl
            total_return = ((final_balance - initial_balance) / initial_balance) * 100

            # 计算最大回撤
            max_drawdown = 0.0
            if equity_curve and len(equity_curve) > 1:
                peak = equity_curve[0].get("Equity", equity_curve[0].get("equity", initial_balance))
                for eq in equity_curve[1:]:
                    eq_val = eq.get("Equity", eq.get("equity", 0))
                    if eq_val > peak:
                        peak = eq_val
                    drawdown = (peak - eq_val) / peak * 100 if peak > 0 else 0
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown

            # 计算夏普比率（简化版）
            sharpe_ratio = 0.0
            if trade_returns and len(trade_returns) > 1:
                avg_return = mean(trade_returns)
                std_return = (sum((x - avg_return) ** 2 for x in trade_returns) / (len(trade_returns) - 1)) ** 0.5
                if std_return > 0:
                    risk_free_rate = 0.02 / 252  # 假设年化无风险利率2%，日化
                    sharpe_ratio = (avg_return - risk_free_rate) / std_return

            metrics = {
                "total_return": round(total_return, 2),
                "total_pnl": round(total_pnl, 2),
                "total_trades": len(trades),
                "symbols_count": len(symbols),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": round(win_rate, 2),
                "avg_trade_return": round(avg_trade, 4),
                "profit_factor": round(profit_factor, 2),
                "max_drawdown": round(max_drawdown, 2),
                "sharpe_ratio": round(sharpe_ratio, 4),
            }

        except Exception as e:
            logger.warning(f"[ResultFormatterService] 计算组合指标失败: {e}")
        return metrics

    @staticmethod
    def format_axon_results(
        results: dict,
        symbol: str,
        timeframe: str,
        strategy_name: str,
    ) -> dict:
        """
        格式化 axond 回测引擎结果为 QuantCell 标准格式（单品种版本）

        Args:
            results: BacktestEngine.run_with_strategy() 返回的结果字典
            symbol: 品种符号
            timeframe: 时间周期
            strategy_name: 策略名称

        Returns:
            dict: 格式化的回测结果（与事件驱动格式兼容）
        """
        key = f"{symbol}_{timeframe}"

        initial_capital = results.get("initial_capital", 100000.0)
        final_nav = results.get("final_nav", 0.0)
        total_pnl = results.get("total_pnl", 0.0)
        trade_count = results.get("trade_count", 0)
        max_dd_pct = results.get("max_drawdown_pct", 0.0)
        win_rate = results.get("win_rate", 0.0)
        sharpe_ratio = results.get("sharpe_ratio", 0.0)
        total_fees = results.get("total_fees", 0.0)
        nav_peak = results.get("nav_peak", initial_capital)
        total_return_pct = ResultFormatterService._calc_return_from_pnl(total_pnl, initial_capital)

        # 计算额外指标
        trades = results.get("trades", [])
        winning_trades = len([t for t in trades if isinstance(t, dict) and t.get("PnL", t.get("pnl", 0)) > 0])
        losing_trades = trade_count - winning_trades if trade_count > 0 else 0
        total_wins = sum(
            t.get("PnL", t.get("pnl", 0)) for t in trades if isinstance(t, dict) and t.get("PnL", t.get("pnl", 0)) > 0
        )
        total_losses = abs(
            sum(
                t.get("PnL", t.get("pnl", 0))
                for t in trades
                if isinstance(t, dict) and t.get("PnL", t.get("pnl", 0)) <= 0
            )
        )
        profit_factor = total_wins / total_losses if total_losses > 0 else (float("inf") if total_wins > 0 else 0.0)

        # 构建 metrics 数组（前端期望格式：[{name, key, value, description, type}]）
        metrics_list = [
            {
                "name": "总收益率",
                "key": "total_return",
                "value": total_return_pct,
                "description": "总收益率",
                "type": "percentage",
            },
            {
                "name": "年化收益率",
                "key": "cagr",
                "value": total_return_pct,
                "description": "年化收益率（简化）",
                "type": "percentage",
            },
            {
                "name": "夏普比率",
                "key": "sharpe_ratio",
                "value": round(sharpe_ratio, 4),
                "description": "夏普比率",
                "type": "number",
            },
            {
                "name": "最大回撤",
                "key": "max_drawdown",
                "value": round(max_dd_pct, 2),
                "description": "最大回撤百分比",
                "type": "percentage",
            },
            {
                "name": "胜率",
                "key": "win_rate",
                "value": round(win_rate, 2),
                "description": "胜率",
                "type": "percentage",
            },
            {
                "name": "盈亏比",
                "key": "profit_factor",
                "value": round(profit_factor, 4) if profit_factor != float("inf") else 999.99,
                "description": "盈亏比",
                "type": "number",
            },
            {
                "name": "交易次数",
                "key": "total_trades",
                "value": trade_count,
                "description": "交易次数",
                "type": "number",
            },
            {
                "name": "盈利交易",
                "key": "winning_trades",
                "value": winning_trades,
                "description": "盈利交易数",
                "type": "number",
            },
            {
                "name": "亏损交易",
                "key": "losing_trades",
                "value": losing_trades,
                "description": "亏损交易数",
                "type": "number",
            },
            {
                "name": "总盈亏",
                "key": "total_pnl",
                "value": round(total_pnl, 2),
                "description": "总盈亏",
                "type": "number",
            },
            {
                "name": "初始权益",
                "key": "initial_equity",
                "value": initial_capital,
                "description": "初始权益",
                "type": "number",
            },
            {
                "name": "最终权益",
                "key": "final_equity",
                "value": final_nav,
                "description": "最终权益",
                "type": "number",
            },
            {
                "name": "权益峰值",
                "key": "equity_peak",
                "value": nav_peak,
                "description": "权益峰值",
                "type": "number",
            },
            {
                "name": "索提诺比率",
                "key": "sortino_ratio",
                "value": 0.0,
                "description": "索提诺比率（待计算）",
                "type": "number",
            },
            {
                "name": "卡尔马比率",
                "key": "calmar_ratio",
                "value": round((total_return_pct / max_dd_pct), 4) if max_dd_pct > 0 else 0.0,
                "description": "卡尔马比率",
                "type": "number",
            },
            {
                "name": "平均回撤",
                "key": "avg_drawdown",
                "value": 0.0,
                "description": "平均回撤（待计算）",
                "type": "percentage",
            },
            {
                "name": "年化波动率",
                "key": "volatility",
                "value": 0.0,
                "description": "年化波动率（待计算）",
                "type": "percentage",
            },
            {
                "name": "期望收益",
                "key": "expectancy",
                "value": round(total_pnl / trade_count, 4) if trade_count > 0 else 0.0,
                "description": "每笔期望收益",
                "type": "number",
            },
            {
                "name": "平均交易",
                "key": "avg_trade",
                "value": round(total_return_pct / trade_count, 4) if trade_count > 0 else 0.0,
                "description": "平均交易收益率",
                "type": "percentage",
            },
            {
                "name": "最佳交易",
                "key": "best_trade",
                "value": round(
                    max(
                        (
                            t.get("PnL", t.get("pnl", 0))
                            / (t.get("EntryPrice", t.get("entry_price", 1)) * t.get("Size", t.get("size", 1)))
                            * 100
                            for t in trades
                            if isinstance(t, dict)
                        ),
                        default=0.0,
                    ),
                    2,
                ),
                "description": "最佳交易收益率",
                "type": "percentage",
            },
            {
                "name": "最差交易",
                "key": "worst_trade",
                "value": round(
                    min(
                        (
                            t.get("PnL", t.get("pnl", 0))
                            / (t.get("EntryPrice", t.get("entry_price", 1)) * t.get("Size", t.get("size", 1)))
                            * 100
                            for t in trades
                            if isinstance(t, dict)
                        ),
                        default=0.0,
                    ),
                    2,
                ),
                "description": "最差交易收益率",
                "type": "percentage",
            },
            {
                "name": "总手续费",
                "key": "total_commission",
                "value": round(total_fees, 2),
                "description": "总手续费",
                "type": "number",
            },
            {
                "name": "阿尔法",
                "key": "alpha",
                "value": 0.0,
                "description": "阿尔法（待计算）",
                "type": "number",
            },
            {
                "name": "贝塔",
                "key": "beta",
                "value": 0.0,
                "description": "贝塔（待计算）",
                "type": "number",
            },
            {
                "name": "SQN",
                "key": "sqn",
                "value": 0.0,
                "description": "系统质量数（待计算）",
                "type": "number",
            },
            {
                "name": "凯利准则",
                "key": "kelly_criterion",
                "value": 0.0,
                "description": "凯利准则（待计算）",
                "type": "number",
            },
            {
                "name": "暴露时间",
                "key": "exposure_time",
                "value": 0.0,
                "description": "暴露时间（待计算）",
                "type": "percentage",
            },
            {
                "name": "回测天数",
                "key": "duration_days",
                "value": 0,
                "description": "回测天数",
                "type": "number",
            },
            {
                "name": "平均持仓时间",
                "key": "avg_trade_duration_hours",
                "value": 0.0,
                "description": "平均持仓时间（小时）",
                "type": "number",
            },
            {
                "name": "最长持仓时间",
                "key": "max_trade_duration_hours",
                "value": 0.0,
                "description": "最长持仓时间（小时）",
                "type": "number",
            },
        ]

        formatted = {
            key: {
                "symbol": symbol,
                "timeframe": timeframe,
                "metrics": metrics_list,
                "trades": trades,
                "positions": results.get("positions", []),
                "equity_curve": results.get("equity_curve", []),
            }
        }

        # 全局账户信息
        formatted["account"] = {
            "starting_balance": initial_capital,
            "final_nav": final_nav,
            "total_pnl": total_pnl,
        }

        # 投资组合汇总
        formatted["portfolio"] = {
            "metrics": metrics_list,
            "trades": trades,
            "equity_curve": results.get("equity_curve", []),
        }

        # 元数据
        now = datetime.now()
        formatted["_meta"] = {
            "engine": "axon",
            "strategy": strategy_name,
            "timestamp": int(now.timestamp()),
            "formatted_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return formatted

    @staticmethod
    def _calc_return_from_pnl(total_pnl: float, initial_capital: float) -> float:
        """从 PnL 和初始资金计算回报率（百分比）

        Args:
            total_pnl: 总盈亏
            initial_capital: 初始资金

        Returns:
            float: 回报率（百分比）
        """
        if initial_capital <= 0:
            return 0.0
        return round((total_pnl / initial_capital) * 100.0, 2)
