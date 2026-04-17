"""市场数据工具 - 获取行情、K线等数据"""

from typing import Any

from ..base import Tool


class GetKlinesTool(Tool):
    """获取 K 线数据"""

    name = "get_klines"
    description = "获取指定交易对的 K 线（蜡烛图）数据。支持多个交易所。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易对，如 BTCUSDT"},
            "timeframe": {"type": "string", "description": "时间周期，如 1m, 5m, 1h, 1d", "enum": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]},
            "limit": {"type": "integer", "description": "返回条数（最大 1000）", "minimum": 1, "maximum": 1000, "default": 100},
            "exchange": {"type": "string", "description": "交易所，如 binance, okx", "default": "binance"},
        },
        "required": ["symbol", "timeframe"],
    }

    async def execute(self, symbol: str, timeframe: str, limit: int = 100, exchange: str = "binance", **kwargs: Any) -> str:
        try:
            # 导入 collector 服务获取数据
            from collector.services.market_data_service import MarketDataService
            
            service = MarketDataService()
            data = await service.get_klines(
                symbol=symbol.upper(),
                timeframe=timeframe,
                limit=min(limit, 1000),
                exchange=exchange,
            )
            
            if not data:
                return f"未找到 {symbol} 的 K 线数据"
            
            # 格式化输出
            lines = [f"{symbol} {timeframe} K线数据（最近 {len(data)} 条）:\n"]
            for item in data[-10:]:  # 只显示最近10条
                lines.append(
                    f"时间: {item['timestamp']}, "
                    f"开: {item['open']:.2f}, "
                    f"高: {item['high']:.2f}, "
                    f"低: {item['low']:.2f}, "
                    f"收: {item['close']:.2f}, "
                    f"量: {item['volume']:.4f}"
                )
            
            if len(data) > 10:
                lines.append(f"\n... 还有 {len(data) - 10} 条数据")
            
            return "\n".join(lines)
        except Exception as e:
            return f"错误: 获取 K 线数据失败: {e}"


class GetTickerTool(Tool):
    """获取最新行情"""

    name = "get_ticker"
    description = "获取指定交易对的最新行情数据（最新价、涨跌幅等）。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易对，如 BTCUSDT"},
            "exchange": {"type": "string", "description": "交易所", "default": "binance"},
        },
        "required": ["symbol"],
    }

    async def execute(self, symbol: str, exchange: str = "binance", **kwargs: Any) -> str:
        try:
            from collector.services.market_data_service import MarketDataService
            
            service = MarketDataService()
            ticker = await service.get_ticker(symbol.upper(), exchange)
            
            if not ticker:
                return f"未找到 {symbol} 的行情数据"
            
            return (
                f"{symbol} 最新行情:\n"
                f"最新价: {ticker.get('last_price', 'N/A')}\n"
                f"24h 涨跌: {ticker.get('price_change_percent', 'N/A')}%\n"
                f"24h 最高: {ticker.get('high_24h', 'N/A')}\n"
                f"24h 最低: {ticker.get('low_24h', 'N/A')}\n"
                f"24h 成交量: {ticker.get('volume_24h', 'N/A')}"
            )
        except Exception as e:
            return f"错误: 获取行情失败: {e}"
