"""Paper 行情泵的 typed HTTP client（P2-09 三轨收敛）。

泵轮询的唯一外部 HTTP 端点是 binance USDT-M testnet 公共收市 K 线。
此前 URL 拼装与裸 list 行消费散在 strategy_manager 内，本模块把它收敛为
带类型定义的 client：``PaperKline`` 描述行 schema，``fetch_paper_klines``
返回已转换的 typed 行，``as_kline`` 做「binance 原始行 / typed dict →
统一形态」的幂等转换（原始行值是字符串，dict 形态数值已是 int/float）。

ponytail: 标准库 urlopen 就够（一次 GET + timeout）；requests 未在
pyproject 声明为直接依赖，不为一次调用升级它。api_symbol/timeframe 均
来自白名单受限字符集，URL 无需额外编码。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, TypedDict


class PaperKline(TypedDict):
    """泛化后的 K 线行（泵轮消费所需的字段子集）。"""

    open_time: int  # 开市毫秒时间戳
    open: float
    high: float
    low: float
    close: float
    volume: float


# paper 行情泵轮询端点：testnet 公共 K 线，不签名、无需凭证
PAPER_KLINES_URL = "https://testnet.binancefuture.com/fapi/v1/klines"

# 轮询强制直连：urllib 默认读 macOS/GUI 代理工具注册的系统代理（如 127.0.0.1:7897），
# 代理不在线时整个轮询管线收不到任何 bar；同链路的 requests/python-binance 只读
# 环境变量故直连可达，这里显式清掉代理保持同一语义
PAPER_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def as_kline(row: Any) -> PaperKline:
    """binance 原始行 / 已转换 typed dict → 统一 ``PaperKline``。

    接受两种输入：
    - 原始行 ``[openTime, open, high, low, close, volume, ...]``（数值是字符串），
      亦是测试 monkeypatch ``_paper_fetch_klines`` 的注入形态；
    - ``as_kline``/``fetch_paper_klines`` 的输出（幂等再转换）。
    """
    if isinstance(row, dict):
        return PaperKline(
            open_time=int(row["open_time"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
    return PaperKline(
        open_time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )


def fetch_paper_klines(api_symbol: str, timeframe: str, limit: int) -> list[PaperKline]:
    """拉取已收市判定用的公共 K 线（不签名），返回 typed 行列表。

    端点错误（限频/参数错）时响应是 ``{"code": ..., "msg": ...}`` dict 而非
    list，显式抛 ValueError 让泵轮按常态异常路径降级告警。
    """
    url = f"{PAPER_KLINES_URL}?symbol={api_symbol}&interval={timeframe}&limit={limit}"
    with PAPER_NO_PROXY_OPENER.open(url, timeout=10) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"paper klines 响应非 list: {rows}")
    return [as_kline(r) for r in rows]
