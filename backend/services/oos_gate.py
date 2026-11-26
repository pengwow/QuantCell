"""OOS 晋升门槛 — 最近 N 轮 walk-forward OOS 连续不达标则闸住 promote。

数据来源是训练产物旁车 `data/models/*.meta.json`(rl_service 落盘):
`walk_forward.oos` 优先(本轮新增),其次顶层 `oos`(兼容既有报告),
最后回退 `walk_forward.aggregate.mean`(旧产物只有汇总)。只读旁车,
不依赖注册表 metadata,所以 promote 端点和 lifecycle 周期审计共用同一判定。

口径刻意保守:只有"最近 N 轮都能评估且全部不达标"才拦,少于 N 轮或指标缺失
一律放行 —— 门槛用来拦连续跑坏的模型,不是拿来封死冷启动/旧数据。

ponytail: 阈值是模块常量 + 调用方关键字覆盖,不引入配置系统;轮次按
meta.created_at 倒序,同一 `model_family` 视为同一模型(见 `model_family`)。
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 默认宽松门槛:非负夏普 + 非负收益;只拦明显跑坏的模型
OOS_MIN_SHARPE = 0.0
OOS_MIN_RETURN_PCT = 0.0
OOS_REQUIRED_FAILED_ROUNDS = 2

_UNIX_TS_SUFFIX = re.compile(r"_\d{10,}$")
_ALGO_SUFFIX = re.compile(r"_(ppo|sac|dqn)$")
_VERSION_SUFFIX = re.compile(r"_v\d+$")
_RETRAIN_SUFFIX = re.compile(r"_retrain(?:ed)?$")
_RETRAIN_TS_SUFFIX = re.compile(r"_retrain(?:ed)?_\d{10,}$")


def model_family(model_id: str) -> str:
    """训练产物名 → 稳定模型族键。

    `BTCUSDT_v1_ppo_1700000000` / `BTCUSDT_retrain_..._ppo_...` 都归到
    `BTCUSDT`,让生命周期多轮重训练的 OOS 能串成连续轮次;无法归约时原样返回。
    先剥时间戳(可能被重训练名叠两层),再剥算法/版本/retrain 标记。
    各模式交替应用直到名字稳定,处理 `retrain_ts_ppo_ts` 这类多段后缀。
    """
    name = str(model_id or "")
    previous = None
    while name and name != previous:
        previous = name
        name = _UNIX_TS_SUFFIX.sub("", name)
        name = _RETRAIN_TS_SUFFIX.sub("", name)
        name = _ALGO_SUFFIX.sub("", name)
        name = _RETRAIN_SUFFIX.sub("", name)
        name = _VERSION_SUFFIX.sub("", name)
    return name or str(model_id or "")


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def round_passes(
    sharpe_ratio: float | None,
    total_return_pct: float | None,
    *,
    min_sharpe: float = OOS_MIN_SHARPE,
    min_return_pct: float = OOS_MIN_RETURN_PCT,
) -> bool | None:
    """单轮 OOS 是否达标;指标缺失返回 None(不可评估,不参与拦停)。"""
    sharpe = _as_float(sharpe_ratio)
    ret = _as_float(total_return_pct)
    if sharpe is None or ret is None:
        return None
    return sharpe >= min_sharpe and ret >= min_return_pct


def _metrics_from_meta(meta: dict[str, Any]) -> tuple[dict[str, Any], str] | tuple[None, str]:
    """按优先级从 meta 取 OOS 指标字典。"""
    for container_name, container in (
        ("oos", meta.get("oos")),
        ("walk_forward.oos", (meta.get("walk_forward") or {}).get("oos")),
    ):
        if isinstance(container, dict) and (
            _as_float(container.get("sharpe_ratio")) is not None
            or _as_float(container.get("total_return_pct")) is not None
        ):
            return container, container_name

    walk_forward = meta.get("walk_forward")
    aggregate = walk_forward.get("aggregate") if isinstance(walk_forward, dict) else None
    mean = aggregate.get("mean") if isinstance(aggregate, dict) else None
    if isinstance(mean, dict) and (
        _as_float(mean.get("sharpe_ratio")) is not None or _as_float(mean.get("total_return_pct")) is not None
    ):
        return mean, "walk_forward.aggregate.mean"
    return None, ""


def _round_from_meta(meta: dict[str, Any], fallback_id: str, mtime: float) -> dict[str, Any] | None:
    metrics, source = _metrics_from_meta(meta)
    if metrics is None:
        return None
    return {
        "model_id": str(meta.get("model_id") or fallback_id),
        "created_at": str(meta.get("created_at") or ""),
        "trained_at_mtime": mtime,
        "sharpe_ratio": _as_float(metrics.get("sharpe_ratio")),
        "total_return_pct": _as_float(metrics.get("total_return_pct")),
        "total_pnl": _as_float(metrics.get("total_pnl")),
        "n_valid_folds": metrics.get("n_valid_folds"),
        "source": source,
    }


def load_oos_rounds(models_dir: str | os.PathLike[str], model_id: str) -> list[dict[str, Any]]:
    """读取 `models_dir` 下与 `model_id` 同族的全部 OOS 轮次,按时间倒序。"""
    family = model_family(model_id)
    rounds: list[dict[str, Any]] = []
    for meta_path in glob.glob(os.path.join(str(models_dir), "*.meta.json")):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if not isinstance(meta, dict):
                continue
            stem = os.path.basename(meta_path)[: -len(".meta.json")]
            if model_family(str(meta.get("model_id") or stem)) != family:
                continue
            mtime = os.path.getmtime(meta_path)
            item = _round_from_meta(meta, stem, mtime)
            if item is not None:
                rounds.append(item)
        except (OSError, ValueError, TypeError):
            # 旁车损坏不该让 promote 500:跳过并在日志留痕
            logger.warning("跳过无法解析的模型旁车: %s", meta_path, exc_info=False)
    rounds.sort(key=lambda r: (r["created_at"], r["trained_at_mtime"]), reverse=True)
    return rounds


def _check_rounds(
    model_id: str,
    rounds: list[dict[str, Any]],
    *,
    min_sharpe: float,
    min_return_pct: float,
    required_rounds: int,
) -> dict[str, Any]:
    for r in rounds:
        r["passed"] = round_passes(
            r["sharpe_ratio"],
            r["total_return_pct"],
            min_sharpe=min_sharpe,
            min_return_pct=min_return_pct,
        )
    evaluable = [r for r in rounds if r["passed"] is not None]
    latest = evaluable[:required_rounds]
    failed = [r for r in latest if r["passed"] is False]
    blocked = len(latest) >= required_rounds and len(failed) >= required_rounds

    result: dict[str, Any] = {
        "model_id": str(model_id),
        "family": model_family(model_id),
        "blocked": blocked,
        "rounds_checked": len(latest),
        "required_rounds": required_rounds,
        "rounds": latest,
        "failed_rounds": failed,
        "thresholds": {"min_sharpe": min_sharpe, "min_return_pct": min_return_pct},
    }
    if blocked:
        result["reason"] = f"连续 {len(failed)} 轮 walk-forward OOS 不达标，拒绝晋升 {model_id}"
    elif len(latest) < required_rounds:
        result["reason"] = f"可评估 OOS 轮次不足({len(latest)}/{required_rounds})，放行"
    elif failed:
        result["reason"] = f"最近 {len(latest)} 轮中仅 {len(failed)} 轮 OOS 不达标，未构成连续失败，放行"
    else:
        result["reason"] = f"最近 {len(latest)} 轮 OOS 均达标，放行"
    return result


def check_oos_gate(
    model_id: str,
    models_dir: str | os.PathLike[str],
    *,
    min_sharpe: float = OOS_MIN_SHARPE,
    min_return_pct: float = OOS_MIN_RETURN_PCT,
    required_rounds: int = OOS_REQUIRED_FAILED_ROUNDS,
) -> dict[str, Any]:
    """判定 `model_id` 是否被连续 N 轮 OOS 不达标闸住。"""
    return _check_rounds(
        model_id,
        load_oos_rounds(models_dir, model_id),
        min_sharpe=min_sharpe,
        min_return_pct=min_return_pct,
        required_rounds=max(1, int(required_rounds)),
    )


def evidence_text(result: dict[str, Any]) -> str:
    """把拦停证据压成一行,给 409 detail / 日志用。"""
    parts = []
    for r in result.get("failed_rounds") or []:
        parts.append(
            f"{r['model_id']}: sharpe={r['sharpe_ratio']}, return%={r['total_return_pct']}, created_at={r['created_at'] or '-'}"
        )
    return "; ".join(parts)


class OosGateError(Exception):
    """promote 被 OOS 门槛拒绝;路由层据此回 409。"""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        detail = result.get("reason") or "OOS 门槛拒绝"
        evidence = evidence_text(result)
        super().__init__(f"{detail}；证据: {evidence}" if evidence else detail)


def audit_oos_gate(models_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """扫描全部模型族并返回 gate 判定,供 lifecycle 周期审计。"""
    families: set[str] = set()
    for meta_path in glob.glob(os.path.join(str(models_dir), "*.meta.json")):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            stem = os.path.basename(meta_path)[: -len(".meta.json")]
            families.add(model_family(str(meta.get("model_id") or stem) if isinstance(meta, dict) else stem))
        except (OSError, ValueError, TypeError):
            continue
    return [check_oos_gate(family, models_dir) for family in sorted(families)]
