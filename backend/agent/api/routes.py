"""Agent API 路由"""

import asyncio
import json
import re
import time
from enum import StrEnum

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


class IntentCategory(StrEnum):
    """意图分类枚举"""
    TRADING_DECISION = "trading_decision"
    BACKTEST = "backtest"
    RL_TRAINING = "rl_training"
    STRATEGY_GENERATION = "strategy_generation"
    DATA_QUERY = "data_query"
    RISK_ASSESSMENT = "risk_assessment"
    GENERAL = "general"


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    message: str
    session_id: str
    intent: IntentCategory = IntentCategory.GENERAL
    role: str = "assistant"
    actions: list[dict] = []
    structured_data: dict = {}


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str


# 预编译正则表达式（缓存以提高性能）
_CODE_BLOCK_REGEX = re.compile(r'```(python)?\s*\n(.*?)```', re.DOTALL)
_STRATEGY_NAME_REGEX = re.compile(r'策略名称[：:]\s*(.+?)\n')
_RISK_LEVEL_REGEX = re.compile(r'风险等级[：:]\s*(.+?)\n')


# 意图关键词映射（按优先级排序，优先级高的在前）
# 每个意图包含：(关键词, 权重)，权重越高匹配越优先
_INTENT_KEYWORDS = [
    # 风险评估（优先于策略生成，因为"评估策略风险"应该是风险评估）
    (IntentCategory.RISK_ASSESSMENT, [
        ("风险评估", 3), ("评估风险", 3), ("风控", 2), ("回撤", 2), ("止损", 2),
        ("风险等级", 3), ("风险分析", 3), ("risk", 1), ("risk assessment", 2),
    ]),
    # 回测（完整短语优先）
    (IntentCategory.BACKTEST, [
        ("历史回测", 3), ("回测结果", 3), ("回测分析", 3), ("测试策略", 2),
        ("backtest", 2), ("回测", 1),
    ]),
    # RL训练
    (IntentCategory.RL_TRAINING, [
        ("强化学习", 2), ("rl训练", 2), ("ppo", 2), ("sac", 2), ("dqn", 2),
        ("train", 1), ("训练", 1),
    ]),
    # 交易决策
    (IntentCategory.TRADING_DECISION, [
        ("下单交易", 2), ("买入", 1), ("卖出", 1), ("buy", 1), ("sell", 1),
        ("持仓", 1), ("平仓", 1), ("交易", 1),
    ]),
    # 策略生成（完整短语优先，避免被单独的"策略"关键词误匹配）
    (IntentCategory.STRATEGY_GENERATION, [
        ("生成策略", 3), ("写策略", 3), ("创建策略", 3), ("策略代码", 3), ("策略模板", 3),
        ("strategy", 1),
    ]),
    # 数据查询
    (IntentCategory.DATA_QUERY, [
        ("查询数据", 2), ("查看行情", 2), ("k线", 2), ("走势", 1), ("价格", 1),
        ("数据", 1), ("行情", 1), ("查询", 1),
    ]),
]


def classify_intent(message: str) -> str:
    """基于关键词分类用户意图（带权重的优先级匹配）
    
    规则：
    1. 完整短语优先匹配（如"评估风险"优先于单独的"风险"）
    2. 权重高的关键词优先
    3. 风险评估优先于策略生成（解决"评估策略风险"的歧义）
    """
    message_lower = message.lower()
    max_score = 0
    best_category = IntentCategory.GENERAL
    
    for category, keyword_pairs in _INTENT_KEYWORDS:
        for keyword, weight in keyword_pairs:
            if keyword.lower() in message_lower:
                # 完整词匹配权重翻倍
                if re.search(rf'(?:^|\W){re.escape(keyword.lower())}(?:$|\W)', message_lower):
                    weight *= 2
                if weight > max_score:
                    max_score = weight
                    best_category = category
    
    return best_category


def detect_role(intent: str) -> str:
    """根据意图确定 AI 角色"""
    role_mapping = {
        IntentCategory.TRADING_DECISION: "交易助手",
        IntentCategory.BACKTEST: "回测分析师",
        IntentCategory.RL_TRAINING: "AI 训练师",
        IntentCategory.STRATEGY_GENERATION: "策略工程师",
        IntentCategory.DATA_QUERY: "数据分析师",
        IntentCategory.RISK_ASSESSMENT: "风控顾问",
        IntentCategory.GENERAL: "AI 助手",
    }
    return role_mapping.get(intent, "AI 助手")


