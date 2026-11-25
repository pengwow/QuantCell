# 系统服务类，处理系统相关的业务逻辑

import asyncio
import platform
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import psutil
from sqlalchemy import func, select

from collector.db.database import SessionLocal
from collector.db.models import CryptoFutureKline, CryptoSpotKline
from config.settings import get_settings
from credentials.service import CredentialsService
from exchange.connection import create_exchange_instance
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 导入WebSocket连接管理器
import contextlib

from websocket.manager import manager

# 首页连接状态探测缓存 TTL（秒），对齐前端首页 60s 轮询周期
_CONN_PROBE_TTL_SECONDS = 60


class ExchangeStatus(Enum):
    """交易所连接状态"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class ExchangeConnectionInfo:
    """交易所连接信息"""

    exchange_name: str
    status: ExchangeStatus
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    reconnect_count: int = 0
    latency_ms: float | None = None
    message_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "exchange_name": self.exchange_name,
            "status": self.status.value,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "last_disconnected_at": self.last_disconnected_at.isoformat() if self.last_disconnected_at else None,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "reconnect_count": self.reconnect_count,
            "latency_ms": self.latency_ms,
            "message_count": self.message_count,
        }


class ExchangeConnectionMonitor:
    """交易所连接状态监测器"""

    def __init__(self):
        """初始化监测器"""
        self._connections: dict[str, ExchangeConnectionInfo] = {}
        self._lock = asyncio.Lock()

    async def register_exchange(self, exchange_name: str) -> ExchangeConnectionInfo:
        """注册交易所"""
        async with self._lock:
            if exchange_name not in self._connections:
                self._connections[exchange_name] = ExchangeConnectionInfo(
                    exchange_name=exchange_name, status=ExchangeStatus.DISCONNECTED
                )
            return self._connections[exchange_name]

    async def update_status(
        self,
        exchange_name: str,
        status: ExchangeStatus,
        error: str | None = None,
        latency_ms: float | None = None,
    ):
        """更新连接状态"""
        async with self._lock:
            if exchange_name not in self._connections:
                await self.register_exchange(exchange_name)

            info = self._connections[exchange_name]
            old_status = info.status
            info.status = status

            # 更新时间戳
            if status == ExchangeStatus.CONNECTED:
                info.last_connected_at = datetime.now()
                # 清除错误信息
                if old_status != ExchangeStatus.CONNECTED:
                    info.last_error = None
            elif status == ExchangeStatus.DISCONNECTED:
                info.last_disconnected_at = datetime.now()
            elif status == ExchangeStatus.ERROR and error:
                info.last_error = error
                info.last_error_at = datetime.now()
            elif status == ExchangeStatus.RECONNECTING:
                info.reconnect_count += 1

            # 更新延迟
            if latency_ms is not None:
                info.latency_ms = latency_ms

    async def increment_message_count(self, exchange_name: str):
        """增加消息计数"""
        async with self._lock:
            if exchange_name in self._connections:
                self._connections[exchange_name].message_count += 1

    def get_connection_info(self, exchange_name: str) -> ExchangeConnectionInfo | None:
        """获取连接信息"""
        return self._connections.get(exchange_name)

    def get_all_connections(self) -> list[ExchangeConnectionInfo]:
        """获取所有连接信息"""
        return list(self._connections.values())

    def get_connections_summary(self) -> dict[str, Any]:
        """获取连接摘要"""
        total = len(self._connections)
        connected = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.CONNECTED)
        disconnected = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.DISCONNECTED)
        error = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.ERROR)
        reconnecting = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.RECONNECTING)

        return {
            "total": total,
            "connected": connected,
            "disconnected": disconnected,
            "error": error,
            "reconnecting": reconnecting,
            "healthy": connected == total and total > 0,
        }


class SystemService:
    """系统服务类，处理系统相关的业务逻辑"""

    def __init__(self):
        """初始化系统服务"""
        # 应用启动时间
        self.start_time = time.time()
        # 系统信息推送定时器
        self.push_timer: asyncio.Task | None = None
        # 最近一次交易所探测明细（含延迟），/system/metrics 直接用
        self._probe_detail: dict[str, dict[str, Any]] = {}
        # 行情库读数缓存（条数/覆盖标的/最新 bar），60s 同 TTL
        self._data_source_cache: tuple[float, dict[str, Any]] | None = None
        # 推送间隔（秒）
        self.push_interval: int = 10
        # 交易所连接监测器
        self.exchange_monitor = ExchangeConnectionMonitor()
        # 交易所状态推送定时器
        self.exchange_push_timer: asyncio.Task | None = None
        # 首页连接状态探测缓存：(time.monotonic 时间戳, 上次探测结论)
        self._conn_probe_cache: tuple[float, str] | None = None
        # CPU 使用率采样缓存：(time.monotonic 时间戳, 上次有效采样值)。
        # 预热基线：macOS 的 CPU 计数器约每秒才刷新一次，短窗口差分恒为 0
        psutil.cpu_percent(interval=None)
        self._cpu_usage_cache: tuple[float, float] | None = None

    def _sample_cpu_usage(self) -> float:
        """CPU 使用率（非阻塞）。

        不能用 ``cpu_percent(interval=0.1)``：macOS 的 CPU 计数器约每秒刷新
        一次，1s 内的差分基本恒为 0，短窗口采样会一直显示 0%。这里改为非阻塞
        采样，距上次采样不足 1s 或撞上计数器未刷新（结果为 0）时复用上次值。
        """
        now = time.monotonic()
        cached = self._cpu_usage_cache
        if cached is not None and now - cached[0] < 1.0:
            return cached[1]
        value = psutil.cpu_percent(interval=None)
        if value == 0.0 and cached is not None:
            return cached[1]
        self._cpu_usage_cache = (now, value)
        return value

    def get_system_info(self) -> dict[str, Any]:
        """获取系统信息

        Returns:
            Dict[str, Any]: 包含系统信息的数据
        """
        try:
            # logger.info("开始获取系统信息")

            # 获取版本信息
            version_info = {
                "system_version": get_settings().app_version,
                "python_version": platform.python_version(),
                "build_date": "2025-11-30",  # 构建日期，可从环境变量或配置文件获取
            }

            # 计算运行时间
            uptime_seconds = time.time() - self.start_time
            days = int(uptime_seconds // (24 * 3600))
            hours = int((uptime_seconds % (24 * 3600)) // 3600)
            uptime_str = f"{days} 天 {hours} 小时"

            # 获取运行状态
            running_status = {
                "uptime": uptime_str,
                "status": "running",
                "status_color": "green",
                "last_check": datetime.now(),
            }

            # 获取资源使用情况
            # CPU使用率
            cpu_usage = psutil.cpu_percent(interval=1)

            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_used = round(memory.used / (1024**3), 2)
            memory_total = round(memory.total / (1024**3), 2)
            memory_str = f"{memory_used}GB / {memory_total}GB"

            # 磁盘空间使用情况
            disk = psutil.disk_usage("/")
            disk_used = round(disk.used / (1024**3), 2)
            disk_total = round(disk.total / (1024**3), 2)
            disk_str = f"{disk_used}GB / {disk_total}GB"

            resource_usage = {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_str,
                "disk_space": disk_str,
            }

            # 构建响应数据
            system_info = {
                "version": version_info,
                "running_status": running_status,
                "resource_usage": resource_usage,
            }

            # logger.info("成功获取系统信息")

            return {
                "success": True,
                "message": "获取系统信息成功",
                "system_info": system_info,
            }
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            return {"success": False, "message": "获取系统信息失败", "error": str(e)}

    def get_system_status(self) -> dict[str, Any]:
        """获取系统状态

        Returns:
            Dict[str, Any]: 包含系统状态的数据
        """
        try:
            # 非阻塞采样，采样间隔不足 1s 时复用上次结果（见 _sample_cpu_usage）
            cpu_usage = self._sample_cpu_usage()

            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_used = round(memory.used / (1024**3), 2)
            memory_total = round(memory.total / (1024**3), 2)
            memory_str = f"{memory_used}GB / {memory_total}GB"
            memory_percent = memory.percent

            # 磁盘空间使用情况
            disk = psutil.disk_usage("/")
            disk_used = round(disk.used / (1024**3), 2)
            disk_total = round(disk.total / (1024**3), 2)
            disk_str = f"{disk_used}GB / {disk_total}GB"
            disk_percent = disk.percent

            system_status = {
                "cpu_usage": cpu_usage,
                "cpu_usage_percent": cpu_usage,
                "memory_usage": memory_str,
                "memory_usage_percent": memory_percent,
                "disk_space": disk_str,
                "disk_space_percent": disk_percent,
                "timestamp": datetime.now().isoformat(),
            }

            # 添加交易所连接状态
            system_status["exchange_connections"] = self.get_exchange_connections_status()

            return system_status
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {
                "cpu_usage": 0,
                "cpu_usage_percent": 0,
                "memory_usage": "0GB / 0GB",
                "memory_usage_percent": 0,
                "disk_space": "0GB / 0GB",
                "disk_space_percent": 0,
                "timestamp": datetime.now().isoformat(),
                "exchange_connections": self.get_exchange_connections_status(),
            }

    def _probe_exchange_connections(self) -> dict[str, dict[str, Any]]:
        """同步探测各交易所公共端点可达性，并记录往返耗时。

        返回值每项为 {ok, latency_ms, checked_at, trading_mode}：latency_ms 是
        health_check（公共行情端点）的实测往返，不是交易所报价延迟，
        不得在 UI 上标成「盘口延迟」。

        探测目标取凭据库已配置账户的去重交易所；未配置或读取失败时退化为默认
        binance（与 engine_status 的默认交易所一致）。health_check 走公共行情
        端点（fetch_time），无需解密 API 密钥。方法内做同步网络 IO，只能在
        线程中执行（get_connection_status 已通过 asyncio.to_thread 调用）。
        """
        try:
            accounts = CredentialsService().list_accounts()
            exchanges = sorted({a.exchange for a in accounts})
        except Exception as e:
            logger.warning(f"读取凭据账户失败，退化为默认探测目标: {e}")
            exchanges = []
        if not exchanges:
            exchanges = ["binance"]

        results: dict[str, dict[str, Any]] = {}
        proxy_url = get_settings().proxy_url
        for name in exchanges:
            t0 = time.monotonic()
            ok = False
            try:
                # QuantCell 主用途是 USDT 永续，按 future 域名探测更贴近真实交易链路
                exchange = create_exchange_instance(exchange_name=name, trading_mode="future", proxy_url=proxy_url)
                ok = bool(exchange.health_check())
            except Exception as e:
                logger.warning(f"交易所 {name} 连接探测失败: {e}")
            results[name] = {
                "ok": ok,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "checked_at": datetime.now().isoformat(),
                "trading_mode": "future",
            }
        self._probe_detail = results
        return results

    async def get_connection_status(self) -> str:
        """真实探测交易所连通性，返回前端连接状态（connected / disconnected）。

        60s TTL 缓存对齐首页轮询周期，失败结果同样缓存防止缓存穿透；
        探测在线程中执行，避免阻塞事件循环。
        """
        now = time.monotonic()
        cached = self._conn_probe_cache
        if cached is not None and now - cached[0] < _CONN_PROBE_TTL_SECONDS:
            return cached[1]

        # 探测是最长 ccxt 默认超时(10s)的同步网络 IO，放线程防止卡死事件循环
        detail = await asyncio.to_thread(self._probe_exchange_connections)
        # 有任何一家交易所可达即视为系统在线（部分中断的明细已记日志）
        status = "connected" if detail and any(d["ok"] for d in detail.values()) else "disconnected"
        logger.info(f"交易所连接探测结果: {[(k, v['ok'], v['latency_ms']) for k, v in detail.items()]} -> {status}")
        self._conn_probe_cache = (now, status)
        return status

    def get_exchange_connections_status(self) -> dict[str, Any]:
        """获取交易所连接状态

        Returns:
            Dict[str, Any]: 交易所连接状态信息
        """
        try:
            # 获取所有连接信息
            connections = self.exchange_monitor.get_all_connections()
            summary = self.exchange_monitor.get_connections_summary()

            # 构建详细连接信息
            connections_detail = []
            for conn in connections:
                conn_dict = conn.to_dict()
                # 添加状态颜色（用于前端展示）
                status_colors = {
                    "connected": "green",
                    "disconnected": "gray",
                    "connecting": "yellow",
                    "error": "red",
                    "reconnecting": "orange",
                }
                conn_dict["status_color"] = status_colors.get(conn.status.value, "gray")
                connections_detail.append(conn_dict)

            return {
                "summary": summary,
                "connections": connections_detail,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"获取交易所连接状态失败: {e}")
            return {
                "summary": {
                    "total": 0,
                    "connected": 0,
                    "disconnected": 0,
                    "error": 0,
                    "reconnecting": 0,
                    "healthy": False,
                },
                "connections": [],
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def get_exchange_probe_detail(self) -> dict[str, Any]:
        """最近一次交易所探测明细。

        延迟 = health_check 公共端点往返实测（与连接状态同一次探测、同 60s 缓存），
        不是交易所报价延迟；未探测过时返回空列表，前端显示「—」。
        """
        if not self._probe_detail:
            return {"exchanges": [], "timestamp": None}
        rows = [
            {
                "exchange": name,
                "ok": bool(info.get("ok")),
                "latency_ms": info.get("latency_ms"),
                "trading_mode": info.get("trading_mode", "future"),
                "checked_at": info.get("checked_at"),
            }
            for name, info in sorted(self._probe_detail.items())
        ]
        return {"exchanges": rows, "timestamp": rows[0]["checked_at"]}

    def get_data_source_status(self) -> dict[str, Any]:
        """本地 K 线库读数：总条数 / 覆盖标的数 / 最新 bar 时间（60s 缓存）。

        首页「行情数据源」行用它说明数据面是否在更新；WS 断线重连计数当前
        没有可信来源（行情 WS 在 Rust 驱动内，Python 侧只有面向浏览器的
        广播管理器），所以这里不提供该字段，前端也不得显示 0 冒充「无重连」。
        """
        now = time.monotonic()
        if self._data_source_cache is not None and now - self._data_source_cache[0] < _CONN_PROBE_TTL_SECONDS:
            return self._data_source_cache[1]

        try:
            with SessionLocal() as db:
                tables = []
                for model in (CryptoSpotKline, CryptoFutureKline):
                    count, latest, symbols = db.execute(
                        select(
                            func.count(model.id),
                            func.max(model.timestamp),
                            func.count(func.distinct(model.symbol)),
                        )
                    ).one()
                    tables.append(
                        {
                            "table": model.__tablename__,
                            "bar_count": int(count or 0),
                            "symbols": int(symbols or 0),
                            "latest_ts": int(latest) if latest is not None else None,
                        }
                    )
        except Exception as e:
            logger.warning(f"读取本地 K 线库读数失败: {e}")
            result: dict[str, Any] = {
                "bar_count": None,
                "symbols": None,
                "latest_at": None,
                "tables": [],
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }
        else:
            latest_ns = max((t["latest_ts"] for t in tables if t["latest_ts"]), default=None)
            result = {
                "bar_count": sum(t["bar_count"] for t in tables),
                "symbols": sum(t["symbols"] for t in tables),
                "latest_at": datetime.fromtimestamp(latest_ns / 1e9).isoformat() if latest_ns else None,
                "tables": tables,
                "timestamp": datetime.now().isoformat(),
            }

        self._data_source_cache = (now, result)
        return result

    async def update_exchange_status(
        self,
        exchange_name: str,
        status: str,
        error: str | None = None,
        latency_ms: float | None = None,
    ):
        """更新交易所连接状态

        Args:
            exchange_name: 交易所名称
            status: 连接状态 (disconnected, connecting, connected, error, reconnecting)
            error: 错误信息（可选）
            latency_ms: 延迟毫秒数（可选）
        """
        try:
            # 转换状态字符串为枚举
            status_enum = ExchangeStatus(status)
            await self.exchange_monitor.update_status(
                exchange_name=exchange_name,
                status=status_enum,
                error=error,
                latency_ms=latency_ms,
            )
            logger.debug(f"交易所 {exchange_name} 状态更新为 {status}")
        except Exception as e:
            logger.error(f"更新交易所状态失败: {e}")

    async def register_exchange(self, exchange_name: str):
        """注册交易所到监测系统

        Args:
            exchange_name: 交易所名称
        """
        try:
            await self.exchange_monitor.register_exchange(exchange_name)
            logger.info(f"交易所 {exchange_name} 已注册到监测系统")
        except Exception as e:
            logger.error(f"注册交易所失败: {e}")

    async def start_system_status_push(self):
        """启动系统状态推送"""
        if not self.push_timer or self.push_timer.done():
            self.push_timer = asyncio.create_task(self._push_system_status_loop())
            logger.info("系统状态推送服务已启动")

    async def stop_system_status_push(self):
        """停止系统状态推送"""
        if self.push_timer and not self.push_timer.done():
            self.push_timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.push_timer
            logger.info("系统状态推送服务已停止")

    async def start_exchange_status_push(self):
        """启动交易所状态推送"""
        if not self.exchange_push_timer or self.exchange_push_timer.done():
            self.exchange_push_timer = asyncio.create_task(self._push_exchange_status_loop())
            logger.info("交易所状态推送服务已启动")

    async def stop_exchange_status_push(self):
        """停止交易所状态推送"""
        if self.exchange_push_timer and not self.exchange_push_timer.done():
            self.exchange_push_timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.exchange_push_timer
            logger.info("交易所状态推送服务已停止")

    async def _push_exchange_status_loop(self):
        """交易所状态推送循环"""
        while True:
            try:
                await self.push_exchange_status()
                await asyncio.sleep(self.push_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易所状态推送失败: {e}")
                await asyncio.sleep(self.push_interval)

    async def push_exchange_status(self):
        """推送交易所状态到前端"""
        try:
            # 获取交易所连接状态
            exchange_status = self.get_exchange_connections_status()

            # 构建交易所状态消息
            message = {
                "type": "exchange_status",
                "id": f"exchange_status_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": exchange_status,
            }

            # 通过WebSocket广播交易所状态
            await manager.broadcast(message, topic="exchange:status")

            logger.debug("交易所状态推送成功")
        except Exception as e:
            logger.error(f"推送交易所状态失败: {e}")

    async def _push_system_status_loop(self):
        """系统状态推送循环"""
        while True:
            try:
                await self.push_system_status()
                await asyncio.sleep(self.push_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"系统状态推送失败: {e}")
                await asyncio.sleep(self.push_interval)

    async def push_system_status(self):
        """推送系统状态到前端"""
        try:
            # 获取系统状态
            system_status = self.get_system_status()

            # 构建系统状态消息
            message = {
                "type": "system_status",
                "id": f"system_status_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": system_status,
            }

            # 通过WebSocket广播系统状态
            await manager.broadcast(message, topic="system:status")

            # logger.debug("系统状态推送成功")
        except Exception as e:
            logger.error(f"推送系统状态失败: {e}")
