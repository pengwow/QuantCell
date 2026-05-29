#!/usr/bin/env python3
"""
插件管理命令行工具

提供插件的创建、安装、卸载、查看、启用/禁用、清理、打包等功能。
核心逻辑复用 PluginInstaller、PluginManager、PluginStore。

使用示例:
    # 创建插件脚手架
    python scripts/plugin_cli.py create my_plugin --output ./plugins --type fullstack

    # 从 ZIP 安装插件
    python scripts/plugin_cli.py install --zip /path/to/plugin.zip

    # 从 Git 仓库安装
    python scripts/plugin_cli.py install --git https://github.com/user/repo.git --branch main

    # 从本地目录安装
    python scripts/plugin_cli.py install --dir /path/to/plugin_dir

    # 列出所有插件
    python scripts/plugin_cli.py list

    # 查看插件详情
    python scripts/plugin_cli.py info my_plugin

    # 启用/禁用插件
    python scripts/plugin_cli.py enable my_plugin
    python scripts/plugin_cli.py disable my_plugin

    # 卸载插件
    python scripts/plugin_cli.py uninstall my_plugin

    # 清理残留数据
    python scripts/plugin_cli.py clean

    # 打包插件
    python scripts/plugin_cli.py pack /path/to/plugin_dir --output plugin.zip
"""

import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

app = typer.Typer(
    name="plugin-cli",
    help="插件管理命令行工具",
    add_completion=False,
)

_plugin_manager = None


def _get_plugin_manager():
    global _plugin_manager
    if _plugin_manager is None:
        from plugins import PluginManager
        plugin_dir = str(backend_path / "data" / "installed_plugins")
        os.makedirs(plugin_dir, exist_ok=True)
        _plugin_manager = PluginManager(app=None, plugin_dir=plugin_dir)
    return _plugin_manager


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("(无数据)")
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    header_line = " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    print(header_line)
    print("-" * len(header_line))

    for row in rows:
        print(" | ".join(
            str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)
        ))


def _status_icon(status: str) -> str:
    return {
        "enabled": "🟢",
        "active": "🟢",
        "installed": "⚪",
        "disabled": "🔴",
        "error": "❌",
    }.get(status, "❓")


# ==================== 安装命令 ====================

@app.command("install", help="安装插件")
def cmd_install(
    zip_file: Annotated[
        Optional[str],
        typer.Option("--zip", "-z", help="从 ZIP 文件安装")
    ] = None,
    git_url: Annotated[
        Optional[str],
        typer.Option("--git", "-g", help="从 Git 仓库安装")
    ] = None,
    dir_path: Annotated[
        Optional[str],
        typer.Option("--dir", "-d", help="从本地目录安装")
    ] = None,
    branch: Annotated[
        Optional[str],
        typer.Option("--branch", "-b", help="Git 分支（仅 --git 时有效）")
    ] = None,
):
    """安装插件，支持 ZIP、Git、本地目录三种来源（三选一）"""
    sources = [s for s in [zip_file, git_url, dir_path] if s is not None]
    if len(sources) == 0:
        typer.echo("错误: 请指定安装来源 (--zip、--git 或 --dir)", err=True)
        raise typer.Exit(1)
    if len(sources) > 1:
        typer.echo("错误: 只能指定一种安装来源", err=True)
        raise typer.Exit(1)

    pm = _get_plugin_manager()

    if zip_file:
        if not os.path.isfile(zip_file):
            typer.echo(f"错误: ZIP 文件不存在: {zip_file}", err=True)
            raise typer.Exit(1)
        typer.echo(f"正在从 ZIP 安装: {zip_file}")
        success, msg = pm.install_from_zip(zip_file)
        if success:
            typer.echo(f"✅ {msg}")
        else:
            typer.echo(f"❌ {msg}", err=True)
            raise typer.Exit(1)

    elif git_url:
        typer.echo(f"正在从 Git 安装: {git_url}")
        if branch:
            typer.echo(f"  分支: {branch}")
        success, msg = pm.install_from_git(git_url, branch)
        if success:
            typer.echo(f"✅ {msg}")
        else:
            typer.echo(f"❌ {msg}", err=True)
            raise typer.Exit(1)

    elif dir_path:
        if not os.path.isdir(dir_path):
            typer.echo(f"错误: 目录不存在: {dir_path}", err=True)
            raise typer.Exit(1)

        manifest_path = os.path.join(dir_path, "manifest.json")
        if not os.path.isfile(manifest_path):
            typer.echo(f"错误: 目录中未找到 manifest.json: {dir_path}", err=True)
            raise typer.Exit(1)

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            typer.echo(f"错误: manifest.json 解析失败: {e}", err=True)
            raise typer.Exit(1)

        from plugins.plugin_installer import PluginInstaller
        installer = PluginInstaller(pm.plugin_dir, pm)
        valid, msg = installer.validate_manifest(manifest)
        if not valid:
            typer.echo(f"错误: manifest 校验失败: {msg}", err=True)
            raise typer.Exit(1)

        plugin_name = manifest["name"]
        dest_dir = os.path.join(pm.plugin_dir, plugin_name)

        existing = pm.get_all_plugins_info()
        if any(p["name"] == plugin_name for p in existing):
            typer.echo(f"错误: 插件 {plugin_name} 已存在，请先卸载", err=True)
            raise typer.Exit(1)

        if os.path.exists(dest_dir):
            typer.echo(f"错误: 目标目录已存在: {dest_dir}", err=True)
            raise typer.Exit(1)

        shutil.copytree(dir_path, dest_dir)
        success = pm.install_plugin(dest_dir, manifest, source_type="manual")
        if success:
            typer.echo(f"✅ 插件 {plugin_name} 安装成功")
        else:
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            typer.echo(f"❌ 插件 {plugin_name} 安装失败", err=True)
            raise typer.Exit(1)


