"""Agent API 路由"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.logger import get_logger, LogType
from ..core.loop import AgentLoop
from ..providers.openai_provider import OpenAIProvider
from ..tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from ..tools.shell import ExecTool
from ..tools.web import WebFetchTool, WebSearchTool
from ..tools.trading.market_data import GetKlinesTool, GetTickerTool
from ..tools.trading.strategy import ListStrategiesTool, GetStrategyDetailTool, RunBacktestTool
from ..tools.trading.news import GetNewsTool, GetMarketSentimentTool

logger = get_logger(__name__, LogType.APPLICATION)

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
        
        # 创建提供者
        provider = OpenAIProvider()
        
        # 创建 Agent
        _agent_instance = AgentLoop(
            provider=provider,
            workspace=workspace,
            model=None,  # 使用默认模型
            max_iterations=40,
            temperature=0.1,
            max_tokens=4096,
            memory_window=100,
        )
        
        # 注册基础工具
        _agent_instance.register_tool(ReadFileTool(workspace))
        _agent_instance.register_tool(WriteFileTool(workspace))
        _agent_instance.register_tool(ListDirTool(workspace))
        _agent_instance.register_tool(ExecTool(
            working_dir=str(workspace),
            timeout=60,
        ))
        _agent_instance.register_tool(WebSearchTool())
        _agent_instance.register_tool(WebFetchTool())
        
        # 注册量化交易工具
        _agent_instance.register_tool(GetKlinesTool())
        _agent_instance.register_tool(GetTickerTool())
        _agent_instance.register_tool(ListStrategiesTool())
        _agent_instance.register_tool(GetStrategyDetailTool())
        _agent_instance.register_tool(RunBacktestTool())
        _agent_instance.register_tool(GetNewsTool())
        _agent_instance.register_tool(GetMarketSentimentTool())
        
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
