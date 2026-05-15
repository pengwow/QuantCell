"""
Worker 系统全局单例

提供统一的 Worker 管理入口，整合状态管理、核心服务、进程管理等功能。
采用延迟初始化 + 全局单例 + 字典管理模式（参考 Nautilus-Web-Interface 设计）。

主要功能：
- Worker 配置的统一管理和持久化
- 生命周期操作（启动/停止/重启）的同步和异步双模式
- 批量操作支持
- 与 worker_state、core_service、manager 无缝集成
"""

import asyncio
import concurrent.futures
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class WorkerConfig:
    """Worker 配置对象"""
    worker_id: int
    name: str
    strategy_id: int
    exchange: str
    symbol: str
    status: str = "stopped"
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)


class WorkerSystem:
    """
    Worker 系统全局单例类

    采用 __new__ 实现单例模式（参考 Nautilus-Web-Interface state.py 设计）
    提供统一的 Worker 管理入口，整合所有子模块功能

    使用方式：
        from worker.worker_system import worker_system

        # 初始化（在应用启动时调用一次）
        await worker_system.initialize()

        # CRUD 操作
        worker_id = worker_system.create_worker({...})
        workers = worker_system.list_workers()

        # 生命周期操作
        result = await worker_system.async_start_worker(worker_id)
        result = worker_system.sync_start_worker(worker_id)  # 同步版本

        # 关闭（在应用退出时调用）
        await worker_system.shutdown()
    """

    _instance: Optional["WorkerSystem"] = None
    _initialized: bool = False
    _fully_initialized: bool = False

    def __new__(cls) -> "WorkerSystem":
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._fully_initialized = False
        return cls._instance

    def __init__(self):
        """轻量级初始化（只创建空字典等基本结构）"""
        if self._initialized:
            return

        self._initialized = True
        self.workers: Dict[int, WorkerConfig] = {}
        self.state_manager: Any = None
        self.manager: Any = None
        self.core_service: Any = None

        logger.info("WorkerSystem 单例已创建")

    @staticmethod
    def get_instance() -> "WorkerSystem":
        """
        获取单例实例（静态方法）

        Returns:
            WorkerSystem: 全局单例实例
        """
        if WorkerSystem._instance is None:
            WorkerSystem()
        instance = WorkerSystem._instance
        assert instance is not None, "WorkerSystem 实例不应为 None"
        return instance

    async def initialize(self) -> None:
        """
        完整初始化（异步方法）

        在应用启动时调用一次，完成：
        1. 导入并初始化 state_manager
        2. 创建 Manager 和 CoreService 实例
        3. 从数据库加载 Worker 配置
        4. 启动后台任务
        """
        if self._fully_initialized:
            logger.warning("WorkerSystem 已经完成完整初始化，跳过重复初始化")
            return

        try:
            logger.info("正在初始化 WorkerSystem...")

            # 首先初始化数据库配置，确保所有 SQLAlchemy 模型被正确导入
            # 这对于解决 Worker <-> Strategy 的循环依赖关系至关重要
            from collector.db.database import init_database_config
            init_database_config()
            logger.info("数据库配置初始化完成")

            from .worker_state import worker_state_manager
            self.state_manager = worker_state_manager

            logger.info("正在初始化状态管理器...")
            await self.state_manager.initialize()
            logger.info("状态管理器初始化完成")

            from .manager import TradingNodeWorkerManager
            self.manager = TradingNodeWorkerManager()
            logger.info("TradingNodeWorkerManager 已创建")

            from .core_service import WorkerCoreService
            self.core_service = WorkerCoreService()
            logger.info("WorkerCoreService 已创建")

            logger.info("正在从数据库加载 Worker 配置...")
            await self._load_workers_from_db()

            logger.info("正在启动 Manager 后台任务...")
            await self.manager.start()
            logger.info("Manager 后台任务已启动")

            self._fully_initialized = True
            logger.info(f"✅ WorkerSystem 初始化完成，共加载 {len(self.workers)} 个 Worker")

        except Exception as e:
            logger.error(f"❌ WorkerSystem 初始化失败: {e}")
            raise RuntimeError(f"WorkerSystem 初始化失败: {e}") from e

    async def shutdown(self) -> None:
        """
        优雅关闭（异步方法）

        在应用退出时调用，完成：
        1. 停止所有运行中的 Worker
        2. 停止 Manager 后台任务
        3. 重置初始化状态
        """
        if not self._fully_initialized:
            logger.warning("WorkerSystem 未完成初始化，无需关闭")
            return

        try:
            logger.info("正在关闭 WorkerSystem...")

            stopped_count = 0
            for worker_id, config in list(self.workers.items()):
                if config.status in ("running", "starting"):
                    try:
                        await self.async_stop_worker(worker_id)
                        stopped_count += 1
                    except Exception as e:
                        logger.error(f"停止 Worker {worker_id} 失败: {e}")

            logger.info(f"已停止 {stopped_count} 个运行中的 Worker")

            if self.manager:
                try:
                    await self.manager.stop()
                    logger.info("Manager 已停止")
                except Exception as e:
                    logger.error(f"停止 Manager 失败: {e}")

            self._fully_initialized = False
            logger.info("✅ WorkerSystem 已优雅关闭")

        except Exception as e:
            logger.error(f"❌ WorkerSystem 关闭时发生错误: {e}")
            self._fully_initialized = False
            raise

    async def _load_workers_from_db(self) -> None:
        """
        从数据库加载 Worker 配置

        查询所有 Worker 记录，构建 WorkerConfig 对象存入 self.workers 字典
        """
        from collector.db.database import SessionLocal

        # 确保 Strategy 模型已被注册（解决 SQLAlchemy 映射器依赖问题）
        try:
            from strategy.models import Strategy
        except ImportError:
            pass

        from . import crud

        db = SessionLocal()
        try:
            workers, total = crud.get_workers(db, skip=0, limit=10000)

            for worker in workers:
                trading_config = worker.get_trading_config_dict()
                worker_config_obj = WorkerConfig(
                    worker_id=int(worker.id),
                    name=str(worker.name),
                    strategy_id=int(worker.strategy_id or 0),
                    exchange=str(trading_config.get("exchange", "binance")),
                    symbol=trading_config.get("symbols_config", {}).get("symbols", ["BTCUSDT"])[0] if trading_config.get("symbols_config", {}).get("symbols") else "BTCUSDT",
                    status=str(worker.status or "stopped"),
                    config=worker.get_config_dict(),
                )
                self.workers[int(worker.id)] = worker_config_obj

            logger.info(f"从数据库加载了 {len(workers)} 个 Worker 配置")

        except Exception as e:
            logger.error(f"从数据库加载 Worker 配置失败: {e}")
            raise
        finally:
            db.close()

    def _ensure_initialized(self) -> None:
        """
        检查是否已完整初始化

        Raises:
            RuntimeError: 如果未完成初始化
        """
        if not self._fully_initialized:
            raise RuntimeError(
                "WorkerSystem 尚未完成初始化。"
                "请先调用 await worker_system.initialize() 完成初始化。"
            )

    # ==================== CRUD 操作 ====================

    def create_worker(self, config: Dict[str, Any]) -> int:
        """
        创建 Worker

        Args:
            config: Worker 配置字典（应符合 schemas.WorkerCreate 格式）

        Returns:
            int: 新创建的 Worker ID

        Raises:
            RuntimeError: 如果未初始化
            Exception: 如果创建失败
        """
        self._ensure_initialized()

        try:
            result = self.core_service.create_worker(config)
            worker_id = result['id']

            trading_config = result.get('trading_config', {})
            if isinstance(trading_config, str):
                import json
                trading_config = json.loads(trading_config)

            symbols = trading_config.get('symbols_config', {}).get('symbols', ['BTCUSDT'])

            worker_config_obj = WorkerConfig(
                worker_id=worker_id,
                name=result['name'],
                strategy_id=result.get('strategy_id', 0),
                exchange=trading_config.get('exchange', 'binance'),
                symbol=symbols[0] if symbols else 'BTCUSDT',
                status='stopped',
                config=result.get('config', {}),
            )
            self.workers[worker_id] = worker_config_obj

            logger.info(f"✅ Worker 创建成功: id={worker_id}, name={result['name']}")
            return worker_id

        except Exception as e:
            logger.error(f"❌ 创建 Worker 失败: {e}")
            raise

    def delete_worker(self, worker_id: int, force_stop: bool = False) -> bool:
        """
        删除 Worker

        Args:
            worker_id: Worker ID
            force_stop: 是否强制停止运行中的 Worker（默认 False）

        Returns:
            bool: 是否删除成功

        Raises:
            RuntimeError: 如果未初始化或 Worker 不存在/状态不允许删除
            Exception: 如果删除失败
        """
        self._ensure_initialized()

        if worker_id not in self.workers:
            raise RuntimeError(f"Worker {worker_id} 不存在")

        config = self.workers[worker_id]

        if config.status == 'running' and not force_stop:
            raise RuntimeError(
                f"Worker {worker_id} 正在运行中，无法删除。"
                f"请先停止 Worker 或使用 force_stop=True 强制删除。"
            )

        if config.status in ('running', 'starting') and force_stop:
            try:
                self.sync_stop_worker(worker_id)
            except Exception as e:
                logger.warning(f"强制停止 Worker {worker_id} 失败: {e}")

        try:
            self.core_service.delete_worker(worker_id)

            del self.workers[worker_id]

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.state_manager.remove_worker(worker_id))
            else:
                loop.run_until_complete(self.state_manager.remove_worker(worker_id))

            logger.info(f"✅ Worker 删除成功: id={worker_id}")
            return True

        except Exception as e:
            logger.error(f"❌ 删除 Worker {worker_id} 失败: {e}")
            raise

    def get_worker(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """
        获取 Worker 详情

        合并 WorkerConfig 字典状态和 state_manager 实时状态，
        返回完整信息（包含 _state_info 字段）

        Args:
            worker_id: Worker ID

        Returns:
            dict: Worker 完整信息，如果不存在返回 None
        """
        self._ensure_initialized()

        if worker_id not in self.workers:
            return None

        config = self.workers[worker_id]
        result = config.to_dict()

        loop = asyncio.get_event_loop()
        if loop.is_running():
            try:
                state_future = asyncio.ensure_future(self.state_manager.get_state(worker_id))
                if state_future.done():
                    state = state_future.result()
                    if state:
                        result['_state_info'] = state.to_dict()
            except Exception:
                pass
        else:
            try:
                state = loop.run_until_complete(self.state_manager.get_state(worker_id))
                if state:
                    result['_state_info'] = state.to_dict()
            except Exception:
                pass

        return result

    def list_workers(self, status_filter: Optional[str] = None) -> List[Dict]:
        """
        获取 Worker 列表

        Args:
            status_filter: 按状态过滤（可选）

        Returns:
            list: Worker 信息列表（包含 id 字段以兼容前端）
        """
        self._ensure_initialized()

        workers_list = []

        for worker_id, config in self.workers.items():
            if status_filter and config.status != status_filter:
                continue

            # 转换为字典并添加 id 别名（兼容前端期望的 id 字段）
            worker_info = config.to_dict()
            worker_info['id'] = worker_id  # 确保前端可以访问 worker.id
            workers_list.append(worker_info)

        return workers_list

    # ==================== 生命周期操作（同步/异步双模式） ====================

    async def async_start_worker(self, worker_id: int) -> Dict:
        """
        异步启动 Worker

        直接调用 CoreService 的内部实现方法 _do_start_worker，
        避免通过 core_service.async_start_worker() 形成循环依赖。

        调用链（修复后）：
        worker_system.async_start_worker()
          → core_service._do_start_worker()  ✅ 直接执行，无循环

        Args:
            worker_id: Worker ID

        Returns:
            dict: 启动结果
        """
        self._ensure_initialized()

        try:
            logger.info(f"[WorkerSystem] 正在异步启动 Worker {worker_id}")

            # 直接调用 CoreService 的内部实现方法，避免循环依赖
            # CoreService._do_start_worker 包含完整的启动逻辑：
            # - 从数据库读取 Worker 配置
            # - 加载策略文件（三层回退机制）
            # - 准备交易配置
            # - 通过 Manager 启动进程
            # - 验证进程存活并更新状态
            task = asyncio.create_task(
                self.core_service._do_start_worker(worker_id)
            )
            result = await asyncio.wait_for(task, timeout=120.0)

            # 更新本地 workers 字典的状态
            if worker_id in self.workers:
                self.workers[worker_id].status = result.get('status', 'running')

            logger.info(f"[WorkerSystem] Worker {worker_id} 异步启动完成")
            return result

        except Exception as e:
            logger.error(f"[WorkerSystem] 异步启动 Worker {worker_id} 失败: {e}")
            if worker_id in self.workers:
                self.workers[worker_id].status = 'error'
            raise

    def sync_start_worker(self, worker_id: int) -> Dict:
        """
        同步启动 Worker（包装器）

        处理事件循环问题：
        - 如果有 loop 在运行，使用 ThreadPoolExecutor 在新线程中运行 asyncio.run()
        - 否则直接 asyncio.run()

        Args:
            worker_id: Worker ID

        Returns:
            dict: 启动结果
        """
        self._ensure_initialized()

        logger.info(f"[WorkerSystem] 正在同步启动 Worker {worker_id}")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug(f"[WorkerSystem] 检测到事件循环正在运行，使用线程池执行")
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, self._sync_start_worker_impl(worker_id))
                    return future.result(timeout=60)
            else:
                logger.debug(f"[WorkerSystem] 事件循环未运行，直接执行")
                return loop.run_until_complete(self.async_start_worker(worker_id))

        except concurrent.futures.TimeoutError:
            logger.error(f"[WorkerSystem] 同步启动 Worker {worker_id} 超时")
            return {
                'worker_id': worker_id,
                'status': 'error',
                'message': '启动超时',
            }
        except Exception as e:
            logger.error(f"[WorkerSystem] 同步启动 Worker {worker_id} 失败: {e}")
            if worker_id in self.workers:
                self.workers[worker_id].status = 'error'
            raise

    async def _sync_start_worker_impl(self, worker_id: int) -> Dict:
        """同步启动的内部实现（在新的事件循环中运行）"""
        return await self.async_start_worker(worker_id)

    async def async_stop_worker(self, worker_id: int) -> Dict:
        """
        异步停止 Worker

        直接调用 CoreService 的内部实现方法 _do_stop_worker，
        避免通过 core_service.async_stop_worker() 形成循环依赖。

        调用链（修复后）：
        worker_system.async_stop_worker()
          → core_service._do_stop_worker()  ✅ 直接执行，无循环

        Args:
            worker_id: Worker ID

        Returns:
            dict: 停止结果
        """
        self._ensure_initialized()

        try:
            logger.info(f"[WorkerSystem] 正在异步停止 Worker {worker_id}")

            # 直接调用 CoreService 的内部实现方法，避免循环依赖
            # CoreService._do_stop_worker 包含完整的停止逻辑：
            # - 从数据库读取 Worker 配置和 PID
            # - 通过 Manager 发送 STOP 控制消息（方案1）
            # - 使用 SIGTERM 信号优雅终止（方案2）
            # - 强制 SIGKILL 终止（方案3）
            # - 更新最终状态为 stopped/error
            task = asyncio.create_task(
                self.core_service._do_stop_worker(worker_id)
            )
            result = await asyncio.wait_for(task, timeout=60.0)

            # 更新本地 workers 字典的状态
            if worker_id in self.workers:
                self.workers[worker_id].status = result.get('status', 'stopped')

            logger.info(f"[WorkerSystem] Worker {worker_id} 异步停止完成")
            return result

        except Exception as e:
            logger.error(f"[WorkerSystem] 异步停止 Worker {worker_id} 失败: {e}")
            raise

    def sync_stop_worker(self, worker_id: int) -> Dict:
        """
        同步停止 Worker（包装器）

        Args:
            worker_id: Worker ID

        Returns:
            dict: 停止结果
        """
        self._ensure_initialized()

        logger.info(f"[WorkerSystem] 正在同步停止 Worker {worker_id}")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug(f"[WorkerSystem] 检测到事件循环正在运行，使用线程池执行")
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, self._sync_stop_worker_impl(worker_id))
                    return future.result(timeout=60)
            else:
                logger.debug(f"[WorkerSystem] 事件循环未运行，直接执行")
                return loop.run_until_complete(self.async_stop_worker(worker_id))

        except concurrent.futures.TimeoutError:
            logger.error(f"[WorkerSystem] 同步停止 Worker {worker_id} 超时")
            return {
                'worker_id': worker_id,
                'status': 'error',
                'message': '停止超时',
            }
        except Exception as e:
            logger.error(f"[WorkerSystem] 同步停止 Worker {worker_id} 失败: {e}")
            raise

    async def _sync_stop_worker_impl(self, worker_id: int) -> Dict:
        """同步停止的内部实现（在新的事件循环中运行）"""
        return await self.async_stop_worker(worker_id)

    def restart_worker(self, worker_id: int) -> Dict:
        """
        重启 Worker（先停后启）

        Args:
            worker_id: Worker ID

        Returns:
            dict: 重启结果
        """
        self._ensure_initialized()

        logger.info(f"[WorkerSystem] 正在重启 Worker {worker_id}")

        try:
            stop_result = self.sync_stop_worker(worker_id)

            import time
            time.sleep(1)

            start_result = self.sync_start_worker(worker_id)

            logger.info(f"[WorkerSystem] Worker {worker_id} 重启完成")
            return {
                'worker_id': worker_id,
                'stop_result': stop_result,
                'start_result': start_result,
                'message': f'Worker {worker_id} 重启完成',
            }

        except Exception as e:
            logger.error(f"[WorkerSystem] 重启 Worker {worker_id} 失败: {e}")
            raise

    # ==================== 批量操作 ====================

    async def async_start_all(self, max_concurrent: int = 3) -> List[Dict]:
        """
        异步批量启动所有停止状态的 Worker

        使用 asyncio.Semaphore 控制并发数量

        Args:
            max_concurrent: 最大并发数（默认 3）

        Returns:
            list: 结果列表（含 success/error 标记）
        """
        self._ensure_initialized()

        stopped_worker_ids = [
            worker_id
            for worker_id, config in self.workers.items()
            if config.status == 'stopped'
        ]

        if not stopped_worker_ids:
            logger.info("[WorkerSystem] 没有需要启动的 Worker（所有 Worker 都不在 stopped 状态）")
            return []

        logger.info(f"[WorkerSystem] 准备批量启动 {len(stopped_worker_ids)} 个 Worker，最大并发数: {max_concurrent}")

        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def start_with_semaphore(worker_id: int) -> Dict:
            async with semaphore:
                try:
                    result = await self.async_start_worker(worker_id)
                    return {
                        'worker_id': worker_id,
                        'success': True,
                        'result': result,
                    }
                except Exception as e:
                    logger.error(f"[WorkerSystem] 批量启动 Worker {worker_id} 失败: {e}")
                    return {
                        'worker_id': worker_id,
                        'success': False,
                        'error': str(e),
                    }

        tasks = [start_with_semaphore(wid) for wid in stopped_worker_ids]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        success_count = sum(1 for r in results if r.get('success'))
        error_count = len(results) - success_count

        logger.info(
            f"[WorkerSystem] 批量启动完成 | "
            f"总计: {len(results)} | 成功: {success_count} | 失败: {error_count}"
        )

        return results

    async def async_stop_all(self) -> List[Dict]:
        """
        异步批量停止所有运行中的 Worker

        Returns:
            list: 结果列表（含 success/error 标记）
        """
        self._ensure_initialized()

        running_worker_ids = [
            worker_id
            for worker_id, config in self.workers.items()
            if config.status in ('running', 'starting')
        ]

        if not running_worker_ids:
            logger.info("[WorkerSystem] 没有需要停止的 Worker（没有运行中的 Worker）")
            return []

        logger.info(f"[WorkerSystem] 准备批量停止 {len(running_worker_ids)} 个 Worker")

        results = []

        for worker_id in running_worker_ids:
            try:
                result = await self.async_stop_worker(worker_id)
                results.append({
                    'worker_id': worker_id,
                    'success': True,
                    'result': result,
                })
            except Exception as e:
                logger.error(f"[WorkerSystem] 批量停止 Worker {worker_id} 失败: {e}")
                results.append({
                    'worker_id': worker_id,
                    'success': False,
                    'error': str(e),
                })

        success_count = sum(1 for r in results if r.get('success'))
        error_count = len(results) - success_count

        logger.info(
            f"[WorkerSystem] 批量停止完成 | "
            f"总计: {len(results)} | 成功: {success_count} | 失败: {error_count}"
        )

        return results

    def get_summary(self) -> Dict:
        """
        获取系统摘要信息

        Returns:
            dict: {
                total_workers: int,
                status_breakdown: Dict[str, int],
                is_initialized: bool,
            }
        """
        status_breakdown: Dict[str, int] = {}

        for config in self.workers.values():
            status = config.status
            status_breakdown[status] = status_breakdown.get(status, 0) + 1

        return {
            'total_workers': len(self.workers),
            'status_breakdown': status_breakdown,
            'is_initialized': self._fully_initialized,
        }


# 文件末尾创建全局单例
worker_system = WorkerSystem.get_instance()
