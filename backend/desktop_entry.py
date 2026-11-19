"""QuantCell 桌面 sidecar 入口（Tauri 打包专用）。

与 main.py 的 CLI 入口的区别：
- host/port/data-dir 由 Tauri 主进程显式传入，绕过 port_manager 的 8000-8010 范围；
- 在导入任何业务模块前注入 QUANTCELL_DATA_DIR / DB_FILE / PORT_CONFIG_PATH / CORS_ORIGINS，
  保证冻结后的应用只写 Tauri app_data_dir，不写只读的安装包目录；
- uvicorn 直接接收 app 对象，避免 PyInstaller 冻结后 "main:app" 字符串导入失效。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import typer

# macOS/Linux WebView origin 为 tauri://localhost，Windows 为 http://tauri.localhost；
# 1420 是 M1 桌面 UI 的 Vite 端口，5173 是 M2 复用 frontend 的 Vite 端口
_DEFAULT_CORS_ORIGINS = (
    "tauri://localhost,http://tauri.localhost,"
    "http://localhost:1420,http://127.0.0.1:1420,"
    "http://localhost:5173,http://127.0.0.1:5173"
)


def build_runtime_env(data_dir: str) -> dict[str, str]:
    """根据数据目录推导 sidecar 运行环境变量（纯函数，便于单测）。"""
    root = Path(data_dir)
    return {
        "QUANTCELL_DATA_DIR": str(root),
        # 与 collector.db.database 默认 sqlite 文件名保持一致
        "DB_FILE": str(root / "quantcell_sqlite.db"),
        # 端口记录文件也放进数据目录，避免多实例/多用户串写
        "PORT_CONFIG_PATH": str(root / "port_config.json"),
        "CORS_ORIGINS": _DEFAULT_CORS_ORIGINS,
        # 桌面 local 模式免登录标记：仅本 sidecar 进程内生效，
        # utils.auth 读取；APP_ENV=production 时该豁免被强制忽略
        "QUANTCELL_DESKTOP_LOCAL": "1",
        # matplotlib 缓存钉到持久目录：默认落 HOME 缓存（冻结 env 下曾每次
        # 重建字体缓存 fontList.json，实测每次启动 +5-10s）
        "MPLCONFIGDIR": str(root / "mpl-cache"),
    }


def apply_runtime_env(data_dir: str) -> None:
    """创建数据目录并把环境变量注入当前进程（必须在导入业务模块前调用）。"""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for key, value in build_runtime_env(data_dir).items():
        os.environ[key] = value


def _parse_system_proxy(scutil_output: str) -> str | None:
    """解析 `scutil --proxy` 输出，HTTPEnable=1 且 host/port 齐全时返回代理 URL。"""

    def _val(key: str) -> str | None:
        m = re.search(rf"^[ \t]*{key}\s*:\s*(\S+)$", scutil_output, re.MULTILINE)
        return m.group(1) if m else None

    if _val("HTTPEnable") != "1":
        return None
    host, port = _val("HTTPProxy"), _val("HTTPPort")
    if not host or not port:
        return None
    return f"http://{host}:{port}"


def inherit_system_proxy() -> None:
    """继承 macOS 系统代理到 PROXY_URL（显式 env 永远优先，幂等可重复）。

    桌面实录：Finder/launchd 启动的 sidecar 拿不到用户 shell 环境里的
    PROXY_URL/HTTP_PROXY，backend/.env 又按 CWD 解析不可达（CWD=/，与
    data/ 相对路径同族问题），交易所连通性探测直连 binance 失败 →
    首页"系统离线"。clash/v2ray 类代理内核会把 HTTP 代理写入系统代理，
    `scutil --proxy` 即得。
    ponytail: 解析失败静默维持直连——现状不可能更坏；Windows/Linux 平台待补。
    """
    if os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"):
        return
    try:
        out = subprocess.run(
            ["/usr/sbin/scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except Exception:
        return
    proxy = _parse_system_proxy(out)
    if proxy:
        os.environ["PROXY_URL"] = proxy
        print(f"[desktop] inherit system proxy for exchange probe: {proxy}", file=sys.stderr)


def apply_extensions_path(data_dir: str) -> None:
    """把已安装扩展的 site-packages 注入 sys.path 头部。

    PEP 302 fallback：PyInstaller FrozenImporter 在归档内查不到 torch 等模块时，
    会继续交给 sys.path 上的外部 path finder；必须在导入 main（业务模块）前调用。
    """
    base = Path(data_dir) / "extensions"
    if not base.is_dir():
        return
    for sp in sorted(base.glob("*/site-packages")):
        if sp.is_dir():
            sys.path.insert(0, str(sp))


def main(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(..., "--port", help="Tauri 分配的端口（必填）"),
    data_dir: str = typer.Option(..., "--data-dir", help="Tauri app_data_dir（必填）"),
) -> None:
    """启动桌面 sidecar：先落 env，再初始化 DB，最后起 uvicorn。"""
    apply_runtime_env(data_dir)
    inherit_system_proxy()
    apply_extensions_path(data_dir)

    import uvicorn

    from collector.db import init_db

    init_db()

    # 首次建库补齐共享 Base 之外的两张表（thinking_chains / strategy_history）：
    # 两个模型模块为避免循环导入了独立 declarative_base，init_db() 的 create_all
    # 覆盖不到；此前全新桌面库上 AI 模型策略历史/思维链接口直接报 no such table
    # （backend/init_db.py 文档字符串同样记录了该缺口）。幂等可重复执行。
    from init_db import create_aux_tables

    create_aux_tables()

    # 在 env 注入之后再导入 app，保证配置/路径在模块加载时已被重定向
    from main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    typer.run(main)