# ==================== 卸载命令 ====================

@app.command("uninstall", help="卸载插件")
def cmd_uninstall(
    plugin_name: Annotated[str, typer.Argument(help="插件名称")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="强制卸载，不提示确认")
    ] = False,
):
    """卸载指定插件"""
    pm = _get_plugin_manager()

    plugin_info = pm.get_all_plugins_info()
    if not any(p["name"] == plugin_name for p in plugin_info):
        typer.echo(f"错误: 插件 {plugin_name} 不存在", err=True)
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"确定要卸载插件 {plugin_name} 吗？")
        if not confirm:
            typer.echo("已取消")
            raise typer.Exit(0)

    success = pm.uninstall_plugin(plugin_name)
    if success:
        plugin_dir = os.path.join(pm.plugin_dir, plugin_name)
        if os.path.exists(plugin_dir):
            trash_dir = backend_path / ".trash" / f"{plugin_name}_{int(__import__('time').time())}"
            trash_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(plugin_dir, str(trash_dir))
            typer.echo(f"✅ 插件 {plugin_name} 已卸载，文件移至: {trash_dir}")
        else:
            typer.echo(f"✅ 插件 {plugin_name} 已卸载")
    else:
        typer.echo(f"❌ 卸载插件 {plugin_name} 失败", err=True)
        raise typer.Exit(1)


# ==================== 列表命令 ====================

@app.command("list", help="列出所有插件")
def cmd_list(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="输出格式: json 或 table")
    ] = "table",
):
    """列出所有已安装的插件"""
    pm = _get_plugin_manager()
    plugins = pm.get_all_plugins_info()

    if not plugins:
        typer.echo("暂无插件")
        return

    if format == "json":
        _print_json(plugins)
    else:
        headers = ["状态", "名称", "版本", "加载类型", "来源", "描述"]
        rows = []
        for p in plugins:
            status = p.get("status", "unknown")
            rows.append([
                _status_icon(status),
                p.get("name", ""),
                p.get("version", ""),
                p.get("load_type", ""),
                p.get("install_source", "") or "manual",
                (p.get("description", "") or "")[:30],
            ])
        _print_table(headers, rows)
        typer.echo(f"\n共 {len(plugins)} 个插件")


# ==================== 详情命令 ====================

