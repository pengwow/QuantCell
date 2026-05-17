"""
Worker核心服务层

提供Worker管理的基础CRUD操作框架，支持同步和异步双模式：
- 同步模式：供CLI命令行工具使用
- 异步模式：供FastAPI接口使用

独立于FastAPI，可直接导入使用
"""

from typing import Dict, List, Optional, Any, Generator, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import os
import json
import subprocess
import signal
import fcntl
import tempfile
import asyncio
import sys
import time
from pathlib import Path

from . import models, crud, schemas
from .worker_state import worker_state_manager, WorkerStateManager
from .worker_system import worker_system, WorkerSystem
from collector.db.database import SessionLocal, init_database_config
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class WorkerOperationError(Exception):
    """Worker操作失败异常"""

    def __init__(self, operation: str, worker_id: int = None, message: str = None):
        self.operation = operation
        self.worker_id = worker_id
        if worker_id:
            self.message = message or f"Worker {worker_id} {operation} 操作失败"
        else:
            self.message = message or f"{operation} 操作失败"
        super().__init__(self.message)


class StrategyLoadError(WorkerOperationError):
    """策略加载失败"""

    def __init__(self, worker_id: int = None, message: str = None):
        super().__init__("策略加载", worker_id, message or "无法加载策略文件")


class ConfigPreparationError(WorkerOperationError):
    """配置准备失败"""

    def __init__(self, worker_id: int = None, message: str = None):
        super().__init__("配置准备", worker_id, message or "交易配置准备失败")


class WorkerStartError(WorkerOperationError):
    """Worker 启动失败"""

    def __init__(self, worker_id: int = None, message: str = None):
        super().__init__("启动", worker_id, message or "Worker 启动失败")


class WorkerNotFoundError(Exception):
    """Worker未找到异常"""

    def __init__(self, worker_id: int, message: str = None):
        self.worker_id = worker_id
        self.message = message or f"Worker {worker_id} 不存在"
        super().__init__(self.message)


class WorkerAlreadyRunningError(Exception):
    """Worker已在运行异常"""

    def __init__(self, worker_id: int, message: str = None):
        self.worker_id = worker_id
        self.message = message or f"Worker {worker_id} 已在运行中"
        super().__init__(self.message)


class LogQueryError(WorkerOperationError):
    """日志查询失败"""

    def __init__(self, worker_id: int = None, message: str = None):
        super().__init__("日志查询", worker_id, message or "日志查询失败")


class MetricsError(WorkerOperationError):
    """性能指标获取失败"""

    def __init__(self, worker_id: int = None, message: str = None):
        super().__init__("性能指标", worker_id, message or "获取性能指标失败")


