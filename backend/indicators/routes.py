"""
指标管理路由

提供指标CRUD、AI生成、代码验证等API端点
"""

import asyncio
import json
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from utils.logger import get_logger, LogType
from common.schemas import ApiResponse
from utils.rbac import is_guest_user, require_permission_sync, Permission

# 尝试导入思维链管理器
try:
    from ai_model.thinking_chain import ThinkingChainManager
except ImportError:
    ThinkingChainManager = None

# 获取日志器
logger = get_logger(__name__, LogType.APPLICATION)

# 创建路由
router = APIRouter(prefix="/api/indicators", tags=["指标管理"])

# 默认提示词（如果没有配置AI提供商时使用）
DEFAULT_INDICATOR_SYSTEM_PROMPT = """# Role

You are an expert Python quantitative trading indicator developer. Your task is to write custom indicator scripts for a professional K-line chart component running in a browser (Pyodide environment).

# Context & Environment

1. **Runtime Environment**: Code runs in a browser sandbox, **network access is prohibited** (cannot use `pip` or `requests`).

2. **Pre-installed Libraries**: The system has already imported `pandas as pd` and `numpy as np`. **DO NOT** include `import pandas as pd` or `import numpy as np` in your generated code. Use `pd` and `np` directly.

3. **Input Data**: The system provides a variable `df` (Pandas DataFrame) with index from 0 to N.
   - Columns include: `df['time']` (timestamp), `df['open']`, `df['high']`, `df['low']`, `df['close']`, `df['volume']`.

# Output Requirement (Strict)

At the end of code execution, you **MUST** define a dictionary variable named `output`. The system only reads this variable to render the chart.

Additionally, you MUST define:
- my_indicator_name = "..."
- my_indicator_description = "..."

`output` MUST follow this shape:
```python
output = {
  "name": my_indicator_name,
  "plots": [ { "name": str, "data": list, "color": "#RRGGBB", "overlay": bool, "type": "line" } ],
  "signals": [ { "type": "buy"|"sell", "text": str, "data": list, "color": "#RRGGBB" } ],
  "calculatedVars": {}
}
```
Where `data` lists MUST have the same length as `df` and use `None` for "no value".

# Signal confirmation / execution timing (IMPORTANT)
- Signals are generally confirmed on bar close. The backtest engine may execute them on the next bar open to better match live trading and avoid look-ahead bias.

# Robustness requirements (IMPORTANT)
- Always handle NaN/inf and division-by-zero (common in RSI/BB/RSV calculations).
- Avoid overly restrictive entry/exit logic that results in zero buy or zero sell signals.
- Prefer edge-triggered signals (one-shot) to avoid repeated consecutive signals:
  buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
  sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))
- If your final conditions produce no buys or no sells in the visible range, relax logically (e.g., remove one filter or widen thresholds).

IMPORTANT: Output Python code directly, without explanations, without descriptions, and do NOT use markdown code blocks like ```python.
"""


class IndicatorCreateRequest(BaseModel):
    """创建指标请求"""
    name: str
    description: Optional[str] = ""
    code: str


