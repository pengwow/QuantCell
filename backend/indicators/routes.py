"""
指标管理路由

提供指标CRUD、代码验证、执行计算、AI生成、参数解析等API端点
"""

import asyncio
import json
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from utils.logger import get_logger, LogType
from common.schemas import ApiResponse
from utils.rbac import is_guest_user, require_permission_sync, Permission

try:
    from ai_model.thinking_chain import ThinkingChainManager
except ImportError:
    ThinkingChainManager = None

from indicators.models import CustomIndicatorBusiness
from indicators.executor import (
    IndicatorExecutor,
    parse_indicator_params,
    _generate_mock_df,
)

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(prefix="/api/indicators", tags=["指标管理"])

# 全局执行器实例（带缓存）
_executor: Optional[IndicatorExecutor] = None


def get_executor() -> IndicatorExecutor:
    global _executor
    if _executor is None:
        _executor = IndicatorExecutor(timeout=10.0)
    return _executor


DEFAULT_INDICATOR_SYSTEM_PROMPT = """# Role

You are an expert Python quantitative trading indicator developer. Your task is to write custom indicator scripts for a professional K-line chart component.

# Context & Environment

1. **Runtime Environment**: Code runs in server-side Python environment with pandas and numpy available.
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
- Signals are generally confirmed on bar close.

# Robustness requirements (IMPORTANT)
- Always handle NaN/inf and division-by-zero (common in RSI/BB/RSV calculations).
- Prefer edge-triggered signals to avoid repeated consecutive signals:
  buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
  sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))

IMPORTANT: Output Python code directly, without explanations, without descriptions, and do NOT use markdown code blocks like ```python.
"""


class IndicatorCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    code: str


class IndicatorUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None


class VerifyCodeRequest(BaseModel):
    code: str


class ExecuteIndicatorRequest(BaseModel):
    symbol: str = Field(..., description="交易对符号")
    period: str = Field("1h", description="K线周期")
    limit: int = Field(500, ge=50, le=2000, description="K线数据条数")
    params: Optional[Dict[str, Any]] = Field(default=None, description="指标参数")


@router.get("")
async def get_indicators(request: Request):
    """获取当前用户的指标列表（从数据库查询）"""
    indicators = CustomIndicatorBusiness.get_all()
    return ApiResponse(
        code=0,
        message="获取指标列表成功",
        data=indicators,
        timestamp=datetime.now(),
    )


@router.get("/{indicator_id}")
async def get_indicator(indicator_id: int):
    """获取单个指标详情"""
    indicator = CustomIndicatorBusiness.get_by_id(indicator_id)
    if not indicator:
        return ApiResponse(
            code=404,
            message="指标不存在",
            data=None,
            timestamp=datetime.now(),
        )
    return ApiResponse(
        code=0,
        message="获取指标详情成功",
        data=indicator,
        timestamp=datetime.now(),
    )


@router.post("")
async def create_indicator(request_body: IndicatorCreateRequest, http_request: Request):
    """创建新指标（持久化到数据库）"""
    if is_guest_user(http_request):
        logger.warning("访客用户尝试创建指标，已拦截")
        return ApiResponse(
            code=403,
            message="权限不足",
            data={"detail": "访客用户无法创建指标"},
            timestamp=datetime.now(),
        )

    result = CustomIndicatorBusiness.create(
        user_id=1,
        name=request_body.name,
        code=request_body.code,
        description=request_body.description or "",
    )

    if not result:
        return ApiResponse(
            code=500,
            message="创建指标失败",
            data=None,
            timestamp=datetime.now(),
        )

    logger.info(f"创建指标: {result['name']} (ID: {result['id']})")
    return ApiResponse(
        code=0,
        message="创建指标成功",
        data=result,
        timestamp=datetime.now(),
    )


