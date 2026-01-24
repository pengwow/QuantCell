import asyncio
import json
import logging

from okx_market_maker.utils.CustomWebSocketFactory import CustomWebSocketFactory

logger = logging.getLogger(__name__)


class CustomWsPublicAsync:
    def __init__(self, url, proxy_host=None, proxy_port=None, proxy_type=None):
        self.url = url
        self.subscriptions = set()
        self.callback = None
        self.loop = asyncio.get_event_loop()
        self.factory = CustomWebSocketFactory(url, proxy_host=proxy_host, proxy_port=proxy_port, proxy_type=proxy_type)

    async def connect(self):
        self.websocket = await self.factory.connect()

    async def consume(self):
        async for message in self.websocket:
            logger.debug("Received message: {%s}", message)
            if self.callback:
                self.callback(message)

    async def subscribe(self, params: list, callback):
        self.callback = callback
        payload = json.dumps({
            "op": "subscribe",
            "args": params
        })
        await self.websocket.send(payload)
        # await self.consume()

    async def unsubscribe(self, params: list, callback):
        self.callback = callback
        payload = json.dumps({
            "op": "unsubscribe",
            "args": params
        })
        logger.info(f"unsubscribe: {payload}")
        await self.websocket.send(payload)

    async def stop(self):
        await self.factory.close()
        self.loop.stop()

    async def start(self):
        logger.info("Connecting to WebSocket...")
        await self.connect()
        self.loop.create_task(self.consume())

    def stop_sync(self):
        # 如果事件循环已在运行，则直接调度stop协程
        if self.loop.is_running():
            self.loop.create_task(self.stop())
        else:
            self.loop.run_until_complete(self.stop())