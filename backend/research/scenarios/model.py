"""model 场景实现：候选 = RL 训练配置（JSON），评估 = 小规模训练 + Walk-Forward，产物 = 模型注册表。

PRD §5.4 / P2 里程碑：MVP「结构搜索但复用现有推理」——候选不是生成模型代码，
而是 RLTrainConfig 参数空间（算法/步数/特征/奖励/折数）的 JSON 配置；训练复用
RLService.train(walk_forward=True)，采纳落 ModelRegistryService（metrics 一并回填）。
场景内硬限额（consts.MODEL_*）保证 evaluate 同步回调分钟级返回；notes §4.1
明令不复用 IC 门禁：无 IC/相关性事件，判重自动跳过（无 train_factor），硬门走 WF 指标。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from research import agents, consts, service
from research.scenarios.base import ScenarioDefaults, _extract_json
from services.model_registry import ModelRegistryService
from utils.db_session import get_db_session

MODEL_HYPOTHESIS_SYSTEM = (
    "你是资深量化模型研究员。基于研究历史与数据说明，提出一条下一步要训练的 RL 模型方向假设，"
    "说明为什么在当前进度下值得试（避免重复已失败的方向）。只输出 JSON："
    '{"hypothesis": "...", "reason": "...", "prediction": "..."}'
)

MODEL_PLAN_SYSTEM = (
    "你是 RL 模型配置搜索规划器。根据假设提出 n 个不同的模型训练配置任务，"
    "在算法（ppo/sac/dqn）、训练步数、特征组合、奖励类型之间拉开差异。"
    "只输出 JSON 数组，元素字段 name/description/params，"
    "params 含 algorithm/total_timesteps/features/reward_type/wf_splits。"
)

MODEL_CODE_SYSTEM = (
    "你生成 RL 模型训练配置。只输出一个 JSON 对象（可放 ```json 代码块），字段：\n"
    '{"algorithm": "ppo|sac|dqn", "total_timesteps": 整数, '
    '"features": ["close", "volume"], "reward_type": "pnl|sharpe", "wf_splits": 整数}\n'
    "约束：features 只能从数据说明列出的列中选；total_timesteps 上限 20000；wf_splits 2~3。"
)

MODEL_FEEDBACK_SYSTEM = (
    "你是量化模型评审。结合研究历史与本轮 walk-forward 训练指标（折均夏普/成交数/最末折表现），"
    "给出下一步：继续调整当前配置族，还是换方向。只输出 JSON："
    '{"observations": "...", "evaluation": "...", "new_hypothesis": "...", "reason": "..."}'
)


class ModelTask(BaseModel):
    """deep 闭环的模型候选任务规格：params 是 RLTrainConfig 参数子集（值可能是列表/字符串/数字）。"""

    name: str = Field(default="model", max_length=80)
    description: str = Field(min_length=1, max_length=600)
    params: dict[str, Any] = Field(default_factory=dict)


def _clamp_int(value: Any, lo: int, hi: int, field_name: str) -> int:
    try:
        num = int(float(value))
    except TypeError, ValueError:
        raise ValueError(f"{field_name}={value!r} 不是有效整数") from None
    return min(max(num, lo), hi)


class ModelScenario(ScenarioDefaults):
    """model 场景：候选是训练配置 JSON，评估走 RL 训练 + WF，采纳落模型注册表。"""

    key = "model"

    # ---- 场景协议：describe / build_tasks / evaluate / promote ----

    def describe(self, cfg: dict[str, Any]) -> str:
        return (
            f"场景：RL 模型挖掘。数据：{','.join(cfg.get('symbols') or [])} "
            f"{cfg.get('interval', '1h')}，窗口 {cfg.get('start')}~{cfg.get('end')}，单品种训练。"
            "评估口径：walk-forward 训练验证（2~3 折），硬门看折均 OOS 夏普与成交数；"
            f"候选是 JSON 训练配置，训练步数限额 {consts.MODEL_MAX_TIMESTEPS}。"
        )

    def build_tasks(self, *, llm_call, hypothesis: str, context: str, n: int) -> tuple[list[ModelTask], dict[str, Any]]:
        user = f"假设：{hypothesis}\n\n上下文：\n{context}\n\n请提出 {max(int(n), 1)} 个模型配置任务（JSON 数组）。"
        content, usage = llm_call(MODEL_PLAN_SYSTEM, user, stage="plan")
        data = _extract_json(content)
        items = data if isinstance(data, list) else data.get("tasks", [])
        tasks: list[ModelTask] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                tasks.append(
                    ModelTask(
                        name=str(item.get("name") or "model")[:80],
                        description=str(item.get("description") or ""),
                        params=dict(item.get("params") or {}),
                    )
                )
            except TypeError, ValueError:
                # 单条任务坏了不影响其余候选
                continue
        return tasks[: max(int(n), 1)], usage

    def evaluate(self, code: str, raw_map: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        # 延迟导入：RLService 组合 HPO/WF 服务与模型目录，保持 research 导入期轻依赖
        from services.rl_service import RLService, RLTrainConfig

        if not raw_map:
            raise ValueError("没有可用的行情数据")
        # MVP 单品种（场景硬限额的一部分）：WF 逐折切分本身按时间纵向切，不涉及多品种池
        sym, df = next(iter(raw_map.items()))
        # create_env 内部会把列名统一小写，校验用同一口径
        params = self._parse_params(code, {str(c).lower() for c in df.columns})

        result = RLService().train(
            RLTrainConfig(
                algorithm=params["algorithm"],
                data=df,
                symbol=sym,
                interval=str(cfg.get("interval") or "1h"),
                candle_type=str(cfg.get("candle_type") or "spot"),
                features=params["features"],
                reward_type=params["reward_type"],
                total_timesteps=params["total_timesteps"],
                walk_forward=True,
                wf_splits=params["wf_splits"],
            )
        )
        return self._build_analysis(sym, params, result)

    def promote(self, trial: dict[str, Any]) -> str:
        """采纳 trial：训练产物注册到模型注册表（metrics/metadata 一并回填），幂等。

        model_path 在 evaluate 时由 RLService.train 落盘到 MODELS_DIR（持久），
        随 trial.metrics_json 保存，重试 promote 时文件仍在。
        """
        already = trial.get("promoted_factor_name")
        if already:
            return str(already)
        metrics = trial.get("metrics") or {}
        model_path = str(metrics.get("model_path") or "")
        if not model_path:
            raise ValueError("trial 没有可注册的训练产物（metrics 缺 model_path）")
        name = f"rs_{int(trial['session_id'])}_{int(trial['id'])}"
        ModelRegistryService().register_model(
            name=name,
            model_path=model_path,
            metadata={
                "source": "research",
                "session_id": trial.get("session_id"),
                "trial_id": trial.get("id"),
                "hypothesis": str(trial.get("hypothesis") or "")[:200],
                "algorithm": metrics.get("algorithm"),
                "params": {k: metrics.get(k) for k in ("total_timesteps", "wf_splits", "features", "reward_type")},
            },
            metrics={k: metrics.get(k) for k in ("sharpe_ratio", "total_pnl", "trades", "win_rate", "n_valid_folds")},
        )
        with get_db_session() as db:
            service.update_trial(db, int(trial["id"]), promoted_factor_name=name)
        return name

    # ---- 场景钩子覆写（默认实现见 scenarios/base.py） ----

    def generate_hypothesis(self, llm_call, context: str, seed_factor: str | None):
        # 种子因子在 model 场景只作方向参考（候选是配置不是因子公式），原样附进上下文
        extra = f"\n\n参考因子方向：{seed_factor}" if seed_factor else ""
        content, usage = llm_call(MODEL_HYPOTHESIS_SYSTEM, context + extra, stage="propose")
        try:
            data = _extract_json(content)
            return agents.HypothesisOut(**data), usage
        except ValueError:
            return agents.HypothesisOut(
                hypothesis="探索不同算法与奖励下的 RL 模型", reason="LLM 输出不可解析，使用兜底假设"
            ), usage

    def data_note(self, raw_map: dict[str, Any], cfg: dict[str, Any], train_bars: int) -> str:
        # 特征列只能从真实数据列里选：把可用列直接列进上下文，减少 LLM 瞎编列名
        _, df = next(iter((raw_map or {}).items()), (None, None))
        cols = sorted({str(c).lower() for c in df.columns}) if df is not None else []
        return (
            f"- 单品种训练：{','.join(cfg.get('symbols') or [])} {cfg.get('interval') or '1h'}，"
            f"训练数据约 {train_bars} 根 K 线\n"
            f"- 可用特征列：{cols}\n"
            "- 候选是 JSON 训练配置（不是代码），模型与训练/评估链路由系统固定，只搜索配置空间"
        )

    def code_prompt(self, task: ModelTask) -> tuple[str, str]:
        user = (
            f"配置名称：{task.name}\n意图：{task.description}\n"
            f"建议参数：{json.dumps(task.params, ensure_ascii=False, default=str)}\n"
            "请只输出一个 JSON 对象。"
        )
        return MODEL_CODE_SYSTEM, user

    def generate_code(self, llm_call, task: ModelTask) -> tuple[str, dict[str, Any]]:
        system, user = self.code_prompt(task)
        content, usage = llm_call(system, user, stage="code")
        return json.dumps(_extract_json(content), ensure_ascii=False), usage

    def repair_code(self, llm_call, task: ModelTask, code: str, kind: str, error: str) -> tuple[str, dict[str, Any]]:
        system, user = self.code_prompt(task)
        user += (
            f"\n\n上一版配置无法评估（{kind}）：{str(error)[:300]}\n\n"
            f"上一版配置：\n{code[:2000]}\n"
            "返修要求：保持配置意图，修复上述问题后输出完整 JSON 对象。"
        )
        content, usage = llm_call(system, user, stage="code")
        return json.dumps(_extract_json(content), ensure_ascii=False), usage

    def build_feedback(self, llm_call, context: str, metrics: dict[str, Any], sota_metrics):
        user = (
            f"{context}\n\n本轮 WF 训练指标：{json.dumps(metrics, ensure_ascii=False, default=str)}\n"
            f"当前 SOTA：{json.dumps(sota_metrics or {}, ensure_ascii=False, default=str)}"
        )
        content, usage = llm_call(MODEL_FEEDBACK_SYSTEM, user, stage="feedback")
        try:
            return agents.FeedbackOut(**_extract_json(content)), usage
        except ValueError:
            return agents.FeedbackOut(evaluation="LLM 输出不可解析", reason=""), usage

    def metrics_from_analysis(self, analysis: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        # 折均指标整体进 metrics_json：promote 注册回填与详情页展示都从这里拿
        return dict(analysis["train"])

    def oos_metrics(
        self, analysis: dict[str, Any], metrics: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """样本外口径：WF 最末折 OOS 指标对比折均值（最后一折是最近时段的真实 OOS）。"""
        last = analysis.get("last_fold") or {}
        if not last or not analysis.get("train", {}).get("n_valid_folds"):
            return None, None, "无有效 WF 折（训练数据不足或训练失败）"
        mean_sharpe = float(metrics.get("sharpe_ratio") or 0.0)
        last_sharpe = float(last.get("sharpe_ratio") or 0.0)
        oos = {k: v for k, v in last.items() if isinstance(v, (int, float))}
        if last_sharpe <= 0:
            flag = "sign_flip"
        elif mean_sharpe > 0 and last_sharpe < 0.3 * mean_sharpe:
            flag = "weak"
        else:
            flag = "ok"
        return oos, flag, f"last_fold_sharpe={last_sharpe:.2f} vs wf_mean={mean_sharpe:.2f}"

    def judge(
        self,
        *,
        metrics: dict[str, Any],
        oos_flag: str | None,
        corr_sota: float | None = None,
        corr_library: float | None = None,
        cfg: dict[str, Any] | None = None,
        sota_expected: bool = False,
    ) -> dict[str, Any]:
        """模型硬门：WF 折均夏普 ≥ 下限、OOS 折均成交数达标、最末折不翻转。

        不复用 IC 门禁（notes §4.1）；corr_* 参数与模型门无关，保留签名以匹配 loop 调用。
        """
        cfg = cfg or {}
        floor = float(cfg.get("sharpe_floor") or consts.DEFAULT_MODEL_SHARPE_FLOOR)
        min_trades = int(cfg.get("min_trades") or consts.DEFAULT_MODEL_MIN_TRADES)
        sharpe = metrics.get("sharpe_ratio")
        trades = metrics.get("trades")
        gates = {
            "sharpe": {"pass": sharpe is not None and float(sharpe) >= floor, "value": sharpe, "floor": floor},
            "trades": {
                "pass": trades is not None and int(trades or 0) >= min_trades,
                "value": trades,
                "floor": min_trades,
            },
            "oos": {"pass": oos_flag in (None, "ok"), "value": oos_flag},
        }
        failed = [name for name, g in gates.items() if not g["pass"]]
        decision = not failed
        return {
            "decision": decision,
            "gates": gates,
            "reason": "模型硬门全部通过" if decision else "未通过：" + "、".join(failed),
        }

    # ---- 内部工具 ----

    def _parse_params(self, code: str, columns: set[str]) -> dict[str, Any]:
        """trial.code（JSON 文本）→ 校验并 clamp 到场景限额的配置 dict。

        非法 JSON / 缺关键字段 / 非法列名抛 ValueError（触发 loop 的 step4 修复回灌）；
        数值超限 clamp 而不报错——限额是场景保护，不是 LLM 错误。
        """
        data = _extract_json(code)
        if not isinstance(data, dict):
            raise ValueError("模型配置必须是 JSON 对象")
        algorithm = str(data.get("algorithm") or "").strip().lower()
        if algorithm not in consts.MODEL_ALGORITHMS:
            raise ValueError(f"algorithm 必须是 {'/'.join(consts.MODEL_ALGORITHMS)} 之一")
        features = [str(c) for c in (data.get("features") or [])]
        if not features:
            raise ValueError("features 不能为空（从数据说明列出的列里选）")
        missing = [c for c in features if c not in columns]
        if missing:
            raise ValueError(f"features 含数据中不存在的列：{missing}，可用列：{sorted(columns)}")
        return {
            "algorithm": algorithm,
            "features": features,
            "reward_type": str(data.get("reward_type") or "pnl"),
            "total_timesteps": _clamp_int(
                data.get("total_timesteps") or 10_000,
                consts.MODEL_MIN_TIMESTEPS,
                consts.MODEL_MAX_TIMESTEPS,
                "total_timesteps",
            ),
            "wf_splits": _clamp_int(
                data.get("wf_splits") or 3,
                consts.MODEL_MIN_WF_SPLITS,
                consts.MODEL_MAX_WF_SPLITS,
                "wf_splits",
            ),
        }

    def _build_analysis(self, sym: str, params: dict[str, Any], result: Any) -> dict[str, Any]:
        """RLTrainResult → loop 消费的分析结构（train 段必填 + per_symbol + 末折）。"""
        wf = result.walk_forward or {}
        agg = wf.get("aggregate") or {}
        mean = agg.get("mean") or {}
        std = agg.get("std") or {}
        folds = wf.get("folds") or []
        last = next((f.get("oos_metrics") for f in reversed(folds) if f.get("oos_metrics")), None)
        train = {
            "sharpe_ratio": round(float(mean.get("sharpe_ratio") or 0.0), 4),
            "total_pnl": round(float(mean.get("total_pnl") or 0.0), 2),
            "trades": int(float(mean.get("num_trades") or 0)),
            "win_rate": round(float(mean.get("win_rate") or 0.0), 4),
            "max_drawdown_pct": round(float(mean.get("max_drawdown_pct") or 0.0), 2),
            "wf_sharpe_std": round(float(std.get("sharpe_ratio") or 0.0), 4),
            "n_valid_folds": int(agg.get("n_valid_folds") or 0),
            "n_folds": len(folds),
            "algorithm": params["algorithm"],
            "total_timesteps": params["total_timesteps"],
            "wf_splits": params["wf_splits"],
            "features": params["features"],
            "reward_type": params["reward_type"],
            "model_id": result.model_id,
            "model_path": result.model_path,
        }
        analysis: dict[str, Any] = {
            "train": train,
            "per_symbol": {sym: {"train": train}},
            # 最末折 OOS 指标单独放：给 oos_metrics 钩子用，不混进 metrics
            "last_fold": {k: v for k, v in (last or {}).items() if isinstance(v, (int, float))},
            # 无 train_factor：loop 的因子相关性去重自动跳过（与 strategy 场景同做法）
        }
        return analysis
