# -*- coding: utf-8 -*-
"""
日志管理API路由

提供日志查询、统计和管理功能
基于文件日志系统实现，替代原数据库日志方案。
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from utils.log_query_engine import get_log_query_engine
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
    基于文件日志系统实现高性能查询。
    """
    try:
        query_engine = get_log_query_engine()
        result = query_engine.query_logs(
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
        logs = [LogResponse(**log) for log in result.logs]

        logger.info(f"查询日志: level={level}, type={log_type}, page={page}, total={result.pagination.get('total', 0)}")

        return LogListResponse(
            logs=logs,
            pagination=result.pagination
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
    基于文件日志系统聚合计算。
    """
    try:
        query_engine = get_log_query_engine()
        stats = query_engine.get_statistics(
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
    基于文件日志系统高效读取。
    """
    try:
        query_engine = get_log_query_engine()
        logs_data = query_engine.get_recent_logs(
            minutes=minutes,
            limit=limit,
            level=level,
        )

        logs = [LogResponse(**log) for log in logs_data]

        return LogListResponse(
            logs=logs,
            pagination={
                'page': 1,
                'page_size': limit,
                'total': len(logs),
                'pages': 1,
            }
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
    基于文件日志系统搜索。
    """
    try:
        query_engine = get_log_query_engine()
        result = query_engine.get_logs_by_trace_id(
            trace_id=trace_id,
            page=page,
            page_size=page_size,
        )

        logs = [LogResponse(**log) for log in result.logs]

        logger.info(f"查询跟踪ID日志: trace_id={trace_id}, count={len(logs)}")

        return LogListResponse(
            logs=logs,
            pagination=result.pagination
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

    删除指定天数之前的日志文件，释放存储空间
    基于文件日志系统直接删除过期文件。
    """
    try:
        query_engine = get_log_query_engine()
        result = query_engine.cleanup_old_logs(days=days)

        logger.info(f"清理旧日志: 保留{days}天, 删除{result.get('deleted_count', 0)}条记录")

        return result
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
    基于文件日志系统聚合计算。
    """
    try:
        query_engine = get_log_query_engine()
        dashboard_data = query_engine.get_dashboard_data(hours=hours)

        logger.info(f"获取日志仪表板数据: 最近{hours}小时")

        return {
            "time_range": dashboard_data["time_range"],
            "statistics": dashboard_data["statistics"],
            "recent_errors": [LogResponse(**log) for log in dashboard_data["recent_errors"]],
            "recent_warnings": [LogResponse(**log) for log in dashboard_data["recent_warnings"]],
        }
    except Exception as e:
        logger.error(f"获取日志仪表板失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取日志仪表板失败: {str(e)}")


# ============ 日志文件管理 API（新增）============

class FileInfo(BaseModel):
    """文件信息模型"""
    name: str
    path: str
    type: str  # 'directory' | 'file'
    size: int  # 字节数
    size_formatted: str
    modified_time: str
    created_time: Optional[str] = None
    line_count: Optional[int] = None
    log_type: Optional[str] = None
    date: Optional[str] = None


class DirectoryNode(BaseModel):
    """目录树节点模型"""
    name: str
    path: str
    type: str  # 'root' | 'directory'
    children: List['DirectoryNode'] = []
    files: List[FileInfo] = []
    total_size: int = 0
    file_count: int = 0


class DiskUsage(BaseModel):
    """磁盘使用情况模型"""
    total_space: int
    used_space: int
    free_space: int
    usage_percent: float
    log_types: dict = {}


class AutoCleanupConfig(BaseModel):
    """自动清理配置模型"""
    enabled: bool = False
    retention_days: int = 30
    max_size_gb: int = 0  # 0表示不限制
    cleanup_schedule: str = 'daily'  # 'daily' | 'weekly'
    last_cleanup_time: Optional[str] = None
    next_cleanup_time: Optional[str] = None
    space_used: int = 0  # MB


class CleanupResult(BaseModel):
    """清理操作结果模型"""
    success: bool
    deleted_files: List[str] = []
    deleted_count: int = 0
    freed_space: int = 0  # 字节
    errors: List[dict] = []


@router.get("/files")
async def get_log_files():
    """
    获取日志目录结构和文件列表

    返回按类型和日期组织的日志文件树形结构。
    """
    try:
        from utils.file_log_manager import get_file_log_manager

        file_manager = get_file_log_manager()
        directory_tree = file_manager.get_directory_tree()

        logger.info("获取日志文件目录结构")

        return {
            "code": 0,
            "message": "获取成功",
            "data": directory_tree
        }
    except Exception as e:
        logger.error(f"获取日志文件列表失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取日志文件列表失败: {str(e)}")


@router.get("/files/{file_path:path}")
async def get_log_file_info(file_path: str):
    """
    获取单个日志文件的详细信息

    包括文件大小、行数、时间范围等元数据。
    """
    try:
        from pathlib import Path
        from utils.file_log_manager import get_file_log_manager

        file_manager = get_file_log_manager()
        full_path = Path(file_path)

        # 安全检查：确保路径在日志目录内
        if not str(full_path).startswith(str(file_manager.base_log_dir)):
            raise HTTPException(status_code=403, detail="访问路径不在允许的范围内")

        file_info = file_manager.get_file_info(full_path)

        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")

        logger.info(f"获取日志文件信息: {file_path}")

        return {
            "code": 0,
            "message": "获取成功",
            "data": file_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取日志文件信息失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取日志文件信息失败: {str(e)}")


@router.delete("/files/{file_path:path}")
async def delete_log_file(file_path: str):
    """
    删除单个日志文件

    执行前需在前端进行二次确认。
    """
    try:
        from pathlib import Path
        from utils.file_log_manager import get_file_log_manager

        file_manager = get_file_log_manager()
        full_path = Path(file_path)

        # 安全检查
        if not str(full_path).startswith(str(file_manager.base_log_dir)):
            raise HTTPException(status_code=403, detail="不允许删除此路径的文件")

        success = file_manager.delete_file(full_path)

        if success:
            logger.info(f"成功删除日志文件: {file_path}")
            return {
                "code": 0,
                "message": "删除成功",
                "data": CleanupResult(
                    success=True,
                    deleted_files=[file_path],
                    deleted_count=1,
                    freed_space=full_path.stat().st_size,
                )
            }
        else:
            raise HTTPException(status_code=500, detail="删除文件失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除日志文件失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"删除日志文件失败: {str(e)}")


@router.delete("/files/batch")
async def delete_log_files_batch(file_paths: List[str]):
    """
    批量删除多个日志文件

    支持一次删除多个文件，返回每个文件的删除结果。
    """
    try:
        from pathlib import Path
        from utils.file_log_manager import get_file_log_manager

        file_manager = get_file_log_manager()

        # 安全检查所有路径
        valid_paths = []
        for fp in file_paths:
            full_path = Path(fp)
            if str(full_path).startswith(str(file_manager.base_log_dir)):
                valid_paths.append(full_path)

        if len(valid_paths) != len(file_paths):
            raise HTTPException(status_code=400, detail="部分路径不在允许范围内")

        result = file_manager.delete_files_batch(valid_paths)

        logger.info(f"批量删除日志文件: 成功{result.get('deleted_count', 0)}个, 失败{len(result.get('errors', []))}个")

        return {
            "code": 0,
            "message": f"批量删除完成，成功 {result.get('deleted_count', 0)} 个",
            "data": CleanupResult(**result)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除日志文件失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"批量删除日志文件失败: {str(e)}")


@router.get("/disk-usage")
async def get_disk_usage():
    """
    获取日志目录的磁盘使用情况

    返回总空间、已用空间、各类型占用等统计信息。
    """
    try:
        from utils.file_log_manager import get_file_log_manager

        file_manager = get_file_log_manager()
        disk_usage = file_manager.get_disk_usage()

        logger.info("获取磁盘使用情况")

        return {
            "code": 0,
            "message": "获取成功",
            "data": DiskUsage(**disk_usage)
        }
    except Exception as e:
        logger.error(f"获取磁盘使用情况失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取磁盘使用情况失败: {str(e)}")


@router.get("/auto-cleanup/config")
async def get_auto_cleanup_config():
    """
    获取自动清理配置

    返回当前的自动清理设置参数。
    """
    try:
        # TODO: 从配置文件或数据库读取实际配置
        config = AutoCleanupConfig(
            enabled=False,
            retention_days=30,
            max_size_gb=10,
            cleanup_schedule='weekly',
            space_used=0,
        )

        logger.info("获取自动清理配置")

        return {
            "code": 0,
            "message": "获取成功",
            "data": config
        }
    except Exception as e:
        logger.error(f"获取自动清理配置失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"获取自动清理配置失败: {str(e)}")


@router.put("/auto-cleanup/config")
async def update_auto_cleanup_config(config: AutoCleanupConfig):
    """
    更新自动清理配置

    保存新的自动清理设置参数。
    """
    try:
        # TODO: 将配置保存到配置文件或数据库
        logger.info(f"更新自动清理配置: enabled={config.enabled}, days={config.retention_days}")

        return {
            "code": 0,
            "message": "配置更新成功",
            "data": {
                "success": True,
                "message": "配置更新成功",
                "config": config.model_dump(),
            }
        }
    except Exception as e:
        logger.error(f"更新自动清理配置失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"更新自动清理配置失败: {str(e)}")


@router.post("/cleanup/execute")
async def execute_manual_cleanup():
    """
    手动触发一次日志清理

    立即执行基于当前配置的清理操作。
    """
    try:
        query_engine = get_log_query_engine()
        result = query_engine.cleanup_old_logs(days=30)

        logger.info("手动执行日志清理完成")

        return {
            "code": 0,
            "message": "手动清理完成",
            "data": {
                "success": True,
                "message": "手动清理完成",
                **result,
            }
        }
    except Exception as e:
        logger.error(f"手动清理失败: {e}", exception=e)
        raise HTTPException(status_code=500, detail=f"手动清理失败: {str(e)}")
