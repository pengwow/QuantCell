"""衍生数据 REST API（4 个端点，与 archive API 对齐）。

端点:
- GET  /api/data/deriv/symbols          列出已采集 symbols
- GET  /api/data/deriv/data             分页查询数据
- GET  /api/data/deriv/meta/{kind}/{market}/{symbol}   读取元数据
- DELETE /api/data/deriv/data           删除某 symbol 的全部数据

注意：下载入口仍然走统一的 /api/data/download-crypto（data_type=fundingRate|openInterest）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query

from collector.config import get_archive_base_dir
from collector.services.deriv_service import DerivService
from utils.logger import LogType, get_logger
from worker.decorators import handle_worker_exceptions

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(prefix="/data/deriv", tags=["deriv"])


def _svc() -> DerivService:
    return DerivService(base_dir=get_archive_base_dir())


# —— 1) GET /symbols ——


@router.get("/symbols")
@handle_worker_exceptions("列出衍生数据 symbols")
def get_symbols(
    kind: str = Query(..., description="衍生数据种类: fundingRate / openInterest"),
    market: str = Query(..., description="市场：spot / um / cm"),
) -> dict:
    try:
        symbols = _svc().list_symbols(kind, market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "symbols": symbols, "total": len(symbols)}


# —— 2) GET /data ——


@router.get("/data")
@handle_worker_exceptions("查询衍生数据")
def get_data(
    kind: str = Query(..., description="数据种类"),
    market: str = Query(..., description="市场"),
    symbol: str = Query(..., description="交易对"),
    start_time: int = Query(..., description="起始时间 (毫秒)"),
    end_time: int = Query(..., description="结束时间 (毫秒)"),
    limit: int = Query(1000, ge=1, le=1_000_000, description="分页行数上限"),
    offset: int = Query(0, ge=0, description="分页偏移"),
) -> dict:
    try:
        result = _svc().query_data(kind, market, symbol, start_time, end_time, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


# —— 3) GET /meta/{kind}/{market}/{symbol} ——


@router.get("/meta/{kind}/{market}/{symbol}")
@handle_worker_exceptions("读取衍生数据元数据")
def get_meta(
    kind: str = Path(..., description="数据种类"),
    market: str = Path(..., description="市场"),
    symbol: str = Path(..., description="交易对"),
) -> dict:
    try:
        meta = _svc().get_meta(kind, market, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "meta": meta}


# —— 4) DELETE /data ——


@router.delete("/data")
@handle_worker_exceptions("删除衍生数据")
def delete_data(
    kind: str = Query(..., description="数据种类"),
    market: str = Query(..., description="市场"),
    symbol: str = Query(..., description="交易对"),
) -> dict:
    try:
        deleted = _svc().delete_data(kind, market, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "deleted": str(deleted) if deleted else None,
        "message": f"已删除 {symbol}" if deleted else "目录不存在，无需删除",
    }
