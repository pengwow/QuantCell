"""
Worker模块CRUD操作

数据库增删改查操作
"""

import json
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
from sqlalchemy import and_, case, desc, func

from utils.db_session import get_db_session

from .models import (
    Worker,
    WorkerFillEvidence,
    WorkerLog,
    WorkerMetric,
    WorkerOrder,
    WorkerParameter,
    WorkerPosition,
    WorkerTrade,
)
from .vocab import normalize_position_side, normalize_side

# strategy.models 仅类型检查期导入：worker.crud ← worker.__init__ ← collector
# （collector.api.archive → worker.decorators）存在模块级循环链，运行时顶层
# import 会在测试/首包加载时命中 partially initialized module；真正使用处
# 一律走函数内 import（见 find_strategy_by_name_or_id / get_worker_strategy_parameters）
if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from strategy.models import Strategy

    from . import schemas


def find_strategy_by_name_or_id(
    db: Session, strategy_id: int | None = None, strategy_name: str | None = None
) -> dict[str, Any] | None:
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
        # 跨模块模型用绝对导入且保持函数内 import（防循环依赖，同 strategy_manager）：
        # uvicorn main:app 下 worker 是顶层包，相对导入 ..strategy 会抛
        # "attempted relative import beyond top-level package"，被下方 except
        # 吞成 None 后任何策略都会被误判为「关联策略不存在」
        from strategy.models import Strategy

        # 优先通过 ID 查找
        if strategy_id:
            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if strategy:
                return {
                    "id": strategy.id,
                    "name": strategy.name,
                    "file_name": getattr(strategy, "file_name", None),
                }
            else:
                # ID 找不到，记录警告并尝试通过名称查找
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"策略 ID {strategy_id} 未找到，尝试通过名称查找...")

        # 通过名称查找（容错机制）
        if strategy_name:
            strategy = (
                db.query(Strategy)
                .filter(
                    and_(
                        Strategy.name == strategy_name,
                        not Strategy.is_deleted if hasattr(Strategy, "is_deleted") else True,
                    )
                )
                .first()
            )

            if strategy:
                return {
                    "id": strategy.id,
                    "name": strategy.name,
                    "file_name": getattr(strategy, "file_name", None),
                }

        return None

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"查找策略失败: {e}")
        return None


