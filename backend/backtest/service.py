"""
回测服务模块（FastAPI层）

提供回测任务的HTTP API服务层。
本模块只负责：
- 任务管理（创建/更新/查询/删除）
- 结果持久化（保存到文件系统）
- 进度跟踪集成
- API响应构建

所有业务逻辑已迁移到独立的服务模块：
- backtest/engine_service.py - 引擎执行逻辑
- backtest/data_provider.py - 数据加载逻辑  
- backtest/strategy_loader_service.py - 策略加载逻辑
- backtest/result_formatter_service.py - 结果格式化逻辑
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


class BacktestService:
    """
    回测服务（FastAPI薄封装）
    
    只做参数转换、错误处理和结果持久化，
    不包含任何回测业务逻辑。
    
    使用示例：
        service = BacktestService()
        task_id = service.create_task(...)
        result = service.run_backtest(task_id)
        results_list = service.get_result_list(limit=10)
    """
    
    def __init__(self):
        """初始化回测服务"""
        self.results_dir = Path(__file__).resolve().parent.parent / 'data' / 'backtest_results'
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        from utils.logger import get_logger, LogType
        self.logger = get_logger(self.__class__.__name__, LogType.APPLICATION)
    
    def create_task(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        symbols: List[str],
        timeframes: List[str],
        engine_type: str,
        config: Optional[Dict] = None,
        task_id: Any = None
    ) -> Any:
        """
        创建回测任务

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_type: 引擎类型 (default/event)
            config: 回测配置
            task_id: 可选的任务ID（如果提供则使用，否则自动生成）

        Returns:
            任务ID（与传入的 task_id 相同类型，或生成的整数）
        """
        if task_id is None:
            task_id = int(datetime.now().timestamp() * 1000)
        
        task_data = {
            "id": task_id,
            "strategy_name": strategy_name,
            "strategy_params": strategy_params,
            "symbols": symbols,
            "timeframes": timeframes,
            "engine_type": engine_type,
            "config": config or {},
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        # 保存任务信息
        task_file = self._get_task_file(task_id)
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info(f"创建回测任务: {task_id}")
        
        return task_id
    
    def run_backtest(
        self,
        task_id: Any,
        progress_tracker=None
    ) -> Dict[str, Any]:
        """
        执行回测任务
        
        Args:
            task_id: 任务ID
            progress_tracker: 进度跟踪器（可选）
            
        Returns:
            dict: 回测结果
            
        Raises:
            ValueError: 当任务不存在或配置无效时
        """
        # 加载任务配置
        task = self._load_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        
        try:
            # 更新状态为运行中
            self._update_task_status(task_id, "running")

            if progress_tracker:
                # 更新数据准备阶段进度（30% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="data_prep",
                    data={
                        "progress": 100.0,
                        "status": "completed",
                        "message": "数据准备完成"
                    }
                )
                # 更新执行阶段进度（60% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="execution",
                    data={
                        "progress": 0.0,
                        "status": "running",
                        "current_symbol": task['symbols'][0] if task.get('symbols') else "",
                        "total_symbols": len(task.get('symbols', [])),
                        "completed_symbols": 0,
                        "message": "开始执行回测..."
                    }
                )
            
            # 调用引擎服务执行回测
            from backtest.data_provider import BacktestDataProvider
            from backtest.engine_service import EventDrivenBacktestService, DefaultBacktestService
            
            data_provider = BacktestDataProvider()
            
            engine_config = task.get('config', {})
            
            if task['engine_type'] == 'event':
                service = EventDrivenBacktestService(data_provider)

                raw_result = service.run_backtest(
                    strategy_name=task['strategy_name'],
                    strategy_params=task.get('strategy_params', {}),
                    symbols=task['symbols'],
                    timeframes=task['timeframes'],
                    engine_config={
                        **engine_config,
                        'log_level': 'WARNING'
                    },
                    show_progress=False
                )

                # 将引擎原始结果包装为标准响应格式
                result = {
                    'status': 'completed',
                    'message': '回测执行成功',
                    'successful_currencies': task['symbols'],
                    'failed_currencies': [],
                    'results': raw_result
                }
            else:
                service = DefaultBacktestService(data_provider)
                
                data_dict, _ = data_provider.load_multiple(
                    symbols=task['symbols'],
                    timeframes=task['timeframes']
                )
                
                if not data_dict:
                    raise ValueError("没有可用的数据")
                
                from backtest.strategy_loader_service import StrategyLoaderService
                
                strategy = StrategyLoaderService.load_strategy(
                    task['strategy_name'],
                    task.get('strategy_params', {})
                )
                
                result = service.run_backtest(
                    strategy=strategy,
                    data_dict=data_dict,
                    config=engine_config,
                    show_progress=False
                )

                # 将引擎原始结果包装为标准响应格式
                raw_result = result
                result = {
                    'status': 'completed',
                    'message': '回测执行成功',
                    'successful_currencies': task['symbols'],
                    'failed_currencies': [],
                    'results': raw_result if isinstance(raw_result, dict) else {'stats': raw_result}
                }
            
            if progress_tracker:
                # 更新执行阶段完成（60% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="execution",
                    data={
                        "progress": 100.0,
                        "status": "completed",
                        "completed_symbols": len(task.get('symbols', [])),
                        "message": "回测执行完成"
                    }
                )
                # 更新分析阶段进度（10% 权重）
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="analysis",
                    data={
                        "progress": 50.0,
                        "status": "running",
                        "message": "正在保存结果..."
                    }
                )

            # 保存结果
            self._save_result(task_id, result)

            # 更新状态为完成
            self._update_task_status(task_id, "completed")

            if progress_tracker:
                # 更新分析阶段完成（10% 权重）- 总体 100%
                progress_tracker.update_progress(
                    task_id=str(task_id),
                    stage="analysis",
                    data={
                        "progress": 100.0,
                        "status": "completed",
                        "message": "回测结果已保存"
                    }
                )
                # 标记整个任务为已完成状态，确保前端轮询能够正确停止
                progress_tracker.complete_progress(task_id)
            
            return result
            
        except Exception as e:
            self.logger.error(f"回测执行失败: {e}")
            self._update_task_status(task_id, "failed")
            raise
    
    def get_result(self, result_id: Any) -> Optional[Dict]:
        """
        获取单个回测结果

        Args:
            result_id: 结果ID（即任务ID）

        Returns:
            dict or None: 回测结果
        """
        result_file = self._get_result_file(result_id)
        
        if not result_file.exists():
            return None
        
        with open(result_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_latest_result(self) -> Optional[Dict]:
        """获取最新的回测结果"""
        results_files = sorted(
            list(self.results_dir.glob('result_*.json')),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        if not results_files:
            return None
        
        latest_file = results_files[0]
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_backtest_symbols(self, backtest_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取可用的回测货币对列表

        扫描数据目录，返回所有有数据的货币对及其可用的时间周期

        Args:
            backtest_id: 可选的回测ID（兼容路由参数，实际不使用）

        Returns:
            dict: 标准响应格式 {
                "status": "success",
                "data": [货币对列表]
            }
        """
        from pathlib import Path
        import os

        symbols = []

        try:
            # 获取数据源目录
            source_dir = Path(__file__).parent.parent / 'data' / 'source' / 'crypto' / 'spot' / 'klines'

            if not source_dir.exists():
                self.logger.warning(f"数据目录不存在: {source_dir}")
                return {"status": "success", "data": symbols}

            # 遍历所有时间周期目录
            for interval_dir in sorted(source_dir.iterdir()):
                if not interval_dir.is_dir():
                    continue

                interval = interval_dir.name  # 如 "15m", "1h"

                # 遍历该周期下的所有 parquet 文件
                for data_file in sorted(interval_dir.glob('*.parquet')):
                    symbol = data_file.stem  # 文件名即货币对（如 ETHUSDT）

                    # 检查是否已在列表中
                    existing = next((s for s in symbols if s['symbol'] == symbol), None)
                    if existing:
                        if interval not in existing['intervals']:
                            existing['intervals'].append(interval)
                        continue

                    # 获取文件信息
                    stat = data_file.stat()
                    data_count = 0

                    try:
                        import pandas as pd
                        df = pd.read_parquet(data_file, columns=[])
                        data_count = len(df)
                    except Exception:
                        pass

                    symbols.append({
                        'symbol': symbol,
                        'intervals': [interval],
                        'data_count': data_count,
                        'last_update': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'file_size': stat.st_size
                    })

            self.logger.info(f"扫描到 {len(symbols)} 个可回测的货币对")

        except Exception as e:
            self.logger.error(f"获取回测货币对列表失败: {e}")

        return {
            "status": "success",
            "data": symbols
        }

    def get_result_list(
        self,
        limit: int = 20,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        获取回测结果列表
        
        Args:
            limit: 返回数量限制
            offset: 偏移量
            status_filter: 状态过滤 (pending/running/completed/failed)
            
        Returns:
            list: 任务列表
        """
        tasks_dir = self.results_dir.parent / 'backtest_tasks'
        if not tasks_dir.exists():
            return []
        
        task_files = sorted(
            list(tasks_dir.glob('task_*.json')),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        results = []
        
        for task_file in task_files[offset:]:
            if len(results) >= limit:
                break
            
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)
                
            if status_filter and task.get('status') != status_filter:
                continue
            
            results.append({
                'id': task.get('id'),
                'strategy_name': task.get('strategy_name'),
                'symbols': ', '.join(task.get('symbols', [])),
                'timeframes': ', '.join(task.get('timeframes', [])),
                'engine_type': task.get('engine_type'),
                'status': task.get('status'),
                'created_at': task.get('created_at'),
                'updated_at': task.get('updated_at'),
            })
        
        return results
    
    def delete_task(self, task_id: Any) -> bool:
        """
        删除回测任务及其结果

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功删除
        """
        task_file = self._get_task_file(task_id)
        result_file = self._get_result_file(task_id)

        deleted = False

        if task_file.exists():
            task_file.unlink()
            deleted = True

        if result_file.exists():
            result_file.unlink()
            deleted = True

        if deleted:
            self.logger.info(f"删除回测任务: {task_id}")

        return deleted

    def delete_backtest_result(self, backtest_id: str) -> bool:
        """
        删除回测结果（路由层兼容接口）

        Args:
            backtest_id: 回测ID

        Returns:
            bool: 是否成功删除
        """
        try:
            task_id = int(backtest_id) if backtest_id.isdigit() else backtest_id
        except (ValueError, AttributeError):
            task_id = backtest_id
        return self.delete_task(task_id)

    def stop_backtest(self, task_id: str) -> Dict[str, Any]:
        """
        终止回测任务

        Args:
            task_id: 任务ID

        Returns:
            dict: 终止结果
        """
        try:
            numeric_id = int(task_id) if task_id.isdigit() else task_id
        except (ValueError, AttributeError):
            numeric_id = task_id

        task = self._load_task(numeric_id)
        if not task:
            return {"status": "error", "message": "回测任务不存在"}

        if task.get("status") not in ("running", "pending"):
            return {"status": "error", "message": "回测任务不在运行中"}

        self._update_task_status(numeric_id, "stopped")
        return {"status": "success", "message": "回测已终止"}

    def analyze_backtest(self, backtest_id: str) -> Dict[str, Any]:
        """
        分析回测结果

        Args:
            backtest_id: 回测ID

        Returns:
            dict: 分析结果
        """
        try:
            result_id = int(backtest_id) if backtest_id.isdigit() else backtest_id
        except (ValueError, AttributeError):
            result_id = backtest_id

        result = self.get_result(result_id)
        if not result:
            return {"status": "error", "message": "回测结果不存在"}

        return {
            "status": "success",
            "metrics": result.get("results", {}).get("stats", {}),
            "trades": [],
            "equity_curve": [],
        }

    def get_replay_data(self, backtest_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取回测回放数据

        Args:
            backtest_id: 回测ID
            symbol: 可选，指定货币对

        Returns:
            dict: 回放数据
        """
        try:
            result_id = int(backtest_id) if backtest_id.isdigit() else backtest_id
        except (ValueError, AttributeError):
            result_id = backtest_id

        result = self.get_result(result_id)
        if not result:
            return {"status": "error", "message": "回测不存在"}

        return {
            "status": "success",
            "data": {
                "kline_data": [],
                "trade_signals": [],
                "equity_data": [],
            },
        }

    def upload_strategy_file(self, strategy_name: str, file_content: str) -> bool:
        """
        上传策略文件

        Args:
            strategy_name: 策略名称
            file_content: 策略文件内容

        Returns:
            bool: 是否上传成功
        """
        strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)

        file_path = strategies_dir / f"{strategy_name}.py"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            self.logger.info(f"策略文件已保存: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存策略文件失败: {e}")
            return False
    
    def _load_task(self, task_id: Any) -> Optional[Dict]:
        """加载任务配置"""
        task_file = self._get_task_file(task_id)

        if not task_file.exists():
            return None

        with open(task_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _update_task_status(self, task_id: Any, status: str):
        """更新任务状态"""
        task = self._load_task(task_id)
        if task:
            task['status'] = status
            task['updated_at'] = datetime.now().isoformat()

            task_file = self._get_task_file(task_id)
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False, default=str)

    def _save_result(self, task_id: Any, result: Dict):
        """保存回测结果"""
        result_file = self._get_result_file(task_id)

        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)

        self.logger.info(f"保存回测结果: {result_file}")

    def _get_task_file(self, task_id: Any) -> Path:
        """获取任务文件路径"""
        tasks_dir = self.results_dir.parent / 'backtest_tasks'
        tasks_dir.mkdir(parents=True, exist_ok=True)
        return tasks_dir / f'task_{task_id}.json'

    def _get_result_file(self, result_id: Any) -> Path:
        """获取结果文件路径"""
        return self.results_dir / f'result_{result_id}.json'