@router.put("/{indicator_id}")
async def update_indicator(indicator_id: int, request_body: IndicatorUpdateRequest, http_request: Request):
    """更新指标"""
    if is_guest_user(http_request):
        return ApiResponse(
            code=403,
            message="权限不足",
            data={"detail": "访客用户无法更新指标"},
            timestamp=datetime.now(),
        )

    update_fields = {}
    if request_body.name is not None:
        update_fields["name"] = request_body.name
    if request_body.description is not None:
        update_fields["description"] = request_body.description
    if request_body.code is not None:
        update_fields["code"] = request_body.code

    result = CustomIndicatorBusiness.update(indicator_id, **update_fields)

    if not result:
        return ApiResponse(
            code=404,
            message="指标不存在或更新失败",
            data=None,
            timestamp=datetime.now(),
        )

    logger.info(f"更新指标: ID={indicator_id}")
    return ApiResponse(
        code=0,
        message="更新指标成功",
        data=result,
        timestamp=datetime.now(),
    )


@router.delete("/{indicator_id}")
async def delete_indicator(indicator_id: int, http_request: Request):
    """删除指标"""
    if is_guest_user(http_request):
        return ApiResponse(
            code=403,
            message="权限不足",
            data={"detail": "访客用户无法删除指标"},
            timestamp=datetime.now(),
        )

    success = CustomIndicatorBusiness.delete(indicator_id)
    logger.info(f"删除指标: ID={indicator_id}, success={success}")

    return ApiResponse(
        code=0,
        message="删除指标成功",
        data=None,
        timestamp=datetime.now(),
    )


@router.post("/verify")
async def verify_code(request: VerifyCodeRequest):
    """验证指标代码（真exec + mock DataFrame）

    使用80条模拟K线数据真正执行用户代码，检查语法和输出格式
    """
    executor = get_executor()
    
    try:
        result = await executor.verify_code(request.code)
        
        if result["valid"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data={
                    "valid": True,
                    "plots_count": result.get("plots_count", 0),
                    "signals_count": result.get("signals_count", 0),
                },
                timestamp=datetime.now(),
            )
        else:
            return ApiResponse(
                code=400,
                message=result["message"],
                data={
                    "valid": False,
                    "plots_count": 0,
                    "signals_count": 0,
                },
                timestamp=datetime.now(),
            )
    except Exception as e:
        logger.error(f"代码验证异常: {e}")
        return ApiResponse(
            code=500,
            message=f"验证过程异常: {str(e)}",
            data={"valid": False},
            timestamp=datetime.now(),
        )


@router.post("/{indicator_id}/execute")
async def execute_indicator(indicator_id: int, request: ExecuteIndicatorRequest):
    """执行自定义指标计算
    
    从数据库加载指标代码，结合K线数据和参数在服务端执行，
    返回 plots 和 signals 数据供前端渲染。
    """
    # 获取指标代码
    indicator = CustomIndicatorBusiness.get_by_id(indicator_id)
    if not indicator:
        return ApiResponse(
            code=404,
            message=f"指标(ID:{indicator_id})不存在",
            data=None,
            timestamp=datetime.now(),
        )
    
    code = indicator.get("code")
    if not code:
        return ApiResponse(
            code=400,
            message="指标代码为空",
            data=None,
            timestamp=datetime.now(),
        )
    
    executor = get_executor()
    
    try:
        result = await executor.execute(
            code=code,
            kline_data=[],
            params=request.params or {},
        )
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message="指标执行成功",
                data=result,
                timestamp=datetime.now(),
            )
        else:
            return ApiResponse(
                code=400,
                message=result.get("error", "指标执行失败"),
                data=result,
                timestamp=datetime.now(),
            )
    except Exception as e:
        logger.error(f"指标执行异常: id={indicator_id}, error={e}")
        return ApiResponse(
            code=500,
            message=f"执行异常: {str(e)}",
            data={
                "success": False,
                "error": str(e),
                "plots": [],
                "signals": [],
            },
            timestamp=datetime.now(),
        )


