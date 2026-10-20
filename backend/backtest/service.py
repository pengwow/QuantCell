"""
回测服务模块（FastAPI层）

提供回测任务的HTTP API服务层。
本模块只负责：
- 任务管理（创建/更新/查询/删除）
- 结果持久化（保存到文件系统）
- 进度跟踪集成
- API响应构建

所有业务逻辑已迁移到独立的服务模块：
- backtest/engine_service.py - 引擎执行逻辑
- backtest/data_provider.py - 数据加载逻辑
- backtest/strategy_loader_service.py - 策略加载逻辑
- backtest/result_formatter_service.py - 结果格式化逻辑
"""

import json
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest.result_analysis import ResultAnalyzer


class BacktestService:
    """
    回测服务（FastAPI薄封装）

    只做参数转换、错误处理和结果持久化，
    不包含任何回测业务逻辑。

    使用示例：
        service = BacktestService()
        task_id = service.create_task(...)
        result = service.run_backtest(task_id)
        results_list = service.get_result_list(limit=10)
    """

    def __init__(self):
        """初始化回测服务"""
        self.results_dir = Path(__file__).resolve().parent.parent / "data" / "backtest_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        from utils.logger import LogType, get_logger

        self.logger = get_logger(self.__class__.__name__, LogType.APPLICATION)

    def create_task(
        self,
        strategy_name: str,
        strategy_params: dict[str, Any],
        symbols: list[str],
        timeframes: list[str],
        engine_type: str,
        config: dict | None = None,
        task_id: Any = None,
    ) -> Any:
        """
        创建回测任务

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_type: 引擎类型 (default/event)
            config: 回测配置
            task_id: 可选的任务ID（如果提供则使用，否则自动生成）

        Returns:
            任务ID（与传入的 task_id 相同类型，或生成的整数）
        """
        if task_id is None:
            task_id = int(datetime.now().timestamp() * 1000)

        task_data = {
            "id": task_id,
            "strategy_name": strategy_name,
            "strategy_params": strategy_params,
            "symbols": symbols,
            "timeframes": timeframes,
            "engine_type": engine_type,
            "config": config or {},
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        # 保存任务信息
        task_file = self._get_task_file(task_id)
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f, indent=2, ensure_ascii=False, default=str)

        self.logger.info(f"创建回测任务: {task_id}")

        return task_id

    def run_backtest(self, task_id: Any, progress_tracker=None) -> dict[str, Any]:
        """
        执行回测任务

        Args:
            task_id: 任务ID
            progress_tracker: 进度跟踪器（可选）

        Returns:
            dict: 回测结果

        Raises:
            ValueError: 当任务不存在或配置无效时
        """
        # 加载任务配置
        task = self._load_task(task_id)
        if not task:
            msg = f"任务不存在: {task_id}"
            raise ValueError(msg)

        try:
            # 更新状态为运行中
            self._update_task_status(task_id, "running")

            if progress_tracker:
                # 更新数据准备阶段进度（30% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="data_prep",
                    data={
                        "progress": 100.0,
                        "status": "completed",
                        "message": "数据准备完成",
                    },
                )
                # 更新执行阶段进度（60% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="execution",
                    data={
                        "progress": 0.0,
                        "status": "running",
                        "current_symbol": task["symbols"][0] if task.get("symbols") else "",
                        "total_symbols": len(task.get("symbols", [])),
                        "completed_symbols": 0,
                        "message": "开始执行回测...",
                    },
                )

            # 调用事件驱动引擎服务执行回测
            from backtest.data_provider import BacktestDataProvider
            from backtest.engine_service import EventDrivenBacktestService

            data_provider = BacktestDataProvider()
            engine_config = task.get("config", {})

            service = EventDrivenBacktestService(data_provider)

            # 引擎每开始一个品种回调一次，把 0/N → (N-1)/N 的真实进度
            # 写入 tracker；跑完后的 100% 仍由下方统一更新
            def _on_symbol_progress(done: int, total: int, symbol: str) -> None:
                if not progress_tracker or total <= 0:
                    return
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="execution",
                    data={
                        "progress": round(done / total * 100, 2),
                        "status": "running",
                        "current_symbol": symbol,
                        "total_symbols": total,
                        "completed_symbols": done,
                        "message": f"正在回测: {symbol}",
                    },
                )

            raw_result = service.run_backtest(
                strategy_name=task["strategy_name"],
                strategy_params=task.get("strategy_params", {}),
                symbols=task["symbols"],
                timeframes=task["timeframes"],
                engine_config={**engine_config, "log_level": "WARNING"},
                show_progress=False,
                factor_names=engine_config.get("factor_names"),
                on_symbol_progress=_on_symbol_progress if progress_tracker else None,
            )
            # 成功/失败口径取实际结果：无数据品种在 engine 层被剔除（skipped_symbols），
            # 不能把请求清单硬编码成"全部成功"，否则提示数量与详情页实际品种数不一致
            skipped = raw_result.get("skipped_symbols") or {}
            result = {
                "status": "completed",
                "message": "回测执行成功",
                "successful_currencies": [s for s in task["symbols"] if s not in skipped],
                "failed_currencies": list(skipped.keys()),
                "skipped_symbols": skipped,
                "results": raw_result,
            }

            if progress_tracker:
                # 更新执行阶段完成（60% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="execution",
                    data={
                        "progress": 100.0,
                        "status": "completed",
                        "completed_symbols": len(task.get("symbols", [])),
                        "message": "回测执行完成",
                    },
                )
                # 更新分析阶段进度（10% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="analysis",
                    data={
                        "progress": 50.0,
                        "status": "running",
                        "message": "正在保存结果...",
                    },
                )

            # 保存结果
            self._save_result(task_id, result)

            # 更新状态为完成
            self._update_task_status(task_id, "completed")

            if progress_tracker:
                # 更新分析阶段完成（10% 权重）- 总体 100%
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="analysis",
                    data={
                        "progress": 100.0,
                        "status": "completed",
                        "message": "回测结果已保存",
                    },
                )
                # 标记整个任务为已完成状态，确保前端轮询能够正确停止
                progress_tracker.complete_progress(task_id)

            return result

        except Exception as e:
            self.logger.error(f"回测执行失败: {e}")
            self._update_task_status(task_id, "failed")
            raise

    def get_result(self, result_id: Any) -> dict | None:
        """
        获取单个回测结果

        Args:
            result_id: 结果ID（即任务ID）

        Returns:
            dict or None: 回测结果
        """
        result_file = self._get_result_file(result_id)

        if not result_file.exists():
            return None

        with open(result_file, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def extract_symbol_entries(results: Any) -> dict[str, dict[str, Any]]:
        """归一化结果 JSON 的 results 字段，返回 {symbol: 品种条目} 有序映射。

        回测结果有两种结构：
        - 单品种：{"ETH/USDT_15m": {symbol, timeframe, metrics, trades, ...}}
        - 多品种：{is_multi_symbol: true, results_by_symbol: {symbol: 条目, ...},
          portfolio, account, _meta, ...}

        多品种封装里混有 strategy_name/symbols 等辅助键，单品种条目则以
        "SYMBOL_TIMEFRAME" 为键；统一按 entry.symbol 建索引，过滤非品种键。
        """
        if not isinstance(results, dict):
            return {}

        # 多品种封装结构（results_by_symbol 存在即为多品种，is_multi_symbol 双重确认）
        by_symbol = results.get("results_by_symbol")
        if isinstance(by_symbol, dict) and by_symbol:
            return {sym: entry for sym, entry in by_symbol.items() if isinstance(entry, dict)}

        # 单品种结构：跳过 portfolio/_meta 等无 symbol 字段的辅助条目
        entries: dict[str, dict[str, Any]] = {}
        for entry in results.values():
            if isinstance(entry, dict) and isinstance(entry.get("symbol"), str) and entry["symbol"]:
                entries[entry["symbol"]] = entry
        return entries

    @staticmethod
    def filter_contract_trades(trades: Any) -> list[dict[str, Any]]:
        """仅保留完整 round-trip 契约记录（timestamp + entry_price 必有）。

        entry_price 排除旧 fill 双写格式，timestamp 排除无 trade_id/symbol 的
        中间版；旧结果文件不迁移，过滤后上层按空成交处理（前端空态提示）。
        """
        if not isinstance(trades, list):
            return []
        return [
            tr
            for tr in trades
            if isinstance(tr, dict) and tr.get("entry_price") is not None and tr.get("timestamp") is not None
        ]

    @staticmethod
    def build_portfolio_view(results: dict[str, Any]) -> dict[str, Any]:
        """组装多品种回测的「全部（组合）」视图。

        引擎对多品种默认是 N 个独立资金池各自回测（共享资金池模式下为单账户），
        组合视图口径：
        - metrics：直接用回测落盘时算好的 portfolio.metrics（总收益率等已按
          独立资金池合计口径二次计算，不能对百分比类指标做简单平均）
        - trades/positions：各品种拼接（round-trip 记录自带 symbol），交易按时间升序
        - equity_curve：独立资金池模式下各品种时间轴不一致（实测长度/起止均不同），
          按时间戳并集对齐后逐时点求和；品种首个真实点之前按初始权益填充（尚未开跑），
          中间缺失时点前向填充。共享资金池模式（capital_mode == "shared"）下各品种
          携带的是同一条单账户曲线，直接取 portfolio.equity_curve（求和会得到 N 倍假值）

        Args:
            results: 结果 JSON 的 results 字段（多品种封装结构）

        Returns:
            dict: {metrics, trades, equity_curve, positions}
        """
        entries = BacktestService.extract_symbol_entries(results)
        portfolio = results.get("portfolio") if isinstance(results, dict) else None
        metrics = portfolio.get("metrics") if isinstance(portfolio, dict) else None
        metrics = metrics if isinstance(metrics, list) else []

        # 交易/持仓拼接：交易 timestamp 为秒级，直接按其排序
        all_trades: list[dict[str, Any]] = []
        all_positions: list[dict[str, Any]] = []
        for entry in entries.values():
            # 旧格式记录不迁移（被 filter 剔除），由前端空态提示
            all_trades.extend(BacktestService.filter_contract_trades(entry.get("trades")))
            all_positions.extend(p for p in (entry.get("positions") or []) if isinstance(p, dict))
        all_trades.sort(key=lambda t: t.get("timestamp") or 0)

        # 共享资金池模式：各品种条目携带的是同一条单账户曲线，组合曲线直接取
        # portfolio.equity_curve；否则（独立资金池）按时间戳并集对齐后逐时点求和
        merged_curve = (
            list(portfolio.get("equity_curve") or [])
            if isinstance(results, dict)
            and results.get("capital_mode") == "shared"
            and isinstance(portfolio, dict)
            and portfolio.get("equity_curve")
            else BacktestService._merge_equity_curves([entry.get("equity_curve") or [] for entry in entries.values()])
        )

        return {
            "metrics": metrics,
            "trades": all_trades,
            "equity_curve": merged_curve,
            "positions": all_positions,
        }

    @staticmethod
    def _merge_equity_curves(curves: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """把多条独立资金池权益曲线按时间戳并集对齐后求和。

        单条曲线缺失时点的处理：首个真实点之前按该品种首点权益填充（尚未开跑，
        权益即初始资金）；其后缺失时点前向填充（权益停留在最近一个真实值）。
        空曲线（无任何点）按零贡献处理。
        """
        valid_curves = [c for c in curves if c]
        if not valid_curves:
            return []

        # 时间戳并集（curve timestamp 为毫秒级）
        all_ts_set: set[int] = set()
        for curve in valid_curves:
            for point in curve:
                ts = point.get("timestamp")
                if ts is not None:
                    all_ts_set.add(ts)
        all_ts = sorted(all_ts_set)
        if not all_ts:
            return []

        # 每个品种预建 timestamp -> 点 映射与初始/末次权益
        prepared: list[tuple[dict[int, dict[str, Any]], dict[str, float], dict[str, Any]]] = []
        for curve in valid_curves:
            ts_to_point = {p["timestamp"]: p for p in curve if p.get("timestamp") is not None}
            first_point = curve[0]
            initial = {
                "equity": float(first_point.get("equity") or first_point.get("Equity") or 0.0),
                "balance": float(first_point.get("balance") or 0.0),
                "margin": float(first_point.get("margin") or 0.0),
            }
            prepared.append((ts_to_point, initial, first_point))

        merged: list[dict[str, Any]] = []
        # 每个品种在并集扫描中的最近真实点（None 表示尚未开跑，用初始值）
        last_points: list[dict[str, Any] | None] = [None] * len(prepared)

        for ts in all_ts:
            total = {"equity": 0.0, "balance": 0.0, "margin": 0.0}
            ref_point: dict[str, Any] | None = None
            for idx, (ts_to_point, initial, _first) in enumerate(prepared):
                point = ts_to_point.get(ts)
                if point is not None:
                    last_points[idx] = point
                    ref_point = point
                current = last_points[idx]
                if current is None:
                    # 该品种尚未出现首个真实点：权益按初始资金计
                    values = initial
                else:
                    values = {
                        "equity": float(current.get("equity") or current.get("Equity") or 0.0),
                        "balance": float(current.get("balance") or 0.0),
                        "margin": float(current.get("margin") or 0.0),
                    }
                for k in total:
                    total[k] += values[k]

            # formatted_time/datetime 取该时点任一真实点（ts 必属于某品种）
            formatted_time = (ref_point or {}).get("formatted_time")
            merged.append(
                {
                    "timestamp": ts,
                    "datetime": (ref_point or {}).get("datetime") or formatted_time,
                    "formatted_time": formatted_time,
                    "equity": round(total["equity"], 8),
                    "balance": round(total["balance"], 8),
                    "margin": round(total["margin"], 8),
                }
            )

        return merged

    # interval -> pandas 网格频率
    _GRID_FREQ = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1D",
        "1w": "1W",
    }

    def build_portfolio_replay(self, results: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """构建全局视角回测回放时间轴。

        与单品种回放（逐根 K 线）不同，全局回放以统一时间网格为时钟：
        - 网格范围取实际数据（各品种 K 线/成交时间）的并集，频率取回测 interval；
          不能用配置的 start/end——实测回测实际数据范围可能与配置不一致
        - account：每个网格点的组合权益/余额/保证金（合并权益曲线 ffill 对齐），
          并派生累计盈亏、滚动回撤、当日盈亏
        - position_events：逐笔成交重建净持仓后的稀疏事件（带移动加权均价）
        - holding_prices：仅在各品种净持仓非零的网格区间给出收盘价点，供前端算浮盈

        Args:
            results: 结果 JSON 的 results 字段
            config: 回测配置（取 interval / initial_cash）

        Returns:
            dict: 全局回放时间轴数据
        """
        entries = self.extract_symbol_entries(results)
        interval = str(config.get("interval") or "15m")
        init_cash = float(config.get("initial_cash") or 0.0)
        # 资金使用方式：shared=组合共享资金池。共享模式下各品种条目携带的是
        # 同一条单账户合并曲线，组合曲线直接取 portfolio.equity_curve，不能再对各品种求和
        capital_mode = str(config.get("capital_mode") or "per_symbol")
        shared_curve: list[dict[str, Any]] | None = None
        if capital_mode == "shared":
            portfolio = results.get("portfolio") if isinstance(results, dict) else None
            if isinstance(portfolio, dict) and portfolio.get("equity_curve"):
                shared_curve = list(portfolio["equity_curve"])

        # ---- 合并 round-trip 成交（秒级 timestamp 开仓时间），按时间排序 ----
        # 旧格式/中间版记录不迁移（被 filter 剔除），回放按空成交处理
        all_trades: list[dict[str, Any]] = []
        for entry in entries.values():
            all_trades.extend(BacktestService.filter_contract_trades(entry.get("trades")))
        all_trades.sort(key=lambda t: t.get("timestamp") or 0)

        # ---- 各品种 K 线 -> 有序毫秒时间戳与收盘价（供网格范围与持仓浮盈取值）----
        klines_ts: dict[str, list[int]] = {}
        klines_close: dict[str, list[float]] = {}
        for sym, entry in entries.items():
            pairs = [
                (int(k["timestamp"]), float(k.get("close") or 0.0))
                for k in (entry.get("klines") or [])
                if isinstance(k, dict) and k.get("timestamp") is not None
            ]
            pairs.sort(key=lambda x: x[0])
            klines_ts[sym] = [p[0] for p in pairs]
            klines_close[sym] = [p[1] for p in pairs]

        # ---- 统一时间网格：实际数据时间并集 ----
        bounds = [ts for seq in klines_ts.values() for ts in (seq[0], seq[-1])]
        trade_bounds = [int(t["timestamp"]) * 1000 for t in all_trades] if all_trades else []
        bounds.extend(trade_bounds)
        if not bounds:
            return {
                "symbols": list(entries.keys()),
                "interval": interval,
                "init_cash": init_cash,
                "capital_mode": capital_mode,
                "start_ms": 0,
                "end_ms": 0,
                "grid_count": 0,
                "grid_step_ms": 900_000,
                "account": [],
                "position_events": [],
                "holding_prices": {},
                "trades": [],
            }
        start_ms, end_ms = min(bounds), max(bounds)
        freq = self._GRID_FREQ.get(interval, "15min")
        # ponytail: 网格点数无上限保护，15m 频率可覆盖约 3 年；更细周期+超长区间会增大响应体
        # 不用 DatetimeIndex.asi8：pandas 2.x 起底层单位不再固定纳秒，直接取毫秒
        grid = [
            int(ts.timestamp() * 1000)
            for ts in pd.date_range(
                pd.to_datetime(start_ms, unit="ms"),
                pd.to_datetime(end_ms, unit="ms"),
                freq=freq,
            )
        ]
        # 等距网格只回传起点/步长/点数，播放端按 索引 -> start+step*i 自行换算，避免 5 万点数组
        grid_step = grid[1] - grid[0] if len(grid) > 1 else 900_000

        # ---- 合并权益曲线：账户序列只保留权益实际变化点（播放端 ffill）----
        if shared_curve:
            # 共享模式：单账户曲线即组合曲线；各品种条目携带的是同一条曲线，
            # 若按并集求和会得到 N 倍假值
            merged = shared_curve
            total_initial = init_cash if init_cash > 0 else float(shared_curve[0].get("equity") or 0.0)
        else:
            merged = self._merge_equity_curves([entry.get("equity_curve") or [] for entry in entries.values()])
            total_initial = sum(
                float((entry.get("equity_curve") or [{}])[0].get("equity", init_cash) or init_cash)
                for entry in entries.values()
                if entry.get("equity_curve")
            )

        # 账户稀疏序列：累计盈亏 / 滚动回撤 / 当日盈亏（UTC 日界）
        account: list[list[float]] = []
        peak = total_initial
        day_first_equity: dict[str, float] = {}
        for p in merged:
            t, equity = int(p["timestamp"]), float(p["equity"])
            peak = max(peak, equity)
            drawdown = (equity - peak) / peak if peak > 0 else 0.0
            day_key = datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m-%d")
            if day_key not in day_first_equity:
                day_first_equity[day_key] = equity
            account.append(
                [
                    t,
                    round(equity, 4),
                    # balance / margin 用 get 兜底：共享模式下 merged 直接来自引擎的
                    # bar_nav_curve（只有 equity/timestamp），没有这两个键；非共享模式
                    # 经 _merge_equity_curves 会补上且恒为 0，两者取值一致
                    round(float(p.get("balance") or 0.0), 4),
                    round(float(p.get("margin") or 0.0), 4),
                    round(equity - total_initial, 4),
                    round(drawdown, 6),
                    round(equity - day_first_equity[day_key], 4),
                ]
            )

        # ---- 持仓重建：round-trip 展开为逐笔 fill 事件（时间轴/持仓需要逐笔粒度）----
        # 开仓 buy + 平仓 sell 各一条，pnl 归平仓事件；exit_timestamp 缺失时退化为开仓时刻
        fill_events: list[dict[str, Any]] = []
        for tr in all_trades:
            size = float(tr.get("size") or 0.0)
            if not tr.get("symbol") or size == 0.0:
                continue
            entry_ts = int(tr.get("timestamp") or 0)
            fill_events.append(
                {
                    "symbol": tr["symbol"],
                    "side": "BUY",
                    "quantity": size,
                    "price": float(tr.get("entry_price") or 0.0),
                    "timestamp": entry_ts,
                    "pnl": 0.0,
                }
            )
            fill_events.append(
                {
                    "symbol": tr["symbol"],
                    "side": "SELL",
                    "quantity": size,
                    "price": float(tr.get("exit_price") or 0.0),
                    "timestamp": int(tr.get("exit_timestamp") or 0) or entry_ts,
                    "pnl": float(tr.get("pnl") or 0.0),
                }
            )
        fill_events.sort(key=lambda e: e["timestamp"])

        position_events, holdings = self._rebuild_positions(fill_events, grid, klines_ts, klines_close)

        # 新契约记录本身即展示所需全集，直接透传（无需再裁剪白名单）
        slim_trades = all_trades

        return {
            "symbols": list(entries.keys()),
            "interval": interval,
            "init_cash": round(total_initial or init_cash, 4),
            "capital_mode": capital_mode,
            "start_ms": grid[0],
            "end_ms": grid[-1],
            "grid_count": len(grid),
            "grid_step_ms": grid_step,
            # [t, equity, balance, margin, cum_pnl, drawdown, day_pnl]
            "account": account,
            "position_events": position_events,
            # {symbol: [[t, close], ...]} 仅净持仓非零的网格点
            "holding_prices": holdings,
            "trades": slim_trades,
        }

    @staticmethod
    def _rebuild_positions(
        trades: list[dict[str, Any]],
        grid: list[int],
        klines_ts: dict[str, list[int]],
        klines_close: dict[str, list[float]],
    ) -> tuple[list[dict[str, Any]], dict[str, list[list[float]]]]:
        """从成交流重建净持仓序列，并给出持仓期间的收盘价点。

        现货允许双向：BUY 记 +quantity、SELL 记 -quantity。同方向加仓按
        移动加权计算均价；反向成交减仓时均价不变；穿越 0 翻仓后剩余部分以
        成交价为新开仓均价。

        Returns:
            (position_events, holding_prices)
            - position_events：每笔成交一条，含成交后净持仓/均价/网格时刻
            - holding_prices：{symbol: [[t, close], ...]}，仅净持仓非零的网格点
        """
        # 每笔成交归入其发生后的第一个网格点（该笔在该格末已成交）
        events: list[dict[str, Any]] = []
        events_by_grid: dict[int, list[dict[str, Any]]] = {}
        # 净持仓状态：symbol -> (qty, avg_cost)
        holding: dict[str, list[float]] = {}

        for tr in trades:
            # 输入恒为 service 层展开的 fill 事件（symbol/side/quantity/price/timestamp/pnl）
            sym = tr.get("symbol") or ""
            price = float(tr.get("price") or 0.0)
            qty = float(tr.get("quantity") or 0.0)
            side = str(tr.get("side") or "").upper()
            signed = qty if side == "BUY" else -qty if side == "SELL" else qty
            if not sym or qty == 0.0 or price == 0.0:
                continue

            old_qty, old_avg = holding.get(sym, [0.0, 0.0])
            new_qty = old_qty + signed
            if old_qty == 0.0:
                new_avg = price
            elif (old_qty > 0) == (signed > 0):
                # 同方向加仓：移动加权均价
                new_avg = (abs(old_qty) * old_avg + abs(signed) * price) / abs(new_qty)
            elif abs(signed) < abs(old_qty):
                # 反向减仓但未翻仓：均价不变
                new_avg = old_avg
            else:
                # 穿越 0 翻仓：反向剩余部分以成交价为均价
                new_avg = price
            holding[sym] = [new_qty, new_avg]

            grid_idx = bisect_left(grid, int(tr["timestamp"]) * 1000)
            t = grid[min(grid_idx, len(grid) - 1)]
            event = {
                "t": t,
                "ts": int(tr["timestamp"]),
                "symbol": sym,
                "side": side or tr.get("direction") or "",
                "qty": round(new_qty, 10),
                "traded_qty": round(signed, 10),
                "avg_cost": round(new_avg, 10),
                "price": price,
                "pnl": float(tr.get("pnl") or 0.0),
            }
            events.append(event)
            events_by_grid.setdefault(t, []).append(event)

        # ---- 扫描网格，维护持仓状态，仅在净持仓非零时记录收盘价点 ----
        holding_prices: dict[str, list[list[float]]] = {s: [] for s in holding}
        state: dict[str, list[float]] = {}
        for t in grid:
            for ev in events_by_grid.get(t, []):
                state[ev["symbol"]] = [ev["qty"], ev["avg_cost"]]
            for sym, qty_avg in state.items():
                qty = qty_avg[0]
                if qty == 0.0:
                    continue
                ts_seq = klines_ts.get(sym) or []
                idx = bisect_right(ts_seq, t) - 1
                if idx < 0:
                    continue  # 该品种此时尚无 K 线，无法取价
                holding_prices[sym].append([t, klines_close[sym][idx]])

        return events, holding_prices

    def get_latest_result(self) -> dict | None:
        """获取最新的回测结果"""
        results_files = sorted(
            list(self.results_dir.glob("result_*.json")),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        if not results_files:
            return None

        latest_file = results_files[0]

        with open(latest_file, encoding="utf-8") as f:
            return json.load(f)

    def get_backtest_symbols(self, backtest_id: str | None = None) -> dict[str, Any]:
        """
        获取指定回测涉及的货币对列表

        从回测结果 JSON 中提取所有有交易数据的品种，返回前端期望的字符串数组结构。
        （旧实现是扫描本地数据目录、忽略 backtest_id，语义错误已废弃。）

        Args:
            backtest_id: 回测ID（用于定位结果文件）

        Returns:
            dict: 标准响应格式 {
                "status": "success",
                "data": {"symbols": ["ETH/USDT", "BTC/USDT"]}
            }
        """
        symbols: list[str] = []

        try:
            if not backtest_id:
                self.logger.warning("get_backtest_symbols 缺少 backtest_id")
                return {"status": "success", "data": {"symbols": symbols}}

            json_result = self.get_result(backtest_id)
            if not isinstance(json_result, dict):
                self.logger.warning(f"回测结果文件不存在: {backtest_id}")
                return {"status": "success", "data": {"symbols": symbols}}

            # 兼容单品种（键 "ETH/USDT_15m"）与多品种（results_by_symbol 封装）两种结构
            results = json_result.get("results") or {}
            symbols = list(self.extract_symbol_entries(results).keys())

            self.logger.info(f"回测 {backtest_id} 涉及 {len(symbols)} 个货币对: {symbols}")

        except Exception as e:
            self.logger.error(f"获取回测货币对列表失败: {e}")

        return {"status": "success", "data": {"symbols": symbols}}

    def get_result_list(self, limit: int = 20, offset: int = 0, status_filter: str | None = None) -> list[dict]:
        """
        获取回测结果列表

        Args:
            limit: 返回数量限制
            offset: 偏移量
            status_filter: 状态过滤 (pending/running/completed/failed)

        Returns:
            list: 任务列表
        """
        tasks_dir = self.results_dir.parent / "backtest_tasks"
        if not tasks_dir.exists():
            return []

        task_files = sorted(
            list(tasks_dir.glob("task_*.json")),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        results = []

        for task_file in task_files[offset:]:
            if len(results) >= limit:
                break

            with open(task_file, encoding="utf-8") as f:
                task = json.load(f)

            if status_filter and task.get("status") != status_filter:
                continue

            results.append(
                {
                    "id": task.get("id"),
                    "strategy_name": task.get("strategy_name"),
                    "symbols": ", ".join(task.get("symbols", [])),
                    "timeframes": ", ".join(task.get("timeframes", [])),
                    "engine_type": task.get("engine_type"),
                    "status": task.get("status"),
                    "created_at": task.get("created_at"),
                    "updated_at": task.get("updated_at"),
                }
            )

        return results

    def delete_task(self, task_id: Any) -> bool:
        """
        删除回测任务及其结果

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功删除
        """
        task_file = self._get_task_file(task_id)
        result_file = self._get_result_file(task_id)

        deleted = False

        if task_file.exists():
            task_file.unlink()
            deleted = True

        if result_file.exists():
            result_file.unlink()
            deleted = True

        if deleted:
            self.logger.info(f"删除回测任务: {task_id}")

        return deleted

    def delete_backtest_result(self, backtest_id: str) -> bool:
        """
        删除回测结果（路由层兼容接口）

        Args:
            backtest_id: 回测ID

        Returns:
            bool: 是否成功删除
        """
        try:
            task_id = int(backtest_id) if backtest_id.isdigit() else backtest_id
        except ValueError, AttributeError:
            task_id = backtest_id
        return self.delete_task(task_id)

    def stop_backtest(self, task_id: str) -> dict[str, Any]:
        """
        终止回测任务

        Args:
            task_id: 任务ID

        Returns:
            dict: 终止结果
        """
        try:
            numeric_id = int(task_id) if task_id.isdigit() else task_id
        except ValueError, AttributeError:
            numeric_id = task_id

        task = self._load_task(numeric_id)
        if not task:
            return {"status": "error", "message": "回测任务不存在"}

        if task.get("status") not in ("running", "pending"):
            return {"status": "error", "message": "回测任务不在运行中"}

        self._update_task_status(numeric_id, "stopped")
        return {"status": "success", "message": "回测已终止"}

    def analyze_backtest(self, backtest_id: str) -> dict[str, Any]:
        """
        分析回测结果

        读取结果文件并用 ResultAnalyzer 做统计分析，
        兼容传统单品种与 axon 单/多品种结果格式。

        Args:
            backtest_id: 回测ID

        Returns:
            dict: 分析结果
        """
        result = self.get_result(backtest_id)
        if not result:
            return {"status": "error", "message": "回测结果不存在"}

        raw_result = result.get("results")
        if not isinstance(raw_result, dict) or not raw_result:
            return {"status": "error", "message": "回测结果为空或格式无效"}

        try:
            analysis = ResultAnalyzer().analyze(raw_result)
        except Exception as e:
            self.logger.error(f"回测结果分析失败: {e}")
            return {"status": "error", "message": f"回测结果分析失败: {e}"}

        return {"status": "success", "backtest_id": backtest_id, "analysis": analysis}

    def upload_strategy_file(self, strategy_name: str, file_content: str) -> bool:
        """
        上传策略文件

        Args:
            strategy_name: 策略名称
            file_content: 策略文件内容

        Returns:
            bool: 是否上传成功
        """
        strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)

        file_path = strategies_dir / f"{strategy_name}.py"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            self.logger.info(f"策略文件已保存: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存策略文件失败: {e}")
            return False

    def _load_task(self, task_id: Any) -> dict | None:
        """加载任务配置"""
        task_file = self._get_task_file(task_id)

        if not task_file.exists():
            return None

        with open(task_file, encoding="utf-8") as f:
            return json.load(f)

    def _update_task_status(self, task_id: Any, status: str):
        """更新任务状态"""
        task = self._load_task(task_id)
        if task:
            task["status"] = status
            task["updated_at"] = datetime.now().isoformat()

            task_file = self._get_task_file(task_id)
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task, f, indent=2, ensure_ascii=False, default=str)

    def _save_result(self, task_id: Any, result: dict):
        """保存回测结果"""
        result_file = self._get_result_file(task_id)

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)

        self.logger.info(f"保存回测结果: {result_file}")

    def _get_task_file(self, task_id: Any) -> Path:
        """获取任务文件路径"""
        tasks_dir = self.results_dir.parent / "backtest_tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        return tasks_dir / f"task_{task_id}.json"

    def _get_result_file(self, result_id: Any) -> Path:
        """获取结果文件路径"""
        return self.results_dir / f"result_{result_id}.json"
