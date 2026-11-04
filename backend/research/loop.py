"""研究闭环编排（PRD §5）。

deep 六步：propose → plan → code → run → feedback → record；
quick 只做一次「调用现有挖掘 → 映射 trial」。

关键约定：
- 每个 workspace 写操作开新 DB 会话（§11 #2），避免长事务；
- 预算、暂停、取消都在 step 边界检查；单条 trial 失败不拖垮会话；
- LLM 只产出假设/计划/代码/反馈，决策由 judge.py 的纯函数做；
- 恢复运行时不新建重复 trial：从会话里未终态的 trial 续跑（DB 唯一约束兜底）。
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from factor.llm_miner import (
    LLMMineParams,
    _metrics_from_analysis,
    _oos_metrics,
    run_llm_mining,
)
from research import agents, consts, service
from research.agents import (
    FactorTask,
    LLMCall,
    build_feedback,
    code_prompt,
    generate_code,
    generate_hypothesis,
    prompt_fingerprint,
    render_context,
)
from research.judge import evaluate_gates
from research.quick import map_candidates_to_trials, session_cost_from_stats
from research.scenario import ResearchScenario, get_scenario
from research.scenarios.factor import rank_corr
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class BudgetExhausted(Exception):
    """预算耗尽：按 completed 收尾，不标 failed。"""


class PauseSignal(Exception):
    """会话被暂停。"""


class CancelSignal(Exception):
    """会话被取消。"""


@dataclass
class Budget:
    max_calls: int
    max_tokens: int
    calls_used: int = 0
    tokens_used: int = 0

    def spend_call(self) -> None:
        """调用前预扣一次，避免预算耗尽后仍发起 LLM 请求。"""
        self.spend_calls(1)

    def spend_calls(self, count: int) -> None:
        extra = max(int(count or 0), 0)
        if self.calls_used + extra > self.max_calls:
            raise BudgetExhausted(f"LLM 调用次数将超过上限 {self.max_calls}")
        self.calls_used += extra

    def add_tokens(self, tokens: int) -> None:
        self.tokens_used += max(int(tokens or 0), 0)
        if self.tokens_used > self.max_tokens:
            raise BudgetExhausted(f"token 用量已达上限 {self.max_tokens}")

    def record(self, calls: int, tokens: int) -> None:
        """quick 模式用挖掘 stats 一次性记账。"""
        self.calls_used += max(int(calls), 0)
        self.tokens_used += max(int(tokens), 0)
        if self.calls_used > self.max_calls or self.tokens_used > self.max_tokens:
            raise BudgetExhausted("quick 轮用量已超预算")


def _default_corr(a: Any, b: Any) -> float | None:
    """训练段因子面板的 Spearman 秩相关；任一缺失或样本不足返回 None。"""
    return rank_corr(a, b)


def _cfg_number(cfg: dict[str, Any], key: str, default: float) -> float:
    """只把缺失（None）当成缺省；显式的 0 必须保留（避免 `or` 静默改写）。"""
    value = cfg.get(key)
    return default if value is None else float(value)


@dataclass
class LoopDeps:
    """可注入依赖，单测用假实现替换真实 LLM/数据/评估。"""

    llm_call: LLMCall | None = None
    mining_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    evaluator: Callable[..., dict[str, Any]] | None = None
    data_loader: Callable[..., dict[str, Any]] | None = None
    corr_fn: Callable[[Any, Any], float | None] = _default_corr
    db_session_factory: Callable[[], AbstractContextManager[Session]] = get_db_session
    scenario: ResearchScenario | None = None
    model_name: str | None = None
    # 过程事件上报（stage, msg）；由 job runner 注入，单测不关心
    event_fn: Callable[[str, str], None] | None = None

    def _scenario(self, cfg: dict[str, Any]) -> ResearchScenario:
        if self.scenario is not None:
            return self.scenario
        return get_scenario(str(cfg.get("scenario") or "factor"))

    def evaluate(self, code: str, raw_map: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        if self.evaluator is not None:
            return self.evaluator(code, raw_map, cfg)
        return self._scenario(cfg).evaluate(code, raw_map, cfg)

    def load(self, cfg: dict[str, Any]) -> dict[str, Any]:
        if self.data_loader is not None:
            return self.data_loader(cfg)
        from factor.engine import load_raw_ohlcv

        return load_raw_ohlcv(
            cfg["symbols"],
            cfg.get("interval", "1h"),
            cfg.get("candle_type", "spot"),
            cfg.get("start"),
            cfg.get("end"),
        )


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _checkpoint(control: service.Control | None) -> None:
    if control is None:
        return
    if control.cancel.is_set():
        raise CancelSignal()
    if control.pause.is_set():
        raise PauseSignal()


class ResearchLoop:
    """单会话执行器，由 job 线程同步调用。"""

    def __init__(self, session_id: int, deps: LoopDeps | None = None):
        self.session_id = session_id
        self.deps = deps or LoopDeps()
        self._sota_factor: Any = None
        self._sota_trial: dict[str, Any] | None = None
        self._scenario_obj: ResearchScenario | None = None

    # ---------- DB 小工具 ----------

    def _db(self) -> AbstractContextManager[Session]:
        return self.deps.db_session_factory()

    def _session_row(self, db: Session) -> Any:
        return service.get_session_row(db, self.session_id)

    def _load_trials(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = service.list_trials(db, self.session_id)
            return [service.trial_to_dict(r, include_code=True) for r in rows]

    def _persist_cost(self, budget: Budget) -> None:
        with self._db() as db:
            service.update_session_fields(
                db,
                self.session_id,
                token_used=budget.tokens_used,
                llm_calls=budget.calls_used,
            )

    def _set_step(self, step_idx: int) -> None:
        with self._db() as db:
            service.update_session_fields(db, self.session_id, step_idx=step_idx)

    def _event(self, stage: str, msg: str) -> None:
        """上报过程事件；事件通道只做观测，失败不影响主流程。"""
        fn = self.deps.event_fn
        if fn is None:
            return
        try:
            fn(stage, msg[:200])
        except Exception:
            logger.exception("[研究] 过程事件上报失败，已忽略")

    def _finish(self, status: str, *, error: str | None = None) -> None:
        with self._db() as db:
            row = self._session_row(db)
            if row.status in {"completed", "failed", "cancelled"}:
                return
            try:
                service.set_session_status(db, row, status, error=error)
            except service.ResearchError:
                # 外部已按暂停/取消/延期改过状态（CAS 失败），不覆盖
                logger.info(f"[研究] 会话 {self.session_id} 收尾状态被并发改写，跳过 {status}")

    # ---------- 入口 ----------

    def run(self, control: service.Control | None = None) -> None:
        with self._db() as db:
            row = self._session_row(db)
            cfg = service.session_config(row)
            mode = row.mode
            budget = Budget(
                max_calls=int(cfg.get("max_llm_calls") or 0),
                max_tokens=int(cfg.get("max_tokens") or 0),
                calls_used=int(row.llm_calls or 0),
                tokens_used=int(row.token_used or 0),
            )
        try:
            self._event("session.start", f"mode={mode}")
            if mode == "quick":
                self._run_quick(cfg, budget, control)
            else:
                self._run_deep(cfg, budget, control)
            self._finish("completed")
            self._event("session.completed", "研究流程结束")
        except BudgetExhausted as exc:
            logger.info(f"[研究] 会话 {self.session_id} 预算耗尽，按完成收尾：{exc}")
            self._event("session.budget_exhausted", str(exc))
            self._finish("completed")
        except CancelSignal:
            logger.info(f"[研究] 会话 {self.session_id} 已取消")
            self._event("session.cancelled", "收到取消信号")
        except PauseSignal:
            logger.info(f"[研究] 会话 {self.session_id} 已暂停")
            self._event("session.paused", "收到暂停信号，可从当前 trial 续跑")
        except Exception as exc:
            logger.exception(f"[研究] 会话 {self.session_id} 失败")
            self._event("session.failed", str(exc))
            self._finish("failed", error=str(exc))

    # ---------- quick ----------

    def _run_quick(self, cfg: dict[str, Any], budget: Budget, control: service.Control | None) -> None:
        _checkpoint(control)
        if self.deps.mining_fn is None:
            raise RuntimeError("quick 模式缺少 mining_fn 依赖")
        # quick 是一次性批量调用，先确认还有额度，避免花掉最后一次调用
        if budget.calls_used + 1 > budget.max_calls:
            raise BudgetExhausted(f"LLM 调用次数已达上限 {budget.max_calls}")

        result = self.deps.mining_fn(cfg)
        self._event("quick.mined", f"candidates={len(result.get('candidates') or [])}")
        calls, tokens = session_cost_from_stats(result.get("stats"))
        trials = map_candidates_to_trials(
            result.get("candidates") or [],
            quick_run_id=result.get("run_id"),
        )
        # I2：先落库候选与成本，再判预算；否则“钱花了但 trials=0”
        with self._db() as db:
            for fields in trials:
                service.add_trial(db, self.session_id, fields)
            service.update_session_fields(
                db,
                self.session_id,
                loop_done=1,
                step_idx=0,
                token_used=budget.tokens_used + tokens,
                llm_calls=budget.calls_used + calls,
            )
        budget.record(calls, tokens)

    # ---------- deep ----------

    def _run_deep(self, cfg: dict[str, Any], budget: Budget, control: service.Control | None) -> None:
        if self.deps.llm_call is None:
            raise RuntimeError("deep 模式缺少 llm_call 依赖")
        self._scenario_obj = self.deps._scenario(cfg)
        raw_map = self.deps.load(cfg)
        with self._db() as db:
            row = self._session_row(db)
            loop_done = int(row.loop_done or 0)
            loop_n = int(cfg.get("loop_n") or 1)
        # SOTA 从 best_trial_id 反查重建：resume/extend 后内存里的旧因子已丢失
        self._ensure_sota(raw_map, cfg)
        self._event("deep.start", f"loop_done={loop_done} loop_n={loop_n}")

        for loop_idx in range(loop_done + 1, loop_n + 1):
            _checkpoint(control)
            existing = self._trial_at(loop_idx)
            if existing is not None and existing["status"] in service.TERMINAL_TRIAL_STATUSES:
                # 上一进程在 trial 终态后、loop_done 落库前退出：补齐进度，不重跑
                with self._db() as db:
                    service.update_session_fields(db, self.session_id, loop_done=loop_idx, step_idx=0)
                continue
            self._execute_loop(loop_idx, cfg, raw_map, budget, control, resume=existing)
            with self._db() as db:
                service.update_session_fields(db, self.session_id, loop_done=loop_idx, step_idx=0)
            self._persist_cost(budget)

    def _trial_at(self, loop_idx: int) -> dict[str, Any] | None:
        with self._db() as db:
            row = service.find_trial(db, self.session_id, loop_idx, 1)
            if row is None:
                return None
            return service.trial_to_dict(row, include_code=True)

    def _ensure_sota(self, raw_map: dict[str, Any], cfg: dict[str, Any]) -> None:
        """best_trial_id → 代码 → 重新评估 → 训练段因子序列（供硬门 3 对比）。"""
        best_id = self._best_trial_id()
        if best_id is None:
            return
        with self._db() as db:
            best = service.get_trial_row(db, best_id)
            code = best.code or ""
            self._sota_trial = {
                "id": best.id,
                "metrics": service._loads(best.metrics_json, {}),
                "code": code,
            }
        if not code:
            return
        try:
            analysis = self.deps.evaluate(code, raw_map, cfg)
            self._sota_factor = analysis.get("train_factor")
        except Exception:
            logger.exception("[研究] 重建 SOTA 因子失败，硬门 3 仅对比因子库")

    def _charge_usage(self, budget: Budget, usage: dict[str, Any]) -> None:
        """按真实调用次数补扣（重试次数已在 agents 里累计），token 走兜底口径。"""
        calls = int(usage.get("llm_calls") or 0)
        if calls > 1:
            budget.spend_calls(calls - 1)
        budget.add_tokens(agents.usage_tokens(usage))

    def _execute_loop(
        self,
        loop_idx: int,
        cfg: dict[str, Any],
        raw_map: dict[str, Any],
        budget: Budget,
        control: service.Control | None,
        resume: dict[str, Any] | None = None,
    ) -> None:
        trials = self._load_trials()
        sota = next((t for t in trials if t["id"] == self._best_trial_id()), None)
        context = render_context(trials, sota or self._sota_trial)

        trial_id: int | None = None
        start_status = "planned"
        metrics: dict[str, Any] = {}
        flag: str | None = None
        analysis: dict[str, Any] = {}
        corr_sota: float | None = None
        corr_library: float | None = None
        feedback_done = False
        started_at = time.monotonic()

        if resume is None:
            # step 1 propose
            self._set_step(1)
            budget.spend_call()
            hypothesis, usage = generate_hypothesis(self.deps.llm_call, context, cfg.get("seed_factor"))
            self._charge_usage(budget, usage)
            self._persist_cost(budget)
            self._event("trial.proposed", f"loop={loop_idx} {hypothesis.hypothesis}")
            _checkpoint(control)

            # step 2 plan
            self._set_step(2)
            budget.spend_call()
            tasks, usage = self._scenario_obj.build_tasks(
                llm_call=self.deps.llm_call,
                hypothesis=hypothesis.hypothesis,
                context=context,
                n=int(cfg.get("tasks_per_loop") or consts.DEFAULT_TASKS_PER_LOOP),
            )
            self._charge_usage(budget, usage)
            self._persist_cost(budget)
            self._event("trial.planned", f"loop={loop_idx} tasks={len(tasks)}")
            _checkpoint(control)

            if not tasks:
                with self._db() as db:
                    service.add_trial(
                        db,
                        self.session_id,
                        {
                            "loop_idx": loop_idx,
                            "candidate_idx": 1,
                            "status": "failed",
                            "hypothesis": hypothesis.hypothesis,
                            "hypothesis_reason": hypothesis.reason,
                            "hypothesis_prediction": hypothesis.prediction,
                            "exception": "实验计划为空",
                            "duration_ms": int((time.monotonic() - started_at) * 1000),
                        },
                    )
                return

            task = tasks[0]
            with self._db() as db:
                trial = service.add_trial(
                    db,
                    self.session_id,
                    {
                        "loop_idx": loop_idx,
                        "candidate_idx": 1,
                        "status": "planned",
                        "hypothesis": hypothesis.hypothesis,
                        "hypothesis_reason": hypothesis.reason,
                        "hypothesis_prediction": hypothesis.prediction,
                        "task_json": task.model_dump(),
                        "model": self.deps.model_name,
                        "temperature": _cfg_number(cfg, "temperature", consts.DEEP_TEMPERATURE),
                    },
                )
                trial_id = trial.id
                self._event("trial.start", f"loop={loop_idx} trial={trial_id}")
        else:
            # 续跑：沿用已落库的假设/任务/中间结果，不重复创建 trial
            trial_id = int(resume["id"])
            start_status = str(resume["status"])
            task = FactorTask.model_validate(resume.get("task") or {})
            metrics = dict(resume.get("metrics") or {})
            flag = resume.get("oos_flag")
            feedback_done = bool(resume.get("feedback"))
            # 续跑不重跑评估：硬门 3 的相关性直接用评估时持久化的值
            corr_sota = resume.get("corr_sota")
            corr_library = resume.get("corr_library")
            logger.info(f"[研究] 会话 {self.session_id} 续跑 trial {trial_id}（status={start_status}）")

        try:
            code = "" if resume is None else (resume.get("code") or "")

            # step 3 code（coding 状态说明上次在生成代码时中断，重生成即可）
            if start_status in {"planned", "coding"} or not code:
                self._set_step(3)
                if start_status == "planned":
                    with self._db() as db:
                        service.update_trial(db, trial_id, status="coding")
                budget.spend_call()
                code, usage = generate_code(self.deps.llm_call, task)
                self._charge_usage(budget, usage)
                self._persist_cost(budget)
                if not code:
                    raise RuntimeError("LLM 未返回可用代码")
                with self._db() as db:
                    service.update_trial(
                        db,
                        trial_id,
                        status="coded",
                        code=code,
                        code_hash=_hash_code(code),
                        prompt_hash=prompt_fingerprint(*code_prompt(task)),
                    )
                self._event("trial.coded", f"loop={loop_idx} trial={trial_id} code_len={len(code)}")
                _checkpoint(control)

            # step 4 run（evaluated 之后的续跑直接复用已落库指标）
            if start_status in {"planned", "coding", "coded", "running"}:
                self._set_step(4)
                with self._db() as db:
                    service.update_trial(db, trial_id, status="running")
                analysis = self.deps.evaluate(code, raw_map, cfg)
                train = analysis.get("train")
                if not train:
                    raise RuntimeError("评估结果缺少 train 段")
                metrics = _metrics_from_analysis(train)
                metrics_oos, flag, note, _folds = _oos_metrics(
                    analysis, metrics, _cfg_number(cfg, "test_ratio", consts.DEFAULT_TEST_RATIO)
                )
                metrics["oos"] = metrics_oos
                # 硬门 3 的相关性在评估完成时一并落库，续跑 judge 不再重算
                corr_sota, corr_library = self._corr_values(analysis, raw_map, cfg)
                with self._db() as db:
                    service.update_trial(
                        db,
                        trial_id,
                        status="evaluated",
                        metrics_json=metrics,
                        metrics_oos_json=metrics_oos,
                        oos_flag=flag,
                        oos_note=note,
                        corr_sota=corr_sota,
                        corr_library=corr_library,
                    )
                self._event(
                    "trial.evaluated",
                    f"loop={loop_idx} trial={trial_id} ic={metrics.get('ic_mean')} "
                    f"icir={metrics.get('ic_ir')} oos={flag} "
                    f"corr_sota={corr_sota} corr_library={corr_library}",
                )
                _checkpoint(control)

            # step 5 feedback（续跑时已有反馈则跳过，避免重复计费）
            if not feedback_done:
                self._set_step(5)
                budget.spend_call()
                feedback, usage = build_feedback(self.deps.llm_call, context, metrics, (sota or {}).get("metrics"))
                self._charge_usage(budget, usage)
                self._persist_cost(budget)
                with self._db() as db:
                    service.update_trial(db, trial_id, feedback_json=feedback.model_dump())
                self._event("trial.feedback", f"loop={loop_idx} trial={trial_id}")
                _checkpoint(control)

            # step 6 record / judge
            self._set_step(6)
            judge = evaluate_gates(
                ic_ir=metrics.get("ic_ir"),
                oos_flag=flag,
                corr_vs_sota=corr_sota,
                corr_vs_library=corr_library,
                icir_floor=_cfg_number(cfg, "icir_floor", consts.DEFAULT_ICIR_FLOOR),
                corr_threshold=_cfg_number(cfg, "corr_threshold", consts.DEFAULT_CORR_THRESHOLD),
                # 有 SOTA 时必须给出 SOTA 相关性；缺失记为 unknown，不放行
                sota_expected=self._sota_trial is not None,
            )
            with self._db() as db:
                service.update_trial(
                    db,
                    trial_id,
                    status="judged",
                    judge_json=judge,
                    decision=judge["decision"],
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                )
            self._event(
                "trial.judged",
                f"loop={loop_idx} trial={trial_id} decision={judge['decision']} {judge['reason']}",
            )
            if judge["decision"]:
                self._sota_factor = analysis.get("train_factor")
                with self._db() as db:
                    service.update_session_fields(db, self.session_id, best_trial_id=trial_id)
        except BudgetExhausted, CancelSignal, PauseSignal:
            # 进度类信号保留非终态，恢复时可从当前 trial 续跑
            raise
        except Exception as exc:
            logger.info(f"[研究] trial {trial_id} 失败：{exc}")
            self._event("trial.failed", f"loop={loop_idx} trial={trial_id} {exc}")
            if trial_id is not None:
                try:
                    with self._db() as db:
                        service.update_trial(
                            db,
                            trial_id,
                            status="failed",
                            exception=str(exc)[:1000],
                            duration_ms=int((time.monotonic() - started_at) * 1000),
                        )
                except Exception:
                    logger.exception("[研究] 标记 trial 失败时再次出错")
        finally:
            self._persist_cost(budget)

    def _corr_values(
        self, analysis: dict[str, Any], raw_map: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[float | None, float | None]:
        """硬门 3：与 SOTA 及因子库的最大 |秩相关|。"""
        factor_series = analysis.get("train_factor")
        corr_sota = None
        if self._sota_factor is not None:
            corr_sota = self.deps.corr_fn(factor_series, self._sota_factor)
        corr_library = None
        library_corr = getattr(self._scenario_obj, "library_corr", None)
        if callable(library_corr):
            try:
                corr_library = library_corr(factor_series, raw_map)
            except Exception:
                logger.exception("[研究] 因子库相关性计算失败，硬门 3 仅对比 SOTA")
        return corr_sota, corr_library

    def _best_trial_id(self) -> int | None:
        with self._db() as db:
            return self._session_row(db).best_trial_id


def mining_params_from_config(cfg: dict[str, Any], model_name: str) -> LLMMineParams:
    """研究会话配置 → 现有挖掘参数（quick 复用，不改挖掘语义）。"""
    return LLMMineParams(
        symbols=list(cfg["symbols"]),
        interval=cfg.get("interval", "1h"),
        candle_type=cfg.get("candle_type", "spot"),
        start=cfg.get("start"),
        end=cfg.get("end"),
        n_candidates=int(cfg.get("n_candidates") or consts.DEFAULT_QUICK_CANDIDATES),
        n_rounds=1,  # quick 固定单轮
        temperature=_cfg_number(cfg, "temperature", consts.QUICK_TEMPERATURE),
        model_name=model_name or "",
        test_ratio=_cfg_number(cfg, "test_ratio", consts.DEFAULT_TEST_RATIO),
        wf_folds=int(_cfg_number(cfg, "wf_folds", consts.DEFAULT_WF_FOLDS)),
        dedup_corr=consts.QUICK_DEDUP_CORR,
        compose=bool(cfg.get("compose", True)),
    )


def default_mining_fn(backend: Any, model_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """构造 quick 执行器：直接把会话配置喂给 run_llm_mining。"""

    def _run(cfg: dict[str, Any]) -> dict[str, Any]:
        params = mining_params_from_config(cfg, model_name)
        return run_llm_mining(params, backend=backend)

    return _run


def default_llm_call(backend: Any) -> LLMCall:
    """axon backend → 同步 (system,user) 调用（线程内 asyncio.run）。"""
    import asyncio

    from axon_bridge.llm import chat_to_dict

    def _call(system: str, user: str) -> tuple[str, dict[str, Any]]:
        resp = asyncio.run(
            chat_to_dict(
                backend,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        )
        return (resp.get("content") or ""), (resp.get("usage") or {})

    return _call
