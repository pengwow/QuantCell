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
        logger.info(f"[WorkerCoreService] 初始化完成，配置已加载")

    @classmethod
    def reset_instance(cls):
        """重置单例状态（用于测试）"""
        cls._instance = None

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
            with self.get_db() as db:
                worker_data = schemas.WorkerCreate(**data)
                worker = crud.create_worker(db, worker_data)
                result = worker.to_dict()
                logger.info(f"[WorkerCoreService] Worker创建成功: id={result['id']}, name={result['name']}")
                return result
        except Exception as e:
            logger.error(f"[WorkerCoreService] 创建Worker失败: {e}")
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
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundError(worker_id)
            return worker.to_dict()

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
        page_size = min(page_size, self._config["max_page_size"])
        skip = (page - 1) * page_size

        with self.get_db() as db:
            workers, total = crud.get_workers(
                db,
                status=status,
                strategy_id=strategy_id,
                skip=skip,
                limit=page_size,
            )
            return {
                "items": [w.to_dict() for w in workers],
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
        with self.get_db() as db:
            success = crud.delete_worker(db, worker_id)
            if not success:
                raise WorkerNotFoundError(worker_id)
            logger.info(f"[WorkerCoreService] Worker删除成功: id={worker_id}")
            return True

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
        批量操作Worker（同步版本）

        Args:
            worker_ids: Worker ID列表
            operation: 操作类型 (start/stop/restart)

        Returns:
            包含success、failed、total的字典
        """
        valid_operations = ["start", "stop", "restart"]
        if operation not in valid_operations:
            raise WorkerOperationError(
                operation,
                message=f"不支持的操作类型: {operation}，支持的操作: {valid_operations}",
            )

        success_list = []
        failed_dict = {}

        for wid in worker_ids:
            try:
                with self.get_db() as db:
                    worker = crud.get_worker(db, wid)
                    if not worker:
                        failed_dict[wid] = "Worker不存在"
                        continue

                    if operation == "start":
                        if worker.status == "running":
                            failed_dict[wid] = "Worker已在运行中"
                            continue
                        crud.update_worker_status(db, wid, "starting")
                    elif operation == "stop":
                        if worker.status == "stopped":
                            failed_dict[wid] = "Worker已停止"
                            continue
                        crud.update_worker_status(db, wid, "stopped")
                    elif operation == "restart":
                        crud.update_worker_status(db, wid, "stopped")

                    success_list.append(wid)
                    logger.info(f"[WorkerCoreService] 批量{operation}成功: worker_id={wid}")
            except Exception as e:
                failed_dict[wid] = str(e)
                logger.error(f"[WorkerCoreService] 批量{operation}失败: worker_id={wid}, error={e}")

        result = {
            "success": success_list,
            "failed": failed_dict,
            "total": len(worker_ids),
        }
        logger.info(
            f"[WorkerCoreService] 批量{operation}完成: "
            f"成功={len(success_list)}, 失败={len(failed_dict)}, 总计={len(worker_ids)}"
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
        加载策略代码或路径（三层回退机制）

        Args:
            worker: Worker 模型实例
            db: 数据库会话

        Returns:
            tuple: (strategy_path: Optional[str], strategy_code: Optional[str], strategy_found: bool)

        Layer 1: 从数据库 strategy 表查询（最优先）
        Layer 2: 通过 strategy_file_name 参数查找文件
        Layer 3: 文件系统扫描兜底
        """
        import json as json_lib
        from pathlib import Path

        # 确定策略目录的绝对路径（基于 core_service.py 文件位置）
        # core_service.py 在 backend/worker/ 目录下
        # 策略目录在 backend/strategies/ 目录下
        _backend_dir = Path(__file__).parent.parent.resolve()
        _strategies_dir = _backend_dir / "strategies"

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

        if worker.strategy_id or strategy_file_name_from_config:
            # Layer 1: 从数据库查询（最优先）
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
                            f"[策略加载] 使用数据库策略代码 "
                            f"(策略: {strategy.name}, ID: {strategy.id})"
                        )
                    elif strategy.file_name:
                        # 使用绝对路径
                        strategy_path = str(_strategies_dir / strategy.file_name)
                        logger.info(
                            f"[策略加载] 使用策略文件名 "
                            f"(策略: {strategy.name}, 文件: {strategy.file_name})"
                        )
                    else:
                        logger.warning(
                            f"[策略加载] 数据库策略缺少 code 和 file_name "
                            f"(ID: {strategy.id})"
                        )

            # Layer 2: 通过 strategy_file_name 参数查找
            if not strategy_found and strategy_file_name_from_config:
                file_name = strategy_file_name_from_config
                full_path = _strategies_dir / file_name  # 使用绝对路径

                if full_path.exists():
                    strategy_path = str(full_path)
                    strategy_found = True
                    logger.info(
                        f"[策略加载] 通过文件名找到策略文件: {full_path}"
                    )
                else:
                    logger.warning(f"[策略加载] 策略文件不存在: {full_path}")

            # Layer 3: 文件系统扫描（兜底）
            if not strategy_found:
                logger.info(
                    "[策略加载] 数据库和精确文件名均未找到，开始文件系统扫描..."
                )

                # 使用绝对路径进行文件系统扫描
                strategies_dir = _strategies_dir

                if strategies_dir.exists():
                    candidates = []

                    if worker.strategy_id:
                        candidates.append(f"{worker.strategy_id}.py")

                    if strategy_file_name_from_config:
                        candidates.append(strategy_file_name_from_config)

                    candidates.append(
                        f"{worker.name.lower().replace(' ', '_')}.py"
                    )

                    for candidate in candidates:
                        candidate_path = strategies_dir / candidate
                        if candidate_path.exists():
                            strategy_path = str(candidate_path)
                            strategy_found = True
                            logger.info(
                                f"[策略加载] 文件系统扫描找到策略: {candidate_path}"
                            )
                            break

                    if not strategy_found:
                        available_files = list(strategies_dir.glob("*.py"))
                        available_names = [
                            f.stem
                            for f in available_files
                            if f.stem != "__init__"
                        ]
                        logger.error(
                            f"[策略加载] 策略文件未找到！\n"
                            f"   - strategy_id: {worker.strategy_id}\n"
                            f"   - strategy_file_name: {strategy_file_name_from_config}\n"
                            f"   - 可用策略文件: {available_names}"
                        )
                else:
                    logger.error(
                        f"[策略加载] 策略目录不存在: {strategies_dir.absolute()}"
                    )

        # 最终检查
        if not strategy_code and not strategy_path:
            raise StrategyLoadError(
                worker.id,
                message=(
                    f"无法加载策略文件。"
                    f"strategy_id={worker.strategy_id}, "
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

        流程：
        1. 获取 Worker 记录
        2. 检查状态（如果 running 则返回提示）
        3. 加载策略（调用 _load_strategy）
        4. 准备配置（调用 _prepare_trading_config）
        5. 更新状态为 starting
        6. 调用 WorkerManager.start_trading_worker()
        7. 更新状态为 running，记录 PID
        8. 返回成功结果

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "running", "pid": int}

        Raises:
            WorkerNotFoundError: Worker 不存在
            WorkerAlreadyRunningError: Worker 已在运行
            StrategyLoadError: 策略加载失败
            ConfigPreparationError: 配置准备失败
            WorkerStartError: 启动失败
        """
        import asyncio

        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                # 检查 Worker 是否已在运行
                if worker.status == "running":
                    raise WorkerAlreadyRunningError(worker_id)

                # 加载策略（三层回退机制）
                strategy_path, strategy_code, strategy_found = self._load_strategy(
                    worker, db
                )

                # 准备交易配置
                config = self._prepare_trading_config(
                    worker, db, strategy_code=strategy_code
                )

                # 更新状态为 starting
                logger.info(
                    f"[start_worker] Worker {worker_id} 状态变更: "
                    f"{worker.status} -> starting"
                )
                worker.status = "starting"
                worker.started_at = datetime.now()
                db.commit()

                # 获取 Manager 并启动 Worker（异步调用需要在同步上下文中包装）
                manager = self._get_manager()

                async def _async_start():
                    return await manager.start_trading_worker(
                        strategy_path=strategy_path,
                        config=config,
                        worker_id=str(worker_id),
                        exchange_config=config.get("trading"),
                    )

                result_worker_id = asyncio.run(_async_start())
                logger.info(
                    f"[start_worker] Worker {worker_id} "
                    f"manager.start_trading_worker() 返回: {result_worker_id}"
                )

                if not result_worker_id:
                    # 启动失败，更新状态为 error
                    logger.error(
                        f"[start_worker] Worker {worker_id} start_trading_worker 返回 None"
                    )
                    worker.status = "error"
                    worker.pid = None
                    db.commit()
                    raise WorkerStartError(
                        worker_id,
                        message="Worker 启动失败（Nautilus Trader 初始化失败）",
                    )

                # Worker 启动成功，更新状态为 running
                logger.info(
                    f"[start_worker] Worker {worker_id} 启动成功，更新状态为 running"
                )
                worker.status = "running"
                worker.pid = manager.get_worker_pid(str(worker_id))
                db.commit()
                logger.info(
                    f"[start_worker] Worker {worker_id} 已更新为 running 状态，"
                    f"pid={worker.pid}"
                )

                return {
                    "worker_id": worker_id,
                    "status": "running",
                    "pid": worker.pid,
                }

        except (WorkerNotFoundError, WorkerAlreadyRunningError, StrategyLoadError, ConfigPreparationError, WorkerStartError):
            raise
        except Exception as e:
            logger.error(f"[start_worker] 启动 Worker {worker_id} 失败: {e}")
            raise WorkerStartError(worker_id, message=f"启动 Worker 失败: {str(e)}")

    async def async_start_worker(self, worker_id: int) -> dict:
        """
        异步版本启动 Worker（供 API 使用）

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "running", "pid": int}
        """
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                # 检查 Worker 是否已在运行
                if worker.status == "running":
                    raise WorkerAlreadyRunningError(worker_id)

                # 加载策略（三层回退机制）
                strategy_path, strategy_code, strategy_found = self._load_strategy(
                    worker, db
                )

                # 准备交易配置
                config = self._prepare_trading_config(
                    worker, db, strategy_code=strategy_code
                )

                # 更新状态为 starting
                logger.info(
                    f"[async_start_worker] Worker {worker_id} 状态变更: "
                    f"{worker.status} -> starting"
                )
                worker.status = "starting"
                worker.started_at = datetime.now()
                db.commit()

                # 获取 Manager 并启动 Worker
                manager = self._get_manager()
                result_worker_id = await manager.start_trading_worker(
                    strategy_path=strategy_path,
                    config=config,
                    worker_id=str(worker_id),
                    exchange_config=config.get("trading"),
                )
                logger.info(
                    f"[async_start_worker] Worker {worker_id} "
                    f"manager.start_trading_worker() 返回: {result_worker_id}"
                )

                if not result_worker_id:
                    logger.error(
                        f"[async_start_worker] Worker {worker_id} start_trading_worker 返回 None"
                    )
                    worker.status = "error"
                    worker.pid = None
                    db.commit()
                    raise WorkerStartError(
                        worker_id,
                        message="Worker 启动失败（Nautilus Trader 初始化失败）",
                    )

                # Worker 启动成功
                logger.info(
                    f"[async_start_worker] Worker {worker_id} 启动成功，更新状态为 running"
                )
                worker.status = "running"
                worker.pid = manager.get_worker_pid(str(worker_id))
                db.commit()
                logger.info(
                    f"[async_start_worker] Worker {worker_id} 已更新为 running 状态，"
                    f"pid={worker.pid}"
                )

                return {
                    "worker_id": worker_id,
                    "status": "running",
                    "pid": worker.pid,
                }

        except (WorkerNotFoundError, WorkerAlreadyRunningError, StrategyLoadError, ConfigPreparationError, WorkerStartError):
            raise
        except Exception as e:
            logger.error(f"[async_start_worker] 启动 Worker {worker_id} 失败: {e}")
            raise WorkerStartError(worker_id, message=f"启动 Worker 失败: {str(e)}")

    def stop_worker(self, worker_id: int) -> dict:
        """
        停止 Worker（同步版本）

        流程：
        1. 检查 Worker 是否存在
        2. 检查状态（如果 stopped 则返回提示）
        3. 调用 WorkerManager.stop_worker()
        4. 更新状态为 stopped，清空 PID
        5. 返回成功结果

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "stopped"}

        Raises:
            WorkerNotFoundError: Worker 不存在
            WorkerOperationError: 停止失败
        """
        import asyncio

        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                # 检查状态
                if worker.status == "stopped":
                    return {"worker_id": worker_id, "status": "stopped", "message": "Worker 已停止"}

                # 获取 Manager 并停止 Worker
                manager = self._get_manager()

                async def _async_stop():
                    return await manager.stop_worker(str(worker_id))

                success = asyncio.run(_async_stop())

                if not success:
                    raise WorkerOperationError("停止", worker_id, message="停止 Worker 失败")

                # 更新状态
                worker.status = "stopped"
                worker.pid = None
                db.commit()
                logger.info(f"[stop_worker] Worker {worker_id} 已停止")

                return {"worker_id": worker_id, "status": "stopped"}

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[stop_worker] 停止 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("停止", worker_id, message=str(e))

    async def async_stop_worker(self, worker_id: int) -> dict:
        """异步版本停止 Worker"""
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundError(worker_id)

                if worker.status == "stopped":
                    return {"worker_id": worker_id, "status": "stopped", "message": "Worker 已停止"}

                manager = self._get_manager()
                success = await manager.stop_worker(str(worker_id))

                if not success:
                    raise WorkerOperationError("停止", worker_id, message="停止 Worker 失败")

                worker.status = "stopped"
                worker.pid = None
                db.commit()
                logger.info(f"[async_stop_worker] Worker {worker_id} 已停止")

                return {"worker_id": worker_id, "status": "stopped"}

        except WorkerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[async_stop_worker] 停止 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("停止", worker_id, message=str(e))

    def restart_worker(self, worker_id: int) -> dict:
        """
        重启 Worker（同步版本）

        先停止再启动

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": "running", "pid": int}
        """
        try:
            # 先停止
            self.stop_worker(worker_id)
            # 再启动
            return self.start_worker(worker_id)
        except Exception as e:
            logger.error(f"[restart_worker] 重启 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("重启", worker_id, message=str(e))

    async def async_restart_worker(self, worker_id: int) -> dict:
        """异步版本重启 Worker"""
        try:
            await self.async_stop_worker(worker_id)
            return await self.async_start_worker(worker_id)
        except Exception as e:
            logger.error(f"[async_restart_worker] 重启 Worker {worker_id} 失败: {e}")
            raise WorkerOperationError("重启", worker_id, message=str(e))

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
