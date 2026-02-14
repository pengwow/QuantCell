"""
Worker模块CRUD操作

数据库增删改查操作
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

from . import schemas
from .models import Worker, WorkerLog, WorkerMetric, WorkerPerformance, WorkerParameter, WorkerTrade


def create_worker(db: Session, worker_data: schemas.WorkerCreate) -> Worker:
    """创建Worker"""
    import json
    db_worker = Worker(
        name=worker_data.name,
        description=worker_data.description,
        strategy_id=worker_data.strategy_id,
        exchange=worker_data.exchange,
        symbol=worker_data.symbol,
        timeframe=worker_data.timeframe,
        market_type=worker_data.market_type,
        trading_mode=worker_data.trading_mode,
        cpu_limit=worker_data.cpu_limit,
        memory_limit=worker_data.memory_limit,
        env_vars=json.dumps(worker_data.env_vars) if worker_data.env_vars else '{}',
        config=json.dumps(worker_data.config) if worker_data.config else '{}',
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
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return None
    
    update_data = worker_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
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
        exchange=source_worker.exchange,
        symbol=source_worker.symbol,
        timeframe=source_worker.timeframe,
        market_type=source_worker.market_type,
        trading_mode=source_worker.trading_mode,
        cpu_limit=source_worker.cpu_limit,
        memory_limit=source_worker.memory_limit,
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

def create_worker_log(db: Session, worker_id: int, level: str, message: str, source: str = "worker") -> WorkerLog:
    """创建Worker日志"""
    log = WorkerLog(
        worker_id=worker_id,
        level=level,
        message=message,
        source=source,
        timestamp=datetime.now()
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


# Worker指标操作

def create_worker_metric(db: Session, worker_id: int, metrics: Dict[str, Any]) -> WorkerMetric:
    """创建Worker指标记录"""
    metric = WorkerMetric(
        worker_id=worker_id,
        cpu_usage=metrics.get("cpu_usage", 0),
        memory_usage=metrics.get("memory_usage", 0),
        memory_used_mb=metrics.get("memory_used_mb", 0),
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
