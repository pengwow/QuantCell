"""
QuantCell CLI 入口（`quantcell` 命令 / `python -m cli` 共用）。

子命令注册放在 main() 中延迟执行，确保 import cli 包本身无副作用，
`python -m cli.<子模块>` 时不会被其他子模块的导入日志污染 stdout。
"""

from cli import app, register_commands


def main() -> None:
    """注册所有子命令并启动 CLI。"""
    register_commands()
    app()


if __name__ == "__main__":
    main()
