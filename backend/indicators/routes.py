"""
指标管理路由

提供指标CRUD、代码验证、执行计算、AI生成、参数解析等API端点
"""

import json
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from utils.logger import LogType, get_logger
from utils.rbac import is_guest_user

try:
    from ai_model.thinking_chain import ThinkingChainManager
except ImportError:
    ThinkingChainManager = None

from indicators.code_quality import analyze_indicator_code_quality, get_quality_score
from indicators.executor import (
    IndicatorExecutor,
    parse_indicator_params,
)
from indicators.models import CustomIndicatorBusiness

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(prefix="/api/indicators", tags=["指标管理"])

# 全局执行器实例（带缓存）
_executor: IndicatorExecutor | None = None


def get_executor() -> IndicatorExecutor:
    global _executor
    if _executor is None:
        _executor = IndicatorExecutor(timeout=10.0)
    return _executor


DEFAULT_INDICATOR_SYSTEM_PROMPT = """# Role
You are an expert Python quantitative trading indicator developer for a professional K-line chart platform.

# Runtime Environment & Pre-installed Libraries

1. **Execution**: Server-side Python sandbox with pandas and numpy pre-loaded.
2. **Available variables**: `df` (pandas DataFrame), `pd` (pandas), `np` (numpy), `math`, `params` (dict).
3. **DO NOT** import any modules — they are already available.
4. **Input DataFrame `df`**: index 0..N, columns: `time`(timestamp), `open`, `high`, `low`, `close`, `volume`.
5. **Always start with**: `df = df.copy()` to avoid modifying the original data.

# Output Contract (MUST follow exactly)

You MUST define these two metadata variables:
```python
my_indicator_name = "指标名称"
my_indicator_description = "指标描述"
```

And a final dictionary variable named `output`:
```python
output = {
    "name": my_indicator_name,
    "plots": [
        {
            "name": "显示名称",
            "data": [number or None, ...],   # 长度必须等于 len(df)
            "color": "#RRGGBB",              # 十六进制颜色
            "overlay": True,                  # True=叠加主图, False=独立副图
            "type": "line"                    # line/bar/candle/area
        },
        # ...更多 plot
    ],
    "signals": [
        {
            "type": "buy" | "sell",           # 仅支持两种信号类型
            "text": "B" | "S",               # 显示文字标签
            "data": [number or None, ...],    # 有值处显示标记, None 处不显示
            "color": "#RRGGBB"
        },
        # ...更多 signal
    ]
}
```

# Critical Rules (VIOLATION = RENDER FAILURE)

## NaN Handling (CRITICAL)
- rolling(N).mean(), ewm(), shift() produce leading NaN values.
- **ALWAYS** apply `.fillna()` after rolling/window operations:
  ```python
  sma = df["close"].rolling(20).mean().fillna(method="ffill").fillna(df["close"].iloc[0])
  ```
- **NEVER** use literal `np.nan` or `float('nan')` in data lists — use `None` instead.
- For division, guard against zero: `(a / b.replace(0, np.nan)).fillna(default_value)`

## Signal Markers (BEST PRACTICE)
- Use edge-triggered signals to avoid repeated consecutive marks:
  ```python
  raw_buy = condition_here
  buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
  ```
- Signal marker positions: use price-based positioning for visual clarity:
  ```python
  buy_marks = [df['low'].iloc[i] * 0.995 if bool(buy.iloc[i]) else None for i in range(len(df))]
  sell_marks = [df['high'].iloc[i] * 1.005 if bool(sell.iloc[i]) else None for i in range(len(df))]
  ```

## Data Length Consistency
- ALL `data` lists in plots and signals MUST have exactly `len(df)` elements.
- Use `.tolist()` to convert Series/Series to Python list.

# Quality Self-Check (before output)
✓ output dict has "name", "plots", "signals" keys
✓ Each plot has: name, data(list), color, overlay
✓ Each signal has: type(buy|sell), text, data(list), color
✓ All data lists length == len(df)
✓ No NaN values in any data list (use fillna)
✓ No dangerous imports (os, sys, requests, subprocess...)

Return ONLY valid Python source code. No markdown fences, no explanations, no prose.
"""


class IndicatorCreateRequest(BaseModel):
    name: str
    description: str | None = ""
    code: str


class IndicatorUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    code: str | None = None


class VerifyCodeRequest(BaseModel):
    code: str


class ExecuteIndicatorRequest(BaseModel):
    symbol: str = Field(..., description="交易对符号")
    period: str = Field("1h", description="K线周期")
    limit: int = Field(500, ge=50, le=2000, description="K线数据条数")
    params: dict[str, Any] | None = Field(default=None, description="指标参数")
    kline_data: list[dict[str, Any]] | None = Field(
        default=None,
        alias="klineData",
        description="前端传入的K线数据（可选，为空则使用mock数据）",
    )

    model_config = {"populate_by_name": True}


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


