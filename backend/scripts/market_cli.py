#!/usr/bin/env python3
"""
市场数据命令行工具

提供K线数据、实时行情、交易对查询等功能。
此模块为薄封装层，核心逻辑调用Service层或ccxt库。

使用示例:
    # 获取K线数据
    python scripts/market_cli.py klines --symbol BTCUSDT --timeframe 1h

    # 获取最新行情
    python scripts/market_cli.py ticker --symbol BTCUSDT

    # 获取交易对列表
    python scripts/market_cli.py symbols --exchange binance --filter USDT

    # 获取市场数据（综合接口）
    python scripts/market_cli.py fetch --symbol BTCUSDT --data-type kline
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 创建主应用
app = typer.Typer(
    name="market-cli",
    help="市场数据命令行工具",
    add_completion=False,
)


def _get_exchange_config(exchange: str = "binance") -> Dict[str, Any]:
    """获取交易所配置"""
    try:
        from utils.config_manager import load_system_configs

        configs = load_system_configs()
        proxy_enabled = configs.get(f"exchange.{exchange}.proxy_enabled", configs.get("proxy_enabled", False))
        if isinstance(proxy_enabled, str):
            proxy_enabled = proxy_enabled in ("1", "true")
        proxy_url = configs.get(f"exchange.{exchange}.proxy_url", configs.get("proxy_url"))

        config = {"enableRateLimit": True}
        if proxy_enabled and proxy_url:
            config["proxies"] = {"http": proxy_url, "https": proxy_url}

        return config
    except Exception:
        return {"enableRateLimit": True}


def get_klines(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 100,
    exchange: str = "binance",
) -> str:
    """
    获取K线数据

    Args:
        symbol: 交易对，如 BTCUSDT
        timeframe: 时间周期，如 1m, 5m, 1h, 1d
        limit: 返回条数（最大1000）
        exchange: 交易所名称

    Returns:
        str: K线数据或错误信息
    """
    try:
        from ccxt import binance as binance_exchange

        config = _get_exchange_config(exchange)
        ex = binance_exchange(config)

        # 转换时间周期格式
        tf_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
            "12h": "12h", "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
        }
        tf = tf_map.get(timeframe, timeframe)

        # 获取K线数据
        ohlcv = ex.fetch_ohlcv(symbol.upper(), tf, limit=min(limit, 1000))

        if not ohlcv:
            return f"未找到 {symbol} 的 K 线数据"

        # 格式化输出
        from datetime import datetime, timezone

        lines = [f"{symbol} {timeframe} K线数据（最近 {len(ohlcv)} 条）:\n"]
        for item in ohlcv[-10:]:  # 只显示最近10条
            timestamp, open_price, high, low, close, volume = item
            dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(
                f"时间: {time_str} ({timestamp}), "
                f"开: {open_price:.2f}, "
                f"高: {high:.2f}, "
                f"低: {low:.2f}, "
                f"收: {close:.2f}, "
                f"量: {volume:.4f}"
            )

        if len(ohlcv) > 10:
            lines.append(f"\n... 还有 {len(ohlcv) - 10} 条数据")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return f"错误: 获取 K 线数据失败: {e}"


def get_ticker(
    symbol: str,
    exchange: str = "binance",
) -> str:
    """
    获取最新行情

    Args:
        symbol: 交易对，如 BTCUSDT
        exchange: 交易所名称

    Returns:
        str: 行情数据或错误信息
    """
    try:
        from ccxt import binance as binance_exchange

        config = _get_exchange_config(exchange)
        ex = binance_exchange(config)

        ticker = ex.fetch_ticker(symbol.upper())

        if not ticker:
            return f"未找到 {symbol} 的行情数据"

        return (
            f"{symbol} 最新行情:\n"
            f"最新价: {ticker.get('last', 'N/A')}\n"
            f"24h 涨跌: {ticker.get('percentage', 'N/A')}%\n"
            f"24h 最高: {ticker.get('high', 'N/A')}\n"
            f"24h 最低: {ticker.get('low', 'N/A')}\n"
            f"24h 成交量: {ticker.get('baseVolume', 'N/A')}\n"
            f"买一价: {ticker.get('bid', 'N/A')}\n"
            f"卖一价: {ticker.get('ask', 'N/A')}"
        )
    except Exception as e:
        logger.error(f"获取行情失败: {e}")
        return f"错误: 获取行情失败: {e}"


def get_crypto_symbols(
    exchange: str = "binance",
    filter: str = "USDT",
    limit: int = 100,
    market_type: str = "spot",
) -> str:
    """
    获取交易所支持的加密货币交易对列表

    Args:
        exchange: 交易所名称
        filter: 过滤条件，如 USDT
        limit: 返回数量
        market_type: 市场类型：spot(现货)/future(合约)

    Returns:
        str: JSON格式的交易对列表
    """
    try:
        from ccxt import binance as binance_exchange

        config = _get_exchange_config(exchange)
        ex = binance_exchange(config)
        ex.load_markets()

        symbols = []
        for symbol, market in ex.markets.items():
            if market.get("quote") == filter:
                symbols.append({
                    "symbol": symbol.replace("/", ""),
                    "base": market.get("base"),
                    "quote": market.get("quote"),
                    "active": market.get("active", True),
                    "type": market.get("type", "spot"),
                })

        if market_type:
            symbols = [s for s in symbols if s.get("type") == market_type]

        symbols = symbols[:limit]

        return json.dumps({
            "success": True,
            "exchange": exchange,
            "total": len(symbols),
            "symbols": symbols,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"获取交易对列表失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def fetch_market_data(
    symbol: str,
    data_type: str,
    interval: str = "1h",
    limit: int = 100,
    market_type: str = "spot",
) -> str:
    """
    获取实时或历史市场数据

    Args:
        symbol: 交易对，如 BTCUSDT
        data_type: 数据类型：kline(K线)、24h_ticker(24小时行情)
        interval: K线时间周期
        limit: 返回数据条数
        market_type: 市场类型：spot(现货)/future(合约)

    Returns:
        str: JSON格式的市场数据
    """
    try:
        if data_type == "kline":
            from collector.services.kline_factory import KlineDataFactory
            from collector.db.database import SessionLocal, init_database_config

            init_database_config()
            crypto_type = "spot" if market_type == "spot" else "future"
            fetcher = KlineDataFactory.create_fetcher("crypto", crypto_type)
            db = SessionLocal()
            try:
                result = fetcher.fetch_kline_data(db, symbol, interval, limit=limit)
                kline_data = result.get("kline_data", [])[-limit:]
                return json.dumps({
                    "success": True,
                    "symbol": symbol,
                    "interval": interval,
                    "count": len(kline_data),
                    "klines": kline_data,
                }, ensure_ascii=False)
            finally:
                db.close()

        elif data_type == "24h_ticker":
            from ccxt import binance as binance_exchange

            config = _get_exchange_config("binance")
            ex = binance_exchange(config)
            ticker = ex.fetch_ticker(symbol)

            return json.dumps({
                "success": True,
                "symbol": symbol,
                "ticker": {
                    "last": ticker.get("last"),
                    "change": ticker.get("change"),
                    "percentage": ticker.get("percentage"),
                    "baseVolume": ticker.get("baseVolume"),
                    "quoteVolume": ticker.get("quoteVolume"),
                    "high": ticker.get("high"),
                    "low": ticker.get("low"),
                    "bid": ticker.get("bid"),
                    "ask": ticker.get("ask"),
                },
            }, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"不支持的数据类型: {data_type}"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"获取市场数据失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ==================== CLI 命令 ====================

@app.command("klines")
def cli_klines(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对，如 BTCUSDT")],
    timeframe: Annotated[str, typer.Option("--timeframe", "-t", help="时间周期")] = "1h",
    limit: Annotated[int, typer.Option("--limit", "-l", help="返回条数")] = 100,
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
):
    """获取K线数据"""
    result = get_klines(symbol, timeframe, limit, exchange)
    typer.echo(result)


@app.command("ticker")
def cli_ticker(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对，如 BTCUSDT")],
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
):
    """获取最新行情"""
    result = get_ticker(symbol, exchange)
    typer.echo(result)


@app.command("symbols")
def cli_symbols(
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    filter: Annotated[str, typer.Option("--filter", "-f", help="过滤条件，如 USDT")] = "USDT",
    limit: Annotated[int, typer.Option("--limit", "-l", help="返回数量")] = 100,
    market_type: Annotated[str, typer.Option("--market-type", help="市场类型：spot/future")] = "spot",
):
    """获取交易对列表"""
    result = get_crypto_symbols(exchange, filter, limit, market_type)
    typer.echo(result)


@app.command("fetch")
def cli_fetch(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对，如 BTCUSDT")],
    data_type: Annotated[str, typer.Option("--data-type", "-d", help="数据类型：kline/24h_ticker")] = "kline",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线时间周期")] = "1h",
    limit: Annotated[int, typer.Option("--limit", "-l", help="返回数据条数")] = 100,
    market_type: Annotated[str, typer.Option("--market-type", help="市场类型：spot/future")] = "spot",
):
    """获取市场数据（综合接口）"""
    result = fetch_market_data(symbol, data_type, interval, limit, market_type)
    typer.echo(result)


if __name__ == "__main__":
    app()
