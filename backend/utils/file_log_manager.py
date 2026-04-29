# -*- coding: utf-8 -*-
"""
文件日志管理器

提供基于文件的日志存储和查询功能，替代数据库日志系统。
使用 JSON Lines 格式存储日志，支持高效的查询和分析。
"""

import os
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from contextlib import contextmanager
import re

from utils.logger import LogRecord


@dataclass
class LogFilters:
    """日志查询过滤器"""
    level: Optional[str] = None
    log_type: Optional[str] = None
    module: Optional[str] = None
    trace_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    keyword: Optional[str] = None


@dataclass
class PaginatedResult:
    """分页查询结果"""
    logs: List[Dict[str, Any]] = field(default_factory=list)
    pagination: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogStatistics:
    """日志统计信息"""
    total_count: int = 0
    by_level: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)


class FileLogManager:
    """
    文件日志管理器

    负责日志的文件存储、查询和管理工作。
    使用线程锁确保并发安全性。
    """

    _instance: Optional["FileLogManager"] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, base_log_dir: str = None) -> "FileLogManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, base_log_dir: str = None):
        if self._initialized:
            return

        self._initialized = True

        # 设置基础日志目录
        if base_log_dir:
            self.base_log_dir = Path(base_log_dir)
        else:
            backend_path = Path(__file__).resolve().parent.parent
            self.base_log_dir = backend_path / "logs" / "system"

        # 创建目录结构
        self.base_log_dir.mkdir(parents=True, exist_ok=True)

        # 写入锁（确保并发写入安全）
        self._write_lock = threading.Lock()

        # 缓存最近打开的文件句柄（优化性能）
        self._file_handles: Dict[str, Any] = {}
        self._file_lock = threading.Lock()

    def _get_log_file_path(self, log_type: str, date: datetime = None) -> Path:
        """
        获取日志文件路径

        Args:
            log_type: 日志类型
            date: 日期，默认为当前日期

        Returns:
            Path: 日志文件路径
        """
        if date is None:
            date = datetime.utcnow()

        # 创建类型子目录
        type_dir = self.base_log_dir / log_type
        type_dir.mkdir(exist_ok=True)

        # 按日期生成文件名：{type}_{YYYYMMDD}.log
        filename = f"{log_type}_{date.strftime('%Y%m%d')}.log"
        return type_dir / filename

    @contextmanager
    def _open_file_for_writing(self, file_path: Path):
        """
        获取文件写入句柄（带缓存）

        使用上下文管理器确保资源正确释放
        """
        file_key = str(file_path)

        with self._file_lock:
            if file_key in self._file_handles:
                handle = self._file_handles[file_key]
            else:
                handle = open(file_path, 'a', encoding='utf-8', buffering=8192)
                self._file_handles[file_key] = handle

        try:
            yield handle
            handle.flush()
        except Exception as e:
            print(f"[FileLogManager] 写入错误: {e}", file=__import__('sys').stderr)

    def write_log(self, record: LogRecord) -> bool:
        """
        写入单条日志记录

        Args:
            record: 日志记录对象

        Returns:
            bool: 写入成功返回True
        """
        try:
            # 转换为字典
            log_dict = record.to_dict()

            # 序列化为JSON字符串
            json_str = json.dumps(log_dict, ensure_ascii=False, separators=(',', ':'))

            # 获取目标文件路径
            file_path = self._get_log_file_path(record.log_type, record.timestamp)

            # 原子写入（使用锁保证并发安全）
            with self._write_lock:
                with self._open_file_for_writing(file_path) as f:
                    f.write(json_str + '\n')

            return True

        except Exception as e:
            print(f"[FileLogManager] 写入日志失败: {e}", file=__import__('sys').stderr)
            return False

    def write_batch(self, records: List[LogRecord]) -> int:
        """
        批量写入日志记录

        Args:
            records: 日志记录列表

        Returns:
            int: 成功写入的数量
        """
        success_count = 0

        # 按日志类型分组
        grouped: Dict[str, List[LogRecord]] = {}
        for record in records:
            if record.log_type not in grouped:
                grouped[record.log_type] = []
            grouped[record.log_type].append(record)

        # 分组批量写入
        for log_type, type_records in grouped.items():
            try:
                lines = []
                for record in type_records:
                    log_dict = record.to_dict()
                    json_str = json.dumps(log_dict, ensure_ascii=False, separators=(',', ':'))
                    lines.append(json_str)

                # 获取该类型的最新文件路径
                file_path = self._get_log_file_path(log_type)

                with self._write_lock:
                    with self._open_file_for_writing(file_path) as f:
                        f.write('\n'.join(lines) + '\n')

                success_count += len(type_records)

            except Exception as e:
                print(f"[FileLogManager] 批量写入失败 ({log_type}): {e}",
                      file=__import__('sys').stderr)

        return success_count

    def query_logs(
        self,
        filters: LogFilters,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResult:
        """
        查询日志记录

        支持多种过滤条件组合查询，结果按时间倒序排列。

        Args:
            filters: 过滤条件
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            PaginatedResult: 包含日志列表和分页信息
        """
        all_logs = []

        # 遍历所有日志文件
        log_files = self._get_log_files_in_range(filters.start_time, filters.end_time)

        for file_path in log_files:
            try:
                file_logs = self._read_and_filter_file(file_path, filters)
                all_logs.extend(file_logs)
            except Exception as e:
                print(f"[FileLogManager] 读取文件失败 {file_path}: {e}",
                      file=__import__('sys').stderr)

        # 按时间戳倒序排序
        all_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # 计算总数
        total = len(all_logs)

        # 计算分页
        pages = (total + page_size - 1) // page_size if total > 0 else 0
        offset = (page - 1) * page_size
        paginated_logs = all_logs[offset:offset + page_size]

        return PaginatedResult(
            logs=paginated_logs,
            pagination={
                'page': page,
                'page_size': page_size,
                'total': total,
                'pages': pages,
            }
        )

    def get_recent_logs(
        self,
        minutes: int = 60,
        limit: int = 100,
        level: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的日志记录

        Args:
            minutes: 最近多少分钟
            limit: 返回数量限制
            level: 日志级别过滤（可选）

        Returns:
            List[Dict]: 日志列表
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=minutes)

        filters = LogFilters(
            start_time=start_time,
            end_time=end_time,
            level=level
        )

        result = self.query_logs(filters, page=1, page_size=limit)
        return result.logs

    def get_logs_by_trace_id(
        self,
        trace_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResult:
        """
        根据跟踪ID获取相关日志

        Args:
            trace_id: 跟踪ID
            page: 页码
            page_size: 每页数量

        Returns:
            PaginatedResult: 相关日志列表
        """
        filters = LogFilters(trace_id=trace_id)
        return self.query_logs(filters, page=page, page_size=page_size)

    def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> LogStatistics:
        """
        获取日志统计信息

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            LogStatistics: 统计信息
        """
        filters = LogFilters(start_time=start_time, end_time=end_time)

        # 获取所有匹配的日志（不分页，用于统计）
        result = self.query_logs(filters, page=1, page_size=1000000)

        by_level: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for log in result.logs:
            level = log.get('level', 'UNKNOWN')
            log_type = log.get('log_type', 'UNKNOWN')

            by_level[level] = by_level.get(level, 0) + 1
            by_type[log_type] = by_type.get(log_type, 0) + 1

        return LogStatistics(
            total_count=result.pagination.get('total', 0),
            by_level=by_level,
            by_type=by_type,
        )

    def cleanup_old_logs(self, days: int = 30) -> int:
        """
        清理指定天数之前的旧日志文件

        Args:
            days: 保留天数

        Returns:
            int: 删除的文件数量
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        deleted_count = 0

        try:
            # 遍历所有子目录
            for type_dir in self.base_log_dir.iterdir():
                if not type_dir.is_dir():
                    continue

                # 遍历该类型下的日志文件
                for log_file in type_dir.iterdir():
                    if not log_file.suffix == '.log':
                        continue

                    # 从文件名解析日期
                    try:
                        # 文件名格式：{type}_YYYYMMDD.log
                        parts = log_file.stem.split('_')
                        if len(parts) >= 2:
                            file_date_str = parts[-1]
                            file_date = datetime.strptime(file_date_str, '%Y%m%d')

                            # 如果文件日期早于截止日期，删除文件
                            if file_date < cutoff_date:
                                log_file.unlink()
                                deleted_count += 1
                                print(f"[FileLogManager] 删除旧日志: {log_file}")
                    except (ValueError, IndexError):
                        continue

        except Exception as e:
            print(f"[FileLogManager] 清理旧日志失败: {e}",
                  file=__import__('sys').stderr)

        return deleted_count

    def _get_log_files_in_range(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Path]:
        """
        获取指定时间范围内的日志文件列表

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            List[Path]: 日志文件路径列表（按时间倒序）
        """
        files = []

        try:
            for type_dir in self.base_log_dir.iterdir():
                if not type_dir.is_dir():
                    continue

                for log_file in type_dir.iterdir():
                    if not log_file.suffix == '.log' or not log_file.exists():
                        continue

                    # 如果没有时间范围限制，返回所有文件
                    if start_time is None and end_time is None:
                        files.append(log_file)
                        continue

                    # 从文件名解析日期进行预筛选
                    try:
                        parts = log_file.stem.split('_')
                        if len(parts) >= 2:
                            file_date_str = parts[-1]
                            file_date = datetime.strptime(file_date_str, '%Y%m%d')

                            # 检查文件是否在时间范围内
                            in_range = True
                            if start_time and file_date.date() < start_time.date():
                                in_range = False
                            if end_time and file_date.date() > end_time.date():
                                in_range = False

                            if in_range:
                                files.append(log_file)
                    except (ValueError, IndexError):
                        # 无法解析日期的文件也包含在内
                        files.append(log_file)

        except Exception as e:
            print(f"[FileLogManager] 获取日志文件列表失败: {e}",
                  file=__import__('sys').stderr)

        # 按文件修改时间倒序排列（最新的在前）
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        return files

    def _read_and_filter_file(
        self,
        file_path: Path,
        filters: LogFilters
    ) -> List[Dict[str, Any]]:
        """
        读取并过滤单个日志文件

        流式读取避免内存爆炸，逐行解析和过滤。

        Args:
            file_path: 日志文件路径
            filters: 过滤条件

        Returns:
            List[Dict]: 匹配的日志记录列表
        """
        matched_logs = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        log_entry = json.loads(line)

                        # 应用过滤条件
                        if not self._match_filters(log_entry, filters):
                            continue

                        matched_logs.append(log_entry)

                    except json.JSONDecodeError:
                        # 跳过格式错误的行
                        continue

        except Exception as e:
            print(f"[FileLogManager] 读取文件出错 {file_path}: {e}",
                  file=__import__('sys').stderr)

        return matched_logs

    def _match_filters(self, log_entry: Dict[str, Any], filters: LogFilters) -> bool:
        """
        检查日志记录是否匹配所有过滤条件

        Args:
            log_entry: 日志记录字典
            filters: 过滤条件

        Returns:
            bool: 是否匹配
        """
        try:
            # 日志级别过滤（不区分大小写）
            if filters.level:
                if log_entry.get('level', '').upper() != filters.level.upper():
                    return False

            # 日志类型过滤
            if filters.log_type:
                if log_entry.get('log_type') != filters.log_type:
                    return False

            # 模块名称模糊匹配
            if filters.module:
                module = log_entry.get('module', '')
                if filters.module.lower() not in module.lower():
                    return False

            # 跟踪ID精确匹配
            if filters.trace_id:
                if log_entry.get('trace_id') != filters.trace_id:
                    return False

            # 时间范围过滤
            if filters.start_time or filters.end_time:
                timestamp_str = log_entry.get('timestamp', '')
                if timestamp_str:
                    try:
                        log_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

                        if filters.start_time and log_time < filters.start_time:
                            return False
                        if filters.end_time and log_time > filters.end_time:
                            return False
                    except (ValueError, AttributeError):
                        pass

            # 关键词搜索（在message中搜索）
            if filters.keyword:
                message = log_entry.get('message', '')
                if filters.keyword.lower() not in message.lower():
                    return False

            # 所有条件都通过
            return True

        except Exception as e:
            # 解析异常时默认不匹配
            print(f"[FileLogManager] 过滤条件匹配异常: {e}",
                  file=__import__('sys').stderr)
            return False

    def close(self):
        """关闭所有打开的文件句柄"""
        with self._file_lock:
            for file_key, handle in self._file_handles.items():
                try:
                    handle.close()
                except Exception as e:
                    print(f"[FileLogManager] 关闭文件句柄失败 {file_key}: {e}",
                          file=__import__('sys').stderr)

            self._file_handles.clear()

    def get_directory_tree(self) -> Dict[str, Any]:
        """
        获取日志目录的树形结构

        Returns:
            dict: 包含目录树、文件列表和统计信息的字典
        """
        tree = {
            'name': 'logs',
            'path': str(self.base_log_dir),
            'type': 'root',
            'children': [],
            'files': [],
            'total_size': 0,
            'file_count': 0,
        }

        try:
            if not self.base_log_dir.exists():
                return tree

            for type_dir in sorted(self.base_log_dir.iterdir()):
                if not type_dir.is_dir():
                    continue

                type_node = {
                    'name': type_dir.name,
                    'path': str(type_dir),
                    'type': 'directory',
                    'children': [],
                    'files': [],
                    'total_size': 0,
                    'file_count': 0,
                }

                for log_file in sorted(type_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
                    if not log_file.suffix == '.log':
                        continue

                    try:
                        stat = log_file.stat()
                        file_info = {
                            'name': log_file.name,
                            'path': str(log_file),
                            'type': 'file',
                            'size': stat.st_size,
                            'size_formatted': self._format_size(stat.st_size),
                            'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'created_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            'line_count': None,
                            'log_type': type_dir.name,
                            'date': self._extract_date_from_filename(log_file.name),
                        }

                        type_node['files'].append(file_info)
                        type_node['total_size'] += stat.st_size
                        type_node['file_count'] += 1
                        tree['total_size'] += stat.st_size
                        tree['file_count'] += 1

                    except Exception as e:
                        print(f"[FileLogManager] 获取文件信息失败 {log_file}: {e}",
                              file=__import__('sys').stderr)
                        continue

                tree['children'].append(type_node)

        except Exception as e:
            print(f"[FileLogManager] 获取目录树失败: {e}",
                  file=__import__('sys').stderr)

        return tree

    def get_file_info(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        获取单个文件的详细信息

        Args:
            file_path: 文件路径

        Returns:
            Optional[Dict]: 文件信息字典，不存在返回None
        """
        try:
            if not file_path.exists() or not file_path.is_file():
                return None

            stat = file_path.stat()

            # 计算行数（快速估算）
            line_count = None
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                pass

            return {
                'name': file_path.name,
                'path': str(file_path),
                'type': 'file',
                'size': stat.st_size,
                'size_formatted': self._format_size(stat.st_size),
                'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'created_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'line_count': line_count,
                'log_type': file_path.parent.name if file_path.parent != self.base_log_dir else None,
                'date': self._extract_date_from_filename(file_path.name),
            }

        except Exception as e:
            print(f"[FileLogManager] 获取文件信息失败 {file_path}: {e}",
                  file=__import__('sys').stderr)
            return None

    def delete_file(self, file_path: Path) -> bool:
        """
        安全删除单个日志文件

        Args:
            file_path: 要删除的文件路径

        Returns:
            bool: 删除成功返回True
        """
        try:
            if not file_path.exists():
                print(f"[FileLogManager] 文件不存在: {file_path}",
                      file=__import__('sys').stderr)
                return False

            # 安全检查：确保在日志目录内
            if not str(file_path.resolve()).startswith(str(self.base_log_dir.resolve())):
                print(f"[FileLogManager] 不允许删除此路径: {file_path}",
                      file=__import__('sys').stderr)
                return False

            file_path.unlink()
            print(f"[FileLogManager] 成功删除文件: {file_path}")
            return True

        except Exception as e:
            print(f"[FileLogManager] 删除文件失败 {file_path}: {e}",
                  file=__import__('sys').stderr)
            return False

    def delete_files_batch(self, file_paths: List[Path]) -> Dict[str, Any]:
        """
        批量删除多个日志文件

        Args:
            file_paths: 要删除的文件路径列表

        Returns:
            Dict: 包含删除结果的字典
        """
        result = {
            'success': True,
            'deleted_files': [],
            'deleted_count': 0,
            'freed_space': 0,
            'errors': [],
        }

        for file_path in file_paths:
            try:
                if self.delete_file(file_path):
                    result['deleted_files'].append(str(file_path))
                    result['deleted_count'] += 1
                    result['freed_space'] += file_path.stat().st_size if file_path.exists() else 0
                else:
                    result['success'] = False
                    result['errors'].append({
                        'file': str(file_path),
                        'error': '删除失败或权限不足',
                    })
            except Exception as e:
                result['success'] = False
                result['errors'].append({
                    'file': str(file_path),
                    'error': str(e),
                })

        return result

    def get_disk_usage(self) -> Dict[str, Any]:
        """
        获取磁盘使用统计信息

        Returns:
            Dict: 磁盘使用情况
        """
        import shutil

        total_size = 0
        log_types_stats = {}

        try:
            total, used, free = shutil.disk_usage(self.base_log_dir)

            if self.base_log_dir.exists():
                for type_dir in self.base_log_dir.iterdir():
                    if not type_dir.is_dir():
                        continue

                    type_size = 0
                    type_count = 0

                    for log_file in type_dir.rglob('*.log'):
                        if log_file.is_file():
                            type_size += log_file.stat().st_size
                            type_count += 1

                    log_types_stats[type_dir.name] = {
                        'count': type_count,
                        'total_size': type_size,
                    }
                    total_size += type_size

            usage_percent = (total_size / used * 100) if used > 0 else 0

            return {
                'total_space': total,
                'used_space': used,
                'free_space': free,
                'usage_percent': round(usage_percent, 2),
                'log_types': log_types_stats,
                'logs_total_size': total_size,
            }

        except Exception as e:
            print(f"[FileLogManager] 获取磁盘使用情况失败: {e}",
                  file=__import__('sys').stderr)
            return {
                'total_space': 0,
                'used_space': 0,
                'free_space': 0,
                'usage_percent': 0,
                'log_types': {},
                'logs_total_size': 0,
            }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(size_bytes) < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    @staticmethod
    def _extract_date_from_filename(filename: str) -> Optional[str]:
        """从文件名提取日期（YYYYMMDD格式）"""
        try:
            parts = filename.replace('.log', '').split('_')
            if len(parts) >= 2:
                date_str = parts[-1]
                if len(date_str) == 8 and date_str.isdigit():
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        except (ValueError, IndexError):
            pass
        return None


# 全局实例缓存
_file_log_manager_instance: Optional[FileLogManager] = None
_instance_lock = threading.Lock()


def get_file_log_manager(base_log_dir: str = None) -> FileLogManager:
    """
    获取文件日志管理器的全局单例

    Args:
        base_log_dir: 基础日志目录（可选，仅在首次调用时生效）

    Returns:
        FileLogManager: 文件日志管理器实例
    """
    global _file_log_manager_instance

    if _file_log_manager_instance is None:
        with _instance_lock:
            if _file_log_manager_instance is None:
                _file_log_manager_instance = FileLogManager(base_log_dir)

    return _file_log_manager_instance


def shutdown_file_log_manager():
    """关闭文件日志管理器（应用退出时调用）"""
    global _file_log_manager_instance

    if _file_log_manager_instance:
        _file_log_manager_instance.close()
        _file_log_manager_instance = None
