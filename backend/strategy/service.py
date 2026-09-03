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
                            parsed_info = self._parse_strategy_file(strategy_name, file_content)
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
                        existing_strategy.file_name = strategy_info["file_name"]
                        existing_strategy.code = file_content  # 保存策略内容到数据库
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
                            file_name=strategy_info["file_name"],
                            code=file_content,  # 保存策略内容到数据库
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