@app.command("info", help="查看插件详情")
def cmd_info(
    plugin_name: Annotated[str, typer.Argument(help="插件名称")],
):
    """查看指定插件的详细信息"""
    from plugins.plugin_store import PluginStore

    plugin = PluginStore.get_plugin(plugin_name)
    if not plugin:
        typer.echo(f"错误: 插件 {plugin_name} 不存在", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n🔌 插件: {plugin['name']}")
    typer.echo("=" * 50)
    typer.echo(f"  版本: {plugin['version']}")
    typer.echo(f"  作者: {plugin.get('author') or 'N/A'}")
    typer.echo(f"  描述: {plugin.get('description') or 'N/A'}")
    typer.echo(f"  加载类型: {plugin['load_type']}")
    typer.echo(f"  状态: {plugin['status']}")
    typer.echo(f"  安装来源: {plugin.get('install_source') or 'manual'}")
    typer.echo(f"  安装路径: {plugin.get('install_path') or 'N/A'}")

    perms = plugin.get("permissions")
    if perms:
        typer.echo(f"  权限: {', '.join(perms) if isinstance(perms, list) else perms}")
    else:
        typer.echo("  权限: 无")

    schema = plugin.get("config_schema")
    if schema:
        typer.echo(f"  配置结构: 有")
    else:
        typer.echo("  配置结构: 无")

    frontend = plugin.get("frontend_entry")
    if frontend:
        typer.echo(f"  前端入口: {frontend}")

    err = plugin.get("error_message")
    if err:
        typer.echo(f"  错误信息: {err}")

    typer.echo(f"  安装时间: {plugin.get('installed_at') or 'N/A'}")
    typer.echo(f"  更新时间: {plugin.get('updated_at') or 'N/A'}")
    typer.echo()


# ==================== 启用/禁用命令 ====================

@app.command("enable", help="启用插件")
def cmd_enable(
    plugin_name: Annotated[str, typer.Argument(help="插件名称")],
):
    """启用指定插件"""
    pm = _get_plugin_manager()

    plugin_info = pm.get_all_plugins_info()
    if not any(p["name"] == plugin_name for p in plugin_info):
        typer.echo(f"错误: 插件 {plugin_name} 不存在", err=True)
        raise typer.Exit(1)

    success = pm.enable_plugin(plugin_name)
    if success:
        typer.echo(f"✅ 插件 {plugin_name} 已启用")
    else:
        typer.echo(f"❌ 启用插件 {plugin_name} 失败", err=True)
        raise typer.Exit(1)


@app.command("disable", help="禁用插件")
def cmd_disable(
    plugin_name: Annotated[str, typer.Argument(help="插件名称")],
):
    """禁用指定插件"""
    pm = _get_plugin_manager()

    plugin_info = pm.get_all_plugins_info()
    if not any(p["name"] == plugin_name for p in plugin_info):
        typer.echo(f"错误: 插件 {plugin_name} 不存在", err=True)
        raise typer.Exit(1)

    success = pm.disable_plugin(plugin_name)
    if success:
        typer.echo(f"✅ 插件 {plugin_name} 已禁用")
    else:
        typer.echo(f"❌ 禁用插件 {plugin_name} 失败", err=True)
        raise typer.Exit(1)


# ==================== 清理命令 ====================

@app.command("clean", help="清理残留数据")
def cmd_clean(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="强制清理，不提示确认")
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="仅预览，不实际执行清理")
    ] = False,
):
    """清理插件残留数据：无效数据库记录、残留目录、临时文件"""
    pm = _get_plugin_manager()
    db_plugins = pm.get_all_plugins_info()
    db_names = {p["name"] for p in db_plugins}

    actions = []

    # 1. 检查数据库中不存在对应目录的残留记录
    for p in db_plugins:
        name = p["name"]
        install_path = p.get("install_path")
        if install_path and not os.path.isdir(install_path):
            actions.append(("db_record", name, f"目录不存在: {install_path}"))
        elif not install_path:
            default_path = os.path.join(pm.plugin_dir, name)
            if not os.path.isdir(default_path):
                actions.append(("db_record", name, f"默认目录不存在: {default_path}"))

    # 2. 检查目录中不存在数据库记录的残留文件夹
    if os.path.isdir(pm.plugin_dir):
        for item in os.listdir(pm.plugin_dir):
            item_path = os.path.join(pm.plugin_dir, item)
            if not os.path.isdir(item_path):
                continue
            manifest_path = os.path.join(item_path, "manifest.json")
            if not os.path.exists(manifest_path):
                continue
            if item not in db_names:
                actions.append(("dir", item, "数据库中无记录"))

    # 3. 清理临时目录
    temp_dirs = []
    for tmp_base in [tempfile.gettempdir()]:
        if not os.path.isdir(tmp_base):
            continue
        for entry in os.listdir(tmp_base):
            if entry.startswith(("plugin_install_", "plugin_git_")):
                temp_dirs.append(os.path.join(tmp_base, entry))

    if not actions and not temp_dirs:
        typer.echo("✅ 未发现需要清理的残留数据")
        return

    typer.echo(f"\n发现以下可清理项:\n")

    db_records = [a for a in actions if a[0] == "db_record"]
    dirs = [a for a in actions if a[0] == "dir"]

    if db_records:
        typer.echo("📋 无效数据库记录:")
        for _, name, reason in db_records:
            typer.echo(f"  - {name}: {reason}")
        typer.echo()

    if dirs:
        typer.echo("📁 残留插件目录:")
        for _, name, reason in dirs:
            typer.echo(f"  - {name}: {reason}")
        typer.echo()

    if temp_dirs:
        typer.echo("🗑️  临时目录:")
        for d in temp_dirs:
            typer.echo(f"  - {d}")
        typer.echo()

    if dry_run:
        typer.echo("(dry-run 模式，未执行任何操作)")
        return

    if not force:
        confirm = typer.confirm("确定要清理以上项目吗？")
        if not confirm:
            typer.echo("已取消")
            raise typer.Exit(0)

    cleaned = 0

    # 清理无效数据库记录
    from plugins.plugin_store import PluginStore
    for _, name, _ in db_records:
        if PluginStore.delete_plugin(name):
            typer.echo(f"  ✅ 已删除数据库记录: {name}")
            cleaned += 1
        else:
            typer.echo(f"  ❌ 删除数据库记录失败: {name}")

    # 移动残留目录到 .trash
    for _, name, _ in dirs:
        src = os.path.join(pm.plugin_dir, name)
        if os.path.exists(src):
            trash_dir = backend_path / ".trash" / f"{name}_{int(__import__('time').time())}"
            trash_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, str(trash_dir))
            typer.echo(f"  ✅ 已移动残留目录: {name} -> {trash_dir}")
            cleaned += 1

    # 清理临时目录
    for d in temp_dirs:
        try:
            shutil.rmtree(d)
            typer.echo(f"  ✅ 已删除临时目录: {d}")
            cleaned += 1
        except Exception as e:
            typer.echo(f"  ❌ 删除临时目录失败: {d}, {e}")

    typer.echo(f"\n共清理 {cleaned} 个项目")


