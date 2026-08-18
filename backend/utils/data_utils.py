"""
数据工具模块

提供数据清理、转换等通用工具函数。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-24
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


# ---------------------------------------------------------------------------
# 路径工具函数（统一基于 backend/ 根目录解析，避免 cwd 依赖）
# ---------------------------------------------------------------------------


def get_backend_root() -> Path:
    """返回 backend/ 目录的绝对路径"""
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """返回 backend/data 目录的绝对路径"""
    return get_backend_root() / "data"


def get_source_data_dir() -> Path:
    """返回 backend/data/source 目录的绝对路径（存储原始下载数据）"""
    return get_data_dir() / "source"


def get_symbols_from_data_pool(pool_name: str) -> list[str]:
    """
    从数据池获取自选组合的货币对列表

    Args:
        pool_name: 自选组合名称

    Returns:
        List[str]: 货币对列表（空表示组合中无资产或未找到）
    """
    try:
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import DataPool, DataPoolAsset

        init_database_config()
        db = SessionLocal()

        try:
            pool = db.query(DataPool).filter_by(name=pool_name).first()
            if not pool:
                logger.warning(f"自选组合不存在: {pool_name}")
                return []

            assets = db.query(DataPoolAsset).filter_by(pool_id=pool.id).all()
            symbols = [asset.asset_id for asset in assets]

            if not symbols:
                logger.warning(f"自选组合 '{pool_name}' 中没有货币对")
                return []

            logger.info(f"从自选组合 '{pool_name}' 获取到 {len(symbols)} 个货币对: {symbols}")
            return symbols
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"从数据池获取货币对失败: {e}")
        return []


def sanitize_for_json(data: Any) -> Any:
    """
    递归清理数据，使其可以被 JSON 序列化

    处理以下特殊情况：
    - NaT (Not a Time) 值
    - NaN (Not a Number) 值
    - Infinity 值
    - Timestamp 对象
    - Timedelta 对象
    - NumPy 类型

    Args:
        data: 需要清理的数据，可以是任意类型

    Returns:
        Any: 清理后的数据，可以被 JSON 序列化

    Examples:
        >>> sanitize_for_json(pd.Timestamp('2023-01-01'))
        '2023-01-01 00:00:00'
        >>> sanitize_for_json(np.nan)
        None
        >>> sanitize_for_json(np.inf)
        None
    """
    try:
        # 处理字典类型
        if isinstance(data, dict):
            return {k: sanitize_for_json(v) for k, v in data.items()}

        # 处理列表类型
        elif isinstance(data, list):
            return [sanitize_for_json(item) for item in data]

        # 处理 Timestamp 和 datetime 对象
        elif isinstance(data, (pd.Timestamp, datetime)):
            if pd.isna(data):
                return None
            return data.strftime("%Y-%m-%d %H:%M:%S")

        # 处理 Timedelta 对象
        elif isinstance(data, pd.Timedelta):
            if pd.isna(data):
                return None
            return str(data)

        # 处理 NaT、NaN、None 值
        elif pd.isna(data):
            return None

        # 处理浮点数的无穷大值
        elif isinstance(data, float):
            if np.isinf(data):
                return None
            return data

        # 处理 NumPy 整数类型
        elif isinstance(data, (np.integer, np.int64, np.int32)):
            return int(data)

        # 处理 NumPy 浮点类型
        elif isinstance(data, (np.floating, np.float64, np.float32)):
            if np.isnan(data) or np.isinf(data):
                return None
            return float(data)

        # 其他类型直接返回
        else:
            return data
    except Exception as e:
        logger.warning(f"清理数据时发生异常: {e}, 数据类型: {type(data)}")
        return None


# ---------------------------------------------------------------------------
# Parquet 文件操作工具（从 cli/data.py 迁移而来）
# ---------------------------------------------------------------------------


def _normalize_symbol(symbol: str) -> str:
    """标准化交易对名称"""
    return symbol.replace("/", "").replace("\\", "").replace(" ", "")


def _find_parquet_file(symbol: str, interval: str, market_type: str = "spot") -> Path | None:
    """查找指定交易对和时间框架的parquet文件"""
    data_dir = get_source_data_dir()
    norm_symbol = _normalize_symbol(symbol)
    return data_dir / market_type / interval / f"{norm_symbol}.parquet"


def _get_default_date_range(end_date=None) -> tuple[str, str]:
    """获取默认日期范围"""
    from datetime import datetime, timedelta

    if end_date is None:
        end = datetime.now()
    elif isinstance(end_date, datetime):
        end = end_date
    else:
        end = datetime.now()
    start = end - timedelta(days=30)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def filter_by_date_range(df, start_date=None, end_date=None):
    """按日期范围过滤DataFrame"""
    if df is None or df.empty:
        return df
    if "timestamp" not in df.columns:
        return df
    mask = pd.Series(True, index=df.index)
    if start_date:
        start_ts = pd.Timestamp(start_date)
        if df["timestamp"].dtype == "int64" or df["timestamp"].dtype == "int32":
            if df["timestamp"].max() > 1e12:
                start_ts = int(start_ts.timestamp() * 1_000_000_000)
            else:
                start_ts = int(start_ts.timestamp())
        mask &= df["timestamp"] >= start_ts
    if end_date:
        end_ts = pd.Timestamp(end_date)
        if df["timestamp"].dtype == "int64" or df["timestamp"].dtype == "int32":
            if df["timestamp"].max() > 1e12:
                end_ts = int(end_ts.timestamp() * 1_000_000_000)
            else:
                end_ts = int(end_ts.timestamp())
        mask &= df["timestamp"] <= end_ts
    return df[mask]


def load_from_parquet(file_path) -> pd.DataFrame:
    """从parquet加载数据"""
    return pd.read_parquet(file_path)


def get_parquet_info(file_path: Path) -> dict:
    """获取parquet文件信息"""
    try:
        df = load_from_parquet(file_path)
        return {
            "file": str(file_path),
            "rows": len(df),
            "columns": list(df.columns),
            "size": file_path.stat().st_size if file_path.exists() else 0,
            "num_rows": len(df),
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
        }
    except Exception as e:
        return {"file": str(file_path), "error": str(e)}


def scan_parquet_files(symbol=None, interval=None, market_type: str = "spot", base_dir=None) -> list:
    """扫描parquet文件"""
    if base_dir is None:
        base_dir = get_source_data_dir()
    if not base_dir.exists():
        return []

    results = []
    klines_dir = base_dir / market_type

    if not klines_dir.exists():
        for f in sorted(base_dir.glob("*.parquet")):
            results.append((f.stem, f))
        return results

    if symbol and interval:
        interval_dir = klines_dir / symbol / interval
        if interval_dir.is_dir():
            for f in interval_dir.iterdir():
                if f.suffix == ".parquet":
                    info = get_parquet_info(f)
                    results.append(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "file": f,
                            "info": info,
                        }
                    )
    elif symbol:
        symbol_dir = klines_dir / symbol
        if symbol_dir.is_dir():
            for interval_dir in symbol_dir.iterdir():
                if interval_dir.is_dir():
                    for f in interval_dir.iterdir():
                        if f.suffix == ".parquet":
                            info = get_parquet_info(f)
                            results.append(
                                {
                                    "symbol": symbol,
                                    "interval": interval_dir.name,
                                    "file": f,
                                    "info": info,
                                }
                            )
    else:
        for sym_dir in klines_dir.iterdir():
            if sym_dir.is_dir():
                for interval_dir in sym_dir.iterdir():
                    if interval_dir.is_dir():
                        for f in interval_dir.iterdir():
                            if f.suffix == ".parquet":
                                info = get_parquet_info(f)
                                results.append(
                                    {
                                        "symbol": sym_dir.name,
                                        "interval": interval_dir.name,
                                        "file": f,
                                        "info": info,
                                    }
                                )
    return results


def _validate_parquet_export(file_path, df) -> bool:
    """验证parquet导出"""
    if not file_path.exists():
        return False
    if file_path.stat().st_size == 0:
        return False
    try:
        loaded_df = load_from_parquet(file_path)
    except Exception:
        return False
    if len(loaded_df) != len(df):
        return False
    return list(loaded_df.columns) == list(df.columns)


def format_size(size_bytes: float) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes:.1f} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def calculate_data_completeness(bar_count, start_ts, end_ts, interval) -> dict:
    """计算数据完整率"""
    if bar_count == 0 or start_ts is None or end_ts is None:
        return {"completeness_pct": 0, "status": "-"}

    interval_minutes = _parse_interval_minutes(interval)
    if interval_minutes <= 0:
        return {"completeness_pct": 0, "status": "-"}

    is_nanoseconds = start_ts > 1e12

    duration_seconds = (end_ts - start_ts) / 1000000000 if is_nanoseconds else end_ts - start_ts

    expected_bars = duration_seconds / (interval_minutes * 60)

    if expected_bars <= 0:
        return {"completeness_pct": 0, "status": "-"}

    pct = min(100.0, (bar_count / expected_bars) * 100.0)

    if pct >= 100.0:
        status = "✓"
    elif pct >= 70:
        status = "⚠️"
    else:
        status = "✗"

    return {"completeness_pct": round(pct, 1), "status": status}


def _parse_interval_minutes(interval: str) -> float:
    """解析时间框架为分钟"""
    interval = interval.lower().strip()
    mappings = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "8h": 480,
        "12h": 720,
        "1d": 1440,
        "3d": 4320,
        "1w": 10080,
    }
    if interval in mappings:
        return mappings[interval]
    return 0


def format_completeness(info: dict) -> str:
    """格式化完整率"""
    if info.get("status") == "-":
        return "-"
    pct = info.get("completeness_pct", 0)
    status = info.get("status", "-")
    return f"{int(pct)}% {status}"


def format_time_range(start, end) -> str:
    """格式化时间范围"""
    if start is None and end is None:
        return "-"
    try:
        if start is not None:
            start_dt = _ts_to_datetime(start)
            start_str = start_dt.strftime("%Y-%m-%d")
        else:
            start_str = "?"
        if end is not None:
            end_dt = _ts_to_datetime(end)
            end_str = end_dt.strftime("%Y-%m-%d")
        else:
            end_str = "?"
        return f"{start_str} ~ {end_str}"
    except Exception:
        return "-"


def _ts_to_datetime(ts):
    """时间戳转datetime"""
    from datetime import datetime

    if ts > 1e12:
        return datetime.fromtimestamp(ts / 1_000_000_000)
    return datetime.fromtimestamp(ts)


class DataSanitizer:
    """数据清理器，负责数据清理和转换"""

    def sanitize_for_json(self, data: Any) -> Any:
        """
        递归清理数据，使其可以被JSON序列化
        处理 NaT, NaN, Infinity, Timestamp 等

        Args:
            data: 需要清理的数据

        Returns:
            Any: 清理后的数据
        """
        return sanitize_for_json(data)

    def translate_metrics(self, stats: dict[str, Any], language: str = "zh-CN") -> list[dict[str, Any]]:
        """
        翻译回测结果指标为多语言

        Args:
            stats: 回测结果统计
            language: 目标语言

        Returns:
            List[Dict[str, Any]]: 翻译后的指标列表
        """
        from i18n.utils import load_translations

        # 加载翻译
        trans = load_translations(language)

        translated_metrics = []
        for key, value in stats.items():
            # 跳过内部字段
            if key in ["_strategy", "_equity_curve", "_trade_list", "_trades"]:
                continue

            # 获取翻译
            name = trans.get(key, key)
            desc = trans.get(f"{key}.desc", name)

            # 处理特殊类型的值
            metric_info = self._process_metric_value(key, value)
            if metric_info is None:
                continue

            translated_metrics.append(
                {
                    "name": name,
                    "key": key,
                    "value": metric_info["value"],
                    "description": desc,
                    "type": metric_info["type"],
                }
            )

        return translated_metrics

    def _process_metric_value(self, key: str, value: Any) -> dict[str, Any] | None:
        """
        处理指标值，返回处理后的值和类型

        Args:
            key: 指标键
            value: 指标值

        Returns:
            Optional[Dict[str, Any]]: 包含 value 和 type 的字典，如果应该跳过则返回 None
        """
        # 处理 Timestamp
        if isinstance(value, pd.Timestamp):
            return {"value": self.sanitize_for_json(value), "type": "datetime"}

        # 处理 Timedelta
        if isinstance(value, pd.Timedelta):
            return {"value": self.sanitize_for_json(value), "type": "duration"}

        # 跳过复杂数据结构
        if isinstance(value, (pd.Series, pd.DataFrame)):
            return None

        # 处理数值类型
        if isinstance(value, (int, float)):
            metric_type = "number"
            if "[%]" in key:
                metric_type = "percentage"
            elif "[$]" in key:
                metric_type = "currency"

            return {"value": value, "type": metric_type}

        # 其他类型
        return {"value": value, "type": "string"}
