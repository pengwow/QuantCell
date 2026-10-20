"""
回测引擎服务模块（基于 axon_quant 体系）

默认回测路径：BaseStrategy → RustStrategyAdapter → axon_quant worker.BacktestRunner
（Rust 原生撮合编排）；engine_config['runner']='python' 可回退到
BaseStrategy → BacktestLoop → axon_quant backtest.BacktestEngine。

本模块负责数据加载、因子特征注入与结果格式化，两条引擎路径的编排差异
必须在 Rust 侧复刻（parity 由 tests/unit/backtest/test_rust_runner_parity.py 守护）。
放行的 data_type 见下方 `RUST_RUNNER_DATA_TYPES`（含两个语义边界说明）。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from backtest.backtest_loop import BacktestLoop, BacktestResult, clean_ohlcv_df
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

# 逐品种进度回调：参数为 (已完成品种数, 品种总数, 当前开始回测的品种)
# ponytail: 粒度只到品种级，单品种回测在引擎执行期间没有中间进度（需 Rust 引擎支持 bar 级回调）
SymbolProgressCallback = Callable[[int, int, str], None]

# 放行 Rust BacktestRunner 的 data_type：四类适配器（KlineAdapter / TickAdapter /
# OrderBookAdapter / DerivAdapter）已把它们聚合成 bar 形状（大写 OHLCV + int64 纳秒
# timestamp），`clean_ohlcv_df` → `_df_to_rust_bars` 可直接消费。
#
# 两个必须守住的语义边界：
# - `fundingRate` 作为 data_type 是 DerivAdapter 产出的特征列（feature_funding_rate），
#   与 `_build_rust_funding` 的资金费结算通道（仅 futures 且 provider 有费率时生效）
#   不是一回事，二者不得混用，否则双重计费；
# - `bookDepth` / `bookTicker` 聚合出的是 mid-price 合成价，不是可撮合盘口深度。
#
# 不在放行范围：原生 tick / 逐档 book 驱动的撮合（需 Rust L2/L3 + 非 bar 步进编排）。
RUST_RUNNER_DATA_TYPES = frozenset(
    {
        "kline",
        "markPriceKlines",
        "indexPriceKlines",
        "premiumIndexKlines",
        "aggTrades",
        "trades",
        "bookDepth",
        "bookTicker",
        "fundingRate",
        "openInterest",
    }
)

# market → 永续保证金结算方式（spot 无 settle 概念，缺省按 U 本位）
_SWAP_SETTLE_BY_MARKET = {"um": "usd_margin", "cm": "coin_margin"}


def adapter_feature_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    """从适配器输出的 `feature_*` 列派生逐 bar 特征帧（供策略 ctx.features 消费）。

    适配器把特征作为列挂在 data 上（feature_mid_price / feature_spread /
    feature_funding_rate / feature_open_interest* 等），而 `clean_ohlcv_df`
    只保留 timestamp + OHLCV，这些列会被丢弃 —— 因此在清洗前抽出来单独成帧。

    - 列名去掉 `feature_` 前缀（与因子库的命名口径一致，策略里直接读 `mid_price` 等）；
    - 索引对齐 bar 时间戳（data 的 `timestamp` 列，纳秒）。
    拿不到时间列且索引不是 DatetimeIndex 时返回 None：宁可不注入特征，
    也不能把特征错位到别的 bar 上。
    """
    cols = [c for c in df.columns if str(c).lower().startswith("feature_")]
    if not cols:
        return None

    # 用 dict 构帧（列名就地去掉 feature_ 前缀），避免 df[cols] 的分支推断歧义
    out = pd.DataFrame({str(c)[len("feature_") :]: df[c] for c in cols}, index=df.index)

    if "timestamp" in df.columns:
        out.index = pd.to_datetime(df["timestamp"], utc=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        return None  # 拿不到时间列且索引不是时间索引
    return out


class EventDrivenBacktestService:
    """
    事件驱动回测引擎服务（基于 axond 体系）

    封装事件驱动引擎的完整生命周期管理：
    1. 数据加载（通过 BacktestDataProvider）
    2. 引擎初始化（BacktestEngine）
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
            strategy_name="sma_crossover",
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
        strategy_params: dict[str, Any],
        symbols: list[str],
        timeframes: list[str],
        engine_config: dict | None = None,
        show_progress: bool = False,
        data_type: str = "kline",
        market: str = "spot",
        factor_names: list[str] | None = None,
        on_symbol_progress: SymbolProgressCallback | None = None,
    ) -> dict:
        """
        执行完整的事件驱动回测流程

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_config: 引擎配置（可选），支持 trading_mode: "spot"/"futures"
            show_progress: 是否显示进度
            data_type: 数据类型 (kline/aggTrades/fundingRate/bookDepth 等)
            market: 市场类型 (spot/um/cm)
            factor_names: 参与回测的因子名称列表（可选）
            on_symbol_progress: 逐品种进度回调，每个品种开跑前以
                (已完成品种数, 品种总数, 当前品种) 触发（可选）

        Returns:
            dict: 格式化的回测结果
        """
        logger.info(
            f"[EventDrivenBacktestService] 开始执行回测: {strategy_name}, data_type={data_type}, market={market}"
        )

        # 解析默认配置
        engine_cfg = engine_config or {}
        # 键名归一化：CLI 传 initial_capital/time_range，REST API 契约（BacktestConfig schema）
        # 是 initial_cash/start_time + end_time。只认一种会导致另一侧配置静默失效：
        # 资金跌回默认值、时间范围退化为全量历史数据。
        init_cash = engine_cfg.get("initial_capital", engine_cfg.get("initial_cash", 10000))
        # 资金使用方式：per_symbol=各品种独立资金池（现状，N×init_cash）；
        # shared=组合共享资金池（单账户，总名义敞口 ≤ init_cash × leverage）
        capital_mode = engine_cfg.get("capital_mode", "per_symbol")
        leverage = float(engine_cfg.get("leverage", 1.0) or 1.0)
        time_range = engine_cfg.get("time_range")
        if not time_range:
            start_time, end_time = engine_cfg.get("start_time"), engine_cfg.get("end_time")
            if start_time and end_time:
                # parse_time_range 支持的 "start-end" 拼接格式（ISO datetime 含空格可正确分割）
                time_range = f"{start_time}-{end_time}"
        # 交易模式: spot(现货) / futures(永续合约)
        trading_mode = engine_cfg.get("trading_mode", "spot")
        candle_type = "future" if trading_mode == "futures" else "spot"

        # 永续合约口径：保证金结算方式由 market 推导（"cm" 币本位 → coin_margin，
        # 其余含 "um" → usd_margin）；合约乘数由调用方经 engine_config 显式提供。
        #
        # ponytail: 乘数默认 1.0 —— 仓库内没有离线可用的合约面值来源（collector 落地的
        # exchangeInfo 不含 contractSize），且 axon 引擎目前只把乘数当品种元数据、
        # 未计入名义价值/盈亏（axon-backtest engine.rs 挂着 0.8.0 待办），所以币本位
        # 只有结算方式被如实标注，账务仍是近似。要真做对需要「面值表 + 引擎侧乘数入账」
        # + 「ratio → 合约张数」的换算，属独立立项。
        swap_settle = _SWAP_SETTLE_BY_MARKET.get(market, "usd_margin")
        contract_size = float(engine_cfg.get("contract_size", 1.0))

        # 1. 加载数据
        # 无数据被剔除的品种：{品种名: 原因}。剔除本身是正确行为（空数据跑回测产出假结果），
        # 但必须随结果透出，否则「选 2 个标的跑完只剩 1 个」用户无从知道原因
        skipped_symbols: dict[str, str] = {}
        if data_type == "kline":
            # K线数据：使用原有加载逻辑
            data_dict, _ = self.provider.load_multiple(
                symbols=symbols,
                timeframes=timeframes,
                candle_type=candle_type,
                time_range=time_range,
                auto_download=False,
                show_progress=show_progress,
            )
            # 转换为统一格式
            loaded_data: dict[str, Any] = {}
            for key, df in data_dict.items():
                # 时间范围内无数据的品种剔除：空 df 进回测会产出全 fallback 的假
                # 结果（初始权益 100000 / 最终权益 0），污染详情页按品种视图
                if df is None or df.empty:
                    logger.warning(f"{key} 在配置时间范围内无数据，已跳过该品种")
                    skipped_symbols[key.rsplit("_", 1)[0]] = "配置时间范围内无数据"
                    continue
                loaded_data[key] = {
                    "data": df,
                    "features": None,
                    "feature_dataframe": None,
                    "data_type": "kline",
                }
        else:
            # 非K线数据：通过适配器加载
            adapter_dict, _ = self.provider.load_multiple_data(
                symbols=symbols,
                timeframes=timeframes,
                data_type=data_type,
                market=market,
                time_range=time_range,
                show_progress=show_progress,
            )
            loaded_data: dict[str, Any] = {}
            for key, result in adapter_dict.items():
                # 同 kline 分支：无数据品种剔除，避免空结果条目污染详情页
                if result.data is None or result.data.empty:
                    logger.warning(f"{key} 在配置时间范围内无数据，已跳过该品种")
                    skipped_symbols[key.rsplit("_", 1)[0]] = "配置时间范围内无数据"
                    continue
                loaded_data[key] = {
                    "data": result.data,
                    "features": result.metadata.get("features_dict"),
                    # 适配器一般把特征作为 feature_* 列挂在 data 上（AdapterResult.features
                    # 常为 None），这里回退成从列派生，否则非 K 线回测拿不到任何特征
                    "feature_dataframe": result.features
                    if result.features is not None and not result.features.empty
                    else adapter_feature_frame(result.data),
                    "data_type": data_type,
                }

        if not loaded_data:
            msg = "没有成功加载任何数据，回测无法继续"
            raise ValueError(msg)

        # 因子特征帧：回测后用于详情页因子分析（时序、归因、交易时点因子值）
        feature_frames: dict[str, pd.DataFrame] | None = None

        # 因子特征：用因子库预计算逐品种特征帧并回填，BacktestLoop 逐 bar 注入
        if factor_names and data_type == "kline":
            from factor.features import attach_feature_frames, build_feature_frames

            f_start = f_end = None
            if time_range:
                try:
                    from utils.validation import parse_time_range

                    f_start_dt, f_end_dt = parse_time_range(time_range)
                    f_start = f_start_dt.strftime("%Y-%m-%d")
                    f_end = f_end_dt.strftime("%Y-%m-%d")
                except Exception as e:
                    logger.warning(f"因子取数时间范围解析失败，改用全量数据: {e}")

            rank_factor = (strategy_params or {}).get("factor_name") or factor_names[0]
            frames = build_feature_frames(
                factor_names=factor_names,
                symbols=symbols,
                interval=timeframes[0],
                candle_type=candle_type,
                start=f_start,
                end=f_end,
                rank_factor=rank_factor if len(symbols) >= 2 else None,
            )
            feature_frames = frames
            attach_feature_frames(loaded_data, frames)

        # 2. 加载策略（先判断策略基类，决定走共享引擎还是逐品种独立回测）
        from backtest.strategy_loader_service import StrategyLoaderService

        instrument_ids = [{"symbol": s, "venue": "BINANCE"} for s in symbols for _ in timeframes]
        bar_types = list(timeframes) * len(symbols)

        strategy = StrategyLoaderService.load_strategy(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            instrument_ids=instrument_ids,
            bar_types=bar_types,
        )

        if strategy is None:
            msg = f"无法加载策略: {strategy_name}"
            raise ValueError(msg)

        # 多品种结果占位（单品种路径不赋值，保持 None）
        per_symbol_results: dict[str, dict[str, Any]] | None = None

        # 3. 执行回测 —— 唯一路径：BaseStrategy → BacktestLoop（ctx 注入 features/funding/account）
        loop = BacktestLoop(initial_cash=init_cash)
        force_liquidate = (engine_config or {}).get("force_liquidate", False)

        # 回测编排路径选择：默认 Rust 原生（axon_quant.worker.BacktestRunner），
        # 可显式设 engine_config['runner']='python' 回退到 Python BacktestLoop。
        #
        # 放行条件：data_type ∈ RUST_RUNNER_DATA_TYPES（见模块常量，kline 家族 / tick /
        # orderbook / deriv 共 10 类，均由适配器聚合为 bar 形状）。期货资金费、逐 bar
        # 特征注入、force_liquidate 均已由 Rust 侧支持；多品种按「每品种独立跑一个 runner」
        # 执行（与 BacktestLoop 每品种独立资金池口径一致），跨品种聚合仍在 Python 侧。
        runner_mode = (engine_config or {}).get("runner", "rust")
        use_rust_runner = runner_mode == "rust" and data_type in RUST_RUNNER_DATA_TYPES

        if len(symbols) == 1:
            first_key = next(iter(loaded_data.keys()))
            entry = loaded_data[first_key]
            df = entry["data"]
            parts = first_key.rsplit("_", 1)
            symbol = parts[0] if len(parts) > 1 else first_key
            if on_symbol_progress:
                on_symbol_progress(0, 1, symbol)
            if use_rust_runner:
                # Rust 原生编排：BacktestRunner 逐 bar 调策略，结果映射回同一契约
                result = self._run_rust_single(
                    strategy=strategy,
                    df=df,
                    symbol=symbol,
                    init_cash=init_cash,
                    force_liquidate=force_liquidate,
                    feature_dataframe=entry.get("feature_dataframe"),
                    funding_df=self._load_funding(symbol, trading_mode, time_range),
                    futures=(trading_mode == "futures"),
                    settle=swap_settle,
                    contract_size=contract_size,
                )
            else:
                result = loop.run(
                    strategy=strategy,
                    data=df,
                    symbol=symbol,
                    force_liquidate=force_liquidate,
                    features=entry.get("features"),
                    feature_dataframe=entry.get("feature_dataframe"),
                    data_type=entry.get("data_type", "kline"),
                    trading_mode=trading_mode,
                    funding_df=self._load_funding(symbol, trading_mode, time_range),
                    settle=swap_settle,
                    contract_size=contract_size,
                )
            raw_results = self._convert_backtest_result(result)
            # 清洗后 K 线写入结果，供回放页 kline_data（只进结果 JSON，不入 DB）
            raw_results["klines"] = self._build_kline_records(clean_ohlcv_df(df), engine_config, time_range)
        elif capital_mode == "shared":
            # 组合共享资金池：所有品种的**策略实例**注册到**同一个** runner（单 engine、
            # 一笔 init_cash），总名义敞口受 init_cash × leverage 约束。与下面 else 的
            # 「各品种独立资金池」循环是两条互斥路径，后者逐字保持原样。
            if on_symbol_progress:
                # 共享模式是单次阻塞调用，无法逐品种上报（见设计文档「7. 进度上报」）
                on_symbol_progress(0, 1, "组合共享资金池")
            strategies_by_symbol: dict[str, Any] = {}
            entries_for_multi: dict[str, dict[str, Any]] = {}
            for key, entry in loaded_data.items():
                parts = key.rsplit("_", 1)
                sym = parts[0] if len(parts) > 1 else key
                # 每个品种一个独立策略实例：共享账户下策略内部的滚动状态必须按品种隔离，
                # 否则两品种会互相污染彼此的指标窗口
                sym_strategy = StrategyLoaderService.load_strategy(
                    strategy_name=strategy_name,
                    strategy_params=strategy_params,
                    instrument_ids=[{"symbol": sym, "venue": "BINANCE"}],
                    bar_types=[timeframes[0]] if timeframes else ["15m"],
                )
                if sym_strategy is None:
                    msg = f"无法加载策略: {strategy_name} ({sym})"
                    raise ValueError(msg)
                strategies_by_symbol[sym] = sym_strategy
                entries_for_multi[sym] = entry
            multi_result, per_symbol_trades, per_symbol_fills = self._run_rust_multi(
                strategies_by_symbol=strategies_by_symbol,
                entries=entries_for_multi,
                init_cash=init_cash,
                capital_budget=init_cash * leverage,
                force_liquidate=force_liquidate,
                futures=(trading_mode == "futures"),
                settle=swap_settle,
                contract_size=contract_size,
                trading_mode=trading_mode,
                time_range=time_range,
            )
            raw_results = multi_result
            per_symbol_results = {}
            for sym, entry in entries_for_multi.items():
                # 各品种条目是同一共享账户的**拆分视图**：
                # - 成交派生指标（盈亏、收益率、成交笔数、胜率…）按品种归因，
                #   否则切换品种时详情页看到的是同一组聚合数字（各品种完全一样）；
                # - 账户级口径（初始/最终权益、权益峰值、夏普、回撤、手续费）属于整个
                #   共享账户，无法按品种拆分 → 保持 agg 真值（前端在品种视角隐藏它们）
                sym_result = dict(multi_result)
                sym_trades = per_symbol_trades.get(sym, [])
                sym_result["trades"] = sym_trades
                sym_result["trade_count"] = len(sym_trades)
                sym_result["fills"] = per_symbol_fills.get(sym, 0)
                # 引擎 realized_pnl 可加：按品种汇总即该品种对账户盈亏的贡献。
                # 账户级费用（未平仓腿的手续费/盯市/资金费）无法归属到品种，故各品种
                # 已实现盈亏之和允许与账户 total_pnl 有小差异（差额留在组合视图）
                sym_pnl = sum(float(t.get("pnl") or 0.0) for t in sym_trades)
                sym_result["total_pnl"] = sym_pnl
                # 胜率按本品种成交重算（引擎 win_rate 是全账户口径，沿用会让所有品种一样）
                sym_wins = sum(1 for t in sym_trades if float(t.get("pnl") or 0.0) > 0)
                sym_result["win_rate"] = (sym_wins / len(sym_trades) * 100.0) if sym_trades else 0.0
                # total_return 由 format_axon_results 用 total_pnl / initial_capital 算：
                # initial_capital 是共享账户的一笔 init_cash（各品种统一基数 → 贡献可加）
                # 品种视角权益曲线按用户确认口径取共享账户合并曲线（见设计「5. 回放口径」）
                sym_result["equity_curve"] = list(multi_result["equity_curve"])
                sym_result["klines"] = self._build_kline_records(
                    clean_ohlcv_df(entry["data"]), engine_config, time_range
                )
                per_symbol_results[sym] = sym_result
        else:
            aggregated_metrics: dict[str, Any] = {}
            per_symbol_results = {}
            loaded_entries = list(loaded_data.items())
            for idx, (key, entry) in enumerate(loaded_entries):
                df = entry["data"]
                parts = key.rsplit("_", 1)
                sym = parts[0] if len(parts) > 1 else key
                if on_symbol_progress:
                    on_symbol_progress(idx, len(loaded_entries), sym)
                if use_rust_runner:
                    # 每品种独立跑一个 Rust runner（与 BacktestLoop 每品种独立资金池口径一致）
                    loop_result = self._run_rust_single(
                        strategy=strategy,
                        df=df,
                        symbol=sym,
                        init_cash=init_cash,
                        force_liquidate=force_liquidate,
                        feature_dataframe=entry.get("feature_dataframe"),
                        funding_df=self._load_funding(sym, trading_mode, time_range),
                        futures=(trading_mode == "futures"),
                        settle=swap_settle,
                        contract_size=contract_size,
                    )
                else:
                    loop_result = loop.run(
                        strategy=strategy,
                        data=df,
                        symbol=sym,
                        force_liquidate=force_liquidate,
                        features=entry.get("features"),
                        feature_dataframe=entry.get("feature_dataframe"),
                        data_type=entry.get("data_type", "kline"),
                        trading_mode=trading_mode,
                        funding_df=self._load_funding(sym, trading_mode, time_range),
                        settle=swap_settle,
                        contract_size=contract_size,
                    )
                result = self._convert_backtest_result(loop_result)
                per_symbol_results[sym] = result
                # 清洗后 K 线写入结果，供回放页 kline_data（只进结果 JSON，不入 DB）
                result["klines"] = self._build_kline_records(clean_ohlcv_df(df), engine_config, time_range)
                self._accumulate_symbol_metrics(result, aggregated_metrics)
            raw_results = aggregated_metrics

        # 4.5 构建因子分析载荷（仅当配置了 factor_names 且特征帧可用时）
        if factor_names and feature_frames:
            factors_payload = self._build_factors_payload(
                feature_frames=feature_frames,
                loaded_data=loaded_data,
                raw_results=raw_results,
                per_symbol_results=per_symbol_results,
                factor_names=factor_names,
                strategy_params=strategy_params or {},
                symbols=symbols,
            )
            if len(symbols) == 1:
                raw_results["factors"] = factors_payload.get(symbols[0], {})
            elif per_symbol_results:
                for sym in symbols:
                    if sym in per_symbol_results and sym in factors_payload:
                        per_symbol_results[sym]["factors"] = factors_payload[sym]

        # 5. 格式化结果
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
            # 单品种路径也带上资金使用方式：详情页/回放页据此显示口径
            formatted_results["capital_mode"] = capital_mode
        else:
            # 多品种结果汇总（多品种路径下 per_symbol_results 必为 dict）
            formatted_results = self._format_results(
                results=raw_results,
                symbols=symbols,
                timeframe=timeframes[0] if timeframes else "15m",
                strategy_name=strategy_name,
                per_symbol_results=per_symbol_results or {},
                capital_mode=capital_mode,
            )

        # 无数据品种剔除信息写入最终结果：service 层据此修正成功/失败口径，
        # 详情接口透传给前端提示「XX 在所选时间范围内无数据」
        if skipped_symbols:
            formatted_results["skipped_symbols"] = skipped_symbols

        logger.info("[EventDrivenBacktestService] 回测完成")

        return formatted_results

    def _build_kline_records(
        self,
        kline_df: pd.DataFrame,
        engine_config: dict | None,
        time_range: str | None,
    ) -> list[dict[str, Any]]:
        """清洗后 K 线按回测区间裁剪并转 records（回放页 kline_data）。

        区间解析兼容 time_range 字符串和 start_time/end_time 两种 config 风格；
        裁剪结果为空（时区/格式异常）时回退全量。
        """
        k_start = k_end = None
        try:
            from utils.validation import parse_time_range

            if time_range:
                k_start, k_end = parse_time_range(time_range)
            else:
                s = (engine_config or {}).get("start_time")
                e = (engine_config or {}).get("end_time")
                if s and e:
                    k_start, k_end = s, e
        except Exception as e2:
            logger.warning(f"回放 K 线区间解析失败，使用全量数据: {e2}")

        if k_start and k_end:
            # df.index 是 UTC tz-aware，naive 端点需先 localize，否则比较报 TypeError
            k0, k1 = pd.Timestamp(k_start), pd.Timestamp(k_end)
            k0 = k0.tz_localize("UTC") if k0.tz is None else k0.tz_convert("UTC")
            k1 = k1.tz_localize("UTC") if k1.tz is None else k1.tz_convert("UTC")
            clipped = kline_df.loc[(kline_df.index >= k0) & (kline_df.index <= k1)]
            # 比较结果为空（时区/格式异常），回退全量
            kline_df = clipped if not clipped.empty else kline_df

        return self._klines_to_records(kline_df)

    @staticmethod
    def _accumulate_symbol_metrics(result: dict[str, Any], aggregated: dict[str, Any]) -> None:
        """把单品种结果的标量指标累加进聚合 dict（原地修改）。

        累加类求和，起止时间分别取 min/max；trades/positions 等嵌套字段跳过。
        """
        sum_keys = {
            "total_pnl",
            "orders_accepted",
            "orders_rejected",
            "fills",
            "total_orders",
            "total_fees",
            "events_processed",
            "duration_secs",
            "trade_count",
            "bar_count",
        }
        min_keys = {"data_start_ns"}
        max_keys = {"data_end_ns"}

        for k, v in result.items():
            if not isinstance(v, (int, float)):
                continue
            if k in sum_keys:
                aggregated[k] = aggregated.get(k, 0) + v
            elif k in min_keys:
                cur = aggregated.get(k)
                aggregated[k] = v if cur is None else min(cur, v)
            elif k in max_keys:
                cur = aggregated.get(k)
                aggregated[k] = v if cur is None else max(cur, v)

    def _build_factors_payload(
        self,
        feature_frames: dict[str, pd.DataFrame],
        loaded_data: dict[str, Any],
        raw_results: dict[str, Any],
        per_symbol_results: dict[str, dict[str, Any]] | None,
        factor_names: list[str],
        strategy_params: dict[str, Any],
        symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        """从特征帧构建因子分析载荷（列式时序 + 交易时点因子值 + 归因）。

        返回 {symbol: {names, thresholds, time_series, trade_factors, attribution}}。
        任一环节失败时该 symbol 条目为 {}，不阻断回测主流程。
        """
        from factor.attribution import compute_factor_attribution

        payload: dict[str, dict[str, Any]] = {}

        for key, entry in loaded_data.items():
            parts = key.rsplit("_", 1)
            symbol = parts[0] if len(parts) > 1 else key
            feat_df = entry.get("feature_dataframe")
            if feat_df is None or feat_df.empty:
                continue

            try:
                # ① 列式紧凑时序：共享 timestamps + 每因子一列值
                idx = feat_df.index
                ts_ms = (pd.to_datetime(idx, utc=True).tz_convert("UTC").asi8 // 1_000_000).tolist()
                formatted = pd.to_datetime(idx, utc=True).strftime("%Y-%m-%d %H:%M:%S").tolist()

                time_series: dict[str, Any] = {
                    "timestamps": ts_ms,
                    "formatted_times": formatted,
                }
                for col in feat_df.columns:
                    time_series[col] = [None if pd.isna(v) else float(v) for v in feat_df[col]]

                # ② 交易时点因子值：按 trade timestamp 在特征帧中 lookup
                # 单品种用 raw_results.trades；多品种用 per_symbol_results[symbol].trades
                if len(symbols) == 1 or not per_symbol_results:
                    trades = raw_results.get("trades", [])
                else:
                    trades = per_symbol_results.get(symbol, {}).get("trades", [])
                trade_factors = self._trade_factors_lookup(feat_df, trades)

                # ③ 归因：取该品种的收盘价计算 forward returns
                closes = self._extract_closes(entry.get("data"), idx)
                attribution = compute_factor_attribution(feat_df, closes) if closes is not None else {}

                payload[symbol] = {
                    "names": list(feat_df.columns),
                    "thresholds": self._extract_thresholds(strategy_params),
                    "time_series": time_series,
                    "trade_factors": trade_factors,
                    "attribution": attribution,
                }
            except Exception as e:
                logger.warning(f"品种 {symbol} 因子载荷构建失败: {e}")
                payload[symbol] = {}

        return payload

    @staticmethod
    def _trade_factors_lookup(feat_df: pd.DataFrame, trades: list[dict]) -> list[dict[str, Any]]:
        """按每笔 trade 的 timestamp 在特征帧中查找最接近的 bar 的因子值。"""
        if not trades:
            return []

        # 特征帧索引转毫秒，用于快速查找
        idx_ms = pd.to_datetime(feat_df.index, utc=True).tz_convert("UTC").asi8 // 1_000_000
        result: list[dict[str, Any]] = []
        for trade in trades:
            ts = trade.get("timestamp")
            if ts is None:
                result.append({})
                continue
            # 后端 trade timestamp 可能是秒级或毫秒级，统一转毫秒
            ts_ms = int(ts) if int(ts) > 10_000_000_000 else int(ts) * 1000
            # 找 <= ts_ms 的最大索引位置
            pos = int(idx_ms.searchsorted(ts_ms, side="right")) - 1
            if pos < 0 or pos >= len(idx_ms):
                result.append({})
                continue
            row = feat_df.iloc[pos]
            entry: dict[str, Any] = {
                "timestamp": int(idx_ms[pos]),
                "formatted_time": pd.to_datetime(feat_df.index[pos], utc=True).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for col in feat_df.columns:
                v = row[col]
                entry[col] = None if pd.isna(v) else float(v)
            result.append(entry)
        return result

    @staticmethod
    def _extract_closes(data: Any, idx: pd.Index) -> pd.Series | None:
        """从 loaded_data 的 data（DataFrame）中提取收盘价序列，对齐到 feat_df 索引。

        特征帧索引是 naive datetime64[ns]（factor.engine._timestamps_to_datetime），
        K 线数据索引是 UTC tz-aware DatetimeIndex，必须统一时区再求交集，
        否则 intersection 为空导致归因无法计算。
        """
        if data is None or not isinstance(data, pd.DataFrame) or "close" not in data.columns:
            return None
        try:
            closes = data["close"].copy()
            # 统一到 UTC tz-aware
            if closes.index.tz is None:
                closes.index = closes.index.tz_localize("UTC")
            else:
                closes.index = closes.index.tz_convert("UTC")
            feat_idx = pd.DatetimeIndex(idx)
            if feat_idx.tz is None:
                feat_idx = feat_idx.tz_localize("UTC")
            else:
                feat_idx = feat_idx.tz_convert("UTC")
            common = closes.index.intersection(feat_idx)
            if len(common) < 2:
                return None
            return closes.loc[common]
        except Exception:
            return None

    @staticmethod
    def _extract_thresholds(strategy_params: dict[str, Any]) -> dict[str, dict[str, float]]:
        """从策略参数提取因子阈值（buy_threshold/sell_threshold）。"""
        factor_name = strategy_params.get("factor_name")
        if not factor_name:
            return {}
        thresholds: dict[str, dict[str, float]] = {}
        entry: dict[str, float] = {}
        if "buy_threshold" in strategy_params:
            entry["buy"] = float(strategy_params["buy_threshold"])
        if "sell_threshold" in strategy_params:
            entry["sell"] = float(strategy_params["sell_threshold"])
        if entry:
            thresholds[factor_name] = entry
        return thresholds

    def _convert_backtest_result(self, result) -> dict:
        """将 BacktestResult 对象转换为字典格式（兼容原有 API）"""
        return {
            "initial_capital": result.final_nav - result.total_pnl,
            "final_nav": result.final_nav,
            "total_pnl": result.total_pnl,
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "nav_peak": result.nav_peak,
            "orders_accepted": result.orders_accepted,
            "orders_rejected": result.orders_rejected,
            "fills": result.fills,
            "total_orders": result.total_orders,
            "events_processed": result.events_processed,
            "duration_secs": result.duration_secs,
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_fees": result.total_fees,
            "trade_count": len(result.trade_records),
            "trades": list(result.trade_records),
            "equity_curve": list(result.equity_curve),
            "data_start_ns": result.data_start_ns,
            "data_end_ns": result.data_end_ns,
            "bar_count": result.bar_count,
        }

    # ─── Rust 原生回测路径（axon_quant.worker.BacktestRunner） ───

    def _run_rust_single(
        self,
        strategy,
        df: pd.DataFrame,
        symbol: str,
        init_cash: float,
        force_liquidate: bool = False,
        feature_dataframe: pd.DataFrame | None = None,
        funding_df: pd.DataFrame | None = None,
        futures: bool = False,
        settle: str = "usd_margin",
        contract_size: float = 1.0,
    ) -> BacktestResult:
        """Rust 原生回测：BacktestRunner 逐 bar 编排策略，结果映射回 QuantCell 契约。

        与 BacktestLoop 路径的差异仅在编排层（循环在 Rust 侧而非 Python 逐 bar），
        两者共用同一个 axon BacktestEngine，撮合语义一致。

        - `feature_dataframe`：逐 bar 因子帧 → 转成 per-bar state（`state["features"]` +
          `cross_sectional_rank`），Rust 侧透传给 Python 策略；
        - `funding_df` + `futures`：期货资金费查找表（键为 bar 纳秒时间戳）→ Rust 逐 bar 结算；
        - `settle` + `contract_size`：永续品种的保证金结算方式与合约乘数（仅 futures 生效，
          口径由调用方给出，见 run_backtest 里的 market 推导与 ponytail 说明）。
        """
        from axon_quant import worker

        from strategy.rust_adapter import RustStrategyAdapter, _normalize_symbol

        # 与 BacktestLoop 一致：先做 K 线清洗归一（单调时间/无 NaN/Inf）
        df = clean_ohlcv_df(df)
        bars = self._df_to_rust_bars(df)
        bar_ts_list = [b["timestamp"] for b in bars]
        rust_symbol = _normalize_symbol(symbol)

        states_by_symbol = self._build_rust_states(feature_dataframe, bar_ts_list, rust_symbol)
        funding_by_symbol = self._build_rust_funding(funding_df, rust_symbol, futures)

        runner = worker.BacktestRunner(
            initial_cash=init_cash,
            futures=futures,
            force_liquidate=force_liquidate,
            settle=settle,
            contract_size=contract_size,
        )
        # symbol 显式传给适配器：多品种「独立资金池」分支（run_backtest 的 else 分支）
        # 复用同一个策略实例（config.symbol 固定为首品种），而本次回测品种是入参 symbol。
        # 不覆盖会让引擎按策略 symbol 建 instrument，把入参品种的数据跑到首品种上，
        # 同时让 states/funding 的键与引擎查找键错位。
        adapter = RustStrategyAdapter(strategy, initial_cash=init_cash, symbol=symbol)
        runner.add_strategy(adapter)
        # 统一入口：单品种包装成「单 symbol 网格」（无 None 缺口），与共享资金池同一路径
        rust_result = runner.run(
            bars_by_symbol={rust_symbol: list(bars)},
            states_by_symbol=states_by_symbol,
            funding_by_symbol=funding_by_symbol,
        )
        return self._map_rust_result(rust_result, df, symbol)

    def _run_rust_multi(
        self,
        strategies_by_symbol: dict[str, Any],
        entries: dict[str, dict[str, Any]],
        init_cash: float,
        capital_budget: float | None,
        force_liquidate: bool = False,
        futures: bool = False,
        settle: str = "usd_margin",
        contract_size: float = 1.0,
        trading_mode: str = "spot",
        time_range: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, list[dict]]]:
        """共享资金池：单 BacktestRunner + N 品种共享账户编排。

        与 ``_run_rust_single`` 的差异：
        - 只跑**一次** ``run``（单 engine、一笔 ``init_cash``），而不是每品种一个 runner
        - 各品种 bar 对齐到统一时间网格（``shared_capital_grid``），缺口以 ``None`` 占位
          （Rust 侧前向填充价格参与盯市，但不触发策略决策）
        - 每个品种一个策略实例（共享模式的必要条件：策略内部滚动状态必须按品种隔离）
        - 成交按 ``TradeRecord.instrument`` 拆分回各品种

        Returns:
            (聚合结果 dict, {品种: round-trip 成交列表}, {品种: fills 笔数})
            fills 与 round-trip 条数不同口径（逐笔开/平均计 vs 开平配对），
            详情页「交易次数」沿用引擎 fills 口径，故单独回传
        """
        from axon_quant import worker

        from backtest.shared_capital_grid import align_bars_to_grid, build_shared_grid
        from strategy.rust_adapter import RustStrategyAdapter, _normalize_symbol

        # 1) 各品种清洗 → Rust bars → 网格并集（Rust 侧要求所有品种等长，故按并集对齐）
        bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
        rust_to_qc: dict[str, str] = {}
        for sym, entry in entries.items():
            df = clean_ohlcv_df(entry["data"])
            bars_by_symbol[sym] = self._df_to_rust_bars(df)
            # Rust 侧 instrument 用 BASE/QUOTE 归一化名，回拆成交时需还原成 QuantCell 品种名
            rust_to_qc[_normalize_symbol(sym)] = sym
        grid = build_shared_grid(bars_by_symbol)
        grid_len = len(grid)

        # 2) 按网格对齐 bar（缺口 None，由 Rust 前向填充价格）
        aligned_bars = {_normalize_symbol(sym): align_bars_to_grid(bars, grid) for sym, bars in bars_by_symbol.items()}

        # 3) 逐 bar state 按同一网格对齐（复用 _build_rust_states 的键口径）；
        #    funding 查找表语义同 _run_rust_single（仅 futures 时非空）
        states_by_symbol: dict[str, list] = {}
        funding_by_symbol: dict[str, dict[int, tuple[float, float]]] = {}
        for sym, entry in entries.items():
            rust_symbol = _normalize_symbol(sym)
            states_by_symbol.update(self._build_rust_states(entry.get("feature_dataframe"), grid, rust_symbol))
            funding_by_symbol.update(
                self._build_rust_funding(
                    self._load_funding(sym, trading_mode, time_range),
                    rust_symbol,
                    futures,
                )
            )

        # 4) 单 runner 注册全部品种的策略适配器（共享同一笔 init_cash）
        runner = worker.BacktestRunner(
            initial_cash=init_cash,
            futures=futures,
            force_liquidate=force_liquidate,
            settle=settle,
            contract_size=contract_size,
        )
        for strategy in strategies_by_symbol.values():
            runner.add_strategy(RustStrategyAdapter(strategy, initial_cash=init_cash))

        rust_result = runner.run(
            bars_by_symbol=aligned_bars,
            states_by_symbol=states_by_symbol or None,
            funding_by_symbol=funding_by_symbol or None,
            capital_budget=capital_budget,
        )

        # 5) 结果映射：共享账户没有单一 df，数据时间范围显式取网格端点
        agg = self._convert_backtest_result(
            self._map_rust_result(
                rust_result,
                None,
                "PORTFOLIO",
                data_range=(grid[0], grid[-1]) if grid_len else (0, 0),
            )
        )

        # 6) 成交按 instrument 拆分回各品种（rust_result.trades 每个 fill 带 instrument 元组）
        per_symbol_raw: dict[str, list[dict]] = {sym: [] for sym in entries}
        for tr in list(rust_result.trades):
            inst = tr.get("instrument")
            if not inst:
                continue
            qc_sym = rust_to_qc.get(f"{inst[1]}/{inst[2]}")
            if qc_sym is not None:
                per_symbol_raw[qc_sym].append(tr)

        per_symbol_trades = {
            sym: BacktestLoop._format_round_trip_trades(raw, sym) for sym, raw in per_symbol_raw.items()
        }
        # 6b. 成交笔数按 fills_detail 的 instrument 拆分：`trade_records` 是开平配对后的
        #     round-trip（条数≠fill 数），而详情页「交易次数」沿用引擎 fills 口径（开+平各计一笔），
        #     只有逐笔 fill 明细能精确归属到品种，且各品种之和 == 账户总 fills。
        per_symbol_fills: dict[str, int] = dict.fromkeys(entries, 0)
        for fr in list(rust_result.fills_detail):
            inst = fr.get("instrument")
            if not inst:
                continue
            qc_sym = rust_to_qc.get(f"{inst[1]}/{inst[2]}")
            if qc_sym is not None:
                per_symbol_fills[qc_sym] += 1
        return agg, per_symbol_trades, per_symbol_fills

    @staticmethod
    def _build_rust_states(
        feature_dataframe: pd.DataFrame | None,
        bar_ts_list: list[int],
        rust_symbol: str,
    ) -> dict[str, list]:
        """因子帧 → Rust per-bar state 列表（`{symbol: [state或None, ...]}`）。

        口径对齐 BacktestLoop 的 feature_lookup：DatetimeIndex 按纳秒建键，
        整数索引按原值建键；无匹配 bar 的 state 置 None（不注入，保持 ctx 上次值）。
        """
        if feature_dataframe is None or feature_dataframe.empty:
            return {}

        if isinstance(feature_dataframe.index, pd.DatetimeIndex):
            lookup = {int(pd.Timestamp(i).timestamp() * 1_000_000_000): row for i, row in feature_dataframe.iterrows()}
        else:
            lookup = {int(i): row for i, row in feature_dataframe.iterrows()}

        per_bar: list[dict | None] = []
        for ts in bar_ts_list:
            row = lookup.get(ts)
            if row is None:
                per_bar.append(None)
                continue
            # cross_sectional_rank 不进 features，改由 bar 承载（对齐 BacktestLoop）
            feats = {str(k): float(v) for k, v in row.items() if k != "cross_sectional_rank" and pd.notna(v)}
            state: dict = {"features": feats}
            rank_v = row.get("cross_sectional_rank")
            if rank_v is not None and pd.notna(rank_v):
                state["cross_sectional_rank"] = int(rank_v)
            per_bar.append(state)

        return {rust_symbol: per_bar}

    @staticmethod
    def _build_rust_funding(
        funding_df: pd.DataFrame | None,
        rust_symbol: str,
        futures: bool,
    ) -> dict[str, dict[int, tuple[float, float]]]:
        """资金费率 DataFrame → Rust 查找表 `{symbol: {bar_纳秒: (rate, mark_price)}}`。

        仅期货模式构建；键为 bar 纳秒时间戳，Rust 侧命中即入队结算。
        """
        if not futures or funding_df is None or funding_df.empty:
            return {}
        sched: dict[int, tuple[float, float]] = {}
        for ts_idx, row in funding_df.iterrows():
            ts_ns = int(pd.Timestamp(ts_idx).timestamp() * 1_000_000_000)
            rate = float(row.get("funding_rate", 0.0) or 0.0)
            mark = float(row.get("mark_price", 0.0) or 0.0)
            sched[ts_ns] = (rate, mark)
        return {rust_symbol: sched}

    @staticmethod
    def _df_to_rust_bars(df: pd.DataFrame) -> list[dict[str, Any]]:
        """OHLCV DataFrame → Rust BacktestRunner 期望的 bar dict 列表（纳秒时间戳）。

        列名统一小写；时间列优先 "timestamp"，否则取首列。
        """
        out = df.reset_index()
        out.columns = [str(c).lower() for c in out.columns]
        time_col = "timestamp" if "timestamp" in out.columns else out.columns[0]
        # DatetimeIndex → int64 纳秒（as_unit 显式定标，避免原 dtype 单位漂移）
        ts_ns = pd.to_datetime(out[time_col], utc=True).dt.as_unit("ns").astype("int64").tolist()
        volume = out["volume"] if "volume" in out.columns else pd.Series(0.0, index=out.index)
        return [
            {
                "timestamp": int(ts_ns[i]),
                "open": float(out["open"].iloc[i]),
                "high": float(out["high"].iloc[i]),
                "low": float(out["low"].iloc[i]),
                "close": float(out["close"].iloc[i]),
                "volume": float(volume.iloc[i]),
            }
            for i in range(len(out))
        ]

    @staticmethod
    def _map_rust_result(
        rust_result,
        df: pd.DataFrame | None,
        symbol: str,
        data_range: tuple[int, int] | None = None,
    ) -> BacktestResult:
        """Rust BacktestResult → QuantCell BacktestResult（口径与 BacktestLoop 完全一致）。

        关键换算：max_drawdown_pct / win_rate 由引擎的小数形式 ×100 转显示口径。
        `data_range`：共享模式没有单一 df（`df=None`），由调用方显式给出数据时间范围
        （网格端点纳秒）；独立模式不传，保持既有 df 推导口径不变。
        """
        raw_max_dd_pct = float(rust_result.max_drawdown_pct)
        max_drawdown_usd = float(rust_result.nav_peak) * raw_max_dd_pct

        # equity_curve：逐 bar NAV 曲线（bar_nav_curve），格式适配前端 EquityChart
        # 0.21.0 起同时携带 balance（存款）曲线：引擎 bar_balance_curve 与 bar_nav_curve
        # 逐帧对齐，equity - balance 即该帧浮盈；旧 wheel 无该属性时退化为 0（不画存款曲线）
        raw_balance_curve = getattr(rust_result, "bar_balance_curve", None) or []
        equity_curve = []
        for idx, (ts_ns, nav) in enumerate(rust_result.bar_nav_curve):
            dt_str = datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            nav_float = float(nav)
            balance_float = float(raw_balance_curve[idx][1]) if idx < len(raw_balance_curve) else 0.0
            equity_curve.append(
                {
                    "datetime": dt_str,
                    "equity": nav_float,
                    "balance": balance_float,
                    "formatted_time": dt_str,
                    "timestamp": int(ts_ns / 1e6),  # 毫秒级时间戳
                }
            )

        trade_records = BacktestLoop._format_round_trip_trades(list(rust_result.trades), symbol)

        # 数据时间范围：显式 data_range（共享模式取网格端点）优先，其次 timestamp 列，
        # 最后从 DatetimeIndex 推导（与 BacktestLoop.run 口径一致）
        if data_range is not None:
            data_start_ns, data_end_ns = int(data_range[0]), int(data_range[1])
        elif df is None or len(df) == 0:
            data_start_ns = 0
            data_end_ns = 0
        elif "timestamp" in df.columns:
            data_start_ns = int(df["timestamp"].iloc[0])
            data_end_ns = int(df["timestamp"].iloc[-1])
        else:
            data_start_ns = int(pd.Timestamp(df.index[0]).timestamp() * 1e9)
            data_end_ns = int(pd.Timestamp(df.index[-1]).timestamp() * 1e9)

        return BacktestResult(
            total_pnl=float(rust_result.total_pnl),
            total_orders=int(rust_result.orders_accepted) + int(rust_result.orders_rejected),
            fills=int(rust_result.fills),
            final_nav=float(rust_result.final_nav),
            max_drawdown=max_drawdown_usd,
            orders_accepted=int(rust_result.orders_accepted),
            orders_rejected=int(rust_result.orders_rejected),
            events_processed=int(rust_result.events_processed),
            duration_secs=float(rust_result.duration_secs),
            total_fees=float(rust_result.total_fees),
            win_rate=float(rust_result.win_rate) * 100.0,
            sharpe_ratio=float(rust_result.sharpe_ratio),
            nav_peak=float(rust_result.nav_peak),
            max_drawdown_pct=raw_max_dd_pct * 100.0,
            trade_records=trade_records,
            equity_curve=equity_curve,
            data_start_ns=data_start_ns,
            data_end_ns=data_end_ns,
            bar_count=len(df) if df is not None else 0,
            final_positions=dict(rust_result.final_positions),
        )

    @staticmethod
    def _klines_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
        """清洗后的 K 线 DataFrame → JSON 友好的 list[dict]（回放页 kline_data）

        klinecharts 要求毫秒时间戳，同时附 formatted_time 便于排障。
        """
        import json as _json

        out = df.reset_index()
        out.columns = [str(c).lower() for c in out.columns]
        time_col = "timestamp" if "timestamp" in out.columns else out.columns[0]
        ts = pd.to_datetime(out[time_col], utc=True)
        # klinecharts 要求毫秒；先统一到 ms 精度再取整数值，
        # 避免 astype("int64") 直接取原 dtype(usize/ns/s) 单位漂移
        out[time_col] = ts.dt.as_unit("ms").astype("int64").tolist()
        out["formatted_time"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
        # to_dict 后 ndarray 不利于 JSON 序列化，先转 records 再 round-trip 保证纯 JSON 类型
        return _json.loads(out.to_json(orient="records", date_format="iso"))

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str]:
        """
        解析交易对符号，提取基础货币和计价货币

        Args:
            symbol: 交易对符号（如 "BTCUSDT", "BTC/USDT", "BTC-USDT"）

        Returns:
            tuple: (base, quote) 如 ("BTC", "USDT")
        """
        for sep in ["/", "-", "_"]:
            if sep in symbol:
                parts = symbol.split(sep)
                return parts[0].upper(), parts[1].upper()
        if len(symbol) > 3:
            return symbol[:3].upper(), symbol[3:].upper()
        # 短符号(如 "ETH")直接视为 base,quote 兜底 USDT;
        # 不能返回嵌套 tuple,否则 base, quote = ... 解包时 quote 是 tuple
        return symbol.upper(), "USDT"

    def _load_funding(self, symbol: str, trading_mode: str, time_range: str | None):
        """futures 模式加载资金费率 DataFrame 供 BacktestLoop 透传给引擎。"""
        if trading_mode != "futures":
            return None
        start = end = None
        if time_range:
            try:
                from utils.validation import parse_time_range

                s, e = parse_time_range(time_range)
                start = s.strftime("%Y-%m-%d") if s else None
                end = e.strftime("%Y-%m-%d") if e else None
            except Exception as exc:
                logger.warning(f"解析资金费率时间范围失败: {exc}")
        try:
            funding_df = self.provider.load_funding_rate(symbol, start=start, end=end)
            if funding_df is None or funding_df.empty:
                logger.warning(f"{symbol} 无资金费率数据，将不进行资金费用结算")
                return None
            return funding_df
        except Exception as exc:
            logger.warning(f"{symbol} 资金费率加载失败，跳过: {exc}")
            return None

    def _format_results(
        self,
        results: dict,
        symbols: list[str],
        timeframe: str,
        strategy_name: str,
        per_symbol_results: dict,
        capital_mode: str = "per_symbol",
    ) -> dict:
        """汇总多品种回测结果

        Args:
            results: 跨品种聚合后的指标(PnL/fills/fees 累加,data_start 取 min 等)
            per_symbol_results: 每个品种单独的原始结果,用于 results_by_symbol[k].metrics
                填单品种 metrics(否则 output_results 显示的"贡献盈亏"是聚合 PnL)
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称
            capital_mode: 资金使用方式。per_symbol=N 个独立资金池（现状口径）；
                shared=组合共享资金池（单账户，各品种条目是同一账户的拆分视图：
                成交派生指标按品种归因，账户级指标保持账户口径）

        Returns:
            多品种汇总 dict
        """
        from backtest.result_formatter_service import ResultFormatterService

        # 计算 portfolio-level 指标(从 per_symbol_results 重算,不能简单 sum 百分比类)
        n = len(per_symbol_results)
        total_pnl = results.get("total_pnl", 0.0)
        shares_equity = capital_mode == "shared"
        # 共享模式：成交数取各品种拆分后之和（引擎聚合值含全部 instrument，口径会偏）
        total_trades = (
            sum(len(r.get("trades", [])) for r in per_symbol_results.values())
            if shares_equity
            else results.get("trade_count", 0)
        )
        total_fills = results.get("fills", 0)

        if shares_equity:
            # 单账户：初始权益即**一笔** init_cash（引擎结果 initial_capital = final_nav - total_pnl），
            # 绝不是 per_symbol × n；initial_capital 缺失/为 0 时由 final_nav - total_pnl 反推，
            # 不 fallback 成 100000 污染组合指标
            final_equity = float(results.get("final_nav") or 0.0)
            initial_equity = float(results.get("initial_capital") or 0.0) or (final_equity - total_pnl)
        else:
            # initial_equity / final_equity:每品种独立资金池(每 run 都 initial_cash 起步)
            # 从实际参与回测的首个品种读初始资金：按请求 symbols[0] 取会在该品种
            # 无数据被剔除时拿到空 dict，fallback 成 100000 污染组合初始权益
            first_result = next(iter(per_symbol_results.values()), {})
            initial_cash_per_symbol = first_result.get("initial_capital", 100000.0)
            initial_equity = initial_cash_per_symbol * n  # N 个独立资金池
            final_equity = initial_equity + total_pnl
        # total_return:百分比
        total_return = (total_pnl / initial_equity * 100.0) if initial_equity > 0 else 0.0

        # win_rate:跨品种重新统计(从 per_symbol 各自的 wins / trades_count 算)
        # 没 trade records 数据时 fallback 到 fills 兜底(撮合成交笔数 = 交易笔数近似)
        winning_trades = 0
        losing_trades = 0
        for r in per_symbol_results.values():
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
        win_rate = winning_trades / total_trades * 100.0 if total_trades > 0 else 0.0

        # max_drawdown:独立资金池取最大回撤品种的 pct(不该 sum)；共享模式分品种无定义，
        # 直接用引擎给出的单账户聚合值
        if shares_equity:
            max_dd_pct = float(results.get("max_drawdown_pct", 0.0))
        else:
            max_dd_pct = 0.0
            for r in per_symbol_results.values():
                sym_dd = r.get("max_drawdown_pct", 0.0)
                if sym_dd > max_dd_pct:
                    max_dd_pct = sym_dd

        # sharpe_ratio:共享模式单账户夏普由引擎聚合给出（分品种加权在此无意义）；
        # 独立模式仍按 fills 加权平均
        if shares_equity:
            sharpe_ratio = float(results.get("sharpe_ratio", 0.0))
        elif n == 1:
            sharpe_ratio = first_result.get("sharpe_ratio", 0.0)
        else:
            if total_fills > 0:
                sharpe_ratio = (
                    sum(r.get("sharpe_ratio", 0.0) * r.get("fills", 0) for r in per_symbol_results.values())
                    / total_fills
                )
            else:
                sharpe_ratio = sum(r.get("sharpe_ratio", 0.0) for r in per_symbol_results.values()) / n

        # 填充 results 的 portfolio-level 字段,让 output_results 能读到
        # (原本只有 sum/min/max 字段,initial_equity/win_rate 等需显式计算)
        results["initial_equity"] = initial_equity
        results["final_equity"] = final_equity
        results["total_return"] = total_return
        results["win_rate"] = win_rate
        results["max_drawdown"] = max_dd_pct  # 用 pct 字段(百分比,单位一致)
        results["sharpe_ratio"] = sharpe_ratio

        # portfolio 级别的 metrics 使用聚合数据格式化
        # format_axon_results 按 initial_capital/final_nav/max_drawdown_pct 取数，
        # 聚合 dict 里的对应键是 initial_equity/final_equity/max_drawdown，
        # 必须改名注入，否则 fallback 到 100000/0.0，组合指标与权益曲线互相矛盾
        # 组合（「全部」）视图也需要真实输入，否则 SQN/凯利/暴露时间/波动率/平均回撤
        # 等派生指标在组合视图恒为 0。成交取各品种拼接；曲线：共享模式即单账户曲线，
        # 独立资金池模式按时间戳并集对齐后逐点求和（复用读取侧同一函数）
        merged_trades = [t for r in per_symbol_results.values() for t in (r.get("trades") or [])]
        if shares_equity:
            merged_curve = list(results.get("equity_curve") or [])
        else:
            # 函数内 import：backtest.service 在模块级 import engine_service，避免循环导入
            from backtest.service import BacktestService

            # 只喂 dict 点：_merge_equity_curves 的契约是 list[dict]，历史/合成
            # 结果里残缺的非 dict 点（如旧写法 [(ts, equity)]）直接跳过，避免其 .get 崩
            merged_curve = BacktestService._merge_equity_curves(
                [[p for p in (r.get("equity_curve") or []) if isinstance(p, dict)] for r in per_symbol_results.values()]
            )
        portfolio_payload = ResultFormatterService.format_axon_results(
            results={
                **results,
                "initial_capital": initial_equity,
                "final_nav": final_equity,
                "max_drawdown_pct": max_dd_pct,
                "trades": merged_trades,
                "equity_curve": merged_curve,
            },
            symbol=symbols[0] if symbols else "PORTFOLIO",
            timeframe=timeframe,
            strategy_name=strategy_name,
        ).get("portfolio", {})
        # 组合条目：trades 保留各品种拼接（formatter 的盈利/亏损、盈亏比、最佳/最差交易
        # 全部从 trades 现算，置空会退化成「盈利 0 / 亏损=trade_count / 盈亏比 0」的假值）；
        # 上面传入的合并曲线只用于计算派生指标（平均回撤/年化波动率），组合条目的曲线
        # 维持既有形状——共享模式回填单账户曲线，独立模式留空（读取侧 build_portfolio_view
        # 自行按时间戳并集合并，避免结果 JSON 额外膨胀）
        portfolio_payload["equity_curve"] = list(results.get("equity_curve") or []) if shares_equity else []

        return {
            "strategy_name": strategy_name,
            "symbols": symbols,
            "timeframe": timeframe,
            "is_multi_symbol": True,
            # 资金使用方式：组合视图/回放按模式切换聚合口径（Task 7 消费）
            "capital_mode": capital_mode,
            "results_by_symbol": {
                # 只遍历实际参与回测的品种：无数据品种不在 per_symbol_results 里，
                # 按请求 symbols 全集遍历会让缺失品种以空 dict 走 fallback，
                # 产出初始权益 100000 / 最终权益 0 的假条目污染详情页
                symbol: ResultFormatterService.format_axon_results(
                    results=per_symbol_results[symbol],
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_name=strategy_name,
                ).get(f"{symbol}_{timeframe}", {})
                for symbol in per_symbol_results
            },
            "portfolio": portfolio_payload,
            # 保留 _meta 和 account 信息
            "_meta": {
                "engine": "axon",
                "strategy": strategy_name,
                "timestamp": int(datetime.now().timestamp()),
                "formatted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "account": {
                "starting_balance": initial_equity,
                "final_nav": final_equity,
                "total_pnl": total_pnl,
            },
        }