class IndicatorGenerateRequest(BaseModel):
    """AI生成指标请求体"""

    prompt: str = Field(..., description="指标生成提示词")
    existing_code: str = Field("", description="现有代码（用于优化）")


@router.post("/ai-generate")
async def ai_generate_indicator(request: IndicatorGenerateRequest):
    """AI流式生成指标代码（SSE）"""
    logger.info(f"AI生成指标: {request.prompt[:50]}...")

    return StreamingResponse(
        generate_indicator_stream(request.prompt, request.existing_code),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
    """验证指标代码（真exec + mock DataFrame）+ 静态质量分析

    使用80条模拟K线数据真正执行用户代码，检查语法和输出格式，
    同时进行静态代码质量分析，返回质量评分
    """
    executor = get_executor()

    try:
        result = await executor.verify_code(request.code)

        # 静态代码质量分析
        hints = analyze_indicator_code_quality(request.code)
        score, level = get_quality_score(hints)

        if result["valid"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data={
                    "valid": True,
                    "plots_count": result.get("plots_count", 0),
                    "signals_count": result.get("signals_count", 0),
                    "quality": {"score": score, "level": level, "hints": hints},
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
                    "quality": {"score": score, "level": level, "hints": hints},
                },
                timestamp=datetime.now(),
            )
    except Exception as e:
        logger.error(f"代码验证异常: {e}")
        return ApiResponse(
            code=500,
            message=f"验证过程异常: {e!s}",
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
        kline_data_to_use = request.kline_data or []
        logger.info(
            f"指标执行请求: indicator_id={indicator_id}, kline_data长度={len(kline_data_to_use)}, symbol={request.symbol}"
        )

        if not kline_data_to_use:
            logger.warning(f"指标执行未收到K线数据, 将使用mock数据: indicator_id={indicator_id}")

        result = await executor.execute(
            code=code,
            kline_data=kline_data_to_use,
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
            message=f"执行异常: {e!s}",
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


async def generate_indicator_stream(prompt: str, existing_code: str = "") -> AsyncGenerator[str]:
    """流式生成指标代码，含静态质量分析和LLM自动修复

    使用4步思维链展示生成进度：需求分析 → 指标设计 → 代码生成 → 验证优化
    """
    request_id = f"indicator_{int(time.time() * 1000)}"

    def _send_step(
        current_step: int,
        total_steps: int,
        title: str,
        description: str,
        status: str,
        progress: int,
    ) -> str:
        """构建思维链SSE事件"""
        return f"data: {json.dumps({'type': 'thinking_chain', 'data': {'current_step': current_step, 'total_steps': total_steps, 'step_title': title, 'step_description': description, 'status': status, 'progress': progress}})}\n\n"

    # 加载思维链步骤定义
    total_steps = 1
    step_defs = [
        {"title": "生成指标", "description": "正在生成K线图指标代码..."},
    ]
    try:
        if ThinkingChainManager is not None:
            chain = ThinkingChainManager.get_active_chain_by_type("indicator_generation")
            if chain and chain.get("steps"):
                steps = chain["steps"]
                total_steps = len(steps)
                step_defs = [
                    {
                        "title": s.get("title", f"步骤{i + 1}"),
                        "description": s.get("description", "").strip()
                        or f"正在执行{s.get('title', f'步骤{i + 1}')}...",
                    }
                    for i, s in enumerate(steps)
                ]
    except Exception as e:
        logger.warning(f"无法加载指标思维链配置: {e}")

    # 如果数据库中没有，尝试从TOML文件直接加载作为回退
    if total_steps == 1:
        try:
            import os

            toml_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "ai_model",
                "prompts",
                "templates",
                "indicator_thinking_chain_config.toml",
            )
            if os.path.exists(toml_path):
                import toml as toml_lib

                with open(toml_path) as f:
                    config = toml_lib.load(f)
                steps = config.get("thinking_chain", {}).get("steps", [])
                if steps:
                    total_steps = len(steps)
                    step_defs = [
                        {
                            "title": s.get("title", f"步骤{i + 1}"),
                            "description": s.get("description", "").strip()
                            or f"正在执行{s.get('title', f'步骤{i + 1}')}...",
                        }
                        for i, s in enumerate(steps)
                    ]
        except Exception as e:
            logger.warning(f"TOML回退加载也失败: {e}")

    try:
        # 步骤1：需求分析
        s1 = step_defs[0] if len(step_defs) > 0 else {"title": "需求分析", "description": "正在分析指标需求..."}
        yield _send_step(1, total_steps, s1["title"], s1["description"], "processing", 15)

        # 步骤2：指标设计（如果仅1步则跳过）
        if total_steps > 1:
            s2 = step_defs[1] if len(step_defs) > 1 else {"title": "指标设计", "description": "正在设计指标计算逻辑..."}
            yield _send_step(1, total_steps, s1["title"], s1["description"], "completed", 25)
            yield _send_step(2, total_steps, s2["title"], s2["description"], "processing", 35)

        # 步骤3：调用LLM生成代码
        s3_idx = 2 if total_steps > 2 else 1 if total_steps > 1 else 0
        s3 = (
            step_defs[min(s3_idx, len(step_defs) - 1)]
            if step_defs
            else {"title": "代码生成", "description": "正在生成指标代码..."}
        )

        if total_steps > 1:
            # 标记前序步骤完成
            prev_step = min(2, total_steps - 1)
            prev_s = step_defs[min(prev_step - 1, len(step_defs) - 1)]
            yield _send_step(
                prev_step,
                total_steps,
                prev_s["title"],
                prev_s["description"],
                "completed",
                50,
            )

        yield _send_step(
            min(total_steps - 1, max(1, total_steps)),
            total_steps,
            s3["title"],
            "正在调用AI模型生成代码...",
            "processing",
            55,
        )

        full_code = await call_ai_generate_code(prompt, existing_code)

        yield _send_step(
            min(total_steps - 1, max(1, total_steps)),
            total_steps,
            s3["title"],
            "代码生成完成",
            "completed",
            70,
        )

        # 步骤4：验证优化（质量分析 + 自动修复）
        s4_idx = 3 if total_steps > 3 else total_steps - 1
        s4 = (
            step_defs[min(s4_idx, len(step_defs) - 1)]
            if step_defs
            else {"title": "验证优化", "description": "正在分析代码质量..."}
        )

        yield _send_step(total_steps, total_steps, s4["title"], s4["description"], "processing", 75)

        hints = analyze_indicator_code_quality(full_code)
        score, level = get_quality_score(hints)
        error_hints = [h for h in hints if h.get("severity") == "error"]

        if error_hints:
            logger.info(f"[{request_id}] 指标代码检测到{len(error_hints)}个错误，尝试LLM自动修复")
            yield _send_step(
                total_steps,
                total_steps,
                s4["title"],
                f"发现{len(error_hints)}个问题，正在智能修复...",
                "processing",
                85,
            )

            repaired_code = await _repair_indicator_code_via_llm(prompt, full_code, hints)
            if repaired_code:
                repaired_hints = analyze_indicator_code_quality(repaired_code)
                repaired_errors = [h for h in repaired_hints if h.get("severity") == "error"]
                if len(repaired_errors) < len(error_hints):
                    full_code = repaired_code
                    hints = repaired_hints
                    score, level = get_quality_score(hints)
                    logger.info(
                        f"[{request_id}] LLM修复成功: {len(error_hints)}→{len(repaired_errors)}个错误, 质量分={score}"
                    )
                else:
                    logger.warning(f"[{request_id}] LLM修复后仍有{len(repaired_errors)}个错误，使用原始代码")

        yield _send_step(
            total_steps,
            total_steps,
            s4["title"],
            f"完成 (质量分:{score}/{level})",
            "completed",
            100,
        )

        yield f"data: {json.dumps({'type': 'done', 'code': full_code, 'raw_content': full_code, 'quality': {'score': score, 'level': level, 'hints': hints}})}\n\n"

    except Exception as e:
        logger.error(f"指标生成失败: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


async def call_ai_generate_code(prompt: str, existing_code: str = "") -> str:
    """调用AI生成指标代码

    Raises:
        Exception: 当AI模型配置缺失、API调用失败或返回空内容时抛出具体异常
    """
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

    # 获取AI模型配置
    from ai_model.config_utils import get_default_provider_and_models

    config = get_default_provider_and_models()

    if not config or not config.get("provider"):
        msg = "未获取到AI模型配置，请在系统设置中配置AI模型提供商"
        raise Exception(msg)

    provider = config["provider"]
    api_key = provider.get("api_key", "")
    api_host = provider.get("api_host", "").rstrip("/")

    enabled_models = config.get("enabled_models", [])
    if not enabled_models:
        msg = f"未获取到启用的模型，请检查提供商 [{provider.get('name')}] 的模型配置"
        raise Exception(msg)

    _model = enabled_models[0]
    model = _model.get("id") or _model.get("name") or _model.get("model_name") or "gpt-4"

    logger.info(f"使用模型: {model}, API Host: {api_host}")

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=f"{api_host}/v1" if not api_host.endswith("/v1") else api_host,
            timeout=120.0,
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4096,
        )

        generated_code = response.choices[0].message.content

        if not generated_code:
            msg = f"LLM模型 [{model}] 返回了空内容，请尝试更换其他模型"
            raise Exception(msg)

        # 清理代码：移除markdown代码块标记
        cleaned_code = _clean_generated_code(generated_code)

        logger.info(f"AI生成指标代码成功, 长度: {len(cleaned_code)}")
        return cleaned_code

    except Exception as e:
        error_msg = str(e)
        # 提取有意义的错误信息
        if "authentication" in error_msg.lower() or "401" in error_msg or "invalid_api_key" in error_msg.lower():
            msg = f"AI模型认证失败 (401): 请检查API密钥是否正确。原始错误: {error_msg}"
            raise Exception(msg)
        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower() or "network" in error_msg.lower():
            msg = f"AI模型连接失败: 无法连接到 {api_host}。请检查网络和API地址是否正确。原始错误: {error_msg}"
            raise Exception(msg)
        elif "rate_limit" in error_msg.lower() or "429" in error_msg:
            msg = f"AI模型请求频率限制 (429): 请稍后重试。原始错误: {error_msg}"
            raise Exception(msg)
        elif "model" in error_msg.lower() and (
            "not_found" in error_msg.lower() or "does_not_exist" in error_msg.lower()
        ):
            msg = f"AI模型不存在: 模型名称 [{model}] 无效，请在系统设置中选择正确的模型。原始错误: {error_msg}"
            raise Exception(msg)
        else:
            msg = f"AI生成指标代码失败: {error_msg}"
            raise Exception(msg)


def _clean_generated_code(code: str) -> str:
    """清理LLM生成的代码，移除markdown标记和多余文本"""
    lines = code.strip().split("\n")

    start_idx = 0
    end_idx = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```python") or stripped.startswith("```"):
            start_idx = i + 1
            break
        if stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            start_idx = i
            break

    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped == "```":
            end_idx = i
            break
        if stripped and not stripped.startswith("#"):
            end_idx = i + 1
            break

    cleaned = "\n".join(lines[start_idx:end_idx]).strip()

    return cleaned or code.strip()


def generate_default_indicator_code(prompt: str) -> str:
    """生成默认指标代码模板"""
    return f'''# 指标代码 - 根据需求生成
# 需求: {prompt}

my_indicator_name = "自定义指标"
my_indicator_description = "{prompt[:200]}"

df = df.copy()

rsi_period = 14

delta = df['close'].diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)

avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()

rs = avg_gain / avg_loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
rsi = rsi.fillna(method="ffill").fillna(50)

raw_buy = (rsi < 30)
raw_sell = (rsi > 70)

buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))

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


async def _repair_indicator_code_via_llm(prompt: str, original_code: str, hints: list) -> str | None:
    """调用LLM自动修复指标代码中的错误"""
    try:
        from ai_model.config_utils import get_default_provider_and_models

        provider_config = get_default_provider_and_models()
        if not provider_config:
            logger.warning("无法获取默认AI模型配置，跳过LLM修复")
            return None

        model_id = provider_config.get("enabled_models")
        if not model_id:
            return None

        error_hints = [h for h in hints if h.get("severity") == "error"]
        error_messages = "\n".join(f"  - [{h.get('code', 'UNKNOWN')}] {h.get('message', '')}" for h in error_hints)

        repair_prompt = f"""# Indicator Code Repair Task

## Original User Request
{prompt}

## Current Code (has errors)
```python
{original_code}
```

## Errors Found by Static Analysis
{error_messages}

## Instructions
Fix ALL errors listed above while preserving the indicator's core logic.
Follow these rules:
- Keep the same indicator name and description
- Fix NaN handling: add .fillna() after rolling/ewm operations
- Ensure all data lists have length equal to len(df)
- Use None instead of np.nan in data lists
- Do NOT add new features, only fix bugs
- Output ONLY valid Python code, no explanations

## Fixed Code:"""

        from ai_model.services import AIModelService

        api_key_val = provider_config.get("api_key") or ""
        adapter = AIModelService.get_adapter(
            provider_config["id"],
            api_key_val,
            provider_config.get("api_host"),
        )
        if not adapter:
            return None

        client = getattr(adapter, "_client", None)
        if not client:
            return None

        model_name = model_id.split("-", 1)[-1] if "-" in str(model_id) else str(model_id)
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": DEFAULT_INDICATOR_SYSTEM_PROMPT},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )

        repaired = response.choices[0].message.content or ""
        if repaired and len(repaired) > 50:
            cleaned = re.sub(r"^```(?:python)?\s*\n?", "", repaired.strip())
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            if cleaned and "output" in cleaned:
                return cleaned

        return None

    except Exception as e:
        logger.warning(f"LLM自动修复失败: {e}")
        return None
