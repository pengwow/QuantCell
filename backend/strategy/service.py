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
from pathlib import Path

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)
from datetime import datetime
from enum import Enum
from typing import Any


def _annotation_to_str(node: ast.AST | None) -> str:
    """把 type annotation AST 节点转成可读字符串（类外顶层函数，供静态方法调用）。"""
    if node is None:
        return "Any"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name):
            return node.value.id
        return "Any"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _annotation_to_str(node.left)
        return left if left != "None" else "Any"
    return "Any"


class StrategyType(Enum):
    """策略类型枚举"""

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
        """获取单个策略详情。

        factors / params / code 三个字段：DB 里如果有用户手动维护过的版本，优先返回；
        没有则回退到 AST 自动解析（_parse_strategy_file）的结果。
        """
        from strategy.models import Strategy
        from utils.db_session import get_db_session

        file_path = self.strategy_dir / f"{name}.py"
        if not file_path.exists():
            return None

        content = file_path.read_text(encoding="utf-8")
        info = self._parse_strategy_file(name, content)
        if info:
            info["code"] = content

        # 融合 DB 里手动维护过的 params / factors / description
        try:
            import json

            with get_db_session() as db:
                row = db.query(Strategy).filter_by(name=name).first()
            if row:
                # DB 有 params → 覆盖 AST 解析结果
                if row.parameters:
                    try:
                        info["params"] = json.loads(row.parameters)
                    except json.JSONDecodeError:
                        pass
                # DB 有 factors → 覆盖 AST 解析结果
                if row.factors:
                    try:
                        info["factors"] = self._strip_placeholder_descriptions(json.loads(row.factors))
                    except json.JSONDecodeError:
                        pass
                # DB 有 description（非空）→ 覆盖 AST docstring
                if row.description:
                    info["description"] = row.description
        except Exception as e:
            logger.debug(f"get_strategy DB 融合失败，跳过: {e}")

        return info

    def save_strategy(self, name: str, content: str) -> dict[str, Any]:
        """保存策略文件"""
        file_path = self.strategy_dir / f"{name}.py"
        file_path.write_text(content, encoding="utf-8")
        info = self._parse_strategy_file(name, content)
        logger.info(f"策略已保存: {name}")
        return info or {"name": name, "file_name": f"{name}.py"}

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
        """解析策略文件，提取参数、因子、类型等元信息"""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        strategy_class = None
        docstring = ""
        params: list[dict[str, Any]] = []
        factors: list[dict[str, Any]] = []

        # 第一次 walk：找 Config 类（类名含 Config）
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if "Config" not in node.name:
                continue

            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    # 跳过基类公共参数
                    raw_params = self._extract_params_from_init(item)
                    # 过滤掉基类的公共参数（策略模板里总会有）
                    _BASE_CONFIG_PARAMS = {"instrument_ids", "bar_types", "trade_size", "log_level"}
                    params = [p for p in raw_params if p["name"] not in _BASE_CONFIG_PARAMS]
                    break

            # 优先级：DEMO_FACTORS > AST 自动提取
            demo_factors = self._extract_demo_factors(node)
            if demo_factors is not None:
                factors = demo_factors

            # DEMO_PARAMS 优先级最高（覆盖 Config.__init__ 扫描结果）
            demo_params = self._extract_demo_params(node)
            if demo_params is not None:
                params = self._demo_params_to_list(demo_params)

            # Config 类一旦找到就停（后面扫主类时只取名字）
            break

        # 第二次 walk：取主类名（跳过 Config 类）+ 扫 BaseStrategy 风格的 self.config.params.get("name", default)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if strategy_class is None and "Config" not in node.name:
                    strategy_class = node.name

                # BaseStrategy 模板：没 Config 类，参数在 self.config.params.get(...) 里
                if not params:
                    params = self._extract_params_from_config_get(tree)

                # 主类也检查一下 DEMO_FACTORS（主类也可能写）
                if not factors:
                    demo_factors = self._extract_demo_factors(node)
                    if demo_factors is not None:
                        factors = demo_factors

            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    docstring = node.value.value

        # 没有 DEMO_FACTORS，走 AST 自动提取
        if not factors:
            factors = self._extract_factors(tree, content)

        strategy_type = self.detect_strategy_type(content)

        return {
            "name": name,
            "file_name": f"{name}.py",
            "file_path": str(self.strategy_dir / f"{name}.py"),
            "description": docstring[:200] if docstring else "",
            "version": "1.0.0",
            "tags": [],
            "params": params,
            "factors": factors,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "source": "files",
            "strategy_type": strategy_type,
            "strategy_class": strategy_class,
        }

    @staticmethod
    def _extract_params_from_init(init_fn: ast.FunctionDef) -> list[dict[str, Any]]:
        """从 __init__ signature 提取参数信息（真实 type + default）。

        ast 里 args.args 与 args.defaults 是右对齐的：
          def __init__(self, a, b=1, c="x"): ...
          args.args = [self, a, b, c]
          args.defaults = [1, "x"]
          → self 跳过；a 没有 default（required）；b→1, c→"x"
        """
        result: list[dict[str, Any]] = []
        args = init_fn.args.args
        defaults = init_fn.args.defaults  # 只包含有默认值的那些（右侧）
        n_default = len(defaults)

        for i, arg in enumerate(args):
            if arg.arg == "self":
                continue

            # type hint（ast 3.8+ 支持）
            type_ann = _annotation_to_str(getattr(arg, "annotation", None)) or "Any"

            # default 值：从右往左对齐
            default_idx = i - (len(args) - n_default)
            default_val: Any = None
            required = True
            if default_idx >= 0 and default_idx < n_default:
                try:
                    default_val = ast.literal_eval(defaults[default_idx])
                    required = False
                except ValueError, TypeError, SyntaxError:
                    default_val = None
                    required = False  # 有 default 但算不出具体值，也算非必填

            result.append(
                {
                    "name": arg.arg,
                    "type": type_ann,
                    "default": default_val,
                    "description": "",
                    "required": required,
                }
            )

        return result

    @staticmethod
    def _extract_demo_params(class_node: ast.ClassDef) -> dict[str, Any] | None:
        """从类属性里找 DEMO_PARAMS 字典（字面量 eval，安全）。"""
        for item in class_node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "DEMO_PARAMS":
                        try:
                            val = ast.literal_eval(item.value)
                            if isinstance(val, dict):
                                return val
                        except ValueError, TypeError, SyntaxError:
                            pass
        return None

    @staticmethod
    def _demo_params_to_list(demo: dict[str, Any]) -> list[dict[str, Any]]:
        """把 DEMO_PARAMS 字典转成前端 params 数组格式。"""
        result = []
        for name, info in demo.items():
            if not isinstance(info, dict):
                info = {}
            result.append(
                {
                    "name": name,
                    "type": info.get("type", "Any"),
                    "default": info.get("default"),
                    "description": info.get("desc", info.get("description", "")),
                    "required": False,
                }
            )
        return result

    @staticmethod
    def _extract_demo_factors(class_node: ast.ClassDef) -> list[dict[str, Any]] | None:
        """从类属性里找 DEMO_FACTORS 列表。"""
        for item in class_node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "DEMO_FACTORS":
                        try:
                            val = ast.literal_eval(item.value)
                            if isinstance(val, list):
                                return [
                                    {"name": str(f), "type": "factor", "description": ""} if isinstance(f, str) else f
                                    for f in val
                                ]
                        except ValueError, TypeError, SyntaxError:
                            pass
        return None

    @staticmethod
    def _extract_factors(tree: ast.AST, content: str) -> list[dict[str, Any]]:
        """自动从策略 AST 里提取因子引用，两种路径：

        1. BaseStrategy 路径：扫 Call 节点，找 ctx.get_feature("xxx") /
           ctx.get_feature(变量名)，变量名再去 Config.__init__ 里找
           对应的默认值字符串
        2. Config 路径：扫 Config.__init__ 参数里 factor_*
           前缀（factor_name, factor_threshold ...）

        去重后合并返回。
        """
        factors: dict[str, dict[str, Any]] = {}

        # —— 路径 1：ctx.get_feature / self.ctx.get_feature 调用 ——
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "get_feature":
                continue
            # 左边得是 ctx 或 self.ctx
            left = node.func.value
            is_ctx = (isinstance(left, ast.Name) and left.id == "ctx") or (
                isinstance(left, ast.Attribute) and left.attr == "ctx"
            )
            if not is_ctx:
                continue
            if not node.args:
                continue

            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                # 直接字符串字面量：ctx.get_feature("momentum_10")
                factors[arg.value] = {
                    "name": arg.value,
                    "type": "factor",
                    "description": "",
                }
            elif isinstance(arg, ast.Name):
                # 变量名：ctx.get_feature(factor_name) —— 记下来，后面去 Config 里找默认值
                var_name = arg.id
                factors[f"__config_var:{var_name}"] = {
                    "name": var_name,
                    "type": "config_ref",
                    "description": "",
                }

        # —— 路径 2：Config.__init__ 参数里的 factor_* 前缀 ——
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    args = item.args.args
                    defaults = item.args.defaults
                    n_default = len(defaults)
                    for i, arg in enumerate(args):
                        if arg.arg == "self":
                            continue
                        if not arg.arg.startswith("factor"):
                            continue

                        default_idx = i - (len(args) - n_default)
                        default_val: Any = None
                        if default_idx >= 0 and default_idx < n_default:
                            try:
                                default_val = ast.literal_eval(defaults[default_idx])
                            except ValueError, TypeError, SyntaxError:
                                pass

                        entry = {
                            "name": arg.arg,
                            "type": "factor_param",
                            "description": "",
                        }
                        if isinstance(default_val, str) and default_val:
                            entry["default"] = default_val
                            # 如果默认值是个非空字符串，当作候选因子名
                            factors.setdefault(
                                default_val,
                                {
                                    "name": default_val,
                                    "type": "factor",
                                    "description": "",
                                },
                            )
                        factors[f"__param:{arg.arg}"] = entry
                    break

        # 清理内部标记键，只保留干净的因子列表
        clean: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key, val in factors.items():
            if key.startswith("__"):
                continue
            if val["name"] in seen:
                continue
            seen.add(val["name"])
            clean.append(val)

        return clean

    @staticmethod
    def _strip_placeholder_descriptions(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """清除 AST 自动提取时残留的占位符描述（如"来自 Config.factor_name 默认值"）。

        旧版 _extract_factors 会写入这类调试信息，现已不再生成；但 DB 里可能
        还存着历史数据，返回前端前统一清掉，前端再用因子库真实描述兜底。
        """
        for f in factors:
            desc = f.get("description")
            if isinstance(desc, str) and desc.startswith("来自 "):
                f["description"] = ""
        return factors

    @staticmethod
    def _extract_params_from_config_get(tree: ast.AST) -> list[dict[str, Any]]:
        """扫 self.config.params.get("name", default) 调用，提取 BaseStrategy 模板的参数。"""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        _BASE_CONFIG_KEYS = {
            "factor_name",
            "buy_threshold",
            "sell_threshold",
            "position_limit",
            "fast",
            "slow",
            "fast_period",
            "slow_period",
            "mode",
            "signal_interval",
            "lookback",
            "threshold",
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
                continue
            # 左边得是 self.config.params
            left = node.func.value
            if not (isinstance(left, ast.Attribute) and left.attr == "params"):
                continue
            parent = left.value
            if not (isinstance(parent, ast.Attribute) and parent.attr == "config"):
                continue

            if not node.args:
                continue

            # 第一个参数是常量字符串 → 参数名
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            name = first.value
            if name in seen:
                continue
            seen.add(name)

            # 第二个参数是默认值（可选）
            default_val: Any = None
            if len(node.args) >= 2:
                try:
                    default_val = ast.literal_eval(node.args[1])
                except ValueError, TypeError, SyntaxError:
                    default_val = None

            # 猜类型：默认值的 Python 类型 → 前端 type hint
            if default_val is None:
                guessed_type = "Any"
            elif isinstance(default_val, bool):
                guessed_type = "bool"
            elif isinstance(default_val, int):
                guessed_type = "int"
            elif isinstance(default_val, float):
                guessed_type = "float"
            elif isinstance(default_val, str):
                guessed_type = "str"
            else:
                guessed_type = "Any"

            desc = ""
            if name in _BASE_CONFIG_KEYS:
                desc_map = {
                    "factor_name": "因子名称，需与回测 factor_names 里的名字一致",
                    "buy_threshold": "因子买入阈值",
                    "sell_threshold": "因子卖出阈值",
                    "position_limit": "目标仓位上限",
                }
                desc = desc_map.get(name, "")

            result.append(
                {
                    "name": name,
                    "type": guessed_type,
                    "default": default_val,
                    "description": desc,
                    "required": False,
                }
            )

        return result

    def upload_strategy_file(
        self,
        strategy_name: str,
        file_content: str,
        version: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        id: int | None = None,
        params: list[dict] | None = None,
        factors: list[dict] | None = None,
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
                        "params": params or [],
                        "factors": factors,  # None 表示"未传，用解析结果"；否则用传入值
                    }

                    # 如果没有传入 params/factors，尝试解析策略内容自动提取
                    if not params or factors is None:
                        try:
                            parsed_info = self._parse_strategy_file(strategy_name, file_content)
                            if parsed_info:
                                if description is None:
                                    strategy_info["description"] = parsed_info["description"]
                                if not params:
                                    strategy_info["params"] = parsed_info["params"]
                                if factors is None:
                                    strategy_info["factors"] = parsed_info.get("factors", [])
                                if not tags and "tags" in parsed_info:
                                    strategy_info["tags"] = parsed_info["tags"]
                                logger.info("策略解析成功，使用解析的信息")
                            else:
                                logger.info("策略解析失败，使用默认信息")
                        except Exception as parse_e:
                            logger.error(f"解析策略内容失败: {parse_e}")
                            logger.exception(parse_e)

                    # 准备参数JSON
                    params_json = json.dumps(strategy_info["params"]) if strategy_info["params"] else None
                    tags_json = json.dumps(strategy_info["tags"]) if strategy_info["tags"] else None
                    factors_json = (
                        json.dumps(strategy_info.get("factors") or []) if strategy_info.get("factors") else None
                    )
                    logger.info(f"准备保存的参数: {params_json}, factors: {factors_json}")

                    if existing_strategy:
                        # 更新现有策略
                        logger.info(f"更新现有策略: id={id}, name={strategy_name}")
                        existing_strategy.name = strategy_name
                        existing_strategy.file_name = strategy_info["file_name"]
                        existing_strategy.code = file_content
                        existing_strategy.description = strategy_info["description"]
                        existing_strategy.parameters = params_json
                        existing_strategy.factors = factors_json
                        existing_strategy.tags = tags_json
                        existing_strategy.version = strategy_info["version"]
                        logger.info(f"更新策略信息到数据库: {strategy_name}")
                    else:
                        # 创建新策略
                        logger.info(f"创建新策略: {strategy_name}")
                        new_strategy = Strategy(
                            name=strategy_name,
                            file_name=strategy_info["file_name"],
                            code=file_content,
                            description=strategy_info["description"],
                            parameters=params_json,
                            factors=factors_json,
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

    # —— factors 独立 CRUD ——

    def get_factors(self, strategy_name: str) -> list[dict[str, Any]]:
        """获取策略的因子列表（优先 DB 里的，没存则回退 AST 自动解析）。"""
        from strategy.models import Strategy
        from utils.db_session import get_db_session

        with get_db_session() as db:
            row = db.query(Strategy).filter_by(name=strategy_name).first()
            if row and row.factors:
                try:
                    import json

                    return self._strip_placeholder_descriptions(json.loads(row.factors))
                except Exception:
                    pass

        # DB 没存 → 回退 AST 自动解析
        file_path = self.strategy_dir / f"{strategy_name}.py"
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            info = self._parse_strategy_file(strategy_name, content)
            return info.get("factors", []) if info else []
        return []

    def replace_factors(self, strategy_name: str, factors: list[dict[str, Any]]) -> bool:
        """整体覆盖策略的因子列表（前端手动维护完保存用）。"""
        import json

        from strategy.models import Strategy
        from utils.db_session import get_db_session

        with get_db_session() as db:
            row = db.query(Strategy).filter_by(name=strategy_name).first()
            if row is None:
                logger.warning(f"替换因子失败：策略不存在: {strategy_name}")
                return False
            row.factors = json.dumps(factors) if factors else None
            db.commit()
        logger.info(f"策略因子已覆盖: {strategy_name}, 共 {len(factors)} 个")
        return True

    def add_factor(self, strategy_name: str, factor: dict[str, Any]) -> bool:
        """给策略添加一个因子（按 name 去重）。"""
        existing = self.get_factors(strategy_name)
        name = factor.get("name")
        if not name:
            return False
        if any(f.get("name") == name for f in existing):
            return True  # 已存在，幂等
        existing.append(factor)
        return self.replace_factors(strategy_name, existing)

    def remove_factor(self, strategy_name: str, factor_name: str) -> bool:
        """从策略里移除指定因子。"""
        existing = self.get_factors(strategy_name)
        new_list = [f for f in existing if f.get("name") != factor_name]
        if len(new_list) == len(existing):
            return False  # 没找到要删的
        return self.replace_factors(strategy_name, new_list)

    def update_factor(self, strategy_name: str, factor_name: str, patch: dict[str, Any]) -> bool:
        """更新单个因子字段（比如改 description）。"""
        existing = self.get_factors(strategy_name)
        for i, f in enumerate(existing):
            if f.get("name") == factor_name:
                existing[i] = {**f, **patch, "name": factor_name}  # name 不允许改
                return self.replace_factors(strategy_name, existing)
        return False

    def reparse_strategy(self, strategy_name: str) -> dict[str, Any] | None:
        """重新 AST 解析策略源码，把 params + factors 同步回 DB。"""
        import json

        from strategy.models import Strategy
        from utils.db_session import get_db_session

        file_path = self.strategy_dir / f"{strategy_name}.py"
        if not file_path.exists():
            logger.warning(f"重新解析失败：策略文件不存在: {file_path}")
            return None

        content = file_path.read_text(encoding="utf-8")
        info = self._parse_strategy_file(strategy_name, content)
        if not info:
            return None

        with get_db_session() as db:
            row = db.query(Strategy).filter_by(name=strategy_name).first()
            if row:
                row.parameters = json.dumps(info["params"]) if info["params"] else None
                row.factors = json.dumps(info["factors"]) if info["factors"] else None
                row.code = content
                row.description = info.get("description", "") or row.description
                db.commit()
                logger.info(
                    f"重新解析已同步到 DB: {strategy_name}, params={len(info['params'])}, factors={len(info['factors'])}"
                )
            else:
                logger.warning(f"重新解析跳过：DB 中无记录，未自动创建: {strategy_name}")

        return info

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
            from ai.config.services import AIModelService

            # 获取AI模型适配器
            adapter = None
            if model_id:
                # 从数据库获取模型配置
                from ai.config.models import AIModelBusiness

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
