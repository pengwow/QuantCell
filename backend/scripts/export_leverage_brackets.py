#!/usr/bin/env python3
"""导出币安 USDT-M 杠杆档位到内置快照 JSON（离线回测的二级数据源）。

用法::

    cd backend
    .venv/bin/python scripts/export_leverage_brackets.py                 # 从币安接口拉取
    .venv/bin/python scripts/export_leverage_brackets.py -s BTCUSDT -s ETHUSDT
    .venv/bin/python scripts/export_leverage_brackets.py --source db     # 从 collector 库导出

写盘采用「合并」语义：只覆盖本次成功取到的品种，取不到的保留原值，
避免一次网络抖动把已有快照清空。
"""

import asyncio
import json
import sys
from pathlib import Path

import typer

# 直接执行脚本时 sys.path[0] 是 scripts/，项目包位于 backend/ 下，先补上再导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 注意：下面的项目包导入必须在 sys.path 注入之后
from collector.services.deriv_collector import LeverageBracketCollector
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "binance_um_leverage_brackets.json"
_DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

app = typer.Typer(add_completion=False, help="导出币安 USDT-M 杠杆档位快照")


async def _fetch_symbols(
    symbols: list[str],
    collector: LeverageBracketCollector,
    proxy: str | None,
    save_db: bool,
) -> dict[str, list[dict]]:
    """并发拉取各品种档位；单品种失败只跳过，不影响其他品种"""

    async def _one(session, symbol: str) -> tuple[str, list[dict] | None]:
        try:
            brackets = await collector.fetch(session, symbol, proxy=proxy)
        except Exception as exc:  # 网络/接口错误都按单品种失败处理
            logger.error(f"{symbol} 杠杆档位拉取失败: {exc}")
            return symbol, None
        return symbol, brackets

    import aiohttp

    result: dict[str, list[dict]] = {}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for symbol, brackets in await asyncio.gather(*(_one(session, s) for s in symbols)):
            if not brackets:
                logger.warning(f"{symbol} 未返回档位数据，跳过")
                continue
            result[symbol.upper()] = brackets
            if save_db:
                collector.save(symbol, brackets)
    return result


def _load_from_db(symbols: list[str]) -> dict[str, list[dict]]:
    """从 collector 库导出（复用回测侧的三级回退读取逻辑）"""
    from backtest.margin_specs import _load_from_db as load_brackets

    result: dict[str, list[dict]] = {}
    for symbol in symbols:
        brackets = load_brackets(symbol)
        if brackets:
            result[symbol.upper()] = brackets
    return result


@app.command()
def export(
    symbols: list[str] = typer.Option(None, "-s", "--symbol", help=f"交易对，可重复；默认 {_DEFAULT_SYMBOLS}"),
    output: Path = typer.Option(_DEFAULT_OUTPUT, "-o", "--output", help="快照输出路径"),
    source: str = typer.Option("api", "--source", help="数据来源：api（币安接口）/ db（collector 库）"),
    save_db: bool = typer.Option(True, "--save-db/--no-save-db", help="api 模式是否同时落库"),
) -> None:
    """拉取/导出档位并写入快照 JSON"""
    wanted = [s.upper() for s in (symbols or _DEFAULT_SYMBOLS)]

    if source == "db":
        fetched = _load_from_db(wanted)
    elif source == "api":
        import os

        proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
        fetched = asyncio.run(_fetch_symbols(wanted, LeverageBracketCollector(), proxy, save_db))
    else:
        raise typer.BadParameter(f"未知的数据来源: {source}（可选 api / db）")

    if not fetched:
        logger.error("没有取到任何档位数据，快照保持不变")
        raise typer.Exit(code=1)

    merged: dict[str, list[dict]] = {}
    if output.exists():
        try:
            merged = json.loads(output.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"{output} 内容不是合法 JSON，将整体覆盖")
    merged.update(fetched)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info(f"档位快照已更新: {output}（品种 {len(fetched)} 个，累计 {len(merged)} 个）")


if __name__ == "__main__":
    app()
