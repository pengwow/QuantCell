"""Agent 工厂 - 创建和管理 Agent 单例实例"""

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger, LogType
from .loop import AgentLoop
from ..providers.openai_provider import OpenAIProvider

logger = get_logger(__name__, LogType.APPLICATION)

_agent_instance: AgentLoop | None = None


def get_ai_config() -> dict[str, Any] | None:
    """从系统配置获取AI模型配置

    直接实现配置读取，避免通过 ai_model.config_utils 导入导致的循环导入问题。
    参考策略模块的配置读取方式，但使用更安全的导入策略。
    """
    try:
        # 直接读取数据库配置，避免导入 settings.models 导致的循环导入
        from collector.db.database import SessionLocal, init_database_config
        from sqlalchemy import text

        init_database_config()
        db = SessionLocal()

        try:
            result = db.execute(text("SELECT key, value FROM system_config WHERE key LIKE 'ai_model.%'")).fetchall()

            if not result:
                return None

            all_configs = {row[0]: {"value": row[1]} for row in result}

            if not all_configs:
                return None

            providers = {}
            for key, config in all_configs.items():
                value = config.get("value")
                if not isinstance(value, str):
                    continue

                if key.startswith("ai_model."):
                    parts = key.split(".")
                    if len(parts) >= 3:
                        provider_id = parts[1]
                        field = ".".join(parts[2:])

                        if provider_id not in providers:
                            providers[provider_id] = {"id": provider_id}

                        if field == "models" and value:
                            try:
                                providers[provider_id][field] = json.loads(value)
                            except json.JSONDecodeError:
                                providers[provider_id][field] = []
                        elif field in ["is_default", "proxy_enabled"]:
                            providers[provider_id][field] = value in ("true", "1", True)
                        elif field == "is_enabled":
                            providers[provider_id][field] = value if value else None
                        else:
                            providers[provider_id][field] = value

            provider_list = list(providers.values())

            default_provider = None
            for provider in provider_list:
                if provider.get("is_default", False):
                    default_provider = provider
                    break

            if not default_provider:
                for provider in provider_list:
                    if provider.get("is_enabled"):
                        default_provider = provider
                        break

            if not default_provider:
                return None

            # is_enabled 存储的是启用的模型ID，需要在 models 列表中找到对应模型
            enabled_model_id = default_provider.get("is_enabled")
            all_models = default_provider.get("models", [])

            # 根据 is_enabled 查找启用的模型
            enabled_model = None
            if enabled_model_id:
                for m in all_models:
                    if isinstance(m, dict) and m.get("id") == enabled_model_id:
                        enabled_model = m
                        break

            # 如果没找到，使用第一个模型
            if not enabled_model and all_models:
                enabled_model = all_models[0] if isinstance(all_models[0], dict) else None

            if not enabled_model:
                logger.warning(f"提供商 {default_provider.get('id')} 没有可用的模型")
                return None

            result = {
                "provider": {
                    "id": default_provider.get("id"),
                    "name": default_provider.get("name", ""),
                    "provider": default_provider.get("provider", ""),
                    "api_key": default_provider.get("api_key", ""),
                    "api_host": default_provider.get("api_host", ""),
                },
                "enabled_model": {
                    "id": enabled_model.get("id"),
                    "name": enabled_model.get("name"),
                    "model_name": enabled_model.get("model_name"),
                },
            }

            logger.info(f"从系统配置加载AI模型: {result['provider']['name']}, 模型: {result['enabled_model']['name']} (ID: {result['enabled_model']['id']})")
            return result

        finally:
            db.close()

    except ImportError as e:
        logger.debug(f"无法导入数据库模块: {e}")
        return None
    except Exception as e:
        logger.debug(f"获取系统AI配置失败: {e}")
        return None


def get_agent() -> AgentLoop:
    """获取或创建 Agent 实例"""
    global _agent_instance

    if _agent_instance is None:
        # 创建工作空间目录
        workspace = Path(__file__).parent.parent.parent.parent / "agent_workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        # 从系统配置获取AI模型配置
        ai_config = get_ai_config()

        if ai_config:
            # 使用系统配置中的模型设置
            provider_config = ai_config["provider"]
            enabled_model = ai_config.get("enabled_model", {})

            # 获取启用的模型信息
            if enabled_model:
                # 使用 name 进行API调用（与策略生成接口保持一致），如果没有则使用 id
                model_id = enabled_model.get("name") or enabled_model.get("id")
                logger.info(f"Agent使用模型: id={enabled_model.get('id')}, name={enabled_model.get('name')}")
            else:
                model_id = None

            # 创建提供者（使用系统配置的API密钥和主机）
            provider = OpenAIProvider(
                api_key=provider_config.get("api_key"),
                base_url=provider_config.get("api_host") or None,
            )

            logger.info(f"Agent使用系统配置: 提供商={provider_config['name']}, 模型={model_id}")
        else:
            # 使用环境变量配置
            provider = OpenAIProvider()
            model_id = None
            logger.info("Agent使用环境变量配置")

        # 创建 Agent
        _agent_instance = AgentLoop(
            provider=provider,
            workspace=workspace,
            model=model_id,  # 使用系统配置中的模型
            max_iterations=40,
            temperature=0.1,
            max_tokens=4096,
            memory_window=100,
        )
        
        # 使用统一的工具注册机制（自动发现并注册所有工具）
        from agent.tools import create_registry
        tools_registry = create_registry(workspace)
        
        # 将工具注册到 Agent 实例
        for tool in tools_registry._tools.values():
            _agent_instance.register_tool(tool)
        
        logger.info("Agent 实例已初始化")
    
    return _agent_instance