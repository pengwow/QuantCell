# -*- coding: utf-8 -*-
"""
回测引擎服务模块（基于 axond 体系）

封装事件驱动回测引擎的初始化、数据加载、策略加载和执行流程。
将原本分散在 cli.py 和 service.py 中的引擎操作逻辑统一到此模块。
完全基于 axond.BacktestEngine，不依赖任何外部量化框架。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class EventDrivenBacktestService:
    """
    事件驱动回测引擎服务（基于 axond 体系）

    封装事件驱动引擎的完整生命周期管理：
    1. 数据加载（通过 BacktestDataProvider）
    2. 引擎初始化（AxonBacktestEngine）
    3. 数据转换并加载到引擎
    4. 策略加载和实例化
    5. 回测执行
    6. 结果格式化

    使用示例：
        from backtest.data_provider import BacktestDataProvider
        from backtest.engine_service import EventDrivenBacktestService

        provider = BacktestDataProvider()
        service = EventDrivenBacktestService(provider)

        results = service.run_backtest(
            strategy_name="simple_dual_ma",
            strategy_params={"fast_period": 10},
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            engine_config={"initial_capital": 100000}
        )
    """

    def __init__(self, data_provider):
        """
        初始化引擎服务

        Args:
            data_provider: BacktestDataProvider 实例
        """
        self.provider = data_provider

    def run_backtest(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        symbols: List[str],
        timeframes: List[str],
        engine_config: Optional[Dict] = None,
        show_progress: bool = False,
    ) -> Dict:
        """
        执行完整的事件驱动回测流程

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_config: 引擎配置（可选）
            show_progress: 是否显示进度

        Returns:
            dict: 格式化的回测结果
        """
        logger.info(f"[EventDrivenBacktestService] 开始执行回测: {strategy_name}")

        # 解析默认配置
        init_cash = (engine_config or {}).get("initial_capital", 10000)

        # 1. 加载数据
        if show_progress:
            print("\n[1/5] 正在加载数据...")

        data_dict, _ = self.provider.load_multiple(
            symbols=symbols,
            timeframes=timeframes,
            candle_type="spot",
            time_range=(engine_config or {}).get("time_range"),
            auto_download=False,
            show_progress=show_progress,
        )

        if not data_dict:
            raise ValueError("没有成功加载任何数据，回测无法继续")

        # 2. 初始化引擎
        if show_progress:
            print("[2/5] 正在初始化引擎...")

        engine = self._initialize_engine(
            engine_config=engine_config,
            strategy_name=strategy_name,
            init_cash=init_cash,
        )

        # 3. 加载策略
        if show_progress:
            print(f"[3/5] 正在加载策略: {strategy_name}...")

        from backtest.strategy_loader_service import StrategyLoaderService

        # 构造策略必需的 instrument_ids / bar_types
        instrument_ids = []
        bar_types = []
        for s in symbols:
            for t in timeframes:
                instrument_ids.append({"symbol": s, "venue": "BINANCE"})
                bar_types.append(t)

        strategy = StrategyLoaderService.load_strategy(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            instrument_ids=instrument_ids,
            bar_types=bar_types,
        )

        if strategy is None:
            raise ValueError(f"无法加载策略: {strategy_name}")

        # 4. 执行回测（axon_quant 适配层）
        if show_progress:
            print(f"[4/5] 正在执行回测（{len(data_dict)} 个品种）...")

        if len(symbols) == 1:
            # 单品种：直接调用 run_with_strategy
            first_key = list(data_dict.keys())[0]
            df = data_dict[first_key]
            parts = first_key.rsplit("_", 1)
            symbol = parts[0] if len(parts) > 1 else first_key

            # 末日单管理:CLI / 脚本传 force_liquidate 控制回测结束 EOD 平仓
            # True = 强制市价清仓(所有 PnL 转为已实现,适合日报/对账)
            force_liquidate = (engine_config or {}).get("force_liquidate", False)

            raw_results = engine.run_with_strategy(
                strategy=strategy,
                data=df,
                symbol=symbol,
                force_liquidate=force_liquidate,
            )
        else:
            # 多品种：每个品种跑一次，结果合并
            # 白名单累加:只累加跨品种有可加性的字段(PnL/fills/trades/fees 等)
            # 旧逻辑把所有 int/float 累加,data_start_ns/end_ns/bar_count 等
            # per-symbol 字段也被累加,导致时间范围错乱、nav 倍增
            #
            # 字段策略:
            # - _SUM_KEYS:累加(跨品种汇总有意义的,如 PnL、成交笔数、手续费)
            # - _MIN_KEYS:取 min(如 data_start_ns,跨品种最早 bar)
            # - _MAX_KEYS:取 max(如 data_end_ns,跨品种最晚 bar)
            # - 其他 per-symbol 字段(initial_capital/final_nav/sharpe/max_dd/win_rate/
            #   equity_curve/trades/nav_peak):跳过,后续由 formatter/单 symbol 报告展示
            force_liquidate = (engine_config or {}).get("force_liquidate", False)
            _SUM_KEYS = {
                "total_pnl", "orders_accepted", "orders_rejected", "fills",
                "total_orders", "total_fees", "events_processed",
                "duration_secs", "trade_count", "bar_count",
            }
            _MIN_KEYS = {"data_start_ns"}
            _MAX_KEYS = {"data_end_ns"}
            aggregated_metrics: Dict[str, Any] = {}
            # 保留 per-symbol 单独的结果,供 _aggregate_multi_results 给各 symbol 填自己的 metrics
            # (否则 results_by_symbol[k].metrics 只能塞聚合后的 dict,output_results 显示的
            # "贡献盈亏"会是聚合 PnL 而非单品种 PnL,用户看到的 ETH/BTC PnL 一样,误导)
            per_symbol_results: Dict[str, Dict[str, Any]] = {}
            for key, df in data_dict.items():
                parts = key.rsplit("_", 1)
                sym = parts[0] if len(parts) > 1 else key
                result = engine.run_with_strategy(
                    strategy=strategy,
                    data=df,
                    symbol=sym,
                    force_liquidate=force_liquidate,
                )
                per_symbol_results[sym] = result
                for k, v in result.items():
                    if k in _SUM_KEYS and isinstance(v, (int, float)):
                        aggregated_metrics[k] = aggregated_metrics.get(k, 0) + v
                    elif k in _MIN_KEYS and isinstance(v, (int, float)):
                        # 取最早时间 = min(已见, 当前)
                        cur = aggregated_metrics.get(k, v)
                        aggregated_metrics[k] = min(cur, v) if cur else v
                    elif k in _MAX_KEYS and isinstance(v, (int, float)):
                        # 取最晚时间 = max(已见, 当前)
                        cur = aggregated_metrics.get(k, v)
                        aggregated_metrics[k] = max(cur, v) if cur else v
                    # 其他字段(int/float 但不是 per-portfolio 字段 / 非数值)
                    # 一律丢弃:它们是 per-symbol 的状态,汇总会失真
            raw_results = aggregated_metrics

        # 5. 格式化结果
        if show_progress:
            print("[5/5] 正在格式化结果...")

        if len(symbols) == 1:
            # axon 引擎结果格式（final_nav/total_pnl/...）,
            # 与 event 格式（metrics/trades/...）不同,必须用 format_axon_results
            # 否则 metrics 字段全部为 0
            from backtest.result_formatter_service import ResultFormatterService

            formatted_results = ResultFormatterService.format_axon_results(
                results=raw_results,
                symbol=symbols[0],
                timeframe=timeframes[0] if timeframes else "1h",
                strategy_name=strategy_name,
            )
        else:
            # 多品种结果汇总
            formatted_results = self._aggregate_multi_results(
                raw_results=raw_results,
                per_symbol_results=per_symbol_results,
                symbols=symbols,
                timeframe=timeframes[0] if timeframes else "15m",
                strategy_name=strategy_name,
            )

        # 清理资源
        engine.cleanup()

        logger.info(f"[EventDrivenBacktestService] 回测完成")

        return formatted_results

    def _initialize_engine(
        self,
        engine_config: Optional[Dict],
        strategy_name: str,
        init_cash: float,
    ):
        """
        初始化事件驱动引擎

        Args:
            engine_config: 引擎配置字典
            strategy_name: 策略名称
            init_cash: 初始资金

        Returns:
            AxonBacktestEngine: 已初始化的引擎实例
        """
        from backtest.engines.axon_engine import AxonBacktestEngine

        config = {
            "initial_capital": init_cash,
            "log_level": (engine_config or {}).get("log_level", "INFO"),
        }

        engine = AxonBacktestEngine(config)
        engine.initialize()

        logger.info(f"[EventDrivenBacktestService] 引擎初始化完成")
        return engine

    def _aggregate_multi_results(
        self,
        raw_results: dict,
        per_symbol_results: Dict[str, Dict[str, Any]],
        symbols: List[str],
        timeframe: str,
        strategy_name: str,
    ) -> dict:
        """汇总多品种回测结果

        Args:
            raw_results: 跨品种聚合后的指标(PnL/fills/fees 累加,data_start 取 min 等)
            per_symbol_results: 每个品种单独的原始结果,用于 results_by_symbol[k].metrics
                填单品种 metrics(否则 output_results 显示的"贡献盈亏"是聚合 PnL)
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称

        Returns:
            多品种汇总 dict
        """
        # 计算 portfolio-level 指标(从 per_symbol_results 重算,不能简单 sum 百分比类)
        n = len(per_symbol_results)
        total_pnl = raw_results.get("total_pnl", 0.0)
        total_trades = raw_results.get("trade_count", 0)
        total_fills = raw_results.get("fills", 0)
        total_fees = raw_results.get("total_fees", 0.0)

        # initial_equity / final_equity:每品种独立资金池(每 run 都 initial_cash 起步)
        # 假设所有品种用同一 initial_cash,从第一个结果读
        first_sym = symbols[0] if symbols else None
        first_result = per_symbol_results.get(first_sym, {}) if first_sym else {}
        initial_cash_per_symbol = first_result.get("initial_capital", 100000.0)
        initial_equity = initial_cash_per_symbol * n  # N 个独立资金池
        final_equity = initial_equity + total_pnl
        # total_return:百分比
        total_return = (total_pnl / initial_equity * 100.0) if initial_equity > 0 else 0.0

        # win_rate:跨品种重新统计(从 per_symbol 各自的 wins / trades_count 算)
        # 没 trade records 数据时 fallback 到 fills 兜底(撮合成交笔数 = 交易笔数近似)
        winning_trades = 0
        losing_trades = 0
        for sym, r in per_symbol_results.items():
            sym_trades = r.get("trades", [])
            if sym_trades:
                # 有 trade records(开平仓配对)
                for t in sym_trades:
                    pnl = t.get("pnl", 0) if isinstance(t, dict) else 0
                    if pnl > 0:
                        winning_trades += 1
                    elif pnl < 0:
                        losing_trades += 1
            else:
                # 没 trade records,fallback 到 per-symbol 的 win_rate * fills 估算
                sym_wr = r.get("win_rate", 0.0)
                sym_fills = r.get("fills", 0)
                winning_trades += int(sym_wr * sym_fills)
        win_rate = (
            winning_trades / total_trades * 100.0
            if total_trades > 0 else 0.0
        )

        # max_drawdown:取最大回撤品种的 pct(独立资金池不该 sum)
        max_dd_pct = 0.0
        for sym, r in per_symbol_results.items():
            sym_dd = r.get("max_drawdown_pct", 0.0)
            if sym_dd > max_dd_pct:
                max_dd_pct = sym_dd

        # sharpe_ratio:per-symbol 加权平均(按交易笔数加权,更接近 portfolio 真实夏普)
        # 简单实现:n=1 时直接用,否则用 fills 加权
        if n == 1:
            sharpe_ratio = first_result.get("sharpe_ratio", 0.0)
        else:
            if total_fills > 0:
                sharpe_ratio = sum(
                    r.get("sharpe_ratio", 0.0) * r.get("fills", 0)
                    for r in per_symbol_results.values()
                ) / total_fills
            else:
                sharpe_ratio = sum(
                    r.get("sharpe_ratio", 0.0)
                    for r in per_symbol_results.values()
                ) / n

        # 填充 raw_results 的 portfolio-level 字段,让 output_results 能读到
        # (原本只有 sum/min/max 字段,initial_equity/win_rate 等需显式计算)
        raw_results["initial_equity"] = initial_equity
        raw_results["final_equity"] = final_equity
        raw_results["total_return"] = total_return
        raw_results["win_rate"] = win_rate
        raw_results["max_drawdown"] = max_dd_pct  # 用 pct 字段(百分比,单位一致)
        raw_results["sharpe_ratio"] = sharpe_ratio

        return {
            "strategy_name": strategy_name,
            "symbols": symbols,
            "timeframe": timeframe,
            "is_multi_symbol": True,
            "results_by_symbol": {
                symbol: {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy_name": strategy_name,
                    # 用 per_symbol_results[symbol] 给单 symbol 填自己真实的 metrics
                    # 旧实现塞 raw_results(聚合后),导致 CLI 贡献盈亏显示聚合 PnL
                    "metrics": per_symbol_results.get(symbol, raw_results),
                    # 透传 trades / equity_curve 等 list 字段到顶层
                    # (axon_engine 返回的 dict 里 trades 在顶层 metrics 同级;
                    # output_results 读 result.get('trades', []),需要在顶层)
                    "trades": per_symbol_results.get(symbol, {}).get("trades", []),
                    "equity_curve": per_symbol_results.get(symbol, {}).get("equity_curve", []),
                }
                for symbol in symbols
            },
            "metrics": raw_results,
        }
