"""归档数据 REST API（7 个端点）。

所有端点统一返回 `{success, message, data?, total?}` 风格
(遵循项目其他路由的约定,例如 collector/api/data.py)。
所有端点用 `handle_worker_exceptions` 装饰器统一处理业务异常。

端点清单:
- POST   /api/data/archive/download        创建下载任务
- GET    /api/data/archive/tasks/{task_id} 查询任务进度
- GET    /api/data/archive/symbols         列出已采集的 symbols
- GET    /api/data/archive/data            分页查询数据
- GET    /api/data/archive/meta/{kind}/{market}/{symbol}  读 _meta.json
- DELETE /api/data/archive/data            删除某 symbol 的全部数据
- GET    /api/data/archive/watermark       按 kind 聚合水位 + 存储用量（首屏只读卡）
"""

from __future__ import annotations

import shutil
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from collector.config import get_archive_base_dir, get_binance_proxy
from collector.services import kline_browse_service
from collector.services.archive_service import ArchiveService
from collector.utils.task_manager import task_manager
from exchange.binance.archive.kinds import (
    ArchiveKind,
    MarketType,
    get_save_dir,
)
from utils.logger import LogType, get_logger
from worker.decorators import handle_worker_exceptions

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(prefix="/data/archive", tags=["archive"])

# K 线数据不是 Binance Vision 归档 zip，而是本地 parquet（与回测/研究同一份文件）：
# kind=kline 走 kline_browse_service，其余 7 种仍走 ArchiveService
KLINE_KIND = "kline"


def _parse_market(market: str) -> MarketType:
    try:
        return MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"非法 market: {market!r}") from exc


def _get_service() -> ArchiveService:
    """从 settings / system_config 解析 base_dir + proxy。"""
    return ArchiveService(
        base_dir=get_archive_base_dir(),
        proxy=get_binance_proxy(),
    )


def _parse_kind_market(kind: str, market: str) -> tuple[ArchiveKind, MarketType]:
    """把字符串 kind/market 解析为枚举, 解析失败抛 HTTPException(400)。"""
    try:
        kind_e = ArchiveKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"非法 kind: {kind!r}") from exc
    try:
        market_e = MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"非法 market: {market!r}") from exc
    return kind_e, market_e


# =================== 1) POST /download ===================


class DownloadRequest(BaseModel):
    """创建归档下载任务的请求体。"""

    symbols: list[str] = Field(..., min_length=1, description="交易对列表")
    kind: str = Field(..., description="数据种类 (aggTrades/trades/...)")
    market: str = Field(..., description="市场 (spot/um/cm)")
    start_date: str = Field(..., description="起始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    mode: Literal["inc", "full"] = Field("inc", description="inc=增量 / full=全量")
    interval: str | None = Field(None, description="K 线类需要 (1m/3m/5m/15m/30m/1h/2h/1d)")


@router.post("/download")
@handle_worker_exceptions("创建归档下载任务")
def post_download(req: DownloadRequest) -> dict:
    """创建归档下载任务, 返回 task_id 与 pending 状态。

    业务异常 (K 线类缺 interval 等) → 400。
    """
    kind_e, market_e = _parse_kind_market(req.kind, req.market)
    svc = _get_service()
    try:
        task_id = svc.create_download_task(
            symbols=req.symbols,
            kind=kind_e,
            market=market_e,
            start_date=req.start_date,
            end_date=req.end_date,
            mode=req.mode,
            interval=req.interval,
        )
    except ValueError as exc:
        # K 线类缺 interval 或非法 interval
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        f"创建归档下载任务: task_id={task_id}, kind={kind_e.value}, market={market_e.value}, "
        f"symbols={req.symbols}, mode={req.mode}, interval={req.interval}"
    )
    return {
        "success": True,
        "task_id": task_id,
        "status": "pending",
        "message": "归档下载任务已创建, 可通过 /api/data/archive/tasks/{task_id} 查询进度",
    }


# =================== 2) GET /tasks/{task_id} ===================


@router.get("/tasks/{task_id}")
@handle_worker_exceptions("查询归档任务进度")
def get_task_progress(task_id: str = Path(..., description="任务 ID")) -> dict:
    """查询归档下载任务的当前进度。"""
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    return {"success": True, **task}


# =================== 3) GET /symbols ===================


@router.get("/symbols")
@handle_worker_exceptions("列出归档 symbols")
def get_symbols(
    kind: str = Query(..., description="数据种类"),
    market: str = Query(..., description="市场"),
    interval: str | None = Query(None, description="K 线类周期（kline 可选：只列该周期有文件的标的）"),
) -> dict:
    """列出 (kind, market) 下已采集的 symbols。"""
    if kind == KLINE_KIND:
        market_e = _parse_market(market)
        symbols = kline_browse_service.list_symbols(market_e.value, interval)
        return {"success": True, "symbols": symbols, "total": len(symbols)}
    kind_e, market_e = _parse_kind_market(kind, market)
    svc = _get_service()
    symbols = svc.list_symbols(kind_e, market_e)
    return {"success": True, "symbols": symbols, "total": len(symbols)}


