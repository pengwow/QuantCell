# -*- coding: utf-8 -*-
"""
Worker 分享系统 业务逻辑层

build_snapshot() 严格白名单聚合：
- 复用 worker.stats_service.StatsService.get_overview() 获取 KPI / 收益曲线 / 盈亏分布
- 持仓仅投影白名单字段（symbol / side / quantity / entry_price / current_price /
  unrealized_pnl / pnl_percentage / open_time）
- 绝不暴露：strategy_code、worker_params、initial_capital、api_key、
  trades、orders、logs、leverage 详细阈值、mark_price、liquidation_price、margin_used
"""
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List
from uuid import UUID

from sqlalchemy.orm import Session

from worker.models import Worker, WorkerPosition
from worker.stats_service import TradingStatsService


logger = logging.getLogger(__name__)


def _to_json_safe(obj: Any) -> Any:
    """递归把对象转成 JSON 原生类型，便于 quantcell.top 端 parse 失败容错。

    - datetime/date → ISO 字符串
    - Decimal / float 子类 → float
    - UUID → str
    - dict / list → 递归
    - 其他 → 强转 str
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_json_safe(v) for v in obj]
    return str(obj)


# 持仓白名单字段 —— 顺序敏感，前端按此顺序展示
POSITION_SNAPSHOT_FIELDS = (
    "symbol",
    "side",
    "quantity",
    "entry_price",
    "current_price",
    "unrealized_pnl",
    "pnl_percentage",
    "open_time",
)

# Worker 元信息白名单
WORKER_SNAPSHOT_FIELDS = (
    "id",
    "name",
    "status",
    "exchange",
    "timeframe",
    "market_type",
    "trading_mode",
    "symbols",
    "created_at",
    "started_at",
)


def _extract_symbols_from_trading_config(trading_config_str: str) -> list:
    """从 trading_config JSON 中提取交易标的列表（非敏感）"""
    if not trading_config_str:
        return []
    try:
        cfg = json.loads(trading_config_str)
    except (json.JSONDecodeError, TypeError):
        return []
    symbols_cfg = cfg.get("symbols_config", {}) or {}
    items = symbols_cfg.get("symbols") or []
    if isinstance(items, list):
        return [str(s) for s in items if s]
    return []


def _filter_worker(worker: Worker) -> dict:
    """Worker 元信息白名单投影"""
    trading_cfg = worker.trading_config or "{}"
    return {
        "id": worker.id,
        "name": worker.name,
        "status": worker.status,
        "exchange": _safe_get_trading_cfg_field(trading_cfg, "exchange"),
        "timeframe": _safe_get_trading_cfg_field(trading_cfg, "timeframe"),
        "market_type": _safe_get_trading_cfg_field(trading_cfg, "market_type"),
        "trading_mode": _safe_get_trading_cfg_field(trading_cfg, "trading_mode"),
        "symbols": _extract_symbols_from_trading_config(trading_cfg),
        "created_at": worker.created_at.isoformat() if worker.created_at else None,
        "started_at": worker.started_at.isoformat() if worker.started_at else None,
    }


def _safe_get_trading_cfg_field(trading_cfg_str: str, field: str):
    """从 trading_config 中安全读取字段"""
    try:
        cfg = json.loads(trading_cfg_str)
    except (json.JSONDecodeError, TypeError):
        return None
    val = cfg.get(field)
    return val if val is not None else None


def _filter_position(p: WorkerPosition) -> dict:
    """持仓白名单投影 —— 严格不包含 leverage/margin_used/mark_price/liquidation_price"""
    # 计算 pnl_percentage = unrealized_pnl / (quantity * entry_price) * 100
    pnl_pct = 0.0
    try:
        cost = (p.entry_price or 0) * (p.quantity or 0)
        if cost > 0:
            pnl_pct = round((p.unrealized_pnl or 0) / cost * 100, 4)
    except Exception:
        pnl_pct = 0.0

    return {
        "symbol": p.symbol,
        "side": p.side,
        "quantity": float(p.quantity or 0),
        "entry_price": float(p.entry_price or 0),
        "current_price": float(p.current_price or 0),
        "unrealized_pnl": float(p.unrealized_pnl or 0),
        "pnl_percentage": pnl_pct,
        "open_time": p.opened_at.isoformat() if p.opened_at else None,
    }


def _get_open_positions(db: Session, worker_id: int) -> List[WorkerPosition]:
    """查询 worker 的所有 OPEN 持仓"""
    return (
        db.query(WorkerPosition)
        .filter(
            WorkerPosition.worker_id == worker_id,
            WorkerPosition.status == "OPEN",
        )
        .all()
    )


def build_snapshot(db: Session, worker_id: int, window: str = "30d") -> dict:
    """构建分享页所需的只读快照（严格白名单）

    Args:
        db: 数据库会话
        worker_id: Worker ID
        window: 时间窗口（24h/7d/30d/90d/all），默认 30d

    Returns:
        dict: 白名单字段组成的 snapshot payload

    Raises:
        ValueError: worker 不存在
    """
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise ValueError(f"Worker {worker_id} 不存在")

    # 1. Worker 元信息（白名单）
    worker_snapshot = _filter_worker(worker)

    # 2. 复用 TradingStatsService 聚合 overview 数据
    try:
        stats = TradingStatsService(db)
        overview = stats.get_overview(worker_id, window=window)
        metrics = overview.get("metrics", {})
        cumulative_pnl_series = overview.get("cumulative_pnl_series", {})
        pnl_distribution = overview.get("pnl_distribution", {})
    except Exception as e:
        # 聚合失败时给空数据，不让分享完全不可用
        logger.warning("build_snapshot 聚合 overview 失败 worker=%s err=%s", worker_id, e)
        metrics = {}
        cumulative_pnl_series = {}
        pnl_distribution = {}

    # 3. 持仓白名单
    positions = _get_open_positions(db, worker_id)
    position_snapshots = [_filter_position(p) for p in positions]

    return {
        "worker": worker_snapshot,
        "metrics": metrics,
        "cumulative_pnl_series": cumulative_pnl_series,
        "pnl_distribution": pnl_distribution,
        "positions": position_snapshots,
        "generated_at": datetime.now().isoformat(),
        "read_only": True,
    }


def serialize_for_remote(snapshot: dict) -> dict:
    """对外推送前的最终清洗：JSON 安全化 + 标记 static_compat（仅远端使用）。"""
    safe = _to_json_safe(snapshot)
    safe["static_compat"] = True  # 标记：snapshot 经 _to_json_safe 二次清洗，quantcell.top 端可放心 JSON parse
    return safe
