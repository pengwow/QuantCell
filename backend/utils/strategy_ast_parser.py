"""
策略代码AST解析工具

提供统一的策略代码AST解析功能，消除重复的解析逻辑。

主要功能:
    - AST解析和遍历
    - 策略类和配置类查找
    - 基类继承关系判断
    - 参数提取功能

使用示例:
    >>> from utils.strategy_ast_parser import StrategyASTParser
    >>> parser = StrategyASTParser()
    >>> tree = parser.parse(code)
    >>> strategy_classes = parser.find_strategy_classes(tree)

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-28
"""

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class StrategyClassInfo:
    """策略类信息"""
    class_node: ast.ClassDef
    class_name: str
    base_classes: List[str]
    is_strategy_class: bool
    is_config_class: bool
    line_number: int = 0
    col_offset: int = 0
    
    def __post_init__(self):
        if self.class_node:
            self.line_number = self.class_node.lineno
            self.col_offset = self.class_node.col_offset
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_name": self.class_name,
            "base_classes": self.base_classes,
            "is_strategy_class": self.is_strategy_class,
            "is_config_class": self.is_config_class,
            "line_number": self.line_number,
            "col_offset": self.col_offset
        }


@dataclass
class StrategyParseResult:
    """策略解析结果"""
    strategy_classes: List[StrategyClassInfo] = field(default_factory=list)
    config_classes: List[StrategyClassInfo] = field(default_factory=list)
    all_classes: List[StrategyClassInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_classes": [cls.to_dict() for cls in self.strategy_classes],
            "config_classes": [cls.to_dict() for cls in self.config_classes],
            "all_classes": [cls.to_dict() for cls in self.all_classes],
            "imports": self.imports,
            "methods": self.methods
        }


