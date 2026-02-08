# 策略服务
# 实现策略的加载、获取列表等功能

import sys
import os
import importlib.util
import ast
import inspect
import uuid
from pathlib import Path
from loguru import logger
from backtesting import Strategy
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

# 导入策略基类
from .strategy_base import StrategyBase

class StrategyService:
    """
    策略服务类，用于管理和加载策略
    """
    
    def __init__(self):
        """初始化策略服务"""
        # 策略存储路径 - 后端代码第一层的strategies目录
        self.strategy_dir = Path(__file__).parent.parent / "strategies"
        self.strategy_dir.mkdir(parents=True, exist_ok=True)
        
        # 策略实例缓存
        self.strategy_instances: Dict[str, Any] = {}
        
        # 策略执行状态
        self.strategy_executions: Dict[str, Dict[str, Any]] = {}
        
        # logger.debug(f"策略服务初始化成功，策略目录: {self.strategy_dir}")
    
    def _parse_strategy_content(self, file_content, strategy_name):
        """
        解析策略文件内容，提取策略信息
        
        :param file_content: 策略文件内容
        :param strategy_name: 策略名称
        :return: 策略信息字典，如果没有找到策略类则返回None
        """
        try:
            # 解析Python代码
            tree = ast.parse(file_content)
            
            # 获取文件修改时间
            file_path = self.strategy_dir / f"{strategy_name}.py"
            created_at = datetime.now()
            updated_at = datetime.now()
            
            if file_path.exists():
                try:
                    # 使用文件的修改时间
                    mtime = file_path.stat().st_mtime
                    created_at = datetime.fromtimestamp(mtime)
                    updated_at = datetime.fromtimestamp(mtime)
                except Exception as e:
                    logger.warning(f"获取文件时间失败: {e}")
            
            # 初始化策略信息
            strategy_info = {
                "name": strategy_name,
                "file_name": f"{strategy_name}.py",
                "file_path": str(file_path),
                "description": "",
                "version": "1.0.0",
                "tags": [],
                "params": [],
                "created_at": created_at,
                "updated_at": updated_at,
                "code": file_content
            }
            
            logger.info(f"开始查找策略类，代码内容: {file_content[:100]}...")
            # 查找策略类
            found_strategy_class = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    logger.info(f"找到类定义: {node.name}")
                    # 检查是否继承自Strategy或StrategyBase
                    has_strategy_base = False
                    for base in node.bases:
                        logger.info(f"检查基类: {base}")
                        if isinstance(base, ast.Name) and (base.id == 'Strategy' or base.id == 'StrategyBase'):
                            has_strategy_base = True
                            logger.info(f"找到直接继承: {base.id}")
                        elif isinstance(base, ast.Attribute) and (base.attr == 'Strategy' or base.attr == 'StrategyBase'):
                            has_strategy_base = True
                            logger.info(f"找到属性继承: {base.attr}")
                    
                    if has_strategy_base:
                        found_strategy_class = True
                        logger.info(f"找到策略类: {node.name}")
                        # 提取类文档字符串
                        strategy_info["description"] = ast.get_docstring(node) or ""
                        logger.info(f"策略描述: {strategy_info['description']}")
                        
                        # 提取类属性（策略参数）
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                # 只处理简单的属性赋值
                                if len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                                    param_name = item.targets[0].id
                                    # 跳过以下划线开头的私有属性
                                    if param_name.startswith('_'):
                                        continue
                                    
                                    # 提取属性值
                                    param_default = None
                                    if isinstance(item.value, ast.Constant):
                                        param_default = item.value.value
                                    elif isinstance(item.value, ast.Num):
                                        param_default = item.value.n
                                    elif isinstance(item.value, ast.Str):
                                        param_default = item.value.s
                                    elif isinstance(item.value, ast.NameConstant):
                                        param_default = item.value.value
                                    
                                    # 提取注释
                                    param_desc = ""
                                    if hasattr(item, 'docstring') and item.docstring:
                                        param_desc = item.docstring
                                    elif hasattr(item, 'lineno'):
                                        # 查找行注释
                                        lines = file_content.split('\n')
                                        if item.lineno <= len(lines):
                                            line = lines[item.lineno - 1]
                                            comment_index = line.find('#')
                                            if comment_index != -1:
                                                param_desc = line[comment_index + 1:].strip()
                                    
                                    # 确定参数类型
                                    param_type = type(param_default).__name__ if param_default is not None else "Any"
                                    
                                    # 添加到参数列表
                                    strategy_info["params"].append({
                                        "name": param_name,
                                        "type": param_type,
                                        "default": param_default,
                                        "description": param_desc,
                                        "required": False
                                    })
            
            logger.info(f"策略类查找结果: {found_strategy_class}")
            # 只有当找到策略类时才返回策略信息
            return strategy_info if found_strategy_class else None
        except Exception as e:
            logger.error(f"解析策略内容失败: {strategy_name}, 错误: {e}")
            logger.exception(e)
            return None
    
    def _parse_strategy_file(self, file_path):
        """
        解析策略文件，提取策略信息
        
        :param file_path: 策略文件路径
        :return: 策略信息字典
        """
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # 调用解析内容方法
            strategy_info = self._parse_strategy_content(file_content, file_path.stem)
            if strategy_info:
                # 添加来源字段
                strategy_info["source"] = "files"
            return strategy_info
        except Exception as e:
            logger.error(f"解析策略文件失败: {file_path}, 错误: {e}")
            logger.exception(e)
            return None
    
    def get_strategy_list(self, source=None):
        """
        获取所有支持的策略列表
        
        :param source: 策略来源，"files"表示从实体文件获取，"db"表示从数据库表获取，None表示两者都获取
        :return: 策略列表，每个策略包含完整的策略信息，并添加source字段区分来源
        """
        try:
            strategies = []
            
            # 如果source为None或包含"files"，则从文件获取策略
            if source is None or source == "files":
                # 从策略目录中获取所有策略文件
                strategy_files = list(self.strategy_dir.glob("*.py"))
                
                # 构建策略列表，包含完整的策略信息
                for file in strategy_files:
                    if file.stem == "__init__":
                        continue
                        
                    strategy_info = self._parse_strategy_file(file)
                    if strategy_info:
                        # 移除code字段，列表接口不需要返回完整代码
                        strategy_info.pop("code")
                        # 添加source字段
                        strategy_info["source"] = "files"
                        strategies.append(strategy_info)
                
                logger.info(f"从文件获取策略列表成功，共 {len(strategies)} 个策略")
            
            # 如果source为None或包含"db"，则从数据库获取策略
            if source is None or source == "db":
                try:
                    # 从数据库表中获取策略列表
                    from collector.db.database import SessionLocal, init_database_config
                    from collector.db.models import Strategy
                    import json
                    
                    init_database_config()
                    db = SessionLocal()
                    try:
                        # 查询所有策略
                        db_strategies = db.query(Strategy).all()
                        
                        # 构建策略列表
                        db_strategies_list = []
                        for strategy in db_strategies:
                            # 安全解析tags
                            tags = []
                            if strategy.tags:
                                try:
                                    tags = json.loads(strategy.tags)
                                except json.JSONDecodeError:
                                    # 如果解析失败，可能是直接存储的字符串
                                    # 检查是否是 'demo' 这种非JSON格式的字符串
                                    logger.warning(f"解析策略标签失败: {strategy.tags}，尝试作为单个标签处理")
                                    tags = [str(strategy.tags)]
                                except Exception as e:
                                    logger.error(f"解析策略标签异常: {strategy.name}, {e}")
                                    tags = []

                            # 安全解析params
                            params = []
                            if strategy.parameters:
                                try:
                                    params = json.loads(strategy.parameters)
                                except Exception as e:
                                    logger.error(f"解析策略参数异常: {strategy.name}, {e}")
                                    params = []

                            db_strategies_list.append({
                            "name": strategy.name,
                            "file_name": strategy.filename,
                            "file_path": str(self.strategy_dir / strategy.filename),
                            "description": strategy.description or "",
                            "version": strategy.version or "1.0.0",
                            "tags": tags,
                            "params": params,
                            "created_at": strategy.created_at,
                            "updated_at": strategy.updated_at,
                            "source": "db",
                            "code": strategy.content or ""
                        })
                        
                        strategies.extend(db_strategies_list)
                        logger.info(f"从数据库获取策略列表成功，共 {len(db_strategies_list)} 个策略")
                    finally:
                        db.close()
                except ImportError:
                    logger.warning("无法导入数据库模块，跳过从数据库获取策略")
                except Exception as e:
                    logger.error(f"从数据库获取策略列表失败: {e}")
                    logger.exception(e)
            
            # 去重，优先保留数据库策略，因为数据库策略包含真实的创建时间
            strategy_dict = {}
            for strategy in strategies:
                if strategy["name"] not in strategy_dict or strategy["source"] == "db":
                    strategy_dict[strategy["name"]] = strategy
            
            final_strategies = list(strategy_dict.values())
            logger.info(f"最终获取策略列表成功，共 {len(final_strategies)} 个策略")
            return final_strategies
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            logger.exception(e)
            return []
    
    def get_strategy_detail(self, strategy_name, file_content=None):
        """
        获取单个策略的详细信息
        
        :param strategy_name: 策略名称
        :param file_content: 策略文件内容（可选），如果提供则直接解析
        :return: 策略详细信息，如果获取失败返回None
        """
        try:
            if file_content is not None:
                # 如果提供了文件内容，直接解析
                strategy_info = self._parse_strategy_content(file_content, strategy_name)
                if strategy_info:
                    # 添加来源字段
                    strategy_info["source"] = "content"
                    logger.info(f"通过内容获取策略详情成功: {strategy_name}")
                    return strategy_info
                
                logger.error(f"解析策略内容失败: {strategy_name}")
                return None
            else:
                # 首先尝试从文件获取
                strategy_file = self.strategy_dir / f"{strategy_name}.py"
                if strategy_file.exists():
                    strategy_info = self._parse_strategy_file(strategy_file)
                    if strategy_info:
                        logger.info(f"从文件获取策略详情成功: {strategy_name}")
                        return strategy_info
                    
                    logger.error(f"解析策略文件失败: {strategy_file}")
                
                # 如果文件不存在或解析失败，尝试从数据库获取
                try:
                    from collector.db.database import SessionLocal, init_database_config
                    from collector.db.models import Strategy
                    import json
                    
                    init_database_config()
                    db = SessionLocal()
                    try:
                        # 查询策略
                        strategy = db.query(Strategy).filter_by(name=strategy_name).first()
                        if strategy:
                            logger.info(f"从数据库获取策略详情: {strategy_name}")
                            # 使用数据库中的内容解析策略
                            if strategy.content:
                                strategy_info = self._parse_strategy_content(strategy.content, strategy_name)
                                if strategy_info:
                                    # 使用数据库中的版本值覆盖解析结果中的版本值
                                    strategy_info["version"] = strategy.version or "1.0.0"
                                    # 使用数据库中的创建时间和更新时间
                                    strategy_info["created_at"] = strategy.created_at
                                    strategy_info["updated_at"] = strategy.updated_at
                                    # 设置来源为db
                                    strategy_info["source"] = "db"
                                    logger.info(f"通过数据库内容获取策略详情成功: {strategy_name}")
                                    return strategy_info
                                
                            # 如果解析失败，构建基本策略信息
                            logger.info(f"构建基本策略信息: {strategy_name}")
                            return {
                                "name": strategy.name,
                                "file_name": strategy.filename,
                                "file_path": str(self.strategy_dir / strategy.filename),
                                "description": strategy.description or "",
                                "version": strategy.version or "1.0.0",
                                "params": json.loads(strategy.parameters) if strategy.parameters else [],
                                "created_at": strategy.created_at,
                                "updated_at": strategy.updated_at,
                                "code": strategy.content or "",
                                "source": "db"
                            }
                    finally:
                        db.close()
                except Exception as db_e:
                    logger.error(f"从数据库获取策略详情失败: {db_e}")
                    logger.exception(db_e)
                
                logger.error(f"获取策略详情失败: {strategy_name}")
                return None
        except Exception as e:
            logger.error(f"获取策略详情失败: {e}")
            logger.exception(e)
            return None
    
    def _find_strategy_class(self, module, strategy_name):
        """
        在模块中查找策略类
        """
        for name, cls in module.__dict__.items():
            if isinstance(cls, type):
                # 检查是否继承自Strategy或StrategyBase
                # 注意：这里需要确保Strategy和StrategyBase在当前作用域可用
                is_strategy = False
                try:
                    if (issubclass(cls, Strategy) and cls != Strategy):
                        is_strategy = True
                except TypeError:
                    pass
                
                try:
                    if (issubclass(cls, StrategyBase) and cls != StrategyBase):
                        is_strategy = True
                except TypeError:
                    pass
                    
                if is_strategy:
                    logger.info(f"成功加载策略类: {strategy_name}.{name}")
                    return cls
        return None

    def load_strategy(self, strategy_name) -> Optional[Type[Any]]:
        """
        从文件或数据库中加载策略类
        
        :param strategy_name: 策略名称
        :return: 策略类，如果加载失败返回None
        """
        try:
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            
            # 1. 尝试从文件加载
            if strategy_file.exists():
                try:
                    # 动态导入策略模块
                    spec = importlib.util.spec_from_file_location(strategy_name, strategy_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[strategy_name] = module
                        spec.loader.exec_module(module)
                        
                        strategy_cls = self._find_strategy_class(module, strategy_name)
                        if strategy_cls:
                            return strategy_cls
                except Exception as e:
                    logger.warning(f"从文件加载策略失败，尝试从数据库加载: {e}")
            
            # 2. 如果文件不存在或加载失败，尝试从数据库加载
            logger.info(f"尝试从数据库加载策略: {strategy_name}")
            
            try:
                from collector.db.database import SessionLocal, init_database_config
                from collector.db.models import Strategy as StrategyModel
                
                init_database_config()
                db = SessionLocal()
                try:
                    strategy = db.query(StrategyModel).filter_by(name=strategy_name).first()
                    if strategy and strategy.content:
                        logger.info(f"从数据库找到策略内容: {strategy_name}")
                        
                        # 动态创建模块
                        module = type(sys)(strategy_name)
                        module.__file__ = str(strategy_file) # 设置虚拟路径
                        sys.modules[strategy_name] = module
                        
                        # 执行代码
                        exec(strategy.content, module.__dict__)
                        
                        strategy_cls = self._find_strategy_class(module, strategy_name)
                        if strategy_cls:
                            return strategy_cls
                    else:
                        logger.error(f"数据库中未找到策略或策略内容为空: {strategy_name}")
                finally:
                    db.close()
            except Exception as db_e:
                logger.error(f"从数据库加载策略失败: {db_e}")
            
            logger.error(f"无法加载策略: {strategy_name}")
            return None
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            logger.exception(e)
            return None
    
    def create_strategy_instance(self, strategy_name: str, params: Optional[Dict[str, Any]] = None) -> str:
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
                "status": "created"
            }
            
            logger.info(f"创建策略实例成功: {instance_id}")
            return instance_id
        except Exception as e:
            logger.error(f"创建策略实例失败: {e}")
            logger.exception(e)
            return ""
    
    def get_strategy_instance(self, instance_id: str) -> Optional[Any]:
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
    
    def get_strategy_instances(self) -> List[Dict[str, Any]]:
        """
        获取所有策略实例
        
        :return: 策略实例列表
        """
        try:
            instances = []
            for instance_id, instance_info in self.strategy_instances.items():
                instances.append({
                    "instance_id": instance_id,
                    "strategy_name": instance_info["strategy_name"],
                    "params": instance_info["params"],
                    "created_at": instance_info["created_at"],
                    "status": instance_info["status"]
                })
            
            logger.info(f"获取策略实例列表成功，共 {len(instances)} 个实例")
            return instances
        except Exception as e:
            logger.error(f"获取策略实例列表失败: {e}")
            logger.exception(e)
            return []
    
    def execute_strategy(self, strategy_name: str, params: Dict[str, Any], mode: str = "backtest", backtest_config: Optional[Dict[str, Any]] = None) -> str:
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
                    slippage=backtest_config.get("slippage", 0.0)
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
                "engine": engine
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
    
    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
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
    
    def upload_strategy_file(self, strategy_name: str, file_content: str, version: Optional[str] = None, description: Optional[str] = None, tags: Optional[List[str]] = None, id: Optional[int] = None) -> bool:
        """
        上传策略文件
        
        :param strategy_name: 策略名称
        :param file_content: 文件内容
        :param version: 策略版本（可选），如果提供则使用，否则从文件内容中提取
        :param description: 策略描述（可选），如果提供则使用，否则从文件内容中提取
        :param tags: 策略标签（可选）
        :param id: 策略ID（可选），如果提供则更新现有策略，否则根据策略名称判断
        :return: 是否上传成功
        """
        try:
            # 保存策略文件
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            with open(strategy_file, "w") as f:
                f.write(file_content)
            
            logger.info(f"策略文件上传成功: {strategy_file}")
            
            # 将策略信息保存到数据库
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import Strategy
            import json
            from datetime import datetime
            
            init_database_config()
            db = SessionLocal()
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
                    "params": []
                }
                
                # 尝试解析策略内容，提取策略信息
                try:
                    parsed_info = self._parse_strategy_content(file_content, strategy_name)
                    if parsed_info:
                        strategy_info["description"] = description or parsed_info["description"]
                        strategy_info["params"] = parsed_info["params"]
                        # 如果没有提供tags，保留默认空列表；如果提供了tags，使用提供的
                        if not tags and "tags" in parsed_info:
                             strategy_info["tags"] = parsed_info["tags"]
                        logger.info(f"策略解析成功，使用解析的信息")
                    else:
                        logger.info(f"策略解析失败，使用默认信息")
                except Exception as parse_e:
                    logger.error(f"解析策略内容失败: {parse_e}")
                    logger.exception(parse_e)
                
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
                        version=strategy_info["version"]
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
            finally:
                db.close()
            
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
    
    def delete_strategy(self, strategy_name: str, strategy_id: Optional[int] = None) -> bool:
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
                from collector.db.database import SessionLocal, init_database_config
                from collector.db.models import Strategy
                
                init_database_config()
                db = SessionLocal()
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
                finally:
                    db.close()
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
    
    def validate_strategy_params(self, strategy_name: str, params: Dict[str, Any]) -> bool:
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
    
    def update_strategy_instance_params(self, instance_id: str, params: Dict[str, Any]) -> bool:
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
