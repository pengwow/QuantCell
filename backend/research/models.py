"""研究会话 / 试验 / 知识三张表（PRD §7）。

约定与现有 factor 表一致：JSON 字段统一用 Text 存字符串，由 service 负责序列化。
为避免 research_sessions ↔ research_trials 的循环外键（best_trial_id 指回 trials），
只有 session_id 建真实外键；parent_trial_id / replay_of_id / best_trial_id 用普通
整数列（SQLite 下也不强约束），语义由 service 保证。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from collector.db.database import Base


class ResearchSession(Base):
    """研究会话：一次 quick 或 deep 运行。"""

    __tablename__ = "research_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # 场景：factor / model / strategy（P0 只有 factor 有实现）
    scenario: Mapped[str] = mapped_column(String(12), nullable=False, default="factor")
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="deep")
    n_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 后端统一任务管理器中的 job_id，便于恢复进度与事件流
    backend_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 会话配置快照：数据窗口、轮次、预算、硬门阈值等
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    best_trial_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loop_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_research_sessions_owner_created", "owner_id", "created_at"),
        Index("ix_research_sessions_status", "status"),
        Index("ix_research_sessions_mode", "mode"),
        Index("ix_research_sessions_scenario", "scenario"),
    )


class ResearchTrial(Base):
    """单条候选试验：quick 一轮落 N 条，deep 每轮落 1 条。"""

    __tablename__ = "research_trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("research_sessions.id"), nullable=False)
    loop_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    candidate_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    # interrupted 时记录中断前所处的 step 状态，恢复时据此接续
    resume_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 假设的理由/预测（PRD §7.2 hypothesis_json 的拆列存法）
    hypothesis_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis_prediction: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 样本外原始评估结构（PRD §7.2 metrics_oos_json）
    metrics_oos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    oos_flag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    oos_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 自修复内环的每轮摘要（{round, kind, error} 列表），只存截断后的错误摘要
    repair_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 硬门 3 的实测相关性（评估完成即落库，续跑 judge 直接复用，不依赖重算）
    corr_sota: Mapped[float | None] = mapped_column(Float, nullable=True)
    corr_library: Mapped[float | None] = mapped_column(Float, nullable=True)
    promoted_factor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # quick 轮关联到 factor_mining_runs.id（Integer，与既有表主键对齐）
    quick_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parent_trial_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replay_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 回放元数据：{partial, missing, notes, tolerance, diff, consistent, unreproducible}
    replay_meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 复现所需：模型名 / prompt 指纹 / 温度 / 执行耗时
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exception: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # 唯一约束保证续跑不会为同一 (session, loop, candidate) 重复落 trial
        Index(
            "ix_research_trials_session_loop",
            "session_id",
            "loop_idx",
            "candidate_idx",
            unique=True,
        ),
        Index("ix_research_trials_status", "status"),
    )


class ResearchKnowledge(Base):
    """失败签名与经验库（P0 仅落表，P1 才做连续失败短路）。"""

    __tablename__ = "research_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trial_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="failure")
    signature: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_research_knowledge_signature", "signature"),
        Index("ix_research_knowledge_owner_kind", "owner_id", "kind"),
    )


class ResearchEvent(Base):
    """会话过程事件（持久化，多 worker 下同样可见）。

    顺序语义（P2 决策：明确降级为“最终一致”，不做会话级锁/独立 seq 分配）：
    - seq 直接复用自增主键，代表“写库顺序”，不是“事件发生顺序”；
    - 正常情况下同一会话只有一个 runner 线程在写（resume 前的 _ensure_no_active_job
      + 进程内 Control 约束），单会话内 seq 与发生顺序一致；
    - 多 backend 进程同时操作同一会话属于异常场景（job_manager 是进程内的，跨进程
      看不到对方的 job），此时 seq 仍是全序，但可能与 wall-clock ts 出现毫秒级倒挂；
      前端按 seq 增量拉取/排序即可得到稳定的最终一致视图，ts 只作参考；
    - 不用“DB 侧 max(seq)+1”或“会话级锁”：两者都只能保证写入时刻有序，
      SQLite 下还会把同一会话的所有写串行化，收益不足以抵消复杂度。

    其余局限：每个会话只保留最近 EVENTS_RETENTION 条（append 时裁剪），不做全量归档；
    若未来迁移到消息队列/流式存储，应以本表为迁移起点而非进程内缓冲。
    """

    __tablename__ = "research_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("research_sessions.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="info")
    stage: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    msg: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 事件时间用 epoch 秒，避免 DB server_default=now() 的时区歧义
    ts: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_research_events_session_id", "session_id", "id"),)
