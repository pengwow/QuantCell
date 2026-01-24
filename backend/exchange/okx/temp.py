import asyncio

from okx.websocket.WsPublicAsync import WsPublicAsync
from okx.Account import AccountAPI

def publicCallback(message):
    print("publicCallback", message)

API_KEY = "7361a754-6fcf-4d8c-a81e-82abe6419911"
API_KEY_SECRET = "D44AF42935AF27262DDFE4DDE3B63103"
API_PASSPHRASE = "lwobqobj6L.."
IS_PAPER_TRADING = True
async def main():
    
    # url = "wss://wspap.okex.com:8443/ws/v5/public?brokerId=9999"
    url = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
    ws = WsPublicAsync(url=url)
    await ws.start()
    args = []
    # arg1 = {"channel": "instruments", "instType": "FUTURES"}
    arg2 = {"channel": "instruments", "instType": "SPOT"}
    # arg3 = {"channel": "tickers", "instId": "BTC-USDT-SWAP"}
    # arg4 = {"channel": "tickers", "instId": "ETH-USDT"}
    # args.append(arg1)
    # args.append(arg2)
    # args.append(arg3)
    # args.append(arg4)
    # args.append({"channel": "open-interest", "instId": "LTC-USD-SWAP"})
    # args.append({"channel": "mark-price-candle1D", "instId": "BTC-USD"})
    args.append({"channel": "books", "instId": "BTC-USDT-SWAP"})
    await ws.subscribe(args, publicCallback)
    await asyncio.sleep(5)
    await ws.unsubscribe(args, publicCallback)

    # print("-----------------------------------------unsubscribe--------------------------------------------")
    # args2 = [arg4]
    # await ws.unsubscribe(args2, publicCallback)
    # await asyncio.sleep(5)
    # print("-----------------------------------------unsubscribe all--------------------------------------------")
    # args3 = [arg1, arg2, arg3]
    # await ws.unsubscribe(args3, publicCallback)
    account_api = AccountAPI(api_key=API_KEY, api_secret_key=API_KEY_SECRET, passphrase=API_PASSPHRASE,
                                      flag='0' if not IS_PAPER_TRADING else '1', debug=False, proxy='http://127.0.0.1:7890')
    res = account_api.get_account_config()
    print(res)

if __name__ == '__main__':
    asyncio.run(main())