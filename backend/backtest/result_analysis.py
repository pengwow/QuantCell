"""
回测结果分析模块

提供回测结果的分析、序列化和可视化功能，包括：
- 结果统计分析
- 结果序列化（JSON/CSV）
- 结果加载
- 结果输出格式化
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


def _format_ts_iso(ts_ns: int) -> str:
    """纳秒时间戳 -> ISO 8601 字符串(本地时区)

    优先用 fromtimestamp 兼容 timestamp;若 ts_ns 异常则原样返回
    """
    if not isinstance(ts_ns, (int, np.integer)) or ts_ns <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts_ns / 1e9).strftime("%Y-%m-%d %H:%M:%S")
    except OSError, OverflowError, ValueError:
        return str(ts_ns)


def _metrics_to_dict(raw_metrics: Any) -> dict[str, Any]:
    """指标归一化：format_axon_results 产出 [{key, value, ...}] 列表格式，统一转 {key: value}"""
    if isinstance(raw_metrics, dict):
        return raw_metrics
    if isinstance(raw_metrics, list):
        return {m["key"]: m["value"] for m in raw_metrics if isinstance(m, dict) and "key" in m}
    return {}


def _print_data_range(metrics_or_result: dict) -> None:
    """打印回测数据的时间范围 + bar 数"""
    start_ns = metrics_or_result.get("data_start_ns", 0)
    end_ns = metrics_or_result.get("data_end_ns", 0)
    bar_count = metrics_or_result.get("bar_count", 0)
    if start_ns <= 0 or end_ns <= 0:
        return
    start_iso = _format_ts_iso(start_ns)
    end_iso = _format_ts_iso(end_ns)
    duration_secs = (end_ns - start_ns) / 1e9
    if duration_secs >= 86400:
        duration_str = f"{duration_secs / 86400:.1f} 天"
    elif duration_secs >= 3600:
        duration_str = f"{duration_secs / 3600:.1f} 小时"
    else:
        duration_str = f"{duration_secs:.0f} 秒"
    # 面向终端用户的展示信息（CLI 输出路径），用 print 而非 logger
    print(f"数据范围: {start_iso} → {end_iso} ({duration_str}),共 {bar_count} 根 K 线")


class QuantCellJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理pandas/numpy等特殊类型"""

    def default(self, obj):
        # 处理 pandas NA/NaT
        if obj is pd.NA or obj is pd.NaT:
            return None

        # 处理 numpy 类型
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.floating, float)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)

        # 处理 datetime
        if isinstance(obj, datetime):
            return obj.isoformat()

        # 处理 Pandas Timestamp
        if isinstance(obj, pd.Timestamp):
            return obj.strftime("%Y-%m-%d %H:%M:%S")

        # 处理 Pandas Timedelta
        if isinstance(obj, pd.Timedelta):
            return str(obj)

        # 处理 bytes
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="ignore")

        # 默认处理
        try:
            return super().default(obj)
        except TypeError:
            # 如果无法序列化，转为字符串
            try:
                return str(obj)
            except Exception:
                return None


