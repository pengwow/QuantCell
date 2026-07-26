import asyncio
import json
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required, jwt_auth_required_sync
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 插件资源目录基准路径，与 plugin_manager.py 保持一致
_PLUGIN_ASSETS_BASE = Path(__file__).resolve().parent.parent / "data" / "installed_plugins"

router = APIRouter(
    prefix="/api/plugins",
    tags=["plugins"],
    responses={
        404: {"description": "插件不存在"},
        503: {"description": "插件管理器不可用"},
    },
)

_event_queues: List[asyncio.Queue] = []

# ponytail: 插件名防路径遍历
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$", re.ASCII)
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


class GitInstallRequest(BaseModel):
    url: str
    branch: Optional[str] = None


def _get_plugin_manager(request: Request):
    pm = getattr(request.app.state, "plugin_manager", None)
    if pm is None:
        raise HTTPException(status_code=503, detail="插件管理器不可用")
    return pm


def broadcast_event(event_type: str, data: dict):
    for queue in _event_queues:
        try:
            queue.put_nowait({"event": event_type, "data": data})
        except asyncio.QueueFull:
            pass


async def _sse_generator(queue: asyncio.Queue):
    try:
        while True:
            event = await queue.get()
            event_type = event.get("event", "message")
            data = json.dumps(event.get("data", {}), ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"
    except asyncio.CancelledError:
        return


@router.get("/", response_model=ApiResponse)
async def list_plugins(request: Request):
    try:
        pm = _get_plugin_manager(request)
        plugins = pm.get_all_plugins_info()
        return ApiResponse(code=0, message="获取插件列表成功", data={"plugins": plugins})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取插件列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
async def plugin_events(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    _event_queues.append(queue)

    async def cleanup():
        _event_queues.remove(queue)

    async def event_stream():
        try:
            async for chunk in _sse_generator(queue):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            await cleanup()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{name}", response_model=ApiResponse)
async def get_plugin(name: str):
    try:
        from plugins.plugin_store import PluginStore
        store = PluginStore()
        plugin = store.get_plugin(name)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        return ApiResponse(code=0, message="获取插件详情成功", data=plugin)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取插件详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install/upload", response_model=ApiResponse)
@jwt_auth_required
async def install_plugin_upload(request: Request, file: UploadFile = File(...)):
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="上传文件为空")
        if len(content) > _MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"文件大小超过{_MAX_UPLOAD_SIZE // 1024 // 1024}MB限制")

        suffix = ".zip"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            pm = _get_plugin_manager(request)
            success, msg = pm.install_from_zip(tmp_path)
            if not success:
                raise HTTPException(status_code=400, detail=msg)
            broadcast_event("plugin_installed", {
                "name": msg,
                "status": "installed",
            })
            return ApiResponse(code=0, message="插件安装成功", data={"name": msg})
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传安装插件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install/git", response_model=ApiResponse)
@jwt_auth_required
async def install_plugin_git(request: Request, body: GitInstallRequest):
    try:
        pm = _get_plugin_manager(request)
        success, msg = pm.install_from_git(body.url, body.branch)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        broadcast_event("plugin_installed", {
            "name": msg,
            "status": "installed",
        })
        return ApiResponse(code=0, message="插件安装成功", data={"name": msg})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Git安装插件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}", response_model=ApiResponse)
@jwt_auth_required
async def uninstall_plugin(request: Request, name: str):
    try:
        pm = _get_plugin_manager(request)
        result = pm.uninstall_plugin(name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        broadcast_event("plugin_uninstalled", {
            "name": name,
            "status": "uninstalled",
        })
        return ApiResponse(code=0, message="插件卸载成功", data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"卸载插件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/enable", response_model=ApiResponse)
@jwt_auth_required
async def enable_plugin(request: Request, name: str):
    try:
        pm = _get_plugin_manager(request)
        result = pm.enable_plugin(name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        broadcast_event("plugin_loaded", {
            "name": name,
            "status": "enabled",
        })
        return ApiResponse(code=0, message="插件启用成功", data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用插件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/disable", response_model=ApiResponse)
@jwt_auth_required
async def disable_plugin(request: Request, name: str):
    try:
        pm = _get_plugin_manager(request)
        result = pm.disable_plugin(name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        broadcast_event("plugin_unloaded", {
            "name": name,
            "status": "disabled",
        })
        return ApiResponse(code=0, message="插件禁用成功", data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"禁用插件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/assets/{path:path}")
async def serve_plugin_asset(name: str, path: str):
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="插件名称不合法")
    try:
        # 使用绝对路径查找插件资源，避免工作目录不一致导致 404
        plugin_dir = _PLUGIN_ASSETS_BASE / name / "frontend" / "dist" / path
        if not plugin_dir.is_file():
            # 兼容旧路径（框架源码目录下的 plugins）
            plugin_dir = Path(__file__).resolve().parent.parent / "plugins" / name / "frontend" / "dist" / path
        if not plugin_dir.is_file():
            raise HTTPException(status_code=404, detail="资源文件不存在")

        content_type, _ = mimetypes.guess_type(str(plugin_dir))
        if not content_type:
            # 根据文件扩展名明确设置 MIME type
            ext = plugin_dir.suffix.lower()
            if ext == ".js":
                content_type = "application/javascript"
            elif ext == ".css":
                content_type = "text/css"
            elif ext == ".json":
                content_type = "application/json"
            elif ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
                content_type = f"image/{ext.lstrip('.')}"
            else:
                content_type = "application/octet-stream"

        return FileResponse(
            path=str(plugin_dir),
            media_type=content_type,
            filename=plugin_dir.name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取插件资源失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/config", response_model=ApiResponse)
async def get_plugin_config(name: str):
    try:
        from plugins.plugin_store import PluginStore
        store = PluginStore()
        plugin = store.get_plugin(name)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        config_schema = plugin.get("config_schema")
        return ApiResponse(code=0, message="获取插件配置成功", data=config_schema)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取插件配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
