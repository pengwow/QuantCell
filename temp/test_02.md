要通过币安（Binance）交易所API获取货币对（交易对）的24小时涨跌幅、成交量、成交额等实时行情数据，需使用其公共API接口（无需API密钥，直接调用）。以下是详细步骤、接口说明、示例代码及注意事项，重点覆盖你提到的核心需求。

一、核心接口：获取24小时行情数据

币安API中，GET /api/v3/ticker/24hr 是最常用的接口，用于获取所有交易对或指定交易对的24小时统计数据，包含：  
• 24小时价格变动（priceChange）  

• 24小时价格变动百分比（priceChangePercent，即涨跌幅）  

• 24小时成交量（基础资产数量，volume）  

• 24小时成交额（报价资产数量，quoteVolume，如USDT计价）  

• 当前价格（lastPrice）、最高价（highPrice）、最低价（lowPrice）等  

1. 接口参数

• symbol（可选）：指定交易对，如 BTCUSDT（比特币/USDT）。若不填，返回所有交易对的24小时数据。  

• 其他参数（如recvWindow、timestamp）为签名参数，公共接口无需填写。  

2. 请求示例

① 获取所有交易对的24小时数据

# curl命令（直接调用）
curl "https://api.binance.com/api/v3/ticker/24hr"


② 获取指定交易对（如BTCUSDT）的24小时数据

curl "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"


3. 返回数据解析（关键字段）

以 BTCUSDT 为例，返回JSON数据如下（截取核心字段）：  
{
  "symbol": "BTCUSDT",          // 交易对
  "priceChange": "123.45",      // 24小时价格变动（USDT）
  "priceChangePercent": "2.50",  // 24小时涨跌幅（%，正数为涨，负数为跌）
  "weightedAvgPrice": "50123.67",// 24小时加权平均价
  "prevClosePrice": "49876.54",  // 前一日收盘价
  "lastPrice": "50123.67",       // 当前最新价
  "lastQty": "0.001",            // 最新成交数量
  "bidPrice": "50120.00",        // 买一价
  "askPrice": "50125.00",        // 卖一价
  "openPrice": "49900.22",       // 24小时开盘价
  "highPrice": "51000.00",       // 24小时最高价
  "lowPrice": "49500.11",        // 24小时最低价
  "volume": "1234.5678",         // 24小时成交量（基础资产数量，如BTC）
  "quoteVolume": "61876543.21",  // 24小时成交额（报价资产数量，如USDT）
  "openTime": 1620000000000,     // 24小时周期开始时间（毫秒级时间戳）
  "closeTime": 1620086400000,    // 24小时周期结束时间
  "count": 98765                 // 24小时成交笔数
}


关键字段对应关系：  
• 24小时涨跌幅 → priceChangePercent（如 "2.50" 表示上涨2.50%）  

• 24小时成交量 → volume（基础资产数量，如BTC数量）  

• 24小时成交额 → quoteVolume（报价资产数量，如USDT金额）  

二、“市值”数据的获取说明

币安API未直接返回“市值”（Market Cap），因为市值 = 当前价格 × 流通供应量，需结合两部分数据计算：  

1. 获取当前价格

通过 GET /api/v3/ticker/price 接口获取指定交易对的当前价格（如 BTCUSDT 的最新价）：  
curl "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
# 返回：{"symbol":"BTCUSDT","price":"50123.67"}


2. 获取流通供应量

币安API不直接提供流通供应量，需通过以下方式间接获取：  
• 第三方数据源：如CoinGecko API（/coins/{id}）、CoinMarketCap API（需API密钥），获取货币的流通量（circulating supply）。  

• 币安“符号详情”接口：GET /api/v3/exchangeInfo 返回所有交易对的元数据（如基础资产的精度），但不含流通量。  

3. 市值计算示例

假设：  
• BTC当前价格（lastPrice）= 50123.67 USDT  

• BTC流通供应量（来自CoinGecko）= 19,500,000 BTC  

则市值 = 50123.67 × 19,500,000 ≈ 977,411,565,000 USDT（约9774亿美元）。  

三、其他常用行情接口

1. 获取单个交易对的最新价格

接口：GET /api/v3/ticker/price  
示例：  
curl "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
# 返回：{"symbol":"ETHUSDT","price":"3000.50"}


2. 获取所有交易对的当前价格

接口：GET /api/v3/ticker/price（不带symbol参数）  
返回所有交易对的最新价格列表。  

3. 获取K线数据（蜡烛图）

接口：GET /api/v3/klines（用于获取历史行情，如日K、小时K）  
参数：symbol（交易对）、interval（时间间隔，如1d=日K、1h=小时K）、limit（返回数量，默认500）。  

四、代码示例（Python调用）

以下是用Python的requests库调用币安API获取BTCUSDT24小时数据的示例：  
import requests

def get_24hr_ticker(symbol="BTCUSDT"):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    params = {"symbol": symbol} if symbol else {}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # 检查HTTP错误
        data = response.json()
        
        # 提取关键信息
        print(f"交易对: {data['symbol']}")
        print(f"24小时涨跌幅: {data['priceChangePercent']}%")
        print(f"24小时成交量: {data['volume']} {data['symbol'][:-4]}")  # 基础资产（如BTC）
        print(f"24小时成交额: {data['quoteVolume']} {data['symbol'][-4:]}")  # 报价资产（如USDT）
        print(f"当前价格: {data['lastPrice']} {data['symbol'][-4:]}")
        
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")

# 调用函数（获取BTCUSDT数据）
get_24hr_ticker("BTCUSDT")


运行结果：  

交易对: BTCUSDT
24小时涨跌幅: 2.50%
24小时成交量: 1234.5678 BTC
24小时成交额: 61876543.21 USDT
当前价格: 50123.67 USDT


五、注意事项

1. 频率限制：  
   币安公共API的请求频率限制为：  
   • 未认证用户：1200次/分钟（IP级别）  

   • 认证用户（API密钥）：10000次/分钟  

   超限会返回 429 Too Many Requests，需控制调用频率。  

2. 数据单位：  
   • volume：基础资产数量（如BTCUSDT的volume是BTC数量）。  

   • quoteVolume：报价资产数量（如BTCUSDT的quoteVolume是USDT金额）。  

3. 时间戳：  
   接口返回的openTime/closeTime为毫秒级Unix时间戳（需转换为北京时间：时间戳 ÷ 1000 + 8×3600）。  

4. 错误处理：  
   若交易对不存在（如拼写错误），返回 400 Bad Request，错误信息含 Invalid symbol。  

六、官方文档参考

• 币安API v3文档：https://binance-docs.github.io/apidocs/spot/en/  

• 24小时行情接口详情：https://binance-docs.github.io/apidocs/spot/en/#24hr-ticker-price-change-statistics  

通过以上方法，你可以轻松获取币安交易对的24小时涨跌、成交量、成交额等核心数据。若需市值，需结合第三方数据源计算当前价格与流通供应量的乘积。