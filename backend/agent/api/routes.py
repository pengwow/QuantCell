"""Agent API 路由"""

import asyncio
import json
import re
import time
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config.capabilities import Capability, require_capability
from utils.auth import get_current_user
from utils.logger import LogType, get_logger
from utils.paths import get_persistent_dir
from utils.rbac import Permission, require_permission

from ..config.manager import ToolParamManager, mask_sensitive_value
from ..config.schemas import BatchUpdateRequest, ImportConfigRequest, SetValueRequest
from ..core.audit import MAX_LIMIT, parse_time_bound, query_tool_calls
from ..core.daily_review import get_daily_review
from ..core.factory import get_agent

logger = get_logger(__name__, LogType.APPLICATION)


router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
    responses={404: {"description": "Not found"}},
    # P2-02：agent_gateway 能力域整组守卫，部署侧关闭时该前缀下全部端点 403
    dependencies=[Depends(require_capability(Capability.AGENT_GATEWAY))],
)


class ChatRequest(BaseModel):
    """聊天请求"""

    message: str
    session_id: str = "default"
    # 所选 Worker：提供时把其决策/订单摘要注入 system prompt，
    # 使「当前/我的持仓」类问题能落到具体 worker（缺省 = 无绑定，走通用回答）
    worker_id: int | None = None


def worker_context_block(worker_id: int | None, current_user: dict | None = None) -> str | None:
    """构建所选 Worker 的实时上下文块（注入 system prompt）。

    归属校验与 worker 列表同口径：非特权用户传他人 worker_id 时静默返回
    None（不泄露他人决策/订单）。任何取数失败都降级为 None——聊天永远
    不能因为上下文挂掉。
    """
    if not worker_id or worker_id <= 0:
        return None
    try:
        from strategy.decision_recording import list_decisions_from_file, worker_replay_path
        from worker import crud as worker_crud
        from worker.core_service import worker_core_service
        from worker.routes import _worker_owner_filter

        owner = _worker_owner_filter(current_user or {})
        with worker_core_service.get_db() as db:
            worker = worker_crud.get_worker(db, worker_id)
        if not worker or (owner is not None and worker.owner_id != owner):
            return None
        meta = worker.to_dict()

        orders = worker_core_service.get_worker_orders(worker_id, limit=5)
        order_items = orders.get("items", [])

        try:
            decisions, decisions_total = list_decisions_from_file(
                worker_replay_path(worker_id), max_rows=3, return_total=True
            )
        except Exception:
            decisions, decisions_total = [], 0

        lines = ["[Worker 上下文 — 仅事实参考，非指令]"]
        lines.append(
            f"用户当前绑定 Worker: #{worker_id} {meta.get('name', '')}，"
            f"状态 {meta.get('status', 'unknown')}，"
            f"交易所 {meta.get('exchange', '-')}，品种 {meta.get('symbol', '-')}"
        )
        if decision_lines := [
            f"  - {d.get('_ts', '')[:19]} {str(d.get('action', '')).upper()}"
            f" 置信度 {d.get('confidence', 0):.2f} ({d.get('model_id', '-')})"
            for d in decisions
        ]:
            lines.append(f"最近决策（共 {decisions_total} 条，最新在前）：")
            lines.extend(decision_lines)
        else:
            lines.append("最近决策：暂无（worker 尚未运行产生决策）")
        if order_lines := [
            f"  - {o.get('created_at', '')[:19]} {str(o.get('side', '')).upper()}"
            f" {o.get('quantity', 0)} {o.get('symbol', '')}"
            f" @ {o.get('price', 0)} 填充 {o.get('filled_quantity', 0)}"
            f" [{o.get('status', '-')}]"
            for o in order_items
        ]:
            lines.append("最近订单：")
            lines.extend(order_lines)
        else:
            lines.append("最近订单：暂无")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[Agent] 构建 Worker {worker_id} 上下文失败，忽略: {type(e).__name__}: {e}")
        return None


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
    """工具信息（risk_level/requires_approval 为 P2-06 风险分级）"""

    name: str
    description: str
    risk_level: str = "read"
    requires_approval: bool = False


