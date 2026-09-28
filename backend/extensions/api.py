"""桌面端可选扩展 REST 接口。

边界：这些端点只在桌面 sidecar 有意义——QUANTCELL_DATA_DIR 由 desktop_entry
注入；安装还要求 Rust 侧注入 QUANTCELL_UV_BIN（随包 uv resource 路径）。
Web/源码部署两者皆无，对应请求得到 503。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse
from extensions import installer, manifest
from extensions.manifest import ExtensionSpec, get_extension
from utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/extensions", tags=["Extensions"])


class ExtensionInfo(BaseModel):
    id: str
    name: str
    category: str
    description: str
    deps: list[str]
    approx_size_mb: int
    live_size_mb: int | None
    purpose: str
    installed: bool
    versions: dict[str, str]


class InstallResponse(BaseModel):
    task_id: str


class ProgressResponse(BaseModel):
    task_id: str | None
    status: str  # idle | resolving | downloading | installing | done | error
    pct: int
    detail: str


def _data_dir() -> str:
    data_dir = os.environ.get("QUANTCELL_DATA_DIR")
    if not data_dir:
        raise HTTPException(status_code=503, detail="扩展管理是桌面端功能")
    return data_dir


def _uv_bin() -> str:
    uv_bin = os.environ.get("QUANTCELL_UV_BIN")
    if not uv_bin or not Path(uv_bin).is_file():
        raise HTTPException(status_code=503, detail="扩展安装不可用（随包 uv 二进制缺失）")
    return uv_bin


def _require_ext(ext_id: str) -> ExtensionSpec:
    spec = get_extension(ext_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"未知扩展: {ext_id}")
    return spec


def _to_info(spec: ExtensionSpec, data_dir: str) -> ExtensionInfo:
    return ExtensionInfo(
        id=spec.id,
        name=spec.name,
        category=spec.category,
        description=spec.description,
        deps=list(spec.deps),
        approx_size_mb=spec.approx_size_mb,
        live_size_mb=manifest.live_total_size_mb(spec.deps),
        purpose=spec.purpose,
        installed=manifest.is_installed(data_dir, spec.id),
        versions=manifest.installed_versions(data_dir, spec.id),
    )


@router.get("", summary="扩展列表", description="返回静态清单 + PyPI 实时大小估算 + 安装状态")
def list_extensions(current_user: dict = Depends(get_current_user)) -> ApiResponse:
    data_dir = _data_dir()
    return ApiResponse(
        code=0,
        message="success",
        data=[_to_info(ext, data_dir).model_dump() for ext in manifest.EXTENSIONS],
    )


@router.get("/{ext_id}/status", summary="单扩展状态")
def get_status(ext_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    spec = _require_ext(ext_id)
    data_dir = _data_dir()
    return ApiResponse(code=0, message="success", data=_to_info(spec, data_dir).model_dump())


@router.post("/{ext_id}/install", summary="启动安装", description="异步任务，返回 task_id；同扩展并发安装返回 409")
def install_extension(ext_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    spec = _require_ext(ext_id)
    data_dir = _data_dir()
    uv_bin = _uv_bin()
    if installer.running_task_id(ext_id):
        raise HTTPException(status_code=409, detail="该扩展正在安装中")
    task_id = installer.start_install(spec, data_dir, uv_bin)
    return ApiResponse(
        code=0,
        message="安装任务已启动",
        data=InstallResponse(task_id=task_id).model_dump(),
    )


@router.get("/{ext_id}/progress", summary="查询安装进度", description="无任务时返回 idle；终态保留至下次安装")
def get_progress(ext_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    _require_ext(ext_id)
    # 优先活动任务；否则回落到最近一次任务（done/error 终态需可被前端消费一次）
    task_id = installer.running_task_id(ext_id) or installer.last_task_id(ext_id)
    state = installer.get_task(task_id) if task_id else None
    if state is None:
        progress = ProgressResponse(task_id=None, status="idle", pct=0, detail="")
    else:
        progress = ProgressResponse(
            task_id=task_id,
            status=state.status,
            pct=state.pct,
            detail=state.detail,
        )
    return ApiResponse(code=0, message="success", data=progress.model_dump())


@router.post("/{ext_id}/uninstall", summary="卸载扩展", description="幂等删除数据目录下的扩展目录；安装进行中返回 409")
def uninstall_extension(ext_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    spec = _require_ext(ext_id)
    data_dir = _data_dir()
    if installer.running_task_id(ext_id):
        raise HTTPException(status_code=409, detail="安装进行中，无法卸载")
    installer.uninstall(data_dir, spec.id)
    return ApiResponse(code=0, message="已卸载", data=None)