# ==================== 打包命令 ====================

@app.command("pack", help="打包插件为 ZIP")
def cmd_pack(
    plugin_dir: Annotated[str, typer.Argument(help="插件目录路径")],
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="输出 ZIP 文件路径")
    ] = None,
):
    """将本地插件目录打包成 ZIP 文件（供离线分发）"""
    if not os.path.isdir(plugin_dir):
        typer.echo(f"错误: 目录不存在: {plugin_dir}", err=True)
        raise typer.Exit(1)

    manifest_path = os.path.join(plugin_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        typer.echo(f"错误: 目录中未找到 manifest.json: {plugin_dir}", err=True)
        raise typer.Exit(1)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        typer.echo(f"错误: manifest.json 解析失败: {e}", err=True)
        raise typer.Exit(1)

    from plugins.plugin_installer import PluginInstaller
    installer = PluginInstaller(plugin_dir="")
    valid, msg = installer.validate_manifest(manifest)
    if not valid:
        typer.echo(f"错误: manifest 校验失败: {msg}", err=True)
        raise typer.Exit(1)

    plugin_name = manifest["name"]
    version = manifest.get("version", "0.0.0")

    if output is None:
        output = f"{plugin_name}-{version}.zip"

    output_path = Path(output).resolve()
    if output_path.exists():
        typer.echo(f"错误: 输出文件已存在: {output_path}", err=True)
        raise typer.Exit(1)

    # 创建临时 staging 目录，复制插件文件并排除不需要的文件
    staging = tempfile.mkdtemp(prefix="plugin_pack_")
    try:
        staging_plugin = os.path.join(staging, plugin_name)

        def ignore_patterns(src, names):
            return {
                name for name in names
                if name == "__pycache__"
                or name.endswith(".pyc")
                or name.endswith(".pyo")
                or name.endswith(".db")
                or name == ".DS_Store"
                or name.endswith(".egg-info")
            }

        shutil.copytree(plugin_dir, staging_plugin, ignore=ignore_patterns)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(staging_plugin):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, staging)
                    zf.write(file_path, arcname)

        typer.echo(f"✅ 打包完成: {output_path}")
        typer.echo(f"\nZIP 结构:")
        with zipfile.ZipFile(output_path) as zf:
            for name in sorted(zf.namelist()):
                typer.echo(f"  {name}")

    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ==================== 创建命令 ====================

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _snake_to_pascal(name: str) -> str:
    return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))


