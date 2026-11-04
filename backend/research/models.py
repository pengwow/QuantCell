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
