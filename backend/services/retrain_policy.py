"""重训策略：每日收盘后挑选「该重训」的模型族（纯判定，不训练）。

判定输入全部复用既有落点，不新增数据源：

- **OOS 衰减**：`data/models/*.meta.json` 里的 `walk_forward.aggregate.mean`
  （训练期/walk-forward 均值夏普）对比 `walk_forward.oos`（OOS 夏普）。
  OOS 相对训练期跌破 `oos_decay_ratio` → 该族衰减（取最近 2 轮均值）。
- **数据新鲜度**：meta `created_at`（缺失回退旁车 mtime）距今 > `stale_days`。
- **冷却 / 日上限 / 幂等**：`lifecycle/retrain_history.json`（本模块读写）。
  同一族冷却期内跳过、当天已重训跳过、单日重训族数不超过 `max_per_day`。

设计取舍（改前先读）：

- 不做配置系统：常量 + `RetrainPolicy` 覆写，运营侧只留 4 个环境变量旋钮。
- 选目（读）与记录（写）分开：训练结束后由 `rl.lifecycle` 调 `record_retrain`，
  便于单测只测判定、不碰训练。
- 族名即 symbol：训练产物命名约定 `<SYMBOL>_...`（见 `oos_gate.model_family`），
  重训时以族名当 symbol。族名不合约定时重训会取不到数据 → 循环内单族异常隔离。
- ponytail: 判据是「读旁车的最新一轮」，不做跨族优先级排序/排队模型；
  天花板 = 每日最多 2 族、且衰减判据只看夏普均值。升级路径是把候选打分
  （衰减幅度 × 数据年龄）交给调度器挑 top-N，本模块签名不变。
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from services.oos_gate import model_family
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# ---- 默认常量（环境变量可覆盖，见 RetrainPolicy.from_env） ----
MAX_RETRAINS_PER_DAY = 2
COOLDOWN_DAYS = 3.0
STALE_DAYS = 14.0
OOS_DECAY_RATIO = 0.5
#: 参与衰减判定的最近轮次（与 OOS gate 的 required_rounds 口径一致）
DECAY_ROUNDS = 2

_ENV_KEYS = {
    "max_per_day": "QUANTCELL_RETRAIN_MAX_PER_DAY",
    "cooldown_days": "QUANTCELL_RETRAIN_COOLDOWN_DAYS",
    "stale_days": "QUANTCELL_RETRAIN_STALE_DAYS",
    "oos_decay_ratio": "QUANTCELL_RETRAIN_OOS_DECAY_RATIO",
}

REASON_OOS_DECAY = "oos_decay"
REASON_STALE = "data_stale"

#: 自动重训闭环总闸（调度器据此决定是否挂每日 job；函数本身不检查，便于手动触发）
AUTO_RETRAIN_ENV = "QUANTCELL_AUTO_RETRAIN"
#: 第二道闸：shadow + OOS gate 双绿后是否自动 promote（缺省只写晋升待审）
AUTO_PROMOTE_ENV = "QUANTCELL_AUTO_PROMOTE"


def env_flag(name: str, default: bool = False) -> bool:
    """`1/true/yes/on` 视为开启；空值回落 default。"""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def auto_retrain_enabled() -> bool:
    return env_flag(AUTO_RETRAIN_ENV)


def auto_promote_enabled() -> bool:
    return env_flag(AUTO_PROMOTE_ENV)


def lifecycle_dir(models_dir: str | os.PathLike[str] | None = None) -> Path:
    """生命周期状态目录：`QUANTCELL_RL_LIFECYCLE_DIR` > `<models_dir>/lifecycle`。"""
    override = os.environ.get("QUANTCELL_RL_LIFECYCLE_DIR", "").strip()
    if override:
        return Path(override)
    if models_dir is None:
        from services.rl_service import MODELS_DIR

        models_dir = MODELS_DIR
    return Path(models_dir) / "lifecycle"


def models_dir_default() -> Path:
    """训练产物目录（延迟 import，避免本模块被选中时拉起训练栈）。"""
    from services.rl_service import MODELS_DIR

    return Path(MODELS_DIR)


@dataclass(frozen=True)
class RetrainPolicy:
    """重训判定参数。全部可由环境变量覆盖，便于运维不重启改旋钮。"""

    max_per_day: int = MAX_RETRAINS_PER_DAY
    cooldown_days: float = COOLDOWN_DAYS
    stale_days: float = STALE_DAYS
    oos_decay_ratio: float = OOS_DECAY_RATIO

    @classmethod
    def from_env(cls) -> RetrainPolicy:
        """环境变量覆盖（非法值忽略并告警，回落到默认，绝不让调度挂掉）。"""
        values: dict[str, Any] = {
            "max_per_day": cls.max_per_day,
            "cooldown_days": cls.cooldown_days,
            "stale_days": cls.stale_days,
            "oos_decay_ratio": cls.oos_decay_ratio,
        }
        for key, env_name in _ENV_KEYS.items():
            raw = os.environ.get(env_name, "").strip()
            if not raw:
                continue
            try:
                values[key] = int(raw) if key == "max_per_day" else float(raw)
            except ValueError:
                logger.warning(f"忽略非法环境变量 {env_name}={raw!r}，沿用默认 {values[key]}")
        if values["max_per_day"] < 1:
            values["max_per_day"] = 1
        return cls(**values)


@dataclass
class RetrainCandidate:
    """一个待重训模型族及其判定证据（证据原样进 promote 待审记录）。"""

    family: str
    model_id: str
    model_path: str | None
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "model_id": self.model_id,
            "model_path": self.model_path,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


# ---------------------------------------------------------------------------
# 旁车快照：每族取最新一轮，附带最近 N 轮的 OOS / 训练期夏普均值
# ---------------------------------------------------------------------------


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _parse_created_at(meta: dict[str, Any], mtime: float) -> datetime:
    """meta.created_at（本地 ISO）→ aware datetime；缺失/损坏回退旁车 mtime。"""
    raw = str(meta.get("created_at") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo else parsed.astimezone()
        except ValueError:
            pass
    return datetime.fromtimestamp(mtime).astimezone()


def _metrics_of(meta: dict[str, Any]) -> tuple[float | None, float | None]:
    """(训练期/walk-forward 均值夏普, OOS 夏普)；缺失返回 None。"""
    walk_forward = meta.get("walk_forward")
    wf = walk_forward if isinstance(walk_forward, dict) else {}
    aggregate = wf.get("aggregate")
    mean = aggregate.get("mean") if isinstance(aggregate, dict) else None
    train_sharpe = _as_float(mean.get("sharpe_ratio")) if isinstance(mean, dict) else None

    oos = meta.get("oos")
    if not isinstance(oos, dict):
        oos = wf.get("oos")
    # 旧产物只有 aggregate、没有 oos 容器 → oos_sharpe=None，不可判衰减（只能看数据新鲜度）
    oos_sharpe = _as_float(oos.get("sharpe_ratio")) if isinstance(oos, dict) else None
    return train_sharpe, oos_sharpe


def family_snapshots(
    models_dir: str | os.PathLike[str] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """扫描旁车，返回 `family -> 快照`：最新一轮 + 最近 DECAY_ROUNDS 轮均值。"""
    base = Path(models_dir) if models_dir is not None else models_dir_default()
    now = now or datetime.now(UTC)
    by_family: dict[str, list[dict[str, Any]]] = {}
    for meta_path in glob.glob(os.path.join(str(base), "*.meta.json")):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if not isinstance(meta, dict):
                continue
            mtime = os.path.getmtime(meta_path)
        except OSError, ValueError, TypeError:
            logger.warning(f"跳过无法解析的模型旁车: {meta_path}")
            continue
        stem = os.path.basename(meta_path)[: -len(".meta.json")]
        # 旁车两种命名并存：legacy `<stem>.meta.json` 与 rl_service 产物的
        # `<stem>.zip.meta.json`——统一归约到 zip 实名，否则 zip_path 拼成
        # `<stem>.zip.zip` 恒缺失，真实目录（一律 .zip.meta.json）上永远选不出候选。
        model_stem = stem.removesuffix(".zip")
        family = model_family(str(meta.get("model_id") or model_stem))
        train_sharpe, oos_sharpe = _metrics_of(meta)
        zip_path = os.path.join(str(base), f"{model_stem}.zip")
        by_family.setdefault(family, []).append(
            {
                "model_id": model_stem,
                "model_path": zip_path if os.path.isfile(zip_path) else None,
                "created_at": _parse_created_at(meta, mtime),
                "train_sharpe": train_sharpe,
                "oos_sharpe": oos_sharpe,
            }
        )

    snapshots: dict[str, dict[str, Any]] = {}
    for family, rounds in by_family.items():
        rounds.sort(key=lambda r: r["created_at"], reverse=True)
        latest = rounds[0]
        recent = rounds[:DECAY_ROUNDS]
        age_days = max(0.0, (now - latest["created_at"]).total_seconds() / 86400.0)
        snapshots[family] = {
            "family": family,
            "model_id": latest["model_id"],
            "model_path": latest["model_path"],
            "age_days": round(age_days, 2),
            "train_sharpe": _mean([r["train_sharpe"] for r in recent if r["train_sharpe"] is not None]),
            "oos_sharpe": _mean([r["oos_sharpe"] for r in recent if r["oos_sharpe"] is not None]),
            "rounds_considered": len(recent),
        }
    return snapshots


# ---------------------------------------------------------------------------
# 重训历史（冷却 / 日上限 / 同日幂等）
# ---------------------------------------------------------------------------


def history_path(models_dir: str | os.PathLike[str] | None = None) -> Path:
    return lifecycle_dir(models_dir) / "retrain_history.json"


def load_retrain_history(
    models_dir: str | os.PathLike[str] | None = None,
    *,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """读历史；文件缺失/损坏一律当空历史（调度不该因脏文件停摆）。"""
    target = path or history_path(models_dir)
    try:
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
    except OSError, ValueError, TypeError:
        return []
    records = data.get("records") if isinstance(data, dict) else data
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


def _write_json_atomic(target: Path, payload: Any) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def record_retrain(
    family: str,
    *,
    model_id: str | None = None,
    status: str = "trained",
    at: datetime | None = None,
    models_dir: str | os.PathLike[str] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """追加一条重训记录（训练结束后调用；失败也记，避免同一天反复重试同族）。"""
    moment = at or datetime.now(UTC)
    record = {
        "family": family,
        "day": moment.date().isoformat(),
        "at": moment.isoformat(),
        "model_id": model_id,
        "status": status,
    }
    target = path or history_path(models_dir)
    records = load_retrain_history(path=target)
    records.append(record)
    _write_json_atomic(target, {"records": records})
    return record


def _last_retrain_at(records: list[dict[str, Any]], family: str) -> datetime | None:
    last: datetime | None = None
    for record in records:
        if record.get("family") != family:
            continue
        try:
            parsed = datetime.fromisoformat(str(record.get("at")))
        except ValueError:
            continue
        parsed = parsed if parsed.tzinfo else parsed.astimezone()
        if last is None or parsed > last:
            last = parsed
    return last


def retrained_today(records: list[dict[str, Any]], family: str, day: date) -> bool:
    return any(r.get("family") == family and r.get("day") == day.isoformat() for r in records)


# ---------------------------------------------------------------------------
# 选目
# ---------------------------------------------------------------------------


def _decayed(snapshot: dict[str, Any], ratio: float) -> bool:
    oos, train = snapshot.get("oos_sharpe"), snapshot.get("train_sharpe")
    if oos is None or train is None or train <= 0:
        return False
    return oos < train * ratio


def select_retrain_candidates(
    models_dir: str | os.PathLike[str] | None = None,
    *,
    now: datetime | None = None,
    policy: RetrainPolicy | None = None,
    history: list[dict[str, Any]] | None = None,
) -> list[RetrainCandidate]:
    """挑出当日该重训的族（OOS 衰减优先，其次数据陈旧），已按上限截断。

    过滤顺序 = 判定 → 冷却 → 同日幂等 → 日上限。任何一步失败只跳过该族，
    不抛异常（调度侧只关心「今天要重训谁」）。
    """
    policy = policy or RetrainPolicy.from_env()
    now = now or datetime.now(UTC)
    records = history if history is not None else load_retrain_history(models_dir)
    day = now.date()

    scored: list[tuple[int, float, RetrainCandidate]] = []
    for family, snapshot in family_snapshots(models_dir, now=now).items():
        if not snapshot.get("model_path"):
            logger.info(f"跳过模型族 {family}：产物文件缺失，无法做 champion 对照")
            continue

        reason: str | None = None
        evidence: dict[str, Any] = {
            "age_days": snapshot["age_days"],
            "train_sharpe": snapshot["train_sharpe"],
            "oos_sharpe": snapshot["oos_sharpe"],
            "oos_decay_ratio": policy.oos_decay_ratio,
            "stale_days": policy.stale_days,
        }
        if _decayed(snapshot, policy.oos_decay_ratio):
            reason = REASON_OOS_DECAY
        elif snapshot["age_days"] > policy.stale_days:
            reason = REASON_STALE
        if reason is None:
            continue

        if retrained_today(records, family, day):
            logger.info(f"跳过模型族 {family}：当日已重训过（幂等）")
            continue
        last = _last_retrain_at(records, family)
        if last is not None and (now - last) < timedelta(days=policy.cooldown_days):
            logger.info(f"跳过模型族 {family}：冷却期内（上次 {last.isoformat(timespec='seconds')}）")
            continue

        candidate = RetrainCandidate(
            family=family,
            model_id=snapshot["model_id"],
            model_path=snapshot["model_path"],
            reason=reason,
            evidence=evidence,
        )
        scored.append((0 if reason == REASON_OOS_DECAY else 1, -snapshot["age_days"], candidate))

    scored.sort(key=lambda item: (item[0], item[1]))
    selected = [candidate for _, _, candidate in scored[: policy.max_per_day]]
    if len(scored) > len(selected):
        logger.info(f"重训选目 {len(selected)}/{len(scored)}：触及单日上限 {policy.max_per_day}")
    return selected
