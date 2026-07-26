import json
import threading
import time
from typing import Dict, Optional

import typer
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plugins.event_bus import EventBus
from plugins.plugin_base import PluginBase
from plugins.plugin_loader import HotPluginLoader
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

cli_app = typer.Typer(name="plugin-dev", help="插件独立启动/调试工具", add_completion=False)


class MockPluginManager:

    def __init__(self):
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_configs: Dict[str, dict] = {}
        self._event_bus = EventBus()

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        return self.plugins.get(name)

    def register_plugin_config(self, name: str, config: dict) -> None:
        self.plugin_configs[name] = config


def _build_app(plugin_dir: str, host: str, port: int, enable_reload: bool) -> FastAPI:
    dev_app = FastAPI(title="Plugin Dev Server")

    dev_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    dev_router = APIRouter()

    mock_manager = MockPluginManager()
    loader = HotPluginLoader()

    loaded_plugin: Dict[str, Optional[PluginBase]] = {"current": None}
    manifest_mtime: Dict[str, float] = {"value": 0.0}
    entry_mtime: Dict[str, float] = {"value": 0.0}

    def _get_manifest_and_entry() -> Optional[tuple]:
        manifest_path = os.path.join(plugin_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        main_file = manifest.get("main", "plugin.py")
        entry_path = os.path.join(plugin_dir, main_file)
        return manifest_path, entry_path

    def _do_load() -> Optional[PluginBase]:
        plugin_sub_app = FastAPI()
        plugin = loader.load_plugin(plugin_dir, plugin_sub_app)
        if plugin is not None:
            mock_manager.plugins[plugin.name] = plugin
            plugin.plugin_manager = mock_manager
            loaded_plugin["current"] = plugin
            dev_app.mount("/", plugin_sub_app)
            logger.info(f"插件加载成功: {plugin.name} v{plugin.version}")
        else:
            logger.error(f"插件加载失败: {plugin_dir}")
        return plugin

    def _do_reload() -> Optional[PluginBase]:
        current = loaded_plugin.get("current")
        if current is not None:
            try:
                current.stop()
            except Exception:
                pass
            mock_manager.plugins.pop(current.name, None)

        loaded_plugin["current"] = None

        dev_app.routes.clear()
        dev_app.router.routes.clear()
        dev_app.include_router(dev_router)

        return _do_load()

    @dev_router.get("/dev/health")
    def health_check():
        plugin_info = None
        current = loaded_plugin.get("current")
        if current is not None:
            plugin_info = current.get_info()
        return {
            "status": "running",
            "plugin_dir": plugin_dir,
            "plugin": plugin_info,
            "reload_enabled": enable_reload,
        }

    @dev_router.post("/dev/reload")
    def reload_plugin():
        plugin = _do_reload()
        if plugin is not None:
            return {"status": "reloaded", "plugin": plugin.get_info()}
        return {"status": "reload_failed"}

    dev_app.include_router(dev_router)
    _do_load()

    if enable_reload:

        def _watch_loop() -> None:
            pair = _get_manifest_and_entry()
            if pair is None:
                logger.warning("无法获取 manifest 信息，文件监控未启动")
                return
            manifest_path, entry_path = pair
            manifest_mtime["value"] = os.path.getmtime(manifest_path)
            entry_mtime["value"] = os.path.getmtime(entry_path)

            while True:
                time.sleep(1.0)
                try:
                    current_manifest_mtime = os.path.getmtime(manifest_path)
                    current_entry_mtime = os.path.getmtime(entry_path) if os.path.exists(entry_path) else 0.0
                    if current_manifest_mtime != manifest_mtime["value"] or current_entry_mtime != entry_mtime["value"]:
                        logger.info("检测到插件文件变更，自动重载中...")
                        manifest_mtime["value"] = current_manifest_mtime
                        entry_mtime["value"] = current_entry_mtime
                        _do_reload()
                except Exception:
                    pass

        watch_thread = threading.Thread(target=_watch_loop, daemon=True)
        watch_thread.start()

    return dev_app


@cli_app.command()
def run(
    plugin_dir: str = typer.Option(..., help="插件目录路径"),
    port: int = typer.Option(9000, help="监听端口"),
    host: str = typer.Option("localhost", help="监听地址"),
    reload: bool = typer.Option(False, help="是否启用目录监控自动重载"),
):
    plugin_path = Path(plugin_dir).resolve()
    if not plugin_path.is_dir():
        typer.echo(f"插件目录不存在: {plugin_path}")
        raise typer.Exit(code=1)

    manifest_path = plugin_path / "manifest.json"
    if not manifest_path.exists():
        typer.echo(f"manifest.json 不存在: {manifest_path}")
        raise typer.Exit(code=1)

    typer.echo(f"启动插件开发服务器...")
    typer.echo(f"  插件目录: {plugin_path}")
    typer.echo(f"  监听地址: {host}:{port}")
    typer.echo(f"  自动重载: {'启用' if reload else '禁用'}")

    dev_app = _build_app(str(plugin_path), host, port, reload)
    uvicorn.run(dev_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli_app()
