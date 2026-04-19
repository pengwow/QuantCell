"""Agent API 路由"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.logger import get_logger, LogType
from ..core.loop import AgentLoop
from ..providers.openai_provider import OpenAIProvider

logger = get_logger(__name__, LogType.APPLICATION)


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

router = APIRouter(
    prefix="/api/agent",
    tags=["agent"],
    responses={404: {"description": "Not found"}},
)

# 全局 Agent 实例
_agent_instance: AgentLoop | None = None


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    message: str
    session_id: str


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str


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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    与 Agent 进行对话
    
    - **message**: 用户消息
    - **session_id**: 会话标识（可选，默认为 default）
    """
    try:
        agent = get_agent()
        response = await agent.process_message(
            content=request.message,
            session_key=request.session_id,
        )
        
        return ChatResponse(
            success=True,
            message=response,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.error(f"Agent 处理消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """获取所有可用工具列表"""
    try:
        agent = get_agent()
        tools = []
        for name in agent.tools.tool_names:
            tool = agent.tools.get(name)
            if tool:
                tools.append(ToolInfo(name=name, description=tool.description))
        return tools
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """清空指定会话的历史记录"""
    try:
        agent = get_agent()
        session = agent.sessions.get_or_create(session_id)
        session.clear()
        agent.sessions.save(session)
        
        return {"success": True, "message": f"会话 {session_id} 已清空"}
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, limit: int = 50):
    """获取会话历史记录"""
    try:
        agent = get_agent()
        session = agent.sessions.get_or_create(session_id)
        history = session.get_history(max_messages=limit)
        
        return {
            "success": True,
            "session_id": session_id,
            "history": history,
            "total_messages": len(session.messages),
        }
    except Exception as e:
        logger.error(f"获取会话历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话（包括消息记录）"""
    try:
        agent = get_agent()
        success = agent.sessions.delete(session_id)
        
        if success:
            return {
                "success": True,
                "message": f"会话 {session_id} 已删除",
                "warning": "该会话的历史消息已永久删除，但已整合的长期记忆仍保留在 MEMORY.md 中"
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """获取所有会话列表"""
    try:
        agent = get_agent()
        sessions = []
        
        # 从工作空间读取所有会话
        sessions_dir = agent.workspace / "sessions"
        if sessions_dir.exists():
            for session_file in sessions_dir.glob("*.json"):
                try:
                    import json
                    with open(session_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        sessions.append({
                            "id": data.get("id", session_file.stem),
                            "name": data.get("name", "未命名"),
                            "createdAt": data.get("createdAt", ""),
                            "updatedAt": data.get("updatedAt", ""),
                        })
                except Exception as e:
                    logger.debug(f"读取会话文件失败 {session_file}: {e}")
        
        # 按更新时间排序
        sessions.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
        
        return {"success": True, "sessions": sessions}
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    name: str | None = None


@router.post("/sessions")
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    try:
        agent = get_agent()
        
        # 生成会话ID
        import uuid
        from datetime import datetime
        
        session_id = str(uuid.uuid4())[:8]
        
        # 创建会话
        session = agent.sessions.get_or_create(session_id)
        
        # 保存会话（name 存储在 metadata 中）
        name = request.name or f"会话 {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
        
        # 将会话保存到文件时添加 name 字段
        session_data = session.to_dict()
        session_data["id"] = session.key
        session_data["name"] = name
        
        # 保存到文件
        sessions_dir = agent.workspace / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = sessions_dir / f"{session.key}.json"
        
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "session": {
                "id": session.key,
                "name": name,
                "createdAt": session_data.get("created_at", ""),
                "updatedAt": session_data.get("updated_at", ""),
            }
        }
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    try:
        agent = get_agent()
        session = agent.sessions.get_or_create(session_id)
        
        # 尝试从文件读取 name
        name = session_id
        sessions_dir = agent.workspace / "sessions"
        session_file = sessions_dir / f"{session_id}.json"
        if session_file.exists():
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = data.get("name", session_id)
            except:
                pass
        
        return {
            "success": True,
            "session": {
                "id": session.key,
                "name": name,
                "createdAt": session.created_at.isoformat() if hasattr(session.created_at, 'isoformat') else str(session.created_at),
                "updatedAt": session.updated_at.isoformat() if hasattr(session.updated_at, 'isoformat') else str(session.updated_at),
                "messageCount": len(session.messages),
            }
        }
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 工具参数管理 API ====================

from datetime import datetime
from typing import Optional
from fastapi import Query

from agent.config.manager import ToolParamManager, mask_sensitive_value
from agent.config.schemas import (
    BatchUpdateRequest,
    ImportConfigRequest,
    SetValueRequest,
)


@router.get("/tools/params/tools")
async def get_registered_tools():
    """获取所有已注册的工具列表及其参数状态"""
    try:
        tools = ToolParamManager.get_registered_tools()
        return {"code": 200, "data": tools}
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/params/{tool_name}")
async def get_tool_params(
    tool_name: str,
    include_sensitive: bool = Query(False, description="是否包含敏感参数真实值")
):
    """获取指定工具的参数配置"""
    try:
        params = ToolParamManager.get_tool_params(
            tool_name, 
            include_sensitive=include_sensitive
        )
        return {
            "code": 200,
            "data": {
                "tool_name": tool_name,
                "params": params
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取工具参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tools/params/{tool_name}/{param_name}")
async def set_tool_param(
    tool_name: str,
    param_name: str,
    request: SetValueRequest
):
    """设置工具参数"""
    try:
        success = ToolParamManager.set_tool_param(
            tool_name, param_name, request.value
        )
        
        if success:
            return {
                "code": 200,
                "message": "参数更新成功",
                "data": {
                    "param_name": param_name,
                    "value_masked": mask_sensitive_value(str(request.value)) if ToolParamManager.get_tool_params(tool_name, include_sensitive=False).get(param_name, {}).get("sensitive") else str(request.value),
                    "updated_at": datetime.now().isoformat()
                }
            }
        else:
            raise HTTPException(status_code=500, detail="保存失败")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"设置工具参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/params/{tool_name}/batch")
async def batch_update_params(
    tool_name: str,
    request: BatchUpdateRequest
):
    """批量更新工具参数"""
    try:
        result = ToolParamManager.batch_update(
            tool_name,
            request.params,
            overwrite=request.overwrite
        )
        
        return {
            "code": 200,
            "message": f"成功更新 {len(result['updated'])} 个参数",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"批量更新参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tools/params/{tool_name}/{param_name}")
async def delete_tool_param(tool_name: str, param_name: str):
    """删除工具参数"""
    try:
        success = ToolParamManager.delete_tool_param(tool_name, param_name)
        
        if success:
            return {
                "code": 200,
                "message": "参数已删除，将使用默认值或环境变量"
            }
        else:
            raise HTTPException(status_code=404, detail="参数不存在")
            
    except Exception as e:
        logger.error(f"删除工具参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/params/export")
async def export_config(
    tool_name: Optional[str] = Query(None, description="工具名称，不传则导出全部")
):
    """导出配置"""
    try:
        config = ToolParamManager.export_config(tool_name)
        return {"code": 200, "data": config}
    except Exception as e:
        logger.error(f"导出配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/params/import")
async def import_config(request: ImportConfigRequest):
    """导入配置"""
    try:
        imported, skipped, errors = ToolParamManager.import_config(
            request.config,
            overwrite=request.overwrite
        )
        
        return {
            "code": 200,
            "data": {
                "imported": imported,
                "skipped": skipped,
                "errors": errors
            }
        }
        
    except Exception as e:
        logger.error(f"导入配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