def _snake_to_kebab(name: str) -> str:
    return name.replace("_", "-")


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def _make_executable(path: str) -> None:
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _render_manifest(
    plugin_name: str,
    description: str,
    author: str,
    load_type: str,
    plugin_type: str,
) -> str:
    data = {
        "name": plugin_name,
        "version": "0.1.0",
        "description": description,
        "author": author,
        "main": "plugin.py",
        "frontend_entry": "frontend/src/main.tsx" if plugin_type == "fullstack" else None,
        "load_type": load_type,
        "permissions": [],
        "config_schema": None,
        "dependencies": [],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _render_plugin_py(plugin_name: str) -> str:
    class_name = _snake_to_pascal(plugin_name)
    kebab = _snake_to_kebab(plugin_name)
    return f'''from fastapi import APIRouter

from plugins.plugin_base import PluginBase
from utils.logger import get_plugin_logger


class {class_name}Plugin(PluginBase):

    def __init__(self) -> None:
        super().__init__("{plugin_name}", "0.1.0")
        self.logger = get_plugin_logger("{plugin_name}")
        self.router = APIRouter(prefix="/api/plugins/{kebab}")
        self._setup_routes()

    def _setup_routes(self) -> None:

        @self.router.get("/health")
        async def health():
            return {{"status": "ok", "plugin": self.name, "version": self.version}}

    def register(self, plugin_manager) -> None:
        super().register(plugin_manager)
        self.logger.info(f"{{self.name}} 已注册")

    def start(self) -> None:
        super().start()
        self.logger.info(f"{{self.name}} 已启动")

    def stop(self) -> None:
        super().stop()
        self.logger.info(f"{{self.name}} 已停止")


def register_plugin():
    return {class_name}Plugin()
'''


def _render_build_sh(plugin_name: str) -> str:
    return f'''#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[0;33m'
NC='\\033[0m'

info()  {{ echo -e "${{GREEN}}[INFO]${{NC}}  $*"; }}
warn()  {{ echo -e "${{YELLOW}}[WARN]${{NC}}  $*"; }}
error() {{ echo -e "${{RED}}[ERROR]${{NC}} $*"; exit 1; }}

SKIP_FRONTEND=false
for arg in "$@"; do
    case "$arg" in
        --skip-frontend) SKIP_FRONTEND=true ;;
    esac
done

MANIFEST="manifest.json"
if [ ! -f "$MANIFEST" ]; then
    error "manifest.json 不存在"
fi

PLUGIN_NAME=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['name'])" "$MANIFEST")
PLUGIN_VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$MANIFEST")

info "插件: $PLUGIN_NAME v$PLUGIN_VERSION"

if [ "$SKIP_FRONTEND" = false ]; then
    if [ -d "frontend" ]; then
        info "构建前端..."
        cd frontend
        bun install --frozen-lockfile 2>/dev/null || bun install
        bun run build
        cd ..
        info "前端构建完成"
    fi
else
    info "跳过前端构建"
    if [ -d "frontend" ] && [ ! -d "frontend/dist" ]; then
        error "frontend/dist/ 不存在，请先执行完整构建（不带 --skip-frontend）"
    fi
fi

OUTPUT_DIR="$SCRIPT_DIR/dist"
mkdir -p "$OUTPUT_DIR"

ZIP_NAME="${{PLUGIN_NAME}}-${{PLUGIN_VERSION}}.zip"
ZIP_PATH="$OUTPUT_DIR/$ZIP_NAME"
rm -f "$ZIP_PATH"

STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT
STAGING_PLUGIN="$STAGING/$PLUGIN_NAME"
mkdir -p "$STAGING_PLUGIN"

rsync -a \\
    --exclude='__pycache__' \\
    --exclude='*.pyc' \\
    --exclude='*.pyo' \\
    --exclude='*.db' \\
    --exclude='.DS_Store' \\
    --exclude='*.egg-info' \\
    --exclude='node_modules' \\
    --exclude='frontend/node_modules' \\
    --exclude='.git' \\
    --exclude='/dist' \\
    "$SCRIPT_DIR/" "$STAGING_PLUGIN/"

(cd "$STAGING" && zip -r "$ZIP_PATH" "$PLUGIN_NAME/" -q)

info "打包完成: $ZIP_PATH"
info ""
info "ZIP 结构:"
python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as zf:
    for name in sorted(zf.namelist()):
        print(f'  {{name}}')
" "$ZIP_PATH"
'''


def _render_frontend_package_json(plugin_name: str, description: str) -> str:
    data = {
        "name": f"@quantcell-plugin/{plugin_name}",
        "private": True,
        "version": "0.1.0",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
            "antd": "^5.24.0",
            "@ant-design/icons": "^5.6.1",
        },
        "devDependencies": {
            "@types/react": "^18.3.18",
            "@types/react-dom": "^18.3.5",
            "@vitejs/plugin-react": "^4.3.4",
            "typescript": "~5.6.2",
            "vite": "^6.0.0",
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _render_vite_config_ts(plugin_name: str) -> str:
    return '''import { defineConfig } from 'vite';
import type { Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// 匹配 JS 标识符（包括 $ 和 Unicode 字符，与 Rollup 压缩后的变量名兼容）
const IDENT = String.raw`[\\p{ID_Start}$_][\\p{ID_Continue}$\\u200C\\u200D]*`;

function externalsToGlobals(): Plugin {
  const moduleMap: Record<string, string> = {
    'react': 'React',
    'react-dom': 'ReactDOM',
    'react-dom/client': 'ReactDOM',
    'react/jsx-runtime': 'ReactJSX',
  };

  function transformImports(code: string): string {
    let result = code;
    for (const [mod, globalName] of Object.entries(moduleMap)) {
      const escaped = mod.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');

      // 1) import * as X from "mod"
      const nsRe = new RegExp(
        `import\\\\s+\\\\*\\\\s+as\\\\s+(${IDENT})\\\\s+from\\\\s*"${escaped}"\\\\s*;?`,
        'gu'
      );
      result = result.replace(nsRe, (_m: string, name: string) =>
        `const ${name} = ${globalName};`
      );

      // 2) import X, { a, b as c } from "mod"
      const defNamedRe = new RegExp(
        `import\\\\s+(${IDENT})\\\\s*,\\\\s*\\\\{([^}]+)\\\\}\\\\s+from\\\\s*"${escaped}"\\\\s*;?`,
        'gu'
      );
      result = result.replace(defNamedRe, (_m: string, defName: string, named: string) => {
        const parts = [`const ${defName} = ${globalName};`];
        parseNamedImports(named, globalName, parts);
        return parts.join('\\n');
      });

      // 3) import { a, b as c } from "mod"
      const namedRe = new RegExp(
        `import\\\\s+\\\\{([^}]+)\\\\}\\\\s+from\\\\s*"${escaped}"\\\\s*;?`,
        'gu'
      );
      result = result.replace(namedRe, (_m: string, named: string) => {
        const parts: string[] = [];
        parseNamedImports(named, globalName, parts);
        return parts.join('\\n');
      });

      // 4) import X from "mod"
      const defRe = new RegExp(
        `import\\\\s+(${IDENT})\\\\s+from\\\\s*"${escaped}"\\\\s*;?`,
        'gu'
      );
      result = result.replace(defRe, (_m: string, name: string) =>
        `const ${name} = ${globalName};`
      );
    }
    return result;
  }

  function parseNamedImports(named: string, globalName: string, parts: string[]): void {
    for (const item of named.split(',')) {
      const t = item.trim();
      if (!t) continue;
      // 使用宽松的正则匹配标识符，支持 $ 符号（Rollup 压缩后的变量名如 $t）
      const asMatch = t.match(new RegExp(`^(${IDENT})\\\\s+as\\\\s+(${IDENT})$`, 'u'));
      if (asMatch) {
        parts.push(`const ${asMatch[2]} = ${globalName}.${asMatch[1]};`);
      } else {
        parts.push(`const ${t} = ${globalName}.${t};`);
      }
    }
  }

  return {
    name: 'externals-to-globals',
    generateBundle(_options, bundle) {
      for (const chunk of Object.values(bundle)) {
        if (chunk.type === 'chunk') {
          chunk.code = transformImports(chunk.code);
        }
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), externalsToGlobals()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    lib: {
      entry: 'src/main.tsx',
      formats: ['es'],
      fileName: 'index',
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime', 'react-dom/client'],
      output: {
        entryFileNames: 'index.js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
    cssCodeSplit: false,
    outDir: 'dist',
    emptyOutDir: true,
  },
});
'''


def _render_tsconfig_json() -> str:
    return '''{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
'''


def _render_tsconfig_node_json() -> str:
    return '''{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["vite.config.ts"]
}
'''


def _render_index_html(plugin_name: str) -> str:
    return f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{plugin_name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
'''


def _render_main_tsx(plugin_name: str) -> str:
    kebab = _snake_to_kebab(plugin_name)
    return f'''import App from './App';

const routes = [
  {{
    path: '/plugins/{kebab}',
    element: React.createElement(App),
    pluginName: '{plugin_name}',
  }},
];

const menuItems = [
  {{
    key: '/plugins/{kebab}',
    label: '{plugin_name}',
    pluginName: '{plugin_name}',
  }},
];

export function registerPlugin() {{
  return {{
    register(context) {{
      for (const route of routes) {{
        context.addRoute(route);
      }}
      for (const menu of menuItems) {{
        context.addMenu(menu);
      }}
    }},
    getRoutes: () => routes,
    getMenuItems: () => menuItems,
  }};
}}
'''


def _render_app_tsx(plugin_name: str, description: str) -> str:
    display_desc = description or f"{plugin_name} 插件"
    return f'''import {{ Card, Typography, ConfigProvider, theme as antdTheme }} from 'antd';
import {{ useTheme }} from './hooks/useTheme';
import {{ useLocale }} from './hooks/useLocale';

const {{ Title, Paragraph }} = Typography;

export default function App() {{
  const theme = useTheme();
  const locale = useLocale();
  const isDark = theme === 'dark';

  return (
    <ConfigProvider
      locale={{locale}}
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {{
          colorBgBase: isDark ? '#141414' : '#fff',
        }},
      }}
    >
      <div style={{{{ padding: 0, background: isDark ? '#141414' : '#fff' }}}}>
        <Card style={{{{ background: isDark ? '#1f1f1f' : '#fff' }}}}>
          <Title level={{{{3}}}} style={{{{ color: isDark ? '#fff' : undefined }}}}>
            {plugin_name}
          </Title>
          <Paragraph style={{{{ color: isDark ? 'rgba(255,255,255,0.65)' : undefined }}}}>
            {display_desc}
          </Paragraph>
          <Paragraph type="secondary">
            插件已成功加载。编辑此组件开始开发你的插件页面。
          </Paragraph>
        </Card>
      </div>
    </ConfigProvider>
  );
}}
'''


def _render_vite_env_d_ts() -> str:
    return '''/// <reference types="vite/client" />
'''


def _render_use_theme_ts() -> str:
    return '''import { useState, useEffect } from 'react';

export type ThemeMode = 'light' | 'dark';

export function useTheme(): ThemeMode {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof document !== 'undefined') {
      return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    }
    return 'light';
  });

  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          const isDark = document.documentElement.classList.contains('dark');
          setTheme(isDark ? 'dark' : 'light');
        }
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => observer.disconnect();
  }, []);

  return theme;
}
'''


def _render_use_locale_ts() -> str:
    return '''import { useState, useEffect } from 'react';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import type { Locale } from 'antd/es/locale';

