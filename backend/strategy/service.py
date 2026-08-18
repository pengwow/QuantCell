"""策略模块服务层

实现策略的加载、管理和解析功能。

主要功能:
    - 策略文件管理
    - 策略加载和解析
    - 策略列表获取
    - 策略详情获取
    - 策略文件上传

支持两种策略类型：
- 规则策略：实现 on_bar(bar) → Action 的 Python 类
- RL 策略：使用 axon_quant.rl.TradingEnv 的训练/推理流程

服务类:
    - StrategyService: 策略服务主类

作者: QuantCell Team
版本: 1.2.0
日期: 2026-08-13
"""

import ast
import importlib.util
import sys
import uuid
from pathlib import Path

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)
from datetime import datetime
from enum import Enum
from typing import Any

# 导入事件驱动策略基类
from backtest.strategies.event_strategy import (
    EventDrivenStrategy,
)

# 导入统一的AST解析工具
# 导入策略基类（从 strategy.core 统一导入）
from .core import StrategyBase

# 策略基类别名，用于兼容性检查
Strategy = StrategyBase


class StrategyType(Enum):
    """策略类型枚举"""

    LEGACY = "legacy"  # Legacy 策略 (StrategyBase)
    EVENT_DRIVEN = "event_driven"  # 事件驱动策略 (EventDrivenStrategy)
    UNKNOWN = "unknown"  # 未知类型

    RULE = "rule"
    RL = "rl"


