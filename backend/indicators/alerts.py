"""指标信号提醒：规则评估 + 去重 + 通知文本组装（P2-07）。

评估口径：按规则 symbol/period 拉最近若干根K线（缺数自动向交易所回补），
用指标沙箱重算，取指定 plot 线的最新值（cross_* 用最近两根）与阈值比较；
命中后刷新 last_fired_at 作为去重依据，触发列表交由 lifespan 协程经统一
通知服务投递。本模块全部为同步函数（供 `asyncio.to_thread` 调用），
不直接依赖通知服务，便于单独测试。
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from indicators.executor import IndicatorExecutor
from indicators.models import CustomIndicator, IndicatorAlertRule
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

OPS = ("gt", "lt", "cross_up", "cross_down")
OP_DESC = {"gt": "高于", "lt": "低于", "cross_up": "上穿", "cross_down": "下穿"}

# 每次评估拉取的K线条数：覆盖常规 rolling 窗口即可，不追求长历史
DEFAULT_EVAL_BARS = 200


def utc_now() -> datetime:
    """DB 列为 UTC naive（SQLite func.now() 即 UTC），代码侧统一对齐。"""
    return datetime.now(UTC).replace(tzinfo=None)


def check_condition(values: list[float], op: str, threshold: float) -> bool:
    """判定 plot 值序列是否命中条件。

    values 必须按时间升序（values[-1] 为最新一根）；None/NaN 已在
    extract_plot_values 中剔除。cross_* 需要"前一根不满足、最新一根满足"，
    天然要求至少两根数据，不足时视为未触发。
    """
    if not op or len(values) == 0:
        return False
    latest = values[-1]
    if op == "gt":
        return latest > threshold
    if op == "lt":
        return latest < threshold
    if op in ("cross_up", "cross_down"):
        if len(values) < 2:
            return False
        prev = values[-2]
        if op == "cross_up":
            return prev <= threshold < latest
        return prev >= threshold > latest
    return False


def extract_plot_values(exec_result: dict[str, Any], plot_name: str) -> list[float] | None:
    """从指标执行结果中取出指定 plot 的数值序列（升序，剔除 None/NaN/Inf）。

    plot_name 为空时回落到第一个 plot；字符串 label 之类的非数值一律剔除。
    找不到任何可用 plot 返回 None。
    """
    plots = exec_result.get("plots") or []
    target = next(
        (p for p in plots if isinstance(p, dict) and p.get("name") == plot_name),
        None,
    )
    if target is None:
        target = next((p for p in plots if isinstance(p, dict) and p.get("data")), None)
    if target is None:
        return None
    values: list[float] = []
    for item in target.get("data") or []:
        if isinstance(item, int | float) and item == item and abs(item) != float("inf"):
            values.append(float(item))
    return values or None


def fetch_kline_bars(rule: dict[str, Any]) -> list[dict[str, Any]]:
    """拉取评估所需的K线（collector 现有链路，缺数自动向交易所回补）。"""
    # 函数内 import：collector.data_service 依赖重（K线工厂/ccxt 注册表），
    # 仅评估线程需要，避免拖慢应用启动
    from collector.services.data_service import DataService

    with get_db_session() as db:
        service = DataService(db)
        result = service.get_kline_data(
            symbol=rule["symbol"],
            interval=rule["period"],
            market_type=rule.get("market_type") or "crypto",
            crypto_type=rule.get("crypto_type") or "spot",
            limit=DEFAULT_EVAL_BARS,
            order="desc",
        )
    if not result.get("success"):
        logger.warning(f"提醒评估拉取K线失败: {rule['symbol']} {rule['period']}: {result.get('message')}")
        return []
    bars = result.get("kline_data") or []
    # kline 工厂多数路径返回升序，这里强排序一次，保证「最后两根为最新」语义
    bars.sort(key=lambda b: b.get("timestamp") or 0)
    return bars


async def execute_indicator(
    executor: IndicatorExecutor, code: str, bars: list[dict[str, Any]], params: dict[str, Any]
) -> dict[str, Any]:
    """在当前事件循环里跑指标沙箱（lifespan 协程内 await 调用）。"""
    return await executor.execute(code=code, kline_data=bars, params=params)


def build_alert_texts(rule: dict[str, Any], evaluation: dict[str, Any]) -> tuple[str, str]:
    """组装通知标题与正文。"""
    title = f"指标信号提醒: {rule.get('name') or rule['plot_name'] or '指标'}"
    detail = (
        f"{rule['symbol']} {rule['period']} | {rule['plot_name'] or '默认plot'} "
        f"{OP_DESC.get(rule['op'], rule['op'])} {rule['threshold']}"
    )
    value = evaluation.get("value")
    value_text = f"{value:g}" if isinstance(value, int | float) else "-"
    if evaluation.get("triggered"):
        message = f"{detail}，当前值 {value_text}，条件已触发。"
    else:
        message = f"{detail}，当前值 {value_text}（测试发送）。"
    return title, message


def _rule_snapshot(row: IndicatorAlertRule) -> dict[str, Any]:
    """规则行转 dict 快照（脱离 session 使用）。"""
    return {
        "id": row.id,
        "indicator_id": row.indicator_id,
        "name": row.name or "",
        "symbol": row.symbol,
        "period": row.period,
        "market_type": row.market_type,
        "crypto_type": row.crypto_type,
        "params": json.loads(row.params) if row.params else {},
        "plot_name": row.plot_name or "",
        "op": row.op,
        "threshold": float(row.threshold) if row.threshold is not None else 0.0,
        "channels": json.loads(row.channels) if row.channels else ["websocket"],
        "frequency": row.frequency or 30,
        "last_fired_at": row.last_fired_at,
    }


def load_due_rules(now: datetime | None = None) -> list[dict[str, Any]]:
    """加载启且已过去重窗口的规则（dict 快照列表）。"""
    now = now or utc_now()
    with get_db_session() as db:
        rows = db.scalars(select(IndicatorAlertRule).where(IndicatorAlertRule.enabled.is_(True))).all()
        due: list[dict[str, Any]] = []
        for row in rows:
            fired_at = row.last_fired_at
            if fired_at is not None and now - fired_at < timedelta(minutes=row.frequency or 30):
                continue
            due.append(_rule_snapshot(row))
        return due


def load_indicator_codes() -> dict[int, str]:
    """一次性装载全部自定义指标的代码（指标数量级小，不必按 id 逐条查）。"""
    with get_db_session() as db:
        rows = db.execute(select(CustomIndicator.id, CustomIndicator.code)).all()
        return {row[0]: row[1] for row in rows}


async def evaluate_rule(
    rule: dict[str, Any],
    code: str,
    executor: IndicatorExecutor,
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    """评估单条规则：跑指标 → 取 plot 值 → 条件判定。

    协程函数：有事件循环的调用方（test 路由）直接 await；
    无循环的评估线程由 run_evaluation_round 包 asyncio.run。
    """
    if not bars:
        return {"triggered": False, "error": "无K线数据"}
    try:
        result = await executor.execute(code=code, kline_data=bars, params=rule.get("params") or {})
    except Exception as e:  # 沙箱执行失败不应中断整轮评估
        return {"triggered": False, "error": f"指标执行异常: {e}"}
    if not result.get("success"):
        return {"triggered": False, "error": result.get("error") or "指标执行失败"}

    values = extract_plot_values(result, rule.get("plot_name") or "")
    if values is None or len(values) < 2:
        return {"triggered": False, "error": "plot 数据不足（有效值少于2个）"}

    triggered = check_condition(values, rule["op"], float(rule.get("threshold") or 0.0))
    result_info: dict[str, Any] = {"triggered": triggered, "value": values[-1]}
    if triggered:
        result_info["message"] = (
            f"plot「{rule['plot_name'] or '默认'}」最新值 {values[-1]:g} "
            f"{OP_DESC.get(rule['op'], rule['op'])} {rule['threshold']}"
        )
    return result_info


def mark_fired(rule_id: int, fired_at: datetime) -> None:
    """触发后写入 last_fired_at（去重窗口起点）。"""
    with get_db_session() as db:
        row = db.get(IndicatorAlertRule, rule_id)
        if row is not None:
            row.last_fired_at = fired_at
            db.commit()


# ponytail: 每轮全量重算启用规则（本地规模 <100 条，60s 一轮足够）；
# 规模上来后再按 symbol 缓存K线或改事件驱动
def run_evaluation_round(
    executor: IndicatorExecutor | None = None,
    fetch_kline=None,
) -> list[dict[str, Any]]:
    """同步评估一轮全部到期规则，返回触发列表。

    Args:
        executor: 指标沙箱执行器，测试可注入
        fetch_kline: K线拉取函数，测试可注入

    Returns:
        触发列表，每项含 rule 快照与 evaluation 结果；调用方负责投递通知。
        last_fired_at 在本函数内刷新，保证去重窗口由评估入口统一控制。
    """
    if executor is None:
        executor = IndicatorExecutor(timeout=10.0)
    if fetch_kline is None:
        fetch_kline = fetch_kline_bars

    now = utc_now()
    try:
        due = load_due_rules(now)
    except Exception as e:
        logger.error(f"加载提醒规则失败: {e}")
        return []
    if not due:
        return []

    try:
        codes = load_indicator_codes()
    except Exception as e:
        logger.error(f"加载指标代码失败: {e}")
        return []

    triggers: list[dict[str, Any]] = []
    for rule in due:
        code = codes.get(rule["indicator_id"])
        if not code:
            logger.warning(f"提醒规则指向的指标不存在，跳过: rule_id={rule['id']} indicator_id={rule['indicator_id']}")
            continue
        try:
            bars = fetch_kline(rule)
            # 评估线程（to_thread）内没有运行中的 loop，asyncio.run 安全
            evaluation = asyncio.run(evaluate_rule(rule, code, executor, bars))
        except Exception as e:
            logger.warning(f"提醒规则评估异常: rule_id={rule['id']}, error={e}")
            continue
        if not evaluation.get("triggered"):
            continue
        mark_fired(rule["id"], now)
        title, message = build_alert_texts(rule, evaluation)
        triggers.append(
            {
                "rule": rule,
                "evaluation": evaluation,
                "title": title,
                "message": message,
            }
        )
        logger.info(f"指标提醒触发: rule_id={rule['id']} {title}")
    return triggers