class ResultAnalyzer:
    """回测结果分析器"""

    # 结果字典中的框架键，不是真实品种结果，分析时跳过
    _FRAMEWORK_KEYS = frozenset(
        {
            "portfolio",
            "account",
            "_meta",
            "strategy_name",
            "symbols",
            "timeframe",
            "is_multi_symbol",
            "results_by_symbol",
        }
    )

    def analyze(self, results: dict[str, Any]) -> dict[str, Any]:
        """
        分析回测结果

        参数：
            results: 回测结果字典，兼容三种形态：
                - 传统单品种: {symbol_timeframe: result}
                - axon 单品种 format_axon_results: {symbol_tf: {...}, account, portfolio, _meta}
                - axon 多品种 _format_results: {is_multi_symbol, results_by_symbol, portfolio, ...}

        返回：
            Dict[str, Any]: 分析后的结果摘要
        """
        if not isinstance(results, dict):
            results = {}

        # 带 portfolio 键的组合结果（axon 格式的单品种/多品种都带 portfolio）
        if isinstance(results.get("portfolio"), dict):
            return self._analyze_portfolio_results(results)

        # 传统单交易对回测结果
        summary = {
            "total_symbols": 0,
            "total_trades": 0,
            "total_pnl": 0.0,
            "avg_win_rate": 0.0,
            "avg_sharpe": 0.0,
            "symbols": [],
        }

        win_rates = []
        sharpe_ratios = []

        for key, result in results.items():
            # 跳过框架键和非 dict 值（如 strategy_name、_meta 等标量/列表字段）
            if key in self._FRAMEWORK_KEYS or not isinstance(result, dict):
                continue

            symbol_summary = self._analyze_single_result(key, result)
            summary["symbols"].append(symbol_summary)

            # 累计统计
            summary["total_trades"] += symbol_summary["trade_count"]
            summary["total_pnl"] += symbol_summary["total_pnl"]

            if "win_rate" in symbol_summary:
                win_rates.append(symbol_summary["win_rate"])
            if "sharpe_ratio" in symbol_summary:
                sharpe_ratios.append(symbol_summary["sharpe_ratio"])

        summary["total_symbols"] = len(summary["symbols"])

        # 计算平均值
        if win_rates:
            summary["avg_win_rate"] = sum(win_rates) / len(win_rates)
        if sharpe_ratios:
            summary["avg_sharpe"] = sum(sharpe_ratios) / len(sharpe_ratios)

        return summary

    def _analyze_portfolio_results(self, results: dict[str, Any]) -> dict[str, Any]:
        """分析投资组合回测结果（portfolio.metrics 为列表格式，归一化后取值）"""
        portfolio_metrics = _metrics_to_dict(results["portfolio"].get("metrics", {}))

        summary = {
            "is_portfolio": True,
            "total_symbols": 0,
            "total_trades": portfolio_metrics.get("total_trades", 0),
            "total_pnl": portfolio_metrics.get("total_pnl", 0.0),
            "win_rate": portfolio_metrics.get("win_rate", 0.0),
            "sharpe_ratio": portfolio_metrics.get("sharpe_ratio", 0.0),
            "max_drawdown": portfolio_metrics.get("max_drawdown", 0.0),
            "total_return": portfolio_metrics.get("total_return", 0.0),
            "initial_equity": portfolio_metrics.get("initial_equity", 0.0),
            "final_equity": portfolio_metrics.get("final_equity", 0.0),
            "symbols": [],
        }

        # 分析各交易对：多品种在 results_by_symbol，其余从顶层非框架键提取
        # （results_by_symbol 优先，避免与顶层键重复时按品种名去重）
        symbol_sources = [results.get("results_by_symbol", {}), results]
        seen: set[str] = set()

        for source in symbol_sources:
            if not isinstance(source, dict):
                continue
            for key, result in source.items():
                if key == "portfolio" or key in self._FRAMEWORK_KEYS or not isinstance(result, dict):
                    continue
                if key in seen:
                    continue
                seen.add(key)
                summary["symbols"].append(self._analyze_single_result(key, result))

        summary["total_symbols"] = len(summary["symbols"])
        return summary

    def _analyze_single_result(self, key: str, result: dict[str, Any]) -> dict[str, Any]:
        """分析单个交易对的结果（metrics 兼容 list 与 dict 两种格式）"""
        # 解析symbol和timeframe
        parts = key.split("_")
        symbol = parts[0] if parts else key
        timeframe = parts[1] if len(parts) > 1 else "unknown"

        result = result if isinstance(result, dict) else {}

        # 获取资金曲线
        cash = result.get("cash") or []
        init_cash = cash[0] if len(cash) > 0 else 0.0
        final_cash = cash[-1] if len(cash) > 0 else 0.0

        # 获取持仓
        positions = result.get("positions") or []
        if isinstance(positions, np.ndarray) and positions.ndim > 1:
            final_position = positions[-1, 0] if len(positions) > 0 else 0.0
        else:
            final_position = positions[-1] if len(positions) > 0 else 0.0

        # 获取交易数量
        trades = result.get("trades") or []
        trade_count = len(trades)

        # 获取指标（format_axon_results 产出 list 格式，统一转 dict）
        metrics = _metrics_to_dict(result.get("metrics", {}))

        return {
            "key": key,
            "symbol": symbol,
            "timeframe": timeframe,
            "init_cash": float(init_cash),
            "final_cash": float(final_cash),
            "final_position": float(final_position),
            "trade_count": trade_count,
            "total_pnl": float(metrics.get("total_pnl", 0)),
            "win_rate": float(metrics.get("win_rate", 0)),
            "sharpe_ratio": float(metrics.get("sharpe_ratio", 0)),
            "max_drawdown": float(metrics.get("max_drawdown", 0)),
            "profit_factor": float(metrics.get("profit_factor", 0)),
            "metrics": metrics,
        }

    def calculate_statistics(self, trades: list[dict], equity_curve: list[dict]) -> dict[str, Any]:
        """
        计算交易统计指标

        参数：
            trades: 交易列表
            equity_curve: 资金曲线

        返回：
            Dict[str, Any]: 统计指标
        """
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
            }

        # 计算盈亏
        profits = []
        losses = []

        for trade in trades:
            pnl = trade.get("pnl", 0) or trade.get("PnL", 0)
            if pnl > 0:
                profits.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))

        total_trades = len(trades)
        winning_trades = len(profits)
        losing_trades = len(losses)

        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        avg_profit = sum(profits) / len(profits) if profits else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        total_profit = sum(profits)
        total_loss = sum(losses)
        profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_profit": total_profit,
            "total_loss": total_loss,
        }


