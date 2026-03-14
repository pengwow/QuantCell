# -*- coding: utf-8 -*-
"""
后端服务启动脚本

支持自动端口检测和切换功能。

使用示例:
    # 使用默认端口或自动查找可用端口
    python scripts/start_server.py

    # 指定端口启动
    python scripts/start_server.py --port 9000

    # 指定端口范围
    python scripts/start_server.py --port-range 8000 8010

    # 指定主机地址
    python scripts/start_server.py --host 127.0.0.1

    # 启用热重载（开发模式）
    python scripts/start_server.py --reload
"""

import sys
import os
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import typer
import uvicorn
from typing import Optional, Tuple

from utils.logger import get_logger, LogType
from utils.port_manager import get_port_manager

# 获取日志器
logger = get_logger(__name__, LogType.SYSTEM)

# 创建 typer 应用
app = typer.Typer(
    name="start-server",
    help="启动 QuantCell 后端服务",
    add_completion=False,
)


def print_banner(port: int, host: str) -> None:
    """打印启动横幅"""
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                    QuantCell 后端服务                          ║
╠══════════════════════════════════════════════════════════════╣
║  服务地址: http://{host}:{port:<5}                          ║
║  API 文档: http://{host}:{port}/docs                        ║
║  健康检查: http://{host}:{port}/health                      ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


@app.command()
def start(
    port: Optional[int] = typer.Option(
        None,
        "--port",
        "-p",
        help="指定端口，如果不指定则自动查找可用端口",
    ),
    port_range: Optional[Tuple[int, int]] = typer.Option(
        None,
        "--port-range",
        help="指定端口范围 (例如: --port-range 8000 8010)",
    ),
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="主机地址",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        "-r",
        help="启用热重载（开发模式）",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        "-l",
        help="日志级别 (debug, info, warning, error)",
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        help="工作进程数（仅在不使用热重载时有效）",
    ),
) -> None:
    """
    启动 QuantCell 后端服务

    自动检测端口占用并切换到可用端口
    """
    logger.info("=" * 60)
    logger.info("QuantCell 后端服务启动")
    logger.info("=" * 60)

    # 获取端口管理器
    port_manager = get_port_manager()

    # 确定要使用的端口
    try:
        if port is not None:
            # 指定了端口，检查是否可用
            logger.info(f"尝试使用指定端口: {port}")
            if not port_manager.check_port_available(port):
                logger.error(f"指定端口 {port} 已被占用")
                if port_range:
                    # 如果指定了范围，在范围内查找
                    start_port, end_port = port_range
                    logger.info(f"在指定范围 {start_port}-{end_port} 内查找可用端口...")
                    available_port = port_manager.find_available_port(start_port, end_port)
                    if available_port:
                        port = available_port
                        logger.info(f"找到可用端口: {port}")
                    else:
                        logger.error(f"在端口范围 {start_port}-{end_port} 内未找到可用端口")
                        sys.exit(1)
                else:
                    # 使用配置的范围
                    try:
                        port, _ = port_manager.find_backend_port()
                    except RuntimeError as e:
                        logger.error(str(e))
                        sys.exit(1)
            else:
                logger.info(f"指定端口 {port} 可用")
        else:
            # 未指定端口，自动查找
            logger.info("未指定端口，自动查找可用端口...")
            if port_range:
                # 使用命令行指定的范围
                start_port, end_port = port_range
                logger.info(f"在指定范围 {start_port}-{end_port} 内查找...")
                available_port = port_manager.find_available_port(start_port, end_port)
                if available_port:
                    port = available_port
                    logger.info(f"找到可用端口: {port}")
                else:
                    logger.error(f"在端口范围 {start_port}-{end_port} 内未找到可用端口")
                    sys.exit(1)
            else:
                # 使用配置的范围
                try:
                    port, _ = port_manager.find_backend_port()
                except RuntimeError as e:
                    logger.error(str(e))
                    sys.exit(1)

        # 保存端口信息
        port_manager.save_port_info(port, "backend")

        logger.info(f"最终使用端口: {port}")
        logger.info(f"主机地址: {host}")
        logger.info(f"热重载: {'启用' if reload else '禁用'}")
        logger.info(f"日志级别: {log_level.upper()}")

        # 打印横幅
        print_banner(port, host)

        # 启动 uvicorn
        logger.info("正在启动 Uvicorn 服务器...")

        # 设置环境变量，供应用读取
        os.environ["QUANTCELL_BACKEND_PORT"] = str(port)
        os.environ["QUANTCELL_BACKEND_HOST"] = host

        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level.lower(),
            workers=workers if not reload else 1,
        )

    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭服务...")
        # 清理端口信息
        port_manager.clear_port_info("backend")
        sys.exit(0)
    except Exception as e:
        logger.error(f"启动服务时发生错误: {e}")
        # 清理端口信息
        port_manager.clear_port_info("backend")
        sys.exit(1)


@app.command()
def stop() -> None:
    """停止服务并清理端口信息"""
    port_manager = get_port_manager()
    port_manager.clear_port_info("backend")
    logger.info("已清理后端端口信息")


@app.command()
def status() -> None:
    """查看当前端口使用情况"""
    port_manager = get_port_manager()
    all_info = port_manager.get_all_port_info()

    if not all_info:
        logger.info("暂无端口使用信息")
        return

    logger.info("当前端口使用情况:")
    for service, info in all_info.items():
        logger.info(f"  {service}:")
        logger.info(f"    端口: {info.get('port')}")
        logger.info(f"    PID: {info.get('pid')}")
        logger.info(f"    启动时间: {info.get('started_at')}")


if __name__ == "__main__":
    app()
