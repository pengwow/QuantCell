# 定时任务管理器，用于管理和执行定时任务

import json
from datetime import datetime
from typing import Dict, List, Optional

from apscheduler.job import Job
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from collector.db.models import ScheduledTaskBusiness
from collector.scripts.get_data import GetData


class ScheduledTaskManager:
    """定时任务管理器，用于管理和执行定时任务
    
    实现单例模式，确保全局只有一个定时任务管理器实例
    集成APScheduler框架，支持CRON、间隔和单次执行
    """
    
    _instance = None
    
    def __new__(cls):
        """创建单例实例
        
        Returns:
            ScheduledTaskManager: 定时任务管理器实例
        """
        if cls._instance is None:
            cls._instance = super(ScheduledTaskManager, cls).__new__(cls)
            cls._instance._scheduler = None
            cls._instance._jobs = {}
            cls._instance._init_scheduler()
        return cls._instance
    
    def _init_scheduler(self):
        """初始化调度器"""
        try:
            # 创建后台调度器
            self._scheduler = BackgroundScheduler()
            logger.info("APScheduler初始化成功")
        except Exception as e:
            logger.error(f"APScheduler初始化失败: {e}")
            raise
    
    def start(self):
        """启动调度器"""
        try:
            if not self._scheduler.running:
                self._scheduler.start()
                logger.info("APScheduler调度器已启动")
                # 从数据库加载所有定时任务
                self.load_tasks_from_db()
            else:
                logger.warning("APScheduler调度器已经在运行中")
        except Exception as e:
            logger.error(f"启动APScheduler调度器失败: {e}")
            raise
    
    def shutdown(self):
        """关闭调度器"""
        try:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=True)
                logger.info("APScheduler调度器已关闭")
        except Exception as e:
            logger.error(f"关闭APScheduler调度器失败: {e}")
            raise
    
    def load_tasks_from_db(self):
        """从数据库加载所有定时任务"""
        try:
            # 获取所有启用的定时任务
            tasks = ScheduledTaskBusiness.get_all(filters={"status": ["pending", "running"]})
            
            for task_id, task_info in tasks.items():
                self.add_task(task_info)
            
            logger.info(f"从数据库加载了 {len(tasks)} 个定时任务")
        except Exception as e:
            logger.error(f"从数据库加载定时任务失败: {e}")
    
    def add_task(self, task_info: Dict):
        """添加定时任务
        
        Args:
            task_info: 任务信息字典
        """
        try:
            task_id = task_info["id"]
            
            # 检查任务是否已经存在
            if str(task_id) in self._jobs:
                logger.warning(f"定时任务已存在: task_id={task_id}")
                return
            
            # 根据频率类型创建触发器
            trigger = self._create_trigger(task_info)
            if not trigger:
                logger.error(f"创建触发器失败: task_id={task_id}")
                return
            
            # 添加任务到调度器
            job = self._scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                id=str(task_id),
                name=task_info["name"],
                args=[task_id],
                replace_existing=True
            )
            
            # 保存任务信息
            self._jobs[str(task_id)] = job
            
            # 更新数据库中的下次执行时间
            next_run_time = job.next_run_time
            ScheduledTaskBusiness.update(
                task_id=task_id,
                next_run_time=next_run_time
            )
            
            logger.info(f"定时任务已添加: task_id={task_id}, name={task_info['name']}, next_run_time={next_run_time}")
        except Exception as e:
            logger.error(f"添加定时任务失败: task_id={task_info.get('id')}, error={e}")
    
    def update_task(self, task_info: Dict):
        """更新定时任务
        
        Args:
            task_info: 任务信息字典
        """
        try:
            task_id = task_info["id"]
            task_id_str = str(task_id)
            
            # 先移除旧任务
            if task_id_str in self._jobs:
                self.remove_task(task_id)
            
            # 添加新任务
            self.add_task(task_info)
            
            logger.info(f"定时任务已更新: task_id={task_id}, name={task_info['name']}")
        except Exception as e:
            logger.error(f"更新定时任务失败: task_id={task_id}, error={e}")
    
    def remove_task(self, task_id: int):
        """移除定时任务
        
        Args:
            task_id: 任务ID
        """
        try:
            task_id_str = str(task_id)
            
            # 从调度器中移除任务
            if task_id_str in self._jobs:
                self._scheduler.remove_job(task_id_str)
                del self._jobs[task_id_str]
            
            logger.info(f"定时任务已移除: task_id={task_id}")
        except Exception as e:
            logger.error(f"移除定时任务失败: task_id={task_id}, error={e}")
    
    def pause_task(self, task_id: int):
        """暂停定时任务
        
        Args:
            task_id: 任务ID
        """
        try:
            task_id_str = str(task_id)
            
            # 暂停调度器中的任务
            if task_id_str in self._jobs:
                self._scheduler.pause_job(task_id_str)
            
            # 更新数据库中的任务状态
            ScheduledTaskBusiness.update(
                task_id=task_id,
                status="paused"
            )
            
            logger.info(f"定时任务已暂停: task_id={task_id}")
        except Exception as e:
            logger.error(f"暂停定时任务失败: task_id={task_id}, error={e}")
    
    def resume_task(self, task_id: int):
        """恢复定时任务
        
        Args:
            task_id: 任务ID
        """
        try:
            task_id_str = str(task_id)
            
            # 恢复调度器中的任务
            if task_id_str in self._jobs:
                self._scheduler.resume_job(task_id_str)
            
            # 更新数据库中的任务状态
            ScheduledTaskBusiness.update(
                task_id=task_id,
                status="running"
            )
            
            logger.info(f"定时任务已恢复: task_id={task_id}")
        except Exception as e:
            logger.error(f"恢复定时任务失败: task_id={task_id}, error={e}")
    
    def get_job(self, task_id: int) -> Optional[Job]:
        """获取任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Job]: 任务对象，如果任务不存在则返回None
        """
        return self._jobs.get(str(task_id))
    
    def get_all_jobs(self) -> List[Job]:
        """获取所有任务
        
        Returns:
            List[Job]: 所有任务对象列表
        """
        return list(self._jobs.values())
    
    def _create_trigger(self, task_info: Dict):
        """根据任务信息创建触发器
        
        Args:
            task_info: 任务信息字典
            
        Returns:
            Optional[Trigger]: 触发器对象，如果创建失败则返回None
        """
        frequency_type = task_info.get("frequency_type")
        
        if frequency_type == "cron":
            # CRON触发器
            cron_expression = task_info.get("cron_expression")
            if cron_expression:
                return CronTrigger.from_crontab(cron_expression)
        elif frequency_type == "interval":
            # 间隔触发器
            interval = task_info.get("interval")
            if interval:
                # 解析间隔字符串，如1h, 1d, 1w
                return self._parse_interval_trigger(interval)
        elif frequency_type == "date":
            # 单次执行触发器
            start_time = task_info.get("start_time")
            if start_time:
                return DateTrigger(run_date=start_time)
        elif frequency_type == "hourly":
            # 每小时执行
            return IntervalTrigger(hours=1)
        elif frequency_type == "daily":
            # 每天执行
            return IntervalTrigger(days=1)
        elif frequency_type == "weekly":
            # 每周执行
            return IntervalTrigger(weeks=1)
        elif frequency_type == "monthly":
            # 每月执行
            return IntervalTrigger(days=30)
        
        logger.error(f"不支持的频率类型: frequency_type={frequency_type}")
        return None
    
    def _parse_interval_trigger(self, interval_str: str):
        """解析间隔字符串，创建间隔触发器
        
        Args:
            interval_str: 间隔字符串，如1h, 1d, 1w
            
        Returns:
            Optional[IntervalTrigger]: 间隔触发器对象，如果解析失败则返回None
        """
        try:
            # 解析间隔字符串
            # 支持的格式：数字+单位，如1h, 30m, 2d, 1w
            unit = interval_str[-1]
            value = int(interval_str[:-1])
            
            if unit == "s":
                return IntervalTrigger(seconds=value)
            elif unit == "m":
                return IntervalTrigger(minutes=value)
            elif unit == "h":
                return IntervalTrigger(hours=value)
            elif unit == "d":
                return IntervalTrigger(days=value)
            elif unit == "w":
                return IntervalTrigger(weeks=value)
            else:
                logger.error(f"不支持的时间单位: unit={unit}")
                return None
        except Exception as e:
            logger.error(f"解析间隔字符串失败: interval_str={interval_str}, error={e}")
            return None
    
    def _execute_task(self, task_id: int):
        """执行定时任务
        
        Args:
            task_id: 任务ID
        """
        logger.info(f"开始执行定时任务: task_id={task_id}")
        
        # 更新任务状态为运行中
        ScheduledTaskBusiness.update(
            task_id=task_id,
            status="running",
            last_run_time=datetime.now(timezone.utc)
        )
        
        try:
            # 获取任务信息
            task_info = ScheduledTaskBusiness.get(task_id)
            if not task_info:
                logger.error(f"定时任务不存在: task_id={task_id}")
                return
            
            logger.info(f"执行定时任务: {task_info['name']}, type={task_info['task_type']}")
            
            # 根据任务类型执行不同的操作
            if task_info["task_type"] == "download_crypto":
                # 执行加密货币数据下载
                self._download_crypto_data(task_info)
            else:
                logger.error(f"不支持的任务类型: task_type={task_info['task_type']}")
                
            # 更新任务状态为已完成
            ScheduledTaskBusiness.update(
                task_id=task_id,
                status="completed",
                last_result="success",
                run_count=task_info.get("run_count", 0) + 1,
                success_count=task_info.get("success_count", 0) + 1
            )
            
            logger.info(f"定时任务执行成功: task_id={task_id}, name={task_info['name']}")
        except Exception as e:
            logger.error(f"定时任务执行失败: task_id={task_id}, error={e}")
            
            # 更新任务状态为失败
            task_info = ScheduledTaskBusiness.get(task_id)
            if task_info:
                ScheduledTaskBusiness.update(
                    task_id=task_id,
                    status="failed",
                    last_result="failed",
                    error_message=str(e),
                    run_count=task_info.get("run_count", 0) + 1,
                    fail_count=task_info.get("fail_count", 0) + 1
                )
    
    def _download_crypto_data(self, task_info: Dict):
        """执行加密货币数据下载
        
        Args:
            task_info: 任务信息字典
        """
        try:
            # 解析任务参数
            symbols = task_info.get("symbols", [])
            exchange = task_info.get("exchange", "binance")
            candle_type = task_info.get("candle_type", "spot")
            save_dir = task_info.get("save_dir", "data/crypto_data")
            max_workers = task_info.get("max_workers", 1)
            incremental_enabled = task_info.get("incremental_enabled", True)
            
            # 获取上次采集日期
            last_collected_date = task_info.get("last_collected_date")
            
            logger.info(f"开始下载加密货币数据: symbols={symbols}, exchange={exchange}, incremental_enabled={incremental_enabled}, last_collected_date={last_collected_date}")
            
            # 创建GetData实例
            get_data = GetData(
                symbols=symbols,
                exchange=exchange,
                candle_type=candle_type,
                save_dir=save_dir,
                max_workers=max_workers
            )
            
            # 执行下载
            # 这里需要根据incremental_enabled和last_collected_date来决定下载时间范围
            if incremental_enabled and last_collected_date:
                # 增量下载，从上次采集日期到现在
                get_data.run(start_date=last_collected_date)
            else:
                # 全量下载
                get_data.run()
            
            # 更新上次采集日期
            ScheduledTaskBusiness.update(
                task_id=task_info["id"],
                last_collected_date=datetime.now(timezone.utc)
            )
            
            logger.info(f"加密货币数据下载完成: symbols={symbols}, exchange={exchange}")
        except Exception as e:
            logger.error(f"下载加密货币数据失败: error={e}")
            raise


# 创建全局定时任务管理器实例
scheduled_task_manager = ScheduledTaskManager()
