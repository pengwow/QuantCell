"""QuantCell 桌面 sidecar 入口（Tauri 打包专用）。

与 main.py 的 CLI 入口的区别：
- host/port/data-dir 由 Tauri 主进程显式传入，绕过 port_manager 的 8000-8010 范围；
- 在导入任何业务模块前注入 QUANTCELL_DATA_DIR / DB_FILE / PORT_CONFIG_PATH / CORS_ORIGINS，
  保证冻结后的应用只写 Tauri app_data_dir，不写只读的安装包目录；
- uvicorn 直接接收 app 对象，避免 PyInstaller 冻结后 "main:app" 字符串导入失效。
"""

from __future__ import annotations

import os
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
    }


def apply_runtime_env(data_dir: str) -> None:
    """创建数据目录并把环境变量注入当前进程（必须在导入业务模块前调用）。"""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for key, value in build_runtime_env(data_dir).items():
        os.environ[key] = value


def main(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(..., "--port", help="Tauri 分配的端口（必填）"),
    data_dir: str = typer.Option(..., "--data-dir", help="Tauri app_data_dir（必填）"),
) -> None:
    """启动桌面 sidecar：先落 env，再初始化 DB，最后起 uvicorn。"""
    apply_runtime_env(data_dir)

    import uvicorn

    from collector.db import init_db

    init_db()

    # 在 env 注入之后再导入 app，保证配置/路径在模块加载时已被重定向
    from main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    typer.run(main)
