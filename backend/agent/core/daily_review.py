"""AgentLoop 每日复盘报告 v1（设计文档 P4-4）。

一条流水线：聚合（活跃 worker × overview/positions/orders + 决策录制 + 模型 OOS 门槛）
→ 结构化 ``sections`` → 模板文本（默认）/ 可选 LLM 自然语言摘要。

口径（改动前先读）
------------------
- **不是 agent 工具调用**：``agent_tool_audit`` 由 ``tools/registry.execute`` 写，记录的是
  LLM 发起的工具调用；复盘是系统自产报告，不伪装成工具调用，只在应用日志留痕。
- **不是 LLM 派生决策**：不进 ``decision_replay``。LLM 只负责「把已经算好的数字译成人话」，
  数据本身全部来自确定性查询，因此复盘不参与回测可回放约束。
- **红线：不静默假成功**。LLM 未启用 → ``mode="template"``；启用了但不可用/报错/返回空
  → 回落模板文本且 ``meta.degraded=True`` + ``meta.llm.error``，绝不留空摘要。
- **注入聊天流不伪装成用户输入**：``publish`` 以 ``role="assistant"`` 追加一条会话消息，
  附 ``meta.kind="daily_review"`` 供前端识别（``to_axon_messages`` 只取 role/content，
  meta 不会进 LLM 请求体）。

数据来源（每节）
----------------
- overview / workers 盈亏成交：``worker.crud.get_trading_summary``（SQL 聚合 worker_trades）
- workers 订单：``worker.crud.get_worker_orders_paginated``（worker_orders 按日窗口）
- workers 持仓：``worker.service.get_positions_sync``（worker_positions OPEN，
  空表回退未配对成交推导 —— 与该端点既有口径一致）
- decisions：``strategy.decision_recording.worker_replay_path`` +
  ``list_decisions_from_file``（按 ``_ts`` 前缀过滤当日）
- models / oos_gate：``services.oos_gate.audit_oos_gate``（读 data/models/*.meta.json 旁车）
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 复盘消息落到哪个会话：/agent 聊天流的默认会话
REVIEW_SESSION_KEY = "default"

# 「活跃」定义：非 stopped/error 的运行态（paused 仍持有仓位，必须纳入异常检查）
ACTIVE_WORKER_STATUSES = ("running", "paused", "starting")

# 异常持仓阈值（模块常量，不引配置系统）
POSITION_LOSS_ALERT_PCT = -5.0  # 浮动亏损百分比不高于此值 → 高浮亏
POSITION_CONCENTRATION_ALERT_PCT = 50.0  # 单仓名义价值占该 worker 持仓总值的比例
ORDER_SCAN_LIMIT = 200  # 每 worker 当日订单扫描上限（只用于状态计数）
DECISION_TAIL_ROWS = 5000  # 决策录制只读尾部 N 条（单日复盘足够）
SAME_DAY_SCAN_MESSAGES = 50  # 幂等检查扫描的会话尾部消息数

_LLM_MAX_TOKENS = 512
_LLM_PROMPT_HEAD = (
    "你是量化交易的复盘助手。下面是一次每日复盘的结构化数据（JSON）。"
    "请用 200-300 字中文写一段自然语言复盘：先讲总体盈亏与成交，"
    "再点出异常持仓/集中度风险，最后说明模型与 OOS 晋升门槛状态。"
    "只使用数据里出现过的数字，不要编造。直接输出复盘正文，不加标题。\n\n"
)


# ---------- 时间窗口 ----------


def day_window(day: date) -> tuple[datetime, datetime]:
    """[当日 00:00, 次日 00:00) 的 naive datetime 窗口（库列为 naive UTC-agnostic）。"""
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def parse_review_date(value: str | None) -> date:
    """``YYYY-MM-DD`` → date；缺省为昨天（每日复盘默认看上一交易日）。"""
    if value is None or not str(value).strip():
        return date.today() - timedelta(days=1)
    raw = str(value).strip()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        msg = f"date 需为 YYYY-MM-DD: {value!r}"
        raise ValueError(msg) from exc


# ---------- 数据聚合 ----------


def _worker_positions(worker_id: int) -> list[dict[str, Any]]:
    from worker.service import get_positions_sync

    return list(get_positions_sync(worker_id).get("items") or [])


def _day_decisions(worker_id: int, day: date) -> dict[str, Any]:
    """当日决策录制统计：按 ``_ts``（ISO8601 纳秒 UTC）日期前缀过滤。"""
    from strategy.decision_recording import list_decisions_from_file, worker_replay_path

    rows = list_decisions_from_file(worker_replay_path(worker_id), max_rows=DECISION_TAIL_ROWS)
    prefix = day.isoformat()
    todays = [r for r in rows if str(r.get("_ts") or "").startswith(prefix)]
    return {
        "count": len(todays),
        "by_action": dict(Counter(str(r.get("action") or "unknown") for r in todays)),
    }


def _models_dir() -> Path:
    from services.rl_service import MODELS_DIR

    return Path(MODELS_DIR)


def _model_status() -> dict[str, Any]:
    """模型族 OOS 晋升门槛判定（只读旁车，与 promote 端点/周期审计同一实现）。"""
    try:
        from services.oos_gate import audit_oos_gate

        results = audit_oos_gate(_models_dir())
    except Exception as e:  # 旁车缺失/损坏不该让复盘整体失败
        logger.warning(f"[daily_review] 模型 OOS 状态读取失败: {e}")
        return {"families": 0, "blocked": [], "latest_rounds": [], "error": str(e)}

    blocked = [
        {"family": r.get("family"), "model_id": r.get("model_id"), "reason": r.get("reason")}
        for r in results
        if r.get("blocked")
    ]
    latest_rounds = []
    for r in results:
        rounds = r.get("rounds") or []
        top = rounds[0] if rounds else {}
        latest_rounds.append(
            {
                "family": r.get("family"),
                "model_id": top.get("model_id") or r.get("model_id"),
                "sharpe_ratio": top.get("sharpe_ratio"),
                "total_return_pct": top.get("total_return_pct"),
                "created_at": top.get("created_at") or None,
                "blocked": bool(r.get("blocked")),
            }
        )
    return {"families": len(results), "blocked": blocked, "latest_rounds": latest_rounds}


def _position_anomalies(worker: dict[str, Any], positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """单 worker 持仓异常：高浮亏 + 高集中度（占本 worker 持仓总名义价值）。"""
    book_value = sum(
        abs(float(p.get("quantity") or 0) * float(p.get("current_price") or p.get("entry_price") or 0))
        for p in positions
    )
    anomalies: list[dict[str, Any]] = []
    for p in positions:
        quantity = float(p.get("quantity") or 0)
        price = float(p.get("current_price") or p.get("entry_price") or 0)
        value = abs(quantity * price)
        pnl_pct = float(p.get("unrealized_pnl_pct") or 0.0)
        base = {
            "worker_id": worker["worker_id"],
            "worker_name": worker["name"],
            "symbol": p.get("symbol"),
            "position_side": p.get("position_side") or p.get("side"),
            "quantity": quantity,
            "unrealized_pnl": p.get("unrealized_pnl"),
            "unrealized_pnl_pct": round(pnl_pct, 2),
        }
        if pnl_pct <= POSITION_LOSS_ALERT_PCT:
            anomalies.append({"type": "position_loss", "detail": f"{p.get('symbol')} 浮动亏损 {pnl_pct:.2f}%", **base})
        if book_value > 0 and value / book_value * 100 >= POSITION_CONCENTRATION_ALERT_PCT:
            share = value / book_value * 100
            anomalies.append(
                {
                    "type": "position_concentration",
                    "detail": f"{p.get('symbol')} 占本 worker 持仓名义价值 {share:.1f}%",
                    "share_pct": round(share, 2),
                    **base,
                }
            )
    return anomalies


def collect_sections(day: date) -> dict[str, Any]:
    """聚合当日复盘的全部数据源，返回可直接渲染/序列化的 sections。"""
    from utils.db_session import get_db_session
    from worker import crud, models

    start, end = day_window(day)
    workers: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    totals = {"total_pnl": 0.0, "total_trades": 0, "winning_trades": 0, "orders": 0, "decisions": 0}

    with get_db_session() as db:
        rows = (
            db.query(models.Worker)
            .filter(models.Worker.status.in_(ACTIVE_WORKER_STATUSES))
            .order_by(models.Worker.id)
            .all()
        )
        for w in rows:
            summary = crud.get_trading_summary(db, w.id, start, end)
            orders, order_total = crud.get_worker_orders_paginated(
                db, w.id, start_time=start, end_time=end, limit=ORDER_SCAN_LIMIT
            )
            workers.append(
                {
                    "worker_id": w.id,
                    "name": w.name,
                    "status": w.status,
                    "strategy_type": w.strategy_type,
                    "pnl": summary.get("total_pnl", 0.0),
                    "trades": summary.get("total_trades", 0),
                    "win_rate": summary.get("win_rate", 0.0),
                    "orders": order_total,
                    "order_status": dict(Counter(o.status for o in orders)),
                }
            )
            totals["total_pnl"] += float(summary.get("total_pnl") or 0.0)
            totals["total_trades"] += int(summary.get("total_trades") or 0)
            totals["winning_trades"] += int(summary.get("winning_trades") or 0)
            totals["orders"] += int(order_total or 0)

    # 持仓/决策读各自的数据源（独立会话/文件），保持既有查询函数不动
    for worker in workers:
        positions = _worker_positions(worker["worker_id"])
        worker["positions"] = positions
        worker["decisions"] = _day_decisions(worker["worker_id"], day)
        totals["decisions"] += worker["decisions"]["count"]
        anomalies.extend(_position_anomalies(worker, positions))

    total_trades = totals["total_trades"]
    overview = {
        "date": day.isoformat(),
        "active_workers": len(workers),
        "total_pnl": round(totals["total_pnl"], 2),
        "total_trades": total_trades,
        "win_rate": round(totals["winning_trades"] / total_trades * 100, 2) if total_trades else 0.0,
        "orders": totals["orders"],
        "decisions": totals["decisions"],
        "anomaly_count": len(anomalies),
    }

    return {
        "overview": overview,
        "workers": workers,
        "anomalies": anomalies,
        "models": _model_status(),
    }


# ---------- 模板文本 ----------


def render_template_text(sections: dict[str, Any]) -> str:
    """纯数据拼装的自然语言复盘（LLM 不可用时的兜底，也便于测试断言）。"""
    o = sections["overview"]
    lines = [
        f"每日复盘 {o['date']}：活跃 worker {o['active_workers']} 个。",
        f"当日已实现盈亏 {o['total_pnl']:.2f}，成交 {o['total_trades']} 笔，胜率 {o['win_rate']:.2f}%，"
        f"订单 {o['orders']} 笔，决策录制 {o['decisions']} 条。",
    ]

    if o["anomaly_count"]:
        lines.append(f"持仓异常 {o['anomaly_count']} 项：")
        lines.extend(f"- {a['detail']}" for a in sections["anomalies"])
    else:
        lines.append("持仓异常 0 项，未见高浮亏或高集中度仓位。")

    models = sections["models"]
    if models.get("error"):
        lines.append(f"模型状态读取失败：{models['error']}")
    elif not models["families"]:
        lines.append("未发现训练产物旁车，OOS 门槛无记录。")
    else:
        blocked = models["blocked"]
        if blocked:
            lines.append(f"模型族 {models['families']} 个，其中 {len(blocked)} 个被 OOS 门槛拦停：")
            lines.extend(f"- {b['reason']}" for b in blocked)
        else:
            lines.append(f"模型族 {models['families']} 个，OOS 门槛全部放行。")

    return "\n".join(lines)


# ---------- LLM 增强（可选，失败降级） ----------


def _build_llm_prompt(sections: dict[str, Any]) -> str:
    return _LLM_PROMPT_HEAD + json.dumps(sections, ensure_ascii=False, default=str)


def _default_llm() -> tuple[Callable[[str], str] | None, str | None]:
    """按 agent 既有 provider 配置构造一次性摘要器；不可用返回 (None, None)。

    ponytail: 用 asyncio.run 调 axon 后端 —— 所有调用方（FastAPI 端点经
    asyncio.to_thread、调度器后台线程）都在无事件循环的线程里，直接复用它比另造
    同步 HTTP 客户端少一层依赖；若将来有 async 调用方再补 async 版本。
    """
    try:
        from agent.core.factory import get_ai_config

        cfg = get_ai_config()
    except Exception as e:
        logger.warning(f"[daily_review] 读取 AI 配置失败: {e}")
        return None, None
    if not cfg:
        return None, None

    provider = cfg.get("provider") or {}
    api_key = provider.get("api_key") or ""
    base_url = provider.get("api_host") or ""
    if not api_key and not base_url:
        return None, None

    model = (cfg.get("enabled_model") or {}).get("name") or os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
    try:
        import asyncio

        from axon_bridge.llm import chat_to_dict, create_llm_backend

        backend = create_llm_backend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.2,
            max_tokens=_LLM_MAX_TOKENS,
        )
    except Exception as e:
        logger.warning(f"[daily_review] 构造 LLM 后端失败: {e}")
        return None, model

    def summarize(prompt: str) -> str:
        response = asyncio.run(chat_to_dict(backend, [{"role": "user", "content": prompt}]))
        return (response.get("content") or "").strip()

    return summarize, model


def build_report(
    day: date | None = None,
    *,
    use_llm: bool = False,
    llm: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """生成复盘报告。``llm`` 显式传入时跳过 provider 探测（测试/离线注入用）。"""
    day = day or parse_review_date(None)
    sections = collect_sections(day)
    template_text = render_template_text(sections)

    meta: dict[str, Any] = {
        "mode": "template",
        "degraded": False,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "llm": {"enabled": bool(use_llm), "used": False, "model": None, "error": None},
    }
    summary_text = template_text

    if use_llm:
        summarizer, model = (llm, None) if llm is not None else _default_llm()
        meta["llm"]["model"] = model
        if summarizer is None:
            meta["mode"] = "template_fallback"
            meta["degraded"] = True
            meta["llm"]["error"] = "llm_unavailable"
        else:
            try:
                summary_text = summarizer(_build_llm_prompt(sections)).strip()
            except Exception as e:
                summary_text = ""
                meta["llm"]["error"] = f"{type(e).__name__}: {e}"
            if summary_text:
                meta["mode"] = "llm"
                meta["llm"]["used"] = True
            else:
                meta["mode"] = "template_fallback"
                meta["degraded"] = True
                meta["llm"]["error"] = meta["llm"]["error"] or "empty_response"
                summary_text = template_text
                logger.warning(f"[daily_review] LLM 摘要不可用，回落模板文本: {meta['llm']['error']}")

    return {
        "date": day.isoformat(),
        "sections": sections,
        "summary_text": summary_text,
        "template_text": template_text,
        "meta": meta,
    }


def get_daily_review(
    day: str | None = None, *, use_llm: bool = False, llm: Callable[[str], str] | None = None
) -> dict[str, Any]:
    """端点/调度共用入口：解析日期后生成报告。"""
    return build_report(parse_review_date(day), use_llm=use_llm, llm=llm)


# ---------- 注入 /agent 聊天流 ----------


def publish(report: dict[str, Any], session_key: str = REVIEW_SESSION_KEY) -> dict[str, Any]:
    """把复盘作为一条 assistant 消息写进会话（同一天幂等，不伪装成用户输入）。

    前端按 ``meta.kind == "daily_review"`` 识别并渲染结构化 ``meta.report``；
    LLM 请求体只取 role/content，meta 不会污染对话上下文。
    """
    from agent.core.factory import get_agent

    agent = get_agent()
    session = agent.sessions.get_or_create(session_key)
    for msg in reversed(session.messages[-SAME_DAY_SCAN_MESSAGES:]):
        meta = msg.get("meta") or {}
        if meta.get("kind") == "daily_review" and meta.get("date") == report["date"]:
            logger.info(f"[daily_review] {report['date']} 复盘已存在，跳过重复发布 (session={session_key})")
            return {"published": False, "reason": "duplicate", "session_id": session_key, "date": report["date"]}

    session.messages.append(
        {
            "role": "assistant",
            "content": report["summary_text"],
            "meta": {
                "kind": "daily_review",
                "date": report["date"],
                "degraded": report["meta"]["degraded"],
                "report": report,
            },
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )
    session.updated_at = datetime.now()
    agent.sessions.save(session)
    logger.info(
        f"[daily_review] 复盘已注入会话 {session_key}: date={report['date']} "
        f"mode={report['meta']['mode']} degraded={report['meta']['degraded']}"
    )
    return {"published": True, "session_id": session_key, "date": report["date"], "mode": report["meta"]["mode"]}