# 预编译正则表达式（缓存以提高性能）
_CODE_BLOCK_REGEX = re.compile(r"```(python)?\s*\n(.*?)```", re.DOTALL)
_STRATEGY_NAME_REGEX = re.compile(r"策略名称[：:]\s*(.+?)\n")
_RISK_LEVEL_REGEX = re.compile(r"风险等级[：:]\s*(.+?)\n")


# 意图关键词映射（按优先级排序，优先级高的在前）
# 每个意图包含：(关键词, 权重)，权重越高匹配越优先
_INTENT_KEYWORDS = [
    # 风险评估（优先于策略生成，因为"评估策略风险"应该是风险评估）
    (
        IntentCategory.RISK_ASSESSMENT,
        [
            ("风险评估", 3),
            ("评估风险", 3),
            ("风控", 2),
            ("回撤", 2),
            ("止损", 2),
            ("风险等级", 3),
            ("风险分析", 3),
            ("risk", 1),
            ("risk assessment", 2),
        ],
    ),
    # 回测（完整短语优先）
    (
        IntentCategory.BACKTEST,
        [
            ("历史回测", 3),
            ("回测结果", 3),
            ("回测分析", 3),
            ("测试策略", 2),
            ("backtest", 2),
            ("回测", 1),
        ],
    ),
    # RL训练
    (
        IntentCategory.RL_TRAINING,
        [
            ("强化学习", 2),
            ("rl训练", 2),
            ("ppo", 2),
            ("sac", 2),
            ("dqn", 2),
            ("train", 1),
            ("训练", 1),
        ],
    ),
    # 交易决策
    (
        IntentCategory.TRADING_DECISION,
        [
            ("下单交易", 2),
            ("买入", 1),
            ("卖出", 1),
            ("buy", 1),
            ("sell", 1),
            ("持仓", 1),
            ("平仓", 1),
            ("交易", 1),
        ],
    ),
    # 策略生成（完整短语优先，避免被单独的"策略"关键词误匹配）
    (
        IntentCategory.STRATEGY_GENERATION,
        [
            ("生成策略", 3),
            ("写策略", 3),
            ("创建策略", 3),
            ("策略代码", 3),
            ("策略模板", 3),
            ("strategy", 1),
        ],
    ),
    # 数据查询
    (
        IntentCategory.DATA_QUERY,
        [
            ("查询数据", 2),
            ("查看行情", 2),
            ("k线", 2),
            ("走势", 1),
            ("价格", 1),
            ("数据", 1),
            ("行情", 1),
            ("查询", 1),
        ],
    ),
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
                if re.search(rf"(?:^|\W){re.escape(keyword.lower())}(?:$|\W)", message_lower):
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
        _BACKTEST_METRIC_REGEX = re.compile(r"(年化收益率|夏普比率|最大回撤|总收益|胜率)[：:]\s*([\d.]+)")
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


@router.post(
    "/chat",
    response_model=ChatResponse,
    # P1-07 权限灰度：/api/v1/agent/* 全量挂载，读走 AI_READ、变更走 AI_WRITE
    # （enforcement off 时依赖直接放行，行为与未挂载一致）
    dependencies=[Depends(require_permission(Permission.AI_WRITE))],
)
async def chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    与 Agent 进行对话

    - **message**: 用户消息
    - **session_id**: 会话标识（可选，默认为 default）
    - **worker_id**: Worker 编号（可选，提供时注入其决策/订单摘要）

    返回包含意图分类、角色类型、建议操作和结构化数据的响应
    """
    try:
        agent = get_agent()
        response = await agent.process_message(
            content=request.message,
            session_key=request.session_id,
            extra_context=worker_context_block(request.worker_id, current_user),
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


@router.post("/chat/stream", dependencies=[Depends(require_permission(Permission.AI_WRITE))])
async def chat_stream(request: ChatRequest, current_user: dict = Depends(get_current_user)):
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
        fetch('/api/v1/agent/chat/stream', {
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
            start_data = json.dumps(
                {
                    "type": "start",
                    "data": {
                        "intent": intent,
                        "role": role,
                        "message": request.message,
                    },
                    "timestamp": time.time(),
                },
                ensure_ascii=False,
            )
            yield f"event: start\ndata: {start_data}\n\n"
            await asyncio.sleep(0)

            async for event in agent.iter_message_stream(
                content=request.message,
                session_key=request.session_id,
                extra_context=worker_context_block(request.worker_id, current_user),
            ):
                # 累积内容用于后续结构化数据提取（loop 的 content 事件 data 是
                # dict：{"content": 增量, "full_content": 累计}——直接 += 会抛
                # "can only concatenate str (not \"dict\") to str"）
                if event.event_type == "content" and event.data:
                    accumulated_content += (
                        event.data.get("content", "") if isinstance(event.data, dict) else str(event.data)
                    )

                # 格式化为 SSE 事件
                event_data = json.dumps(
                    {
                        "type": event.event_type,
                        "data": event.data,
                        "timestamp": event.timestamp,
                    },
                    ensure_ascii=False,
                )

                yield f"event: {event.event_type}\ndata: {event_data}\n\n"

                # 确保缓冲区刷新，让客户端能及时收到数据
                await asyncio.sleep(0)

            # 发送 complete 事件（包含结构化数据和建议操作）
            structured_data = extract_structured_data(accumulated_content, intent)
            actions = build_actions(intent)

            complete_data = json.dumps(
                {
                    "type": "complete",
                    "data": {
                        "intent": intent,
                        "role": role,
                        "structured_data": structured_data,
                        "actions": actions,
                    },
                    "timestamp": time.time(),
                },
                ensure_ascii=False,
            )
            yield f"event: complete\ndata: {complete_data}\n\n"

        except Exception as e:
            # 发送错误事件
            error_data = json.dumps(
                {
                    "type": "error",
                    "data": {"error": str(e), "timestamp": time.time()},
                },
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保实时传输
            "Access-Control-Allow-Origin": "*",  # 允许跨域访问
        },
    )


@router.get("/tools", response_model=list[ToolInfo], dependencies=[Depends(require_permission(Permission.AI_READ))])
async def list_tools():
    """获取所有可用工具列表"""
    try:
        agent = get_agent()
        tools = []
        for name in agent.tools.tool_names:
            tool = agent.tools.get(name)
            if tool:
                tools.append(
                    ToolInfo(
                        name=name,
                        description=tool.description,
                        risk_level=tool.risk_level,
                        requires_approval=tool.requires_approval,
                    )
                )
        return tools
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/clear", dependencies=[Depends(require_permission(Permission.AI_WRITE))])
async def clear_session(session_id: str):
    try:
        agent = get_agent()
        agent.sessions.clear_session(session_id)
        return {"success": True, "message": f"会话 {session_id} 已清空"}
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/history", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_session_history(session_id: str, limit: int = 50):
    try:
        agent = get_agent()
        result = agent.sessions.get_history(session_id, limit)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"获取会话历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}", dependencies=[Depends(require_permission(Permission.AI_WRITE))])
async def delete_session(session_id: str):
    try:
        agent = get_agent()
        success = agent.sessions.delete(session_id)

        if success:
            return {
                "success": True,
                "message": f"会话 {session_id} 已删除",
                "warning": "该会话的历史消息已永久删除，但已整合的长期记忆仍保留在 MEMORY.md 中",
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", dependencies=[Depends(require_permission(Permission.AI_READ))])
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


@router.post("/sessions", dependencies=[Depends(require_permission(Permission.AI_WRITE))])
async def create_session(request: CreateSessionRequest):
    try:
        agent = get_agent()
        session_info = agent.sessions.create_session(request.name)
        return {"success": True, "session": session_info}
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_session(session_id: str):
    try:
        agent = get_agent()
        session_info = agent.sessions.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"success": True, "session": session_info}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 每日复盘 API ====================


@router.get("/daily-review", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_daily_review_report(
    date_str: str | None = Query(None, alias="date", description="复盘日期 YYYY-MM-DD，默认昨天"),
    llm: bool = Query(False, description="是否追加 LLM 自然语言摘要（不可用时降级为模板文本）"),
):
    """每日复盘报告：数据聚合 + 模板/LLM 摘要。

    sections 为确定性数据（worker 盈亏/持仓/订单、决策录制、模型 OOS 门槛、风控建议），
    风控建议只读评估并给出建议额度，不写任何风控参数/不热更引擎；
    meta.mode 区分 template / llm / template_fallback，degraded=True 表示 LLM 请求失败已兜底。
    复盘入聊天流由调度器完成（assistant 消息 + meta.kind=daily_review），本端点只读不发布。
    """
    try:
        report = await asyncio.to_thread(get_daily_review, date_str, use_llm=llm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"生成每日复盘失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, **report}


# ==================== 自迭代（Loop）状态 API ====================

#: Agent 工作区（与 agent/core/factory.py::get_agent 同口径；桌面=持久数据目录）
_AGENT_WORKSPACE = get_persistent_dir(
    "data/agent_workspace",
    Path(__file__).parent.parent.parent / "data" / "agent_workspace",
)

#: 自迭代链路四个 job：(id, 展示名, cron 文案)；cron 文案与 core/scheduler.py 手写对齐
_LOOP_JOBS = (
    ("rl_oos_gate_audit", "RL OOS gate audit", "每日 03:30"),
    ("agent_daily_review", "Agent daily review", "每日 03:35"),
    ("rl_auto_retrain", "RL auto retrain (closed loop)", "每日 03:40"),
    ("agent_dream", "Agent dream (memory self-edit)", "每日 04:00"),
)


def _read_text_or(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, ValueError:
        return default


def _next_run_at(scheduler: object, job_id: str, mounted: set[str]) -> str | None:
    """从真实挂载的调度器 job 取 ``next_run_time``（ISO8601）；取不到返回 None。

    scheduler 传进来而不是内部再取，单测可以直接塞假实例；未挂载的 job 不必查询
    （没挂的 cron 没有「下次」）。调度器已 shutdown 时 APScheduler 会抛
    SchedulerNotRunningError，同样按「取不到」处理，不让展示层连带 500。
    """
    if scheduler is None or job_id not in mounted:
        return None
    try:
        job = scheduler.get_job(job_id)  # type: ignore[attr-defined]
    except Exception:
        return None
    next_run = getattr(job, "next_run_time", None) if job is not None else None
    return next_run.isoformat() if next_run is not None else None


def _lifecycle_families() -> list[dict]:
    """lifecycle_state.json → 每族一行（缺失/损坏一律 []，不猜字段）。

    shadow 台账条目只有 date/winner/engine/degraded/error，没有 status：
    有 promotion 记录就用它的 status，否则给 lifecycle 结果里同义的 shadow_running。
    其余字段映射不了的，原样塞进 note（截断 200 字），不新造字段。
    """
    try:
        from rl.lifecycle import load_lifecycle_state

        state = load_lifecycle_state()
    except Exception:
        return []
    shadow = state.get("shadow") if isinstance(state.get("shadow"), dict) else {}
    promo_status = {
        str(rec["family"]): str(rec.get("status") or "")
        for rec in state.get("promotions") or []
        if isinstance(rec, dict) and rec.get("family")
    }
    families: list[dict] = []
    for family in [*shadow, *(f for f in promo_status if f not in shadow)]:
        entries = [e for e in (shadow.get(family) or []) if isinstance(e, dict)]
        last = entries[-1] if entries else {}
        item: dict = {"family": family, "status": promo_status.get(family) or "shadow_running"}
        days = {str(e["date"]) for e in entries if e.get("date")}
        if days:
            item["shadow_days"] = len(days)
        raw = {k: last[k] for k in ("winner", "engine", "degraded", "error") if last.get(k) is not None}
        if raw:
            item["note"] = str(raw)[:200]
        families.append(item)
    return families


@router.get("/memory", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_agent_memory():
    """记忆自迭代只读视图：MEMORY.md 全文 / Dream 游标 / 历史条数 / 上次运行。

    全部软失败（缺文件给空值），进程内 LAST_RUNS 重启即空属预期。
    """
    from core.scheduler import get_last_runs
    from services.retrain_policy import env_flag

    memory_dir = _AGENT_WORKSPACE / "memory"
    try:
        dream_cursor = int(_read_text_or(memory_dir / ".dream_cursor").strip() or 0)
    except ValueError:
        dream_cursor = 0
    history_entries = 0
    try:
        with open(memory_dir / "history.jsonl", encoding="utf-8") as f:
            history_entries = sum(1 for _ in f)
    except OSError:
        pass
    return {
        "success": True,
        "enabled": env_flag("QUANTCELL_AGENT_DREAM"),
        "memory_markdown": _read_text_or(memory_dir / "MEMORY.md"),
        "dream_cursor": dream_cursor,
        "history_entries": history_entries,
        "last_run": get_last_runs().get("agent_dream"),
    }


@router.get("/loop-status", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_loop_status():
    """自迭代四个 job 的挂载/上次运行/下次运行 + 重训双闸 + 各族状态。

    mounted 与 last_run 都来自本进程内存（core.scheduler），重启后为空/未挂。
    next_run_at 直接取真实挂载的 APScheduler job 的 ``next_run_time``（ISO8601）；
    未挂载 / 调度器未启动 / job 取不到一律 null —— 不解析 cron 猜时间。
    """
    from core.scheduler import MOUNTED_JOBS, get_last_runs, get_scheduler
    from services.retrain_policy import auto_promote_enabled, auto_retrain_enabled

    last_runs = get_last_runs()
    scheduler = get_scheduler()
    return {
        "success": True,
        "jobs": [
            {
                "id": job_id,
                "name": name,
                "cron": cron,
                "mounted": job_id in MOUNTED_JOBS,
                "last_run": last_runs.get(job_id),
                "next_run_at": _next_run_at(scheduler, job_id, MOUNTED_JOBS),
            }
            for job_id, name, cron in _LOOP_JOBS
        ],
        "retrain": {
            "gates": {
                "auto_retrain": auto_retrain_enabled(),
                "auto_promote": auto_promote_enabled(),
            },
            "families": _lifecycle_families(),
        },
    }


# ==================== 工具调用审计 API ====================


@router.get("/audit", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def list_tool_audit(
    start: str | None = Query(None, description="起始时间（ISO8601 或 epoch 秒/毫秒，含边界）"),
    end: str | None = Query(None, description="结束时间（ISO8601 或 epoch 秒/毫秒，含边界）"),
    tool: str | None = Query(None, description="工具名（前缀匹配，传完整工具名即精确）"),
    result_status: str | None = Query(None, description="结果状态，如 success / error / blocked_scope"),
    user: str | None = Query(None, description="调用方（JWT sub 或 token 名称）"),
    token: str | None = Query(None, description='令牌来源："jwt" 或 "#<token_id>"'),
    limit: int = Query(50, ge=1, description="每页条数（上限 500，超出按 500 截断）"),
    offset: int = Query(0, ge=0, description="分页偏移"),
):
    """查询工具调用审计（P2-06 落库表 agent_tool_audit），created_at 倒序。

    args_redacted 落库时已脱敏，原样返回；args_hash 为参数摘要，供等幂比对。
    """
    limit = min(limit, MAX_LIMIT)
    try:
        total, audits = query_tool_calls(
            start=parse_time_bound(start, name="start"),
            end=parse_time_bound(end, name="end"),
            tool=tool,
            result_status=result_status,
            user=user,
            token=token,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询工具调用审计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "total": total, "limit": limit, "offset": offset, "audits": audits}


# ==================== 工具参数管理 API ====================


@router.get("/tools/params/tools", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_registered_tools():
    """获取所有已注册的工具列表及其参数状态"""
    try:
        tools = ToolParamManager.get_registered_tools()
        return {"code": 200, "data": tools}
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/params/{tool_name}", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def get_tool_params(
    tool_name: str,
    include_sensitive: bool = Query(False, description="是否包含敏感参数真实值"),
):
    """获取指定工具的参数配置"""
    try:
        params = ToolParamManager.get_tool_params(tool_name, include_sensitive=include_sensitive)
        return {"code": 200, "data": {"tool_name": tool_name, "params": params}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取工具参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/tools/params/{tool_name}/{param_name}",
    dependencies=[Depends(require_permission(Permission.AI_WRITE))],
)
async def set_tool_param(tool_name: str, param_name: str, request: SetValueRequest):
    """设置工具参数"""
    try:
        success = ToolParamManager.set_tool_param(tool_name, param_name, request.value)

        if success:
            return {
                "code": 200,
                "message": "参数更新成功",
                "data": {
                    "param_name": param_name,
                    "value_masked": mask_sensitive_value(str(request.value))
                    if ToolParamManager.get_tool_params(tool_name, include_sensitive=False)
                    .get(param_name, {})
                    .get("sensitive")
                    else str(request.value),
                    "updated_at": datetime.now().isoformat(),
                },
            }
        else:
            raise HTTPException(status_code=500, detail="保存失败")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"设置工具参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/params/{tool_name}/batch", dependencies=[Depends(require_permission(Permission.AI_WRITE))])
async def batch_update_params(tool_name: str, request: BatchUpdateRequest):
    """批量更新工具参数"""
    try:
        result = ToolParamManager.batch_update(tool_name, request.params, overwrite=request.overwrite)

        return {
            "code": 200,
            "message": f"成功更新 {len(result['updated'])} 个参数",
            "data": result,
        }

    except Exception as e:
        logger.error(f"批量更新参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/tools/params/{tool_name}/{param_name}",
    dependencies=[Depends(require_permission(Permission.AI_WRITE))],
)
async def delete_tool_param(tool_name: str, param_name: str):
    """删除工具参数"""
    try:
        success = ToolParamManager.delete_tool_param(tool_name, param_name)

        if success:
            return {"code": 200, "message": "参数已删除，将使用默认值或环境变量"}
        else:
            raise HTTPException(status_code=404, detail="参数不存在")

    except Exception as e:
        logger.error(f"删除工具参数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/params/export", dependencies=[Depends(require_permission(Permission.AI_READ))])
async def export_config(
    tool_name: str | None = Query(None, description="工具名称，不传则导出全部"),
):
    """导出配置"""
    try:
        config = ToolParamManager.export_config(tool_name)
        return {"code": 200, "data": config}
    except Exception as e:
        logger.error(f"导出配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/params/import", dependencies=[Depends(require_permission(Permission.AI_WRITE))])
async def import_config(request: ImportConfigRequest):
    """导入配置"""
    try:
        imported, skipped, errors = ToolParamManager.import_config(request.config, overwrite=request.overwrite)

        return {
            "code": 200,
            "data": {"imported": imported, "skipped": skipped, "errors": errors},
        }

    except Exception as e:
        logger.error(f"导入配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