# =================== 4) GET /data ===================


@router.get("/data")
@handle_worker_exceptions("查询归档数据")
def get_data(
    kind: str = Query(..., description="数据种类"),
    market: str = Query(..., description="市场"),
    symbol: str = Query(..., description="交易对"),
    start_time: int = Query(..., description="起始时间 (毫秒)"),
    end_time: int = Query(..., description="结束时间 (毫秒)"),
    limit: int = Query(1000, ge=1, le=1_000_000, description="分页行数上限"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    interval: str | None = Query(None, description="K 线类周期（kline 缺省取该标的第一个可用周期）"),
) -> dict:
    """分页查询指定 (kind, market, symbol) 在 [start_time, end_time] 区间的数据。"""
    if kind == KLINE_KIND:
        market_e = _parse_market(market)
        result = kline_browse_service.query_data(market_e.value, symbol, start_time, end_time, limit, offset, interval)
        return {"success": True, **result}
    kind_e, market_e = _parse_kind_market(kind, market)
    svc = _get_service()
    result = svc.query_data(
        kind_e,
        market_e,
        symbol,
        start_time,
        end_time,
        limit,
        offset,
    )
    return {"success": True, **result}


# =================== 5) GET /meta/{kind}/{market}/{symbol} ===================


@router.get("/meta/{kind}/{market}/{symbol}")
@handle_worker_exceptions("读取归档元数据")
def get_meta(
    kind: str = Path(..., description="数据种类"),
    market: str = Path(..., description="市场"),
    symbol: str = Path(..., description="交易对"),
    interval: str | None = Query(None, description="K 线类周期（kline 缺省取该标的第一个可用周期）"),
) -> dict:
    """读取 _meta.json; 不存在时 meta=null（kline 按本地 parquet 现算）。"""
    if kind == KLINE_KIND:
        market_e = _parse_market(market)
        return {"success": True, "meta": kline_browse_service.get_meta(market_e.value, symbol, interval)}
    kind_e, market_e = _parse_kind_market(kind, market)
    svc = _get_service()
    meta = svc.get_meta(kind_e, market_e, symbol)
    return {"success": True, "meta": meta}


# =================== 5b) GET /symbol-coverage ===================


@router.get("/symbol-coverage")
@handle_worker_exceptions("读取单标的归档覆盖")
def get_symbol_coverage(
    symbol: str = Query(..., description="交易对，如 LTC/USDT 或 LTCUSDT"),
    market: str = Query("spot", description="市场 spot/um/cm"),
) -> dict:
    """单标的已采集覆盖：各 kind 的行数 / 周期 / 日期（标的简况面板）。

    与 /watermark 的区别：那是按 kind 的全市场聚合，这里是「这一个标的」的明细。
    """
    try:
        market_e = MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown market: {market}") from exc
    svc = _get_service()
    return {"success": True, **svc.get_symbol_coverage(symbol, market_e)}


# =================== 6) DELETE /data ===================


@router.delete("/data")
@handle_worker_exceptions("删除归档数据")
def delete_data(
    kind: str = Query(..., description="数据种类"),
    market: str = Query(..., description="市场"),
    symbol: str = Query(..., description="交易对"),
    interval: str | None = Query(None, description="K 线类周期（kline 可选：只删该周期）"),
) -> dict:
    """删除某 (kind, market, symbol) 目录下的全部数据。

    注意: 这是一个破坏性操作, 调用方需自行确认 (前端/CLI 二次确认)。
    """
    if kind == KLINE_KIND:
        market_e = _parse_market(market)
        deleted = kline_browse_service.delete_symbol(market_e.value, symbol, interval)
        return {
            "success": True,
            "deleted": deleted,
            "message": f"已删除 {deleted}" if deleted else "文件不存在, 无需删除",
        }
    kind_e, market_e = _parse_kind_market(kind, market)
    svc = _get_service()
    save_dir = get_save_dir(svc.base_dir, market_e, kind_e, symbol)
    if save_dir.exists():
        shutil.rmtree(save_dir)
        logger.warning(f"已删除归档目录: {save_dir}")
        return {
            "success": True,
            "deleted": str(save_dir),
            "message": f"已删除 {save_dir}",
        }
    return {"success": True, "deleted": None, "message": "目录不存在, 无需删除"}


# =================== 7) GET /watermark ===================


@router.get("/watermark")
@handle_worker_exceptions("聚合归档水位与存储用量")
def get_watermark() -> dict:
    """按 kind 聚合数据源水位与 parquet 磁盘占用。

    两族布局都统计：归档布局以 `_meta.json` 为权威来源；数据池布局（`crypto/**/klines`、
    `fundingRate`、`openInterest`）没有 meta，改读 parquet footer 兜底。没有 parquet 的
    kind 不出现在 `storage` 里，读不出行数的也不进 `watermarks`（不补 0 占位）。
    """
    svc = _get_service()
    return {"success": True, **svc.get_watermark()}
