"""
定时任务调度器模块

提供定时任务调度功能
"""

import os
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services.retrain_policy import AUTO_RETRAIN_ENV, env_flag
from services.symbol_sync import symbol_sync_manager
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

#: 进程内「上次运行」记录：job_id -> {ts_iso, ok, detail, ...}。
#: 只读端点 /agent/loop-status 消费；重启即清空（不持久化，进度条会变空但不会撒谎）。
LAST_RUNS: dict[str, dict] = {}
#: 本进程实际挂上的定时 job id（`/agent/loop-status` 判断 mounted）。
MOUNTED_JOBS: set[str] = set()


def _record_run(job_id: str, ok: bool, detail: str = "", **extra) -> None:
    """记一次 job 运行结果（纯内存，失败也记）。"""
    LAST_RUNS[job_id] = {
        "ts_iso": datetime.now(UTC).isoformat(),
        "ok": ok,
        "detail": detail,
    } | extra


def get_last_runs() -> dict[str, dict]:
    """LAST_RUNS 的浅拷贝（调用方不得改动调度器内部状态）。"""
    return dict(LAST_RUNS)


def run_auto_retrain_job() -> dict[str, Any] | None:
    """每日自动重训闭环 job 体（模块级，便于单测直接调）。

    job 级 try/except：选目 / 训练 / 对照任何一步炸掉都只记日志，绝不让异常
    冒泡到 APScheduler（否则该 job 后续触发会被框架按失败策略处理）。
    """
    try:
        from rl.lifecycle import run_auto_retrain_cycle

        summary = run_auto_retrain_cycle()
        families = [(r.get("family"), r.get("status")) for r in summary.get("results") or []]
        logger.info(
            "RL 自动重训闭环完成: candidates=%s results=%s",
            len(summary.get("candidates") or []),
            families,
        )
        _record_run(
            "rl_auto_retrain",
            True,
            detail=f"candidates={len(summary.get('candidates') or [])} families={families}",
        )
        return summary
    except Exception as e:
        logger.exception("RL 自动重训闭环失败")
        _record_run("rl_auto_retrain", False, error=str(e)[:300])
        return None


def run_agent_dream_job() -> bool:
    """每日记忆自迭代（Dream）job 体（模块级，便于单测/手动直调）。

    Dream 是 Agent 的自我修改记忆机制：消费 Consolidator 归档到
    history.jsonl 的条目，两阶段 LLM（分析 → 编辑）改写 MEMORY.md。
    无新条目直接 no-op；Phase1 输出 [SKIP] 时不触碰 MEMORY.md——
    最坏情况就是一次 LLM 调用的成本，不会写坏记忆。
    总闸 QUANTCELL_AGENT_DREAM 与重训双闸同款默认关；调度线程内没有
    事件循环，用 get_agent() 单例 + asyncio.run 驱动。
    """
    import asyncio
    import time

    from agent.core.factory import get_agent

    started = time.monotonic()
    try:
        dream = get_agent().dream
        updated = asyncio.run(dream.run())
    except Exception as e:
        logger.exception("Agent Dream 记忆整理失败")
        _record_run("agent_dream", False, error=str(e)[:300])
        raise
    elapsed = time.monotonic() - started
    logger.info(f"Agent Dream 记忆整理完成: updated={updated}")
    # ponytail: 消费条数在 Dream.run 内部，骨架拿不到就不编造（只报 updated/耗时）。
    detail = f"updated={updated} elapsed={elapsed:.1f}s" if updated else "noop: 无未处理历史"
    _record_run("agent_dream", True, detail=detail)
    return updated


