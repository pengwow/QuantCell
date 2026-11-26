"""RL 策略自动迭代生命周期

自动循环：训练 → 回测评估 → 决策 → 重训练 → 循环

使用：python -m rl.lifecycle --symbol BTCUSDT --interval 1h
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.retrain_policy import (
    AUTO_PROMOTE_ENV,
    AUTO_RETRAIN_ENV,
    RetrainCandidate,
    RetrainPolicy,
    auto_promote_enabled,
    auto_retrain_enabled,
    env_flag,
    record_retrain,
    select_retrain_candidates,
)
from services.rl_service import MODELS_DIR, CostProfile, RLService, RLTrainConfig
from services.rl_task_runner import cancel_task, get_task, submit_train_task
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


def audit_recent_oos(models_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """扫描模型旁车,按族给出 promote 门槛判定(只读,不触发训练)。

    周期入口:core.scheduler 的每日审计 job 直接调用;也可在 lifecycle
    run_loop 的每轮迭代里复用。
    """
    from services.oos_gate import audit_oos_gate

    results = audit_oos_gate(models_dir or MODELS_DIR)
    for result in results:
        if result.get("blocked"):
            logger.warning(f"[OOS] 晋升门槛: {result['reason']}")
    return results


@dataclass
class LifecycleConfig:
    """生命周期配置"""

    symbol: str = "BTCUSDT"
    interval: str = "1h"
    algorithm: str = "ppo"
    reward_type: str = "pnl"
    train_timesteps: int = 30_000
    retrain_timesteps: int = 10_000
    # 重训练触发条件
    min_trades: int = 10  # 最少交易次数
    max_drawdown_pct: float = 5.0  # 最大回撤阈值（%）
    min_sharpe: float = 0.5  # 最低夏普比率
    # 循环控制
    check_interval_hours: int = 24  # 检查间隔（小时）


@dataclass
class ModelMetrics:
    """模型性能指标（来自真实回测）"""

    model_name: str
    timestamp: str = ""
    total_pnl: float = 0.0
    num_trades: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    portfolio_value: float = 100_000.0


class RLLifecycle:
    """RL 策略自动迭代生命周期，统一委托给 services.rl_service 完成真实训练与回测。"""

    def __init__(self, config: LifecycleConfig | None = None):
        self.config = config or LifecycleConfig()
        self._svc = RLService()

    def _make_train_config(self, timesteps: int, model_name: str) -> RLTrainConfig:
        return RLTrainConfig(
            algorithm=self.config.algorithm,
            symbol=self.config.symbol,
            interval=self.config.interval,
            total_timesteps=timesteps,
            reward_type=self.config.reward_type,
            model_name=model_name,
        )

    @staticmethod
    def _to_metrics(model_name: str, bt: dict) -> ModelMetrics:
        """将 services.rl_service.run_backtest 的返回字典转换为 ModelMetrics。"""
        return ModelMetrics(
            model_name=model_name,
            total_pnl=bt.get("total_pnl", 0.0),
            num_trades=bt.get("num_trades", 0),
            win_rate=bt.get("win_rate", 0.0),
            sharpe_ratio=bt.get("sharpe_ratio", 0.0),
            max_drawdown_pct=bt.get("max_drawdown_pct", 0.0),
            portfolio_value=bt.get("initial_capital", 100_000.0) + bt.get("total_pnl", 0.0),
        )

    def run_initial_training(self) -> str:
        """初始训练，返回保存后的模型路径。"""
        logger.info(f"[Phase 1] 初始训练: {self.config.symbol} {self.config.interval}")
        result = self._svc.train(self._make_train_config(self.config.train_timesteps, f"{self.config.symbol}_v1"))
        logger.info(f"[Phase 1] 训练完成: {result.model_path}")
        return result.model_path

    def run_backtest(self, model_path: str) -> dict:
        """用已训练模型做真实回测，返回 services.rl_service.run_backtest 的指标字典。"""
        logger.info(f"[Phase 2] 回测: {model_path}")
        result = self._svc.run_backtest(
            model_path, self.config.symbol, self.config.interval, reward_type=self.config.reward_type
        )
        logger.info(f"[Phase 2] 回测完成: PnL=${result.get('total_pnl', 0.0):.2f}")
        return result

    def oos_promotion_status(self, model_id: str) -> dict[str, Any]:
        """读取同族最近 N 轮 walk-forward OOS,返回 promote 门槛判定。"""
        from services.oos_gate import check_oos_gate

        return check_oos_gate(model_id, MODELS_DIR)

    def run_oos_audit(self) -> list[dict[str, Any]]:
        """周期审计所有模型族的 OOS 门槛状态(只读,不训练)。"""
        return audit_recent_oos()

    def evaluate_and_decide(self, metrics: ModelMetrics) -> str:
        """根据真实指标决定下一步。"""
        reasons = []

        if metrics.num_trades < self.config.min_trades:
            reasons.append(f"交易次数不足({metrics.num_trades}<{self.config.min_trades})")

        if abs(metrics.max_drawdown_pct) > self.config.max_drawdown_pct:
            reasons.append(f"回撤过大({metrics.max_drawdown_pct:.1f}%>{self.config.max_drawdown_pct}%)")

        if metrics.sharpe_ratio < self.config.min_sharpe:
            reasons.append(f"夏普过低({metrics.sharpe_ratio:.2f}<{self.config.min_sharpe})")

        if reasons:
            logger.info(f"[Phase 3] 需要重训练: {'; '.join(reasons)}")
            return "retrain"

        logger.info("[Phase 3] 模型表现良好，继续使用")
        return "keep"

    def retrain(self, current_model: str) -> str:
        """用最新数据重训练新模型；仅当新模型夏普更高时才替换当前模型。"""
        logger.info(f"[Phase 4] 重训练: {current_model}")
        new_name = f"{self.config.symbol}_retrain_{int(time.time())}"
        result = self._svc.train(self._make_train_config(self.config.retrain_timesteps, new_name))
        new_model = result.model_path

        old_metrics = self._to_metrics(Path(current_model).stem, self.run_backtest(current_model))
        new_metrics = self._to_metrics(result.model_id, self.run_backtest(new_model))

        if new_metrics.sharpe_ratio > old_metrics.sharpe_ratio:
            logger.info(
                f"[Phase 4] 新模型更优 (Sharpe: {new_metrics.sharpe_ratio:.2f} > {old_metrics.sharpe_ratio:.2f})"
            )
            return new_model

        logger.info("[Phase 4] 旧模型更优，保留")
        return current_model

    def run_once(self) -> dict:
        """执行单次迭代（训练 → 回测 → 决策 → 可选重训练），返回汇总。"""
        current_model = self.run_initial_training()
        bt = self.run_backtest(current_model)
        metrics = self._to_metrics(Path(current_model).stem, bt)
        decision = self.evaluate_and_decide(metrics)

        if decision == "retrain":
            current_model = self.retrain(current_model)
            bt = self.run_backtest(current_model)

        return {"model_path": current_model, "backtest": bt, "decision": decision}

    def run_loop(self):
        """无限自动迭代循环。"""
        logger.info(f"RL 自动迭代生命周期启动: {self.config.symbol} {self.config.interval}")
        while True:
            self.run_once()
            # OOS 门槛是 promote 的读侧闸门,不需要额外训练;每轮顺带审计一次,
            # 让连续不达标的模型在日志里可见(真正的训练/重训仍在 run_once)。
            self.run_oos_audit()
            logger.info(f"等待 {self.config.check_interval_hours}h 后下次检查...")
            time.sleep(self.config.check_interval_hours * 3600)


# ---------------------------------------------------------------------------
# P4-3 每日自动闭环：选目（policy）→ 重训 → shadow 纸面对照 → 待审 / promote
#
# 双闸默认全关（设计北极星：自主率 + 保险丝）：
# - `QUANTCELL_AUTO_RETRAIN=1` 才由 core.scheduler 挂每日 job；关闭时本模块函数
#   仍可直调（手动触发 / 单测），只是没有定时入口。
# - `QUANTCELL_AUTO_PROMOTE=1` 才在 shadow + OOS gate 双绿后自动 promote；缺省
#   只写「晋升待审」记录（challenger 停在 staging），人审后再走
#   `POST /api/v1/models/{id}/promote`。
# ---------------------------------------------------------------------------

#: 训练任务轮询间隔（秒）
TRAIN_POLL_SECONDS = 1.0
#: 单族重训等待上限（小时）；超时按失败记录，不让 job 卡死调度器
TRAIN_TIMEOUT_SECONDS = 6 * 3600
#: shadow 对照结论：「challenger 需连续 N 天胜出」的目标态是 3；v1 默认 1，
#: 因为纸面对照走的是回测替代口径（见 shadow_compare 的 degraded 说明）。
DEFAULT_REQUIRED_SHADOW_WIN_DAYS = 1

_STATUS_DONE = "done"


# ---- 生命周期状态落点（shadow 台账 + 晋升待审记录） ----


def lifecycle_state_path(models_dir: str | os.PathLike[str] | None = None) -> Path:
    from services.retrain_policy import lifecycle_dir

    return lifecycle_dir(models_dir) / "lifecycle_state.json"


def load_lifecycle_state(models_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """读状态文件；缺失/损坏一律当空状态（不自愈即报错，job 才能继续）。"""
    path = lifecycle_state_path(models_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"shadow": {}, "promotions": []}
    if not isinstance(data, dict):
        return {"shadow": {}, "promotions": []}
    data.setdefault("shadow", {})
    data.setdefault("promotions", [])
    return data


def _save_lifecycle_state(state: dict[str, Any], models_dir: str | os.PathLike[str] | None = None) -> None:
    from services.retrain_policy import _write_json_atomic

    _write_json_atomic(lifecycle_state_path(models_dir), state)


def pending_promotions(models_dir: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """「晋升待审」记录（status=pending；人审通路读取，含 champ/challenger 完整证据）。"""
    return [
        r
        for r in load_lifecycle_state(models_dir).get("promotions", [])
        if isinstance(r, dict) and r.get("status") == "pending"
    ]


def _shadow_win_streak(entries: list[dict[str, Any]]) -> int:
    """连续 challenger 胜出的天数（同日多条只取最后一条）。"""
    latest_by_day: dict[str, str | None] = {}
    for entry in entries:
        day = str(entry.get("date") or "")
        winner = entry.get("winner")
        if day:
            latest_by_day[day] = winner if isinstance(winner, str) else None
    streak = 0
    for day in sorted(latest_by_day, reverse=True):
        if latest_by_day[day] != "challenger":
            break
        streak += 1
    return streak


# ---- 训练 / 对照 / 闸门 ----


def train_challenger(config: RLTrainConfig, *, timeout: float = TRAIN_TIMEOUT_SECONDS) -> dict[str, Any]:
    """提交训练并同步等待（复用 rl_task_runner 的全局并发=1 锁）。

    「同步等待」而不是另起线程：本函数只跑在调度器 worker / 手动触发里，
    等锁期间不阻塞任何请求线程；与 /train/async 共用同一把锁，避免每日重训
    和用户手动训练撞车（两条 SB3 训练并发会把 CPU 打满并互相拖慢）。
    """
    task_id = submit_train_task(config)
    deadline = time.time() + timeout
    while True:
        task = get_task(task_id)
        snapshot = task.snapshot() if task is not None else {"status": "error", "error": "训练任务丢失"}
        if snapshot["status"] in ("done", "error", "cancelled"):
            if snapshot["status"] != _STATUS_DONE:
                raise RuntimeError(f"重训任务未完成: status={snapshot['status']} error={snapshot.get('error') or '-'}")
            return snapshot
        if time.time() > deadline:
            try:
                cancel_task(task_id)
            except Exception as cancel_exc:  # 取消是尽力而为，超时本身已经要报错
                logger.error(f"重训超时后取消任务失败: {task_id}", exception=cancel_exc)
            raise TimeoutError(f"重训超时（>{timeout}s）: {task_id}")
        time.sleep(TRAIN_POLL_SECONDS)


def _train_config_from_meta(
    meta: dict[str, Any],
    *,
    family: str,
    interval: str,
    candle_type: str,
    timesteps: int,
    model_name: str,
) -> RLTrainConfig:
    """按 champion 旁车复刻训练口径，只换数据窗口（重训 = 同口径新数据）。"""
    kwargs: dict[str, Any] = {
        "algorithm": str(meta.get("algorithm") or "ppo"),
        "symbol": family,
        "interval": interval,
        "candle_type": candle_type,
        "total_timesteps": timesteps,
        "reward_type": str(meta.get("reward_type") or "pnl"),
        "model_name": model_name,
        "data_type": str(meta.get("data_type") or "kline"),
        "obs_mode": str(meta.get("obs_mode") or "features"),
        "obs_window": int(meta.get("obs_window") or 1),
    }
    reward_terms = meta.get("reward_terms")
    if isinstance(reward_terms, dict) and reward_terms:
        kwargs["reward_terms"] = reward_terms
    cost_rate = meta.get("transaction_cost")
    if isinstance(cost_rate, (int, float)) and not isinstance(cost_rate, bool):
        kwargs["cost_profile"] = CostProfile(default=float(cost_rate))
    # 派生微结构通道不落 meta 顶层的独立键，只能从 obs_features 反推：
    # obs_features = OBS_CHANNELS + extras（见 rl_service 的 meta 写入）。
    features = meta.get("obs_features")
    if kwargs["obs_mode"] == "ohlcv_window" and isinstance(features, list):
        base = {"open", "high", "low", "close", "volume"}
        extras = [str(name) for name in features if str(name) not in base]
        if extras:
            kwargs["obs_extra_channels"] = extras
    return RLTrainConfig(**kwargs)


def _registry_available() -> bool:
    try:
        from services import model_registry

        return bool(model_registry.AVAILABLE)
    except Exception:
        return False


def register_staging(model_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """把 challenger 注册进模型注册表（stage=staging，即「停留待审」）。"""
    if not _registry_available():
        return {"registered": False, "error": "axon_quant.registry 不可用"}
    try:
        from services.model_registry import ModelRegistryService

        version = ModelRegistryService(storage_path=str(Path(model_path).parent)).register_model(
            name=Path(model_path).stem,
            model_path=model_path,
            metadata=metadata,
        )
        return {"registered": True, "version": version}
    except Exception as exc:  # 注册失败不该吞掉训练/对照结论，落证据即可
        logger.error(f"challenger 注册 staging 失败: {exc}", exception=exc)
        return {"registered": False, "error": f"{type(exc).__name__}: {exc}"}


def promote_challenger(model_id: str, *, models_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """自动 promote（仅在 QUANTCELL_AUTO_PROMOTE=1 且双闸放行时调用）。"""
    from services.model_registry import ModelRegistryService
    from services.oos_gate import OosGateError

    try:
        svc = ModelRegistryService(storage_path=str(models_dir or MODELS_DIR))
        promoted = svc.promote_to_production(model_id)
        return {"promoted": bool(promoted)}
    except OosGateError as exc:  # OOS 门槛在注册表侧再兜一次（与路由 409 同一判定）
        return {"promoted": False, "oos_blocked": True, "error": str(exc)}
    except Exception as exc:
        logger.error(f"自动 promote 失败: {exc}", exception=exc)
        return {"promoted": False, "error": f"{type(exc).__name__}: {exc}"}


def shadow_compare(
    champion_path: str,
    challenger_path: str,
    *,
    symbol: str,
    interval: str,
    reward_type: str,
    svc: Any,
) -> dict[str, Any]:
    """champion vs challenger 同窗口纸面对照。

    **降级说明（如实标注）**：`axon_quant` 的 shadow oracle 是 Rust 内部能力
    （`axon-worker::shadow::run_shadow`，`crates/axon-worker/src/shadow.rs:157`），
    它比对的是「legacy BacktestRunner vs 新 Kernel」两条**引擎路径**，且未暴露
    Python 绑定（`crates/axon-worker/src/python.rs` 无 `shadow` 导出）——
    既不是 champion/challenger 模型对照，也无法 Python 直调。故这里降级为
    「同一数据源的 trading_env 回测结果对照」：`run_backtest` 对同一 symbol /
    interval 取同一份数据，两条回测窗口一致，差异只来自模型本身。
    升级路径：Rust 侧把 `run_shadow` 或「同窗口双模型」导出成 Python API 后，
    只需替换本函数实现，返回结构（winner/engine/degraded）不变。
    """
    result: dict[str, Any] = {
        "engine": "trading_env",
        "mode": "backtest_compare",
        "degraded": True,
        "degraded_reason": "axon_quant shadow oracle 仅内核内部且非模型对照，回退 trading_env 同窗口回测",
        "symbol": symbol,
        "interval": interval,
    }
    metrics: dict[str, dict[str, Any]] = {}
    for role, path in (("champion", champion_path), ("challenger", challenger_path)):
        try:
            bt = svc.run_backtest(path, symbol, interval, reward_type=reward_type)
        except Exception as exc:
            logger.error(f"shadow 对照 {role} 回测失败: {exc}", exception=exc)
            return {**result, "winner": None, "error": f"{role} 回测失败: {type(exc).__name__}: {exc}"}
        metrics[role] = {
            "model_id": Path(path).stem,
            "sharpe_ratio": bt.get("sharpe_ratio"),
            "total_pnl": bt.get("total_pnl"),
            "max_drawdown_pct": bt.get("max_drawdown_pct"),
            "num_trades": bt.get("num_trades"),
            "engine": bt.get("engine", "trading_env"),
        }
    champion, challenger = metrics["champion"], metrics["challenger"]
    winner: str | None = None
    if champion["sharpe_ratio"] is not None and challenger["sharpe_ratio"] is not None:
        champ_key = (float(champion["sharpe_ratio"]), float(champion["total_pnl"] or 0.0))
        chal_key = (float(challenger["sharpe_ratio"]), float(challenger["total_pnl"] or 0.0))
        if chal_key > champ_key:
            winner = "challenger"
        elif chal_key < champ_key:
            winner = "champion"
    return {**result, "champion": champion, "challenger": challenger, "winner": winner}


# ---- 单日闭环 ----


@dataclass
class AutoCycleConfig:
    """自动闭环参数（默认值即生产默认；测试与运维按需覆写）。"""

    #: shadow 连续胜出天数门槛（目标态 3；v1 默认 1，见 DEFAULT_ 注释）
    required_shadow_win_days: int = DEFAULT_REQUIRED_SHADOW_WIN_DAYS
    retrain_timesteps: int = 10_000
    interval: str = "1h"
    candle_type: str = "spot"
    policy: RetrainPolicy | None = None
    models_dir: Path | None = None
    #: None = 读 QUANTCELL_AUTO_PROMOTE；显式布尔给单测/手动触发覆写
    auto_promote: bool | None = None
    train_timeout_seconds: float = TRAIN_TIMEOUT_SECONDS


def _resolve_auto_promote(config: AutoCycleConfig) -> bool:
    return auto_promote_enabled() if config.auto_promote is None else bool(config.auto_promote)


def _retrain_one(
    candidate: RetrainCandidate,
    *,
    config: AutoCycleConfig,
    models_dir: Path,
    now: datetime,
    state: dict[str, Any],
    svc: Any,
) -> dict[str, Any]:
    """单族：重训 → shadow 对照 → 闸门判定 → 待审 / promote。

    注意：所有闸门判定都在训练成功之后，训练失败只记 error（冷却/日上限仍生效，
    防止同一族一天内反复重训烧 CPU）。
    """
    from services.oos_gate import check_oos_gate
    from services.rl_service import load_rl_meta

    family = candidate.family
    champion_path = candidate.model_path or ""
    meta = load_rl_meta(champion_path)
    model_name = f"{family}_retrain_{int(now.timestamp())}"
    train_config = _train_config_from_meta(
        meta,
        family=family,
        interval=config.interval,
        candle_type=config.candle_type,
        timesteps=config.retrain_timesteps,
        model_name=model_name,
    )
    logger.info(f"[AutoRetrain] {family} 开始重训: reason={candidate.reason} model_name={model_name}")
    snapshot = train_challenger(train_config, timeout=config.train_timeout_seconds)
    challenger_path = str(snapshot.get("model_path") or "")
    if not challenger_path:
        raise RuntimeError("训练任务完成但快照缺 model_path")
    challenger_id = Path(challenger_path).stem
    record_retrain(family, model_id=challenger_id, status="trained", at=now, models_dir=models_dir)

    shadow = shadow_compare(
        champion_path,
        challenger_path,
        symbol=family,
        interval=config.interval,
        reward_type=str(meta.get("reward_type") or "pnl"),
        svc=svc,
    )
    entry = {
        "date": now.date().isoformat(),
        "at": now.isoformat(),
        "winner": shadow.get("winner"),
        "engine": shadow.get("engine"),
        "degraded": shadow.get("degraded"),
        "champion": shadow.get("champion"),
        "challenger": shadow.get("challenger"),
        "error": shadow.get("error"),
    }
    family_entries = state.setdefault("shadow", {}).setdefault(family, [])
    family_entries.append(entry)
    _save_lifecycle_state(state, models_dir)

    streak = _shadow_win_streak(family_entries)
    result: dict[str, Any] = {
        "family": family,
        "reason": candidate.reason,
        "champion": candidate.model_id,
        "challenger": challenger_id,
        "challenger_path": challenger_path,
        "shadow": {"winner": shadow.get("winner"), "streak_days": streak, "degraded": shadow.get("degraded")},
        "status": "shadow_running",
    }

    gate = check_oos_gate(challenger_id, models_dir)
    result["oos"] = {"blocked": gate["blocked"], "reason": gate.get("reason"), "rounds_checked": gate["rounds_checked"]}
    if gate["blocked"]:
        result["status"] = "oos_blocked"
        return result
    if streak < max(1, int(config.required_shadow_win_days)):
        result["status"] = "shadow_running"
        return result

    evidence = {
        "generated_at": now.isoformat(),
        "family": family,
        "champion": shadow.get("champion"),
        "challenger": shadow.get("challenger"),
        "shadow": {"streak_days": streak, "required_days": config.required_shadow_win_days, "history": family_entries},
        "oos_gate": gate,
        "retrain_reason": candidate.reason,
        "retrain_evidence": candidate.evidence,
    }
    registry = register_staging(challenger_path, metadata={"source": "auto_retrain", **evidence})
    record = {
        "kind": "promotion_pending",
        "family": family,
        "challenger_id": challenger_id,
        "champion_id": candidate.model_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "evidence": evidence,
        "registry": registry,
    }
    if _resolve_auto_promote(config):
        outcome = promote_challenger(challenger_id, models_dir=models_dir)
        record["status"] = "auto_promoted" if outcome.get("promoted") else "auto_promote_failed"
        record["promote"] = outcome
        result["status"] = record["status"]
    else:
        result["status"] = "pending_review"
    state.setdefault("promotions", []).append(record)
    _save_lifecycle_state(state, models_dir)
    result["promotion"] = {"status": record["status"], "registry": registry}
    return result


def run_auto_retrain_cycle(
    config: AutoCycleConfig | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """执行一次每日闭环：选目 → 逐族重训/对照/闸门 → 汇总。

    **不检查 QUANTCELL_AUTO_RETRAIN**：总闸只决定调度器是否挂 job，函数保持
    可直调（手动触发 / 单测）。单族失败只记 error，不中断其它族；job 级
    try/except 在 `core.scheduler`。重复调用天然幂等（同族当日已重训会跳过）。
    """
    config = config or AutoCycleConfig()
    now = now or datetime.now(UTC)
    models_dir = Path(config.models_dir or MODELS_DIR)
    policy = config.policy or RetrainPolicy.from_env()
    state = load_lifecycle_state(models_dir)

    candidates = select_retrain_candidates(models_dir, now=now, policy=policy)
    summary: dict[str, Any] = {
        "checked_at": now.isoformat(),
        "auto_promote": _resolve_auto_promote(config),
        "policy": {
            "max_per_day": policy.max_per_day,
            "cooldown_days": policy.cooldown_days,
            "stale_days": policy.stale_days,
            "oos_decay_ratio": policy.oos_decay_ratio,
        },
        "candidates": [c.to_dict() for c in candidates],
        "results": [],
    }
    if not candidates:
        logger.info("[AutoRetrain] 今日无重训候选")
        return summary

    svc = RLService()
    for candidate in candidates:
        try:
            summary["results"].append(
                _retrain_one(candidate, config=config, models_dir=models_dir, now=now, state=state, svc=svc)
            )
        except Exception as exc:  # 单族失败隔离：其它族继续，job 不因此中断
            logger.exception(f"[AutoRetrain] {candidate.family} 重训闭环失败")
            record_retrain(
                candidate.family,
                model_id=None,
                status=f"error:{type(exc).__name__}",
                at=now,
                models_dir=models_dir,
            )
            summary["results"].append(
                {"family": candidate.family, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
    return summary


if __name__ == "__main__":
    from typing import Annotated

    import typer

    app = typer.Typer(help="RL 自动迭代生命周期", add_completion=False)

    @app.command()
    def run(
        symbol: Annotated[str, typer.Option("--symbol", "-s")] = "BTCUSDT",
        interval: Annotated[str, typer.Option("--interval", "-i")] = "1h",
        algorithm: Annotated[str, typer.Option("--algorithm", "-a")] = "ppo",
        train_steps: Annotated[int, typer.Option("--train-steps")] = 30000,
        retrain_steps: Annotated[int, typer.Option("--retrain-steps")] = 10000,
        check_hours: Annotated[int, typer.Option("--check-hours")] = 24,
    ):
        """运行生命周期；--check-hours 0 表示只跑一次。"""
        config = LifecycleConfig(
            symbol=symbol,
            interval=interval,
            algorithm=algorithm,
            train_timesteps=train_steps,
            retrain_timesteps=retrain_steps,
            check_interval_hours=check_hours,
        )
        lifecycle = RLLifecycle(config)
        if check_hours > 0:
            lifecycle.run_loop()
        else:
            lifecycle.run_once()

    app()
