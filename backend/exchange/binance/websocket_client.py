"""
Binance WebSocket客户端

实现AbstractExchangeClient接口的WebSocket客户端，用于实时数据订阅
包含自动重连和连接状态监控功能
"""

import asyncio
import json
import os
import re
import time
from typing import TYPE_CHECKING, Any

from binance import AsyncClient
from binance.ws.streams import BinanceSocketManager

from utils.logger import LogType, get_logger
from utils.proxy import resolve_proxy

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from realtime.abstract_client import AbstractExchangeClient

from .config import BinanceConfig

# 排障插桩开关：QC_WS_DEBUG=1 时输出每轮接收循环的耗时与结果类型（默认关闭）
_WS_DEBUG = os.environ.get("QC_WS_DEBUG") == "1"

if TYPE_CHECKING:
    from collections.abc import Callable


class BinanceWebSocketClient(AbstractExchangeClient):
    """
    Binance WebSocket客户端

    实现AbstractExchangeClient接口，提供实时数据订阅功能
    支持自动重连和连接状态监控
    """

    exchange_name: str = "binance"

    def __init__(self, config: BinanceConfig | None = None):
        """
        初始化Binance WebSocket客户端

        Args:
            config: Binance配置
        """
        # 将BinanceConfig转换为字典格式
        if config is None:
            config = BinanceConfig()

        config_dict = {
            "api_key": config.api_key,
            "api_secret": config.api_secret,
            "testnet": config.testnet,
            "tld": config.tld,
            "proxy_url": config.proxy_url,
        }

        super().__init__(config_dict)
        self._binance_config = config
        self._client: AsyncClient | None = None
        self._socket_manager: BinanceSocketManager | None = None
        self._connected = False
        self._active_sockets: dict[str, Any] = {}
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._receive_task: asyncio.Task | None = None
        # 断流自愈待重试表：channel -> [下次重试时刻(monotonic), 已尝试次数]。
        # python-binance 的 ReconnectingWebsocket 读循环在连续 5 次重连失败后会
        # 永久退出（之后 recv() 抛 ReadLoopClosed），仅依赖其内置自愈不够；
        # 曾导致 BTCUSDT@aggTrade 死后无限期断流（trades 广播全灭）。
        self._resubscribe_due: dict[str, list[float]] = {}

        # 重连相关
        self._reconnect_enabled = True
        self._reconnect_delay = 5.0  # 重连延迟（秒）
        self._max_reconnect_attempts = 3
        self._reconnect_attempts = 0
        self._last_ping_time = 0
        self._ping_interval = 30  # ping间隔（秒）

        logger.info("BinanceWebSocketClient initialized")

    async def connect(self) -> bool:
        """
        建立WebSocket连接

        Returns:
            bool: 连接是否成功
        """
        try:
            # 如果已连接，先断开
            if self._connected:
                await self.disconnect()

            # 本机直连 binance 域名不可达，REST 与 WS 统一走项目代理解析。
            # python-binance 默认超时 10s，testnet REST 偶发 >10s（2026-11-15 21:00 实测
            # 连接耗时 10.088s 报空 TimeoutError），放宽到 30s 吸收抖动。
            proxy = self.config.get("proxy_url") or resolve_proxy()
            self._client = await AsyncClient.create(
                api_key=self.config.get("api_key"),
                api_secret=self.config.get("api_secret"),
                testnet=self.config.get("testnet", True),
                tld=self.config.get("tld", "com"),
                https_proxy=proxy,
                requests_params={"timeout": 30},
            )

            # 创建Socket管理器
            self._socket_manager = BinanceSocketManager(self._client)

            self._connected = True
            self._reconnect_attempts = 0
            self._last_ping_time = time.time()

            logger.info("Binance WebSocket client connected successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to connect Binance WebSocket: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        """
        断开WebSocket连接

        Returns:
            bool: 断开是否成功
        """
        try:
            self._connected = False

            # 取消接收任务
            if self._receive_task:
                try:
                    self._receive_task.cancel()
                    # 等待任务取消，设置超时
                    await asyncio.wait_for(asyncio.shield(self._receive_task), timeout=2.0)
                except asyncio.CancelledError:
                    pass
                except TimeoutError:
                    logger.warning("接收任务取消超时")
                except Exception as e:
                    logger.warning(f"等待接收任务取消时出错: {e}")
                finally:
                    self._receive_task = None

            # 关闭所有活跃的socket
            close_tasks = []
            for channel, socket in list(self._active_sockets.items()):
                try:
                    if hasattr(socket, "close"):
                        close_tasks.append(socket.close())
                except Exception as e:
                    logger.warning(f"准备关闭socket {channel} 时出错: {e}")

            if close_tasks:
                try:
                    await asyncio.gather(*close_tasks, return_exceptions=True)
                except Exception as e:
                    logger.warning(f"关闭socket时出错: {e}")

            self._active_sockets.clear()

            # 关闭客户端连接
            if self._client:
                try:
                    await asyncio.wait_for(self._client.close_connection(), timeout=3.0)
                except TimeoutError:
                    logger.warning("关闭客户端连接超时")
                except Exception as e:
                    logger.warning(f"关闭客户端连接时出错: {e}")
                finally:
                    self._client = None

            self._socket_manager = None

            logger.info("Binance WebSocket client disconnected")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting Binance WebSocket: {e}")
            return False

    async def _reconnect(self) -> bool:
        """
        尝试重新连接

        Returns:
            bool: 重连是否成功
        """
        if not self._reconnect_enabled:
            return False

        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"Max reconnection attempts ({self._max_reconnect_attempts}) reached")
            return False

        self._reconnect_attempts += 1
        logger.info(f"Attempting to reconnect... (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})")

        # 保存当前订阅的频道
        saved_channels = list(self.subscribed_channels)

        # 断开当前连接
        await self.disconnect()

        # 等待重连延迟
        await asyncio.sleep(self._reconnect_delay)

        # 尝试重新连接
        if await self.connect():
            # 重新订阅之前的频道
            if saved_channels:
                logger.info(f"Resubscribing to {len(saved_channels)} channels")
                await self.subscribe(saved_channels)
            return True

        return False

    async def subscribe(self, channels: list[str]) -> bool:
        """
        订阅指定的WebSocket频道

        Args:
            channels: 要订阅的频道列表，格式如 ["BTCUSDT@kline_1m", "ETHUSDT@depth"]

        Returns:
            bool: 订阅是否成功
        """
        try:
            # 连接丢失时现场重连：engine/ws_manager 的 connected 标志可能滞后于
            # 真实链路（断线重连耗尽后无人回写），订阅请求不能依赖上游标志
            if not self._connected or not self._socket_manager:
                logger.warning("WebSocket not connected, attempting reconnect before subscribe")
                if not await self.connect():
                    logger.error("WebSocket not connected and reconnect failed")
                    return False

            for channel in channels:
                try:
                    # 如果已经订阅，跳过
                    if channel in self._active_sockets:
                        logger.debug(f"Channel {channel} already subscribed")
                        continue

                    # 解析频道名
                    if "@" in channel:
                        symbol_raw, stream_type = channel.split("@", 1)
                    else:
                        logger.warning(f"Invalid channel format: {channel}")
                        continue
                    # symbol 必须清洗为币安流名格式（ETHUSDT）：带分隔符（如 ETH/USDT）
                    # 会拼出 /ws/eth/usdt@… 的斜杠路径，服务端静默不推流
                    symbol = symbol_raw.replace("/", "").replace(":", "").upper()

                    # depth 系流名先做一次解析：无层数（depth、depth@100ms）是全量 diff 流，
                    # 带层数（depth20、depth20@100ms）是部分订单簿快照流
                    depth_match = re.match(r"^depth(\d+)?(?:@(\d+)ms)?$", stream_type)

                    # 根据类型创建对应的socket
                    if stream_type.startswith("kline_"):
                        interval = stream_type.split("_", 1)[1]
                        socket = self._socket_manager.kline_socket(symbol=symbol, interval=interval)
                    elif depth_match is not None:
                        if depth_match.group(1):
                            # 快照流：@Nms 后缀透传刷新率——不传默认 1s 推一条（订单簿慢的根因），
                            # depth_socket 仅支持 None/0/100，故仅 100ms 映射为 interval=100，
                            # 其余后缀（如显式 1000ms）按默认 1s
                            interval_ms = int(depth_match.group(2)) if depth_match.group(2) else None
                            update_interval = 100 if interval_ms == 100 else None
                            socket = self._socket_manager.depth_socket(
                                symbol=symbol, depth=depth_match.group(1), interval=update_interval
                            )
                        else:
                            # 全量 diff 增量流，保持旧行为
                            socket = self._socket_manager.depth_socket(symbol=symbol)
                    elif stream_type == "aggTrade":
                        # 聚合成交流（python-binance 方法名为 aggtrade_socket）
                        socket = self._socket_manager.aggtrade_socket(symbol=symbol)
                    elif stream_type == "trade":
                        socket = self._socket_manager.trade_socket(symbol=symbol)
                    elif stream_type == "ticker":
                        socket = self._socket_manager.ticker_socket(symbol=symbol)
                    else:
                        logger.warning(f"Unsupported stream type: {stream_type}")
                        continue

                    # 建立WebSocket连接
                    try:
                        await socket.connect()
                        logger.info(f"Socket connected for channel: {channel}")
                    except Exception as e:
                        logger.error(f"Failed to connect socket for {channel}: {e}")
                        continue

                    # 存储socket引用
                    self._active_sockets[channel] = socket
                    self.subscribed_channels.add(channel)

                    logger.info(f"Subscribed to channel: {channel}")

                except Exception as e:
                    logger.error(f"Failed to subscribe to {channel}: {e}")
                    continue

            # 启动消息接收任务（如果未启动）
            if not self._receive_task or self._receive_task.done():
                self._receive_task = asyncio.create_task(self._receive_messages())

            return True

        except Exception as e:
            logger.error(f"Error subscribing to channels: {e}")
            return False

    async def unsubscribe(self, channels: list[str]) -> bool:
        """
        取消订阅指定的WebSocket频道

        Args:
            channels: 要取消订阅的频道列表

        Returns:
            bool: 取消订阅是否成功
        """
        try:
            for channel in channels:
                if channel in self._active_sockets:
                    try:
                        socket = self._active_sockets.pop(channel)
                        if hasattr(socket, "close"):
                            await socket.close()
                    except Exception as e:
                        logger.warning(f"Error closing socket {channel}: {e}")

                    if channel in self.subscribed_channels:
                        self.subscribed_channels.remove(channel)

                    logger.info(f"Unsubscribed from channel: {channel}")

            return True

        except Exception as e:
            logger.error(f"Error unsubscribing from channels: {e}")
            return False

    async def receive_message(self) -> dict[str, Any] | None:
        """
        接收并处理WebSocket消息

        Returns:
            Optional[Dict[str, Any]]: 处理后的消息
        """
        # 实际的消息接收在_receive_messages中处理
        # 这里返回None，因为消息通过回调处理
        return None

    async def _receive_messages(self):
        """
        后台任务：接收所有活跃socket的消息（优化版：并发接收）
        包含连接断开检测和自动重连逻辑
        """
        consecutive_errors = 0
        max_consecutive_errors = 5
        # 每轮每 socket 最多排空的缓冲消息数：首条到达后连读已缓冲报文，
        # 避免旧实现每轮只搬 1 条把 @100ms 订单簿（10Hz）等高频流拖成秒级
        max_drain_per_round = 20

        async def receive_from_socket(channel: str, socket):
            """从单个socket接收本轮已到达的消息（最多 max_drain_per_round 条）"""
            try:
                # 检查socket是否已关闭
                if hasattr(socket, "_conn") and socket._conn is None:
                    logger.warning(f"Socket {channel} connection is None, removing")
                    return {"type": "socket_closed", "channel": channel}

                messages = []
                # 首条消息等待 0.1s：静默 socket 靠超时让路，活跃 socket 立即返回
                msg = await asyncio.wait_for(socket.recv(), timeout=0.1)

                # 后续消息用 1ms 短超时当非阻塞探询，只排空已缓冲的报文
                while msg:
                    data = json.loads(msg) if isinstance(msg, str) else msg
                    # 添加频道信息
                    data["channel"] = channel
                    messages.append(data)
                    if len(messages) >= max_drain_per_round:
                        break
                    try:
                        msg = await asyncio.wait_for(socket.recv(), timeout=0.001)
                    except TimeoutError:
                        break

                if messages:
                    return {"type": "messages", "data_list": messages}

            except TimeoutError:
                # 超时是正常的
                return None
            except Exception as e:
                error_msg = str(e).lower()
                # 检查是否是连接关闭的错误
                if (
                    "read loop has been closed" in error_msg
                    or "websocket connection is closed" in error_msg
                    or "connection reset" in error_msg
                ):
                    logger.warning(f"Socket {channel} connection closed: {e}")
                    return {"type": "socket_closed", "channel": channel}
                else:
                    logger.error(f"Error receiving message from {channel}: {e}")
                    return {"type": "error", "channel": channel, "error": e}

            return None

        try:
            while self._connected:
                try:
                    has_message = False

                    # 断流自愈：每轮先处理到期的重订阅（指数退避 2s→4s→…→30s 封顶）
                    await self._run_resubscribe_due()
                    if _WS_DEBUG:
                        _round_start = time.perf_counter()

                    # 检查是否需要发送ping保持连接
                    current_time = time.time()
                    if current_time - self._last_ping_time > self._ping_interval:
                        # 更新ping时间
                        self._last_ping_time = current_time

                    # 并发从所有socket接收消息
                    if self._active_sockets:
                        tasks = [
                            receive_from_socket(channel, socket) for channel, socket in self._active_sockets.items()
                        ]

                        # 等待所有任务完成，设置整体超时
                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        # 处理结果
                        for result in results:
                            if isinstance(result, Exception):
                                consecutive_errors += 1
                                continue

                            if result is None:
                                continue

                            if result["type"] == "messages":
                                has_message = True
                                consecutive_errors = 0
                                # 调用回调（使用create_task避免阻塞）
                                for data in result["data_list"]:
                                    for callback in self._callbacks:
                                        try:
                                            callback(data)
                                        except Exception as e:
                                            logger.error(f"[KlinePush] 回调函数执行失败: {e}")

                            elif result["type"] == "socket_closed":
                                channel = result["channel"]
                                self._active_sockets.pop(channel, None)
                                consecutive_errors += 1
                                # 登记 1 秒后重试：仅从活跃表移除会让频道无限期断流
                                # （全局 _reconnect 需连续 5 轮错误，而健康流消息会
                                # 持续清零计数器，实际永远触发不了）
                                if channel in self.subscribed_channels:
                                    next_due = time.monotonic() + 1.0
                                    self._resubscribe_due.setdefault(channel, [next_due, 0])
                                    logger.warning(f"Socket {channel} closed, resubscribe scheduled")

                            elif result["type"] == "error":
                                consecutive_errors += 1

                    # 如果没有活跃的socket，退出循环
                    if not self._active_sockets and self.subscribed_channels:
                        logger.warning("No active sockets but channels still subscribed")
                        consecutive_errors += 1

                    # 如果连续错误过多，尝试重连
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning(f"Too many consecutive errors ({consecutive_errors}), attempting reconnect")
                        if await self._reconnect():
                            consecutive_errors = 0
                        else:
                            logger.error("Reconnection failed")
                            break

                    # 短暂休眠避免CPU占用过高（如果没有消息，减少CPU使用）
                    await asyncio.sleep(0.001 if has_message else 0.01)

                    if _WS_DEBUG:
                        _dur = (time.perf_counter() - _round_start) * 1000
                        _parts = []
                        for _chan, _res in zip(self._active_sockets.keys(), results, strict=False):
                            if isinstance(_res, Exception):
                                _parts.append(f"{_chan}:EXC:{type(_res).__name__}")
                            elif _res is None:
                                _parts.append(f"{_chan}:-")
                            elif _res["type"] == "messages":
                                _parts.append(f"{_chan}x{len(_res['data_list'])}")
                            else:
                                _parts.append(f"{_chan}:{_res['type']}")
                        # 插桩日志走 DEBUG 级别：不能污染 INFO 层常规日志，需 LOG_LEVEL=DEBUG 才可见
                        logger.debug(f"[WSDebug] round={_dur:.1f}ms {' '.join(_parts)}")

                except Exception as e:
                    logger.error(f"Error in message receive loop: {e}")
                    consecutive_errors += 1
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.info("Message receive task cancelled")
        except Exception as e:
            logger.error(f"Fatal error in receive messages loop: {e}")
        finally:
            logger.info("Message receive task ended")

    async def _run_resubscribe_due(self) -> None:
        """断流自愈：重试登记在 _resubscribe_due 里的频道（指数退避）。

        重订阅成功判定 = channel 回到 _active_sockets（subscribe 内部对连接
        失败的频道不会登记）；失败则按 2^n 秒退避（封顶 30s）继续排队。
        用户显式退订（已从 subscribed_channels 移除）的频道直接剔除，不再自愈。
        """
        if not self._resubscribe_due:
            return
        now = time.monotonic()
        for channel, state in list(self._resubscribe_due.items()):
            due, attempts = state
            if now < due:
                continue
            if channel not in self.subscribed_channels:
                # 用户已显式退订，停止自愈
                self._resubscribe_due.pop(channel, None)
                continue
            try:
                await self.subscribe([channel])
            except Exception as e:
                logger.warning(f"Resubscribe {channel} attempt {attempts + 1} error: {e}")
            if channel in self._active_sockets:
                self._resubscribe_due.pop(channel, None)
                logger.info(f"Socket {channel} resubscribed successfully")
            else:
                wait = min(2.0**attempts, 30.0)
                self._resubscribe_due[channel] = [now + wait, attempts + 1]
                logger.warning(f"Resubscribe {channel} attempt {attempts + 1} failed, retry in {wait:.0f}s")

    @property
    def is_connected(self) -> bool:
        """
        检查是否已连接

        必须是 property（对齐抽象基类契约）：websocket_manager 的断线监控与
        状态上报以属性方式访问 `client.is_connected`，若定义为普通方法，
        拿到的是恒为真值的 bound method，断线检测将永远失效。
        """
        return self._connected and self._client is not None

    def get_connection_status(self) -> dict[str, Any]:
        """
        获取连接状态信息

        Returns:
            Dict[str, Any]: 连接状态
        """
        return {
            "connected": self._connected,
            "active_sockets": len(self._active_sockets),
            "subscribed_channels": len(self.subscribed_channels),
            "reconnect_attempts": self._reconnect_attempts,
        }

    def get_data_parser(self):
        """
        获取数据解析器实例

        Returns:
            Any: 数据解析器实例
        """
        return BinanceDataParser()

    def get_available_channels(self) -> list[str]:
        """
        获取交易所支持的频道列表

        Returns:
            List[str]: 支持的频道列表
        """
        return [
            "kline",
            "depth",
            "trade",
            "ticker",
            "miniTicker",
            "bookTicker",
            "aggTrade",
        ]

    def add_message_callback(self, callback: Callable[[dict[str, Any]], None]):
        """
        添加消息回调函数

        Args:
            callback: 回调函数，接收消息字典
        """
        self._callbacks.append(callback)

    def remove_message_callback(self, callback: Callable[[dict[str, Any]], None]):
        """
        移除消息回调函数

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)


class BinanceDataParser:
    """Binance数据解析器"""

    def parse_kline(self, data: dict[str, Any]) -> dict[str, Any]:
        """解析K线数据"""
        k = data.get("k", {})
        return {
            "symbol": k.get("s"),
            "open_time": k.get("t"),
            "close_time": k.get("T"),
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
            "quote_volume": float(k.get("q", 0)),
            "trades": k.get("n", 0),
            "interval": k.get("i"),
            "is_final": k.get("x", False),
        }

    def parse_depth(self, data: dict[str, Any]) -> dict[str, Any]:
        """解析深度数据"""
        return {
            "symbol": data.get("s"),
            "last_update_id": data.get("u"),
            "bids": [[float(p), float(q)] for p, q in data.get("b", [])],
            "asks": [[float(p), float(q)] for p, q in data.get("a", [])],
        }

    def parse_trade(self, data: dict[str, Any]) -> dict[str, Any]:
        """解析交易数据"""
        return {
            "symbol": data.get("s"),
            "trade_id": data.get("t"),
            "price": float(data.get("p", 0)),
            "quantity": float(data.get("q", 0)),
            "trade_time": data.get("T"),
            "is_buyer_maker": data.get("m", False),
        }
