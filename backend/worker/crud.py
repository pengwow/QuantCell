"""
Worker模块CRUD操作

数据库增删改查操作
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, cast, Date, case
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
import numpy as np

from .models import Worker, WorkerLog, WorkerMetric, WorkerPerformance, WorkerParameter, WorkerTrade, WorkerOrder, WorkerPosition
from . import schemas


def find_strategy_by_name_or_id(db: Session, strategy_id: Optional[int] = None, strategy_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    通过 strategy_id 或 strategy_name 查找策略信息
    
    容错逻辑：
    1. 优先使用 strategy_id 查找
    2. 如果 strategy_id 找不到，尝试使用 strategy_name 查找
    3. 返回策略信息字典（包含 id, name, file_name 等）
    
    Args:
        db: 数据库会话
        strategy_id: 策略 ID（可选）
        strategy_name: 策略名称（可选）
    
    Returns:
        dict: 策略信息，如果找不到返回 None
    """
    try:
        from ..strategy.models import Strategy
        
        # 优先通过 ID 查找
        if strategy_id:
            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if strategy:
                return {
                    'id': strategy.id,
                    'name': strategy.name,
                    'file_name': getattr(strategy, 'file_name', None),
                }
            else:
                # ID 找不到，记录警告并尝试通过名称查找
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"策略 ID {strategy_id} 未找到，尝试通过名称查找...")
        
        # 通过名称查找（容错机制）
        if strategy_name:
            strategy = db.query(Strategy).filter(
                and_(
                    Strategy.name == strategy_name,
                    Strategy.is_deleted == False if hasattr(Strategy, 'is_deleted') else True
                )
            ).first()
            
            if strategy:
                return {
                    'id': strategy.id,
                    'name': strategy.name,
                    'file_name': getattr(strategy, 'file_name', None),
                }
        
        return None
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"查找策略失败: {e}")
        return None