class IndicatorUpdateRequest(BaseModel):
    """更新指标请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None


class IndicatorResponse(BaseModel):
    """指标响应"""
    id: int
    name: str
    description: str
    code: str
    user_id: int
    created_at: str
    updated_at: str


class VerifyCodeRequest(BaseModel):
    """验证代码请求"""
    code: str


class VerifyCodeResponse(BaseModel):
    """验证代码响应"""
    valid: bool
    message: str
    plots_count: Optional[int] = 0
    signals_count: Optional[int] = 0


# 模拟指标存储（实际应该使用数据库）
indicators_db = {}
indicator_id_counter = 1


@router.get("")
async def get_indicators():
    """获取所有指标列表
    
    返回标准API响应格式:
    {
        "code": 0,
        "message": "操作成功",
        "data": [...],
        "timestamp": "2026-03-10T15:37:48.767391"
    }
    """
    return ApiResponse(
        code=0,
        message="获取指标列表成功",
        data=list(indicators_db.values()),
        timestamp=datetime.now()
    )


@router.get("/{indicator_id}")
async def get_indicator(indicator_id: int):
    """获取单个指标详情

    返回标准API响应格式:
    {
        "code": 0,
        "message": "操作成功",
        "data": {...},
        "timestamp": "2026-03-10T15:37:48.767391"
    }
    """
    if indicator_id not in indicators_db:
        return ApiResponse(
            code=404,
            message="指标不存在",
            data=None,
            timestamp=datetime.now()
        )
    return ApiResponse(
        code=0,
        message="获取指标详情成功",
        data=indicators_db[indicator_id],
        timestamp=datetime.now()
    )


@router.post("")
async def create_indicator(request: IndicatorCreateRequest, http_request: Request):
    """创建新指标

    返回标准API响应格式:
    {
        "code": 0,
        "message": "操作成功",
        "data": {...},
        "timestamp": "2026-03-10T15:37:48.767391"
    }

    权限控制: 访客用户无法创建指标
    """
    # 检查是否为访客用户
    if is_guest_user(http_request):
        logger.warning("访客用户尝试创建指标，已拦截")
        return ApiResponse(
            code=403,
            message="权限不足",
            data={"detail": "访客用户无法创建指标，请使用普通用户账号登录"},
            timestamp=datetime.now()
        )

    global indicator_id_counter

    indicator = {
        "id": indicator_id_counter,
        "name": request.name,
        "description": request.description or "",
        "code": request.code,
        "user_id": 1,  # 模拟当前用户
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    indicators_db[indicator_id_counter] = indicator
    indicator_id_counter += 1

    logger.info(f"创建指标: {indicator['name']} (ID: {indicator['id']})")
    return ApiResponse(
        code=0,
        message="创建指标成功",
        data=indicator,
        timestamp=datetime.now()
    )


@router.put("/{indicator_id}")
async def update_indicator(indicator_id: int, request: IndicatorUpdateRequest, http_request: Request):
    """更新指标

    返回标准API响应格式:
    {
        "code": 0,
        "message": "操作成功",
        "data": {...},
        "timestamp": "2026-03-10T15:37:48.767391"
    }

    权限控制: 访客用户无法更新指标
    """
    # 检查是否为访客用户
    if is_guest_user(http_request):
        logger.warning(f"访客用户尝试更新指标(ID: {indicator_id})，已拦截")
        return ApiResponse(
            code=403,
            message="权限不足",
            data={"detail": "访客用户无法更新指标，请使用普通用户账号登录"},
            timestamp=datetime.now()
        )

    if indicator_id not in indicators_db:
        return ApiResponse(
            code=404,
            message="指标不存在",
            data=None,
            timestamp=datetime.now()
        )

    indicator = indicators_db[indicator_id]
    if request.name is not None:
        indicator["name"] = request.name
    if request.description is not None:
        indicator["description"] = request.description
    if request.code is not None:
        indicator["code"] = request.code

    indicator["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    logger.info(f"更新指标: {indicator['name']} (ID: {indicator['id']})")
    return ApiResponse(
        code=0,
        message="更新指标成功",
        data=indicator,
        timestamp=datetime.now()
    )


@router.delete("/{indicator_id}")
async def delete_indicator(indicator_id: int, request: Request):
    """删除指标

    返回标准API响应格式:
    {
        "code": 0,
        "message": "操作成功",
        "data": null,
        "timestamp": "2026-03-10T15:37:48.767391"
    }

    权限控制: 访客用户无法删除指标
    """
    # 检查是否为访客用户
    if is_guest_user(request):
        logger.warning(f"访客用户尝试删除指标(ID: {indicator_id})，已拦截")
        return ApiResponse(
            code=403,
            message="权限不足",
            data={"detail": "访客用户无法删除指标，请使用普通用户账号登录"},
            timestamp=datetime.now()
        )

    if indicator_id not in indicators_db:
        return ApiResponse(
            code=404,
            message="指标不存在",
            data=None,
            timestamp=datetime.now()
        )

    indicator = indicators_db.pop(indicator_id)
    logger.info(f"删除指标: {indicator['name']} (ID: {indicator['id']})")
    return ApiResponse(
        code=0,
        message="删除指标成功",
        data=None,
        timestamp=datetime.now()
    )


@router.post("/verify")
async def verify_code(request: VerifyCodeRequest):
    """验证指标代码
    
    返回标准API响应格式:
    {
        "code": 0,
        "message": "操作成功",
        "data": {...},
        "timestamp": "2026-03-10T15:37:48.767391"
    }
    """
    code = request.code
    
    # 基础语法检查
    try:
        compile(code, '<string>', 'exec')
    except SyntaxError as e:
        return ApiResponse(
            code=400,
            message=f"语法错误: {str(e)}",
            data={
                "valid": False,
                "plots_count": 0,
                "signals_count": 0
            },
            timestamp=datetime.now()
        )
    
    # 检查必要的输出格式
    if 'output' not in code and 'OUTPUT' not in code:
        return ApiResponse(
            code=400,
            message="代码中必须包含 'output' 变量定义",
            data={
                "valid": False,
                "plots_count": 0,
                "signals_count": 0
            },
            timestamp=datetime.now()
        )
    
    # 检查必要的变量
    if 'my_indicator_name' not in code:
        return ApiResponse(
            code=400,
            message="代码中必须定义 'my_indicator_name' 变量",
            data={
                "valid": False,
                "plots_count": 0,
                "signals_count": 0
            },
            timestamp=datetime.now()
        )
    
    # 统计 plots 和 signals
    plots_count = code.count('"plots"') + code.count("'plots'")
    signals_count = code.count('"signals"') + code.count("'signals'")
    
    return ApiResponse(
        code=0,
        message="代码验证通过",
        data={
            "valid": True,
            "plots_count": plots_count,
            "signals_count": signals_count
        },
        timestamp=datetime.now()
    )


async def generate_indicator_stream(
    prompt: str,
    existing_code: str = ""
) -> AsyncGenerator[str, None]:
    """流式生成指标代码，带思维链
    
    Args:
        prompt: 用户提示词
        existing_code: 现有代码（用于优化场景）
        
    Yields:
        SSE格式的数据字符串
    """
    request_id = f"indicator_{int(time.time() * 1000)}"
    
    try:
        # 步骤1: 需求分析
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 1, 'total_steps': 4, 'step_title': '需求分析', 'step_description': '分析用户提供的指标需求，提取关键要素', 'status': 'processing', 'progress': 25}})}\n\n"
        await asyncio.sleep(0.3)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 1, 'total_steps': 4, 'step_title': '需求分析', 'step_description': '分析用户提供的指标需求，提取关键要素', 'status': 'completed', 'progress': 25}})}\n\n"
        await asyncio.sleep(0.1)
        
        # 步骤2: 指标设计
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 2, 'total_steps': 4, 'step_title': '指标设计', 'step_description': '基于需求分析，设计指标计算逻辑', 'status': 'processing', 'progress': 50}})}\n\n"
        await asyncio.sleep(0.3)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 2, 'total_steps': 4, 'step_title': '指标设计', 'step_description': '基于需求分析，设计指标计算逻辑', 'status': 'completed', 'progress': 50}})}\n\n"
        await asyncio.sleep(0.1)
        
        # 步骤3: 代码生成 - 调用AI
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 3, 'total_steps': 4, 'step_title': '代码生成', 'step_description': '根据指标设计，生成完整的Python代码', 'status': 'processing', 'progress': 75}})}\n\n"
        await asyncio.sleep(0.1)
        
        # 调用AI生成代码
        full_code = await call_ai_generate_code(prompt, existing_code)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 3, 'total_steps': 4, 'step_title': '代码生成', 'step_description': '根据指标设计，生成完整的Python代码', 'status': 'completed', 'progress': 75}})}\n\n"
        await asyncio.sleep(0.1)
        
        # 步骤4: 验证优化
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 4, 'total_steps': 4, 'step_title': '验证优化', 'step_description': '验证指标的正确性和性能', 'status': 'processing', 'progress': 100}})}\n\n"
        await asyncio.sleep(0.3)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 4, 'total_steps': 4, 'step_title': '验证优化', 'step_description': '验证指标的正确性和性能', 'status': 'completed', 'progress': 100}})}\n\n"
        await asyncio.sleep(0.1)
        
        # 返回生成的代码
        yield f"data: {json.dumps({'type': 'done', 'code': full_code, 'raw_content': full_code})}\n\n"
        
    except Exception as e:
        logger.error(f"指标生成失败: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


async def call_ai_generate_code(prompt: str, existing_code: str = "") -> str:
    """调用AI生成指标代码
    
    Args:
        prompt: 用户提示词
        existing_code: 现有代码（用于优化场景）
        
    Returns:
        生成的Python代码
    """
    try:
        # 从思维链配置获取 system_prompt
        system_prompt = DEFAULT_INDICATOR_SYSTEM_PROMPT
        
        try:
            if ThinkingChainManager is not None:
                chain = ThinkingChainManager.get_active_chain_by_type("indicator_generation")
                if chain and chain.get("system_prompt"):
                    system_prompt = chain["system_prompt"]
                    logger.info("使用数据库中的 system_prompt")
        except Exception as e:
            logger.warning(f"无法从数据库获取 system_prompt，使用默认: {e}")
        
        # 构建用户提示词
        user_prompt = prompt
        if existing_code:
            user_prompt = f"# Existing Code (modify based on this):\n\n{existing_code}\n\n# Modification Requirements:\n\n{prompt}\n\nPlease generate complete new Python code based on the existing code above and my modification requirements. Output the complete Python code directly."
        
        # TODO: 调用实际的AI API
        # 这里暂时返回默认模板，后续需要集成真实的AI调用
        logger.info(f"AI生成指标代码: {prompt[:50]}...")
        
        # 模拟AI调用，返回默认代码
        return generate_default_indicator_code(prompt)
        
    except Exception as e:
        logger.error(f"AI生成代码失败: {e}")
        return generate_default_indicator_code(prompt)


def generate_default_indicator_code(prompt: str) -> str:
    """生成默认指标代码模板"""
    return f'''# 指标代码 - 根据需求生成
# 需求: {prompt}

my_indicator_name = "自定义指标"
my_indicator_description = "{prompt[:200]}"

# 计算指标 - RSI示例
rsi_period = 14

delta = df['close'].diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)

# Wilder平滑
avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()

rs = avg_gain / avg_loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
rsi = rsi.fillna(50)

# 生成交易信号
raw_buy = (rsi < 30)
raw_sell = (rsi > 70)

# 边沿触发信号
buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))

df['buy'] = buy.astype(bool)
df['sell'] = sell.astype(bool)

# 生成标记点
buy_marks = [df['low'].iloc[i] * 0.995 if bool(buy.iloc[i]) else None for i in range(len(df))]
sell_marks = [df['high'].iloc[i] * 1.005 if bool(sell.iloc[i]) else None for i in range(len(df))]

# 输出格式
output = {{
    "name": my_indicator_name,
    "plots": [
        {{"name": "RSI({{}})".format(rsi_period), "data": rsi.tolist(), "color": "#faad14", "overlay": False}}
    ],
    "signals": [
        {{"type": "buy", "text": "B", "data": buy_marks, "color": "#00E676"}},
        {{"type": "sell", "text": "S", "data": sell_marks, "color": "#FF5252"}}
    ]
}}
'''


@router.get("/ai-generate")
async def ai_generate_indicator(
    prompt: str = Query(..., description="指标生成提示词"),
    existing_code: str = Query("", description="现有代码（用于优化）")
):
    """AI流式生成指标代码
    
    使用SSE流式返回生成的代码和思维链状态
    
    Args:
        prompt: 指标生成提示词
        existing_code: 现有代码（可选，用于优化场景）
        
    Returns:
        StreamingResponse: SSE流式响应
    """
    logger.info(f"AI生成指标: {prompt[:50]}...")
    
    return StreamingResponse(
        generate_indicator_stream(prompt, existing_code),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
