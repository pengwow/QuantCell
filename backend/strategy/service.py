# -*- coding: utf-8 -*-
"""策略模块服务层

实现策略的加载、管理和解析功能。
支持两种策略类型：
- 规则策略：实现 on_bar(bar) → Action 的 Python 类
- RL 策略：使用 axon_quant.rl.TradingEnv 的训练/推理流程
"""

import sys
import importlib.util
import ast
from pathlib import Path
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)
from datetime import datetime
from typing import Any, Dict, List, Optional


class StrategyType:
    RULE = "rule"
    RL = "rl"


class StrategyService:
    """策略服务类"""

    def __init__(self):
        self.strategy_dir = Path(__file__).parent.parent / "strategies"
        self.strategy_dir.mkdir(parents=True, exist_ok=True)
        self.strategy_instances: Dict[str, Any] = {}

    def list_strategies(self) -> List[Dict[str, Any]]:
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

    def get_strategy(self, name: str) -> Optional[Dict[str, Any]]:
        """获取单个策略详情"""
        file_path = self.strategy_dir / f"{name}.py"
        if not file_path.exists():
            return None
        content = file_path.read_text(encoding="utf-8")
        info = self._parse_strategy_file(name, content)
        if info:
            info["code"] = content
        return info

    def save_strategy(self, name: str, content: str) -> Dict[str, Any]:
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
                if isinstance(node, ast.ImportFrom):
                    if node.module and "rl" in node.module.lower():
                        return StrategyType.RL
        except SyntaxError:
            pass
        return StrategyType.RULE

    def _parse_strategy_file(self, name: str, content: str) -> Optional[Dict[str, Any]]:
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