class StrategyASTParser:
    """策略代码AST解析器"""
    
    # 默认的策略基类名称
    DEFAULT_STRATEGY_BASES = ['Strategy', 'StrategyBase']
    DEFAULT_CONFIG_SUFFIX = 'Config'
    
    def __init__(self, strategy_bases: Optional[List[str]] = None, config_suffix: Optional[str] = None):
        """
        初始化AST解析器
        
        Args:
            strategy_bases: 策略基类名称列表，默认为['Strategy', 'StrategyBase']
            config_suffix: 配置类后缀，默认为'Config'
        """
        self.strategy_bases = strategy_bases or self.DEFAULT_STRATEGY_BASES
        self.config_suffix = config_suffix or self.DEFAULT_CONFIG_SUFFIX
        logger.debug(f"StrategyASTParser初始化完成，策略基类: {self.strategy_bases}")
    
    def parse(self, code: str) -> Optional[ast.AST]:
        """
        解析Python代码为AST
        
        Args:
            code: Python代码字符串
            
        Returns:
            AST树，解析失败返回None
        """
        try:
            tree = ast.parse(code)
            logger.debug("AST解析成功")
            return tree
        except SyntaxError as e:
            logger.error(f"AST解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"AST解析异常: {e}")
            return None
    
    def find_all_classes(self, tree: ast.AST) -> List[StrategyClassInfo]:
        """
        查找所有类定义
        
        Args:
            tree: AST树
            
        Returns:
            类信息列表
        """
        classes_info = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class_info(node)
                classes_info.append(class_info)
        
        logger.debug(f"找到{len(classes_info)}个类定义")
        return classes_info
    
    def find_strategy_classes(self, tree: ast.AST) -> List[StrategyClassInfo]:
        """
        查找所有策略类
        
        策略类的定义：
        1. 类名包含'Strategy'
        2. 或者继承自Strategy/StrategyBase
        
        Args:
            tree: AST树
            
        Returns:
            策略类信息列表
        """
        all_classes = self.find_all_classes(tree)
        strategy_classes = []
        
        for class_info in all_classes:
            # 跳过配置类
            if class_info.is_config_class:
                continue
            
            # 检查是否为策略类
            if class_info.is_strategy_class:
                strategy_classes.append(class_info)
        
        logger.debug(f"找到{len(strategy_classes)}个策略类")
        return strategy_classes
    
    def find_config_classes(self, tree: ast.AST) -> List[StrategyClassInfo]:
        """
        查找所有配置类
        
        配置类的定义：类名以'Config'结尾
        
        Args:
            tree: AST树
            
        Returns:
            配置类信息列表
        """
        all_classes = self.find_all_classes(tree)
        config_classes = [cls for cls in all_classes if cls.is_config_class]
        
        logger.debug(f"找到{len(config_classes)}个配置类")
        return config_classes
    
    def find_strategy_config_classes(self, tree: ast.AST) -> List[StrategyClassInfo]:
        """
        查找继承自StrategyConfig的配置类
        
        Args:
            tree: AST树
            
        Returns:
            配置类信息列表
        """
        all_classes = self.find_all_classes(tree)
        strategy_config_classes = []
        
        for class_info in all_classes:
            # 检查是否继承自StrategyConfig
            if 'StrategyConfig' in class_info.base_classes:
                strategy_config_classes.append(class_info)
        
        logger.debug(f"找到{len(strategy_config_classes)}个StrategyConfig类")
        return strategy_config_classes
    
    def find_imports(self, tree: ast.AST) -> List[str]:
        """
        查找所有导入语句
        
        Args:
            tree: AST树
            
        Returns:
            导入列表
        """
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        logger.debug(f"找到{len(imports)}个导入")
        return imports
    
    def find_methods(self, tree: ast.AST) -> List[str]:
        """
        查找所有方法定义
        
        Args:
            tree: AST树
            
        Returns:
            方法名列表
        """
        methods = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                methods.append(node.name)
        
        logger.debug(f"找到{len(methods)}个方法")
        return methods
    
    def find_class_methods(self, class_node: ast.ClassDef) -> List[str]:
        """
        查找类中的所有方法
        
        Args:
            class_node: 类定义节点
            
        Returns:
            方法名列表
        """
        methods = []
        
        for node in ast.walk(class_node):
            if isinstance(node, ast.FunctionDef):
                methods.append(node.name)
        
        return methods
    
    def extract_strategy_info(self, tree: ast.AST) -> StrategyParseResult:
        """
        提取策略的完整信息
        
        Args:
            tree: AST树
            
        Returns:
            策略解析结果
        """
        result = StrategyParseResult()
        
        result.all_classes = self.find_all_classes(tree)
        result.strategy_classes = self.find_strategy_classes(tree)
        result.config_classes = self.find_config_classes(tree)
        result.imports = self.find_imports(tree)
        result.methods = self.find_methods(tree)
        
        return result
    
    def _extract_class_info(self, class_node: ast.ClassDef) -> StrategyClassInfo:
        """
        提取类信息
        
        Args:
            class_node: 类定义节点
            
        Returns:
            类信息对象
        """
        class_name = class_node.name
        base_classes = self._extract_base_classes(class_node)
        
        # 判断是否为配置类
        is_config_class = class_name.endswith(self.config_suffix)
        
        # 判断是否为策略类
        is_strategy_class = self._is_strategy_class(class_name, base_classes)
        
        return StrategyClassInfo(
            class_node=class_node,
            class_name=class_name,
            base_classes=base_classes,
            is_strategy_class=is_strategy_class,
            is_config_class=is_config_class
        )
    
    def _extract_base_classes(self, class_node: ast.ClassDef) -> List[str]:
        """
        提取基类名称
        
        Args:
            class_node: 类定义节点
            
        Returns:
            基类名称列表
        """
        base_classes = []
        
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                base_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_classes.append(base.attr)
        
        return base_classes
    
    def _is_strategy_class(self, class_name: str, base_classes: List[str]) -> bool:
        """
        判断是否为策略类
        
        Args:
            class_name: 类名
            base_classes: 基类名称列表
            
        Returns:
            是否为策略类
        """
        # 检查类名是否包含'Strategy'
        if 'Strategy' in class_name:
            return True
        
        # 检查基类是否为策略基类
        for base_class in base_classes:
            if base_class in self.strategy_bases:
                return True
        
        return False
    
    def is_axon_strategy(self, tree: ast.AST) -> bool:
        """
        检查是否为axon_quant策略
        
        Args:
            tree: AST树
            
        Returns:
            是否为axon_quant策略
        """
        imports = self.find_imports(tree)
        
        for imp in imports:
            if 'axon_quant' in imp or 'axon' in imp.lower():
                return True
        
        return False
    
    def extract_params_from_config_class(self, config_class_node: ast.ClassDef, file_content: str) -> List[Dict[str, Any]]:
        """
        从配置类的__init__方法中提取参数
        
        Args:
            config_class_node: 配置类节点
            file_content: 文件内容
            
        Returns:
            参数列表
        """
        params = []
        
        for item in config_class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                args = item.args
                # 跳过 self 参数
                arg_names = [arg.arg for arg in args.args[1:]]
                defaults = args.defaults
                
                # 计算默认值起始索引
                defaults_start = len(arg_names) - len(defaults)
                
                for i, arg_name in enumerate(arg_names):
                    # 跳过内置参数
                    if arg_name in ['instrument_ids', 'bar_types', 'trade_size', 'log_size', 'log_level']:
                        continue
                    
                    # 获取默认值
                    default_value = None
                    if i >= defaults_start:
                        default_node = defaults[i - defaults_start]
                        default_value = self._extract_default_value(default_node)
                    
                    # 确定参数类型
                    param_type = "Any"
                    # 从函数注解中获取类型
                    if hasattr(args, 'annotations') and arg_name in args.annotations:
                        ann = args.annotations[arg_name]
                        if isinstance(ann, ast.Name):
                            param_type = ann.id
                        elif isinstance(ann, ast.Attribute):
                            param_type = ann.attr
                        elif isinstance(ann, ast.Subscript):
                            if isinstance(ann.value, ast.Name):
                                param_type = f"{ann.value.id}[...]"
                    
                    # 从默认值推断类型
                    if default_value is not None:
                        param_type = type(default_value).__name__
                    
                    # 添加到参数列表
                    params.append({
                        "name": arg_name,
                        "type": param_type,
                        "default": default_value,
                        "description": "",
                        "required": default_value is None
                    })
                break
        
        return params
    
    def extract_params_from_strategy_class(self, strategy_class_node: ast.ClassDef, file_content: str) -> List[Dict[str, Any]]:
        """
        从策略类的类属性中提取参数（Legacy格式）
        
        Args:
            strategy_class_node: 策略类节点
            file_content: 文件内容
            
        Returns:
            参数列表
        """
        params = []
        
        for item in strategy_class_node.body:
            if isinstance(item, ast.Assign):
                if len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                    param_name = item.targets[0].id
                    if param_name.startswith('_'):
                        continue
                    
                    param_default = None
                    if isinstance(item.value, ast.Constant):
                        param_default = item.value.value
                    elif isinstance(item.value, ast.Num):
                        param_default = item.value.n
                    elif isinstance(item.value, ast.Str):
                        param_default = item.value.s
                    elif isinstance(item.value, ast.NameConstant):
                        param_default = item.value.value
                    
                    param_desc = ""
                    if hasattr(item, 'lineno'):
                        lines = file_content.split('\n')
                        if item.lineno <= len(lines):
                            line = lines[item.lineno - 1]
                            comment_index = line.find('#')
                            if comment_index != -1:
                                param_desc = line[comment_index + 1:].strip()
                    
                    param_type = type(param_default).__name__ if param_default is not None else "Any"
                    
                    params.append({
                        "name": param_name,
                        "type": param_type,
                        "default": param_default,
                        "description": param_desc,
                        "required": False
                    })
        
        return params
    
    def _extract_default_value(self, default_node: ast.expr) -> Any:
        """
        提取默认值
        
        Args:
            default_node: 默认值节点
            
        Returns:
            默认值
        """
        if isinstance(default_node, ast.Constant):
            return default_node.value
        elif isinstance(default_node, ast.Num):
            return default_node.n
        elif isinstance(default_node, ast.Str):
            return default_node.s
        elif isinstance(default_node, ast.NameConstant):
            return default_node.value
        elif isinstance(default_node, ast.Call):
            # 处理 Decimal("0.1") 这样的调用
            if isinstance(default_node.func, ast.Name) and default_node.func.id == 'Decimal':
                if default_node.args and isinstance(default_node.args[0], ast.Str):
                    try:
                        return float(default_node.args[0].s)
                    except (ValueError, TypeError):
                        return None
            elif isinstance(default_node.func, ast.Attribute):
                # 处理其他类型的调用
                return None
        return None


def parse_strategy_code(code: str) -> Dict[str, Any]:
    """
    解析策略代码，返回策略类和配置类信息
    
    Args:
        code: 策略代码
        
    Returns:
        包含策略类和配置类信息的字典
    """
    parser = StrategyASTParser()
    tree = parser.parse(code)
    
    if not tree:
        return {
            "success": False,
            "error": "代码解析失败",
            "strategy_classes": [],
            "config_classes": []
        }
    
    strategy_classes = parser.find_strategy_classes(tree)
    config_classes = parser.find_config_classes(tree)
    
    return {
        "success": True,
        "strategy_classes": [cls.to_dict() for cls in strategy_classes],
        "config_classes": [cls.to_dict() for cls in config_classes],
        "total_classes": len(strategy_classes) + len(config_classes)
    }
