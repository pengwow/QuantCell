# 定时任务管理API

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from collector.db.models import ScheduledTaskBusiness
from collector.schemas import ApiResponse, ScheduledTaskCreate, ScheduledTaskUpdate
from collector.utils.scheduled_task_manager import scheduled_task_manager

# 创建API路由实例
router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


@router.get("/", response_model=ApiResponse)
async def get_all_scheduled_tasks(
    status: Optional[str] = Query(None, description="任务状态过滤"),
    task_type: Optional[str] = Query(None, description="任务类型过滤")
):
    """获取所有定时任务
    
    获取系统中所有的定时任务，支持按状态和任务类型过滤
    
    Args:
        status: 任务状态过滤，可选值：pending, running, completed, failed, paused
        task_type: 任务类型过滤，可选值：download_crypto等
    
    Returns:
        ApiResponse: API响应，包含所有定时任务列表
    """
    try:
        logger.info(f"获取所有定时任务，过滤条件: status={status}, task_type={task_type}")
        
        # 构建过滤条件
        filters = {}
        if status:
            filters["status"] = status
        if task_type:
            filters["task_type"] = task_type
        
        # 获取所有定时任务
        tasks = ScheduledTaskBusiness.get_all(filters=filters)
        
        logger.info(f"获取到 {len(tasks)} 个定时任务")
        
        return ApiResponse(
            code=0,
            message="获取定时任务成功",
            data={
                "tasks": list(tasks.values()),
                "total": len(tasks)
            }
        )
    except Exception as e:
        logger.error(f"获取定时任务失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=ApiResponse)
async def get_scheduled_task(task_id: int):
    """获取指定定时任务详情
    
    Args:
        task_id: 定时任务ID
    
    Returns:
        ApiResponse: API响应，包含指定定时任务的详细信息
    """
    try:
        logger.info(f"获取定时任务详情: task_id={task_id}")
        
        # 获取定时任务详情
        task = ScheduledTaskBusiness.get(task_id)
        
        if not task:
            logger.error(f"定时任务不存在: task_id={task_id}")
            return ApiResponse(
                code=404,
                message="定时任务不存在",
                data={}
            )
        
        logger.info(f"获取定时任务详情成功: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="获取定时任务详情成功",
            data={"task": task}
        )
    except Exception as e:
        logger.error(f"获取定时任务详情失败: task_id={task_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ApiResponse)
async def create_scheduled_task(request: ScheduledTaskCreate):
    """创建新的定时任务
    
    Args:
        request: 定时任务创建请求参数
    
    Returns:
        ApiResponse: API响应，包含创建的定时任务信息
    """
    try:
        logger.info(f"创建定时任务: request={request.model_dump()}")
        
        # 创建定时任务
        task_id = ScheduledTaskBusiness.create(
            name=request.name,
            description=request.description,
            task_type=request.task_type,
            cron_expression=request.cron_expression,
            interval=request.interval,
            start_time=request.start_time,
            end_time=request.end_time,
            frequency_type=request.frequency_type,
            symbols=request.symbols,
            exchange=request.exchange,
            candle_type=request.candle_type,
            save_dir=request.save_dir,
            max_workers=request.max_workers,
            incremental_enabled=request.incremental_enabled,
            notification_enabled=request.notification_enabled,
            notification_type=request.notification_type,
            notification_email=request.notification_email,
            notification_webhook=request.notification_webhook,
            created_by="system"  # 可以根据实际情况修改为当前用户
        )
        
        if not task_id:
            logger.error("创建定时任务失败")
            return ApiResponse(
                code=500,
                message="创建定时任务失败",
                data={}
            )
        
        # 获取新创建的定时任务信息
        task = ScheduledTaskBusiness.get(task_id)
        
        if task:
            # 添加到调度器
            scheduled_task_manager.add_task(task)
        
        logger.info(f"创建定时任务成功: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="创建定时任务成功",
            data={"task": task}
        )
    except Exception as e:
        logger.error(f"创建定时任务失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}", response_model=ApiResponse)
async def update_scheduled_task(task_id: int, request: ScheduledTaskUpdate):
    """更新定时任务
    
    Args:
        task_id: 定时任务ID
        request: 定时任务更新请求参数
    
    Returns:
        ApiResponse: API响应，包含更新后的定时任务信息
    """
    try:
        logger.info(f"更新定时任务: task_id={task_id}, request={request.model_dump()}")
        
        # 更新定时任务
        success = ScheduledTaskBusiness.update(
            task_id=task_id,
            name=request.name,
            description=request.description,
            status=request.status,
            cron_expression=request.cron_expression,
            interval=request.interval,
            start_time=request.start_time,
            end_time=request.end_time,
            frequency_type=request.frequency_type,
            symbols=request.symbols,
            exchange=request.exchange,
            candle_type=request.candle_type,
            save_dir=request.save_dir,
            max_workers=request.max_workers,
            incremental_enabled=request.incremental_enabled,
            notification_enabled=request.notification_enabled,
            notification_type=request.notification_type,
            notification_email=request.notification_email,
            notification_webhook=request.notification_webhook
        )
        
        if not success:
            logger.error(f"更新定时任务失败: task_id={task_id}")
            return ApiResponse(
                code=500,
                message="更新定时任务失败",
                data={}
            )
        
        # 获取更新后的定时任务信息
        task = ScheduledTaskBusiness.get(task_id)
        
        if task:
            # 更新调度器中的任务
            scheduled_task_manager.update_task(task)
        
        logger.info(f"更新定时任务成功: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="更新定时任务成功",
            data={"task": task}
        )
    except Exception as e:
        logger.error(f"更新定时任务失败: task_id={task_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}", response_model=ApiResponse)
async def delete_scheduled_task(task_id: int):
    """删除定时任务
    
    Args:
        task_id: 定时任务ID
    
    Returns:
        ApiResponse: API响应，包含删除结果
    """
    try:
        logger.info(f"删除定时任务: task_id={task_id}")
        
        # 从调度器中移除任务
        scheduled_task_manager.remove_task(task_id)
        
        # 删除定时任务
        success = ScheduledTaskBusiness.delete(task_id)
        
        if not success:
            logger.error(f"删除定时任务失败: task_id={task_id}")
            return ApiResponse(
                code=500,
                message="删除定时任务失败",
                data={}
            )
        
        logger.info(f"删除定时任务成功: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="删除定时任务成功",
            data={}
        )
    except Exception as e:
        logger.error(f"删除定时任务失败: task_id={task_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/run", response_model=ApiResponse)
async def run_scheduled_task_now(task_id: int):
    """立即执行定时任务
    
    立即执行指定的定时任务，而不等待调度时间
    
    Args:
        task_id: 定时任务ID
    
    Returns:
        ApiResponse: API响应，包含执行结果
    """
    try:
        logger.info(f"立即执行定时任务: task_id={task_id}")
        
        # 获取定时任务信息
        task = ScheduledTaskBusiness.get(task_id)
        
        if not task:
            logger.error(f"定时任务不存在: task_id={task_id}")
            return ApiResponse(
                code=404,
                message="定时任务不存在",
                data={}
            )
        
        # 立即执行任务
        from collector.utils.scheduled_task_manager import scheduled_task_manager
        import threading
        
        # 在后台线程中执行任务，避免阻塞API响应
        def _run_task():
            try:
                scheduled_task_manager._execute_task(task_id)
            except Exception as e:
                logger.error(f"立即执行定时任务失败: task_id={task_id}, error={e}")
        
        # 启动后台线程执行任务
        threading.Thread(target=_run_task).start()
        
        logger.info(f"立即执行定时任务请求已提交: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="定时任务已开始执行",
            data={}
        )
    except Exception as e:
        logger.error(f"立即执行定时任务失败: task_id={task_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/pause", response_model=ApiResponse)
async def pause_scheduled_task(task_id: int):
    """暂停定时任务
    
    暂停指定的定时任务，暂停后任务将不再按照调度执行
    
    Args:
        task_id: 定时任务ID
    
    Returns:
        ApiResponse: API响应，包含暂停结果
    """
    try:
        logger.info(f"暂停定时任务: task_id={task_id}")
        
        # 暂停定时任务
        scheduled_task_manager.pause_task(task_id)
        
        logger.info(f"暂停定时任务成功: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="暂停定时任务成功",
            data={}
        )
    except Exception as e:
        logger.error(f"暂停定时任务失败: task_id={task_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/resume", response_model=ApiResponse)
async def resume_scheduled_task(task_id: int):
    """恢复定时任务
    
    恢复指定的定时任务，恢复后任务将按照调度继续执行
    
    Args:
        task_id: 定时任务ID
    
    Returns:
        ApiResponse: API响应，包含恢复结果
    """
    try:
        logger.info(f"恢复定时任务: task_id={task_id}")
        
        # 恢复定时任务
        scheduled_task_manager.resume_task(task_id)
        
        logger.info(f"恢复定时任务成功: task_id={task_id}")
        
        return ApiResponse(
            code=0,
            message="恢复定时任务成功",
            data={}
        )
    except Exception as e:
        logger.error(f"恢复定时任务失败: task_id={task_id}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))
