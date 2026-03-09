"""AI模型性能监控模块

提供AI模型调用的性能监控功能，包括指标记录、统计计算和告警检查。
数据存储在内存中，定期持久化到JSON文件。
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
class PerformanceMonitor:
    """性能监控器（单例模式）

    用于监控AI模型调用的性能指标，包括请求耗时、Token使用量、成功率等。
    支持按模型和时间范围查询统计数据，并提供告警功能。

    Attributes:
        _instance: 单例实例
        _lock: 线程锁，用于保证线程安全
        _data: 内存中的监控数据
        _persistence_interval: 持久化间隔（秒）
        _data_file: 数据文件路径
        _last_persistence_time: 上次持久化时间
    """

    _instance: Optional["PerformanceMonitor"] = None
    _instance_lock = threading.Lock()

    # 告警阈值
    ALERT_LATENCY_THRESHOLD = 30.0  # 耗时阈值（秒）
    ALERT_FAILURE_RATE_THRESHOLD = 0.20  # 失败率阈值（20%）

    # 默认配置
    DEFAULT_PERSISTENCE_INTERVAL = 300  # 5分钟
    DEFAULT_DATA_FILE = "ai_model_performance.json"

    def __new__(cls, *args, **kwargs) -> "PerformanceMonitor":
        """创建单例实例"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        data_dir: Optional[str] = None,
        persistence_interval: int = DEFAULT_PERSISTENCE_INTERVAL,
    ):
        """初始化性能监控器

        Args:
            data_dir: 数据文件存储目录，默认为backend目录下的data文件夹
            persistence_interval: 数据持久化间隔（秒）
        """
        # 避免重复初始化
        if self._initialized:
            return

        self._lock = threading.Lock()
        self._data: List[Dict[str, Any]] = []
        self._persistence_interval = persistence_interval
        self._last_persistence_time = time.time()

        # 设置数据文件路径
        if data_dir:
            self._data_file = Path(data_dir) / self.DEFAULT_DATA_FILE
        else:
            # 默认存储在backend目录下的data文件夹
            backend_dir = Path(__file__).parent.parent
            data_dir_path = backend_dir / "data"
            data_dir_path.mkdir(exist_ok=True)
            self._data_file = data_dir_path / self.DEFAULT_DATA_FILE

        # 加载已有数据
        self._load_data()

        self._initialized = True
        logger.info(f"PerformanceMonitor初始化完成，数据文件: {self._data_file}")

    def _load_data(self) -> None:
        """从文件加载历史数据"""
        try:
            if self._data_file.exists():
                with open(self._data_file, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    # 转换时间字符串为datetime对象
                    for record in loaded_data:
                        if "timestamp" in record and isinstance(record["timestamp"], str):
                            record["timestamp"] = datetime.fromisoformat(record["timestamp"])
                    self._data = loaded_data
                logger.info(f"已加载 {len(self._data)} 条历史监控数据")
        except Exception as e:
            logger.error(f"加载监控数据失败: {e}")
            self._data = []

    def _persist_data(self, force: bool = False) -> None:
        """将数据持久化到文件

        Args:
            force: 是否强制持久化，忽略时间间隔
        """
        current_time = time.time()
        if not force and (current_time - self._last_persistence_time) < self._persistence_interval:
            return

        try:
            # 转换datetime对象为ISO格式字符串
            data_to_save = []
            for record in self._data:
                record_copy = record.copy()
                if "timestamp" in record_copy and isinstance(record_copy["timestamp"], datetime):
                    record_copy["timestamp"] = record_copy["timestamp"].isoformat()
                data_to_save.append(record_copy)

            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            self._last_persistence_time = current_time
            logger.debug(f"监控数据已持久化，共 {len(self._data)} 条记录")
        except Exception as e:
            logger.error(f"持久化监控数据失败: {e}")

    def record_request(
        self,
        model_id: str,
        success: bool,
        generation_time: float,
        tokens_used: Optional[int] = None,
        error_code: Optional[str] = None,
    ) -> None:
        """记录请求指标

        Args:
            model_id: 模型ID
            success: 请求是否成功
            generation_time: 生成耗时（秒）
            tokens_used: 使用的Token数量
            error_code: 错误代码（如果失败）
        """
        record = {
            "timestamp": datetime.now(),
            "model_id": model_id,
            "success": success,
            "generation_time": generation_time,
            "tokens_used": tokens_used,
            "error_code": error_code,
        }

        with self._lock:
            self._data.append(record)
            # 检查是否需要持久化
            self._persist_data()

        status = "成功" if success else "失败"
        logger.info(
            f"记录性能指标: 模型={model_id}, 状态={status}, "
            f"耗时={generation_time:.2f}s, Tokens={tokens_used}"
        )

    def get_stats(
        self,
        model_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取统计数据

        Args:
            model_id: 模型ID过滤，为None则统计所有模型
            start_date: 开始时间，为None则不限制
            end_date: 结束时间，为None则不限制

        Returns:
            包含统计数据的字典:
                - total_requests: 总请求数
                - successful_requests: 成功请求数
                - failed_requests: 失败请求数
                - success_rate: 成功率
                - avg_generation_time: 平均生成时间
                - min_generation_time: 最小生成时间
                - max_generation_time: 最大生成时间
                - avg_tokens_used: 平均Token使用量
                - total_tokens_used: 总Token使用量
        """
        with self._lock:
            return self._get_stats_internal(model_id, start_date, end_date)

    def _get_stats_internal(
        self,
        model_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """内部获取统计数据（不获取锁，调用者需确保线程安全）

        Args:
            model_id: 模型ID过滤，为None则统计所有模型
            start_date: 开始时间，为None则不限制
            end_date: 结束时间，为None则不限制

        Returns:
            包含统计数据的字典
        """
        filtered_data = self._filter_data(model_id, start_date, end_date)

        if not filtered_data:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "avg_generation_time": 0.0,
                "min_generation_time": 0.0,
                "max_generation_time": 0.0,
                "avg_tokens_used": 0.0,
                "total_tokens_used": 0,
            }

        total_requests = len(filtered_data)
        successful_requests = sum(1 for r in filtered_data if r["success"])
        failed_requests = total_requests - successful_requests
        success_rate = successful_requests / total_requests if total_requests > 0 else 0.0

        generation_times = [r["generation_time"] for r in filtered_data]
        avg_generation_time = sum(generation_times) / len(generation_times)
        min_generation_time = min(generation_times)
        max_generation_time = max(generation_times)

        # Token统计（排除None值）
        tokens_list = [r["tokens_used"] for r in filtered_data if r["tokens_used"] is not None]
        avg_tokens_used = sum(tokens_list) / len(tokens_list) if tokens_list else 0.0
        total_tokens_used = sum(tokens_list) if tokens_list else 0

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "success_rate": round(success_rate, 4),
            "avg_generation_time": round(avg_generation_time, 4),
            "min_generation_time": round(min_generation_time, 4),
            "max_generation_time": round(max_generation_time, 4),
            "avg_tokens_used": round(avg_tokens_used, 2),
            "total_tokens_used": total_tokens_used,
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取总体摘要

        Returns:
            包含总体统计和按模型分组的统计数据:
                - overall: 总体统计
                - by_model: 按模型分组的统计字典
                - time_range: 数据时间范围
        """
        with self._lock:
            if not self._data:
                return {
                    "overall": self._get_stats_internal(),
                    "by_model": {},
                    "time_range": None,
                }

            # 获取时间范围
            timestamps = [r["timestamp"] for r in self._data]
            min_time = min(timestamps)
            max_time = max(timestamps)

            # 总体统计
            overall_stats = self._get_stats_internal()

            # 按模型分组统计
            model_ids = set(r["model_id"] for r in self._data)
            by_model = {}
            for model_id in model_ids:
                by_model[model_id] = self._get_stats_internal(model_id=model_id)

            return {
                "overall": overall_stats,
                "by_model": by_model,
                "time_range": {
                    "start": min_time.isoformat() if isinstance(min_time, datetime) else min_time,
                    "end": max_time.isoformat() if isinstance(max_time, datetime) else max_time,
                },
            }

    def check_alerts(self) -> List[Dict[str, Any]]:
        """检查是否需要告警

        检查条件:
        - 耗时超过30秒
        - 失败率超过20%

        Returns:
            告警列表，每个告警包含:
                - type: 告警类型 ("high_latency" | "high_failure_rate")
                - model_id: 模型ID
                - message: 告警消息
                - value: 触发告警的值
                - threshold: 阈值
        """
        alerts = []

        with self._lock:
            if not self._data:
                return alerts

            # 获取所有模型ID
            model_ids = set(r["model_id"] for r in self._data)

            for model_id in model_ids:
                # 获取最近1小时的统计数据
                one_hour_ago = datetime.now() - timedelta(hours=1)
                stats = self._get_stats_internal(model_id=model_id, start_date=one_hour_ago)

                if stats["total_requests"] == 0:
                    continue

                # 检查高延迟
                if stats["avg_generation_time"] > self.ALERT_LATENCY_THRESHOLD:
                    alerts.append({
                        "type": "high_latency",
                        "model_id": model_id,
                        "message": f"模型 {model_id} 的平均生成时间 ({stats['avg_generation_time']:.2f}s) "
                                   f"超过阈值 ({self.ALERT_LATENCY_THRESHOLD}s)",
                        "value": stats["avg_generation_time"],
                        "threshold": self.ALERT_LATENCY_THRESHOLD,
                    })

                # 检查高失败率
                if stats["success_rate"] < (1 - self.ALERT_FAILURE_RATE_THRESHOLD):
                    failure_rate = 1 - stats["success_rate"]
                    alerts.append({
                        "type": "high_failure_rate",
                        "model_id": model_id,
                        "message": f"模型 {model_id} 的失败率 ({failure_rate:.2%}) "
                                   f"超过阈值 ({self.ALERT_FAILURE_RATE_THRESHOLD:.0%})",
                        "value": failure_rate,
                        "threshold": self.ALERT_FAILURE_RATE_THRESHOLD,
                    })

        if alerts:
            logger.warning(f"检测到 {len(alerts)} 个性能告警")

        return alerts

    def _filter_data(
        self,
        model_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """过滤数据

        Args:
            model_id: 模型ID过滤
            start_date: 开始时间过滤
            end_date: 结束时间过滤

        Returns:
            过滤后的数据列表
        """
        filtered = self._data

        if model_id:
            filtered = [r for r in filtered if r["model_id"] == model_id]

        if start_date:
            filtered = [
                r for r in filtered
                if isinstance(r["timestamp"], datetime) and r["timestamp"] >= start_date
            ]

        if end_date:
            filtered = [
                r for r in filtered
                if isinstance(r["timestamp"], datetime) and r["timestamp"] <= end_date
            ]

        return filtered

    def clear_data(self, older_than_days: Optional[int] = None) -> int:
        """清除数据

        Args:
            older_than_days: 清除指定天数之前的数据，为None则清除所有数据

        Returns:
            清除的数据条数
        """
        with self._lock:
            if older_than_days is None:
                count = len(self._data)
                self._data = []
            else:
                cutoff_date = datetime.now() - timedelta(days=older_than_days)
                old_count = len(self._data)
                self._data = [
                    r for r in self._data
                    if isinstance(r["timestamp"], datetime) and r["timestamp"] >= cutoff_date
                ]
                count = old_count - len(self._data)

            self._persist_data(force=True)

        logger.info(f"已清除 {count} 条监控数据")
        return count

    def force_persist(self) -> None:
        """强制立即持久化数据"""
        self._persist_data(force=True)


# 全局监控器实例
def get_performance_monitor() -> PerformanceMonitor:
    """获取性能监控器实例

    Returns:
        PerformanceMonitor单例实例
    """
    return PerformanceMonitor()