def create_worker(db: Session, worker_data: schemas.WorkerCreate) -> Worker:
    """创建Worker

    `strategy_type` 不在 WorkerCreate 里：worker 镜像被引用策略行的类型
    （rule/rl），本函数回填。/workers/{id}/lifecycle/optimize 按该列分支
    （worker/routes.py:1373），不回填会让 RL 策略的 worker 走成 rule 分支。
    """
    import json

    strategy_type = "rule"
    if worker_data.strategy_id:
        # 函数内 import：跨模块模型（同 find_strategy_by_name_or_id，防 worker ← collector 循环链）
        from strategy.models import Strategy

        strategy = db.query(Strategy).filter(Strategy.id == worker_data.strategy_id).first()
        if strategy is not None and strategy.strategy_type:
            strategy_type = strategy.strategy_type

    db_worker = Worker(
        name=worker_data.name,
        description=worker_data.description,
        strategy_id=worker_data.strategy_id,
        strategy_name=worker_data.strategy_name,  # 策略名称（冗余存储，用于 strategy_id 失效时回退查找）
        strategy_type=strategy_type,
        env_vars=json.dumps(worker_data.env_vars) if worker_data.env_vars else "{}",
        config=json.dumps({**(worker_data.config or {}), "strategy_file_name": worker_data.strategy_file_name})
        if (worker_data.config or worker_data.strategy_file_name)
        else "{}",
        status="stopped",
        # 归属用户ID（P1-07 工人属地）：路由层已从 JWT sub 注入；历史数据/未登录为 None
        owner_id=worker_data.owner_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    # trading_config 必须走 set_trading_config_dict 落库（Phase A 双写收敛点）：
    # 直接 json.dumps(model_dump()) 只剩 interval 单键，会绕过双键共存承诺
    db_worker.set_trading_config_dict(worker_data.trading_config.model_dump())
    db.add(db_worker)
    db.commit()
    db.refresh(db_worker)
    return db_worker


def get_worker(db: Session, worker_id: int) -> Worker | None:
    """获取Worker"""
    return db.query(Worker).filter(Worker.id == worker_id).first()


def get_workers(
    db: Session,
    status: str | None = None,
    strategy_id: int | None = None,
    skip: int = 0,
    limit: int = 20,
    owner_id: int | None = None,
) -> tuple[list[Worker], int]:
    """获取Worker列表

    `owner_id` 提供时按归属过滤（非特权用户只看自己的 worker）；
    None 不过滤（admin / 服务令牌走全量）。
    """
    query = db.query(Worker)

    if status:
        query = query.filter(Worker.status == status)
    if strategy_id:
        query = query.filter(Worker.strategy_id == strategy_id)
    if owner_id is not None:
        # ponytail: 只做归属过滤，不做行级 ACL 推广到所有端点——
        # 逐端点鉴权（详情/订单/决策）需要统一 dependency，另行立项
        query = query.filter(Worker.owner_id == owner_id)

    total = query.count()
    workers = query.order_by(desc(Worker.created_at)).offset(skip).limit(limit).all()
    return workers, total


def update_worker(db: Session, worker_id: int, worker_data: schemas.WorkerUpdate) -> Worker | None:
    """更新Worker"""
    import json

    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return None

    update_data = worker_data.model_dump(exclude_unset=True)

    # strategy_file_name 不是 ORM 列，与 create_worker 口径一致：合并进 config JSON 落库
    strategy_file_name = update_data.pop("strategy_file_name", None)

    # trading_config / config 是 Text JSON 列，序列化后落库。
    # 显式传 null 视为「不修改」并丢弃该键，避免落入下方 setattr 把列置为 NULL。
    for json_field in ("trading_config", "config"):
        if json_field in update_data:
            value = update_data.pop(json_field)
            if value is not None:
                if json_field == "trading_config":
                    # trading_config 走双写收敛点（Phase A）：K线周期在 interval/timeframe 两键同步
                    worker.set_trading_config_dict(value)
                else:
                    setattr(worker, json_field, json.dumps(value))

    if strategy_file_name is not None:
        merged_config = worker.get_config_dict()
        merged_config["strategy_file_name"] = strategy_file_name
        worker.config = json.dumps(merged_config)

    # 其余字段均为真实 ORM 列，直接 setattr
    for field, value in update_data.items():
        setattr(worker, field, value)

    worker.updated_at = datetime.now()
    db.commit()
    db.refresh(worker)
    return worker


def update_worker_config(db: Session, worker_id: int, config: dict[str, Any]) -> Worker | None:
    """更新Worker配置

    P1-6：写回收为单条 UPDATE 直改 config/updated_at 列（原来是先改 ORM
    对象再 commit，fk：ORM 脏对象在并发 session 复用下有隐性覆盖面）。
    ponytail: 跨方言（sqlite/duckdb）没有可用的 JSON merge 原生函数，「合并
    到最新 config」必须在应用层读到现状后进行，读写窗内的并发更新仍可能
    互覆盖；当前调用链均为单请求线程串行，窗口可接受。切 PostgreSQL 后可
    换 jsonb 合并运算符做成纯原子语句。
    """
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return None

    current_config = worker.get_config_dict()
    current_config.update(config)
    db.query(Worker).filter(Worker.id == worker_id).update(
        {
            "config": json.dumps(current_config),
            "updated_at": datetime.now(),
        },
        synchronize_session=False,
    )
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
    """克隆Worker

    P1-6：原实现「先 commit 主记录、再复制参数、再次 commit」，中途失败会
    留下半克隆。改为单事务：主记录 flush 生成 id 后在同一事务内复制参数，
    任一步失败整体回滚。
    """
    source_worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not source_worker:
        msg = "源Worker不存在"
        raise ValueError(msg)

    new_worker = Worker(
        name=request.new_name,
        description=source_worker.description,
        strategy_id=source_worker.strategy_id,
        trading_config=source_worker.trading_config if request.copy_config else "{}",
        env_vars=source_worker.env_vars if request.copy_config else "{}",
        config=source_worker.config if request.copy_config else "{}",
        status="stopped",
        # 克隆副本继承源 worker 的归属（P1-07 工人属地），保持属主不变
        owner_id=source_worker.owner_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    try:
        db.add(new_worker)
        # flush 拿到 new_worker.id，参数复制仍在同一事务内
        db.flush()

        if request.copy_parameters:
            params = db.query(WorkerParameter).filter(WorkerParameter.worker_id == worker_id).all()
            for param in params:
                db.add(
                    WorkerParameter(
                        worker_id=new_worker.id,
                        param_name=param.param_name,
                        param_value=param.param_value,
                        param_type=param.param_type,
                        description=param.description,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(new_worker)
    return new_worker


def update_worker_status(db: Session, worker_id: int, status: str, pid: int | None = None) -> Worker | None:
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


def create_worker_log(
    db: Session,
    worker_id: int,
    level: str,
    message: str,
    source: str = "worker",
    timestamp: datetime | None = None,
) -> WorkerLog:
    """创建Worker日志"""
    log = WorkerLog(
        worker_id=worker_id,
        level=level,
        message=message,
        source=source,
        timestamp=timestamp or datetime.now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_worker_logs(
    db: Session,
    worker_id: int,
    level: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[WorkerLog]:
    """获取Worker日志"""
    query = db.query(WorkerLog).filter(WorkerLog.worker_id == worker_id)

    if level:
        query = query.filter(WorkerLog.level == level)
    if start_time:
        query = query.filter(WorkerLog.timestamp >= start_time)
    if end_time:
        query = query.filter(WorkerLog.timestamp <= end_time)

    return query.order_by(desc(WorkerLog.timestamp)).limit(limit).all()


def clear_worker_logs(db: Session, worker_id: int, before_days: int | None = None) -> int:
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


def create_worker_metric(db: Session, worker_id: int, metrics: dict[str, Any]) -> WorkerMetric:
    """创建Worker指标记录"""
    metric = WorkerMetric(
        worker_id=worker_id,
        network_in=metrics.get("network_in", 0),
        network_out=metrics.get("network_out", 0),
        active_tasks=metrics.get("active_tasks", 0),
        timestamp=datetime.now(),
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def get_metrics_history(
    db: Session,
    worker_id: int,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    interval: str = "1m",
) -> list[dict[str, Any]]:
    """获取历史指标"""
    query = db.query(WorkerMetric).filter(WorkerMetric.worker_id == worker_id)

    if start_time:
        query = query.filter(WorkerMetric.timestamp >= start_time)
    if end_time:
        query = query.filter(WorkerMetric.timestamp <= end_time)

    metrics = query.order_by(WorkerMetric.timestamp).all()
    return [m.to_dict() for m in metrics]


# Worker参数操作


def get_worker_parameters(db: Session, worker_id: int) -> list[WorkerParameter]:
    """获取Worker参数"""
    return db.query(WorkerParameter).filter(WorkerParameter.worker_id == worker_id).all()


def get_worker_strategy_parameters(db: Session, worker_id: int) -> list[dict[str, Any]]:
    """获取 worker 的策略参数视图：策略库 schema 为主干，worker_parameters 快照为覆盖值。

    此前 GET /workers/{id}/strategy/parameters 只读快照表——快照仅在用户保存过
    参数编辑后才有数据，导致从未编辑过参数的 worker 前端一直显示「无可编辑参数」。
    合并规则：每行生效值 = 快照覆盖值优先，回退策略库 schema 默认值
    （strategies.parameters 是 JSON 数组，元素含 name/type/default/description/required，
    由策略 reparse/注册时 AST 解析写入；运行时 strategy_manager start 也读同一列）。
    """
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    schema_items: list[dict[str, Any]] = []
    if worker is not None and worker.strategy_id:
        # 运行时 Strategy 走函数内 import（见文件顶部 TYPE_CHECKING 注释的循环链说明）
        from strategy.models import Strategy

        strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
        if strategy is not None and strategy.parameters:
            try:
                raw = json.loads(strategy.parameters)
            except (json.JSONDecodeError, TypeError):
                raw = None
            if isinstance(raw, list):
                schema_items = [item for item in raw if isinstance(item, dict) and item.get("name")]

    overrides = {p.param_name: p for p in get_worker_parameters(db, worker_id)}

    result: list[dict[str, Any]] = []
    for item in schema_items:
        name = item["name"]
        override = overrides.pop(name, None)
        schema_default = item.get("default")
        row: dict[str, Any] = {
            "worker_id": worker_id,
            "param_name": name,
            # 生效值：worker 覆盖值优先，回退 schema 默认值（None 表示策略内部默认为空）
            "param_value": override.get_value() if override is not None else schema_default,
            "param_type": str(item.get("type") or "string").lower(),
            "default_value": schema_default,
            "description": item.get("description") or "",
            "required": bool(item.get("required")),
            "editable": True,
        }
        if override is not None:
            row["id"] = override.id
            if override.description:
                row["description"] = override.description
        result.append(row)

    # schema 之外的残留覆盖值（策略更新改名后快照还在）：原样保留，避免用户已保存的值静默失去展示
    for orphan in overrides.values():
        result.append(orphan.to_dict())

    return result


def update_worker_parameters(db: Session, worker_id: int, parameters: dict[str, Any]) -> None:
    """更新Worker参数"""
    for name, value in parameters.items():
        param = (
            db.query(WorkerParameter)
            .filter(
                and_(
                    WorkerParameter.worker_id == worker_id,
                    WorkerParameter.param_name == name,
                )
            )
            .first()
        )

        if param:
            param.param_value = value
        else:
            param = WorkerParameter(
                worker_id=worker_id,
                param_name=name,
                param_value=value,
                param_type=type(value).__name__,
                editable=True,
            )
            db.add(param)

    db.commit()


# Worker交易操作


def get_worker_trades(
    db: Session,
    worker_id: int,
    symbol: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[WorkerTrade], int]:
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


def sum_daily_realized_pnl(worker_id: int) -> float:
    """Worker 当日（本地 0 点起）已实现盈亏汇总。

    与 B3 风控引擎回灌共用同一聚合口径（RiskConfig.feeder 的观测源），
    从 LiveTradeSync.daily_realized_pnl 抽取——两处必须同源，避免
    risk-status 展示值与引擎额度判定各算各的。realized_pnl 为空按 0 计
    （现货无 realized_pnl 列值）。"""
    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    with get_db_session() as db:
        total = (
            db.query(func.coalesce(func.sum(WorkerTrade.realized_pnl), 0.0))
            .filter(
                WorkerTrade.worker_id == worker_id,
                WorkerTrade.entry_time >= day_start,
            )
            .scalar()
        )
    return float(total or 0.0)


def create_trade_if_not_exists(db: Session, trade_data: dict) -> WorkerTrade | None:
    """幂等写入成交；未新建（fill_id 查重命中 / evidence 冲突）返回 None，新建返回行。

    返回值语义 = 「是否真的落了一笔」：paper 链路靠先自查绕过旧版无法区分的
    缺陷，live 链路（sync_once）直接按返回值统计新落库笔数，避免重复回报
    被计成“新落库 N 笔”的日志谎报。
    """
    # 三个调用方（live/paper sync、event_handler）各自归一，这里再兜一道：
    # create_trade 与 worker_fill_evidence 同事务双写，防止 evidence 旁路脏写
    trade_data["side"] = normalize_side(trade_data["side"])
    existing = db.query(WorkerTrade).filter(WorkerTrade.fill_id == trade_data["fill_id"]).first()
    if existing:
        return None

    # 函数内 import：utils.config_manager 顶层会拉起 collector.db（SystemConfig），
    # 而 crud 位于 worker.__init__ 循环链内（见文件头注释），沿用既有防御口径
    from sqlalchemy.dialects import postgresql, sqlite

    from utils.config_manager import get_flag

    # 成交证据链（P0-01）：venue_trade_id 幂等主锚，与 trade 行同 session 同事务
    # 提交。rowcount == 0 说明这笔成交已被应用过（跨路径/前次写入命中）——等于
    # 在 fill_id 查重之外的第二把锁，防止 live / 恢复同步两条路重复入账。
    # client_order_id 缺失（paper / journal 通道不提供）时不写 evidence，
    # 幂等完全退回 fill_id 查重（旧行为）。venue_trade_id 列的值域是交易所
    # 原生成交易 id（myTrades 语境，词表按审计裁决保留），数据源即本笔 fill_id 的值
    if get_flag("worker.execution.fill_evidence_enabled", True) and trade_data.get("client_order_id"):
        dialect_insert = sqlite.insert if db.get_bind().dialect.name == "sqlite" else postgresql.insert
        stmt = (
            dialect_insert(WorkerFillEvidence)
            .values(
                worker_id=trade_data["worker_id"],
                client_order_id=trade_data["client_order_id"],
                venue_order_id=trade_data.get("venue_order_id"),
                venue_trade_id=trade_data["fill_id"],
                symbol=trade_data["symbol"],
                side=trade_data["side"],
                quantity=trade_data["quantity"],
                price=trade_data.get("price"),
                fee=trade_data.get("fee"),
                source="sync",
            )
            .on_conflict_do_nothing(index_elements=["venue_trade_id"])
        )
        if db.execute(stmt).rowcount == 0:
            # 证据已存在而 trade 行缺失仅在手工修数据的异常态出现：不再写 trade，跳过
            return None

    db_trade = WorkerTrade(**trade_data)
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade


def create_order_if_not_exists(db: Session, order_data: dict) -> WorkerOrder:
    # 落库信任边界归一：side 上游词形不定（交易所/事件原词），统一 canonical 小写
    order_data["side"] = normalize_side(order_data["side"])
    existing = db.query(WorkerOrder).filter(WorkerOrder.client_order_id == order_data["client_order_id"]).first()
    if existing:
        return existing
    db_order = WorkerOrder(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def upsert_order_filled_from_fill(
    db: Session,
    worker_id: int,
    client_order_id: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: float,
    venue_order_id: str | None = None,
    filled_at: datetime | None = None,
    position_side: str = "both",
    reduce_only: bool = False,
) -> None:
    """成交回报驱动的订单 upsert（FILLED 终态）。

    paper/live 同步链路只能从成交明细看到订单（下单意图事件引擎不回传，
    events.order.* 无发布方），因此首笔 fill 直接落 FILLED 行——订单至少有
    完整的成交历史；同一订单的分笔 fill 累加 filled_quantity 并重算加权均价。
    委托量（quantity）不可知，以首笔成交量近似，分笔场景下会小于 filled_quantity。

    幂等性由调用方保证：仅在 trade 新落库（create_trade_if_not_exists 返回
    新行 / 查重未命中）时调用，查重命中不重复累加。
    """
    order = db.query(WorkerOrder).filter(WorkerOrder.client_order_id == client_order_id).first()
    if order is None:
        order = WorkerOrder(
            client_order_id=client_order_id,
            venue_order_id=venue_order_id,
            worker_id=worker_id,
            symbol=symbol,
            side=normalize_side(side),
            order_type=order_type.upper(),
            quantity=quantity,
            price=None,  # 委托价不可知（市价单），留空展示为“市价”
            filled_quantity=quantity,
            avg_fill_price=price,
            # position_side 是声明值（调用方透传，不从 side 推导，铁律2）
            position_side=normalize_position_side(position_side),
            reduce_only=bool(reduce_only),
            status="FILLED",
            filled_at=filled_at or datetime.now(),
        )
        db.add(order)
    else:
        total_qty = (order.filled_quantity or 0.0) + quantity
        # 数量加权均价（分笔成交逐步逼近真实 VWAP）
        order.avg_fill_price = (
            ((order.avg_fill_price or 0.0) * (order.filled_quantity or 0.0) + price * quantity) / total_qty
            if total_qty
            else price
        )
        order.filled_quantity = total_qty
        if order.status != "FILLED":
            order.status = "FILLED"
            order.filled_at = filled_at or datetime.now()
        if venue_order_id and not order.venue_order_id:
            order.venue_order_id = venue_order_id
    db.commit()


def create_position_if_not_exists(db: Session, position_data: dict) -> WorkerPosition:
    existing = db.query(WorkerPosition).filter(WorkerPosition.position_id == position_data["position_id"]).first()
    if existing:
        return existing
    db_position = WorkerPosition(**position_data)
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    return db_position


def update_position(db: Session, position_id: str, position_data: dict) -> WorkerPosition | None:
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


def derive_positions_from_trades(db: Session, worker_id: int) -> list[dict]:
    """从 worker_trades 未配对 fill（round_trip_id IS NULL）推导当前持仓。

    worker_positions 表常态写入口：paper 由 PaperTradeSync._sync_positions 每泵
    轮对账落库（P1-10）；live 的 LiveTradeRecorder 事件链路仍未接线。表为空时
    （worker 已停止 / 引擎尚未产出 fill）以本推导兜底，「当前持仓」与「持仓中」
    行（同一份数据的未配对 fill 视图）保持同一口径。

    过滤用 round_trip_id 而非 realized_pnl：paper 配对语义下两者等价（组键只在
    round-trip 关闭时回填）；live 由 LiveTradeSync 落库、从不回填组键——若按
    realized_pnl IS NULL 过滤会漏光 live 成交（币安开仓 fill 的 realizedPnl
    也是 0，早期版本误标 0.0 导致 live 持仓恒空，历史误标行已一次性清洗）。

    按净持仓回推：未配对 fill 的净持仓量按 symbol 聚合，非零即当前持仓，
    返回字段形状与 WorkerPosition.to_dict() 完全对齐。

    ponytail: 反手场景下反手 fill 已被配对（有组键）而排除在推导之外，其作为
    反手后新仓 entry 的部分会丢失——paper 侧已由 PaperTradeSync._sync_positions
    以引擎 snapshot 净仓为权威落库规避（本推导仅作表空兜底）；live 天花板仍在
    （引擎/交易所不回传 per-fill 净仓轨迹），升级路径是接 binance user-data
    position 流。
    """
    fills = (
        db.query(WorkerTrade)
        .filter(WorkerTrade.worker_id == worker_id, WorkerTrade.round_trip_id.is_(None))
        .order_by(WorkerTrade.entry_time.asc())
        .all()
    )
    if not fills:
        return []

    # 按 symbol 聚合净持仓：buy 为多头增量、sell 为空头增量
    rows_by_symbol: dict[str, list[WorkerTrade]] = {}
    for fill in fills:
        rows_by_symbol.setdefault(fill.symbol, []).append(fill)

    derived: list[dict] = []
    for symbol, rows in rows_by_symbol.items():
        net = sum(r.quantity if normalize_side(r.side) == "buy" else -r.quantity for r in rows)
        if net == 0:
            continue  # 净额归零 = 该 symbol 已无持仓（部分平仓后的残余互相抵消）

        # 开仓均价 = 与净仓同向的未配对 fill 的成交量加权价
        # （部分平仓 fill 虽也是未配对行，但方向相反，不参与均价）
        same_dir = [r for r in rows if (net > 0) == (normalize_side(r.side) == "buy")]
        same_qty = sum(r.quantity for r in same_dir)
        entry_price = sum(r.quantity * r.price for r in same_dir) / same_qty if same_qty else 0.0

        quantity = abs(net)
        # 近似市价：该 symbol 最后一笔未配对 fill 的成交价（加仓/部分平仓均按市价撮合）
        current_price = rows[-1].price
        unrealized = (current_price - entry_price) * quantity if net > 0 else (entry_price - current_price) * quantity
        derived.append(
            {
                "id": None,
                "worker_id": worker_id,
                "position_id": f"derived:{worker_id}:{symbol}",
                "symbol": symbol,
                # 派生持仓是推导值，此处推导合法（铁律2 只约束声明字段）
                "position_side": "long" if net > 0 else "short",
                # deprecated 响应别名：老前端消费方分批切换，与 position_side 恒同值
                "side": "long" if net > 0 else "short",
                "quantity": quantity,
                "entry_price": entry_price,
                "current_price": current_price,
                "unrealized_pnl": unrealized,
                "unrealized_pnl_pct": (unrealized / (quantity * entry_price) * 100 if quantity and entry_price else 0),
                "realized_pnl": 0.0,
                "margin_used": 0.0,
                "status": "OPEN",
                "opened_at": rows[0].entry_time.isoformat() if rows[0].entry_time else None,
                "updated_at": datetime.now().isoformat(),
            }
        )
    return derived


def get_all_worker_trades(
    db: Session,
    worker_id: int,
    symbol: str | None = None,
    side: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[WorkerTrade]:
    query = db.query(WorkerTrade).filter(WorkerTrade.worker_id == worker_id)
    if symbol:
        query = query.filter(WorkerTrade.symbol == symbol)
    if side:
        query = query.filter(WorkerTrade.side == normalize_side(side))  # 大小写不敏感筛选
    if start_time:
        query = query.filter(WorkerTrade.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerTrade.created_at <= end_time)
    return query.order_by(desc(WorkerTrade.created_at)).all()


def get_worker_order_by_id(db: Session, worker_id: int, client_order_id: str) -> WorkerOrder | None:
    return (
        db.query(WorkerOrder)
        .filter(
            and_(
                WorkerOrder.worker_id == worker_id,
                WorkerOrder.client_order_id == client_order_id,
            )
        )
        .first()
    )


def update_worker_order_status(
    db: Session,
    order_id: int,
    status: str,
    filled_quantity: float,
    avg_fill_price: float,
    commission: float,
    venue_order_id: str,
) -> WorkerOrder | None:
    order = db.query(WorkerOrder).filter(WorkerOrder.id == order_id).first()
    if not order:
        return None
    order.status = status
    order.filled_quantity = filled_quantity
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
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict:
    """
    获取交易汇总统计（优化版 - 使用 SQL 聚合）

    Uses SQLAlchemy aggregate functions to compute statistics at the database level,
    avoiding loading all trade records into memory.
    """
    return get_trading_summary_optimized(db, worker_id, start_time, end_time)


def get_trade_history_chart(db: Session, worker_id: int, days: int = 30) -> dict:
    """
    交易收益曲线数据：X 轴按时间窗口完整铺满，无成交的桶补 0
    （daily_pnl=0、trade_count=0，累计值保持前值 —— 曲线呈水平而非归零）。

    粒度选择：
    - 24h 窗口（days<=1）：按小时铺 24 个点，否则一天只有一个点看不出走势
    - 常规窗口：按天从窗口起点铺到今天
    - all 档（days>365，映射 100 年）：起点收敛到首笔成交，避免铺出上万个空点；
      完全无成交返回空图。

    ponytail: 用 Python 内存聚合而非 SQL 分组 —— 单 worker 交易量级小，
    且要把无数据的日期/小时补零铺轴，SQL group 只能返回有数据的桶。
    """
    now = datetime.now()
    start = now - timedelta(days=days)

    if days > 365:
        first_trade_at = db.query(func.min(WorkerTrade.created_at)).filter(WorkerTrade.worker_id == worker_id).scalar()
        if not first_trade_at:
            return {
                "dates": [],
                "cumulative_pnl": [],
                "daily_pnl": [],
                "trade_count": [],
            }
        start = max(start, first_trade_at)

    trades = (
        db.query(WorkerTrade)
        .filter(
            and_(
                WorkerTrade.worker_id == worker_id,
                WorkerTrade.created_at >= start,
            )
        )
        .order_by(WorkerTrade.created_at)
        .all()
    )

    if days <= 1:
        # 24h 档：最近 24 个整点
        bucket_num = 24
        bucket_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        step = timedelta(hours=1)
        label_fmt = "%m-%d %H:%M"
    else:
        bucket_num = (now.date() - start.date()).days + 1
        bucket_start = datetime.combine(start.date(), time.min)
        step = timedelta(days=1)
        label_fmt = "%Y-%m-%d"

    def _bucket_index(created_at: datetime) -> int:
        if days <= 1:
            return int((created_at.replace(minute=0, second=0, microsecond=0) - bucket_start) / step)
        return (created_at.date() - bucket_start.date()).days

    buckets = [{"pnl": 0.0, "count": 0} for _ in range(bucket_num)]
    for t in trades:
        if not t.created_at:
            continue
        idx = _bucket_index(t.created_at)
        if 0 <= idx < bucket_num:
            buckets[idx]["pnl"] += t.realized_pnl or 0.0
            buckets[idx]["count"] += 1

    dates: list[str] = []
    cumulative_pnl: list[float] = []
    daily_pnl: list[float] = []
    trade_count: list[int] = []
    cumulative = 0.0
    for i in range(bucket_num):
        cumulative += buckets[i]["pnl"]
        dates.append((bucket_start + step * i).strftime(label_fmt))
        cumulative_pnl.append(round(cumulative, 2))
        daily_pnl.append(round(buckets[i]["pnl"], 2))
        trade_count.append(buckets[i]["count"])

    return {
        "dates": dates,
        "cumulative_pnl": cumulative_pnl,
        "daily_pnl": daily_pnl,
        "trade_count": trade_count,
    }


def get_pnl_distribution(db: Session, worker_id: int, start_time: datetime | None = None) -> dict:
    """
    获取 PNL 分布统计（优化版 - 使用 SQL 聚合计算统计量）

    使用 SQLAlchemy 聚合函数在数据库层面计算 mean、std，
    仅加载 pnl_values 用于直方图计算。
    start_time 非空时仅统计该时刻之后的成交（总览页时间窗口切换依赖此过滤）。
    """
    filters = [WorkerTrade.worker_id == worker_id, WorkerTrade.realized_pnl.isnot(None)]
    if start_time:
        filters.append(WorkerTrade.created_at >= start_time)

    # 使用 SQL 聚合计算统计量
    stats_query = db.query(
        func.count(WorkerTrade.id).label("count"),
        func.sum(WorkerTrade.realized_pnl).label("sum_pnl"),
        func.avg(WorkerTrade.realized_pnl).label("mean_pnl"),
        func.min(WorkerTrade.realized_pnl).label("min_pnl"),
        func.max(WorkerTrade.realized_pnl).label("max_pnl"),
    ).filter(*filters)

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
    pnl_values = db.query(WorkerTrade.realized_pnl).filter(*filters).all()
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
    status: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
    position_side: str | None = None,
    reduce_only: bool | None = None,
) -> tuple[list[WorkerOrder], int]:
    query = db.query(WorkerOrder).filter(WorkerOrder.worker_id == worker_id)

    if status:
        query = query.filter(WorkerOrder.status == status)
    if symbol:
        query = query.filter(WorkerOrder.symbol == symbol)
    if side:
        query = query.filter(WorkerOrder.side == normalize_side(side))  # 大小写不敏感筛选
    if order_type:
        query = query.filter(WorkerOrder.order_type == order_type)
    if start_time:
        query = query.filter(WorkerOrder.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerOrder.created_at <= end_time)
    if position_side:
        query = query.filter(WorkerOrder.position_side == normalize_position_side(position_side))
    if reduce_only is not None:
        query = query.filter(WorkerOrder.reduce_only == reduce_only)

    total = query.count()
    orders = query.order_by(desc(WorkerOrder.created_at)).offset(skip).limit(limit).all()
    return orders, total


def get_worker_positions_filtered(
    db: Session,
    worker_id: int,
    status: str | None = "OPEN",
    symbol: str | None = None,
    side: str | None = None,
) -> list[WorkerPosition]:
    query = db.query(WorkerPosition).filter(WorkerPosition.worker_id == worker_id)

    if status:
        query = query.filter(WorkerPosition.status == status)
    if symbol:
        query = query.filter(WorkerPosition.symbol == symbol)
    if side:
        # positions 的 "side" 参数语义=持仓方向（long/short/both），与 buy/sell 不同值域
        query = query.filter(WorkerPosition.position_side == normalize_position_side(side))

    return query.order_by(desc(WorkerPosition.updated_at)).all()


def get_trading_summary_optimized(
    db: Session,
    worker_id: int,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict:
    query = db.query(
        func.count(WorkerTrade.id).label("total_trades"),
        func.sum(case((WorkerTrade.realized_pnl > 0, 1), else_=0)).label("winning_trades"),
        func.sum(case((WorkerTrade.realized_pnl < 0, 1), else_=0)).label("losing_trades"),
        func.sum(WorkerTrade.realized_pnl).label("total_pnl"),
        func.sum(case((WorkerTrade.realized_pnl > 0, WorkerTrade.realized_pnl), else_=0)).label("total_profit"),
        func.sum(case((WorkerTrade.realized_pnl < 0, WorkerTrade.realized_pnl), else_=0)).label("total_loss"),
        func.max(WorkerTrade.realized_pnl).label("largest_profit"),
        func.min(WorkerTrade.realized_pnl).label("largest_loss"),
        func.sum(WorkerTrade.notional).label("total_volume"),
        func.sum(WorkerTrade.fee).label("total_fees"),
        func.count(func.distinct(func.date(WorkerTrade.created_at))).label("trading_days"),
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
    symbol: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    pnl_status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
    position_side: str | None = None,
    reduce_only: bool | None = None,
) -> tuple[list[WorkerTrade], int]:
    query = db.query(WorkerTrade).filter(WorkerTrade.worker_id == worker_id)

    if symbol:
        query = query.filter(WorkerTrade.symbol == symbol)
    if side:
        query = query.filter(WorkerTrade.side == normalize_side(side))  # 大小写不敏感筛选
    if order_type:
        query = query.filter(WorkerTrade.order_type == order_type)
    if pnl_status is not None:
        if pnl_status == "profit":
            query = query.filter(WorkerTrade.realized_pnl > 0)
        elif pnl_status == "loss":
            query = query.filter(WorkerTrade.realized_pnl < 0)
        elif pnl_status == "flat":
            query = query.filter(WorkerTrade.realized_pnl == 0)
        elif pnl_status == "closed":
            # 已平仓 = 配对盈亏已回填的行（entry fill 行 realized_pnl 为 None，不算平仓记录）
            query = query.filter(WorkerTrade.realized_pnl.isnot(None))
        elif pnl_status == "open":
            # 持仓中 = 尚未配对出 round-trip 的 fill 行（开仓成交，realized_pnl 未回填）
            query = query.filter(WorkerTrade.realized_pnl.is_(None))
    if start_time:
        query = query.filter(WorkerTrade.created_at >= start_time)
    if end_time:
        query = query.filter(WorkerTrade.created_at <= end_time)
    if position_side:
        query = query.filter(WorkerTrade.position_side == normalize_position_side(position_side))
    if reduce_only is not None:
        query = query.filter(WorkerTrade.reduce_only == reduce_only)

    total = query.count()
    trades = query.order_by(desc(WorkerTrade.created_at)).offset(skip).limit(limit).all()
    return trades, total


def _build_group_item(group_key: str, group_rows: list[WorkerTrade]) -> dict:
    """把一个 round-trip 组的 fill 行组装成回测 TradeTable 契约的一行。

    契约模板：backtest/backtest_loop.py::_format_round_trip_trades。
    """
    rows = sorted(group_rows, key=lambda r: (r.entry_time or r.created_at or datetime.min, r.id))
    # 组键以 "rt:" 开头 = 引擎配对过；"row:" 前缀 = 无配对行（历史 / live 成交）
    unpaired = not group_key.startswith("rt:")

    def _vwap(rows_: list[WorkerTrade]) -> float:
        qty = sum(r.quantity for r in rows_)
        return sum(r.notional for r in rows_) / qty if qty else 0.0

    def _ts(dt: datetime | None) -> int:
        return int(dt.timestamp()) if dt else 0

    def _iso(dt: datetime | None) -> str | None:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") if dt else None

    # 组内首笔 fill 的 side 定开仓方向：buy → long。
    # ponytail: 反手型 round-trip（同组含双向成交）可能把 offset 标错，
    # 天花板是引擎未来把 entry/exit fill 归属随配对一起带出，届时可精确标注
    entry_side = rows[0].side
    direction = None if unpaired else ("long" if entry_side == "buy" else "short")
    open_rows = [r for r in rows if r.side == entry_side]
    close_rows = [r for r in rows if r.side != entry_side]

    entry_price = _vwap(open_rows) if open_rows else rows[0].price
    exit_price = _vwap(close_rows) if close_rows else entry_price
    quantity = sum(r.quantity for r in close_rows) or sum(r.quantity for r in open_rows)
    # unpaired 行 realized_pnl 可能为 None：记 0，避免前端数值格式化拿 null 崩
    pnl = sum(r.realized_pnl or 0.0 for r in rows)

    first = rows[0]
    first_dt = first.entry_time or first.created_at
    exit_dt = max((r.exit_time for r in rows if r.exit_time), default=None)

    def _fill_json(r: WorkerTrade) -> dict:
        dt = r.entry_time or r.created_at
        return {
            # 分组视图的 fill_id 用行主键（DB 自增），与回测的引擎 fill id 语义不同
            "fill_id": r.id,
            "side": r.side,
            "offset": "open" if r.side == entry_side else "close",
            "price": r.price,
            "quantity": r.quantity,
            "timestamp": _ts(dt),
            "formatted_time": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "",
            "status": "filled",
        }

    return {
        "trade_id": group_key,
        "symbol": first.symbol,
        "timestamp": _ts(first_dt),
        "formatted_time": first_dt.strftime("%Y-%m-%d %H:%M:%S") if first_dt else "",
        "entry_time": _iso(first_dt),
        "exit_time": _iso(exit_dt),
        "exit_timestamp": _ts(exit_dt) if exit_dt else None,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": quantity,
        "pnl": pnl,
        "return_pct": (pnl / (entry_price * quantity) * 100.0) if entry_price * quantity > 0 else 0.0,
        "direction": direction,
        "entry_side": entry_side,
        "exit_side": "sell" if entry_side == "buy" else "buy",
        "status": "unpaired" if unpaired else "closed",
        "entry_fill_ids": [r.id for r in open_rows],
        "exit_fill_ids": [r.id for r in close_rows],
        "fills": [_fill_json(r) for r in rows],
    }


def get_worker_trades_grouped(
    db: Session,
    worker_id: int,
    symbol: str | None = None,
    direction: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = 0,
    limit: int = 10,
) -> tuple[list[dict], int]:
    """按 round-trip 组键聚合成交，返回 (当前页 items, 组总数)。

    过滤层级：symbol 行级 → 组聚合 → 日期组级（组内 MAX(created_at)）
    → 组间倒序 → direction 组级（items 构建后）→ 内存分页。
    ponytail: 全量取该 worker 的行在内存分组/分页，单 worker 百~万行可承受；
    天花板是单 worker 数十万行时需改 SQL group-by 分页，升级路径明确。
    """
    query = db.query(WorkerTrade).filter(WorkerTrade.worker_id == worker_id)
    if symbol:
        query = query.filter(WorkerTrade.symbol == symbol)
    rows = query.all()
    if not rows:
        return [], 0

    groups: dict[str, list[WorkerTrade]] = {}
    for r in rows:
        # 行组键：有配对的多行归一组，无配对行用 fill_id 自成一组
        groups.setdefault(r.round_trip_id or f"row:{r.fill_id}", []).append(r)

    end_bound = end_time
    if end_bound is not None and (end_bound.hour, end_bound.minute, end_bound.second, end_bound.microsecond) == (
        0,
        0,
        0,
        0,
    ):
        # 日期选择器只给到「日」：补到当日最后一刻，避免漏掉当天全部成交
        end_bound = end_bound + timedelta(days=1) - timedelta(microseconds=1)

    kept: list[tuple[datetime, str, list[WorkerTrade]]] = []
    for key, group_rows in groups.items():
        last = max((r.created_at for r in group_rows if r.created_at), default=None)
        if start_time and last is not None and last < start_time:
            continue
        if end_bound and last is not None and last > end_bound:
            continue
        kept.append((last or datetime.min, key, group_rows))

    # 组间按最后活动时间倒序，与平铺表「最新在前」观感一致
    kept.sort(key=lambda x: x[0], reverse=True)

    items = [_build_group_item(key, group_rows) for _, key, group_rows in kept]
    if direction:
        # direction 过滤放在 items 构建后：unpaired 组 direction=None 自动排除
        items = [it for it in items if it["direction"] == direction]

    return items[skip : skip + limit], len(items)
