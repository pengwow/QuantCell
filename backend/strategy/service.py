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
        
        logger.info(f"策略服务初始化成功，策略目录: {self.strategy_dir}")
    
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
            
            # 解析Python代码
            tree = ast.parse(file_content)
            
            # 初始化策略信息
            strategy_info = {
                "name": file_path.stem,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "description": "",
                "version": "1.0.0",
                "params": [],
                "created_at": datetime.fromtimestamp(file_path.stat().st_ctime),
                "updated_at": datetime.fromtimestamp(file_path.stat().st_mtime),
                "code": file_content
            }
            
            # 查找策略类
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 检查是否继承自Strategy或StrategyBase
                    has_strategy_base = False
                    for base in node.bases:
                        if isinstance(base, ast.Name) and (base.id == 'Strategy' or base.id == 'StrategyBase'):
                            has_strategy_base = True
                        elif isinstance(base, ast.Attribute) and (base.attr == 'Strategy' or base.attr == 'StrategyBase'):
                            has_strategy_base = True
                    
                    if has_strategy_base:
                        # 提取类文档字符串
                        strategy_info["description"] = ast.get_docstring(node) or ""
                        
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
            
            return strategy_info
        except Exception as e:
            logger.error(f"解析策略文件失败: {file_path}, 错误: {e}")
            logger.exception(e)
            return None
    
    def get_strategy_list(self):
        """
        获取所有支持的策略列表
        
        :return: 策略列表，每个策略包含完整的策略信息
        """
        try:
            # 从策略目录中获取所有策略文件
            strategy_files = list(self.strategy_dir.glob("*.py"))
            
            # 构建策略列表，包含完整的策略信息
            strategies = []
            for file in strategy_files:
                if file.stem == "__init__":
                    continue
                    
                strategy_info = self._parse_strategy_file(file)
                if strategy_info:
                    # 移除code字段，列表接口不需要返回完整代码
                    strategy_info.pop("code")
                    strategies.append(strategy_info)
            
            logger.info(f"获取策略列表成功，共 {len(strategies)} 个策略")
            return strategies
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            logger.exception(e)
            return []
    
    def get_strategy_detail(self, strategy_name):
        """
        获取单个策略的详细信息
        
        :param strategy_name: 策略名称
        :return: 策略详细信息，如果获取失败返回None
        """
        try:
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.error(f"策略文件不存在: {strategy_file}")
                return None
            
            strategy_info = self._parse_strategy_file(strategy_file)
            if strategy_info:
                logger.info(f"获取策略详情成功: {strategy_name}")
                return strategy_info
            
            logger.error(f"解析策略文件失败: {strategy_file}")
            return None
        except Exception as e:
            logger.error(f"获取策略详情失败: {e}")
            logger.exception(e)
            return None
    
    def load_strategy(self, strategy_name) -> Optional[Type[Any]]:
        """
        从文件中加载策略类
        
        :param strategy_name: 策略名称
        :return: 策略类，如果加载失败返回None
        """
        try:
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.error(f"策略文件不存在: {strategy_file}")
                return None
            
            # 动态导入策略模块
            spec = importlib.util.spec_from_file_location(strategy_name, strategy_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[strategy_name] = module
                spec.loader.exec_module(module)
                
                # 查找Strategy或StrategyBase子类
                for name, cls in module.__dict__.items():
                    if isinstance(cls, type):
                        # 检查是否继承自Strategy或StrategyBase
                        if (issubclass(cls, Strategy) and cls != Strategy) or \
                           (issubclass(cls, StrategyBase) and cls != StrategyBase):
                            logger.info(f"成功加载策略: {strategy_name}.{name}")
                            return cls
            
            logger.error(f"在策略文件中未找到Strategy或StrategyBase子类: {strategy_file}")
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
    
    def upload_strategy_file(self, strategy_name: str, file_content: str) -> bool:
        """
        上传策略文件
        
        :param strategy_name: 策略名称
        :param file_content: 文件内容
        :return: 是否上传成功
        """
        try:
            strategy_file = self.strategy_dir / f"{strategy_name}.py"
            with open(strategy_file, "w") as f:
                f.write(file_content)
            
            logger.info(f"策略文件上传成功: {strategy_file}")
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