def start_scheduler(
    proxy_enabled: bool = False,
    proxy_url: str = "",
    proxy_username: str = "",
    proxy_password: str = "",
):
    """启动定时任务调度器

    Args:
        proxy_enabled: 是否启用代理
        proxy_url: 代理地址
        proxy_username: 代理用户名
        proxy_password: 代理密码

    Returns:
        BackgroundScheduler: 后台调度器实例
    """
    # 创建后台调度器
    scheduler = BackgroundScheduler()
    # 重复调用 start_scheduler（测试/热重启）时以本次挂载为准
    MOUNTED_JOBS.clear()

    # 添加定时任务：每周日凌晨2点执行一次，同步加密货币对
    # 使用同步管理器执行，确保与主动同步的协调
    def scheduled_sync():
        """定时同步任务包装器"""
        # 检查是否正在主动同步
        if symbol_sync_manager.is_syncing:
            logger.info("主动同步正在进行中，跳过本次定时同步")
            return

        # 执行同步
        result = symbol_sync_manager.perform_sync(exchange="binance")
        if result.get("success"):
            logger.info(f"定时同步成功: {result.get('message')}")
        else:
            logger.error(f"定时同步失败: {result.get('message')}")

    scheduler.add_job(
        func=scheduled_sync,
        trigger=CronTrigger(day_of_week=6, hour=2, minute=0),  # 每周日凌晨2点
        id="sync_crypto_symbols",
        name="Sync cryptocurrency symbols",
        replace_existing=True,
    )

    # 每日 OOS 门槛审计:只读模型旁车,把"连续 N 轮 OOS 不达标"的模型族
    # 记进日志(promote 端点本身已同步拦截)。不触发训练——训练侧仍归
    # rl.lifecycle 的 run_loop。导入放函数内,避免调度器启动时拉起 RL 依赖。
    def scheduled_rl_oos_audit():
        try:
            from rl.lifecycle import audit_recent_oos

            audit_recent_oos()
        except Exception as e:
            logger.exception("OOS 门槛周期审计失败")
            _record_run("rl_oos_gate_audit", False, error=str(e)[:300])
            return
        _record_run("rl_oos_gate_audit", True)

    scheduler.add_job(
        func=scheduled_rl_oos_audit,
        trigger=CronTrigger(hour=3, minute=30),
        id="rl_oos_gate_audit",
        name="RL OOS gate audit",
        replace_existing=True,
    )
    MOUNTED_JOBS.add("rl_oos_gate_audit")

    # 每日复盘（P4-4）：聚合昨日 worker 盈亏/持仓异常/决策数/模型 OOS 状态，
    # 作为一条 assistant 消息注入 /agent 默认会话（不伪装成用户输入）。
    # LLM 摘要 opt-in：默认关（QUANTCELL_DAILY_REVIEW_LLM=1 开启），
    # 启用但不可用时回落模板文本并在 meta.degraded 标注。导入放函数内与上面 OOS 一致。
    def scheduled_daily_review():
        use_llm = os.environ.get("QUANTCELL_DAILY_REVIEW_LLM", "0").strip().lower() in ("1", "true", "yes")
        try:
            from agent.core.daily_review import build_report, publish

            report = build_report(use_llm=use_llm)
            publish(report)
        except Exception as e:
            logger.exception("每日复盘生成失败")
            _record_run("agent_daily_review", False, error=str(e)[:300])
            return
        _record_run("agent_daily_review", True, detail=f"use_llm={use_llm}")

    scheduler.add_job(
        func=scheduled_daily_review,
        trigger=CronTrigger(hour=3, minute=35),  # 排在 OOS 审计之后，复用当日审计结果
        id="agent_daily_review",
        name="Agent daily review",
        replace_existing=True,
    )
    MOUNTED_JOBS.add("agent_daily_review")

    # 每日自动重训闭环（P4-3）：选目（retrain_policy）→ 重训 → shadow 纸面对照
    # → 「晋升待审」记录（AUTO_PROMOTE=1 才自动 promote）。
    # 顺序理由：排在 03:30 OOS 审计之后（复用当天的新鲜旁车/审计结论）；
    # 排在 03:35 每日复盘之后 —— 重训是长任务（跑满全局训练锁），不与复盘争资源，
    # 复盘当天看到的仍是「重训前」快照，不会出现「报告说已换模型、训练还没跑完」。
    # 总闸默认关：QUANTCELL_AUTO_RETRAIN 未开启时干脆不挂 job（函数本身仍可直调）。
    if env_flag(AUTO_RETRAIN_ENV):
        scheduler.add_job(
            func=run_auto_retrain_job,
            trigger=CronTrigger(hour=3, minute=40),
            id="rl_auto_retrain",
            name="RL auto retrain (closed loop)",
            replace_existing=True,
        )
        MOUNTED_JOBS.add("rl_auto_retrain")
        logger.info("自动重训闭环已挂载（每日 03:40）")
    else:
        logger.info(f"自动重训闭环未启用（{AUTO_RETRAIN_ENV} != 1）")

    # 每日记忆自迭代（Dream）：两阶段 LLM 编辑 MEMORY.md（历史 → 事实 → 自改写）。
    # 排在 04:00 —— 复盘（03:35）与重训（03:40）之后；Dream 只调 LLM、不碰训练锁，
    # 与重训并行安全。总闸默认关：QUANTCELL_AGENT_DREAM 未开启时干脆不挂
    # job（函数本身仍可直调：手动触发 / 单测）。
    if env_flag("QUANTCELL_AGENT_DREAM"):
        scheduler.add_job(
            func=run_agent_dream_job,
            trigger=CronTrigger(hour=4, minute=0),
            id="agent_dream",
            name="Agent dream (memory self-edit)",
            replace_existing=True,
        )
        MOUNTED_JOBS.add("agent_dream")
        logger.info("Agent Dream 记忆自迭代已挂载（每日 04:00）")
    else:
        logger.info("Agent Dream 记忆自迭代未启用（QUANTCELL_AGENT_DREAM 未开启）")

    # 启动调度器
    scheduler.start()
    logger.info("定时任务调度器已启动，货币对同步任务将在每周日凌晨2点执行")
    return scheduler
