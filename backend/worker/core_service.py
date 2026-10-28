"""
Worker核心服务层

提供Worker管理的基础CRUD操作框架，支持同步和异步双模式：
- 同步模式：供CLI命令行工具使用
- 异步模式：供FastAPI接口使用

基于 state.py 单例枢纽的 trading_system + strategy_registry 进行策略管理，
不再使用 multiprocessing 进程隔离和 ZMQ IPC 通信。

独立于FastAPI，可直接导入使用
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

from . import crud, models, schemas
from .exceptions import (
    LogQueryException,
    MetricsException,
    WorkerAlreadyRunningException,
    WorkerException,
    WorkerNotFoundException,
    WorkerOperationException,
)
from .state import strategy_registry
from .worker_state import worker_state_manager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from sqlalchemy.orm import Session

logger = get_logger(__name__, LogType.APPLICATION)


# 异常类统一在 exceptions.py 中定义并直接使用，不再保留向后兼容别名


__all__ = [
    "LogQueryException",
    "MetricsException",
    "WorkerAlreadyRunningException",
    "WorkerCoreService",
    "WorkerException",
    "WorkerNotFoundException",
    "WorkerOperationException",
    "worker_core_service",
]


class WorkerCoreService:
    """
    Worker核心服务类（单例模式）

    提供Worker的基础CRUD操作，支持同步和异步两种调用模式：
    - 同步方法：以 create_worker、get_worker 等命名，适合CLI使用
    - 异步方法：以 async_create_worker、async_get_worker 等命名，适合API使用

    策略启停通过 state.py 单例枢纽的 trading_system 执行，
    运行时状态通过 strategy_registry 查询。
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

        self._register_state_event_handlers()
        logger.info("[WorkerCoreService] 初始化完成（单例枢纽模式），trading_system 已集成")

    @classmethod
    def reset_instance(cls):
        """重置单例状态（用于测试）"""
        cls._instance = None

    def _load_config(self) -> dict[str, Any]:
        """从环境变量和默认配置文件加载配置"""
        config = {
            "db_path": os.environ.get("DB_FILE", "data/quantcell_sqlite.db"),
            "db_type": os.environ.get("DB_TYPE", "sqlite"),
            "log_dir": os.environ.get("LOG_DIR", "logs"),
            "default_page_size": int(os.environ.get("DEFAULT_PAGE_SIZE", "20")),
            "max_page_size": int(os.environ.get("MAX_PAGE_SIZE", "100")),
        }

        default_config_file = os.path.join(os.path.dirname(__file__), "..", "config", "worker_default.json")
        if os.path.exists(default_config_file):
            try:
                with open(default_config_file, encoding="utf-8") as f:
                    file_config = json.load(f)
                    config.update(file_config)
                    logger.debug(f"[WorkerCoreService] 从配置文件加载配置: {default_config_file}")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"[WorkerCoreService] 配置文件读取失败: {e}")

        return config

    @contextmanager
    def get_db(self) -> Generator[Session]:
        """
        获取同步数据库会话（上下文管理器）

        用于CLI等同步场景，确保会话正确关闭

        Yields:
            Session: SQLAlchemy数据库会话
        """
        with get_db_session() as db:
            yield db

    @asynccontextmanager
    async def async_get_db(self) -> AsyncGenerator[Session]:
        """
        获取异步数据库会话（上下文管理器）

        用于API等异步场景，确保会话正确关闭

        Yields:
            Session: SQLAlchemy数据库会话
        """
        with get_db_session() as db:
            yield db

    # ==================== 同步CRUD方法（供CLI使用） ====================

    def _validate_and_fill_strategy(self, db: Session, worker_data: Any, op_name: str) -> None:
        """落库前校验 Worker 关联的策略有效性，并回填冗余的 id/name。

        daemon 按 strategy_name 加载策略，strategy_id 失效且 strategy_name
        为空的 Worker 会拖到启动阶段才失败。统一在创建/更新入口拦截：
        显式传入的策略引用（id 或名称）查不到时直接拒绝；查到则回填
        真实 id/name，防止后续按失效引用加载。
        部分更新（WorkerUpdate）仅在本次显式涉及策略字段时才校验。
        """
        fields_set = getattr(worker_data, "model_fields_set", None)
        if fields_set is not None and not ({"strategy_id", "strategy_name"} & fields_set):
            return
        if worker_data.strategy_id is None and not worker_data.strategy_name:
            return  # 未关联策略的 Worker 允许存在（用户可稍后编辑补选）
        strategy = crud.find_strategy_by_name_or_id(
            db, strategy_id=worker_data.strategy_id, strategy_name=worker_data.strategy_name
        )
        if strategy is None:
            raise WorkerOperationException(
                op_name,
                message=(
                    f"关联策略不存在（strategy_id={worker_data.strategy_id}, "
                    f"strategy_name={worker_data.strategy_name}），请先在策略库选择有效策略"
                ),
            )
        worker_data.strategy_id = strategy["id"]
        worker_data.strategy_name = strategy["name"]

    def create_worker(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        创建Worker（同步版本）

        Args:
            data: Worker创建数据字典，应符合schemas.WorkerCreate格式

        Returns:
            创建成功的Worker字典

        Raises:
            WorkerOperationException: 创建失败时抛出
        """
        try:
            with self.get_db() as db:
                # crud 层按 WorkerCreate schema 落库；这里把 dict 边界数据转成 schema，
                # 与 update_worker 的 schemas.WorkerUpdate(**data) 保持一致，并让 extra="forbid" 生效
                create_data = schemas.WorkerCreate(**data)
                self._validate_and_fill_strategy(db, create_data, "创建")
                worker = crud.create_worker(db, create_data)
                result = worker.to_dict()
                logger.info(f"[WorkerCoreService] Worker创建成功: id={worker.id}, name={result.get('name')}")
                return result
        except Exception as e:
            logger.error(f"[WorkerCoreService] 创建Worker失败: {e}")
            msg = "create"
            raise WorkerOperationException(msg, message=str(e))

    def get_worker(self, worker_id: int) -> dict[str, Any]:
        """
        获取Worker详情（同步版本）

        Args:
            worker_id: Worker ID

        Returns:
            Worker详情字典

        Raises:
            WorkerNotFoundException: Worker不存在时抛出
        """
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundException(worker_id)
            logger.debug(f"[WorkerCoreService] Worker {worker_id} 获取成功")
            return worker.to_dict()

    def list_workers(
        self,
        status: str | None = None,
        strategy_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
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
        with self.get_db() as db:
            skip = (page - 1) * page_size
            workers, total = crud.get_workers(
                db,
                skip=skip,
                limit=page_size,
                status=status,
                strategy_id=strategy_id,
            )
            logger.debug(f"[WorkerCoreService] 获取到 {total} 个Worker，返回第 {page} 页")
            return {
                "items": [w.to_dict() for w in workers],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def update_worker(self, worker_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        更新Worker（同步版本）

        Args:
            worker_id: Worker ID
            data: 更新数据字典，应符合schemas.WorkerUpdate格式

        Returns:
            更新后的Worker字典

        Raises:
            WorkerNotFoundException: Worker不存在时抛出
            WorkerOperationException: 更新失败时抛出
        """
        try:
            with self.get_db() as db:
                worker_data = schemas.WorkerUpdate(**data)
                self._validate_and_fill_strategy(db, worker_data, "更新")
                worker = crud.update_worker(db, worker_id, worker_data)
                if not worker:
                    raise WorkerNotFoundException(worker_id)
                result = worker.to_dict()
                logger.info(f"[WorkerCoreService] Worker更新成功: id={worker_id}")
                return result
        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[WorkerCoreService] 更新Worker失败: worker_id={worker_id}, error={e}")
            msg = "update"
            raise WorkerOperationException(msg, worker_id, message=str(e))

    def delete_worker(self, worker_id: int) -> bool:
        """
        删除Worker（同步版本）

        Args:
            worker_id: Worker ID

        Returns:
            是否删除成功

        Raises:
            WorkerNotFoundException: Worker不存在时抛出
        """
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundException(worker_id)
            crud.delete_worker(db, worker_id)
            logger.info(f"[WorkerCoreService] Worker {worker_id} 删除成功")
            return True

    def clone_worker(
        self,
        worker_id: int,
        new_name: str,
        copy_config: bool = True,
        copy_parameters: bool = True,
    ) -> dict[str, Any]:
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
            WorkerNotFoundException: 源Worker不存在时抛出
            WorkerOperationException: 克隆失败时抛出
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
                    f"[WorkerCoreService] Worker克隆成功: 源ID={worker_id}, 新ID={result['id']}, 名称={new_name}"
                )
                return result
        except ValueError as e:
            if "不存在" in str(e):
                raise WorkerNotFoundException(worker_id)
            msg = "clone"
            raise WorkerOperationException(msg, worker_id, message=str(e))
        except Exception as e:
            logger.error(f"[WorkerCoreService] 克隆Worker失败: worker_id={worker_id}, error={e}")
            msg = "clone"
            raise WorkerOperationException(msg, worker_id, message=str(e))

    # ==================== 异步CRUD方法（供API使用） ====================

    async def async_create_worker(self, data: dict[str, Any]) -> dict[str, Any]:
        """创建Worker（异步版本，通过线程池执行同步DB操作）"""
        return await asyncio.to_thread(self.create_worker, data)

    async def async_get_worker(self, worker_id: int) -> dict[str, Any]:
        """获取Worker详情（异步版本，通过线程池执行同步DB操作）"""
        return await asyncio.to_thread(self.get_worker, worker_id)

    async def async_list_workers(
        self,
        status: str | None = None,
        strategy_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """获取Worker列表（异步版本，通过线程池执行同步DB操作）"""
        return await asyncio.to_thread(self.list_workers, status, strategy_id, page, page_size)

    async def async_update_worker(self, worker_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """更新Worker（异步版本，通过线程池执行同步DB操作）"""
        return await asyncio.to_thread(self.update_worker, worker_id, data)

    async def async_delete_worker(self, worker_id: int) -> bool:
        """删除Worker（异步版本，通过线程池执行同步DB操作）"""
        return await asyncio.to_thread(self.delete_worker, worker_id)

    async def async_clone_worker(
        self,
        worker_id: int,
        new_name: str,
        copy_config: bool = True,
        copy_parameters: bool = True,
    ) -> dict[str, Any]:
        """克隆Worker（异步版本，通过线程池执行同步DB操作）"""
        return await asyncio.to_thread(self.clone_worker, worker_id, new_name, copy_config, copy_parameters)

    def update_worker_config(self, worker_id: int, config: dict[str, Any]) -> dict[str, Any]:
        """
        更新 Worker 配置（同步版本）

        Args:
            worker_id: Worker ID
            config: 配置字典

        Returns:
            更新后的Worker字典

        Raises:
            WorkerNotFoundException: Worker不存在时抛出
            WorkerOperationException: 更新失败时抛出
        """
        try:
            with self.get_db() as db:
                worker = crud.update_worker_config(db, worker_id, config)
                if not worker:
                    raise WorkerNotFoundException(worker_id)
                result = worker.to_dict()
                logger.info(f"[WorkerCoreService] Worker配置更新成功: id={worker_id}")
                return result
        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[WorkerCoreService] 更新Worker配置失败: worker_id={worker_id}, error={e}")
            msg = "更新配置"
            raise WorkerOperationException(msg, worker_id, message=str(e))

    async def async_update_worker_config(self, worker_id: int, config: dict[str, Any]) -> dict[str, Any]:
        """更新Worker配置（异步版本，通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.update_worker_config, worker_id, config)

    # ==================== 批量操作 ====================

    def batch_operation(self, worker_ids: list[int], operation: str) -> dict[str, Any]:
        """
        批量操作Worker（同步版本，供CLI使用）

        两步语义：
        1. 状态机校验/转换（StateMachineGuard.batch_transition）
        2. 对转换成功的 Worker 逐个执行真实操作（start/stop/restart，
           与单机命令同一调用链，经 Orchestrator→ZMQ 管理独立进程）

        Args:
            worker_ids: Worker ID列表
            operation: 操作类型 (start/stop/restart)

        Returns:
            包含success、failed、total、results的字典
        """
        from .state_guard import StateMachineGuard, WorkerState

        valid_operations = {
            "start": WorkerState.STARTING,
            "stop": WorkerState.STOPPING,
            "restart": WorkerState.RESTARTING,
        }

        if operation not in valid_operations:
            raise WorkerOperationException(
                operation,
                message=f"不支持的操作类型: {operation}，支持的操作: {list(valid_operations.keys())}",
            )

        target_state = valid_operations[operation]
        guard = StateMachineGuard()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # 状态机转换与真实操作解析不能直接 asyncio.run（若已在事件循环中会冲突）
        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                batch_result = pool.submit(
                    asyncio.run,
                    self._run_batch_core(guard, worker_ids, target_state, operation),
                ).result()
        else:
            batch_result = asyncio.run(self._run_batch_core(guard, worker_ids, target_state, operation))

        result = {
            "success": batch_result.success_ids,
            "failed": batch_result.failed_dict,
            "total": batch_result.total,
            "results": batch_result.results,
        }

        logger.info(
            f"[WorkerCoreService] 批量{operation}完成 (状态机+真实操作): "
            f"成功={len(batch_result.success_ids)}, "
            f"失败={len(batch_result.failed_dict)}, "
            f"总计={batch_result.total}"
        )

        return result

    async def _run_batch_core(
        self,
        guard: Any,
        worker_ids: list[int],
        target_state: Any,
        operation: str,
    ) -> Any:
        """批量操作的统一内核（同步/异步两条路径共用）。历经三阶段：

        1. 状态机校验/批量转换（StateMachineGuard）
        2. 对转换成功的 Worker 顺序执行真实操作（与单机命令同一调用链）
        3. 回写状态机终态（running/stopped/error），防止机器长期停留在
           starting/stopping 中间态，阻塞后续批量/单机状态转换

        ponytail: 步骤 2 顺序执行而非并发——批量 Worker 数通常很小，
        并发 Popen+ZMQ 注册窗会放大路由竞态，收益不抵复杂度。
        """
        from .state_guard import WorkerState
        from .worker_state import worker_state_manager

        batch_result = await guard.batch_transition(worker_ids, target_state, operation)

        op_fn = {
            "start": self.start_worker,
            "stop": self.stop_worker,
            "restart": self.restart_worker,
        }[operation]
        final_state = WorkerState.RUNNING if operation in ("start", "restart") else WorkerState.STOPPED

        for wid in list(batch_result.success_ids):
            try:
                await asyncio.to_thread(op_fn, wid)
                # 回写状态机终态：真实操作已完成的语义不能被 starting/stopping 覆盖
                write_result = guard.transition(wid, final_state)
                if not write_result.success:
                    logger.warning(
                        f"[WorkerCoreService] 批量{operation}: Worker {wid} 终态回写失败: {write_result.message}"
                    )
                await worker_state_manager.transition(wid, final_state.value)
                logger.info(f"[WorkerCoreService] 批量{operation}: Worker {wid} 执行成功")
            except Exception as e:
                logger.warning(f"[WorkerCoreService] 批量{operation}: Worker {wid} 执行失败: {e}")
                try:
                    guard.transition(wid, WorkerState.ERROR)
                    await worker_state_manager.transition(wid, "error", error_message=str(e))
                except Exception:
                    pass
                batch_result.success_ids.remove(wid)
                batch_result.failed_dict[wid] = str(e)
        return batch_result

    async def async_batch_operation(self, worker_ids: list[int], operation: str) -> dict[str, Any]:
        """批量操作Worker（异步版本，直接await协程避免死锁）

        与同步版本共用 _run_batch_core 内核，行为完全一致。
        """
        from .state_guard import StateMachineGuard, WorkerState

        valid_operations = {
            "start": WorkerState.STARTING,
            "stop": WorkerState.STOPPING,
            "restart": WorkerState.RESTARTING,
        }

        if operation not in valid_operations:
            raise WorkerOperationException(
                operation,
                message=f"不支持的操作类型: {operation}，支持的操作: {list(valid_operations.keys())}",
            )

        target_state = valid_operations[operation]
        guard = StateMachineGuard()
        batch_result = await self._run_batch_core(guard, worker_ids, target_state, operation)

        result = {
            "success": batch_result.success_ids,
            "failed": batch_result.failed_dict,
            "total": batch_result.total,
            "results": batch_result.results,
        }

        logger.info(
            f"[WorkerCoreService] 批量{operation}完成 (异步): "
            f"成功={len(batch_result.success_ids)}, "
            f"失败={len(batch_result.failed_dict)}, "
            f"总计={batch_result.total}"
        )

        return result

    # ==================== 辅助方法 ====================

    def get_worker_by_name(self, name: str) -> dict[str, Any] | None:
        """根据名称精确匹配获取Worker"""
        with self.get_db() as db:
            worker = db.query(models.Worker).filter(models.Worker.name == name).first()
            if worker:
                return worker.to_dict()
            return None

    def check_worker_exists(self, worker_id: int) -> bool:
        """检查Worker是否存在"""
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            return worker is not None

    def get_worker_count(self, status: str | None = None) -> int:
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

    def _handle_state_change(self, event_data: dict[str, Any]):
        """
        处理 Worker 状态变更事件

        Args:
            event_data: 事件数据字典，包含 worker_id, old_status, new_status, timestamp
        """
        worker_id = event_data.get("worker_id")
        old_status = event_data.get("old_status")
        new_status = event_data.get("new_status")
        timestamp = event_data.get("timestamp")

        logger.info(f"[状态事件] Worker {worker_id} 状态变更: {old_status} -> {new_status} (时间: {timestamp})")

        if new_status == "error":
            error_msg = event_data.get("error_message", "未知错误")
            logger.warning(f"[状态事件] Worker {worker_id} 进入错误状态: {error_msg}")
        elif new_status == "running":
            logger.info(f"[状态事件] Worker {worker_id} 已成功启动并进入运行状态")

    async def handle_state_transition_event_async(self, event_data: dict[str, Any]):
        """
        异步处理策略状态转换事件（简化版，不再管理进程）

        通过 strategy_registry 更新运行时状态，同时更新 worker_state_manager。
        不涉及进程管理或 ZMQ 通信。

        Args:
            event_data: 事件数据字典，包含 worker_id, old_status, new_status 等
        """
        worker_id = event_data.get("worker_id")
        new_status = event_data.get("new_status")
        error_message = event_data.get("error_message")

        if worker_id is None:
            logger.warning("[handle_state_transition_event_async] 缺少 worker_id")
            return

        runtime = strategy_registry.get(worker_id)
        if runtime is not None:
            strategy_registry.update_status(worker_id, new_status, error_message=error_message)

        self._handle_state_change(event_data)

    async def get_worker_state(self, worker_id: int) -> dict[str, Any] | None:
        """
        获取 Worker 完整状态（合并 state_manager + strategy_registry）

        Args:
            worker_id: Worker ID

        Returns:
            Worker 状态字典，如果不存在返回 None
        """
        state = await worker_state_manager.get_state(worker_id)
        if state:
            result = state.to_dict()
            runtime = strategy_registry.get(worker_id)
            if runtime is not None:
                result["runtime"] = runtime.to_dict()
            return result
        return None

    # ==================== 启动 / 停止 / 重启 ====================

    def start_worker(self, worker_id: int) -> dict:
        """
        启动 Worker（同步版本，供 CLI 使用）

        进程内直调 worker_system.start_strategy（规则/LLM/RL 统一由进程内
        Driver 路径运行），在工作线程中以 asyncio.run 驱动 async 入口。

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str, "pid": int}

        Raises:
            WorkerNotFoundException: Worker 不存在
            WorkerAlreadyRunningException: Worker 已在运行
            WorkerOperationException: 启动失败
        """
        # 进程内路径不依赖 trading_system 初始化，因此本方法不调用
        # _ensure_initialized()，CLI 独立进程也能正常启动 Worker。
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundException(worker_id)
            if worker.status == "running":
                raise WorkerAlreadyRunningException(worker_id)

        logger.info(f"[WorkerCoreService] 同步启动 Worker {worker_id}")

        try:
            return self._start_worker_in_process(worker_id)
        except WorkerOperationException:
            raise
        except Exception as e:
            logger.error(f"[WorkerCoreService] 进程内启动 Worker {worker_id} 失败: {e}")
            raise WorkerOperationException("启动", worker_id, message=str(e)) from e

    def _start_worker_in_process(self, worker_id: int) -> dict:
        """进程内直调 worker_system 启动策略（同步上下文入口）。

        本方法运行在工作线程（asyncio.to_thread / CLI 主线程），必须用
        asyncio.run 起新 loop 驱动 async 的 start_strategy；state 管理器的
        锁已是 threading.Lock（worker_state.py），跨 loop 调用安全。
        """
        import asyncio

        from .strategy_manager import worker_system

        ok = asyncio.run(worker_system.start_strategy(worker_id))
        if not ok:
            # start_strategy 吞掉内部异常后返回 False，真实原因落在
            # registry 的 error_message（其内部 update_status(error) 已写入）
            registry = strategy_registry.get(worker_id)
            err_msg = (registry.error_message if registry else None) or "策略启动失败（未知原因，详见服务端日志）"
            raise WorkerOperationException("启动", worker_id, message=str(err_msg))
        # start_strategy 成功路径（_finalize_start）已完成 DB running +
        # pid=os.getpid() 落库（Worker 与主进程同进程，pid 记主进程）
        return {"worker_id": worker_id, "status": "running", "pid": os.getpid()}

    def _stop_worker_in_process(self, worker_id: int) -> dict:
        """进程内直调 worker_system 停止策略（同步上下文入口，asyncio.run 驱动）。

        stop 直调无需位置权限/传输探测，不存在 orchestrator 时代的
        pid SIGTERM 兜底场景——失败直接抛错转译。
        """
        import asyncio

        from .strategy_manager import worker_system

        try:
            asyncio.run(worker_system.stop_strategy(worker_id))
        except WorkerNotFoundException:
            # DB 有记录但 strategy_manager 无运行时（如 API 重启后从未启动过
            # 的 worker）：对齐 orchestrator 时代对无响应 daemon 的幂等语义，
            # 视为已停止而非报错
            logger.info(f"[WorkerCoreService] Worker {worker_id} 无运行时记录，视为已停止")
        return {"worker_id": worker_id, "status": "stopped"}

    def _get_status_via_orchestrator(self, worker_id: int) -> dict:
        """通过 WorkerOrchestrator 获取实时状态。

        启动/停止已切进程内直调后，orchestrator 仅保留 status 查询职责
        （Task 5 摘除启动引用；daemon 侧策略运行时废码已清理）。

        CLI 独立进程场景：注册表为空时主动建立 ZMQ 通道探测 daemon；
        通道不可用（如 FastAPI 占用）则回退返回 DB 状态。
        """
        # 延迟导入：避免 core_service 模块加载时引入 orchestrator 对 ZMQ
        # 传输层的传递依赖，保持 core_service 可独立导入
        from .orchestrator import WorkerOrchestrator

        orchestrator = WorkerOrchestrator.get_instance()

        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundException(worker_id)

        info = orchestrator.get_worker_info(worker_id)
        if info and info.is_alive:
            response = orchestrator.send_command_and_wait(worker_id, "status")
            if response and response.get("status") == "ok":
                data = response.get("data", {})
                return {
                    "worker_id": worker_id,
                    "db_status": worker.status,
                    "runtime_status": data.get("status"),
                    "is_running": data.get("status") == "running",
                    "pid": data.get("pid"),
                }

        # CLI 独立进程：注册表为空 → 尝试建立通道直接探测（短超时，避免久等）
        try:
            orchestrator.ensure_transport()
        except Exception as e:
            logger.warning(f"[WorkerCoreService] ZMQ 通道不可用，返回 DB 状态: {e}")
            return {
                "worker_id": worker_id,
                "db_status": worker.status,
                "runtime_status": None,
                "is_running": False,
                "message": "ZMQ 通道不可用，显示数据库状态",
            }

        response = orchestrator.send_command_and_wait(worker_id, "status", timeout=2.0)
        if response and response.get("status") == "ok" and response.get("data", {}).get("status"):
            data = response.get("data", {})
            return {
                "worker_id": worker_id,
                "db_status": worker.status,
                "runtime_status": data.get("status"),
                "is_running": data.get("status") == "running",
                "pid": data.get("pid") or worker.pid,
            }

        # daemon 无响应，返回 DB 状态
        return {
            "worker_id": worker_id,
            "db_status": worker.status,
            "runtime_status": None,
            "is_running": False,
            "message": "Worker 进程未连接",
        }

    async def async_start_worker(self, worker_id: int) -> dict:
        """异步启动 Worker（与 CLI 同步版本调用链一致，进程内直调 worker_system）。

        统一走 self.start_worker() 的同步实现，通过线程池执行，保证 FastAPI
        与 CLI 行为完全一致：进程内 Driver 路径启动，失败直接抛错不降级。
        """
        logger.info(f"[WorkerCoreService] 异步启动 Worker {worker_id}")
        # 不调用 _ensure_initialized()：进程内路径不依赖 trading_system，CLI/API 必须同语义
        try:
            success = await worker_state_manager.transition(worker_id, "starting")
            if not success:
                state = await worker_state_manager.get_state(worker_id)
                current_status = state.status if state else "unknown"
                if current_status == "running":
                    return {
                        "worker_id": worker_id,
                        "status": "running",
                        "message": "Worker 已经处于运行状态",
                    }
                if current_status == "starting":
                    return {
                        "worker_id": worker_id,
                        "status": "starting",
                        "message": "Worker 正在启动中...",
                    }
                msg = "启动"
                raise WorkerOperationException(msg, worker_id, f"当前状态 ({current_status}) 不允许启动")

            # 后台异步执行启动逻辑，避免阻塞 API 响应
            async def _runner():
                try:
                    result = await asyncio.to_thread(self.start_worker, worker_id)
                    # start_strategy 成功路径（_finalize_start）内部已 transition(running)，
                    # 此处补转会被 running→running 拒绝并返回 False；保留它作为
                    # 启动实现变化时的幂等兜底（拒绝不抛错、调用方不检查返回值）
                    trans_kwargs = {"pid": result["pid"]} if result.get("pid") else {}
                    await worker_state_manager.transition(worker_id, "running", **trans_kwargs)
                    logger.info(f"[async_start_worker] Worker {worker_id} 启动完成: {result}")
                except WorkerNotFoundException:
                    raise
                except Exception as e:
                    logger.exception(f"[async_start_worker] Worker {worker_id} 启动失败")
                    await worker_state_manager.transition(worker_id, "error", error_message=str(e))

            asyncio.create_task(_runner())

            return {
                "worker_id": worker_id,
                "status": "starting",
                "message": "Worker 启动请求已接收，正在异步处理中...",
            }
        except WorkerNotFoundException:
            raise
        except WorkerOperationException:
            raise
        except Exception as e:
            logger.exception(f"[WorkerCoreService] 异步启动 Worker {worker_id} 失败")
            # 未包装成 WorkerOperationException 的异常（如 DB 层异常）统一转译
            raise WorkerOperationException("启动", worker_id, message=str(e)) from e

    def stop_worker(self, worker_id: int) -> dict:
        """
        停止 Worker（同步版本，供 CLI 使用）

        进程内直调 worker_system.stop_strategy（停驱动线程 → 收口 driver →
        DB/状态机置 stopped），在工作线程中以 asyncio.run 驱动 async 入口。

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str}

        Raises:
            WorkerNotFoundException: Worker 不存在
            WorkerOperationException: 停止失败
        """
        # 进程内路径不依赖 trading_system 初始化（同 start_worker 的原因），
        # 本方法不调用 _ensure_initialized()。
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundException(worker_id)

        logger.info(f"[WorkerCoreService] 同步停止 Worker {worker_id}")

        try:
            return self._stop_worker_in_process(worker_id)
        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[WorkerCoreService] 进程内停止 Worker {worker_id} 失败: {e}")
            raise WorkerOperationException("停止", worker_id, message=str(e)) from e

    async def async_stop_worker(self, worker_id: int) -> dict:
        """异步停止 Worker（与 CLI 同步版本调用链一致，进程内直调 worker_system）。

        统一走 self.stop_worker() 的同步实现，通过线程池执行，保证 FastAPI
        与 CLI 行为完全一致：停驱动线程 → 收口 driver → DB/状态机置 stopped。
        """
        logger.info(f"[WorkerCoreService] 异步停止 Worker {worker_id}")
        # 不调用 _ensure_initialized()，原因同 async_start_worker
        try:
            success = await worker_state_manager.transition(worker_id, "stopping")
            if not success:
                state = await worker_state_manager.get_state(worker_id)
                current_status = state.status if state else "unknown"
                if current_status == "stopped":
                    return {
                        "worker_id": worker_id,
                        "status": "stopped",
                        "message": "Worker 已经处于停止状态",
                    }
                if current_status == "stopping":
                    return {
                        "worker_id": worker_id,
                        "status": "stopping",
                        "message": "Worker 正在停止中...",
                    }
                msg = "停止"
                raise WorkerOperationException(msg, worker_id, f"当前状态 ({current_status}) 不允许停止")

            async def _runner():
                try:
                    result = await asyncio.to_thread(self.stop_worker, worker_id)
                    # stop_worker 内部成功后只直写 DB stopped，必须补一次状态机
                    # 转换同步内存缓存；否则缓存停在 stopping，DB 却是 stopped，
                    # 缓存命中后不再水合 → Worker 永久卡死在 stopping
                    await worker_state_manager.transition(worker_id, "stopped")
                    logger.info(f"[async_stop_worker] Worker {worker_id} 停止完成: {result}")
                except WorkerNotFoundException:
                    raise
                except Exception as e:
                    logger.exception(f"[async_stop_worker] Worker {worker_id} 停止失败")
                    await worker_state_manager.transition(worker_id, "error", error_message=str(e))

            asyncio.create_task(_runner())

            return {
                "worker_id": worker_id,
                "status": "stopping",
                "message": "Worker 停止请求已接收，正在异步处理中...",
            }
        except WorkerNotFoundException:
            raise
        except WorkerOperationException:
            raise
        except Exception as e:
            logger.exception(f"[WorkerCoreService] 异步停止 Worker {worker_id} 失败")
            raise WorkerOperationException("停止", worker_id, message=str(e)) from e

    def restart_worker(self, worker_id: int) -> dict:
        """
        重启 Worker（同步版本）

        原子化操作：先停止再启动

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str}

        Raises:
            WorkerOperationException: 重启失败
        """
        # 不调用 _ensure_initialized()：stop/start 均为进程内直调 worker_system
        # （不依赖 trading_system），CLI 独立进程执行 restart 也不应被无关的
        # RuntimeError 阻断。
        logger.info(f"[WorkerCoreService] 同步重启 Worker {worker_id}")

        try:
            self.stop_worker(worker_id)
            return self.start_worker(worker_id)
        except Exception as e:
            logger.error(f"[WorkerCoreService] 同步重启 Worker {worker_id} 失败: {e}")
            raise

    async def _wait_for_terminal_state(self, worker_id: int, timeout: float) -> None:
        """等待 Worker 状态收敛到终态（stopped/error）。

        stop 是后台任务（ZMQ 优雅停止最长约 10s + SIGTERM 兜底），
        必须等它真正收尾后才能执行后续 start，否则 start 撞上
        stopping 过渡态必然被状态机拒绝。
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            state = await worker_state_manager.get_state(worker_id)
            if state is None or state.status in ("stopped", "error"):
                return
            await asyncio.sleep(0.2)
        # 超时未收敛：不吞掉，让后续 start 按当前状态给出明确错误
        logger.warning(f"[WorkerCoreService] 等待 Worker {worker_id} 停止收敛超时（{timeout}s）")

    async def async_restart_worker(self, worker_id: int) -> dict:
        """
        异步版本重启 Worker - 原子化状态驱动模式

        Args:
            worker_id: Worker ID

        Returns:
            dict: {"worker_id": int, "status": str}
        """
        logger.info(f"[WorkerCoreService] 异步重启 Worker {worker_id}")

        try:
            stop_result = await self.async_stop_worker(worker_id)

            if stop_result.get("status", "") == "stopping":
                # stop 是后台任务，先等它收敛到 stopped/error 再启动；
                # 超时余量 = stop 链路（asyncio.to_thread + 策略收尾 join）的经验值
                await self._wait_for_terminal_state(worker_id, timeout=15.0)

            return await self.async_start_worker(worker_id)
        except Exception as e:
            logger.error(f"[WorkerCoreService] 异步重启 Worker {worker_id} 失败: {e}")
            raise

    # ==================== 健康检查 ====================

    async def check_worker_health_async(self, worker_id: int) -> dict[str, Any]:
        """
        异步健康检查 — 基于 strategy_registry 运行时状态

        不再检查操作系统进程（pid/alive），而是直接查询 strategy_registry
        中策略的运行时状态和 asyncio Task 状态。

        Args:
            worker_id: Worker ID

        Returns:
            健康状态字典
        """
        runtime = strategy_registry.get(worker_id)

        if runtime is None:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
            return {
                "worker_id": worker_id,
                "is_healthy": False,
                "status": worker.status if worker else "unknown",
                "reason": "策略未在注册表中",
                "db_exists": worker is not None,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        is_healthy = runtime.is_running
        task = runtime._run_task
        task_healthy = task is not None and not task.done() if is_healthy else None

        return {
            "worker_id": worker_id,
            "is_healthy": is_healthy,
            "status": runtime.status,
            "runtime_status": runtime.status,
            "task_healthy": task_healthy,
            "error_message": runtime.error_message,
            "started_at": runtime.started_at,
            "stopped_at": runtime.stopped_at,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def health_check(self, worker_id: int) -> dict:
        """
        健康检查（同步版本）

        基于 strategy_registry 运行时状态，不再检查操作系统进程。

        Args:
            worker_id: Worker ID

        Returns:
            dict: 健康检查结果
        """
        try:
            runtime = strategy_registry.get(worker_id)

            if runtime is None:
                with self.get_db() as db:
                    worker = crud.get_worker(db, worker_id)
                    if not worker:
                        raise WorkerNotFoundException(worker_id)

                return {
                    "worker_id": worker_id,
                    "status": worker.status,
                    "is_healthy": False,
                    "checks": {
                        "db_record": True,
                        "in_registry": False,
                        "is_running": False,
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            is_healthy = runtime.is_running
            task = runtime._run_task

            return {
                "worker_id": worker_id,
                "status": runtime.status,
                "is_healthy": is_healthy,
                "checks": {
                    "db_record": True,
                    "in_registry": True,
                    "is_running": runtime.is_running,
                    "task_exists": task is not None,
                    "task_done": task.done() if task else None,
                },
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[health_check] Worker {worker_id} 健康检查失败: {e}")
            return {
                "worker_id": worker_id,
                "status": "unknown",
                "is_healthy": False,
                "checks": {},
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def async_health_check(self, worker_id: int) -> dict:
        """异步版本健康检查"""
        return await self.check_worker_health_async(worker_id)

    def get_worker_status(self, worker_id: int) -> dict:
        """
        获取 Worker 实时状态

        优先通过 WorkerOrchestrator 获取独立进程的真实状态（ZMQ 探测），
        ZMQ 通道不可用时回退到 strategy_registry + DB 状态。

        Args:
            worker_id: Worker ID

        Returns:
            dict: Worker 状态信息
        """
        try:
            return self._get_status_via_orchestrator(worker_id)
        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.warning(f"[get_worker_status] ZMQ 路径失败，回退 registry/DB: {e}")

        # 回退: 直接读 strategy_registry + DB（进程内模式）
        try:
            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundException(worker_id)

            runtime = strategy_registry.get(worker_id)

            if runtime is not None:
                return {
                    "worker_id": worker_id,
                    "db_status": worker.status,
                    "runtime_status": runtime.status,
                    "is_running": runtime.is_running,
                    "started_at": runtime.started_at,
                    "stopped_at": runtime.stopped_at,
                    "error_message": runtime.error_message,
                }
            else:
                return {
                    "worker_id": worker_id,
                    "db_status": worker.status,
                    "runtime_status": None,
                    "is_running": False,
                    "message": "Worker 未在 strategy_registry 中注册（可能尚未通过 trading_system 创建）",
                }

        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[get_worker_status] 获取 Worker {worker_id} 状态失败: {e}")
            return {
                "worker_id": worker_id,
                "db_status": "unknown",
                "runtime_status": None,
                "is_running": False,
                "error": str(e),
            }

    async def async_get_worker_status(self, worker_id: int) -> dict:
        """异步版本获取 Worker 状态（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_worker_status, worker_id)

    # ==================== 监控与日志管理方法 ====================

    def _get_log_file_reader(self, worker_id: str):
        """
        获取 LogFileReader 实例

        Args:
            worker_id: Worker ID（字符串格式）

        Returns:
            LogFileReader: 日志文件读取器实例
        """
        from .log_utils import get_log_file_manager

        log_mgr = get_log_file_manager()
        return log_mgr.get_reader(str(worker_id))

    def get_worker_logs(
        self,
        worker_id: int,
        level: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """
        查询 Worker 日志（基于文件系统 - 高性能方案）

        Args:
            worker_id: Worker ID
            level: 日志级别筛选 (DEBUG/INFO/WARNING/ERROR)
            start_time: 开始时间 (ISO 8601 格式字符串)
            end_time: 结束时间 (ISO 8601 格式字符串)
            limit: 返回条数 (1-1000)
            offset: 偏移量（用于分页）

        Returns:
            dict: {"items": List[dict], "total": int, "limit": int, "offset": int}

        Raises:
            LogQueryException: 日志查询失败
        """
        try:
            from datetime import datetime as dt

            start_dt = None
            end_dt = None

            if start_time:
                try:
                    start_dt = dt.fromisoformat(start_time)
                except ValueError:
                    logger.warning(f"[get_worker_logs] 开始时间格式无效: {start_time}")

            if end_time:
                try:
                    end_dt = dt.fromisoformat(end_time)
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
            raise LogQueryException(worker_id, message=str(e))

    async def async_get_worker_logs(
        self,
        worker_id: int,
        level: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """异步版本查询 Worker 日志（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_worker_logs, worker_id, level, start_time, end_time, limit, offset)

    def clear_worker_logs(self, worker_id: int, before_days: int | None = None, confirm: bool = False) -> dict:
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
            LogQueryException: 日志清理失败
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
            raise LogQueryException(worker_id, message=f"日志清理失败: {e!s}")

    async def async_clear_worker_logs(
        self, worker_id: int, before_days: int | None = None, confirm: bool = False
    ) -> dict:
        """异步版本清理 Worker 日志（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.clear_worker_logs, worker_id, before_days, confirm)

    # ---------- 性能指标查询 ----------

    def get_worker_metrics(self, worker_id: int) -> dict:
        """
        获取 Worker 实时性能指标（基于 strategy_registry）

        由于不再使用进程隔离，性能指标从 strategy_registry 运行时状态提取。

        Args:
            worker_id: Worker ID

        Returns:
            dict: 性能指标数据

        Raises:
            MetricsException: 获取性能指标失败
        """
        try:
            runtime = strategy_registry.get(worker_id)

            metrics_data = {
                "worker_id": worker_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "status": runtime.status if runtime else "unknown",
                "is_running": runtime.is_running if runtime else False,
                "started_at": runtime.started_at if runtime else None,
                "stopped_at": runtime.stopped_at if runtime else None,
                "error_message": runtime.error_message if runtime else None,
            }

            with self.get_db() as db:
                worker = crud.get_worker(db, worker_id)
                if not worker:
                    raise WorkerNotFoundException(worker_id)

                metrics_data["status"] = worker.status
                metrics_data["name"] = worker.name

            logger.info(f"[get_worker_metrics] 获取 Worker {worker_id} 性能指标成功")
            return metrics_data

        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[get_worker_metrics] Worker {worker_id} 获取性能指标失败: {e}")
            raise MetricsException(worker_id, message=str(e))

    async def async_get_worker_metrics(self, worker_id: int) -> dict:
        """异步版本获取 Worker 性能指标（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_worker_metrics, worker_id)

    def get_metrics_history(self, worker_id: int, start_time=None, end_time=None, interval="1m") -> list:
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
                start_dt = dt.fromisoformat(start_time) if isinstance(start_time, str) else start_time

            if end_time:
                end_dt = dt.fromisoformat(end_time) if isinstance(end_time, str) else end_time

            with self.get_db() as db:
                history = crud.get_metrics_history(db, worker_id, start_dt, end_dt, interval)
                return history
        except Exception as e:
            logger.error(f"[get_metrics_history] Worker {worker_id} 获取历史指标失败: {e}")
            raise MetricsException(worker_id, message=str(e))

    async def async_get_metrics_history(self, worker_id: int, start_time=None, end_time=None, interval="1m") -> list:
        """异步版本获取历史性能指标（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_metrics_history, worker_id, start_time, end_time, interval)

    # ---------- 交易记录与订单查询 ----------

    def get_worker_trades(
        self,
        worker_id: int,
        symbol: str | None = None,
        side: str | None = None,
        order_type: str | None = None,
        pnl_status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        获取 Worker 交易记录（SQLAlchemy 主库）

        Args:
            worker_id: Worker ID
            symbol: 交易对筛选
            side: 买卖方向 buy/sell
            order_type: 订单类型 market/limit/stop
            pnl_status: 盈亏状态 profit/loss/flat
            start_time: 开始时间
            end_time: 结束时间
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            dict: {"items": List[dict], "total": int, "page": int, "page_size": int}

        Raises:
            WorkerOperationException: 查询失败
        """
        try:
            page_size = min(page_size, self._config["max_page_size"])
            skip = (page - 1) * page_size

            with self.get_db() as db:
                trades, total = crud.get_worker_trades_paginated(
                    db,
                    worker_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    pnl_status=pnl_status,
                    start_time=start_time,
                    end_time=end_time,
                    skip=skip,
                    limit=page_size,
                )
                return {
                    "items": [t.to_dict() for t in trades],
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
        except Exception as e:
            logger.error(f"[get_worker_trades] Worker {worker_id} 获取交易记录失败: {e}")
            msg = "获取交易记录"
            raise WorkerOperationException(msg, worker_id, message=str(e))

    async def async_get_worker_trades(
        self,
        worker_id: int,
        symbol: str | None = None,
        side: str | None = None,
        order_type: str | None = None,
        pnl_status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """异步版本获取 Worker 交易记录（通过线程池执行同步操作）"""
        return await asyncio.to_thread(
            self.get_worker_trades,
            worker_id,
            symbol,
            side,
            order_type,
            pnl_status,
            start_time,
            end_time,
            page,
            page_size,
        )

    def get_worker_orders(self, worker_id: int, status: str | None = None, limit: int = 50) -> dict:
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
                query = db.query(models.WorkerOrder).filter(models.WorkerOrder.worker_id == worker_id)

                if status:
                    query = query.filter(models.WorkerOrder.status == status)

                total = query.count()
                orders = query.order_by(models.WorkerOrder.created_at.desc()).limit(limit).all()

                return {
                    "items": [o.to_dict() for o in orders],
                    "total": total,
                }
        except Exception as e:
            logger.error(f"[get_worker_orders] Worker {worker_id} 获取订单列表失败: {e}")
            msg = "获取订单"
            raise WorkerOperationException(msg, worker_id, message=str(e))

    async def async_get_worker_orders(self, worker_id: int, status: str | None = None, limit: int = 50) -> dict:
        """异步版本获取 Worker 订单列表（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_worker_orders, worker_id, status, limit)

    # ---------- 统计信息 ----------

    def get_worker_stats(self, worker_id: int | None = None) -> dict:
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
                        raise WorkerNotFoundException(worker_id)

                    trades_count = (
                        db.query(models.WorkerTrade).filter(models.WorkerTrade.worker_id == worker_id).count()
                    )

                    orders_count = (
                        db.query(models.WorkerOrder).filter(models.WorkerOrder.worker_id == worker_id).count()
                    )

                    runtime = strategy_registry.get(worker_id)

                    return {
                        "worker_id": worker_id,
                        "name": worker.name,
                        "status": worker.status,
                        "runtime_status": runtime.status if runtime else None,
                        "is_running": runtime.is_running if runtime else False,
                        "trades_count": trades_count,
                        "orders_count": orders_count,
                        "created_at": worker.created_at.isoformat() if worker.created_at else None,
                        "started_at": runtime.started_at
                        if runtime
                        else (worker.started_at.isoformat() if worker.started_at else None),
                    }
                else:
                    running = self.get_worker_count("running")
                    stopped = self.get_worker_count("stopped")
                    error = self.get_worker_count("error")
                    paused = self.get_worker_count("paused")
                    starting = self.get_worker_count("starting")

                    total_workers = db.query(models.Worker).count()

                    running_runtimes = sum(1 for rt in strategy_registry.list_all() if rt.is_running)

                    return {
                        "total_workers": total_workers,
                        "running": running,
                        "stopped": stopped,
                        "error": error,
                        "paused": paused,
                        "starting": starting,
                        "registry_running": running_runtimes,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
        except WorkerNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[get_worker_stats] 获取统计信息失败: {e}")
            msg = "统计信息"
            raise WorkerOperationException(msg, message=str(e))

    async def async_get_worker_stats(self, worker_id: int | None = None) -> dict:
        """异步版本获取 Worker 统计信息（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_worker_stats, worker_id)

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
            msg = "绩效统计"
            raise WorkerOperationException(msg, worker_id, message=str(e))

    async def async_get_worker_performance(self, worker_id: int, days: int = 30) -> list:
        """异步版本获取 Worker 绩效统计（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.get_worker_performance, worker_id, days)

    # ---------- 诊断功能 ----------

    def diagnose_worker(self, worker_id: int | None = None) -> dict:
        """
        诊断 Worker 系统状态（精简版，基于 strategy_registry）

        不再检查 ZMQ 端口或操作系统幽灵进程。

        Args:
            worker_id: Worker ID（可选，不指定则进行系统级诊断）

        Returns:
            dict: 完整的诊断报告
        """
        diagnosis = {
            "timestamp": datetime.now(UTC).isoformat(),
            "diagnosis_type": "system" if not worker_id else "worker",
            "checks": {},
            "issues": [],
            "recommendations": [],
            "summary": "",
        }

        try:
            if worker_id:
                diagnosis["worker_id"] = worker_id

                basic_info = self._get_worker_basic_info(worker_id)
                diagnosis["checks"]["basic_info"] = basic_info

                if not basic_info.get("exists"):
                    diagnosis["issues"].append(f"Worker {worker_id} 不存在")
                    diagnosis["summary"] = f"Worker {worker_id} 不存在，无法继续诊断"
                    return diagnosis

                lifecycle_status = self._diagnose_lifecycle(worker_id)
                diagnosis["checks"]["lifecycle"] = lifecycle_status

                logs_diagnosis = self._diagnose_logs(worker_id)
                diagnosis["checks"]["logs"] = logs_diagnosis

                self._generate_worker_diagnosis_summary(diagnosis, basic_info)
            else:
                stats = self.get_worker_stats()
                diagnosis["checks"]["system_stats"] = stats

                self._generate_system_diagnosis_summary(diagnosis, stats)

            logger.info(f"[diagnose_worker] 诊断完成, 发现 {len(diagnosis['issues'])} 个问题")
            return diagnosis

        except Exception as e:
            logger.error(f"[diagnose_worker] 诊断失败: {e}")
            diagnosis["error"] = str(e)
            diagnosis["issues"].append(f"诊断过程出错: {e!s}")
            return diagnosis

    async def async_diagnose_worker(self, worker_id: int | None = None) -> dict:
        """异步版本诊断 Worker（通过线程池执行同步操作）"""
        return await asyncio.to_thread(self.diagnose_worker, worker_id)

    # ---------- 诊断辅助方法 ----------

    def _get_worker_basic_info(self, worker_id: int) -> dict:
        """获取 Worker 基本信息（合并 DB + registry）"""
        try:
            worker = self.get_worker(worker_id)
            runtime = strategy_registry.get(worker_id)
            return {
                "exists": True,
                "worker_id": worker_id,
                "name": worker.get("name"),
                "status": worker.get("status"),
                "strategy_id": worker.get("strategy_id"),
                "runtime_status": runtime.status if runtime else None,
                "is_running": runtime.is_running if runtime else False,
            }
        except WorkerNotFoundException:
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
        """诊断 Worker 生命周期状态（基于 strategy_registry）"""
        try:
            status = self.get_worker_status(worker_id)
            runtime = strategy_registry.get(worker_id)

            is_healthy = runtime.is_running if runtime else False
            is_alive = runtime.is_running if runtime else False

            issues = []

            if not is_healthy:
                if runtime is None:
                    issues.append("策略未在 strategy_registry 中注册")
                elif runtime.status == "error":
                    issues.append(f"策略处于错误状态: {runtime.error_message}")
                elif runtime.status == "stopped":
                    issues.append("策略已停止")
                else:
                    issues.append("策略未在运行中")

            if status.get("db_status") == "running" and not is_alive:
                issues.append("数据库显示运行中，但 strategy_registry 中策略未运行")

            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "is_healthy": is_healthy,
                "is_alive": is_alive,
                "db_status": status.get("db_status"),
                "runtime_status": runtime.status if runtime else None,
                "issues": issues,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"生命周期检查失败: {e!s}",
                "is_healthy": False,
                "is_alive": False,
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
                issues.append("暂无日志输出（策略可能未真正运行或日志文件不存在）")
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
                "message": f"日志检查失败: {e!s}",
                "has_logs": False,
                "total_logs": 0,
                "recent_logs_count": 0,
                "issues": [str(e)],
            }

    def _generate_worker_diagnosis_summary(self, diagnosis: dict, basic_info: dict):
        """生成 Worker 级别诊断总结"""
        worker_id = diagnosis.get("worker_id")
        current_status = basic_info.get("status", "unknown")
        basic_info.get("runtime_status")

        recommendations = []

        if current_status == "stopped":
            diagnosis["summary"] = f"Worker {worker_id} 状态为 stopped"
            recommendations.append("尝试启动 Worker")
        elif current_status == "running" and not basic_info.get("is_running"):
            diagnosis["summary"] = f"Worker {worker_id} 数据库显示 running 但 registry 中未运行"
            recommendations.append("尝试重启 Worker 以恢复一致性")
        elif current_status == "running":
            lifecycle = diagnosis["checks"].get("lifecycle", {})
            if lifecycle.get("is_healthy"):
                diagnosis["summary"] = f"Worker {worker_id} 状态正常 (running)"
            else:
                diagnosis["summary"] = f"Worker {worker_id} 运行中但存在健康问题"
                recommendations.extend(lifecycle.get("issues", []))
        elif current_status == "error":
            diagnosis["summary"] = f"Worker {worker_id} 处于错误状态"
            recommendations.append("查看日志了解具体错误原因")
        else:
            diagnosis["summary"] = f"Worker {worker_id} 当前状态: {current_status}"

        logs_issues = diagnosis["checks"].get("logs", {}).get("issues", [])
        if logs_issues:
            recommendations.extend(logs_issues)

        diagnosis["recommendations"] = recommendations

    def _generate_system_diagnosis_summary(self, diagnosis: dict, stats: dict):
        """生成系统级诊断总结"""
        recommendations = []
        running = stats.get("running", 0)
        total = stats.get("total_workers", 0)
        registry_running = stats.get("registry_running", 0)

        if total == 0:
            diagnosis["summary"] = "系统中没有任何 Worker"
            recommendations.append("创建并启动一个 Worker")
        elif running == 0:
            diagnosis["summary"] = f"有 {total} 个 Worker 但都没有运行"
            recommendations.append("尝试启动 Worker")
        elif running > 0:
            diagnosis["summary"] = f"系统正常运行，{running}/{total} 个 Worker 在运行"

        if registry_running != running:
            recommendations.append(
                f"DB 运行数 ({running}) 与 registry 运行数 ({registry_running}) 不一致，建议检查策略状态一致性"
            )

        diagnosis["recommendations"] = recommendations

    # ==================== 人工风控管控 ====================

    def _get_risk_control_sync(self, worker_id: int) -> schemas.RiskControlOut | None:
        with get_db_session() as db:
            worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
            if worker is None:
                raise WorkerNotFoundException(worker_id)
            row = db.query(models.WorkerRiskControl).filter(models.WorkerRiskControl.worker_id == worker_id).first()
            if row is None:
                return None
            return schemas.RiskControlOut(
                worker_id=worker_id,
                enabled=row.enabled,
                max_position_pct=row.max_position_pct,
                max_position_size=row.max_position_size,
                daily_loss_amount=row.daily_loss_amount,
                daily_loss_limit=row.daily_loss_limit,
                max_drawdown=row.max_drawdown,
                max_leverage=row.max_leverage,
                circuit_breaker_cooldown_secs=row.circuit_breaker_cooldown_secs,
                updated_at=row.updated_at,
            )

    async def async_get_risk_control(self, worker_id: int) -> schemas.RiskControlOut | None:
        """查询人工风控管控行；未配置返回 None（前端回落继承策略参数展示）。"""
        return await asyncio.to_thread(self._get_risk_control_sync, worker_id)

    def _upsert_risk_control_sync(self, worker_id: int, payload: schemas.RiskControlUpsert) -> None:
        # 显式写全部 8 字段（含 None）：表内历史 ORM default 非零，靠缺省无法区分「用户清空」
        with get_db_session() as db:
            worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
            if worker is None:
                raise WorkerNotFoundException(worker_id)

            def _apply(row: models.WorkerRiskControl) -> None:
                # updated_at 交由模型列 onupdate=func.now() 维护，不手动赋 aware 时间
                # （naive 列上写 aware datetime 会让时间偏 8 小时）
                row.enabled = payload.enabled
                row.max_position_pct = payload.max_position_pct
                row.max_position_size = payload.max_position_size
                row.daily_loss_amount = payload.daily_loss_amount
                row.daily_loss_limit = payload.daily_loss_limit
                row.max_drawdown = payload.max_drawdown
                row.max_leverage = payload.max_leverage
                row.circuit_breaker_cooldown_secs = payload.circuit_breaker_cooldown_secs

            row = db.query(models.WorkerRiskControl).filter(models.WorkerRiskControl.worker_id == worker_id).first()
            if row is None:
                row = models.WorkerRiskControl(worker_id=worker_id)
                db.add(row)
                # SQLAlchemy 坑：带 Column default 的列在「构造后赋 None」时与未赋值不可区分，
                # INSERT 会错误落历史 default（实测带出 0.1）。先 flush 让 default 只作用于本条
                # INSERT，对象转入 persistent 后再赋 None 走 UPDATE，写出的才是真实 NULL。
                db.flush()
            _apply(row)
            try:
                db.commit()
            except IntegrityError as exc:
                # 并发兜底：两个请求同时见「无行」各自 INSERT，后提交者撞 worker_id 唯一约束。
                # 回滚后重读对方已落的行，把字段应用上去再提交，保证并发 upsert 最终一致。
                db.rollback()
                logger.warning(f"[core_service] 风控 upsert 撞并发唯一约束，转更新 worker_id={worker_id}: {exc}")
                row = db.query(models.WorkerRiskControl).filter(models.WorkerRiskControl.worker_id == worker_id).one()
                _apply(row)
                db.commit()

    def _push_risk_control_sync(self, worker_id: int) -> str:
        """查运行中 driver + 策略参数，调 risk_config.push_risk_control 实时推送。异常一律降级 on_start。"""
        # 函数内 import：worker_system 构造重（交易所配置扫描），避免 core_service 导入期副作用
        from worker.risk_config import push_risk_control
        from worker.strategy_manager import worker_system

        driver = worker_system.get_running_driver(worker_id)
        with get_db_session() as db:
            worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
            if worker is None or worker.strategy_id is None:
                return "on_start"
            from strategy.models import Strategy  # 跨模块模型，函数内 import 防循环依赖

            strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
            if strategy is None:
                return "on_start"
        try:
            # strategy.parameters 是自由 JSON 文本：脏数据（非法 JSON / initial_capital 非数字）
            # 解析失败时不让已成功落库的 upsert 接口 500，降级 on_start 走启动前装配语义
            params = json.loads(strategy.parameters or "{}")
            initial_cash = float(params.get("initial_capital", 100_000.0))
            return push_risk_control(worker_id, driver, params, initial_cash)
        except Exception as exc:
            logger.error(f"[core_service] 风控推送异常 worker_id={worker_id}: {exc}")
            return "on_start"

    async def async_upsert_risk_control(
        self, worker_id: int, payload: schemas.RiskControlUpsert
    ) -> schemas.RiskControlOut:
        """落库 + 实时推送，返回 applied（hot=运行中已热更 / on_start=启动时生效）供前端分文案。"""
        await asyncio.to_thread(self._upsert_risk_control_sync, worker_id, payload)
        applied = await asyncio.to_thread(self._push_risk_control_sync, worker_id)
        out = await self.async_get_risk_control(worker_id)
        if out is None:
            # 刚 upsert 必有行；查询为 None 说明 stores 层异常，显式报错便于定位。
            # 不用 assert：python -O 下 assert 被跳过，异常会被静默吞掉
            raise RuntimeError(f"upsert 后查询 worker_risk_control 为空: worker_id={worker_id}")
        out.applied = applied
        return out

    def _worker_exists_sync(self, worker_id: int) -> bool:
        with get_db_session() as db:
            return db.query(models.Worker).filter(models.Worker.id == worker_id).first() is not None

    def _delete_risk_control_sync(self, worker_id: int) -> None:
        with get_db_session() as db:
            row = db.query(models.WorkerRiskControl).filter(models.WorkerRiskControl.worker_id == worker_id).first()
            if row is None:
                return  # 幂等
            db.delete(row)
            db.commit()

    async def async_delete_risk_control(self, worker_id: int) -> schemas.RiskControlOut:
        """删除人工管控行（语义回落 params.risk 直通），并把停用/直通语义实时推给运行中引擎；幂等。"""
        exists = await asyncio.to_thread(self._worker_exists_sync, worker_id)
        if not exists:
            raise WorkerNotFoundException(worker_id)
        await asyncio.to_thread(self._delete_risk_control_sync, worker_id)
        applied = await asyncio.to_thread(self._push_risk_control_sync, worker_id)
        return schemas.RiskControlOut(worker_id=worker_id, enabled=False, updated_at=None, applied=applied)


# 全局单例实例
worker_core_service = WorkerCoreService()
