"""Agent API 路由"""

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from utils.logger import get_logger, LogType
from ..core.factory import get_agent

logger = get_logger(__name__, LogType.APPLICATION)


router = APIRouter(
    prefix="/api/agent",
    tags=["agent"],
    responses={404: {"description": "Not found"}},
)

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


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    流式对话端点 (SSE - Server-Sent Events)

    返回 Server-Sent Events 格式的流式响应，实时推送 Agent 处理过程

    事件类型:
    - start: 开始处理
    - content: 文本内容增量（实时显示）
    - reasoning: 推理过程（DeepSeek-R1 等模型）
    - tool_calls: LLM 返回工具调用
    - tool_start: 开始执行工具
    - tool_result: 工具执行完成
    - complete: 全部处理完成
    - error: 错误信息

    使用示例:
        fetch('/api/agent/chat/stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: '你好'})
        }).then(response => {
            const reader = response.body.getReader();
            // 解析 SSE 事件...
        });
    """
    agent = get_agent()

    async def event_generator():
        """SSE 事件生成器"""
        try:
            async for event in agent.process_message_stream(
                content=request.message,
                session_key=request.session_id,
            ):
                # 格式化为 SSE 事件
                event_data = json.dumps({
                    "type": event.event_type,
                    "data": event.data,
                    "timestamp": event.timestamp,
                }, ensure_ascii=False)

                yield f"event: {event.event_type}\ndata: {event_data}\n\n"

                # 确保缓冲区刷新，让客户端能及时收到数据
                await asyncio.sleep(0)

        except Exception as e:
            # 发送错误事件
            error_data = json.dumps({
                "type": "error",
                "data": {"error": str(e), "timestamp": time.time()},
            }, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保实时传输
            "Access-Control-Allow-Origin": "*",  # 允许跨域访问
        }
    )


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
    try:
        agent = get_agent()
        agent.sessions.clear_session(session_id)
        return {"success": True, "message": f"会话 {session_id} 已清空"}
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, limit: int = 50):
    try:
        agent = get_agent()
        result = agent.sessions.get_history(session_id, limit)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"获取会话历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
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
    try:
        agent = get_agent()
        sessions = agent.sessions.list_sessions()
        return {"success": True, "sessions": sessions}
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CreateSessionRequest(BaseModel):
    name: str | None = None


@router.post("/sessions")
async def create_session(request: CreateSessionRequest):
    try:
        agent = get_agent()
        session_info = agent.sessions.create_session(request.name)
        return {
            "success": True,
            "session": session_info
        }
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    try:
        agent = get_agent()
        session_info = agent.sessions.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {
            "success": True,
            "session": session_info
        }
    except HTTPException:
        raise
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