class ResultSerializer:
    """结果序列化器"""

    def to_json(self, results: dict[str, Any], file_path: str) -> bool:
        """
        将结果保存为JSON

        参数：
            results: 回测结果
            file_path: 文件路径

        返回：
            bool: 是否成功
        """
        try:
            # 序列化结果
            serializable_results = self._make_serializable(results)

            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True) if os.path.dirname(file_path) else None

            # 写入文件，使用自定义编码器
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    serializable_results,
                    f,
                    indent=2,
                    ensure_ascii=False,
                    cls=QuantCellJSONEncoder,
                )

            logger.info(f"结果已保存到: {file_path}")
            return True

        except Exception as e:
            logger.error(f"保存JSON失败: {e}")
            return False

    def to_csv(self, results: dict[str, Any], file_path: str) -> bool:
        """
        将结果保存为CSV

        参数：
            results: 回测结果
            file_path: 文件路径

        返回：
            bool: 是否成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True) if os.path.dirname(file_path) else None

            # 写入CSV
            with open(file_path, "w", encoding="utf-8") as f:
                # 写入表头
                f.write("Symbol,Cash,FinalPosition,TradeCount,")
                f.write("TotalPnl,TotalFees,WinRate,SharpeRatio,FinalEquity\n")

                # 写入数据
                for key, result in results.items():
                    metrics = result.get("metrics", {})
                    cash = result.get("cash", [])
                    positions = result.get("positions", [])

                    init_cash = cash[0] if len(cash) > 0 else 0.0

                    if isinstance(positions, np.ndarray) and positions.ndim > 1:
                        final_position = positions[-1, 0] if len(positions) > 0 else 0.0
                    else:
                        final_position = positions[-1] if len(positions) > 0 else 0.0

                    trades = result.get("trades", [])

                    f.write(f"{key},")
                    f.write(f"{float(init_cash):.2f},")
                    f.write(f"{float(final_position):.4f},")
                    f.write(f"{len(trades)},")
                    f.write(f"{float(metrics.get('total_pnl', 0)):.2f},")
                    f.write(f"{float(metrics.get('total_fees', 0)):.2f},")
                    f.write(f"{float(metrics.get('win_rate', 0)):.4f},")
                    f.write(f"{float(metrics.get('sharpe_ratio', 0)):.4f},")
                    f.write(f"{float(metrics.get('final_equity', 0)):.2f}\n")

            logger.info(f"结果已保存到: {file_path}")
            return True

        except Exception as e:
            logger.error(f"保存CSV失败: {e}")
            return False

    def from_json(self, file_path: str) -> dict[str, Any] | None:
        """
        从JSON加载结果

        参数：
            file_path: 文件路径

        返回：
            Optional[Dict[str, Any]]: 加载的结果
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载JSON失败: {e}")
            return None

    def _make_serializable(self, results: dict[str, Any]) -> dict[str, Any]:
        """将结果转换为可序列化的格式"""
        serializable = {}

        for key, result in results.items():
            # 处理特殊键（以下划线开头的元数据）
            if key.startswith("_"):
                # 对于元数据列表（如 _incomplete_data_info, _download_failures）
                if isinstance(result, list):
                    serializable[key] = [self._serialize_value(item) for item in result]
                else:
                    serializable[key] = self._serialize_value(result)
            elif isinstance(result, dict):
                # 正常的回测结果字典
                serializable[key] = self._serialize_single_result(result)
            else:
                # 顶层非 dict 的标量(str/int/bool/list),直接序列化
                # 修复:多品种 results 顶层有 strategy_name/symbols/timeframe/is_multi_symbol
                # 这些不是 dict,旧逻辑会调 .items() 崩溃('str' object has no attribute 'items')
                serializable[key] = self._serialize_value(result)

        return serializable

    def _serialize_single_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """序列化单个结果"""
        serialized = {}

        # 复制基本字段
        for k, v in result.items():
            if k == "cash":
                # NumPy数组转列表
                if isinstance(v, np.ndarray):
                    serialized[k] = v.tolist()
                else:
                    serialized[k] = v
            elif k == "positions":
                # 持仓列表（包含字典，可能有Timestamp）
                serialized[k] = self._serialize_positions(v)
            elif k == "equity_curve":
                # 权益曲线列表（包含字典，可能有Timestamp）
                serialized[k] = self._serialize_equity_curve(v)
            elif k == "metrics":
                # 指标字段 — 兼容两种格式:
                # 1) {key: value, ...} dict 格式(旧/内部)
                # 2) [{name, key, value, description, type}, ...] 列表格式(axon 前端展示)
                if isinstance(v, list):
                    serialized[k] = [self._serialize_value(item) for item in v]
                elif isinstance(v, dict):
                    serialized[k] = {
                        mk: float(mv)
                        if isinstance(mv, (np.floating, float))
                        else int(mv)
                        if isinstance(mv, (np.integer, int))
                        else str(mv)
                        for mk, mv in v.items()
                    }
                else:
                    serialized[k] = self._serialize_value(v)
            elif k in ["orders", "trades", "strategy_trades"]:
                # 交易/订单列表
                serialized[k] = self._serialize_orders(v)
            elif k == "indicators":
                # 指标
                serialized[k] = self._serialize_indicators(v)
            else:
                # 其他字段
                serialized[k] = self._serialize_value(v)

        return serialized

    def _serialize_equity_curve(self, equity_curve) -> list:
        """序列化权益曲线

        兼容两种点格式：
        - dict（事件驱动引擎）：{"timestamp": ..., "Equity": ...} — 走原逻辑
        - list/tuple（axon 适配层）：(time_ns, equity) — 转为 {"timestamp": t, "equity": e}
        """
        if not equity_curve:
            return []

        serialized = []
        for point in equity_curve:
            # axon 适配层产出 (ts_ns, equity) tuple/list,序列化为标准 dict
            if isinstance(point, (list, tuple)):
                if len(point) < 2:
                    continue
                ts_val, eq_val = point[0], point[1]
                serialized.append(
                    {
                        "timestamp": int(ts_val) if isinstance(ts_val, (int, np.integer)) else ts_val,
                        "equity": float(eq_val)
                        if isinstance(eq_val, (float, np.floating, int, np.integer))
                        else eq_val,
                    }
                )
                continue
            # 事件驱动引擎：dict 格式
            if not isinstance(point, dict):
                continue
            serialized_point = {}
            for key, value in point.items():
                if hasattr(value, "isoformat") or isinstance(value, datetime):  # Timestamp 类型
                    serialized_point[key] = value.isoformat()
                elif isinstance(value, (np.floating, float)):
                    serialized_point[key] = float(value)
                elif isinstance(value, (np.integer, int)):
                    serialized_point[key] = int(value)
                else:
                    serialized_point[key] = value
            serialized.append(serialized_point)
        return serialized

    def _serialize_orders(self, orders: list[dict]) -> list[dict]:
        """序列化订单/交易列表"""
        if not orders:
            return []

        serialized = []
        for idx, order in enumerate(orders):
            if not isinstance(order, dict):
                continue

            # 支持新的 trade_id 字段；如果不存在则使用 order_id 或自增索引
            # 如果不存在 trade_id，则使用 order_id 或自增索引
            trade_id = order.get("trade_id") or order.get("order_id") or str(idx + 1)

            serialized_order = {
                "trade_id": str(trade_id),
                "client_order_id": order.get("client_order_id", ""),
                "venue_order_id": order.get("venue_order_id", ""),
                "position_id": order.get("position_id", ""),
                "direction": order.get("direction", ""),
                "price": float(order.get("price", 0)) if order.get("price") is not None else 0.0,
                "volume": float(order.get("volume") or order.get("size") or 0),
                "status": order.get("status", "filled"),
                "timestamp": self._serialize_timestamp(order.get("timestamp")),
                "formatted_time": self._format_timestamp(order.get("timestamp")),
            }

            # 保留其他字段（如symbol, pnl, fees, commission等）
            for key, value in order.items():
                if key not in serialized_order and key != "order_id":  # 排除旧的 order_id
                    if hasattr(value, "isoformat") or isinstance(value, datetime):  # Timestamp类型
                        serialized_order[key] = value.isoformat()
                    elif isinstance(value, (np.floating, float)):
                        serialized_order[key] = float(value)
                    elif isinstance(value, (np.integer, int)):
                        serialized_order[key] = int(value)
                    elif isinstance(value, list):
                        # 处理列表（如 trade_ids）
                        serialized_order[key] = [
                            v.isoformat()
                            if hasattr(v, "isoformat")
                            else float(v)
                            if isinstance(v, (np.floating, float))
                            else int(v)
                            if isinstance(v, (np.integer, int))
                            else str(v)
                            if v is not None
                            else None
                            for v in value
                        ]
                    else:
                        serialized_order[key] = value

            serialized.append(serialized_order)

        return serialized

    def _serialize_positions(self, positions: list[dict]) -> list[dict]:
        """序列化持仓列表"""
        if not positions:
            return []

        serialized = []
        for position in positions:
            if not isinstance(position, dict):
                continue

            serialized_position = {}
            for key, value in position.items():
                if hasattr(value, "isoformat") or isinstance(value, datetime):  # Timestamp类型
                    serialized_position[key] = value.isoformat()
                elif isinstance(value, (np.floating, float)):
                    serialized_position[key] = float(value)
                elif isinstance(value, (np.integer, int)):
                    serialized_position[key] = int(value)
                elif isinstance(value, list):
                    # 处理列表（如 trade_ids）
                    serialized_position[key] = [
                        v.isoformat()
                        if hasattr(v, "isoformat")
                        else float(v)
                        if isinstance(v, (np.floating, float))
                        else int(v)
                        if isinstance(v, (np.integer, int))
                        else str(v)
                        if v is not None
                        else None
                        for v in value
                    ]
                else:
                    serialized_position[key] = value

            serialized.append(serialized_position)

        return serialized

    def _serialize_indicators(self, indicators: dict) -> dict:
        """序列化指标"""
        if not indicators:
            return {}

        serialized = {}
        for key, value in indicators.items():
            if isinstance(value, dict):
                serialized[str(key)] = {
                    k: float(v)
                    if isinstance(v, (np.floating, float))
                    else int(v)
                    if isinstance(v, (np.integer, int))
                    else v.isoformat()
                    if isinstance(v, datetime)
                    else str(v)
                    for k, v in value.items()
                }
            elif isinstance(value, (np.floating, float)):
                serialized[str(key)] = float(value)
            elif isinstance(value, (np.integer, int)):
                serialized[str(key)] = int(value)
            elif isinstance(value, datetime):
                serialized[str(key)] = value.isoformat()
            else:
                serialized[str(key)] = str(value)

        return serialized

    def _detect_timestamp_unit(self, timestamp: int) -> tuple[float, str]:
        """
        智能识别时间戳精度单位，返回(秒值, 原始单位)

        Returns:
            tuple: (转换为秒的值, 原始单位描述)
        """
        ts = int(timestamp)

        # 根据位数判断精度
        if ts > 1e18:  # 19位+: 纳秒
            return ts / 1e9, "nanoseconds"
        elif ts > 1e15:  # 16-18位: 微秒
            return ts / 1e6, "microseconds"
        elif ts > 1e12:  # 13-15位: 毫秒
            return ts / 1e3, "milliseconds"
        elif ts > 1e9:  # 10-12位: 秒
            return float(ts), "seconds"
        else:
            # 小于10位，可能是秒或无效值，按秒处理
            return float(ts), "seconds"

    def _serialize_timestamp(self, timestamp: Any) -> int:
        """
        序列化时间戳，保持原始精度不变
        直接返回原始值，不进行单位转换
        """
        if timestamp is None:
            return 0

        if isinstance(timestamp, datetime):
            # datetime 转换为秒级时间戳
            return int(timestamp.timestamp())
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
                return int(dt.timestamp())
            except ValueError, TypeError, OSError:
                return 0
        else:
            # 保持原始时间戳值不变
            return int(timestamp) if timestamp else 0

    def _format_timestamp(self, timestamp: Any) -> str:
        """
        格式化时间戳，智能识别精度并正确转换
        支持秒、毫秒、微秒、纳秒级别的时间戳
        """
        if timestamp is None:
            return ""

        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(timestamp, str):
            return timestamp
        else:
            try:
                ts = int(timestamp)
                # 智能识别时间戳精度并转换为秒
                ts_sec, _unit = self._detect_timestamp_unit(ts)

                dt = datetime.fromtimestamp(ts_sec)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError, TypeError, OSError:
                return str(timestamp)

    def _serialize_value(self, value: Any) -> Any:
        """序列化值，处理各种特殊类型"""
        # 使用 pandas 的 isna 检查（可以检测 pd.NA, pd.NaT, np.nan, None 等）
        try:
            if pd.isna(value):
                return None
        except TypeError, ValueError:
            # pd.isna 对自定义类型可能抛出异常，继续其他检查
            pass

        # 处理 numpy 数组
        if isinstance(value, np.ndarray):
            return [self._serialize_value(v) for v in value.tolist()]

        # 处理 numpy 浮点数（包括 nan 和 inf）
        elif isinstance(value, (np.floating, float)):
            if np.isnan(value) or np.isinf(value):
                return None
            return float(value)

        # 处理 numpy 整数
        elif isinstance(value, (np.integer, int)):
            return int(value)

        # 处理 datetime
        elif isinstance(value, datetime):
            return value.isoformat()

        # 处理 Pandas Timestamp
        elif isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d %H:%M:%S")

        # 处理 Pandas Timedelta
        elif isinstance(value, pd.Timedelta):
            return str(value)

        # 处理字典
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}

        # 处理列表和元组
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]

        # 处理 pandas Series
        elif isinstance(value, pd.Series):
            return [self._serialize_value(v) for v in value.tolist()]

        # 处理 pandas DataFrame
        elif isinstance(value, pd.DataFrame):
            return self._serialize_value(value.to_dict(orient="records"))

        # 处理字符串
        elif isinstance(value, str):
            return value

        # 其他类型转为字符串
        else:
            try:
                return str(value)
            except Exception:
                return None