export type SupportedLocale = 'zh-CN' | 'en-US';

const localeMap: Record<SupportedLocale, Locale> = {
  'zh-CN': zhCN,
  'en-US': enUS,
};

export function useLocale(): Locale {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof document !== 'undefined') {
      const lang = document.documentElement.lang as SupportedLocale;
      return localeMap[lang] || zhCN;
    }
    return zhCN;
  });

  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'lang') {
          const lang = document.documentElement.lang as SupportedLocale;
          setLocale(localeMap[lang] || zhCN);
        }
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['lang'],
    });

    return () => observer.disconnect();
  }, []);

  return locale;
}
'''


@app.command("create", help="创建插件脚手架项目")
def cmd_create(
    name: Annotated[str, typer.Argument(help="插件名称，仅允许字母、数字、下划线、连字符")],
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="项目输出目录")
    ] = ".",
    description: Annotated[
        str,
        typer.Option("--description", "-d", help="插件描述")
    ] = "",
    author: Annotated[
        str,
        typer.Option("--author", "-a", help="插件作者")
    ] = "",
    plugin_type: Annotated[
        str,
        typer.Option("--type", "-t", help="插件类型: backend(纯后端) / fullstack(全栈)")
    ] = "fullstack",
    load_type: Annotated[
        str,
        typer.Option("--load-type", help="加载类型: hot(热加载) / restart(重启加载)")
    ] = "hot",
):
    """创建一个符合 QuantCell 标准的插件脚手架项目"""
    if not _NAME_RE.match(name):
        typer.echo(f"错误: 插件名称格式不合法: {name}，仅允许字母、数字、下划线、连字符", err=True)
        raise typer.Exit(1)

    if plugin_type not in ("backend", "fullstack"):
        typer.echo(f"错误: 不支持的插件类型: {plugin_type}，可选: backend / fullstack", err=True)
        raise typer.Exit(1)

    if load_type not in ("hot", "restart"):
        typer.echo(f"错误: 不支持的加载类型: {load_type}，可选: hot / restart", err=True)
        raise typer.Exit(1)

    project_dir = os.path.join(output, name)
    if os.path.exists(project_dir):
        typer.echo(f"错误: 目标目录已存在: {project_dir}", err=True)
        raise typer.Exit(1)

    os.makedirs(project_dir, exist_ok=True)

    _write_file(os.path.join(project_dir, "manifest.json"),
                _render_manifest(name, description, author, load_type, plugin_type))
    _write_file(os.path.join(project_dir, "plugin.py"),
                _render_plugin_py(name))

    build_path = os.path.join(project_dir, "build.sh")
    _write_file(build_path, _render_build_sh(name))
    _make_executable(build_path)

    if plugin_type == "fullstack":
        fe_dir = os.path.join(project_dir, "frontend")
        _write_file(os.path.join(fe_dir, "package.json"),
                    _render_frontend_package_json(name, description))
        _write_file(os.path.join(fe_dir, "vite.config.ts"),
                    _render_vite_config_ts(name))
        _write_file(os.path.join(fe_dir, "tsconfig.json"),
                    _render_tsconfig_json())
        _write_file(os.path.join(fe_dir, "tsconfig.node.json"),
                    _render_tsconfig_node_json())
        _write_file(os.path.join(fe_dir, "index.html"),
                    _render_index_html(name))
        _write_file(os.path.join(fe_dir, "src", "main.tsx"),
                    _render_main_tsx(name))
        _write_file(os.path.join(fe_dir, "src", "App.tsx"),
                    _render_app_tsx(name, description))
        _write_file(os.path.join(fe_dir, "src", "vite-env.d.ts"),
                    _render_vite_env_d_ts())
        # 生成主题和国际化 hooks
        _write_file(os.path.join(fe_dir, "src", "hooks", "useTheme.ts"),
                    _render_use_theme_ts())
        _write_file(os.path.join(fe_dir, "src", "hooks", "useLocale.ts"),
                    _render_use_locale_ts())

    typer.echo(f"\n✅ 插件项目已创建: {project_dir}\n")
    typer.echo("项目结构:")
    for root, dirs, files in os.walk(project_dir):
        dirs.sort()
        level = root.replace(project_dir, "").count(os.sep)
        indent = "  " * level
        basename = os.path.basename(root)
        typer.echo(f"{indent}{basename}/")
        sub_indent = "  " * (level + 1)
        for file in sorted(files):
            typer.echo(f"{sub_indent}{file}")

    typer.echo(f"\n下一步:")
    typer.echo(f"  cd {project_dir}")
    if plugin_type == "fullstack":
        typer.echo(f"  cd frontend && bun install && cd ..")
    typer.echo(f"  ./build.sh")
    typer.echo(f"  cd {backend_path.parent}")
    typer.echo(f"  uv run python backend/scripts/plugin_cli.py install --zip {project_dir}/dist/{name}-0.1.0.zip")


if __name__ == "__main__":
    app()