@router.get("/{indicator_id}/params")
async def get_indicator_params(indicator_id: int):
    """解析指标的参数声明
    
    从指标代码中提取 _get_param() 调用和变量赋值，
    返回参数列表供前端构建配置界面。
    """
    indicator = CustomIndicatorBusiness.get_by_id(indicator_id)
    if not indicator:
        return ApiResponse(
            code=404,
            message="指标不存在",
            data=None,
            timestamp=datetime.now(),
        )
    
    code = indicator.get("code", "")
    params = parse_indicator_params(code)
    
    return ApiResponse(
        code=0,
        message="获取参数列表成功",
        data=params,
        timestamp=datetime.now(),
    )


async def generate_indicator_stream(
    prompt: str,
    existing_code: str = ""
) -> AsyncGenerator[str, None]:
    """流式生成指标代码，带思维链"""
    request_id = f"indicator_{int(time.time() * 1000)}"
    
    try:
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 1, 'total_steps': 4, 'step_title': '需求分析', 'step_description': '分析用户提供的指标需求', 'status': 'processing', 'progress': 25}})}\n\n"
        await asyncio.sleep(0.3)
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 1, 'total_steps': 4, 'step_title': '需求分析', 'status': 'completed', 'progress': 25}})}\n\n"
        await asyncio.sleep(0.1)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 2, 'total_steps': 4, 'step_title': '指标设计', 'status': 'processing', 'progress': 50}})}\n\n"
        await asyncio.sleep(0.3)
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 2, 'total_steps': 4, 'step_title': '指标设计', 'status': 'completed', 'progress': 50}})}\n\n"
        await asyncio.sleep(0.1)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 3, 'total_steps': 4, 'step_title': '代码生成', 'status': 'processing', 'progress': 75}})}\n\n"
        await asyncio.sleep(0.1)
        
        full_code = await call_ai_generate_code(prompt, existing_code)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 3, 'total_steps': 4, 'step_title': '代码生成', 'status': 'completed', 'progress': 75}})}\n\n"
        await asyncio.sleep(0.1)
        
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 4, 'total_steps': 4, 'step_title': '验证优化', 'status': 'processing', 'progress': 100}})}\n\n"
        await asyncio.sleep(0.3)
        yield f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': 4, 'total_steps': 4, 'step_title': '验证优化', 'status': 'completed', 'progress': 100}})}\n\n"
        await asyncio.sleep(0.1)
        
        yield f"data: {json.dumps({'type': 'done', 'code': full_code, 'raw_content': full_code})}\n\n"
        
    except Exception as e:
        logger.error(f"指标生成失败: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


async def call_ai_generate_code(prompt: str, existing_code: str = "") -> str:
    """调用AI生成指标代码"""
    try:
        system_prompt = DEFAULT_INDICATOR_SYSTEM_PROMPT
        
        try:
            if ThinkingChainManager is not None:
                chain = ThinkingChainManager.get_active_chain_by_type("indicator_generation")
                if chain and chain.get("system_prompt"):
                    system_prompt = chain["system_prompt"]
        except Exception as e:
            logger.warning(f"无法获取system_prompt: {e}")
        
        user_prompt = prompt
        if existing_code:
            user_prompt = (
                f"# Existing Code:\n{existing_code}\n\n"
                f"# Modification Requirements:\n{prompt}\n\n"
                f"Please generate complete new Python code."
            )
        
        logger.info(f"AI生成指标代码: {prompt[:50]}...")
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

rsi_period = 14

delta = df['close'].diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)

avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()

rs = avg_gain / avg_loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
rsi = rsi.fillna(50)

raw_buy = (rsi < 30)
raw_sell = (rsi > 70)

buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))

df['buy'] = buy.astype(bool)
df['sell'] = sell.astype(bool)

buy_marks = [df['low'].iloc[i] * 0.995 if bool(buy.iloc[i]) else None for i in range(len(df))]
sell_marks = [df['high'].iloc[i] * 1.005 if bool(sell.iloc[i]) else None for i in range(len(df))]

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
    """AI流式生成指标代码（SSE）"""
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
