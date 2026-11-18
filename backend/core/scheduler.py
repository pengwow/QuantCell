"""
定时任务调度器模块

提供定时任务调度功能
"""

import os
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services.retrain_policy import AUTO_RETRAIN_ENV, env_flag
from services.symbol_sync import symbol_sync_manager
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


def run_auto_retrain_job() -> dict[str, Any] | None:
    """每日自动重训闭环 job 体（模块级，便于单测直接调）。

    job 级 try/except：选目 / 训练 / 对照任何一步炸掉都只记日志，绝不让异常
    冒泡到 APScheduler（否则该 job 后续触发会被框架按失败策略处理）。
    """
    try:
        from rl.lifecycle import run_auto_retrain_cycle

        summary = run_auto_retrain_cycle()
        logger.info(
            "RL 自动重训闭环完成: candidates=%s results=%s",
            len(summary.get("candidates") or []),
            [(r.get("family"), r.get("status")) for r in summary.get("results") or []],
        )
        return summary
    except Exception:
        logger.exception("RL 自动重训闭环失败")
        return None


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
        except Exception:
            logger.exception("OOS 门槛周期审计失败")

    scheduler.add_job(
        func=scheduled_rl_oos_audit,
        trigger=CronTrigger(hour=3, minute=30),
        id="rl_oos_gate_audit",
        name="RL OOS gate audit",
        replace_existing=True,
    )

    # 每日复盘（P4-4）：聚合昨日 worker 盈亏/持仓异常/决策数/模型 OOS 状态，
    # 作为一条 assistant 消息注入 /agent 默认会话（不伪装成用户输入）。
    # LLM 摘要 opt-in：默认关（QUANTCELL_DAILY_REVIEW_LLM=1 开启），
    # 启用但不可用时回落模板文本并在 meta.degraded 标注。导入放函数内与上面 OOS 一致。
    def scheduled_daily_review():
        try:
            from agent.core.daily_review import build_report, publish

            use_llm = os.environ.get("QUANTCELL_DAILY_REVIEW_LLM", "0").strip().lower() in ("1", "true", "yes")
            report = build_report(use_llm=use_llm)
            publish(report)
        except Exception:
            logger.exception("每日复盘生成失败")

    scheduler.add_job(
        func=scheduled_daily_review,
        trigger=CronTrigger(hour=3, minute=35),  # 排在 OOS 审计之后，复用当日审计结果
        id="agent_daily_review",
        name="Agent daily review",
        replace_existing=True,
    )

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
        logger.info("自动重训闭环已挂载（每日 03:40）")
    else:
        logger.info(f"自动重训闭环未启用（{AUTO_RETRAIN_ENV} != 1）")

    # 启动调度器
    scheduler.start()
    logger.info("定时任务调度器已启动，货币对同步任务将在每周日凌晨2点执行")
    return scheduler
