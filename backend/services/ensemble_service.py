"""EnsembleService — 模型集成服务(方案 A:创建期 meta 校验 + records 落盘 + Python 聚合冒烟)。

聚合逻辑在 services.ensemble_aggregator(纯函数),本模块不再构造 Rust
EnsembleManager 投票组件;真实信号路径统一从 load_ensemble_spec 取成员 spec。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from gymnasium import spaces

from services.ensemble_aggregator import BUY_RATIO_EPS, aggregate_ratios, member_ratio_predict_fn
from services.rl_service import MODELS_DIR, RLService, rl_meta_path  # 单一事实源,严禁在本模块重新定义(spec §8)
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 集成元数据落盘:与 MODELS_DIR 同级(backend/data/ensembles.json)
ENSEMBLES_STORE = MODELS_DIR.parent / "ensembles.json"


def _resolve_sb3_zip(entry: str) -> Path | None:
    """判断输入是否指向 SB3 zip:裸 stem(无路径分隔符)或 {stem}.zip,
    且 MODELS_DIR 下存在同名 zip 时返回该路径;否则 None(集成通路直接拒绝)。
    """
    if "/" in entry or "\\" in entry:
        return None
    stem = Path(entry).stem if entry.endswith(".zip") else entry
    zip_path = MODELS_DIR / f"{stem}.zip"
    return zip_path if zip_path.exists() else None


@dataclass
class PredictMemberSpecs:
    """load_ensemble_spec 的产物:成员 ratio predict_fn 列表 + 第一成员 meta。"""

    member_predict_fns: list[Any]  # MemberPredictFn: obs(list[float]) -> float | None
    meta: dict[str, Any]  # 第一成员(基准)obs 规格元数据
    model_id: str  # ensemble_id
    representative_path: str  # 第一成员 zip 路径(stats 缺失时告警定位用)


def _resolved_member_paths(model_paths: list[str]) -> list[tuple[str, Path]]:
    """成员路径 → SB3 zip。pickle 绝对路径在集成通路被拒(无 meta 无法做一致性校验)。"""
    resolved: list[tuple[str, Path]] = []
    for p in model_paths:
        zip_path = _resolve_sb3_zip(p)
        if zip_path is None:
            raise ValueError(f"集成员 {p} 无法解析为模型目录下的 SB3 zip,集成仅支持 {MODELS_DIR} 下的已训练模型")
        resolved.append((Path(p).name.removesuffix(".zip"), zip_path))
    return resolved


def _validated_member_metas(model_paths: list[str]) -> list[tuple[str, Path, dict[str, Any]]]:
    """解析成员并做 obs 规格一致性校验(spec §4.2):第一成员为基准,差异成员明细报错。"""
    members = _resolved_member_paths(model_paths)
    if not members:
        raise ValueError("集成至少需要 1 个成员")
    validated: list[tuple[str, Path, dict[str, Any]]] = []
    base_meta: dict[str, Any] | None = None
    for stem, zip_path in members:
        meta_path = rl_meta_path(zip_path)
        if not meta_path.exists():
            raise ValueError(f"成员 {stem} 缺少 obs 规格元数据({meta_path.name}),无法加入集成")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if base_meta is None:
            base_meta = meta
            validated.append((stem, zip_path, meta))
            continue
        diffs = [key for key in ("spec_version", "window_size", "features") if meta.get(key) != base_meta.get(key)]
        if diffs:
            raise ValueError(f"成员 {stem} 与基准成员 obs 规格不一致: {', '.join(diffs)}")
        validated.append((stem, zip_path, meta))
    return validated


def _feature_names(raw: list[Any]) -> list[str]:
    """meta["features"] → 有序特征名列表。

    真实落盘口径(rl_service.KERNEL_FEATURES / 训练写入的旁车 meta)是特征定义
    dict 列表:{"name", "source", "normalizer", "clip_range"},名字取 item["name"];
    历史口径是裸字符串名。两种形态都兼容,无名/空名元素跳过。
    """
    names: list[str] = []
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else item
        if name:
            names.append(str(name))
    return names


def load_ensemble_spec(ensemble_id: str, *, spec_version: str | None = None) -> PredictMemberSpecs:
    """services 层公共入口:ensemble_id → 校验后可运行的成员 spec。

    paper/live(worker 层 _load_rl_spec)与回测(RLService._run_kernel_backtest)共用,
    保证校验与加载单一事实源。ensemble 不存在 / 成员损坏 / meta 漂移 均 ValueError。
    spec_version 非空时额外校验基准成员 spec_version 与期望一致(内核口径)。
    """
    svc = get_ensemble_service()
    record = svc._records.get(ensemble_id)
    if record is None:
        raise ValueError(f"集成 {ensemble_id} 不存在")
    validated = _validated_member_metas(list(record.get("model_paths") or []))
    _base_stem, base_path, base_meta = validated[0]
    if spec_version is not None and base_meta.get("spec_version") != spec_version:
        raise ValueError(
            f"集成 {ensemble_id} 基准成员 spec_version={base_meta.get('spec_version')!r} 与期望 {spec_version!r} 不符"
        )
    fns: list[Any] = []
    for _stem, zip_path, _meta in validated:
        model = RLService().load_model(str(zip_path))
        if model is None:
            raise ValueError(f"成员 {Path(zip_path).stem} 加载失败")
        fns.append(member_ratio_predict_fn(model))
    return PredictMemberSpecs(
        member_predict_fns=fns,
        meta=base_meta,
        model_id=ensemble_id,
        representative_path=str(base_path),
    )


class EnsembleService:
    """模型集成服务:records 持久化 + 创建期校验 + 前端冒烟预测。

    真实信号路径(paper/live/回测)统一经 load_ensemble_spec 拿成员 spec,
    本类 predict 仅作前端冒烟(spec §4.6);启动时零加载(只读 records)。
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = self._load_records()

    # ---- 元数据持久化 ----

    def _load_records(self) -> dict[str, dict[str, Any]]:
        if not ENSEMBLES_STORE.exists():
            return {}
        try:
            raw = json.loads(ENSEMBLES_STORE.read_text(encoding="utf-8"))
            return {r["id"]: r for r in raw}
        except (json.JSONDecodeError, KeyError, OSError, TypeError) as e:
            logger.warning(f"集成元数据读取失败,按空列表启动: {e}")
            return {}

    def _save_records(self) -> None:
        """原子写(临时文件 + replace),避免半写损坏。"""
        tmp = ENSEMBLES_STORE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(list(self._records.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(ENSEMBLES_STORE)

    # ---- 对外接口 ----

    def create_ensemble(self, strategy: str, model_paths: list[str]) -> tuple[str, list[dict[str, str]]]:
        """创建集成:先做 obs 规格一致性校验(失败整体拒绝),再逐成员加载,
        加载失败的成员进 skipped;skipped == 全体时拒单(spec §4.2)。
        records 记录 members 元数据(action_space 类型供前端展示)。
        """
        # 校验期:zip 解析 + meta 存在 + 一致性,任一失败直接 400
        _validated_member_metas(model_paths)

        skipped: list[dict[str, str]] = []
        members: list[dict[str, Any]] = []
        for stem, zip_path in _resolved_member_paths(model_paths):
            try:
                model = RLService().load_model(str(zip_path))
            except Exception as e:
                logger.warning(f"成员 {stem} 加载失败,跳过: {e}")
                skipped.append({"model_path": stem, "reason": str(e)})
                continue
            if model is None:
                skipped.append({"model_path": stem, "reason": "加载返回空"})
                continue
            kind = "discrete" if isinstance(model.action_space, spaces.Discrete) else "box"
            members.append({"stem": stem, "zip_path": str(zip_path), "action_space": kind})

        if not members:
            raise ValueError("集成没有可加载的成员,创建被拒绝")

        ensemble_id = uuid.uuid4().hex[:8]
        self._records[ensemble_id] = {
            "id": ensemble_id,
            "strategy": strategy,  # 仅存档;方案 A 固定均值聚合,不再影响信号
            "model_paths": list(model_paths),
            "members": members,
            "created_at": int(time.time()),
        }
        self._save_records()
        logger.info(f"集成创建成功: {ensemble_id},成员 {len(members)} 个,skipped {len(skipped)} 个")
        return ensemble_id, skipped

    def delete_ensemble(self, ensemble_id: str) -> None:
        """删除集成(磁盘元数据同步)。id 不存在抛 KeyError。"""
        if ensemble_id not in self._records:
            msg = f"Ensemble {ensemble_id} not found"
            raise KeyError(msg)
        self._records.pop(ensemble_id, None)
        self._save_records()

    def predict(self, ensemble_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        """冒烟预测:dict-obs 按 meta.features 顺序抽特征 → 成员各自推理 → 聚合。

        真实信号路径是策略运行(内核构造特征),本接口只用于前端冒烟(spec §4.6)。
        """
        record = self._records.get(ensemble_id)
        if record is None:
            raise KeyError(f"集成 {ensemble_id} 不存在")
        # 成员函数单一事实源:公共入口产物,不在本方法内二次加载
        spec = load_ensemble_spec(ensemble_id)
        # meta["features"] 真实是特征定义 dict 列表(KERNEL_FEATURES 同构),
        # 冒烟只需特征名;直接拿元素当 dict 键会 TypeError(线上 500 根因)
        feature_names = _feature_names(spec.meta.get("features") or [])
        if not observation:
            # 零观测冒烟(spec 决策 D1):空 dict 按特征名全填 0.0。
            # 成员吃的是内核 Z-Score 后的值,0 = 标准化均值点,语义中性;
            # 非空观测仍严校缺特征(路由层转 400)。
            flat: dict[str, float] = {f: 0.0 for f in feature_names}
        else:
            flat = {}
            for k, v in observation.items():
                values = v if isinstance(v, dict) else {k: v}
                for name, val in values.items():
                    flat[name] = float(val)
            missing = [f for f in feature_names if f not in flat]
            if missing:
                raise ValueError(f"observation 缺少特征: {missing[:5]}{'...' if len(missing) > 5 else ''}")
        obs_vec = [flat[f] for f in feature_names]

        stems = [m.get("stem") for m in record.get("members") or []]
        outputs: list[float | None] = []
        for i, fn in enumerate(spec.member_predict_fns):
            try:
                outputs.append(fn(obs_vec))
            except Exception as e:
                logger.warning(f"冒烟成员 {i} 推理失败,按弃权: {e}")
                outputs.append(None)
        ratio, confidence = aggregate_ratios(outputs)
        return {
            "action_type": "buy" if ratio > BUY_RATIO_EPS else "hold",
            "ratio": ratio,
            "confidence": confidence,
            "members": [{"stem": stems[i] if i < len(stems) else f"m{i}", "ratio": o} for i, o in enumerate(outputs)],
        }

    def list_ensembles(self) -> list[dict[str, Any]]:
        """列出所有集成(读元数据;旧记录缺 members 字段时兜底为空列表)。"""
        return [{**r, "members": r.get("members", [])} for r in self._records.values()]


@lru_cache(maxsize=1)
def get_ensemble_service() -> EnsembleService:
    """模块级单例。"""
    return EnsembleService()
