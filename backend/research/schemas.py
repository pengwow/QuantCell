"""研究工作台请求/响应校验（PRD §8.1）。

所有未拍板默认值从 consts 取值，schema 层只负责范围与跨字段一致性校验。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from research import consts


class ResearchCreateReq(BaseModel):
    """新建研究会话。"""

    mode: Literal["quick", "deep"] = "deep"
    # 只接受 factor；其它值由路由显式返回 400（不用 Literal，避免退化成 422 且错误码不可控）
    scenario: str = Field(default="factor", min_length=1, max_length=12)
    name: str = Field(default="", max_length=64, description="会话名称，空则自动生成")
    symbols: list[str] = Field(..., min_length=1, max_length=consts.MAX_SYMBOLS)
    interval: str = Field(default="1h", min_length=1, description="K线周期，如 15m/1h/4h/1d")
    candle_type: Literal["spot", "future"] = "spot"
    start: str = Field(..., description="开始日期 YYYY-MM-DD")
    end: str = Field(..., description="结束日期 YYYY-MM-DD")

    n_candidates: int | None = Field(default=None, ge=1, le=10)
    loop_n: int | None = Field(default=None, ge=1, le=consts.MAX_LOOP_N)
    tasks_per_loop: int = Field(default=consts.DEFAULT_TASKS_PER_LOOP, ge=1, le=3)
    repair_rounds: int = Field(default=consts.DEFAULT_REPAIR_ROUNDS, ge=0, le=3)

    max_llm_calls: int | None = Field(default=None, ge=1, le=500)
    # 硬下限 = 单次调用预留额度：低于它连一次调用都发不出（不是创建期估算拦截，
    # 估算只作为 budget_hint 提示，见 service.session_to_dict）
    max_tokens: int | None = Field(default=None, ge=consts.EST_TOKENS_PER_CALL, le=2_000_000)
    # 单次 LLM 输出上限（reasoning 模型需要留足正文预算）；空则用 consts 默认值
    llm_max_tokens: int | None = Field(default=None, ge=1024, le=200_000, description="单次 LLM 输出 token 上限")
    # 阶段级单次调用超时（秒）：None 表示沿用全局/阶段默认；下限 30s 防止误配成“几乎必超时”
    llm_propose_timeout_secs: int | None = Field(default=None, ge=30, le=900, description="propose 阶段超时")
    llm_plan_timeout_secs: int | None = Field(default=None, ge=30, le=900, description="plan 阶段超时")
    llm_code_timeout_secs: int | None = Field(default=None, ge=30, le=900, description="code 阶段超时")
    llm_feedback_timeout_secs: int | None = Field(default=None, ge=30, le=900, description="feedback 阶段超时")
    icir_floor: float = Field(default=consts.DEFAULT_ICIR_FLOOR, ge=0.0, le=1.0)
    corr_threshold: float = Field(default=consts.DEFAULT_CORR_THRESHOLD, gt=0.0, le=1.0)

    seed_factor: str | None = Field(default=None, max_length=200)
    model_id: str | None = Field(default=None, description="AI 模型 ID，空则用默认模型")
    temperature: float | None = Field(default=None, ge=0.0, le=1.5)
    test_ratio: float = Field(default=consts.DEFAULT_TEST_RATIO, ge=0.0, le=0.8)
    wf_folds: int = Field(default=consts.DEFAULT_WF_FOLDS, ge=0, le=10)
    compose: bool = True

    @field_validator("symbols")
    @classmethod
    def _normalize_symbols(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for sym in value:
            sym = sym.strip().upper()
            if sym and sym not in cleaned:
                cleaned.append(sym)
        if len(cleaned) < 1:
            raise ValueError("symbols 不能为空")
        return cleaned

    @model_validator(mode="after")
    def _fill_mode_defaults(self) -> ResearchCreateReq:
        try:
            start_dt = datetime.fromisoformat(self.start)
            end_dt = datetime.fromisoformat(self.end)
        except ValueError as exc:
            raise ValueError("start/end 必须是 YYYY-MM-DD 日期") from exc
        if (end_dt - start_dt).days < consts.MIN_WINDOW_DAYS:
            raise ValueError(f"数据窗口至少 {consts.MIN_WINDOW_DAYS} 天")
        if self.candle_type == "future" and self.interval == "1m" and (end_dt - start_dt).days > 365:
            # P0 只做轻量边界检查，避免超大窗口把数据加载拖垮
            raise ValueError("future 1m 窗口不能超过 365 天")

        if self.mode == "quick":
            # quick 是单轮挖掘：轮次固定 1，候选数沿用现有挖掘默认
            if self.loop_n not in (None, 1):
                raise ValueError("quick 模式 loop_n 必须为 1")
            self.loop_n = 1
            if self.n_candidates is None:
                self.n_candidates = consts.DEFAULT_QUICK_CANDIDATES
            if self.max_llm_calls is None:
                self.max_llm_calls = consts.QUICK_MAX_LLM_CALLS
            if self.max_tokens is None:
                self.max_tokens = consts.QUICK_MAX_TOKENS
            if self.temperature is None:
                self.temperature = consts.QUICK_TEMPERATURE
        else:
            if self.n_candidates is None:
                self.n_candidates = consts.DEFAULT_DEEP_CANDIDATES
            if self.loop_n is None:
                self.loop_n = consts.DEFAULT_DEEP_LOOPS
            if self.max_llm_calls is None:
                self.max_llm_calls = consts.DEEP_MAX_LLM_CALLS
            if self.max_tokens is None:
                self.max_tokens = consts.DEEP_MAX_TOKENS
            if self.temperature is None:
                self.temperature = consts.DEEP_TEMPERATURE
        if not self.name:
            self.name = f"{self.mode}-{self.symbols[0]}-{self.start}"
        return self

    def to_config(self) -> dict:
        """会话配置快照（DB config_json / 前端详情共用）。"""
        return {
            "scenario": self.scenario,
            "symbols": self.symbols,
            "interval": self.interval,
            "candle_type": self.candle_type,
            "start": self.start,
            "end": self.end,
            "n_candidates": self.n_candidates,
            "loop_n": self.loop_n,
            "tasks_per_loop": self.tasks_per_loop,
            "repair_rounds": self.repair_rounds,
            "max_llm_calls": self.max_llm_calls,
            "max_tokens": self.max_tokens,
            "llm_max_tokens": self.llm_max_tokens,
            "llm_propose_timeout_secs": self.llm_propose_timeout_secs,
            "llm_plan_timeout_secs": self.llm_plan_timeout_secs,
            "llm_code_timeout_secs": self.llm_code_timeout_secs,
            "llm_feedback_timeout_secs": self.llm_feedback_timeout_secs,
            "icir_floor": self.icir_floor,
            "corr_threshold": self.corr_threshold,
            "seed_factor": self.seed_factor,
            "model_id": self.model_id,
            "temperature": self.temperature,
            "test_ratio": self.test_ratio,
            "wf_folds": self.wf_folds,
            "compose": self.compose,
        }


class ResearchExtendReq(BaseModel):
    """继续研究：追加轮次与增量预算。"""

    extra_loops: int = Field(default=2, ge=1, le=consts.MAX_LOOP_N)
    extra_max_llm_calls: int = Field(default=10, ge=1, le=200)
    extra_max_tokens: int = Field(default=50_000, ge=1000, le=1_000_000)


class ResearchTrialBatchReq(BaseModel):
    """对比用批量取 trial：一次 2–5 条，且必须同属一个会话。"""

    trial_ids: list[int] = Field(..., min_length=2, max_length=5)

    @field_validator("trial_ids")
    @classmethod
    def _unique(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("trial_ids 不能重复")
        return value
