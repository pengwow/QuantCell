"""CLI 共享辅助 — 路径注入 / 日志 / 错误处理 / 通用选项。

所有 cli/<name>.py 都从这里拿共享行为,不要各自重复定义。
"""

from __future__ import annotations

import functools
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

# === 路径注入:确保 from utils.xxx / from services.xxx 等能 import ===
# 必须在任何 backend import 之前执行
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 暴露 backend_dir 供子模块使用(原 scripts 用的 backend_path)
backend_dir = _BACKEND_DIR

import typer

# 延迟到用到时才 import,避免无谓的启动开销
_logger = None


def get_logger(name: str = "cli"):
    """获取 QuantCell 标准 logger(走 utils.logger)。"""
    global _logger
    if _logger is None:
        from utils.logger import LogType
        from utils.logger import get_logger as _get_logger

        _logger = _get_logger(name, LogType.APPLICATION)
    return _logger


# === JSON 输出 ===
def echo_json(data: dict[str, Any], success: bool = True) -> None:
    """统一 JSON 输出格式,带 success 字段。"""
    output = {"success": success, **data}
    typer.echo(json.dumps(output, ensure_ascii=False, indent=2))


def echo_error(message: str, exit_code: int = 1) -> None:
    """统一错误输出,自动 exit 1。"""
    typer.echo(f"错误: {message}", err=True)
    raise typer.Exit(exit_code)


def echo_success(message: str) -> None:
    """统一成功输出。"""
    typer.echo(message)


# === 异常处理装饰器 ===
F = TypeVar("F", bound=Callable[..., Any])


def handle_errors[F: Callable[..., Any]](func: F) -> F:
    """统一异常处理:捕获异常 → 输出错误 JSON / log → exit 1。

    用法:
        @app.command("foo")
        @handle_errors
        def cmd_foo(...): ...
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise  # 透传 typer.Exit(让 --help / 正常 exit 走原路)
        except Exception as e:
            get_logger().error(f"{func.__name__} 失败: {e}")
            typer.echo(f"错误: {e}", err=True)
            raise typer.Exit(1)

    return wrapper  # type: ignore[return-value]


# === 共享选项 ===
def backend_path_option() -> Path:
    """返回 backend 根目录(原 scripts 用的 backend_path)。"""
    return backend_dir
