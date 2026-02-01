import ccxt.pro as ccxtpro
import asyncio


symbol = 'BTC/USDT'


async def main():
    try:
            # 创建交易所实例
        exchange_instance = ccxtpro.binance()
        exchange_instance.timeout = 30000  # 增加超时时间到30秒
        exchange_instance.enableRateLimit = True  # 启用速率限制
        exchange_instance.http_proxy = 'http://127.0.0.1:7897'

        # exchange_instance.socksProxy = 'socks5://127.0.0.1:7897';
        # ccxt库的代理配置应该使用proxies属性（字典格式）
        # exchange_instance.proxies = {
        #     'http': "http://127.0.0.1:7897",
        #     'https': "http://127.0.0.1:7897",
        #     'wss': "http://127.0.0.1:7897",
        #     'ws': "http://127.0.0.1:7897",
        # }
        # exchange_instance.UpdateProxySettings()
        # res2 = await exchange_instance.load_markets()
        # print(res2)
        while True:
            try:
                trades = await exchange_instance.watch_trades(symbol)
                print(trades)
                ohlcvc = exchange_instance.build_ohlcvc(trades, '1m')
                print(ohlcvc)
                print(ohlcvc[-1])
            except Exception as e:
                print(f"Error: {e}")
                break
                # stop the loop on exception or leave it commented to retry
                # raise e
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("finally")
        await exchange_instance.close()
if __name__ == '__main__':
    asyncio.run(main())

# import requests

# req = requests.get('https://api.binance.com/api/v3/exchangeInfo')
# print(req.json())