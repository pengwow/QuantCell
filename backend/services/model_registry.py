"""ModelRegistryService — axon_quant.registry wrapper."""

from __future__ import annotations

import glob
import json
import os
import threading
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 训练产物与注册表共用同一目录(rl_service MODELS_DIR);顶层只放 *.zip + .meta.json
DEFAULT_MODELS_DIR = os.path.join("data", "models")

try:
    from axon_quant._native import registry as _registry_mod

    AVAILABLE = True
except ImportError:
    AVAILABLE = False

# Rust ModelRegistry 的 index 是纯内存(DashMap):registry.json 只写不读、
# 构造时不从磁盘恢复,即每次新建实例都是一张空注册表。若不共享实例,lifespan
# seed 完成后 API 路由每请求新建 svc 将看不到任何已注册模型,seed 形同虚设。
# 故按绝对 storage_path 缓存底层 Rust registry,让 seed / API / 测试共享同一 index。
# ponytail: 天花板 = 仅进程内共享、磁盘态不回填(跨进程仍各为空,依赖重启 seed
# 自愈);升级路径是 Rust ModelRegistry 支持从 registry.json 恢复 index 后移除缓存。
_registry_cache: dict[str, Any] = {}
_registry_cache_lock = threading.Lock()


def _get_shared_registry(storage_path: str) -> Any:
    """按 storage_path 取(或创建)共享的底层 Rust ModelRegistry 实例。"""
    key = os.path.abspath(storage_path)
    with _registry_cache_lock:
        registry = _registry_cache.get(key)
        if registry is None:
            persist_dir = os.path.join(storage_path, ".persist")
            os.makedirs(persist_dir, exist_ok=True)
            local_storage = _registry_mod.LocalStorage(storage_path)
            registry = _registry_mod.ModelRegistry(local_storage, persist_dir)
            _registry_cache[key] = registry
        return registry


def seed_demo_models(count: int = 3, storage_path: str = DEFAULT_MODELS_DIR) -> list[str]:
    """把最近训练的 RL 模型产物幂等 seed 进模型注册表(开箱即用)。

    幂等策略:注册表非空即跳过。重启后 Rust 内存 index 归零(registry.json
    只写不读),此函数同时也是重启自愈入口——重新 register 时版本计数从
    1.0.0 起步,fs::copy 覆盖旧文件,无脏目录累积。

    Returns:
        本次实际注册的模型名列表;已跳过或无可 seed 产物时返回 []。
    """
    if not AVAILABLE:
        logger.warning("axon_quant.registry 不可用,跳过模型注册表 seed")
        return []
    try:
        svc = ModelRegistryService(storage_path=storage_path)
        if svc.list_models():
            return []
    except Exception:
        logger.warning("模型注册表不可用,跳过 seed", exc_info=True)
        return []

    candidates = sorted(
        glob.glob(os.path.join(storage_path, "*.zip")),
        key=os.path.getmtime,
        reverse=True,
    )
    registered: list[str] = []
    for zip_path in candidates:
        if len(registered) >= count:
            break
        meta_path = zip_path + ".meta.json"
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            name = meta["model_id"]
            svc.register_model(
                name=name,
                model_path=zip_path,
                metadata={
                    "spec_version": meta.get("spec_version", ""),
                    "window_size": meta.get("window_size"),
                    "feature_count": len(meta.get("features", [])),
                },
            )
            registered.append(name)
        except OSError, ValueError, KeyError:
            logger.warning("跳过无法解析的模型产物: %s", zip_path, exc_info=True)

    # 第一个示例晋升为 Production,页面状态列可呈现完整生命周期
    if registered:
        svc.promote_to_production(registered[0])
        logger.info("模型注册表 seed 完成: %s", registered)
    return registered