class WorkerManagerLock:
    """WorkerManager 文件锁，防止多实例冲突"""

    def __init__(self):
        lock_dir = Path(tempfile.gettempdir())
        self.lock_file = lock_dir / "quantcell_worker_manager.lock"
        self._lock_fd = None

    def acquire(self, blocking=True) -> bool:
        """
        获取锁

        Args:
            blocking: 是否阻塞等待

        Returns:
            bool: 是否成功获取锁
        """
        try:
            self._lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | (0 if not blocking else fcntl.LOCK_NB))
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
            return True
        except (IOError, OSError):
            if self._lock_fd:
                self._lock_fd.close()
                self._lock_fd = None
            return False

    def release(self):
        """释放锁"""
        if self._lock_fd:
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                self._lock_fd.close()
            except Exception:
                pass
            finally:
                self._lock_fd = None

    def is_locked(self) -> bool:
        """检查是否已被锁定"""
        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read().strip())
                    os.kill(pid, 0)
                    return True
            except (ProcessLookupError, ValueError):
                self.lock_file.unlink(missing_ok=False)
                return False
        return False

    def get_owner_pid(self) -> Optional[int]:
        """获取锁持有者的 PID"""
        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    return int(f.read().strip())
            except (ValueError, IOError):
                pass
        return None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class WorkerCoreService:
    """
    Worker核心服务类（单例模式）

    提供Worker的基础CRUD操作，支持同步和异步两种调用模式：
    - 同步方法：以 create_worker、get_worker 等命名，适合CLI使用
    - 异步方法：以 async_create_worker、async_get_worker 等命名，适合API使用
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._config = self._load_config()
        self._worker_manager = None

        # 获取 WorkerSystem 单例（延迟初始化）
        self.system = worker_system

        # 保留原有的 manager 引用（向后兼容）
        # 但实际操作会委托给 self.system
        self.manager = getattr(self.system, 'manager', None)

        self._register_state_event_handlers()
        logger.info(f"[WorkerCoreService] 初始化完成（Facade模式），配置已加载，状态管理器已集成")

    @classmethod
    def reset_instance(cls):
        """重置单例状态（用于测试）"""
        cls._instance = None

    def _ensure_initialized(self) -> None:
        """
        检查 WorkerSystem 是否已初始化（Facade 模式的安全检查）

        在所有委托方法的开头调用，确保 WorkerSystem 已经完成初始化。
        提供清晰的错误信息，帮助调用方快速定位问题。

        Raises:
            RuntimeError: 如果 WorkerSystem 未完成初始化
        """
        if not hasattr(self, 'system') or self.system is None:
            raise RuntimeError(
                "WorkerCoreService [Facade]: WorkerSystem 单例未正确加载。"
                "请检查 worker_system 模块是否正常导入。"
            )

        if not self.system._fully_initialized:
            raise RuntimeError(
                "WorkerCoreService [Facade]: WorkerSystem 尚未完成初始化。"
                "请先调用 await worker_system.initialize() 完成初始化。"
                "\n提示：通常在应用启动时（main.py 或 lifespan 事件中）调用一次即可。"
            )

        logger.debug("[WorkerCoreService] [Facade] WorkerSystem 初始化检查通过")

    def _load_config(self) -> Dict[str, Any]:
        """从环境变量和默认配置文件加载配置"""
        config = {
            "db_path": os.environ.get("DB_FILE", "data/quantcell_sqlite.db"),
            "db_type": os.environ.get("DB_TYPE", "sqlite"),
            "log_dir": os.environ.get("LOG_DIR", "logs"),
            "default_page_size": int(os.environ.get("DEFAULT_PAGE_SIZE", "20")),
            "max_page_size": int(os.environ.get("MAX_PAGE_SIZE", "100")),
        }

        default_config_file = os.path.join(
            os.path.dirname(__file__), "..", "config", "worker_default.json"
        )
        if os.path.exists(default_config_file):
            try:
                with open(default_config_file, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                    config.update(file_config)
                    logger.debug(f"[WorkerCoreService] 从配置文件加载配置: {default_config_file}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[WorkerCoreService] 配置文件读取失败: {e}")

        return config

    @contextmanager
    def get_db(self) -> Generator[Session, None, None]:
        """
        获取同步数据库会话（上下文管理器）

        用于CLI等同步场景，确保会话正确关闭

        Yields:
            Session: SQLAlchemy数据库会话
        """
        init_database_config()
        db = SessionLocal()
        try:
            yield db
        except Exception as e:
            db.rollback()
            logger.error(f"[WorkerCoreService] 数据库操作异常: {e}")
            raise
        finally:
            db.close()

    @asynccontextmanager
    async def async_get_db(self) -> AsyncGenerator[Session, None]:
        """
        获取异步数据库会话（上下文管理器）

        用于API等异步场景，确保会话正确关闭

        Yields:
            Session: SQLAlchemy数据库会话
        """
        init_database_config()
        db = SessionLocal()
        try:
            yield db
        except Exception as e:
            db.rollback()
            logger.error(f"[WorkerCoreService] 数据库操作异常: {e}")
            raise
        finally:
            db.close()

    # ==================== 同步CRUD方法（供CLI使用） ====================

    def create_worker(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建Worker（同步版本）

        Args:
            data: Worker创建数据字典，应符合schemas.WorkerCreate格式

        Returns:
            创建成功的Worker字典

        Raises:
            WorkerOperationError: 创建失败时抛出
        """
        try:
            self._ensure_initialized()
            logger.debug(f"[WorkerCoreService] [Facade] 委托创建Worker到 WorkerSystem")
            result = self.system.create_worker(data)

            # 获取完整的 Worker 信息（兼容返回值格式）
            worker_info = self.system.get_worker(result)
            if worker_info:
                logger.info(f"[WorkerCoreService] [Facade] Worker创建成功: id={result}, name={worker_info.get('name')}")
                return worker_info
            else:
                # 如果无法获取完整信息，返回基本结果
                logger.info(f"[WorkerCoreService] [Facade] Worker创建成功: id={result}")
                return {"id": result, "status": "stopped"}

        except Exception as e:
            logger.error(f"[WorkerCoreService] [Facade] 创建Worker失败: {e}")
            raise WorkerOperationError("create", message=str(e))

    def get_worker(self, worker_id: int) -> Dict[str, Any]:
        """
        获取Worker详情（同步版本）

        Args:
            worker_id: Worker ID

        Returns:
            Worker详情字典

        Raises:
            WorkerNotFoundError: Worker不存在时抛出
        """
        self._ensure_initialized()
        logger.debug(f"[WorkerCoreService] [Facade] 委托获取Worker {worker_id} 到 WorkerSystem")
        result = self.system.get_worker(worker_id)

        if not result:
            raise WorkerNotFoundError(worker_id)

        logger.debug(f"[WorkerCoreService] [Facade] Worker {worker_id} 获取成功")
        return result

    def list_workers(
        self,
        status: Optional[str] = None,
        strategy_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        获取Worker列表（同步版本，支持分页）

        Args:
            status: 按状态筛选
            strategy_id: 按策略ID筛选
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            包含items、total、page、page_size的字典
        """
        self._ensure_initialized()
        logger.debug(f"[WorkerCoreService] [Facade] 委托获取Worker列表到 WorkerSystem (status={status})")

        # 委托给 WorkerSystem 的 list_workers 方法
        workers_list = self.system.list_workers(status_filter=status)

        # TODO: WorkerSystem.list_workers 目前不支持分页和 strategy_id 筛选
        # 如果需要这些功能，后续需要在 WorkerSystem 中扩展或保留原有逻辑
        # 当前先实现基本委托，保持向后兼容的返回格式

        total = len(workers_list)

        # 手动实现简单的分页（如果需要）
        if page and page_size:
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            workers_list = workers_list[start_idx:end_idx]

        logger.debug(f"[WorkerCoreService] [Facade] 获取到 {total} 个Worker，返回第 {page} 页")
        return {
            "items": workers_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_worker(self, worker_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新Worker（同步版本）

        Args:
            worker_id: Worker ID
            data: 更新数据字典，应符合schemas.WorkerUpdate格式

        Returns:
            更新后的Worker字典

        Raises:
            WorkerNotFoundError: Worker不存在时抛出
            WorkerOperationError: 更新失败时抛出
        """
        try:
            with self.get_db() as db:
                worker_data = schemas.WorkerUpdate(**data)
                worker = crud.update_worker(db, worker_id, worker_data)
                if not worker:
                    raise WorkerNotFoundError(worker_id)
                result = worker.to_dict()
                logger.info(f"[WorkerCoreService] Worker更新成功: id={worker_id}")
                return result
        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[WorkerCoreService] 更新Worker失败: worker_id={worker_id}, error={e}")
            raise WorkerOperationError("update", worker_id, message=str(e))

    def delete_worker(self, worker_id: int) -> bool:
        """
        删除Worker（同步版本）

        Args:
            worker_id: Worker ID

        Returns:
            是否删除成功

        Raises:
            WorkerNotFoundError: Worker不存在时抛出
        """
        self._ensure_initialized()
        logger.debug(f"[WorkerCoreService] [Facade] 委托删除Worker {worker_id} 到 WorkerSystem")
        result = self.system.delete_worker(worker_id)

        logger.info(f"[WorkerCoreService] [Facade] Worker {worker_id} 删除成功")
        return result

    def clone_worker(
        self,
        worker_id: int,
        new_name: str,
        copy_config: bool = True,
        copy_parameters: bool = True,
    ) -> Dict[str, Any]:
        """
        克隆Worker（同步版本）

        Args:
            worker_id: 源Worker ID
            new_name: 新Worker名称
            copy_config: 是否复制配置
            copy_parameters: 是否复制参数

        Returns:
            新克隆的Worker字典

        Raises:
            WorkerNotFoundError: 源Worker不存在时抛出
            WorkerOperationError: 克隆失败时抛出
        """
        try:
            with self.get_db() as db:
                request = schemas.WorkerCloneRequest(
                    new_name=new_name,
                    copy_config=copy_config,
                    copy_parameters=copy_parameters,
                )
                new_worker = crud.clone_worker(db, worker_id, request)
                result = new_worker.to_dict()
                logger.info(
                    f"[WorkerCoreService] Worker克隆成功: "
                    f"源ID={worker_id}, 新ID={result['id']}, 名称={new_name}"
                )
                return result
        except ValueError as e:
            if "不存在" in str(e):
                raise WorkerNotFoundError(worker_id)
            raise WorkerOperationError("clone", worker_id, message=str(e))
        except Exception as e:
            logger.error(f"[WorkerCoreService] 克隆Worker失败: worker_id={worker_id}, error={e}")
            raise WorkerOperationError("clone", worker_id, message=str(e))

    # ==================== 异步CRUD方法（供API使用） ====================

    async def async_create_worker(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建Worker（异步版本）"""
        return self.create_worker(data)

    async def async_get_worker(self, worker_id: int) -> Dict[str, Any]:
        """获取Worker详情（异步版本）"""
        return self.get_worker(worker_id)

    async def async_list_workers(
        self,
        status: Optional[str] = None,
        strategy_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """获取Worker列表（异步版本）"""
        return self.list_workers(status, strategy_id, page, page_size)

    async def async_update_worker(self, worker_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新Worker（异步版本）"""
        return self.update_worker(worker_id, data)

    async def async_delete_worker(self, worker_id: int) -> bool:
        """删除Worker（异步版本）"""
        return self.delete_worker(worker_id)

    async def async_clone_worker(
        self,
        worker_id: int,
        new_name: str,
        copy_config: bool = True,
        copy_parameters: bool = True,
    ) -> Dict[str, Any]:
        """克隆Worker（异步版本）"""
        return self.clone_worker(worker_id, new_name, copy_config, copy_parameters)

    def update_worker_config(self, worker_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新 Worker 配置（同步版本）

        Args:
            worker_id: Worker ID
            config: 配置字典

        Returns:
            更新后的Worker字典

        Raises:
            WorkerNotFoundError: Worker不存在时抛出
            WorkerOperationError: 更新失败时抛出
        """
        try:
            with self.get_db() as db:
                worker = crud.update_worker_config(db, worker_id, config)
                if not worker:
                    raise WorkerNotFoundError(worker_id)
                result = worker.to_dict()
                logger.info(f"[WorkerCoreService] Worker配置更新成功: id={worker_id}")
                return result
        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[WorkerCoreService] 更新Worker配置失败: worker_id={worker_id}, error={e}")
            raise WorkerOperationError("更新配置", worker_id, message=str(e))

    async def async_update_worker_config(self, worker_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """更新Worker配置（异步版本）"""
        return self.update_worker_config(worker_id, config)

    # ==================== 批量操作 ====================

    def batch_operation(self, worker_ids: List[int], operation: str) -> Dict[str, Any]:
        """
        批量操作Worker（增强版 - 通过状态机验证）

        改进点：
        1. 所有状态变更必须通过 StateMachineGuard 验证
        2. 返回详细的结果列表（包含旧状态和新状态）
        3. 支持审计追溯
        4. 自动记录非法转换尝试

        Args:
            worker_ids: Worker ID列表
            operation: 操作类型 (start/stop/restart)

        Returns:
            包含success、failed、total、results的字典
            results 中包含每个 Worker 的详细新旧状态信息
        """
        from .state_guard import StateMachineGuard, WorkerState

        valid_operations = {
            "start": WorkerState.STARTING,
            "stop": WorkerState.STOPPING,
            "restart": WorkerState.RESTARTING,
        }

        if operation not in valid_operations:
            raise WorkerOperationError(
                operation,
                message=f"不支持的操作类型: {operation}，支持的操作: {list(valid_operations.keys())}",
            )

        target_state = valid_operations[operation]
        guard = StateMachineGuard()

        # 使用增强的批量转换方法（自动进行状态机验证）
        batch_result = asyncio.get_event_loop().run_until_complete(
            guard.batch_transition(worker_ids, target_state, operation)
        )

        # 转换为兼容旧接口的格式
        result = {
            "success": batch_result.success_ids,
            "failed": batch_result.failed_dict,
            "total": batch_result.total,
            "results": batch_result.results,  # 新增：详细的操作结果
        }

        logger.info(
            f"[WorkerCoreService] 批量{operation}完成 (状态机验证): "
            f"成功={len(batch_result.success_ids)}, "
            f"失败={len(batch_result.failed_dict)}, "
            f"总计={batch_result.total}"
        )

        return result

    async def async_batch_operation(
        self, worker_ids: List[int], operation: str
    ) -> Dict[str, Any]:
        """批量操作Worker（异步版本）"""
        return self.batch_operation(worker_ids, operation)

    # ==================== 辅助方法 ====================

    def get_worker_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取Worker"""
        with self.get_db() as db:
            from sqlalchemy import or_

            worker = (
                db.query(models.Worker)
                .filter(
                    or_(
                        models.Worker.name == name,
                        models.Worker.name.ilike(f"%{name}%"),
                    )
                )
                .first()
            )
            if worker:
                return worker.to_dict()
            return None

    def check_worker_exists(self, worker_id: int) -> bool:
        """检查Worker是否存在"""
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            return worker is not None

    def get_worker_count(self, status: Optional[str] = None) -> int:
        """获取Worker数量"""
        with self.get_db() as db:
            query = db.query(models.Worker)
            if status:
                query = query.filter(models.Worker.status == status)
            return query.count()

    # ==================== Worker 生命周期管理方法 ====================

    def _register_state_event_handlers(self):
        """
        注册状态变更事件监听器

        在初始化时调用，将状态管理器的事件与 core_service 的处理逻辑绑定
        """
        worker_state_manager.register_handler("state_changed", self._handle_state_change)
        logger.info("[WorkerCoreService] 状态变更事件监听器已注册")

    def _handle_state_change(self, event_data: Dict[str, Any]):
        """
        处理 Worker 状态变更事件

        Args:
            event_data: 事件数据字典，包含 worker_id, old_status, new_status, timestamp
        """
        worker_id = event_data.get("worker_id")
        old_status = event_data.get("old_status")
        new_status = event_data.get("new_status")
        timestamp = event_data.get("timestamp")

        logger.info(
            f"[状态事件] Worker {worker_id} 状态变更: "
            f"{old_status} -> {new_status} (时间: {timestamp})"
        )

        if new_status == "error":
            error_msg = event_data.get("error_message", "未知错误")
            logger.warning(
                f"[状态事件] ⚠️ Worker {worker_id} 进入错误状态: {error_msg}"
            )
        elif new_status == "running":
            logger.info(
                f"[状态事件] ✅ Worker {worker_id} 已成功启动并进入运行状态"
            )

    async def get_worker_state(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """
        从 state_manager 获取 Worker 完整状态对象

        Args:
            worker_id: Worker ID

        Returns:
            Worker 状态字典，如果不存在返回 None
        """
        state = await worker_state_manager.get_state(worker_id)
        if state:
            return state.to_dict()
        return None

    def _get_manager(self):
        """
        获取或创建 WorkerManager 实例（懒加载 + 线程安全）

        Returns:
            TradingNodeWorkerManager: Worker 管理器实例
        """
        if self._worker_manager is None:
            logger.info("[WorkerCoreService] 初始化 TradingNodeWorkerManager...")
            from .manager import TradingNodeWorkerManager

            self._worker_manager = TradingNodeWorkerManager()
            logger.info("[WorkerCoreService] TradingNodeWorkerManager 创建成功")
        return self._worker_manager

    def _load_strategy(
        self, worker: models.Worker, db: Session
    ) -> tuple:
        """
        加载策略代码或路径（多层回退机制）

        Args:
            worker: Worker 模型实例
            db: 数据库会话

        Returns:
            tuple: (strategy_path: Optional[str], strategy_code: Optional[str], strategy_found: bool)

        Layer 1: 从数据库 strategy 表通过 ID 查询（最优先）
        Layer 1.5: 从数据库通过 strategy_name 查询（新增容错）
        Layer 2: 通过 strategy_file_name 参数查找文件
        Layer 2.5: 通过 strategy_name 模糊匹配文件系统（新增）
        Layer 3: 文件系统扫描兜底（增强版：支持模糊匹配）
        """
        import json as json_lib
        from pathlib import Path
        from difflib import SequenceMatcher

        # 确定策略目录的绝对路径（基于 core_service.py 文件位置）
        # core_service.py 在 backend/worker/ 目录下
        # 策略目录在 backend/strategies/ 目录下
        _backend_dir = Path(__file__).parent.parent.resolve()
        _strategies_dir = _backend_dir / "strategies"

        logger.info(f"[策略加载] 📁 策略目录完整路径: {_strategies_dir.absolute()}")
        logger.info(f"[策略加载] 📁 策略目录是否存在: {_strategies_dir.exists()}")

        if _strategies_dir.exists():
            available_strategy_files = list(_strategies_dir.glob("*.py"))
            available_names = [f.stem for f in available_strategy_files if f.stem != "__init__"]
            logger.info(f"[策略加载] 📁 可用策略文件 ({len(available_names)}个): {', '.join(available_names[:10])}{'...' if len(available_names) > 10 else ''}")
        else:
            logger.error(f"[策略加载] ❌ 策略目录不存在: {_strategies_dir.absolute()}")

        strategy_path = None
        strategy_code = None
        strategy_found = False

        worker_config = {}
        if worker.config:
            try:
                worker_config = (
                    json_lib.loads(worker.config)
                    if isinstance(worker.config, str)
                    else worker_config
                )
            except Exception:
                pass

        strategy_file_name_from_config = worker_config.get("strategy_file_name")
        strategy_name_from_worker = getattr(worker, 'strategy_name', None)  # 新增：获取策略名称

        if worker.strategy_id or strategy_file_name_from_config or strategy_name_from_worker:
            # Layer 1: 从数据库查询（最优先）- 通过 ID
            if worker.strategy_id:
                from strategy.models import Strategy

                strategy = (
                    db.query(Strategy)
                    .filter(Strategy.id == worker.strategy_id)
                    .first()
                )

                if strategy:
                    strategy_found = True
                    if strategy.code:
                        strategy_code = strategy.code
                        logger.info(
                            f"[策略加载] ✅ Layer 1: 使用数据库策略代码 "
                            f"(策略: {strategy.name}, ID: {strategy.id})"
                        )
                    elif strategy.file_name:
                        # 使用绝对路径
                        strategy_path = str(_strategies_dir / strategy.file_name)
                        logger.info(
                            f"[策略加载] ✅ Layer 1: 使用策略文件名 "
                            f"(策略: {strategy.name}, 文件: {strategy.file_name})"
                        )
                    else:
                        logger.warning(
                            f"[策略加载] ⚠️ Layer 1: 数据库策略缺少 code 和 file_name "
                            f"(ID: {strategy.id})"
                        )
                else:
                    logger.warning(
                        f"[策略加载] ⚠️ Layer 1: 数据库未找到 strategy_id={worker.strategy_id}"
                    )

            # Layer 1.5: 从数据库查询 - 通过 strategy_name（新增容错机制）
            if not strategy_found and strategy_name_from_worker:
                from strategy.models import Strategy

                logger.info(
                    f"[策略加载] 🔍 Layer 1.5: 尝试通过 strategy_name='{strategy_name_from_worker}' 查找..."
                )

                # 精确匹配策略名称
                strategies_by_name = (
                    db.query(Strategy)
                    .filter(Strategy.name == strategy_name_from_worker)
                    .all()
                )

                if strategies_by_name:
                    # 找到一个或多个匹配的策略
                    strategy = strategies_by_name[0]  # 取第一个
                    strategy_found = True

                    # 更新 Worker 的 strategy_id（修复无效的 ID）
                    try:
                        worker.strategy_id = strategy.id
                        db.commit()
                        logger.info(
                            f"[策略加载] ✅ Layer 1.5: 通过名称找到策略，已更新 strategy_id "
                            f"{worker.strategy_id} → {strategy.id} (策略: {strategy.name})"
                        )
                    except Exception as e:
                        logger.warning(f"[策略加载] ⚠️ 更新 strategy_id 失败: {e}")

                    if strategy.code:
                        strategy_code = strategy.code
                        logger.info(
                            f"[策略加载] ✅ Layer 1.5: 使用数据库策略代码 "
                            f"(策略: {strategy.name}, ID: {strategy.id})"
                        )
                    elif strategy.file_name:
                        strategy_path = str(_strategies_dir / strategy.file_name)
                        logger.info(
                            f"[策略加载] ✅ Layer 1.5: 使用策略文件名 "
                            f"(策略: {strategy.name}, 文件: {strategy.file_name})"
                        )
                else:
                    # 尝试模糊匹配（包含关系）
                    all_strategies = db.query(Strategy).all()
                    matched_strategies = [
                        s for s in all_strategies
                        if strategy_name_from_worker.lower() in s.name.lower()
                           or s.name.lower() in strategy_name_from_worker.lower()
                    ]

                    if matched_strategies:
                        strategy = matched_strategies[0]
                        strategy_found = True

                        logger.info(
                            f"[策略加载] ✅ Layer 1.5: 模糊匹配找到策略 "
                            f"(搜索: '{strategy_name_from_worker}' → 匹配: '{strategy.name}', ID: {strategy.id})"
                        )

                        if strategy.code:
                            strategy_code = strategy.code
                        elif strategy.file_name:
                            strategy_path = str(_strategies_dir / strategy.file_name)
                            logger.info(f"[策略加载] 🔍 Layer 1.5: 拼接后的完整路径: {strategy_path}")
                            logger.info(f"[策略加载] 🔍 Layer 1.5: 文件是否存在: {Path(strategy_path).exists()}")
                    else:
                        from strategy.models import Strategy as StrategyModel
                        all_strategies = db.query(StrategyModel.name).all()
                        existing_names = [s[0] for s in all_strategies if s[0]]
                        logger.warning(
                            f"[策略加载] ⚠️ Layer 1.5: 数据库未找到 strategy_name='{strategy_name_from_worker}'"
                        )
                        logger.warning(
                            f"[策略加载] ⚠️ Layer 1.5: 数据库中现有策略名称 ({len(existing_names)}个): {', '.join(existing_names[:10])}{'...' if len(existing_names) > 10 else ''}"
                        )

            # ✅ 强制降级检查：如果数据库查找失败，立即降级到本地文件系统
            if not strategy_found and strategy_name_from_worker:
                logger.warning(
                    f"[策略加载] 🔄 数据库未找到策略，开始降级到本地文件系统..."
                )
                logger.info(
                    f"[策略加载] 🔍 降级搜索: strategy_name='{strategy_name_from_worker}'"
                )

            # Layer 2: 通过 strategy_file_name 参数查找
            if not strategy_found and strategy_file_name_from_config:
                file_name = strategy_file_name_from_config
                full_path = _strategies_dir / file_name  # 使用绝对路径

                if full_path.exists():
                    strategy_path = str(full_path)
                    strategy_found = True
                    logger.info(
                        f"[策略加载] ✅ Layer 2: 通过文件名找到策略文件: {full_path}"
                    )
                else:
                    logger.warning(f"[策略加载] ⚠️ Layer 2: 策略文件不存在: {full_path}")

            # Layer 2.5: 通过 strategy_name 模糊匹配文件系统（降级机制）
            if not strategy_found and strategy_name_from_worker:
                logger.warning(
                    f"[策略加载] 🔍 Layer 2.5: 尝试通过 strategy_name='{strategy_name_from_worker}' 匹配本地文件..."
                )

                # 获取所有可用的策略文件
                available_files = list(_strategies_dir.glob("*.py"))
                available_names = [f.stem for f in available_files if f.stem != "__init__"]

                logger.warning(
                    f"[策略加载] 📂 本地策略目录: {_strategies_dir.absolute()}"
                )
                logger.warning(
                    f"[策略加载] 📂 找到 {len(available_files)} 个策略文件: {', '.join(available_names[:10])}{'...' if len(available_names) > 10 else ''}"
                )

                # 精确匹配文件名
                exact_match = next(
                    (f for f in available_files if f.stem == strategy_name_from_worker), None
                )
                if exact_match:
                    strategy_path = str(exact_match)
                    strategy_found = True
                    logger.warning(
                        f"[策略加载] ✅ Layer 2.5: 精确匹配找到策略文件: {exact_match.name}"
                    )
                    logger.warning(
                        f"[策略加载] ✅ Layer 2.5: 完整路径: {exact_match.absolute()}"
                    )
                    # ✅ 降级成功：读取本地策略文件内容
                    try:
                        with open(exact_match, 'r', encoding='utf-8') as f:
                            strategy_code = f.read()
                            logger.warning(
                                f"[策略加载] ✅ Layer 2.5: 成功读取策略代码 ({len(strategy_code)} 字符)"
                            )
                    except Exception as read_error:
                        logger.warning(
                            f"[策略加载] ⚠️ Layer 2.5: 读取策略文件失败: {read_error}"
                        )
                else:
                    # 包含匹配（子串）
                    contains_matches = [
                        f for f in available_files
                        if strategy_name_from_worker.lower() in f.stem.lower()
                           or f.stem.lower() in strategy_name_from_worker.lower()
                    ]

                    if contains_matches:
                        best_match = contains_matches[0]
                        strategy_path = str(best_match)
                        strategy_found = True
                        logger.info(
                            f"[策略加载] ✅ Layer 2.5: 包含匹配找到策略文件: {best_match.name} "
                            f"(搜索: '{strategy_name_from_worker}')"
                        )
                    else:
                        # 相似度匹配（使用 SequenceMatcher）
                        similarity_scores = [
                            (f, SequenceMatcher(None, strategy_name_from_worker.lower(), f.stem.lower()).ratio())
                            for f in available_files
                        ]
                        similarity_scores.sort(key=lambda x: x[1], reverse=True)

                        if similarity_scores and similarity_scores[0][1] > 0.6:  # 相似度阈值 60%
                            best_match, score = similarity_scores[0]
                            strategy_path = str(best_match)
                            strategy_found = True
                            logger.info(
                                f"[策略加载] ✅ Layer 2.5: 相似度匹配找到策略文件: {best_match.name} "
                                f"(相似度: {score:.2%}, 搜索: '{strategy_name_from_worker}')"
                            )

            # Layer 3: 文件系统扫描兜底（增强版）
            if not strategy_found:
                logger.info(
                    "[策略加载] Layer 3: 所有精确匹配均失败，开始智能文件系统扫描..."
                )

                # 使用绝对路径进行文件系统扫描
                strategies_dir = _strategies_dir

                if strategies_dir.exists():
                    candidates = []

                    # 候选列表生成（基于多种信息源）
                    if worker.strategy_id:
                        candidates.append(("ID匹配", f"{worker.strategy_id}.py"))

                    if strategy_file_name_from_config:
                        candidates.append(("配置文件名", strategy_file_name_from_config))

                    if strategy_name_from_worker:
                        candidates.append(("策略名称", f"{strategy_name_from_worker}.py"))

                    candidates.append(("Worker名称", f"{worker.name.lower().replace(' ', '_')}.py"))

                    # 尝试精确匹配候选文件
                    for candidate_type, candidate_name in candidates:
                        candidate_path = strategies_dir / candidate_name
                        if candidate_path.exists():
                            strategy_path = str(candidate_path)
                            strategy_found = True
                            logger.info(
                                f"[策略加载] ✅ Layer 3: [{candidate_type}] 找到策略: {candidate_path}"
                            )
                            break

                    # 如果仍然没找到，使用模糊匹配
                    if not strategy_found:
                        available_files = list(strategies_dir.glob("*.py"))
                        available_names = [f.stem for f in available_files if f.stem != "__init__"]

                        # 构建搜索关键词
                        search_terms = []
                        if strategy_name_from_worker:
                            search_terms.append(strategy_name_from_worker)
                        if worker.strategy_id and isinstance(worker.strategy_id, int) and worker.strategy_id < 10000:
                            search_terms.append(str(worker.strategy_id))
                        search_terms.append(worker.name.lower().replace(' ', '_'))

                        # 对每个关键词尝试模糊匹配
                        for term in search_terms:
                            for avail_file in available_files:
                                stem = avail_file.stem.lower()
                                if term.lower() in stem or stem in term.lower():
                                    strategy_path = str(avail_file)
                                    strategy_found = True
                                    logger.info(
                                        f"[策略加载] ✅ Layer 3: 模糊匹配找到策略: {avail_file.name} "
                                        f"(关键词: '{term}')"
                                    )
                                    break
                            if strategy_found:
                                break

                    # 最终仍未找到
                    if not strategy_found:
                        available_names = [f.stem for f in list(strategies_dir.glob("*.py")) if f.stem != "__init__"]
                        logger.error(
                            f"[策略加载] ❌ 策略文件未找到！\n"
                            f"   - worker_id: {worker.id}\n"
                            f"   - worker_name: {worker.name}\n"
                            f"   - strategy_id: {worker.strategy_id}\n"
                            f"   - strategy_name: {strategy_name_from_worker}\n"
                            f"   - strategy_file_name: {strategy_file_name_from_config}\n"
                            f"   - 可用策略文件 ({len(available_names)}个): {available_names[:10]}{'...' if len(available_names) > 10 else ''}"
                        )
                else:
                    logger.error(f"[策略加载] ❌ 策略目录不存在: {strategies_dir.absolute()}")

        # 最终检查
        if not strategy_code and not strategy_path:
            logger.error(
                f"[策略加载] ❌ 策略加载最终失败！\n"
                f"   📁 策略目录: {_strategies_dir.absolute()}\n"
                f"   📁 目录存在: {_strategies_dir.exists()}\n"
                f"   🔍 worker_id: {worker.id}\n"
                f"   🔍 worker_name: {worker.name}\n"
                f"   🔍 strategy_id: {worker.strategy_id}\n"
                f"   🔍 strategy_name: {strategy_name_from_worker}\n"
                f"   🔍 strategy_file_name: {strategy_file_name_from_config}\n"
                f"   🔍 拼接后的预期路径: {_strategies_dir / (strategy_name_from_worker or 'unknown')}.py"
            )
            raise StrategyLoadError(
                worker.id,
                message=(
                    f"无法加载策略文件。"
                    f"strategy_id={worker.strategy_id}, "
                    f"strategy_name={strategy_name_from_worker}, "
                    f"请确认策略已正确配置或在数据库中存在。"
                ),
            )

        # 记录实际使用的策略路径
        if strategy_path:
            logger.info(f"Worker {worker.id} 使用策略路径: {strategy_path}")
        if strategy_code:
            logger.info(f"Worker {worker.id} 使用数据库策略代码")

        return (strategy_path, strategy_code, strategy_found)

    def _prepare_trading_config(
        self, worker: models.Worker, db: Session, strategy_code: Optional[str] = None
    ) -> dict:
        """
        准备交易配置（包含 Nautilus Trader 集成配置）

        Args:
            worker: Worker 模型实例
            db: 数据库会话
            strategy_code: 策略代码（可选）

        Returns:
            dict: 完整的交易配置字典

        包括：
        - 从 trading_config 解析基础配置
        - 确定市场类型和账户类型映射
        - 补充 API 密钥（优先 worker config，其次 SystemConfig）
        - 准备完整的 config 字典传递给 WorkerManager
        """
        trading_config = worker.get_trading_config_dict()
        symbols_config = trading_config.get("symbols_config", {})
        symbols = symbols_config.get("symbols", ["BTCUSDT"])

        # 确定交易模式和账户类型
        market_type = trading_config.get("market_type", "spot")
        account_type_map = {
            "spot": "spot",
            "usdt_futures": "usdt_futures",
            "coin_futures": "coin_futures",
            "futures": "usdt_futures",
        }
        account_type = account_type_map.get(market_type, "spot")

        # 交易模式映射
        trading_mode = trading_config.get(
            "trading_environment", trading_config.get("trading_mode", "live")
        )

        # 从 SystemConfig 补充交易所 API 密钥
        exchange_id = trading_config.get("exchange", "binance")

        # 根据环境类型确定 API 密钥字段名
        if trading_mode == "testnet":
            api_key_field = "testnet_api_key"
            api_secret_field = "testnet_api_secret"
        elif trading_mode == "paper":
            api_key_field = None
            api_secret_field = None
        else:
            api_key_field = "live_api_key"
            api_secret_field = "live_api_secret"

        exchange_api_key = trading_config.get("api_key")
        exchange_api_secret = trading_config.get("api_secret")
        exchange_api_passphrase = trading_config.get("api_passphrase")
        proxy_url = trading_config.get("proxy_url")

        if not exchange_api_key or not exchange_api_secret:
            from collector.db.models import SystemConfig as SystemConfigModel

            exchange_cfg_prefix = f"exchange.{exchange_id}."
            cfg_rows = (
                db.query(SystemConfigModel)
                .filter(SystemConfigModel.key.like(f"{exchange_cfg_prefix}%"))
                .all()
            )
            cfg_map = {}
            for row in cfg_rows:
                field = row.key[len(exchange_cfg_prefix) :]
                cfg_map[field] = row.value

            # 根据环境类型读取对应的 API 密钥
            if trading_mode == "testnet":
                if not exchange_api_key:
                    exchange_api_key = cfg_map.get("testnet_api_key")
                if not exchange_api_secret:
                    exchange_api_secret = cfg_map.get("testnet_api_secret")
            elif trading_mode != "paper":
                if not exchange_api_key:
                    exchange_api_key = cfg_map.get("live_api_key") or cfg_map.get(
                        "api_key"
                    )
                if not exchange_api_secret:
                    exchange_api_secret = cfg_map.get("live_api_secret") or cfg_map.get(
                        "api_secret"
                    )

            if not exchange_api_passphrase:
                exchange_api_passphrase = cfg_map.get("api_passphrase")
            if not proxy_url and cfg_map.get("proxy_enabled") in (True, "1", "true"):
                proxy_url = cfg_map.get("proxy_url")

            logger.info(
                f"Worker {worker.id} 从 SystemConfig 补充交易所密钥: "
                f"exchange={exchange_id}, "
                f"environment={trading_mode}, "
                f"api_key={'已配置' if exchange_api_key else '未配置'}, "
                f"api_secret={'已配置' if exchange_api_secret else '未配置'}"
            )

        # 准备完整的配置字典
        config = {
            "strategy_id": worker.strategy_id,
            "exchange": exchange_id,
            "symbol": symbols[0] if symbols else "BTCUSDT",
            "symbols": symbols,
            "timeframe": trading_config.get("timeframe", "1h"),
            "market_type": market_type,
            "worker_type": "nautilus",
            "trading": {
                "exchange": exchange_id,
                "account_type": account_type,
                "trading_mode": trading_mode,
                "api_key": exchange_api_key,
                "api_secret": exchange_api_secret,
                "api_passphrase": exchange_api_passphrase,
                "proxy_url": proxy_url,
                "log_level": "DEBUG",
            },
            "config": worker.get_config_dict(),
            "strategy_code": strategy_code,
            "params": trading_config.get("strategy_params", {}),
        }

        return config

    def start_worker(self, worker_id: int) -> dict:
        """
        启动 Worker（同步版本，供 CLI 使用）

        保持向后兼容的同步接口，委托给 WorkerSystem.sync_start_worker()

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str, "pid": int}

        Raises:
            WorkerNotFoundError: Worker 不存在
            WorkerAlreadyRunningError: Worker 已在运行
            StrategyLoadError: 策略加载失败
            ConfigPreparationError: 配置准备失败
            WorkerStartError: 启动失败
        """
        self._ensure_initialized()
        logger.info(f"[WorkerCoreService] [Facade] 委托启动Worker {worker_id} 到 WorkerSystem (sync)")
        try:
            result = self.system.sync_start_worker(worker_id)
            logger.info(f"[WorkerCoreService] [Facade] Worker {worker_id} 启动成功")
            return result
        except Exception as e:
            logger.error(f"[WorkerCoreService] [Facade] 同步启动 Worker {worker_id} 失败: {e}")
            raise

    async def _async_start_worker_sync(self, worker_id: int) -> dict:
        """内部使用的异步启动方法（供同步版本调用）"""
        return await self.async_start_worker(worker_id)

    async def async_start_worker(self, worker_id: int) -> dict:
        """
        异步版本启动 Worker - 状态驱动的非阻塞模式

        直接执行启动逻辑，不委托给 WorkerSystem（避免循环依赖）。

        调用链（修复后）：
        外部调用 → core_service.async_start_worker()
          → 状态转换: stopped → starting
          → 异步执行 _do_start_worker()  ✅ 无循环

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "starting", "message": str}
        """
        self._ensure_initialized()

        logger.info(f"[WorkerCoreService] 异步启动 Worker {worker_id}")

        try:
            from .worker_state import worker_state_manager

            # 1. 状态转换: 当前状态 → starting
            success = await worker_state_manager.transition(worker_id, "starting")
            if not success:
                state = await worker_state_manager.get_state(worker_id)
                current_status = state.status if state else "unknown"

                if current_status == "running":
                    return {
                        'worker_id': worker_id,
                        'status': 'running',
                        'message': 'Worker 已经处于运行状态',
                    }
                elif current_status == "starting":
                    return {
                        'worker_id': worker_id,
                        'status': 'starting',
                        'message': 'Worker 正在启动中...',
                    }
                else:
                    raise WorkerOperationError(
                        "启动", worker_id,
                        f"当前状态 ({current_status}) 不允许启动"
                    )

            # 2. 异步执行实际启动操作
            asyncio.create_task(self._do_start_worker(worker_id))

            # 3. 立即返回中间状态
            return {
                'worker_id': worker_id,
                'status': 'starting',
                'message': 'Worker 启动请求已接收，正在异步处理中...',
            }

        except Exception as e:
            logger.error(f"[WorkerCoreService] 异步启动 Worker {worker_id} 失败: {e}")
            raise

    async def _do_start_worker(self, worker_id: int):
        """
        执行 Worker 启动的后台异步任务

        包含完整的启动流程：读取配置、加载策略、启动进程、更新状态
        整体受健康检查超时保护（60秒 starting 超时 → 自动修正为 error）

        Args:
            worker_id: Worker ID
        """
        startup_start_time = time.time()
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    logger.error(f"[_do_start_worker] Worker {worker_id} 不存在")
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message=f"Worker {worker_id} 不存在"
                    )
                    return

                # 加载策略（三层回退机制）
                strategy_path, strategy_code, strategy_found = self._load_strategy(
                    worker, db
                )

                # 准备交易配置
                config = self._prepare_trading_config(
                    worker, db, strategy_code=strategy_code
                )

                logger.info(f"[_do_start_worker] Worker {worker_id} 配置准备完成，正在启动进程...")

                # 获取 Manager 并启动 Worker
                manager = self._get_manager()
                result_worker_id = await manager.start_trading_worker(
                    strategy_path=strategy_path,
                    config=config,
                    worker_id=str(worker_id),
                    exchange_config=config.get("trading"),
                )

                logger.info(
                    f"[_do_start_worker] Worker {worker_id} "
                    f"manager.start_trading_worker() 返回: {result_worker_id}"
                )

                if not result_worker_id:
                    # 启动失败，转换到 error 状态
                    logger.error(f"[_do_start_worker] Worker {worker_id} start_trading_worker 返回 None")
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message="Worker 启动失败（Nautilus Trader 初始化失败）"
                    )
                    return

                # 验证进程存活
                pid = manager.get_worker_pid(str(worker_id))
                is_alive = False

                if pid:
                    try:
                        os.kill(pid, 0)
                        is_alive = True
                        logger.info(f"[_do_start_worker] Worker {worker_id} 进程已启动 (PID: {pid})")
                    except (ProcessLookupError, OSError):
                        logger.warning(f"[_do_start_worker] Worker {worker_id} 进程已退出 (PID: {pid})")

                if not is_alive and pid:
                    logger.error(f"[_do_start_worker] Worker {worker_id} 启动后立即退出！PID: {pid} 已不存在")
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message="Worker 进程启动后立即退出（可能是策略加载失败或配置错误）"
                    )
                    return

                # 短暂等待日志系统初始化
                await asyncio.sleep(2)

                # 再次检查进程存活
                try:
                    os.kill(pid, 0)
                    process_still_alive = True
                except (ProcessLookupError, OSError):
                    process_still_alive = False

                if process_still_alive and is_alive:
                    # 启动成功，转换到 running 状态，记录 PID
                    startup_duration = time.time() - startup_start_time
                    await worker_state_manager.transition(
                        worker_id, "running", pid=pid
                    )
                    logger.info(
                        f"[_do_start_worker] ✅ Worker {worker_id} 启动成功，"
                        f"状态已更新为 running (PID: {pid}, 耗时: {startup_duration:.1f}s)"
                    )
                else:
                    # 进程在等待期间退出
                    logger.error(f"[_do_start_worker] Worker {worker_id} 在初始化期间退出")
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message="Worker 在初始化过程中退出"
                    )

        except StrategyLoadError as e:
            logger.error(f"[_do_start_worker] Worker {worker_id} 策略加载失败: {e}")
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )
        except ConfigPreparationError as e:
            logger.error(f"[_do_start_worker] Worker {worker_id} 配置准备失败: {e}")
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )
        except Exception as e:
            logger.error(f"[_do_start_worker] Worker {worker_id} 启动过程异常: {e}")
            import traceback
            traceback.print_exc()
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )

    def stop_worker(self, worker_id: int) -> dict:
        """
        停止 Worker（同步版本）

        保持向后兼容的同步接口，委托给 WorkerSystem.sync_stop_worker()

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str}

        Raises:
            WorkerNotFoundError: Worker 不存在
            WorkerOperationError: 停止失败
        """
        self._ensure_initialized()
        logger.info(f"[WorkerCoreService] [Facade] 委托停止Worker {worker_id} 到 WorkerSystem (sync)")
        try:
            result = self.system.sync_stop_worker(worker_id)
            logger.info(f"[WorkerCoreService] [Facade] Worker {worker_id} 停止成功")
            return result
        except Exception as e:
            logger.error(f"[WorkerCoreService] [Facade] 同步停止 Worker {worker_id} 失败: {e}")
            raise

    async def _async_stop_worker_sync(self, worker_id: int) -> dict:
        """内部使用的异步停止方法（供同步版本调用）"""
        return await self.async_stop_worker(worker_id)

    async def async_stop_worker(self, worker_id: int) -> dict:
        """
        异步版本停止 Worker - 状态驱动的非阻塞模式

        直接执行停止逻辑，不委托给 WorkerSystem（避免循环依赖）。

        调用链（修复后）：
        外部调用 → core_service.async_stop_worker()
          → 状态转换: running → stopping
          → 异步执行 _do_stop_worker()  ✅ 无循环

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "stopping", "message": str}
        """
        self._ensure_initialized()

        logger.info(f"[WorkerCoreService] 异步停止 Worker {worker_id}")

        try:
            from .worker_state import worker_state_manager

            # 1. 状态转换: 当前状态 → stopping
            success = await worker_state_manager.transition(worker_id, "stopping")
            if not success:
                state = await worker_state_manager.get_state(worker_id)
                current_status = state.status if state else "unknown"

                if current_status == "stopped":
                    return {
                        'worker_id': worker_id,
                        'status': 'stopped',
                        'message': 'Worker 已经处于停止状态',
                    }
                elif current_status == "stopping":
                    return {
                        'worker_id': worker_id,
                        'status': 'stopping',
                        'message': 'Worker 正在停止中...',
                    }
                else:
                    raise WorkerOperationError(
                        "停止", worker_id,
                        f"当前状态 ({current_status}) 不允许停止"
                    )

            # 2. 异步执行实际停止操作
            asyncio.create_task(self._do_stop_worker(worker_id))

            # 3. 立即返回中间状态
            return {
                'worker_id': worker_id,
                'status': 'stopping',
                'message': 'Worker 停止请求已接收，正在异步处理中...',
            }

        except Exception as e:
            logger.error(f"[WorkerCoreService] 异步停止 Worker {worker_id} 失败: {e}")
            raise

    async def _do_stop_worker(self, worker_id: int):
        """
        执行 Worker 停止的后台异步任务

        包含完整的停止流程：发送停止信号、等待退出、超时处理、强制终止

        Args:
            worker_id: Worker ID
        """
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    logger.error(f"[_do_stop_worker] Worker {worker_id} 不存在")
                    await worker_state_manager.transition(
                        worker_id, "stopped"
                    )
                    return

                pid = worker.pid
                stopped_successfully = False
                stop_method = "unknown"

                manager = self._get_manager()

                # 使用 SIGTERM 信号停止 Worker 进程
                if pid:
                    try:
                        os.kill(pid, 0)

                        os.kill(pid, 15)
                        stop_method = "sigterm"
                        logger.info(
                            f"[_do_stop_worker] 向 Worker {worker_id} (PID: {pid}) 发送 SIGTERM"
                        )

                        # 等待进程退出（最多 30 秒）
                        for i in range(60):
                            await asyncio.sleep(0.5)
                            try:
                                os.kill(pid, 0)
                                if i % 10 == 9:
                                    logger.debug(
                                        f"[_do_stop_worker] 等待 Worker {worker_id} "
                                        f"优雅退出... ({(i+1)*0.5:.1f}s)"
                                    )
                            except (ProcessLookupError, OSError):
                                stopped_successfully = True
                                logger.info(
                                    f"[_do_stop_worker] Worker {worker_id} 已优雅退出 "
                                    f"({(i+1)*0.5:.1f}s)"
                                )
                                break
                        else:
                            logger.warning(
                                f"[_do_stop_worker] Worker {worker_id} 未在 30s 内退出，"
                                f"将尝试强制终止"
                            )
                    except ProcessLookupError:
                        logger.info(f"[_do_stop_worker] Worker {worker_id} 进程已不存在")
                        stopped_successfully = True
                    except Exception as e:
                        logger.error(f"[_do_stop_worker] 发送 SIGTERM 失败: {e}")
                else:
                    logger.warning(f"[_do_stop_worker] Worker {worker_id} 没有 PID 信息")

                # 如果 SIGTERM 未成功，使用 SIGKILL 强制终止
                if not stopped_successfully and pid:
                    try:
                        os.kill(pid, 0)
                        logger.warning(
                            f"[_do_stop_worker] 强制终止 Worker {worker_id} (PID: {pid}) SIGKILL"
                        )
                        os.kill(pid, 9)
                        stop_method = "sigkill"

                        await asyncio.sleep(1)
                        try:
                            os.kill(pid, 0)
                        except (ProcessLookupError, OSError):
                            stopped_successfully = True
                            logger.warning(f"[_do_stop_worker] Worker {worker_id} 已被强制终止")
                    except (ProcessLookupError, OSError):
                        stopped_successfully = True
                        stop_method = "already_exited"

                # 更新最终状态
                if stopped_successfully or stop_method in ("already_exited", "sigkill"):
                    await worker_state_manager.transition(worker_id, "stopped")
                    logger.info(
                        f"[_do_stop_worker] ✅ Worker {worker_id} 已成功停止 (方式: {stop_method})"
                    )
                else:
                    # 异常情况：未能确认停止
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message=f"Worker 停止失败，最后尝试方式: {stop_method}"
                    )
                    logger.error(f"[_do_stop_worker] ❌ Worker {worker_id} 停止失败")

        except Exception as e:
            logger.error(f"[_do_stop_worker] Worker {worker_id} 停止过程异常: {e}")
            import traceback
            traceback.print_exc()
            try:
                await worker_state_manager.transition(
                    worker_id, "error", error_message=str(e)
                )
            except Exception as transition_err:
                logger.error(f"[_do_stop_worker] 状态转换失败: {transition_err}")

    def restart_worker(self, worker_id: int) -> dict:
        """
        重启 Worker（同步版本）

        原子化操作：先停止再启动，确保整体流程的一致性
        委托给 WorkerSystem.restart_worker()

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str}

        Raises:
            WorkerOperationError: 重启失败
        """
        self._ensure_initialized()
        logger.info(f"[WorkerCoreService] [Facade] 委托重启Worker {worker_id} 到 WorkerSystem")
        try:
            result = self.system.restart_worker(worker_id)
            logger.info(f"[WorkerCoreService] [Facade] Worker {worker_id} 重启成功")
            return result
        except Exception as e:
            logger.error(f"[WorkerCoreService] [Facade] 同步重启 Worker {worker_id} 失败: {e}")
            raise

    async def _async_restart_worker_sync(self, worker_id: int) -> dict:
        """内部使用的异步重启方法（供同步版本调用）"""
        return await self.async_restart_worker(worker_id)

    async def async_restart_worker(self, worker_id: int) -> dict:
        """
        异步版本重启 Worker - 原子化状态驱动模式

        委托给 WorkerSystem 的 restart_worker 方法（内部处理异步逻辑）

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str}
        """
        logger.info(f"[WorkerCoreService] [Facade] 委托异步重启Worker {worker_id} 到 WorkerSystem")
        try:
            # WorkerSystem.restart_worker 是同步方法，但内部会调用 sync_stop + sync_start
            # 为了保持异步接口的一致性，我们在线程池中执行
            import asyncio
            import concurrent.futures

            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    result = await loop.run_in_executor(
                        executor,
                        self.system.restart_worker,
                        worker_id
                    )
            else:
                result = self.system.restart_worker(worker_id)

            logger.info(f"[WorkerCoreService] [Facade] Worker {worker_id} 异步重启成功")
            return result
        except Exception as e:
            logger.error(f"[WorkerCoreService] [Facade] 异步重启 Worker {worker_id} 失败: {e}")
            raise

    def pause_worker(self, worker_id: int) -> dict:
        """
        暂停 Worker（同步版本）

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "paused"}
        """
        import asyncio

        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                manager = self._get_manager()

                async def _async_pause():
                    return await manager.pause_worker(str(worker_id))

                success = asyncio.run(_async_pause())

                if not success:
                    raise WorkerOperationError("暂停", worker_id, message="暂停 Worker 失败")

                # 更新状态
                worker.status = "paused"
                db.commit()
                logger.info(f"[pause_worker] Worker {worker_id} 已暂停")

                return {"worker_id": worker_id, "status": "paused"}

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[pause_worker] 暂停 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("暂停", worker_id, message=str(e))

    async def async_pause_worker(self, worker_id: int) -> dict:
        """异步版本暂停 Worker"""
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                manager = self._get_manager()
                success = await manager.pause_worker(str(worker_id))

                if not success:
                    raise WorkerOperationError("暂停", worker_id, message="暂停 Worker 失败")

                worker.status = "paused"
                db.commit()
                logger.info(f"[async_pause_worker] Worker {worker_id} 已暂停")

                return {"worker_id": worker_id, "status": "paused"}

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[async_pause_worker] 暂停 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("暂停", worker_id, message=str(e))

    def resume_worker(self, worker_id: int) -> dict:
        """
        恢复 Worker（同步版本）

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "running"}
        """
        import asyncio

        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                manager = self._get_manager()

                async def _async_resume():
                    return await manager.resume_worker(str(worker_id))

                success = asyncio.run(_async_resume())

                if not success:
                    raise WorkerOperationError("恢复", worker_id, message="恢复 Worker 失败")

                # 更新状态
                worker.status = "running"
                db.commit()
                logger.info(f"[resume_worker] Worker {worker_id} 已恢复")

                return {"worker_id": worker_id, "status": "running"}

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[resume_worker] 恢复 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("恢复", worker_id, message=str(e))

    async def async_resume_worker(self, worker_id: int) -> dict:
        """异步版本恢复 Worker"""
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                manager = self._get_manager()
                success = await manager.resume_worker(str(worker_id))

                if not success:
                    raise WorkerOperationError("恢复", worker_id, message="恢复 Worker 失败")

                worker.status = "running"
                db.commit()
                logger.info(f"[async_resume_worker] Worker {worker_id} 已恢复")

                return {"worker_id": worker_id, "status": "running"}

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[async_resume_worker] 恢复 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("恢复", worker_id, message=str(e))

    def get_worker_status(self, worker_id: int) -> dict:
        """
        获取 Worker 实时状态（通过 CommManager）

        包含自动状态转换：starting → running（当检测到 Worker 已完全初始化）

        Args:
            worker_id: Worker ID

        Returns:
            dict: Worker 状态信息
        """
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                manager = self._get_manager()

                # 尝试从 Manager 获取实时状态
                worker_status = manager.get_worker_status(str(worker_id))

                # 🔧 关键修复：自动状态转换 starting → running
                if worker.status == "starting":
                    worker_process = manager.get_worker(str(worker_id))
                    
                    if worker_process and worker_process.is_alive():
                        # 进程存活，检查是否应该升级为 running
                        pid = worker.pid
                        
                        if pid:
                            try:
                                os.kill(pid, 0)  # 验证进程存在
                                
                                # 检查运行时长和日志文件
                                import time
                                started_at = worker.started_at
                                if started_at:
                                    running_time = (datetime.utcnow() - started_at).total_seconds()
                                    
                                    # 如果运行超过 30 秒且进程存活，自动升级为 running
                                    if running_time > 30:
                                        logger.info(
                                            f"[get_worker_status] Worker {worker_id} 自动状态转换: "
                                            f"starting → running (运行 {running_time:.0f}s)"
                                        )
                                        worker.status = "running"
                                        db.commit()
                                        
                            except (ProcessLookupError, OSError):
                                # 进程已退出，保持 starting 或标记为 error
                                logger.warning(f"[get_worker_status] Worker {worker_id} 进程已退出 (PID: {pid})")
                                worker.status = "error"
                                worker.pid = None
                                db.commit()

                if worker_status:
                    return {
                        "worker_id": worker_id,
                        "db_status": worker.status,
                        "real_time_status": worker_status.to_dict(),
                        "is_alive": manager.get_worker(str(worker_id)).is_alive()
                        if manager.get_worker(str(worker_id))
                        else False,
                    }
                else:
                    # Manager 中没有该 Worker 的实时状态，返回数据库状态
                    return {
                        "worker_id": worker_id,
                        "db_status": worker.status,
                        "real_time_status": None,
                        "is_alive": False,
                        "message": "Worker 未在 Manager 中注册（可能未启动或已退出）",
                    }

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[get_worker_status] 获取 Worker {worker_id} 状态失败: {e}")
            return {
                "worker_id": worker_id,
                "db_status": "unknown",
                "real_time_status": None,
                "is_alive": False,
                "error": str(e),
            }

    async def async_get_worker_status(self, worker_id: int) -> dict:
        """异步版本获取 Worker 状态"""
        return self.get_worker_status(worker_id)

    def health_check(self, worker_id: int) -> dict:
        """
        健康检查

        Args:
            worker_id: Worker ID

        Returns:
            dict: 健康检查结果
        """
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                manager = self._get_manager()
                worker_process = manager.get_worker(str(worker_id))

                is_healthy = True
                checks = {
                    "db_record": True,
                    "process_exists": worker_process is not None,
                    "process_alive": worker_process.is_alive() if worker_process else False,
                }

                # 综合判断健康状态
                if not checks["process_exists"] or not checks["process_alive"]:
                    is_healthy = False

                return {
                    "worker_id": worker_id,
                    "status": worker.status,
                    "is_healthy": is_healthy,
                    "checks": checks,
                    "timestamp": datetime.now().isoformat(),
                }

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[health_check] Worker {worker_id} 健康检查失败: {e}")
            return {
                "worker_id": worker_id,
                "status": "unknown",
                "is_healthy": False,
                "checks": {},
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def async_health_check(self, worker_id: int) -> dict:
        """异步版本健康检查"""
        return self.health_check(worker_id)

    # ==================== 监控与日志管理方法 ====================

    def _get_log_file_reader(self, worker_id: str):
        """
        获取 LogFileReader 实例

        Args:
            worker_id: Worker ID（字符串格式）

        Returns:
            LogFileReader: 日志文件读取器实例
        """
        from .log_file_reader import get_log_file_manager

        log_mgr = get_log_file_manager()
        return log_mgr.get_reader(str(worker_id))

    def _run_subprocess(self, cmd: list) -> tuple:
        """
        运行子命令并返回结果

        Args:
            cmd: 命令列表，如 ["ps", "aux"]

        Returns:
            tuple: (stdout: str, stderr: str, returncode: int)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "命令执行超时", -1
        except Exception as e:
            return "", str(e), -1

    # ---------- 日志查询与清理 ----------

    def get_worker_logs(
        self,
        worker_id: int,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """
        查询 Worker 日志（基于文件系统 - 高性能方案）

        使用 LogFileReader 从日志文件读取，支持分页、筛选。

        Args:
            worker_id: Worker ID
            level: 日志级别筛选 (DEBUG/INFO/WARNING/ERROR)
            start_time: 开始时间 (ISO 8601 格式字符串)
            end_time: 结束时间 (ISO 8601 格式字符串)
            limit: 返回条数 (1-1000)
            offset: 偏移量（用于分页）

        Returns:
            dict: {
                "items": List[dict],  # 日志条目列表
                "total": int,         # 总数
                "limit": int,
                "offset": int
            }

        Raises:
            LogQueryError: 日志查询失败
            FileNotFoundError: 日志文件不存在
        """
        try:
            from datetime import datetime as dt

            start_dt = None
            end_dt = None

            if start_time:
                try:
                    start_dt = dt.fromisoformat(start_time.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"[get_worker_logs] 开始时间格式无效: {start_time}")

            if end_time:
                try:
                    end_dt = dt.fromisoformat(end_time.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"[get_worker_logs] 结束时间格式无效: {end_time}")

            reader = self._get_log_file_reader(str(worker_id))
            logs, total = reader.query_logs(
                worker_id=str(worker_id),
                start_time=start_dt,
                end_time=end_dt,
                level=level,
                limit=limit,
                offset=offset,
            )

            logger.info(f"[get_worker_logs] 查询 Worker {worker_id} 日志成功, 返回 {len(logs)} 条 (总计 {total} 条)")
            return {
                "items": logs,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        except FileNotFoundError:
            logger.error(f"[get_worker_logs] Worker {worker_id} 的日志文件不存在")
            raise
        except Exception as e:
            logger.error(f"[get_worker_logs] Worker {worker_id} 日志查询失败: {e}")
            raise LogQueryError(worker_id, message=str(e))

    async def async_get_worker_logs(
        self,
        worker_id: int,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """异步版本查询 Worker 日志"""
        return self.get_worker_logs(worker_id, level, start_time, end_time, limit, offset)

    def clear_worker_logs(
        self,
        worker_id: int,
        before_days: Optional[int] = None,
        confirm: bool = False
    ) -> dict:
        """
        清理 Worker 日志文件

        Args:
            worker_id: Worker ID
            before_days: 清理多少天前的日志，None 表示清理全部
            confirm: 安全确认参数

        Returns:
            dict: {"deleted_count": int}

        Raises:
            ValueError: 危险操作未确认
            LogQueryError: 日志清理失败
        """
        if before_days is None and not confirm:
            error_msg = "危险操作：清理全部日志需要 confirm=True 参数"
            logger.warning(f"[clear_worker_logs] Worker {worker_id}: {error_msg}")
            raise ValueError(error_msg)

        try:
            reader = self._get_log_file_reader(str(worker_id))
            deleted_count = reader.clear_logs(
                worker_id=str(worker_id),
                before_days=before_days,
            )

            logger.info(
                f"[clear_worker_logs] 用户清理了 Worker {worker_id} 的日志文件, "
                f"删除 {deleted_count} 个文件, before_days={before_days}"
            )
            return {"deleted_count": deleted_count}
        except Exception as e:
            logger.error(f"[clear_worker_logs] Worker {worker_id} 日志清理失败: {e}")
            raise LogQueryError(worker_id, message=f"日志清理失败: {str(e)}")

    async def async_clear_worker_logs(
        self,
        worker_id: int,
        before_days: Optional[int] = None,
        confirm: bool = False
    ) -> dict:
        """异步版本清理 Worker 日志"""
        return self.clear_worker_logs(worker_id, before_days, confirm)

    # ---------- 性能指标查询 ----------

    def get_worker_metrics(self, worker_id: int) -> dict:
        """
        获取 Worker 实时性能指标

        包括 CPU 使用率、内存占用、网络 I/O 等。

        Args:
            worker_id: Worker ID

        Returns:
            dict: 性能指标数据

        Raises:
            MetricsError: 获取性能指标失败
        """
        try:
            manager = self._get_manager()

            metrics_data = {
                "worker_id": worker_id,
                "timestamp": datetime.now().isoformat(),
                "cpu_usage": 0.0,
                "memory_usage_mb": 0.0,
                "memory_percent": 0.0,
                "network_io": {"bytes_sent": 0, "bytes_recv": 0},
                "disk_io": {"read_bytes": 0, "write_bytes": 0},
                "pid": None,
                "status": "unknown",
            }

            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                metrics_data["status"] = worker.status
                metrics_data["pid"] = worker.pid

                if worker.pid:
                    import psutil

                    try:
                        process = psutil.Process(worker.pid)

                        metrics_data["cpu_usage"] = process.cpu_percent(interval=0.1)
                        mem_info = process.memory_info()
                        metrics_data["memory_usage_mb"] = mem_info.rss / (1024 * 1024)
                        metrics_data["memory_percent"] = process.memory_percent()

                        io_counters = process.io_counters()
                        if io_counters:
                            metrics_data["disk_io"] = {
                                "read_bytes": getattr(io_counters, 'read_bytes', 0),
                                "write_bytes": getattr(io_counters, 'write_bytes', 0),
                            }

                        network_counters = psutil.net_io_counters()
                        if network_counters:
                            metrics_data["network_io"] = {
                                "bytes_sent": network_counters.bytes_sent,
                                "bytes_recv": network_counters.bytes_recv,
                            }
                    except psutil.NoSuchProcess:
                        logger.warning(f"[get_worker_metrics] Worker {worker_id} 进程不存在 (PID: {worker.pid})")
                        metrics_data["error"] = "进程不存在"
                    except ImportError:
                        logger.warning("[get_worker_metrics] psutil 未安装，使用模拟数据")

            logger.info(f"[get_worker_metrics] 获取 Worker {worker_id} 性能指标成功")
            return metrics_data

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[get_worker_metrics] Worker {worker_id} 获取性能指标失败: {e}")
            raise MetricsError(worker_id, message=str(e))

    async def async_get_worker_metrics(self, worker_id: int) -> dict:
        """异步版本获取 Worker 性能指标"""
        return self.get_worker_metrics(worker_id)

    def get_metrics_history(
        self,
        worker_id: int,
        start_time=None,
        end_time=None,
        interval="1m"
    ) -> list:
        """
        获取历史性能指标

        Args:
            worker_id: Worker ID
            start_time: 开始时间
            end_time: 结束时间
            interval: 时间间隔 (1m/5m/1h)

        Returns:
            list: 历史指标列表
        """
        try:
            from datetime import datetime as dt

            start_dt = None
            end_dt = None

            if start_time:
                if isinstance(start_time, str):
                    start_dt = dt.fromisoformat(start_time.replace("Z", "+00:00"))
                else:
                    start_dt = start_time

            if end_time:
                if isinstance(end_time, str):
                    end_dt = dt.fromisoformat(end_time.replace("Z", "+00:00"))
                else:
                    end_dt = end_time

            with self.get_db() as db:
                history = crud.get_metrics_history(
                    db, worker_id, start_dt, end_dt, interval
                )
                return history
        except Exception as e:
            logger.error(f"[get_metrics_history] Worker {worker_id} 获取历史指标失败: {e}")
            raise MetricsError(worker_id, message=str(e))

    async def async_get_metrics_history(
        self,
        worker_id: int,
        start_time=None,
        end_time=None,
        interval="1m"
    ) -> list:
        """异步版本获取历史性能指标"""
        return self.get_metrics_history(worker_id, start_time, end_time, interval)

    # ---------- 交易记录与订单查询 ----------

    def get_worker_trades(
        self,
        worker_id: int,
        symbol: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """
        获取 Worker 交易记录（SQLAlchemy 主库）

        数据来源：NautilusTrader OrderFilled 事件 → worker_trades 表

        Args:
            worker_id: Worker ID
            symbol: 交易对筛选
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            dict: {
                "items": List[dict],
                "total": int,
                "page": int,
                "page_size": int
            }

        Raises:
            WorkerOperationError: 查询失败
        """
        try:
            page_size = min(page_size, self._config["max_page_size"])
            skip = (page - 1) * page_size

            with self.get_db() as db:
                trades, total = crud.get_worker_trades(
                    db, worker_id, symbol=symbol,
                    skip=skip, limit=page_size
                )
                return {
                    "items": [t.to_dict() for t in trades],
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
        except Exception as e:
            logger.error(f"[get_worker_trades] Worker {worker_id} 获取交易记录失败: {e}")
            raise WorkerOperationError("获取交易记录", worker_id, message=str(e))

    async def async_get_worker_trades(
        self,
        worker_id: int,
        symbol: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """异步版本获取 Worker 交易记录"""
        return self.get_worker_trades(worker_id, symbol, page, page_size)

    def get_worker_orders(
        self,
        worker_id: int,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        获取 Worker 订单列表

        Args:
            worker_id: Worker ID
            status: 订单状态筛选
            limit: 返回数量限制

        Returns:
            dict: {"items": List[dict], "total": int}
        """
        try:
            with self.get_db() as db:
                query = db.query(models.WorkerOrder).filter(
                    models.WorkerOrder.worker_id == worker_id
                )

                if status:
                    query = query.filter(models.WorkerOrder.status == status)

                total = query.count()
                orders = query.order_by(
                    models.WorkerOrder.created_at.desc()
                ).limit(limit).all()

                return {
                    "items": [o.to_dict() for o in orders],
                    "total": total,
                }
        except Exception as e:
            logger.error(f"[get_worker_orders] Worker {worker_id} 获取订单列表失败: {e}")
            raise WorkerOperationError("获取订单", worker_id, message=str(e))

    async def async_get_worker_orders(
        self,
        worker_id: int,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """异步版本获取 Worker 订单列表"""
        return self.get_worker_orders(worker_id, status, limit)

    # ---------- 统计信息 ----------

    def get_worker_stats(self, worker_id: Optional[int] = None) -> dict:
        """
        获取 Worker 统计信息

        如果指定 worker_id：返回单个 Worker 的统计
        如果不指定：返回全局统计（运行中/已停止/错误数量）

        Args:
            worker_id: Worker ID（可选）

        Returns:
            dict: 统计信息
        """
        try:
            with self.get_db() as db:
                if worker_id:
                    worker = crud.get_worker(db, worker_id)
                    if not worker:
                        raise WorkerNotFoundError(worker_id)

                    trades_count = db.query(models.WorkerTrade).filter(
                        models.WorkerTrade.worker_id == worker_id
                    ).count()

                    orders_count = db.query(models.WorkerOrder).filter(
                        models.WorkerOrder.worker_id == worker_id
                    ).count()

                    return {
                        "worker_id": worker_id,
                        "name": worker.name,
                        "status": worker.status,
                        "trades_count": trades_count,
                        "orders_count": orders_count,
                        "created_at": worker.created_at.isoformat() if worker.created_at else None,
                        "started_at": worker.started_at.isoformat() if worker.started_at else None,
                    }
                else:
                    running = self.get_worker_count("running")
                    stopped = self.get_worker_count("stopped")
                    error = self.get_worker_count("error")
                    paused = self.get_worker_count("paused")
                    starting = self.get_worker_count("starting")

                    total_workers = db.query(models.Worker).count()

                    return {
                        "total_workers": total_workers,
                        "running": running,
                        "stopped": stopped,
                        "error": error,
                        "paused": paused,
                        "starting": starting,
                        "timestamp": datetime.now().isoformat(),
                    }
        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[get_worker_stats] 获取统计信息失败: {e}")
            raise WorkerOperationError("统计信息", message=str(e))

    async def async_get_worker_stats(self, worker_id: Optional[int] = None) -> dict:
        """异步版本获取 Worker 统计信息"""
        return self.get_worker_stats(worker_id)

    def get_worker_performance(self, worker_id: int, days: int = 30) -> list:
        """
        获取 Worker 绩效统计

        Args:
            worker_id: Worker ID
            days: 查询天数

        Returns:
            list: 绩效数据列表
        """
        try:
            with self.get_db() as db:
                performance = crud.get_worker_performance(db, worker_id, days)
                return [p.to_dict() for p in performance]
        except Exception as e:
            logger.error(f"[get_worker_performance] Worker {worker_id} 获取绩效统计失败: {e}")
            raise WorkerOperationError("绩效统计", worker_id, message=str(e))

    async def async_get_worker_performance(self, worker_id: int, days: int = 30) -> list:
        """异步版本获取 Worker 绩效统计"""
        return self.get_worker_performance(worker_id, days)

    # ---------- 诊断功能 ----------

    def diagnose_worker(self, worker_id: Optional[int] = None) -> dict:
        """
        诊断 Worker 系统状态

        分析 Worker 启动后状态未变化的可能原因。

        包括：
        - API 连接检查
        - 幽灵进程检测
        - Worker 基本信息
        - 生命周期状态
        - 性能指标
        - 日志检查
        - ZMQ 端口检测
        - 诊断总结和建议

        Args:
            worker_id: Worker ID（可选，不指定则进行系统级诊断）

        Returns:
            dict: 完整的诊断报告
        """
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "diagnosis_type": "system" if not worker_id else "worker",
            "checks": {},
            "issues": [],
            "recommendations": [],
            "summary": "",
        }

        try:
            # 1. API 连接检查
            diagnosis["checks"]["api_connection"] = self._check_api_connection()

            # 2. 幽灵进程检测
            ghost_processes = self._detect_ghost_processes()
            diagnosis["checks"]["ghost_processes"] = ghost_processes

            if worker_id:
                # Worker 级别诊断
                diagnosis["worker_id"] = worker_id

                # 3. Worker 基本信息
                basic_info = self._get_worker_basic_info(worker_id)
                diagnosis["checks"]["basic_info"] = basic_info

                if not basic_info.get("exists"):
                    diagnosis["issues"].append(f"Worker {worker_id} 不存在")
                    diagnosis["summary"] = f"Worker {worker_id} 不存在，无法继续诊断"
                    return diagnosis

                # 4. 生命周期状态
                lifecycle_status = self._diagnose_lifecycle(worker_id)
                diagnosis["checks"]["lifecycle"] = lifecycle_status

                # 5. 性能指标
                metrics_diagnosis = self._diagnose_metrics(worker_id)
                diagnosis["checks"]["metrics"] = metrics_diagnosis

                # 6. 日志检查
                logs_diagnosis = self._diagnose_logs(worker_id)
                diagnosis["checks"]["logs"] = logs_diagnosis

                # 生成诊断总结和建议
                self._generate_worker_diagnosis_summary(diagnosis, basic_info)
            else:
                # 系统级诊断
                stats = self.get_worker_stats()
                diagnosis["checks"]["system_stats"] = stats

                # ZMQ 端口检测
                zmq_ports = self._check_zmq_ports()
                diagnosis["checks"]["zmq_ports"] = zmq_ports

                # 生成系统级诊断总结
                self._generate_system_diagnosis_summary(diagnosis, stats)

            logger.info(f"[diagnose_worker] 诊断完成, 发现 {len(diagnosis['issues'])} 个问题")
            return diagnosis

        except Exception as e:
            logger.error(f"[diagnose_worker] 诊断失败: {e}")
            diagnosis["error"] = str(e)
            diagnosis["issues"].append(f"诊断过程出错: {str(e)}")
            return diagnosis

    async def async_diagnose_worker(self, worker_id: Optional[int] = None) -> dict:
        """异步版本诊断 Worker"""
        return self.diagnose_worker(worker_id)

    # ---------- 诊断辅助方法 ----------

    def _check_api_connection(self) -> dict:
        """检查 API 连接状态"""
        try:
            workers = self.list_workers(page=1, page_size=1)
            return {
                "status": "ok",
                "message": "API 连接正常",
                "can_query": True,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"API 连接失败: {str(e)}",
                "can_query": False,
            }

    def _detect_ghost_processes(self) -> dict:
        """检测幽灵 Worker 进程"""
        stdout, stderr, returncode = self._run_subprocess(["ps", "aux"])

        if returncode != 0:
            return {
                "status": "error",
                "message": f"无法执行 ps 命令: {stderr}",
                "ghost_processes": [],
                "orphaned_processes": [],
            }

        ghost_workers = []
        for line in stdout.split("\n"):
            if "quantcell-worker" in line and "grep" not in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = parts[1]
                    worker_id_from_process = None
                    for part in parts:
                        if part.startswith("quantcell-worker:"):
                            try:
                                worker_id_from_process = part.split(":")[1]
                            except (IndexError, ValueError):
                                pass
                            break

                    if worker_id_from_process:
                        ghost_workers.append({
                            "pid": pid,
                            "worker_id": worker_id_from_process,
                            "cmd": " ".join(parts[10:]) if len(parts) > 10 else "",
                        })

        if not ghost_workers:
            return {
                "status": "ok",
                "message": "没有发现 Worker 进程",
                "ghost_processes": [],
                "orphaned_processes": [],
            }

        try:
            with self.get_db() as db:
                all_workers = db.query(models.Worker).all()
                db_worker_ids = {str(w.id) for w in all_workers}
        except Exception:
            db_worker_ids = set()

        orphaned = []
        for ghost in ghost_workers:
            if ghost["worker_id"] not in db_worker_ids:
                orphaned.append(ghost)

        status = "warning" if orphaned else "ok"
        message = f"发现 {len(ghost_workers)} 个 Worker 进程"
        if orphaned:
            message += f"，其中 {len(orphaned)} 个是幽灵进程（数据库中不存在）"

        return {
            "status": status,
            "message": message,
            "ghost_processes": ghost_workers,
            "orphaned_processes": orphaned,
        }

    def _get_worker_basic_info(self, worker_id: int) -> dict:
        """获取 Worker 基本信息"""
        try:
            worker = self.get_worker(worker_id)
            return {
                "exists": True,
                "worker_id": worker_id,
                "name": worker.get("name"),
                "status": worker.get("status"),
                "pid": worker.get("pid"),
                "strategy_id": worker.get("strategy_id"),
            }
        except WorkerNotFoundError:
            return {
                "exists": False,
                "worker_id": worker_id,
            }
        except Exception as e:
            return {
                "exists": False,
                "worker_id": worker_id,
                "error": str(e),
            }

    def _diagnose_lifecycle(self, worker_id: int) -> dict:
        """诊断 Worker 生命周期状态"""
        try:
            status = self.get_worker_status(worker_id)

            is_healthy = status.get("is_healthy", False)
            real_time_status = status.get("real_time_status")
            is_alive = status.get("is_alive", False)

            issues = []

            if not is_healthy:
                issues.append("Worker 健康检查未通过")

            if not is_alive and status.get("db_status") == "running":
                issues.append("数据库显示运行中，但实际进程不存在")

            if real_time_status:
                last_heartbeat = real_time_status.get("last_heartbeat")
                if last_heartbeat:
                    try:
                        heartbeat_time = datetime.fromisoformat(last_heartbeat.replace("Z", "+00:00"))
                        time_since_heartbeat = datetime.now(timezone.utc) - heartbeat_time
                        if time_since_heartbeat.total_seconds() > 300:
                            issues.append(f"最后心跳时间超过 5 分钟 ({time_since_heartbeat})")
                    except (ValueError, TypeError):
                        pass
            else:
                issues.append("无法获取实时状态（CommManager 可能未初始化）")

            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "is_healthy": is_healthy,
                "is_alive": is_alive,
                "db_status": status.get("db_status"),
                "issues": issues,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"生命周期检查失败: {str(e)}",
                "is_healthy": False,
                "is_alive": False,
                "issues": [str(e)],
            }

    def _diagnose_metrics(self, worker_id: int) -> dict:
        """诊断 Worker 性能指标"""
        try:
            metrics = self.get_worker_metrics(worker_id)

            is_mock = metrics.get('timestamp') is None or metrics.get('cpu_usage') == 0.0

            issues = []
            if is_mock:
                issues.append("性能指标可能是模拟数据（CommManager ZeroMQ 可能未正确初始化）")

            if metrics.get("pid") and not metrics.get("error"):
                if metrics.get("memory_percent", 0) > 90:
                    issues.append(f"内存使用率过高: {metrics['memory_percent']:.1f}%")

                if metrics.get("cpu_usage", 0) > 95:
                    issues.append(f"CPU 使用率过高: {metrics['cpu_usage']:.1f}%")

            return {
                "status": "ok" if not issues else "warning",
                "is_mock_data": is_mock,
                "metrics_snapshot": {
                    k: v for k, v in metrics.items()
                    if k not in ["worker_id", "timestamp"]
                },
                "issues": issues,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"性能指标检查失败: {str(e)}",
                "is_mock_data": True,
                "issues": [str(e)],
            }

    def _diagnose_logs(self, worker_id: int) -> dict:
        """诊断 Worker 日志状态"""
        try:
            logs_result = self.get_worker_logs(worker_id, limit=5)
            logs = logs_result.get("items", [])
            total = logs_result.get("total", 0)

            has_logs = len(logs) > 0
            issues = []

            if not has_logs:
                issues.append("暂无日志输出（Worker 可能未真正运行或日志文件不存在）")
            else:
                recent_errors = sum(1 for log in logs if log.get("level") == "ERROR")
                if recent_errors > 0:
                    issues.append(f"最近 {len(logs)} 条日志中有 {recent_errors} 条错误")

            return {
                "status": "ok" if has_logs else "warning",
                "has_logs": has_logs,
                "total_logs": total,
                "recent_logs_count": len(logs),
                "issues": issues,
            }
        except FileNotFoundError:
            return {
                "status": "warning",
                "has_logs": False,
                "total_logs": 0,
                "recent_logs_count": 0,
                "issues": ["日志文件不存在"],
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"日志检查失败: {str(e)}",
                "has_logs": False,
                "total_logs": 0,
                "recent_logs_count": 0,
                "issues": [str(e)],
            }

    def _check_zmq_ports(self) -> dict:
        """检查 ZMQ 端口占用情况"""
        ports = [5555, 5556, 5557, 5558]
        port_status = {}
        occupied_by_others = []

        for port in ports:
            stdout, stderr, returncode = self._run_subprocess(["lsof", "-i", f":{port}"])

            if returncode == 0 and stdout.strip():
                lines = stdout.strip().split("\n")[1:]
                is_worker_port = any(
                    "quantcell-worker" in line or "Python" in line
                    for line in lines
                    if line
                )

                port_status[port] = {
                    "occupied": True,
                    "by_worker": is_worker_port,
                    "details": lines[0] if lines else "",
                }

                if not is_worker_port:
                    occupied_by_others.append(port)
            else:
                port_status[port] = {
                    "occupied": False,
                    "by_worker": False,
                    "details": "",
                }

        status = "ok" if not occupied_by_others else "warning"
        message = "ZMQ 端口正常" if not occupied_by_others else \
            f"发现 {len(occupied_by_others)} 个 ZMQ 端口被其他进程占用: {occupied_by_others}"

        return {
            "status": status,
            "message": message,
            "ports": port_status,
            "occupied_by_others": occupied_by_others,
        }

    def _generate_worker_diagnosis_summary(self, diagnosis: dict, basic_info: dict):
        """生成 Worker 级别诊断总结"""
        worker_id = diagnosis.get("worker_id")
        current_status = basic_info.get("status", "unknown")

        recommendations = []

        if current_status == 'stopped':
            diagnosis["summary"] = f"Worker {worker_id} 启动后状态仍为 stopped"
            recommendations.extend([
                "等待 10-30 秒后再次检查状态",
                "查看后端服务日志确认错误信息",
                "检查 ZeroMQ 端口是否被占用",
                "确认策略文件是否存在且可执行",
            ])
        elif current_status == 'running':
            lifecycle = diagnosis["checks"].get("lifecycle", {})
            if lifecycle.get("is_healthy"):
                diagnosis["summary"] = f"Worker {worker_id} 状态正常 (running)"
            else:
                diagnosis["summary"] = f"Worker {worker_id} 运行中但存在健康问题"
                recommendations.extend(lifecycle.get("issues", []))
        elif current_status == 'error':
            diagnosis["summary"] = f"Worker {worker_id} 处于错误状态"
            recommendations.append("查看后端服务日志了解具体错误原因")
        else:
            diagnosis["summary"] = f"Worker {worker_id} 当前状态: {current_status}"

        metrics_issues = diagnosis["checks"].get("metrics", {}).get("issues", [])
        if metrics_issues:
            recommendations.extend(metrics_issues)

        logs_issues = diagnosis["checks"].get("logs", {}).get("issues", [])
        if logs_issues:
            recommendations.extend(logs_issues)

        ghost_orphans = diagnosis["checks"].get("ghost_processes", {}).get("orphaned_processes", [])
        if ghost_orphans:
            recommendations.append("发现幽灵进程，建议使用 kill -9 终止")

        diagnosis["recommendations"] = recommendations

    # ==================== Daemon 管理方法 ====================

    def start_daemon(self) -> dict:
        """
        启动 WorkerManager 守护进程

        使用 fork 创建后台进程，运行 WorkerManager 事件循环。

        Returns:
            dict: {"pid": int, "status": "running"}
        """
        if self._is_daemon_running():
            pid = self._get_daemon_pid()
            raise WorkerOperationError("daemon", message=f"Daemon 已在运行 (PID: {pid})")

        pid = os.fork()

        if pid > 0:
            logger.info(f"Daemon 启动成功，PID: {pid}")
            self._save_daemon_pid(pid)
            return {"pid": pid, "status": "running"}

        os.setsid()

        pid = os.fork()
        if pid > 0:
            os._exit(0)

        sys.stdout.flush()
        sys.stderr.flush()

        log_dir = Path(self._config.get('log_dir', '/tmp'))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "worker_manager_daemon.log"

        with open(log_file, 'a') as log:
            os.dup2(log.fileno(), sys.stdout.fileno())
            os.dup2(log.fileno(), sys.stderr.fileno())

        asyncio.run(self._run_daemon_loop())

    def stop_daemon(self) -> dict:
        """
        停止 WorkerManager 守护进程

        Returns:
            dict: {"pid": int, "status": "stopped"}
        """
        pid = self._get_daemon_pid()
        if not pid:
            raise WorkerOperationError("daemon", message="Daemon 未在运行")

        logger.info(f"正在停止 Daemon (PID: {pid})...")
        os.kill(pid, signal.SIGTERM)

        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(1)
            except ProcessLookupError:
                break
        else:
            logger.warning(f"Daemon 强制终止 (PID: {pid})")
            os.kill(pid, signal.SIGKILL)

        self._cleanup_daemon_pid()
        return {"pid": pid, "status": "stopped"}

    def get_daemon_status(self) -> dict:
        """
        获取 Daemon 状态

        Returns:
            dict: {
                "running": bool,
                "pid": Optional[int],
                "uptime": Optional[str],
                "workers_count": int
            }
        """
        pid = self._get_daemon_pid()
        if not pid:
            return {"running": False, "pid": None, "uptime": None, "workers_count": 0}

        try:
            os.kill(pid, 0)

            try:
                import psutil
                process = psutil.Process(pid)
                create_time = datetime.fromtimestamp(process.create_time())
                uptime = datetime.now() - create_time
                uptime_str = str(uptime).split('.')[0]
            except (ImportError, Exception):
                uptime_str = "N/A"

            try:
                workers = self.list_workers()
                workers_count = len(workers.get('items', []))
            except Exception:
                workers_count = 0

            return {
                "running": True,
                "pid": pid,
                "uptime": uptime_str,
                "workers_count": workers_count,
            }
        except ProcessLookupError:
            self._cleanup_daemon_pid()
            return {"running": False, "pid": None, "uptime": None, "workers_count": 0}

    async def _run_daemon_loop(self):
        """Daemon 主事件循环"""
        logger.info("WorkerManager Daemon 启动")

        manager = self._get_manager()
        await manager.start()

        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(self._shutdown_handler(s))
            )

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await manager.stop()
            logger.info("WorkerManager Daemon 已停止")

    async def _shutdown_handler(self, sig):
        """信号处理器"""
        logger.info(f"收到信号 {sig.name}，正在关闭 Daemon...")
        self._cleanup_daemon_pid()
        loop = asyncio.get_event_loop()
        loop.stop()

    def _get_daemon_pid(self) -> Optional[int]:
        """读取 Daemon PID 文件"""
        pid_file = Path(tempfile.gettempdir()) / "quantcell_worker_daemon.pid"
        if pid_file.exists():
            try:
                with open(pid_file, 'r') as f:
                    return int(f.read().strip())
            except (ValueError, IOError):
                pass
        return None

    def _save_daemon_pid(self, pid: int):
        """保存 Daemon PID"""
        pid_file = Path(tempfile.gettempdir()) / "quantcell_worker_daemon.pid"
        with open(pid_file, 'w') as f:
            f.write(str(pid))

    def _cleanup_daemon_pid(self):
        """清理 Daemon PID 文件"""
        pid_file = Path(tempfile.gettempdir()) / "quantcell_worker_daemon.pid"
        pid_file.unlink(missing_ok=True)

    def _is_daemon_running(self) -> bool:
        """检查 Daemon 是否在运行"""
        pid = self._get_daemon_pid()
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            self._cleanup_daemon_pid()
            return False

    def _generate_system_diagnosis_summary(self, diagnosis: dict, stats: dict):
        """生成系统级诊断总结"""
        recommendations = []
        running = stats.get("running", 0)
        total = stats.get("total_workers", 0)

        if total == 0:
            diagnosis["summary"] = "系统中没有任何 Worker"
            recommendations.append("创建并启动一个 Worker")
        elif running == 0:
            diagnosis["summary"] = f"有 {total} 个 Worker 但都没有运行"
            recommendations.append("尝试启动 Worker")
        elif running > 0:
            diagnosis["summary"] = f"系统正常运行，{running}/{total} 个 Worker 在运行"

        zmq_ports = diagnosis["checks"].get("zmq_ports", {})
        if zmq_ports.get("occupied_by_others"):
            recommendations.append(
                f"ZMQ 端口 {zmq_ports['occupied_by_others']} 被其他进程占用，建议终止或更换端口配置"
            )

        ghost_orphans = diagnosis["checks"].get("ghost_processes", {}).get("orphaned_processes", [])
        if ghost_orphans:
            for ghost in ghost_orphans:
                recommendations.append(f"终止幽灵进程: kill -9 {ghost['pid']}")

        diagnosis["recommendations"] = recommendations


# 全局单例实例
worker_core_service = WorkerCoreService()