def create_worker(db: Session, worker_data: schemas.WorkerCreate) -> Worker:
    """创建Worker"""
    import json

    # 处理交易标的：优先使用 symbols 列表，如果没有则使用 symbol 单数
    if worker_data.symbols and len(worker_data.symbols) > 0:
        symbols = worker_data.symbols
    elif worker_data.symbol:
        symbols = [worker_data.symbol]
    else:
        symbols = ["BTCUSDT"]

    # 构建交易配置
    trading_config = {
        "exchange": worker_data.exchange or "binance",
        "symbols_config": {
            "type": "symbols",  # 默认为直接货币对模式
            "symbols": symbols,
            "pool_id": None,
            "pool_name": None
        },
        "timeframe": worker_data.timeframe or "1h",
        "market_type": worker_data.market_type or "spot",
        "trading_mode": worker_data.trading_mode or "paper"
    }

    db_worker = Worker(
        name=worker_data.name,
        description=worker_data.description,
        strategy_id=worker_data.strategy_id,
        strategy_name=getattr(worker_data, 'strategy_name', None),  # 新增：策略名称（冗余存储）
        trading_config=json.dumps(trading_config),
        env_vars=json.dumps(worker_data.env_vars) if worker_data.env_vars else '{}',
        config=json.dumps({**(worker_data.config or {}), 'strategy_file_name': worker_data.strategy_file_name}) if (worker_data.config or worker_data.strategy_file_name) else '{}',
        status="stopped",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    db.add(db_worker)
    db.commit()
    db.refresh(db_worker)
    return db_worker


def get_worker(db: Session, worker_id: int) -> Optional[Worker]:
    """获取Worker"""
    return db.query(Worker).filter(Worker.id == worker_id).first()


def get_workers(
    db: Session,
    status: Optional[str] = None,
    strategy_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 20
) -> Tuple[List[Worker], int]:
    """获取Worker列表"""
    query = db.query(Worker)
    
    if status:
        query = query.filter(Worker.status == status)
    if strategy_id:
        query = query.filter(Worker.strategy_id == strategy_id)
    
    total = query.count()
    workers = query.order_by(desc(Worker.created_at)).offset(skip).limit(limit).all()
    return workers, total


def update_worker(db: Session, worker_id: int, worker_data: schemas.WorkerUpdate) -> Optional[Worker]:
    """更新Worker"""
    import json

    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return None

    update_data = worker_data.model_dump(exclude_unset=True)

    # 特殊处理 trading_mode：需要合并到 trading_config JSON 中
    if 'trading_mode' in update_data:
        trading_mode = update_data.pop('trading_mode')
        current_trading_config = worker.get_trading_config_dict()
        current_trading_config['trading_mode'] = trading_mode
        worker.trading_config = json.dumps(current_trading_config)

    for field, value in update_data.items():
        # 特殊处理 config 和 trading_config 字段（需要 JSON 序列化）
        if field in ('config', 'trading_config') and isinstance(value, dict):
            setattr(worker, field, json.dumps(value))
        else:
            setattr(worker, field, value)

    worker.updated_at = datetime.now()
    db.commit()
    db.refresh(worker)
    return worker


def update_worker_config(db: Session, worker_id: int, config: Dict[str, Any]) -> Optional[Worker]:
    """更新Worker配置"""
    import json
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return None
    
    current_config = worker.get_config_dict()
    current_config.update(config)
    worker.config = json.dumps(current_config)
    worker.updated_at = datetime.now()
    db.commit()
    db.refresh(worker)
    return worker


def delete_worker(db: Session, worker_id: int) -> bool:
    """删除Worker"""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return False
    
    db.delete(worker)
    db.commit()
    return True


def clone_worker(db: Session, worker_id: int, request: schemas.WorkerCloneRequest) -> Worker:
    """克隆Worker"""
    source_worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not source_worker:
        raise ValueError("源Worker不存在")

    new_worker = Worker(
        name=request.new_name,
        description=source_worker.description,
        strategy_id=source_worker.strategy_id,
        trading_config=source_worker.trading_config if request.copy_config else '{}',
        env_vars=source_worker.env_vars if request.copy_config else '{}',
        config=source_worker.config if request.copy_config else '{}',
        status="stopped",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    db.add(new_worker)
    db.commit()
    db.refresh(new_worker)

    # 复制参数
    if request.copy_parameters:
        params = db.query(WorkerParameter).filter(WorkerParameter.worker_id == worker_id).all()
        for param in params:
            new_param = WorkerParameter(
                worker_id=new_worker.id,
                param_name=param.param_name,
                param_value=param.param_value,
                param_type=param.param_type,
                description=param.description
            )
            db.add(new_param)
        db.commit()

    return new_worker


def update_worker_status(db: Session, worker_id: int, status: str, pid: Optional[int] = None) -> Optional[Worker]:
    """更新Worker状态"""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return None
    
    worker.status = status
    if pid is not None:
        worker.pid = pid
    
    if status == "running":
        worker.started_at = datetime.now()
    elif status == "stopped":
        worker.stopped_at = datetime.now()
    
    worker.updated_at = datetime.now()
    db.commit()
    db.refresh(worker)
    return worker


# Worker日志操作

def create_worker_log(db: Session, worker_id: int, level: str, message: str, source: str = "worker", timestamp: Optional[datetime] = None) -> WorkerLog:
    """创建Worker日志"""
    log = WorkerLog(
        worker_id=worker_id,
        level=level,
        message=message,
        source=source,
        timestamp=timestamp if timestamp else datetime.now()
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_worker_logs(
    db: Session,
    worker_id: int,
    level: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100
) -> List[WorkerLog]:
    """获取Worker日志"""
    query = db.query(WorkerLog).filter(WorkerLog.worker_id == worker_id)

    if level:
        query = query.filter(WorkerLog.level == level)
    if start_time:
        query = query.filter(WorkerLog.timestamp >= start_time)
    if end_time:
        query = query.filter(WorkerLog.timestamp <= end_time)

    return query.order_by(desc(WorkerLog.timestamp)).limit(limit).all()


def clear_worker_logs(db: Session, worker_id: int, before_days: Optional[int] = None) -> int:
    """清理Worker日志

    Args:
        db: 数据库会话
        worker_id: Worker ID
        before_days: 清理多少天前的日志，None表示清理所有

    Returns:
        删除的日志条数
    """
    query = db.query(WorkerLog).filter(WorkerLog.worker_id == worker_id)

    if before_days is not None:
        cutoff_time = datetime.now() - timedelta(days=before_days)
        query = query.filter(WorkerLog.timestamp < cutoff_time)

    deleted_count = query.count()
    query.delete(synchronize_session=False)
    db.commit()

    return deleted_count


# Worker指标操作

def create_worker_metric(db: Session, worker_id: int, metrics: Dict[str, Any]) -> WorkerMetric:
    """创建Worker指标记录"""
    metric = WorkerMetric(
        worker_id=worker_id,
        network_in=metrics.get("network_in", 0),
        network_out=metrics.get("network_out", 0),
        active_tasks=metrics.get("active_tasks", 0),
        timestamp=datetime.now()
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def get_metrics_history(
    db: Session,
    worker_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    interval: str = "1m"
) -> List[Dict[str, Any]]:
    """获取历史指标"""
    query = db.query(WorkerMetric).filter(WorkerMetric.worker_id == worker_id)
    
    if start_time:
        query = query.filter(WorkerMetric.timestamp >= start_time)
    if end_time:
        query = query.filter(WorkerMetric.timestamp <= end_time)
    
    metrics = query.order_by(WorkerMetric.timestamp).all()
    return [m.to_dict() for m in metrics]


# Worker绩效操作

def get_worker_performance(db: Session, worker_id: int, days: int = 30) -> List[WorkerPerformance]:
    """获取Worker绩效"""
    start_date = datetime.now() - timedelta(days=days)
    return db.query(WorkerPerformance).filter(
        and_(
            WorkerPerformance.worker_id == worker_id,
            WorkerPerformance.date >= start_date
        )
    ).order_by(WorkerPerformance.date).all()


# Worker参数操作

def get_worker_parameters(db: Session, worker_id: int) -> List[WorkerParameter]:
    """获取Worker参数"""
    return db.query(WorkerParameter).filter(WorkerParameter.worker_id == worker_id).all()


def update_worker_parameters(db: Session, worker_id: int, parameters: Dict[str, Any]) -> None:
    """更新Worker参数"""
    for name, value in parameters.items():
        param = db.query(WorkerParameter).filter(
            and_(
                WorkerParameter.worker_id == worker_id,
                WorkerParameter.param_name == name
            )
        ).first()
        
        if param:
            param.param_value = value
        else:
            param = WorkerParameter(
                worker_id=worker_id,
                param_name=name,
                param_value=value,
                param_type=type(value).__name__,
                editable=True
            )
            db.add(param)
    
    db.commit()


# Worker交易操作

def get_worker_trades(
    db: Session,
    worker_id: int,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 20
) -> Tuple[List[WorkerTrade], int]:
    """获取Worker交易记录"""
    query = db.query(WorkerTrade).filter(WorkerTrade.worker_id == worker_id)
    
    if symbol:
        query = query.filter(WorkerTrade.symbol == symbol)
    if start_time:
        query = query.filter(WorkerTrade.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerTrade.created_at <= end_time)
    
    total = query.count()
    trades = query.order_by(desc(WorkerTrade.created_at)).offset(skip).limit(limit).all()
    return trades, total


def create_trade_if_not_exists(db: Session, trade_data: dict) -> WorkerTrade:
    existing = db.query(WorkerTrade).filter(WorkerTrade.trade_id == trade_data['trade_id']).first()
    if existing:
        return existing
    db_trade = WorkerTrade(**trade_data)
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade


def create_order_if_not_exists(db: Session, order_data: dict) -> WorkerOrder:
    existing = db.query(WorkerOrder).filter(WorkerOrder.client_order_id == order_data['client_order_id']).first()
    if existing:
        return existing
    db_order = WorkerOrder(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def create_position_if_not_exists(db: Session, position_data: dict) -> WorkerPosition:
    existing = db.query(WorkerPosition).filter(WorkerPosition.position_id == position_data['position_id']).first()
    if existing:
        return existing
    db_position = WorkerPosition(**position_data)
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    return db_position


def update_position(db: Session, position_id: str, position_data: dict) -> Optional[WorkerPosition]:
    position = db.query(WorkerPosition).filter(WorkerPosition.position_id == position_id).first()
    if not position:
        return None
    for field, value in position_data.items():
        if hasattr(position, field):
            setattr(position, field, value)
    position.updated_at = datetime.now()
    db.commit()
    db.refresh(position)
    return position


def get_all_worker_trades(
    db: Session,
    worker_id: int,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> List[WorkerTrade]:
    query = db.query(WorkerTrade).filter(WorkerTrade.worker_id == worker_id)
    if symbol:
        query = query.filter(WorkerTrade.symbol == symbol)
    if side:
        query = query.filter(WorkerTrade.side == side)
    if start_time:
        query = query.filter(WorkerTrade.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerTrade.created_at <= end_time)
    return query.order_by(desc(WorkerTrade.created_at)).all()


def get_worker_order_by_id(db: Session, worker_id: int, client_order_id: str) -> Optional[WorkerOrder]:
    return db.query(WorkerOrder).filter(
        and_(
            WorkerOrder.worker_id == worker_id,
            WorkerOrder.client_order_id == client_order_id,
        )
    ).first()


def update_worker_order_status(
    db: Session,
    order_id: int,
    status: str,
    filled_qty: float,
    avg_fill_price: float,
    commission: float,
    venue_order_id: str,
) -> Optional[WorkerOrder]:
    order = db.query(WorkerOrder).filter(WorkerOrder.id == order_id).first()
    if not order:
        return None
    order.status = status
    order.filled_qty = filled_qty
    order.avg_fill_price = avg_fill_price
    order.venue_order_id = venue_order_id
    order.updated_at = datetime.now()
    if status == "FILLED":
        order.filled_at = datetime.now()
    db.commit()
    db.refresh(order)
    return order


def get_trading_summary(
    db: Session,
    worker_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    """
    获取交易汇总统计（优化版 - 使用 SQL 聚合）
    
    Uses SQLAlchemy aggregate functions to compute statistics at the database level,
    avoiding loading all trade records into memory.
    """
    return get_trading_summary_optimized(db, worker_id, start_time, end_time)


def get_trade_history_chart(db: Session, worker_id: int, days: int = 30) -> dict:
    start_date = datetime.now() - timedelta(days=days)
    trades = (
        db.query(WorkerTrade)
        .filter(
            and_(
                WorkerTrade.worker_id == worker_id,
                WorkerTrade.created_at >= start_date,
            )
        )
        .order_by(WorkerTrade.created_at)
        .all()
    )

    if not trades:
        return {
            "dates": [],
            "cumulative_pnl": [],
            "daily_pnl": [],
            "trade_count": [],
        }

    daily_data: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if not t.created_at:
            continue
        date_str = t.created_at.strftime("%Y-%m-%d")
        if date_str not in daily_data:
            daily_data[date_str] = {"pnl": 0.0, "count": 0}
        daily_data[date_str]["pnl"] += t.realized_pnl or 0.0
        daily_data[date_str]["count"] += 1

    sorted_dates = sorted(daily_data.keys())
    dates = []
    cumulative_pnl = []
    daily_pnl = []
    trade_count = []
    cumulative = 0.0

    for date_str in sorted_dates:
        cumulative += daily_data[date_str]["pnl"]
        dates.append(date_str)
        cumulative_pnl.append(round(cumulative, 2))
        daily_pnl.append(round(daily_data[date_str]["pnl"], 2))
        trade_count.append(int(daily_data[date_str]["count"]))

    return {
        "dates": dates,
        "cumulative_pnl": cumulative_pnl,
        "daily_pnl": daily_pnl,
        "trade_count": trade_count,
    }


def get_pnl_distribution(db: Session, worker_id: int) -> dict:
    """
    获取 PNL 分布统计（优化版 - 使用 SQL 聚合计算统计量）
    
    使用 SQLAlchemy 聚合函数在数据库层面计算 mean、std，
    仅加载 pnl_values 用于直方图计算。
    """
    # 使用 SQL 聚合计算统计量
    stats_query = db.query(
        func.count(WorkerTrade.id).label('count'),
        func.sum(WorkerTrade.realized_pnl).label('sum_pnl'),
        func.avg(WorkerTrade.realized_pnl).label('mean_pnl'),
        func.min(WorkerTrade.realized_pnl).label('min_pnl'),
        func.max(WorkerTrade.realized_pnl).label('max_pnl'),
    ).filter(
        WorkerTrade.worker_id == worker_id,
        WorkerTrade.realized_pnl.isnot(None)
    )
    
    stats_row = stats_query.first()
    
    if not stats_row or not stats_row.count:
        return {
            "bins": [],
            "counts": [],
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
        }
    
    # 仅加载 pnl_values 用于直方图和标准差计算
    pnl_values = db.query(WorkerTrade.realized_pnl).filter(
        WorkerTrade.worker_id == worker_id,
        WorkerTrade.realized_pnl.isnot(None)
    ).all()
    pnl_values = [p[0] for p in pnl_values]
    
    pnl_array = np.array(pnl_values)
    counts, bin_edges = np.histogram(pnl_array, bins=20)
    
    # 使用 SQL 计算的 mean，Python 计算 median 和 std
    mean_pnl = float(stats_row.mean_pnl) if stats_row.mean_pnl else 0.0
    
    return {
        "bins": [round(float(b), 2) for b in bin_edges.tolist()],
        "counts": [int(c) for c in counts.tolist()],
        "mean": round(mean_pnl, 2),
        "median": round(float(np.median(pnl_array)), 2),
        "std": round(float(np.std(pnl_array)), 2),
    }


def get_worker_orders_paginated(
    db: Session,
    worker_id: int,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    order_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[WorkerOrder], int]:
    query = db.query(WorkerOrder).filter(WorkerOrder.worker_id == worker_id)

    if status:
        query = query.filter(WorkerOrder.status == status)
    if symbol:
        query = query.filter(WorkerOrder.symbol == symbol)
    if side:
        query = query.filter(WorkerOrder.side == side)
    if order_type:
        query = query.filter(WorkerOrder.order_type == order_type)
    if start_time:
        query = query.filter(WorkerOrder.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerOrder.created_at <= end_time)

    total = query.count()
    orders = query.order_by(desc(WorkerOrder.created_at)).offset(skip).limit(limit).all()
    return orders, total


def get_worker_positions_filtered(
    db: Session,
    worker_id: int,
    status: Optional[str] = "OPEN",
    symbol: Optional[str] = None,
    side: Optional[str] = None,
) -> List[WorkerPosition]:
    query = db.query(WorkerPosition).filter(WorkerPosition.worker_id == worker_id)

    if status:
        query = query.filter(WorkerPosition.status == status)
    if symbol:
        query = query.filter(WorkerPosition.symbol == symbol)
    if side:
        query = query.filter(WorkerPosition.side == side)

    return query.order_by(desc(WorkerPosition.updated_at)).all()


def get_trading_summary_optimized(
    db: Session,
    worker_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    query = db.query(
        func.count(WorkerTrade.id).label('total_trades'),
        func.sum(case((WorkerTrade.realized_pnl > 0, 1), else_=0)).label('winning_trades'),
        func.sum(case((WorkerTrade.realized_pnl < 0, 1), else_=0)).label('losing_trades'),
        func.sum(WorkerTrade.realized_pnl).label('total_pnl'),
        func.sum(case((WorkerTrade.realized_pnl > 0, WorkerTrade.realized_pnl), else_=0)).label('total_profit'),
        func.sum(case((WorkerTrade.realized_pnl < 0, WorkerTrade.realized_pnl), else_=0)).label('total_loss'),
        func.max(WorkerTrade.realized_pnl).label('largest_profit'),
        func.min(WorkerTrade.realized_pnl).label('largest_loss'),
        func.sum(WorkerTrade.amount).label('total_volume'),
        func.sum(WorkerTrade.fee).label('total_fees'),
        func.count(func.distinct(func.date(WorkerTrade.created_at))).label('trading_days'),
    ).filter(WorkerTrade.worker_id == worker_id)

    if start_time:
        query = query.filter(WorkerTrade.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerTrade.created_at <= end_time)

    row = query.first()

    if not row or not row.total_trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "total_profit": 0.0,
            "total_loss": 0.0,
            "profit_factor": 0.0,
            "average_profit": 0.0,
            "average_loss": 0.0,
            "largest_profit": 0.0,
            "largest_loss": 0.0,
            "total_volume": 0.0,
            "total_fees": 0.0,
            "trading_days": 0,
            "daily_average_trades": 0.0,
        }

    total_trades = row.total_trades or 0
    winning_trades = row.winning_trades or 0
    losing_trades = row.losing_trades or 0
    total_pnl = row.total_pnl or 0.0
    total_profit = row.total_profit or 0.0
    total_loss = row.total_loss or 0.0
    largest_profit = row.largest_profit or 0.0
    largest_loss = row.largest_loss or 0.0
    total_volume = row.total_volume or 0.0
    total_fees = row.total_fees or 0.0
    trading_days = row.trading_days or 0

    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (total_profit / abs(total_loss)) if total_loss != 0 else 0.0
    average_profit = (total_profit / winning_trades) if winning_trades > 0 else 0.0
    average_loss = (total_loss / losing_trades) if losing_trades > 0 else 0.0
    daily_average_trades = (total_trades / trading_days) if trading_days > 0 else 0.0

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "total_profit": round(total_profit, 2),
        "total_loss": round(total_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "average_profit": round(average_profit, 2),
        "average_loss": round(average_loss, 2),
        "largest_profit": round(largest_profit, 2),
        "largest_loss": round(largest_loss, 2),
        "total_volume": round(total_volume, 2),
        "total_fees": round(total_fees, 2),
        "trading_days": trading_days,
        "daily_average_trades": round(daily_average_trades, 2),
    }


def get_worker_trades_paginated(
    db: Session,
    worker_id: int,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    order_type: Optional[str] = None,
    pnl_status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[WorkerTrade], int]:
    query = db.query(WorkerTrade).filter(WorkerTrade.worker_id == worker_id)

    if symbol:
        query = query.filter(WorkerTrade.symbol == symbol)
    if side:
        query = query.filter(WorkerTrade.side == side)
    if order_type:
        query = query.filter(WorkerTrade.order_type == order_type)
    if pnl_status is not None:
        if pnl_status == 'profit':
            query = query.filter(WorkerTrade.realized_pnl > 0)
        elif pnl_status == 'loss':
            query = query.filter(WorkerTrade.realized_pnl < 0)
        elif pnl_status == 'flat':
            query = query.filter(WorkerTrade.realized_pnl == 0)
    if start_time:
        query = query.filter(WorkerTrade.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerTrade.created_at <= end_time)

    total = query.count()
    trades = query.order_by(desc(WorkerTrade.created_at)).offset(skip).limit(limit).all()
    return trades, total