class StrategyService:
    """策略服务类"""

    def __init__(self):
        self.strategy_dir = Path(__file__).parent.parent / "strategies"
        self.strategy_dir.mkdir(parents=True, exist_ok=True)
        self.strategy_instances: dict[str, Any] = {}

    def list_strategies(self) -> list[dict[str, Any]]:
        """列出所有策略文件"""
        strategies = []
        for file_path in self.strategy_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                info = self._parse_strategy_file(file_path.stem, content)
                if info:
                    strategies.append(info)
            except Exception as e:
                logger.warning(f"解析策略文件失败 {file_path.name}: {e}")
        return strategies

    def get_strategy(self, name: str) -> dict[str, Any] | None:
        """获取单个策略详情"""
        file_path = self.strategy_dir / f"{name}.py"
        if not file_path.exists():
            return None
        content = file_path.read_text(encoding="utf-8")
        info = self._parse_strategy_file(name, content)
        if info:
            info["code"] = content
        return info

    def save_strategy(self, name: str, content: str) -> dict[str, Any]:
        """保存策略文件"""
        file_path = self.strategy_dir / f"{name}.py"
        file_path.write_text(content, encoding="utf-8")
        info = self._parse_strategy_file(name, content)
        logger.info(f"策略已保存: {name}")
        return info or {"name": name, "file_name": f"{name}.py"}

    def delete_strategy(self, name: str) -> bool:
        """删除策略文件"""
        file_path = self.strategy_dir / f"{name}.py"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"策略已删除: {name}")
            return True
        return False

    def load_strategy_instance(self, name: str) -> Any:
        """加载策略实例"""
        file_path = self.strategy_dir / f"{name}.py"
        if not file_path.exists():
            return None

        # 通过分析策略文件内容，判断是 Legacy 风格还是事件驱动策略。
        spec = importlib.util.spec_from_file_location(name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "on_bar")
                and not attr_name.startswith("_")
                and attr_name not in ("RuleStrategy", "ABC")
            ):
                return attr()

    def _detect_strategy_type_from_content(self, file_content: str) -> StrategyType:
        """
        通过分析策略文件内容，判断是 Legacy 风格还是事件驱动策略。

        返回:
            StrategyType: 策略类型 (LEGACY, EVENT_DRIVEN, 或 UNKNOWN)
        """
        try:
            tree = ast.parse(file_content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        base_name = None

                        # 直接继承，如 class MyStrategy(Strategy)
                        if isinstance(base, ast.Name):
                            base_name = base.id
                        # 属性继承
                        elif isinstance(base, ast.Attribute):
                            base_name = base.attr

                        if base_name and base_name in ("StrategyBase", "Strategy"):
                            # 检查是否从 strategy_base 或 strategy 模块导入
                            for stmt in ast.walk(tree):
                                if isinstance(stmt, ast.ImportFrom):
                                    if stmt.module and "strategy_base" in stmt.module:
                                        logger.info(f"检测到 Legacy 策略: {node.name}")
                                        return StrategyType.LEGACY
                                    # 检查相对导入
                                    if stmt.module is None or "." in str(stmt.module):
                                        for alias in stmt.names:
                                            if alias.name in (
                                                "StrategyBase",
                                                "Strategy",
                                            ):
                                                logger.info(f"检测到 Legacy 策略: {node.name}")
                                                return StrategyType.LEGACY
                        elif base_name and base_name in (
                            "EventDrivenStrategy",
                            "EventDrivenStrategyConfig",
                        ):
                            # 检测事件驱动策略
                            logger.info(f"检测到 Event Driven 策略: {node.name}")
                            return StrategyType.EVENT_DRIVEN

            # 如果通过 AST 无法确定，尝试通过文本内容判断
            if "StrategyBase" in file_content:
                logger.info("通过文本内容检测到 Legacy 策略")
                return StrategyType.LEGACY
            if "EventDrivenStrategy" in file_content:
                logger.info("通过文本内容检测到 Event Driven 策略")
                return StrategyType.EVENT_DRIVEN

            logger.warning("无法识别策略类型")
            return StrategyType.UNKNOWN

        except Exception as e:
            logger.error(f"检测策略类型失败: {e}")
            return StrategyType.UNKNOWN

    def _find_strategy_class(self, module, strategy_name):
        """
        在模块中查找策略类
        """
        for name, cls in module.__dict__.items():
            if isinstance(cls, type):
                # 检查是否继承自Strategy或StrategyBase或EventDrivenStrategy
                # 注意：这里需要确保基类在当前作用域可用
                is_strategy = False
                try:
                    if issubclass(cls, Strategy) and cls != Strategy:
                        is_strategy = True
                except TypeError:
                    pass

                try:
                    if issubclass(cls, StrategyBase) and cls != StrategyBase:
                        is_strategy = True
                except TypeError:
                    pass

                try:
                    if issubclass(cls, EventDrivenStrategy) and cls != EventDrivenStrategy:
                        is_strategy = True
                except TypeError:
                    pass

                if is_strategy:
                    logger.info(f"成功加载策略类: {strategy_name}.{name}")
                    return cls
        return None

    def detect_strategy_type(self, content: str) -> str:
        """检测策略类型"""
        # 源码级检测
        rl_indicators = ["TradingEnv", "stable_baselines3", "model.predict", "from rl."]
        for indicator in rl_indicators:
            if indicator in content:
                return StrategyType.RL
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "rl" in alias.name.lower():
                            return StrategyType.RL
                if isinstance(node, ast.ImportFrom) and node.module and "rl" in node.module.lower():
                    return StrategyType.RL
        except SyntaxError:
            pass
        return StrategyType.RULE

    def _parse_strategy_file(self, name: str, content: str) -> dict[str, Any] | None:
        """解析策略文件，提取信息"""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        strategy_class = None
        docstring = ""
        params = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for arg in item.args.args:
                            if arg.arg != "self":
                                param_info = {
                                    "name": arg.arg,
                                    "type": "Any",
                                    "default": None,
                                    "description": "",
                                    "required": True,
                                }
                                params.append(param_info)
                strategy_class = node.name
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                docstring = node.value.value

        strategy_type = self.detect_strategy_type(content)

        return {
            "name": name,
            "file_name": f"{name}.py",
            "file_path": str(self.strategy_dir / f"{name}.py"),
            "description": docstring[:200] if docstring else "",
            "version": "1.0.0",
            "tags": [],
            "params": params,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "source": "files",
            "strategy_type": strategy_type,
            "strategy_class": strategy_class,
        }

    def _detect_strategy_type_from_class(self, strategy_cls):
        """
        通过分析策略类的继承关系，判断是 Legacy 风格还是事件驱动策略。

        参数:
            strategy_cls: 已加载的策略类

        返回:
            StrategyType: 策略类型
        """
        if issubclass(strategy_cls, EventDrivenStrategy):
            return StrategyType.EVENT_DRIVEN
        if issubclass(strategy_cls, StrategyBase):
            return StrategyType.LEGACY
        else:
            return StrategyType.UNKNOWN

    def load_legacy_strategy(
        self,
        strategy_name: str,
        file_path: Path | None = None,
        file_content: str | None = None,
    ) -> type[Any] | None:
        """
        加载 Legacy 格式的策略 (StrategyBase)

        参数:
            strategy_name: 策略名称
            file_path: 策略文件路径（可选）
            file_content: 策略文件内容（可选）

        返回:
            Optional[Type[Any]]: 策略类，如果加载失败返回 None
        """
        try:
            if file_path and file_path.exists():
                logger.info(f"从文件加载 Legacy 策略: {strategy_name}")
                spec = importlib.util.spec_from_file_location(strategy_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[strategy_name] = module
                    spec.loader.exec_module(module)

                    strategy_cls = self._find_strategy_class(module, strategy_name)
                    if strategy_cls:
                        return strategy_cls

            elif file_content:
                logger.info(f"从内容加载 Legacy 策略: {strategy_name}")
                # 创建临时模块
                module = type(sys)(strategy_name)
                module.__file__ = str(file_path or self.strategy_dir / f"{strategy_name}.py")
                sys.modules[strategy_name] = module
                exec(file_content, module.__dict__)

                strategy_cls = self._find_strategy_class(module, strategy_name)
                if strategy_cls:
                    return strategy_cls

            logger.error("加载 Legacy 策略失败: 未提供有效的文件路径或内容")
            return None

        except Exception as e:
            logger.error(f"加载 Legacy 策略失败: {strategy_name}, 错误: {e}")
            logger.exception(e)
            return None

    def load_strategy(self, strategy_name) -> type[Any] | None:
        """
        从文件或数据库中加载策略类

        自动检测策略类型并加载 Legacy 策略，返回统一的策略接口。

        参数:
            strategy_name: 策略名称

        返回:
            Optional[Type[Any]]: 策略类，如果加载失败返回 None
        """
        try:
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            file_content = None

            # 1. 尝试从文件获取内容
            if strategy_file.exists():
                try:
                    with open(strategy_file, encoding="utf-8") as f:
                        file_content = f.read()
                    logger.info(f"从文件读取策略内容: {strategy_name}")
                except Exception as e:
                    logger.warning(f"从文件读取策略内容失败: {e}")

            # 2. 如果文件不存在，尝试从数据库获取内容
            if not file_content:
                logger.info(f"尝试从数据库获取策略内容: {strategy_name}")
                try:
                    from strategy.models import Strategy as StrategyModel
                    from utils.db_session import get_db_session

                    with get_db_session() as db:
                        strategy = db.query(StrategyModel).filter_by(name=strategy_name).first()
                        if strategy and strategy.content:
                            file_content = strategy.content
                            logger.info(f"从数据库获取策略内容成功: {strategy_name}")
                        else:
                            logger.error(f"数据库中未找到策略或策略内容为空: {strategy_name}")
                            return None
                except Exception as db_e:
                    logger.error(f"从数据库获取策略内容失败: {db_e}")
                    return None

            # 3. 检测策略类型
            strategy_type = self.detect_strategy_type(file_content)
            logger.info(f"策略类型检测结果: {strategy_name} -> {strategy_type.value}")

            # 4. 根据策略类型路由到加载器（统一使用 Legacy 加载器，未知类型和事件驱动也走该路径）
            if (
                strategy_type == StrategyType.LEGACY
                or strategy_type == StrategyType.EVENT_DRIVEN
                or strategy_type == StrategyType.UNKNOWN
            ):
                if strategy_type == StrategyType.UNKNOWN:
                    logger.warning(f"策略类型未知，尝试使用 Legacy 加载器: {strategy_name}")
                if strategy_type == StrategyType.EVENT_DRIVEN:
                    logger.info(f"事件驱动策略，使用加载器加载: {strategy_name}")
                return self.load_legacy_strategy(
                    strategy_name,
                    file_path=strategy_file if strategy_file.exists() else None,
                    file_content=file_content,
                )

        except Exception as e:
            logger.error(f"加载策略失败: {strategy_name}, 错误: {e}")
            logger.exception(e)
            return None

    def create_strategy_instance(self, strategy_name: str, params: dict[str, Any] | None = None) -> str:
        """
        创建策略实例

        :param strategy_name: 策略名称
        :param params: 策略参数
        :return: 策略实例ID
        """
        try:
            # 加载策略类
            strategy_cls = self.load_strategy(strategy_name)
            if not strategy_cls:
                logger.error(f"加载策略类失败: {strategy_name}")
                return ""

            # 创建策略实例
            params = params or {}
            strategy_instance = strategy_cls(params)

            # 生成实例ID
            instance_id = f"{strategy_name}-{uuid.uuid4()}"

            # 缓存策略实例
            self.strategy_instances[instance_id] = {
                "instance": strategy_instance,
                "strategy_name": strategy_name,
                "params": params,
                "created_at": datetime.now(),
                "status": "created",
            }

            logger.info(f"创建策略实例成功: {instance_id}")
            return instance_id
        except Exception as e:
            logger.error(f"创建策略实例失败: {e}")
            logger.exception(e)
            return ""

    def get_strategy_instance(self, instance_id: str) -> Any | None:
        """
        获取策略实例

        :param instance_id: 策略实例ID
        :return: 策略实例，如果不存在返回None
        """
        try:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return None

            return self.strategy_instances[instance_id]["instance"]
        except Exception as e:
            logger.error(f"获取策略实例失败: {e}")
            logger.exception(e)
            return None

    def delete_strategy_instance(self, instance_id: str) -> bool:
        """
        删除策略实例

        :param instance_id: 策略实例ID
        :return: 是否删除成功
        """
        try:
            if instance_id in self.strategy_instances:
                # 停止策略实例
                instance_info = self.strategy_instances[instance_id]
                instance = instance_info["instance"]
                if hasattr(instance, "stop"):
                    instance.stop()

                # 删除策略实例
                del self.strategy_instances[instance_id]
                logger.info(f"删除策略实例成功: {instance_id}")
                return True

            logger.error(f"策略实例不存在: {instance_id}")
            return False
        except Exception as e:
            logger.error(f"删除策略实例失败: {e}")
            logger.exception(e)
            return False

    def get_strategy_instances(self) -> list[dict[str, Any]]:
        """
        获取所有策略实例

        :return: 策略实例列表
        """
        try:
            instances = []
            for instance_id, instance_info in self.strategy_instances.items():
                instances.append(
                    {
                        "instance_id": instance_id,
                        "strategy_name": instance_info["strategy_name"],
                        "params": instance_info["params"],
                        "created_at": instance_info["created_at"],
                        "status": instance_info["status"],
                    }
                )

            logger.info(f"获取策略实例列表成功，共 {len(instances)} 个实例")
            return instances
        except Exception as e:
            logger.error(f"获取策略实例列表失败: {e}")
            logger.exception(e)
            return []

    def execute_strategy(
        self,
        strategy_name: str,
        params: dict[str, Any],
        mode: str = "backtest",
        backtest_config: dict[str, Any] | None = None,
    ) -> str:
        """
        执行策略

        :param strategy_name: 策略名称
        :param params: 策略参数
        :param mode: 执行模式，backtest或live
        :param backtest_config: 回测配置
        :return: 执行ID
        """
        try:
            # 创建策略实例
            instance_id = self.create_strategy_instance(strategy_name, params)
            if not instance_id:
                logger.error(f"创建策略实例失败: {strategy_name}")
                return ""

            # 获取策略实例
            strategy_instance = self.get_strategy_instance(instance_id)
            if not strategy_instance:
                logger.error(f"获取策略实例失败: {instance_id}")
                return ""

            # 导入执行引擎
            from .execution_engine import ExecutionEngineFactory

            # 创建执行引擎
            engine = ExecutionEngineFactory.create_engine(mode)
            engine.set_strategy(strategy_instance)

            # 设置执行参数
            engine.set_params(params)

            # 如果是回测模式，设置回测参数
            if mode == "backtest" and backtest_config:
                engine.set_backtest_params(
                    initial_capital=backtest_config.get("initial_capital", 100000.0),
                    commission=backtest_config.get("commission", 0.0),
                    slippage=backtest_config.get("slippage", 0.0),
                )
                # TODO: 设置回测数据
                # 从数据服务获取回测数据
                # engine.set_backtest_data(data)

            # 记录执行状态
            execution_id = engine.execution_id
            self.strategy_executions[execution_id] = {
                "execution_id": execution_id,
                "strategy_name": strategy_name,
                "instance_id": instance_id,
                "params": params,
                "mode": mode,
                "backtest_config": backtest_config,
                "status": "running",
                "started_at": datetime.now(),
                "result": None,
                "engine": engine,
            }

            # 启动执行引擎（异步）
            import threading

            thread = threading.Thread(target=engine.start)
            thread.daemon = True
            thread.start()

            logger.info(f"执行策略成功，执行ID: {execution_id}")
            return execution_id
        except Exception as e:
            logger.error(f"执行策略失败: {e}")
            logger.exception(e)
            return ""

    def get_execution_status(self, execution_id: str) -> dict[str, Any] | None:
        """
        获取策略执行状态

        :param execution_id: 执行ID
        :return: 执行状态信息
        """
        try:
            if execution_id not in self.strategy_executions:
                logger.error(f"执行ID不存在: {execution_id}")
                return None

            execution_info = self.strategy_executions[execution_id]

            # 如果执行引擎存在，获取最新状态
            if "engine" in execution_info:
                engine = execution_info["engine"]
                # 更新状态和结果
                execution_info["status"] = engine.status
                execution_info["result"] = engine.results

                if engine.end_time:
                    execution_info["ended_at"] = engine.end_time

            return execution_info
        except Exception as e:
            logger.error(f"获取执行状态失败: {e}")
            logger.exception(e)
            return None

    def stop_execution(self, execution_id: str) -> bool:
        """
        停止策略执行

        :param execution_id: 执行ID
        :return: 是否停止成功
        """
        try:
            if execution_id not in self.strategy_executions:
                logger.error(f"执行ID不存在: {execution_id}")
                return False

            # 获取执行信息
            execution_info = self.strategy_executions[execution_id]
            instance_id = execution_info["instance_id"]

            # 停止策略实例
            if instance_id in self.strategy_instances:
                instance = self.strategy_instances[instance_id]["instance"]
                if hasattr(instance, "stop"):
                    instance.stop()

            # 更新执行状态
            execution_info["status"] = "stopped"
            execution_info["stopped_at"] = datetime.now()

            logger.info(f"停止策略执行成功: {execution_id}")
            return True
        except Exception as e:
            logger.error(f"停止策略执行失败: {e}")
            logger.exception(e)
            return False

    def upload_strategy_file(
        self,
        strategy_name: str,
        file_content: str,
        version: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        id: int | None = None,
        params: list[dict] | None = None,
    ) -> bool:
        """
        上传策略文件

        :param strategy_name: 策略名称
        :param file_content: 文件内容
        :param version: 策略版本（可选），如果提供则使用，否则从文件内容中提取
        :param description: 策略描述（可选），如果提供则使用，否则从文件内容中提取
        :param tags: 策略标签（可选）
        :param id: 策略ID（可选），如果提供则更新现有策略，否则根据策略名称判断
        :param params: 策略参数列表（可选），如果提供则优先使用
        :return: 是否上传成功
        """
        try:
            # 保存策略文件
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            with open(strategy_file, "w") as f:
                f.write(file_content)

            logger.info(f"策略文件上传成功: {strategy_file}")

            # 将策略信息保存到数据库
            import json

            from strategy.models import Strategy
            from utils.db_session import get_db_session

            with get_db_session() as db:
                try:
                    # 检查策略是否已存在
                    logger.info(f"检查策略是否已存在: id={id}, name={strategy_name}")
                    existing_strategy = None
                    if id:
                        # 如果提供了id，根据id查询
                        existing_strategy = db.query(Strategy).filter_by(id=id).first()
                    else:
                        # 否则根据策略名称查询
                        existing_strategy = db.query(Strategy).filter_by(name=strategy_name).first()
                    logger.info(f"现有策略: {existing_strategy}")

                    # 初始化基本策略信息
                    strategy_info = {
                        "name": strategy_name,
                        "file_name": f"{strategy_name}.py",
                        "description": description or "",
                        "version": version or "1.0.0",
                        "tags": tags or [],
                        "params": params or [],  # 如果传入了params，优先使用
                    }

                    # 如果没有传入params，尝试解析策略内容提取参数
                    if not params:
                        try:
                            parsed_info = self._parse_strategy_content(file_content, strategy_name)
                            if parsed_info:
                                # 只有当 description 为 None 时才使用解析的描述，空字符串应该被保留
                                if description is None:
                                    strategy_info["description"] = parsed_info["description"]
                                else:
                                    strategy_info["description"] = description
                                strategy_info["params"] = parsed_info["params"]
                                # 如果没有提供tags，保留默认空列表；如果提供了tags，使用提供的
                                if not tags and "tags" in parsed_info:
                                    strategy_info["tags"] = parsed_info["tags"]
                                logger.info("策略解析成功，使用解析的信息")
                            else:
                                logger.info("策略解析失败，使用默认信息")
                        except Exception as parse_e:
                            logger.error(f"解析策略内容失败: {parse_e}")
                            logger.exception(parse_e)
                    else:
                        logger.info(f"使用传入的参数列表，跳过解析: {params}")

                    # 准备参数JSON
                    params_json = json.dumps(strategy_info["params"]) if strategy_info["params"] else None
                    tags_json = json.dumps(strategy_info["tags"]) if strategy_info["tags"] else None
                    logger.info(f"准备保存的参数: {params_json}")

                    if existing_strategy:
                        # 更新现有策略
                        logger.info(f"更新现有策略: id={id}, name={strategy_name}")
                        existing_strategy.name = strategy_name
                        existing_strategy.filename = strategy_info["file_name"]
                        existing_strategy.content = file_content  # 保存策略内容到数据库
                        existing_strategy.description = strategy_info["description"]
                        existing_strategy.parameters = params_json
                        existing_strategy.tags = tags_json
                        existing_strategy.version = strategy_info["version"]
                        # 不需要手动设置updated_at，模型已配置onupdate=func.now()
                        logger.info(f"更新策略信息到数据库: {strategy_name}")
                    else:
                        # 创建新策略
                        logger.info(f"创建新策略: {strategy_name}")
                        new_strategy = Strategy(
                            name=strategy_name,
                            filename=strategy_info["file_name"],
                            content=file_content,  # 保存策略内容到数据库
                            description=strategy_info["description"],
                            parameters=params_json,
                            tags=tags_json,
                            version=strategy_info["version"],
                        )
                        logger.info(f"新策略对象: {new_strategy}")
                        db.add(new_strategy)
                        logger.info(f"保存策略信息到数据库: {strategy_name}")

                    # 提交事务
                    logger.info(f"提交事务: {strategy_name}")
                    db.commit()
                    logger.info(f"策略信息保存到数据库成功: {strategy_name}")
                except Exception as db_e:
                    db.rollback()
                    logger.error(f"保存策略信息到数据库失败: {db_e}")
                    logger.exception(db_e)

            return True
        except Exception as e:
            logger.error(f"策略文件上传失败: {e}")
            logger.exception(e)
            return False

    def delete_strategy_file(self, strategy_name: str) -> bool:
        """
        删除策略文件

        :param strategy_name: 策略名称
        :return: 是否删除成功
        """
        try:
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.error(f"策略文件不存在: {strategy_file}")
                return False

            strategy_file.unlink()
            logger.info(f"策略文件删除成功: {strategy_file}")
            return True
        except Exception as e:
            logger.error(f"策略文件删除失败: {e}")
            logger.exception(e)
            return False

    def delete_strategy(self, strategy_name: str, strategy_id: int | None = None) -> bool:
        """
        删除策略，包括策略文件和数据库记录

        :param strategy_name: 策略名称
        :param strategy_id: 策略ID（可选）
        :return: 是否删除成功
        """
        try:
            logger.info(f"开始删除策略: name={strategy_name}, id={strategy_id}")

            # 1. 删除策略文件
            delete_file_success = self.delete_strategy_file(strategy_name)
            if not delete_file_success:
                logger.warning(f"策略文件删除失败，但继续尝试删除数据库记录: {strategy_name}")

            # 2. 从数据库中删除策略记录
            try:
                from strategy.models import Strategy
                from utils.db_session import get_db_session

                with get_db_session() as db:
                    try:
                        # 构建查询条件
                        query = db.query(Strategy)
                        if strategy_id:
                            # 如果提供了ID，优先使用ID查询
                            query = query.filter_by(id=strategy_id)
                        else:
                            # 否则使用策略名称查询
                            query = query.filter_by(name=strategy_name)

                        # 执行删除
                        deleted_count = query.delete()

                        if deleted_count > 0:
                            logger.info(f"从数据库中删除策略成功，删除了 {deleted_count} 条记录")
                            db.commit()
                        else:
                            logger.warning(f"数据库中未找到要删除的策略: name={strategy_name}, id={strategy_id}")
                    except Exception as db_e:
                        db.rollback()
                        logger.error(f"从数据库中删除策略失败: {db_e}")
                        logger.exception(db_e)
                        return False
            except Exception as db_import_e:
                logger.error(f"导入数据库模块失败: {db_import_e}")
                logger.exception(db_import_e)
                # 如果数据库操作失败，但文件已删除，仍返回成功
                return delete_file_success

            logger.info(f"删除策略成功: {strategy_name}")
            return True
        except Exception as e:
            logger.error(f"删除策略失败: {e}")
            logger.exception(e)
            return False

    def validate_strategy_params(self, strategy_name: str, params: dict[str, Any]) -> bool:
        """
        验证策略参数

        :param strategy_name: 策略名称
        :param params: 策略参数
        :return: 参数是否合法
        """
        try:
            # 获取策略详情
            strategy_info = self.get_strategy_detail(strategy_name)
            if not strategy_info:
                logger.error(f"获取策略详情失败: {strategy_name}")
                return False

            # 验证参数
            for param in strategy_info["params"]:
                param_name = param["name"]
                if param_name in params:
                    param_value = params[param_name]
                    param_type = param["type"]

                    # 验证类型
                    if param_type != "Any":
                        # 简单类型验证
                        if param_type == "int" and not isinstance(param_value, int):
                            logger.error(f"参数 {param_name} 类型错误，期望 int，实际 {type(param_value).__name__}")
                            return False
                        elif param_type == "float" and not isinstance(param_value, (int, float)):
                            logger.error(f"参数 {param_name} 类型错误，期望 float，实际 {type(param_value).__name__}")
                            return False
                        elif param_type == "str" and not isinstance(param_value, str):
                            logger.error(f"参数 {param_name} 类型错误，期望 str，实际 {type(param_value).__name__}")
                            return False
                        elif param_type == "bool" and not isinstance(param_value, bool):
                            logger.error(f"参数 {param_name} 类型错误，期望 bool，实际 {type(param_value).__name__}")
                            return False

            logger.info(f"策略参数验证成功: {strategy_name}")
            return True
        except Exception as e:
            logger.error(f"验证策略参数失败: {e}")
            logger.exception(e)
            return False

    def update_strategy_instance_params(self, instance_id: str, params: dict[str, Any]) -> bool:
        """
        更新策略实例参数

        :param instance_id: 策略实例ID
        :param params: 新的策略参数
        :return: 是否更新成功
        """
        try:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            # 获取策略实例
            instance_info = self.strategy_instances[instance_id]
            instance = instance_info["instance"]
            strategy_name = instance_info["strategy_name"]

            # 验证参数
            if not self.validate_strategy_params(strategy_name, params):
                logger.error(f"验证策略参数失败: {strategy_name}")
                return False

            # 更新参数
            if hasattr(instance, "set_params"):
                instance.set_params(params)
            else:
                # 直接更新实例属性
                for key, value in params.items():
                    setattr(instance, key, value)

            # 更新缓存
            instance_info["params"].update(params)

            logger.info(f"更新策略实例参数成功: {instance_id}")
            return True
        except Exception as e:
            logger.error(f"更新策略实例参数失败: {e}")
            logger.exception(e)
            return False

    def generate_strategy(
        self,
        prompt: str,
        model_id: int | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        使用AI模型生成策略代码

        Args:
            prompt: 策略需求描述
            model_id: AI模型配置ID
            model_name: 具体模型名称
            provider: AI厂商
            conversation_id: 对话ID

        Returns:
            Dict: 包含生成的策略代码和说明
        """
        try:
            logger.info(f"开始AI生成策略，prompt: {prompt[:50]}...")

            # 构建系统提示词
            system_prompt = """你是一个专业的量化交易策略生成助手。
请根据用户的需求生成一个完整的Python策略代码。

策略代码必须遵循以下规范：
1. 使用统一的策略接口，继承自 StrategyBase 或 StrategyConfig
2. 包含完整的配置类和策略类
3. 包含 on_start、on_bar、on_stop 等生命周期方法
4. 代码需要包含详细的中文注释
5. 支持多品种交易

生成的代码应该可以直接运行，不需要用户额外修改。"""

            # 构建用户提示词
            user_prompt = f"请根据以下需求生成一个量化交易策略：\n\n{prompt}\n\n请生成完整的Python代码，包含：\n1. 策略配置类（继承自 StrategyConfig）\n2. 策略主类（继承自 StrategyBase）\n3. 完整的交易逻辑\n4. 详细的中文注释"

            # 导入AI模型服务
            from ai_model.services import AIModelService

            # 获取AI模型适配器
            adapter = None
            if model_id:
                # 从数据库获取模型配置
                from ai_model.models import AIModelBusiness

                model_config = AIModelBusiness.get_by_id(model_id, include_api_key=True)
                if model_config:
                    adapter = AIModelService.get_adapter(
                        provider=model_config.get("provider", "openai"),
                        api_key=model_config.get("api_key", ""),
                        api_host=model_config.get("api_host"),
                    )
                    # 使用配置中的模型名称
                    if not model_name and model_config.get("models"):
                        model_name = model_config["models"][0]

            # 如果没有找到适配器，使用默认配置
            if not adapter:
                logger.warning("未找到AI模型配置，使用默认配置")
                # 这里可以设置默认的API密钥或抛出错误
                msg = "未配置AI模型，请先在模型设置中配置AI模型"
                raise ValueError(msg)

            # 调用AI模型生成策略
            # 构建消息列表
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # 调用AI模型
            response = adapter.client.chat.completions.create(
                model=model_name or "gpt-4",
                messages=messages,
                temperature=0.7,
                max_tokens=4000,
            )

            # 解析AI响应
            ai_content = response.choices[0].message.content

            # 提取代码块
            code = self._extract_code_from_markdown(ai_content)

            # 生成说明
            explanation = self._extract_explanation(ai_content)

            logger.info("AI生成策略成功")

            return {
                "code": code,
                "explanation": explanation,
                "conversation_id": conversation_id,
                "model_used": model_name or "gpt-4",
            }

        except Exception as e:
            logger.error(f"AI生成策略失败: {e}")
            logger.exception(e)
            raise

    def _extract_code_from_markdown(self, content: str) -> str:
        """
        从Markdown格式的内容中提取代码块

        Args:
            content: AI返回的完整内容

        Returns:
            str: 提取的Python代码
        """
        import re

        # 尝试提取Python代码块
        code_pattern = r"```python\n(.*?)\n```"
        matches = re.findall(code_pattern, content, re.DOTALL)

        if matches:
            return matches[0].strip()

        # 如果没有找到Python代码块，尝试提取任意代码块
        code_pattern = r"```\n(.*?)\n```"
        matches = re.findall(code_pattern, content, re.DOTALL)

        if matches:
            return matches[0].strip()

        # 如果都没有找到，返回原始内容
        return content.strip()

    def _extract_explanation(self, content: str) -> str:
        """
        从AI响应中提取说明文字（非代码部分）

        Args:
            content: AI返回的完整内容

        Returns:
            str: 提取的说明文字
        """
        import re

        # 移除代码块
        text = re.sub(r"```python\n.*?\n```", "", content, flags=re.DOTALL)
        text = re.sub(r"```\n.*?\n```", "", text, flags=re.DOTALL)

        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _parse_strategy_file(self, name: str, content: str) -> dict[str, Any] | None:
        """解析策略文件，提取信息"""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        strategy_class = None
        docstring = ""
        params = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for arg in item.args.args:
                            if arg.arg != "self":
                                param_info = {
                                    "name": arg.arg,
                                    "type": "Any",
                                    "default": None,
                                    "description": "",
                                    "required": True,
                                }
                                params.append(param_info)
                strategy_class = node.name
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                docstring = node.value.value

        strategy_type = self.detect_strategy_type(content)

        return {
            "name": name,
            "file_name": f"{name}.py",
            "file_path": str(self.strategy_dir / f"{name}.py"),
            "description": docstring[:200] if docstring else "",
            "version": "1.0.0",
            "tags": [],
            "params": params,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "source": "files",
            "strategy_type": strategy_type,
            "strategy_class": strategy_class,
        }