def extract_structured_data(message: str, intent: str) -> dict:
    """从消息中提取结构化数据"""
    data = {}
    
    if intent == IntentCategory.STRATEGY_GENERATION:
        # 提取策略代码块（使用缓存的正则）
        code_match = _CODE_BLOCK_REGEX.search(message)
        if code_match:
            data["code"] = code_match.group(2).strip()
        
        # 提取策略名称（使用缓存的正则）
        name_match = _STRATEGY_NAME_REGEX.search(message)
        if name_match:
            data["strategy_name"] = name_match.group(1).strip()
    
    elif intent == IntentCategory.BACKTEST:
        # 提取回测指标（预编译正则以提高性能）
        _BACKTEST_METRIC_REGEX = re.compile(r'(年化收益率|夏普比率|最大回撤|总收益|胜率)[：:]\s*([\d.]+)')
        for match in _BACKTEST_METRIC_REGEX.finditer(message):
            data[match.group(1)] = float(match.group(2))
    
    elif intent == IntentCategory.RISK_ASSESSMENT:
        # 提取风险等级（使用缓存的正则）
        risk_match = _RISK_LEVEL_REGEX.search(message)
        if risk_match:
            data["risk_level"] = risk_match.group(1).strip()
    
    return data


def build_actions(intent: str) -> list[dict]:
    """根据意图构建建议操作"""
    action_mapping = {
        IntentCategory.TRADING_DECISION: [
            {"type": "view_positions", "label": "查看持仓"},
            {"type": "place_order", "label": "下单交易"},
            {"type": "view_history", "label": "历史交易"},
        ],
        IntentCategory.BACKTEST: [
            {"type": "view_chart", "label": "查看图表"},
            {"type": "export_report", "label": "导出报告"},
            {"type": "optimize_params", "label": "参数优化"},
        ],
        IntentCategory.STRATEGY_GENERATION: [
            {"type": "view_code", "label": "查看代码"},
            {"type": "deploy_strategy", "label": "部署策略"},
            {"type": "backtest_strategy", "label": "回测策略"},
        ],
        IntentCategory.DATA_QUERY: [
            {"type": "view_kline", "label": "查看K线"},
            {"type": "export_data", "label": "导出数据"},
            {"type": "compare_symbols", "label": "对比分析"},
        ],
        IntentCategory.RISK_ASSESSMENT: [
            {"type": "view_risk_report", "label": "风险报告"},
            {"type": "set_stop_loss", "label": "设置止损"},
            {"type": "adjust_position", "label": "调整仓位"},
        ],
    }
    return action_mapping.get(intent, [])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    与 Agent 进行对话
    
    - **message**: 用户消息
    - **session_id**: 会话标识（可选，默认为 default）
    
    返回包含意图分类、角色类型、建议操作和结构化数据的响应
    """
    try:
        agent = get_agent()
        response = await agent.process_message(
            content=request.message,
            session_key=request.session_id,
        )
        
        # 意图检测和角色识别
        intent = classify_intent(request.message)
        role = detect_role(intent)
        structured_data = extract_structured_data(response, intent)
        actions = build_actions(intent)
        
        return ChatResponse(
            success=True,
            message=response,
            session_id=request.session_id,
            intent=intent,
            role=role,
            structured_data=structured_data,
            actions=actions,
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
    - start: 开始处理（包含意图和角色信息）
    - content: 文本内容增量（实时显示）
    - reasoning: 推理过程（DeepSeek-R1 等模型）
    - tool_calls: LLM 返回工具调用
    - tool_start: 开始执行工具
    - tool_result: 工具执行完成
    - complete: 全部处理完成（包含结构化数据和建议操作）
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
    
    # 意图检测和角色识别（在流式处理开始前完成）
    intent = classify_intent(request.message)
    role = detect_role(intent)
    accumulated_content = ""

    async def event_generator():
        """SSE 事件生成器"""
        nonlocal accumulated_content
        
        try:
            # 发送 start 事件（包含意图和角色信息）
            start_data = json.dumps({
                "type": "start",
                "data": {
                    "intent": intent,
                    "role": role,
                    "message": request.message,
                },
                "timestamp": time.time(),
            }, ensure_ascii=False)
            yield f"event: start\ndata: {start_data}\n\n"
            await asyncio.sleep(0)

            async for event in agent.process_message_stream(
                content=request.message,
                session_key=request.session_id,
            ):
                # 累积内容用于后续结构化数据提取
                if event.event_type == "content" and event.data:
                    accumulated_content += event.data

                # 格式化为 SSE 事件
                event_data = json.dumps({
                    "type": event.event_type,
                    "data": event.data,
                    "timestamp": event.timestamp,
                }, ensure_ascii=False)

                yield f"event: {event.event_type}\ndata: {event_data}\n\n"

                # 确保缓冲区刷新，让客户端能及时收到数据
                await asyncio.sleep(0)

            # 发送 complete 事件（包含结构化数据和建议操作）
            structured_data = extract_structured_data(accumulated_content, intent)
            actions = build_actions(intent)
            
            complete_data = json.dumps({
                "type": "complete",
                "data": {
                    "intent": intent,
                    "role": role,
                    "structured_data": structured_data,
                    "actions": actions,
                },
                "timestamp": time.time(),
            }, ensure_ascii=False)
            yield f"event: complete\ndata: {complete_data}\n\n"

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
