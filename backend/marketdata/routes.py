"""市场数据补充接口。所有响应统一 {code, message, data} 信封。

信封为什么内嵌 _ok 而不 import main：main.py 是应用组装入口，
路由模块反向 import main 会形成模块依赖倒置（main → routes → main 循环）；
common.schemas.ApiResponse 虽是统一模型但额外带服务端 timestamp 字段，
本组契约（前端已按三键解析）固定为 {code, message, data}，故内嵌同构 helper。
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from marketdata import service
from utils.logger import LogType, get_logger

router = APIRouter(prefix="/api/v1/marketdata", tags=["marketdata"])
logger = get_logger(__name__, LogType.APPLICATION)


def _ok(data: Any) -> dict:
    # 与 main.py 的统一响应信封 {code, message, data} 字段完全一致（见模块 docstring）
    return {"code": 0, "message": "success", "data": data}


@router.get(
    "/depth",
    summary="现货订单簿快照",
    description="直接回源 binance 现货 /api/v3/depth，作为图表页订单簿面板 WS 推送前的初始兜底数据。",
)
async def get_depth(
    symbol: str = Query(..., min_length=4, max_length=30, description="交易对，如 BTCUSDT"),
    limit: int = Query(20, ge=5, le=50, description="盘口档位数量"),
):
    try:
        return _ok(await service.fetch_depth_snapshot(symbol, limit))
    except Exception as exc:  # 回源失败统一 502，前端降级展示「暂无数据」
        logger.warning(f"订单簿快照回源失败 symbol={symbol} limit={limit}: {exc}")
        raise HTTPException(status_code=502, detail=f"获取订单簿快照失败: {exc}") from exc


@router.get(
    "/oi/history",
    summary="永续未平仓合约(OI)历史",
    description="币安 USDT-M 永续聚合 OI（sumOpenInterestValue，USD 口径）；历史仅近 30 天，现货品种返回空数组。",
)
async def get_oi_history(
    symbol: str = Query(..., min_length=4, max_length=30, description="交易对，如 BTCUSDT"),
    interval: str = Query("5m", description="K 线粒度 5m..1d，接口不支持的间隔回源按 1h 兜底"),
    limit: int = Query(96, ge=1, le=96, description="返回点数上限"),
):
    try:
        return _ok(await service.fetch_oi_history(symbol, interval, limit))
    except Exception as exc:
        logger.warning(f"OI 历史回源失败 symbol={symbol} interval={interval} limit={limit}: {exc}")
        raise HTTPException(status_code=502, detail=f"获取 OI 历史失败: {exc}") from exc


@router.get(
    "/funding/history",
    summary="永续资金费率历史",
    description="币安 USDT-M 永续资金费率（固定 8h 结算，无 interval 参数），近 14 天窗口内按 limit 截取。",
)
async def get_funding_history(
    symbol: str = Query(..., min_length=4, max_length=30, description="交易对，如 BTCUSDT"),
    limit: int = Query(42, ge=1, le=42, description="返回点数上限（8h 结算，14 天共 42 点）"),
):
    try:
        return _ok(await service.fetch_funding_history(symbol, limit))
    except Exception as exc:
        logger.warning(f"资金费率历史回源失败 symbol={symbol} limit={limit}: {exc}")
        raise HTTPException(status_code=502, detail=f"获取资金费率历史失败: {exc}") from exc
