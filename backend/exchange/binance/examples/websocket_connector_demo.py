import asyncio
import logging
import os
from pathlib import Path
import sys
from binance_common.models import WebsocketApiResponse
# 添加项目根目录到Python路径
backend_root = Path(__file__).parent.parent.parent.parent

project_root = backend_root.parent 

sys.path.append(str(project_root))
from backend.exchange.binance.websocket_connector import BinanceWebSocketConnector

# Configure logging
logging.basicConfig(level=logging.INFO)


def my_callback(data: WebsocketApiResponse):
    """
    用户自定义回调函数
    
    Args:
        data (WebsocketApiResponse): WebSocket 响应数据
    """
    print(f"收到数据: {data.e}")
    if hasattr(data, 'data') and data.data:
        print(f"数据内容: {data.data}")


async def main():
    """
    主函数，演示如何使用 BinanceWebSocketConnector
    """
    # 创建连接器实例
    proxy = {
        "host": "192.168.3.28",
        "port": 7893,
        "protocol": "http",
    }
    
    # 从环境变量获取 API 密钥，或者可以在这里直接指定
    api_key = os.getenv("BINANCE_API_KEY")
    secret_key = os.getenv("BINANCE_SECRET_KEY")
    
    connector = BinanceWebSocketConnector(api_key=api_key, secret_key=secret_key, proxy=proxy)
    
    # 设置回调函数
    connector.set_callback(my_callback)
    
    try:
        # 连接到 WebSocket
        await connector.connect("mark_price_stream", symbol="btcusdt")
        
        # 保持运行
        await connector.run_forever()
    except KeyboardInterrupt:
        logging.info("程序被用户中断")
    except Exception as e:
        logging.error(f"程序运行出错: {e}")
    finally:
        # 断开连接
        await connector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())