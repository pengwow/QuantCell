# -*- coding: utf-8 -*-
"""
日志管理API路由

提供日志查询、统计和管理功能
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from collector.db.models import SystemLogBusiness
from utils.logger import get_logger, LogType

# 获取日志器
logger = get_logger(__name__, LogType.API)

# 创建路由
router = APIRouter(prefix="/api/logs", tags=["日志管理"])


class LogResponse(BaseModel):
    """日志响应模型"""
    id: int
    timestamp: str
    level: str
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    logger_name: Optional[str] = None
    log_type: str
    extra_data: Optional[dict] = None
    exception_info: Optional[str] = None
    trace_id: Optional[str] = None
    created_at: str


class LogListResponse(BaseModel):
    """日志列表响应模型"""
    logs: List[LogResponse]
    pagination: dict


class LogStatisticsResponse(BaseModel):
    """日志统计响应模型"""
    total_count: int
    by_level: dict
    by_type: dict


class LogLevelDistribution(BaseModel):
    """日志级别分布"""
    level: str
    count: int
    percentage: float


class LogTypeDistribution(BaseModel):
    """日志类型分布"""
    log_type: str
    count: int
    percentage: float


class LogTrendItem(BaseModel):
    """日志趋势项"""
    timestamp: str
    count: int


@router.get("/query", response_model=LogListResponse)
async def query_logs(
    level: Optional[str] = Query(None, description="日志级别过滤 (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    log_type: Optional[str] = Query(None, description="日志类型过滤"),
    module: Optional[str] = Query(None, description="模块名称过滤"),
    trace_id: Optional[str] = Query(None, description="跟踪ID过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=1000, description="每页数量"),
):
    """
    查询日志记录

    支持多种过滤条件，包括日志级别、类型、模块、时间范围等
    """
    try:
        result = SystemLogBusiness.query_logs(
            level=level,
            log_type=log_type,
            module=module,
            trace_id=trace_id,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

        # 转换为响应模型
        logs = [LogResponse(**log) for log in result["logs"]]

        logger.info(f"查询日志: level={level}, type={log_type}, page={page}, total={result['pagination']['total']}")

        return LogListResponse(
            logs=logs,
            pagination=result["pagination"]
        )
    except Exception as e:
        logger.error(f"查询日志失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"查询日志失败: {str(e)}")


@router.get("/statistics", response_model=LogStatisticsResponse)
async def get_log_statistics(
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
):
    """
    获取日志统计信息

    返回日志总数、按级别统计、按类型统计等信息
    """
    try:
        stats = SystemLogBusiness.get_log_statistics(
            start_time=start_time,
            end_time=end_time,
        )

        logger.info("获取日志统计信息")

        return LogStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"获取日志统计失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取日志统计失败: {str(e)}")


@router.get("/recent", response_model=LogListResponse)
async def get_recent_logs(
    minutes: int = Query(60, ge=1, le=1440, description="最近多少分钟的日志"),
    level: Optional[str] = Query(None, description="日志级别过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
):
    """
    获取最近的日志

    用于实时监控和快速查看最近的日志记录
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=minutes)

        result = SystemLogBusiness.query_logs(
            level=level,
            start_time=start_time,
            end_time=end_time,
            page=1,
            page_size=limit,
        )

        logs = [LogResponse(**log) for log in result["logs"]]

        return LogListResponse(
            logs=logs,
            pagination=result["pagination"]
        )
    except Exception as e:
        logger.error(f"获取最近日志失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取最近日志失败: {str(e)}")


@router.get("/trace/{trace_id}", response_model=LogListResponse)
async def get_logs_by_trace_id(
    trace_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=1000, description="每页数量"),
):
    """
    根据跟踪ID获取相关日志

    用于追踪一个请求或操作的完整日志链路
    """
    try:
        result = SystemLogBusiness.query_logs(
            trace_id=trace_id,
            page=page,
            page_size=page_size,
        )

        logs = [LogResponse(**log) for log in result["logs"]]

        logger.info(f"查询跟踪ID日志: trace_id={trace_id}, count={len(logs)}")

        return LogListResponse(
            logs=logs,
            pagination=result["pagination"]
        )
    except Exception as e:
        logger.error(f"查询跟踪ID日志失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"查询跟踪ID日志失败: {str(e)}")


@router.delete("/cleanup")
async def cleanup_old_logs(
    days: int = Query(30, ge=1, le=365, description="保留多少天内的日志"),
):
    """
    清理旧日志

    删除指定天数之前的日志记录，释放存储空间
    """
    try:
        deleted_count = SystemLogBusiness.delete_old_logs(days=days)

        logger.info(f"清理旧日志: 保留{days}天, 删除{deleted_count}条记录")

        return {
            "success": True,
            "deleted_count": deleted_count,
            "retention_days": days,
        }
    except Exception as e:
        logger.error(f"清理旧日志失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"清理旧日志失败: {str(e)}")


@router.get("/levels")
async def get_log_levels():
    """
    获取支持的日志级别列表

    返回系统支持的所有日志级别
    """
    from utils.logger import LogLevel

    levels = [
        {"value": level.value, "int_value": level.to_int()}
        for level in LogLevel
    ]

    return {"levels": levels}


@router.get("/types")
async def get_log_types():
    """
    获取支持的日志类型列表

    返回系统支持的所有日志类型
    """
    from utils.logger import LogType

    types = [
        {"value": t.value, "name": t.name}
        for t in LogType
    ]

    return {"types": types}


@router.get("/dashboard")
async def get_log_dashboard(
    hours: int = Query(24, ge=1, le=168, description="统计最近多少小时"),
):
    """
    获取日志仪表板数据

    返回用于仪表板展示的综合统计数据
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        # 获取统计数据
        stats = SystemLogBusiness.get_log_statistics(
            start_time=start_time,
            end_time=end_time,
        )

        # 获取错误日志
        error_result = SystemLogBusiness.query_logs(
            level="ERROR",
            start_time=start_time,
            end_time=end_time,
            page=1,
            page_size=10,
        )

        # 获取警告日志
        warning_result = SystemLogBusiness.query_logs(
            level="WARNING",
            start_time=start_time,
            end_time=end_time,
            page=1,
            page_size=10,
        )

        logger.info(f"获取日志仪表板数据: 最近{hours}小时")

        return {
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours,
            },
            "statistics": stats,
            "recent_errors": [LogResponse(**log) for log in error_result["logs"]],
            "recent_warnings": [LogResponse(**log) for log in warning_result["logs"]],
        }
    except Exception as e:
        logger.error(f"获取日志仪表板失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取日志仪表板失败: {str(e)}")