class ModelRegistryService:
    """Model registry service wrapping axon_quant ModelRegistry."""

    def __init__(self, storage_path: str = "data/models"):
        if not AVAILABLE:
            msg = "axon_quant.registry not available"
            raise RuntimeError(msg)
        # 底层 registry 进程内按路径共享,理由见模块级 _registry_cache 注释
        self._registry = _get_shared_registry(storage_path)
        # get_artifact_path 的路径逃逸校验需要拿它做 realpath 前缀比对
        self._storage_path = storage_path

    def register_model(
        self,
        name: str,
        model_path: str,
        metadata: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        """Register a model and return its ID."""
        desc = json.dumps({"metadata": metadata or {}, "metrics": metrics or {}})
        result = self._registry.register(name, model_path, desc)
        return result["version"]

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered models with full contract.

        非 Production 模型 Rust 侧无 detail 查询接口(version/stage 不可得),
        统一以 development 占位 —— 这是 Rust list_models() 只返回名字的现状。
        """
        rows: list[dict[str, Any]] = []
        for name in self._registry.list_models():
            prod = None
            try:
                prod = self._registry.get_production(name)
            # 无 Production 版本时 Rust get_production 抛错属正常路径
            except Exception:
                prod = None
            metrics: dict[str, Any] = {}
            version = ""
            stage = "development"
            if prod:
                version = prod.get("version", "")
                stage = prod.get("stage", "development")
                try:
                    metrics = json.loads(prod.get("description", "{}")).get("metrics", {})
                except TypeError, ValueError:
                    metrics = {}
            rows.append(
                {
                    "id": name,
                    "name": name,
                    "version": version,
                    "stage": stage,
                    "metrics": metrics,
                }
            )
        return rows

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        """Get production model by name."""
        try:
            return self._registry.get_production(model_id)
        except Exception:
            return None

    def get_model_detail(self, model_id: str) -> dict[str, Any] | None:
        """Production 模型详情;不存在或无 production 返回 None。"""
        prod = self.get_model(model_id)
        if not prod:
            return None
        try:
            desc = json.loads(prod.get("description", "{}"))
        # description 是注册时写入的 JSON 字符串,损坏不应导致 500
        except TypeError, ValueError:
            desc = {}
        return {
            "name": prod.get("name", model_id),
            "version": prod.get("version", ""),
            "stage": prod.get("stage", "production"),
            "metadata": desc.get("metadata", {}),
            "metrics": desc.get("metrics", {}),
            "artifact_size_bytes": prod.get("artifact_size_bytes", 0),
            "artifact_hash": prod.get("artifact_hash", ""),
            "storage_uri": prod.get("storage_uri", ""),
        }

    def get_artifact_path(self, model_id: str) -> str | None:
        """取 production artifact 的本地路径;路径逃逸或文件缺失时返回 None。"""
        prod = self.get_model(model_id)
        if not prod:
            return None
        uri = prod.get("storage_uri", "")
        if not uri:
            return None
        # Rust 侧 storage_uri 是相对 storage_path 的相对路径(如 name/1.0.0/model.bin),
        # 必须先拼回 storage_path 再 realpath 才能与 base 同基比较(os.path.join
        # 遇到绝对路径时直接使用绝对路径,故 storage_uri 为绝对路径时行为不变);
        # 只放行 storage_path 内的路径,防 storage_uri 被改后变成任意文件下载;
        # base + os.sep 前缀同时挡住同级目录(如 data/models-evil)的逃逸
        base = os.path.realpath(self._storage_path)
        real = os.path.realpath(os.path.join(self._storage_path, uri))
        if not real.startswith(base + os.sep) or not os.path.isfile(real):
            return None
        return real

    def promote_to_production(self, model_id: str) -> bool:
        """Promote model to production.

        ponytail: Rust 无 list_versions API,拿不到"最新版本",这里晋升首版
        1.0.0;已有 Production 时 no-op 返回 False(语义修正:晋升已有生产版
        本不是成功操作)。升级路径:Rust 增加版本列表 API 后改传最新 version。
        """
        names = self._registry.list_models()
        if model_id not in names:
            return False
        prod = None
        try:
            prod = self._registry.get_production(model_id)
        except Exception:
            prod = None
        if prod:
            return False
        self._registry.promote_to_production(model_id, "1.0.0")
        return True
