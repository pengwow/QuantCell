"""
系统管理API路由

提供系统指标和日志查询功能
日志查询基于文件日志系统实现。
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import APIRouter, Query

from collector.schemas import ApiResponse
from collector.services.system_service import SystemService
from utils.log_query_engine import get_log_query_engine


router = APIRouter(prefix="/system", tags=["system"])

# 系统服务实例
system_service = SystemService()


class SystemMetrics(BaseModel):
    """系统指标模型"""
    connectionStatus: str = Field(..., description="连接状态")
    cpuUsage: float = Field(..., description="CPU使用率")
    memoryUsed: str = Field(..., description="已用内存")
    memoryTotal: str = Field(..., description="总内存")
    diskUsed: str = Field(..., description="已用磁盘空间")
    diskTotal: str = Field(..., description="总磁盘空间")
    lastUpdated: str = Field(..., description="最后更新时间")


class LogEntry(BaseModel):
    """日志条目模型"""
    id: int = Field(..., description="日志ID")
    timestamp: str = Field(..., description="日志时间")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志内容")
    module: Optional[str] = Field(None, description="模块名称")
    function: Optional[str] = Field(None, description="函数名称")
    line: Optional[int] = Field(None, description="代码行号")
    logger_name: Optional[str] = Field(None, description="日志器名称")
    log_type: Optional[str] = Field(None, description="日志类型")
    extra_data: Optional[dict] = Field(None, description="额外数据")
    exception_info: Optional[str] = Field(None, description="异常信息")
    trace_id: Optional[str] = Field(None, description="跟踪ID")
    created_at: Optional[str] = Field(None, description="创建时间")


class LogQueryResponse(BaseModel):
    """日志查询响应模型"""
    records: list[LogEntry] = Field(..., description="日志列表")
    total: int = Field(..., description="总日志数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    hasMore: bool = Field(..., description="是否有更多数据")


@router.get("/metrics", response_model=ApiResponse)
async def get_system_metrics():
    """
    获取系统指标

    返回系统当前的各种指标数据，包括：
    - connectionStatus: 连接状态
    - cpuUsage: CPU使用率
    - memoryUsed: 已用内存
    - memoryTotal: 总内存
    - diskUsed: 已用磁盘空间
    - diskTotal: 总磁盘空间
    - lastUpdated: 最后更新时间
    """
    try:
        # 获取系统状态
        system_status = system_service.get_system_status()

        # 解析内存和磁盘信息
        memory_parts = system_status.get("memory_usage", "0GB / 0GB").split(" / ")
        disk_parts = system_status.get("disk_space", "0GB / 0GB").split(" / ")

        # 构建响应数据
        metrics = SystemMetrics(
            connectionStatus="connected",  # 默认连接状态
            cpuUsage=system_status.get("cpu_usage", 0),
            memoryUsed=memory_parts[0] if len(memory_parts) > 0 else "0 GB",
            memoryTotal=memory_parts[1] if len(memory_parts) > 1 else "0 GB",
            diskUsed=disk_parts[0] if len(disk_parts) > 0 else "0 GB",
            diskTotal=disk_parts[1] if len(disk_parts) > 1 else "0 GB",
            lastUpdated=system_status.get("timestamp", datetime.now().isoformat())
        )

        return ApiResponse(
            code=0,
            message="获取系统指标成功",
            data=metrics.model_dump()
        )

    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"获取系统指标失败: {str(e)}",
            data=None
        )


@router.get("/logs", response_model=ApiResponse)
async def get_system_logs(
    level: Optional[str] = Query(None, description="日志级别过滤 (DEBUG, INFO, WARNING, ERROR)"),
    start_time: Optional[str] = Query(None, description="开始时间 (ISO格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO格式)"),
    source: Optional[str] = Query(None, description="日志来源过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小")
):
    """
    获取系统日志

    查询系统日志记录，支持按级别、时间范围和来源过滤
    基于文件日志系统实现高性能查询。

    - **level**: 日志级别过滤 (DEBUG, INFO, WARNING, ERROR)
    - **start_time**: 开始时间 (ISO格式)
    - **end_time**: 结束时间 (ISO格式)
    - **source**: 日志来源过滤
    - **page**: 页码，从1开始
    - **page_size**: 每页大小，范围1-100
    """
    try:
        # 解析时间参数
        parsed_start_time = None
        parsed_end_time = None

        if start_time:
            try:
                parsed_start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except ValueError:
                pass

        if end_time:
            try:
                parsed_end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except ValueError:
                pass

        # 使用文件日志查询引擎查询日志
        query_engine = get_log_query_engine()
        result = query_engine.query_logs(
            level=level if level else None,
            log_type=source if source else None,
            start_time=parsed_start_time,
            end_time=parsed_end_time,
            page=page,
            page_size=page_size
        )

        # 转换日志数据
        logs = []
        for log in result.logs:
            logs.append(LogEntry(
                id=log.get("id", 0),
                timestamp=log.get("timestamp", ""),
                level=log.get("level", "INFO"),
                message=log.get("message", ""),
                module=log.get("module"),
                function=log.get("function"),
                line=log.get("line"),
                logger_name=log.get("logger_name"),
                log_type=log.get("log_type"),
                extra_data=log.get("extra_data"),
                exception_info=log.get("exception_info"),
                trace_id=log.get("trace_id"),
                created_at=log.get("created_at")
            ))

        # 计算是否有更多数据
        pagination = result.pagination
        total = pagination.get("total", 0)
        current_page = pagination.get("page", page)
        pages = pagination.get("pages", 1)
        has_more = current_page < pages

        response_data = LogQueryResponse(
            records=logs,
            total=total,
            page=current_page,
            page_size=pagination.get("page_size", page_size),
            hasMore=has_more
        )

        return ApiResponse(
            code=0,
            message="获取系统日志成功",
            data=response_data.model_dump()
        )

    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"获取系统日志失败: {str(e)}",
            data=None
        )