def save_results(results: dict[str, Any], output_file: str, output_format: str = "json") -> bool:
    """
    保存回测结果

    参数：
        results: 回测结果
        output_file: 输出文件路径
        output_format: 输出格式 ('json' 或 'csv')

    返回：
        bool: 是否成功
    """
    serializer = ResultSerializer()

    if output_format.lower() == "json":
        return serializer.to_json(results, output_file)
    elif output_format.lower() == "csv":
        return serializer.to_csv(results, output_file)
    else:
        logger.error(f"不支持的输出格式: {output_format}")
        return False


def output_results(results: dict[str, Any], output_format: str = "json", output_file: str | None = None) -> str:
    """
    输出回测结果：落盘到 JSON/CSV，屏幕上仅打印各品种的数据时间范围

    参数：
        results: 回测结果
        output_format: 输出格式（table/both 是屏幕输出意图，落盘统一转 JSON）
        output_file: 输出文件路径，None则自动生成

    返回：
        str: 输出文件路径
    """
    # 如果没有指定输出文件，自动生成（使用统一的标准目录）
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 统一保存到 logs/backtest/ 目录（与 cli.py 保持一致）
        backend_dir = Path(__file__).resolve().parent.parent
        default_output_dir = backend_dir / "logs" / "backtest"
        default_output_dir.mkdir(parents=True, exist_ok=True)

        # table/both 是「屏幕输出格式」，落盘统一使用 JSON
        save_format = output_format.lower() if output_format.lower() in {"json", "csv"} else "json"
        output_file = str(default_output_dir / f"backtest_results_{timestamp}.{save_format}")
    else:
        # 如果用户显式指定了文件，但 output_format 是 table，仍按 json 格式保存（因为 table 不是可序列化格式）
        save_format = output_format.lower()
        if save_format not in {"json", "csv"}:
            save_format = "json"

    normal_results = {k: v for k, v in results.items() if not k.startswith("_")}
    # 组合结果判定：format_axon_results(单品种) 与 _format_results(多品种) 都带 portfolio 键
    is_portfolio = isinstance(normal_results.get("portfolio"), dict)
    is_multi_symbol = normal_results.get("is_multi_symbol", False) is True

    # 打印组合级数据时间范围
    if is_portfolio:
        _print_data_range(_metrics_to_dict(normal_results["portfolio"].get("metrics", {})))

    # 打印各品种的数据时间范围
    # 多品种：交易对数据在 results_by_symbol；其余直接取顶层
    symbol_results = normal_results.get("results_by_symbol") if is_multi_symbol else None
    if not isinstance(symbol_results, dict):
        symbol_results = normal_results

    for key, result in symbol_results.items():
        # 跳过框架键和非交易对数据
        if key.startswith("_") or key in ResultAnalyzer._FRAMEWORK_KEYS:
            continue
        if not isinstance(result, dict) or "symbol" not in result:
            continue
        _print_data_range(_metrics_to_dict(result.get("metrics", {})))

    # 保存结果（使用 save_format，而非屏幕输出格式）
    save_results(results, output_file, save_format)

    return output_file


def load_results(input_file: str) -> dict[str, Any] | None:
    """
    加载回测结果

    参数：
        input_file: 输入文件路径

    返回：
        Optional[Dict[str, Any]]: 加载的结果
    """
    serializer = ResultSerializer()
    return serializer.from_json(input_file)
