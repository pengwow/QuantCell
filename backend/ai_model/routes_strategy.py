"""
策略生成API路由模块

提供基于AI的策略生成功能的RESTful API端点，支持同步和流式两种调用方式。

路由前缀:
    - /api/ai-models/strategy: 策略生成相关接口

标签: ai-strategy-generation

包含端点:
    - POST /api/ai-models/strategy/generate: 流式生成策略(SSE)
    - POST /api/ai-models/strategy/generate-sync: 同步生成策略
    - POST /api/ai-models/strategy/validate: 验证策略代码
    - POST /api/ai-models/strategy/validate-code: 通用代码验证端点
    - GET /api/ai-models/strategy/history: 获取历史列表
    - GET /api/ai-models/strategy/history/{id}: 获取单条历史
    - DELETE /api/ai-models/strategy/history/{id}: 删除历史
    - POST /api/ai-models/strategy/history/{id}/regenerate: 基于历史重新生成
    - GET /api/ai-models/strategy/templates: 获取模板列表
    - GET /api/ai-models/strategy/templates/{id}: 获取单个模板
    - POST /api/ai-models/strategy/generate-from-template: 基于模板生成
    - GET /api/ai-models/strategy/stats: 获取性能统计

作者: QuantCell Team
版本: 1.1.0
日期: 2026-03-08
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from common.schemas import ApiResponse
from utils.auth import jwt_auth_required

from .prompts import PromptCategory
from .config_utils import get_default_provider_and_models
from .schemas_strategy import (
    CodeValidationRequest,
    CodeValidationResponse,
    PerformanceStatsResponse,
    StrategyGenerateFromTemplateRequest,
    StrategyGenerateRequest,
    StrategyGenerateResponse,
    StrategyHistoryResponse,
    StrategyTemplateResponse,
    StrategyValidateRequest,
    StrategyValidateResponse,
)
from .strategy_generator import (
    APIAuthenticationError,
    APIConnectionError,
    APIRateLimitError,
    ResponseParseError,
    StrategyGenerationError,
    StrategyGenerator,
)
from .thinking_chain import ThinkingChainManager
from .thinking_chain_schemas import (
    ThinkingChainCreate,
    ThinkingChainUpdate,
)

# 创建策略生成API路由
router = APIRouter(prefix="/api/ai-models/strategy", tags=["ai-strategy-generation"])

# AI模型配置名称常量
AI_MODELS_CONFIG_NAME = "ai_models"


def get_default_ai_config() -> Optional[Dict[str, Any]]:
    """获取默认AI模型配置

    从系统配置中读取AI模型配置，包括默认提供商、API密钥、主机地址和模型列表。
    这是策略生成器初始化的基础配置来源。

    Returns:
        Optional[Dict[str, Any]]: 配置字典，包含以下字段:
            - default_provider (str): 默认提供商ID
            - api_key (str): API密钥
            - api_host (str): API主机地址
            - models (List[Dict]): 模型列表，每个模型包含id, name, is_enabled等字段
        如果未配置则返回None

    示例:
        >>> config = get_default_ai_config()
        >>> if config:
        ...     print(f"使用模型: {config['default_provider']}")
        ...     print(f"API密钥: {config['api_key'][:8]}...")
    """
    result = get_default_provider_and_models()
    if not result:
        return None

    return {
        "default_provider": result["provider"]["id"],
        "api_key": result["provider"]["api_key"],
        "api_host": result["provider"]["api_host"],
        "models": [
            {"id": m["id"], "name": m["name"], "is_enabled": True}
            for m in result["enabled_models"]
        ],
    }


def create_strategy_generator(
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
) -> StrategyGenerator:
    """创建策略生成器实例

    从系统配置获取默认AI配置，创建策略生成器。如果没有配置或配置无效会抛出HTTPException。
    使用 get_default_provider_and_models 公共方法获取配置。

    Args:
        model_id: 指定的模型ID（用于内部标识），不传则使用配置中的第一个启用模型，默认使用"gpt-4"
        model_name: 指定的模型名称（用于API调用），不传则使用model_id或默认模型名称
        temperature: 生成温度参数，控制输出的随机性，范围0-2

    Returns:
        StrategyGenerator: 配置好的策略生成器实例

    Raises:
        HTTPException: 当发生以下情况时:
            - 400: 未配置默认AI模型
            - 400: 默认AI模型未配置API密钥

    示例:
        >>> generator = create_strategy_generator(model_id="gpt-4", model_name="gpt-4", temperature=0.7)
        >>> result = generator.generate_strategy("创建一个双均线策略")
    """
    result = get_default_provider_and_models()

    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "未配置默认AI模型",
                "error": "请先配置AI模型并设置默认提供商",
            },
        )

    provider = result["provider"]
    enabled_models = result["enabled_models"]

    api_key = provider.get("api_key")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "默认AI模型未配置API密钥",
                "error": "请配置API密钥",
            },
        )

    api_host = provider.get("api_host")

    # 确定使用的模型ID和名称
    # id 用于内部库操作和模型区分，name 用于 API 调用
    logger.info(f"传入的model_id参数: {model_id}, model_name参数: {model_name}")
    logger.info(f"enabled_models: {enabled_models}")

    use_model_id = None  # 用于内部标识
    use_model_name = None  # 用于 API 调用

    if model_id:
        # 如果传入了 model_id，使用它作为内部标识
        use_model_id = model_id
        # 优先使用传入的 model_name 进行 API 调用
        if model_name:
            use_model_name = model_name
        else:
            # 如果没有传入 model_name，查找对应的模型 name
            for model in enabled_models:
                if model.get("id") == model_id:
                    use_model_name = model.get("name")
                    break
            # 如果没找到对应的 name，使用传入的 id 作为 name（兼容旧数据）
            if not use_model_name:
                use_model_name = model_id
    elif enabled_models:
        # 使用第一个启用的模型
        use_model_id = enabled_models[0].get("id", "gpt-4")
        use_model_name = enabled_models[0].get("name", "gpt-4")
    else:
        use_model_id = "gpt-4"
        use_model_name = "gpt-4"

    logger.info(f"最终使用的model_id: {use_model_id}, model_name: {use_model_name}")

    return StrategyGenerator(
        api_key=api_key,
        api_host=api_host,
        model_id=use_model_id,
        model_name=use_model_name,
        temperature=temperature,
    )


@router.post("/generate")
@jwt_auth_required
async def generate_strategy_stream(request: Request, gen_request: StrategyGenerateRequest):
    """流式生成策略(SSE)

    使用AI模型流式生成策略代码，通过SSE(Server-Sent Events)方式实时返回生成内容。
    适用于需要实时显示生成进度的场景，如Web界面实时展示代码生成过程。

    Args:
        request: FastAPI请求对象，包含用户信息等上下文
        gen_request: 策略生成请求体，字段说明:
            - requirement (str, 必需): 策略需求描述，10-5000字符
            - model_id (str, 可选): 指定模型ID，如"gpt-4"
            - temperature (float, 可选): 温度参数，0-2，默认使用系统配置
            - template_vars (dict, 可选): 模板变量，用于替换提示词占位符

    Returns:
        StreamingResponse: SSE流式响应，Content-Type为text/event-stream

    SSE事件格式:
        每个事件以"data: "开头，以"\n\n"结束，内容为JSON格式。

    SSE事件类型(type字段):
        - thinking_chain: 思维链进度更新（保留流式传输）
            ```json
            {
                "type": "thinking_chain",
                "data": {
                    "current_step": 2,
                    "total_steps": 4,
                    "step_title": "生成代码",
                    "step_description": "正在生成策略代码...",
                    "status": "processing",
                    "progress": 50,
                    "message": "正在生成策略代码..."
                }
            }
            ```
        - done: 生成完成，包含完整代码和元数据（非流式，一次性返回）
            ```json
            {
                "type": "done",
                "code": "class DualMAStrategy:\n    pass",
                "metadata": {
                    "model": "gpt-4",
                    "elapsed_time": 2.5,
                    "chunk_count": 42
                },
                "request_id": "stream_123456"
            }
            ```
        - error: 生成错误，包含错误信息
            ```json
            {
                "type": "error",
                "error": "API密钥无效",
                "error_code": "api_authentication_error",
                "request_id": "stream_123456"
            }
            ```

    优化说明:
        - 思维链进度信息通过流式传输实时展示生成进度
        - 生成的代码内容改为非流式返回，在done事件中一次性返回完整代码
        - 减少网络开销，提升高并发场景下的稳定性

    HTTP响应状态码:
        - 200: 流式响应开始，连接建立成功
        - 400: 请求参数错误或未配置AI模型
            ```json
            {"detail": {"message": "未配置默认AI模型", "error": "请先配置AI模型"}}
            ```
        - 401: 未授权访问，JWT Token无效或过期
        - 500: 服务器内部错误

    示例请求:
        ```bash
        curl -X POST "http://localhost:8000/api/ai-models/strategy/generate" \
            -H "Authorization: Bearer <jwt_token>" \
            -H "Content-Type: application/json" \
            -d '{
                "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入",
                "model_id": "gpt-4",
                "temperature": 0.7,
                "template_vars": {
                    "strategy_name": "DualMAStrategy",
                    "symbol": "BTC/USDT"
                }
            }'
        ```

    示例SSE响应流:
        ```
        // 思维链进度更新（流式传输）
        data: {"type": "thinking_chain", "data": {"current_step": 1, "total_steps": 4, "step_title": "分析需求", "status": "processing", "progress": 25}}\n\n
        data: {"type": "thinking_chain", "data": {"current_step": 1, "total_steps": 4, "step_title": "分析需求", "status": "completed", "progress": 25}}\n\n
        data: {"type": "thinking_chain", "data": {"current_step": 2, "total_steps": 4, "step_title": "设计策略", "status": "processing", "progress": 50}}\n\n
        ...
        // 生成完成，一次性返回完整代码（非流式）
        data: {"type": "done", "code": "class DualMAStrategy:\n    pass", "metadata": {...}, "request_id": "stream_001"}\n\n
        ```

    前端JavaScript使用示例:
        ```javascript
        const eventSource = new EventSource('/api/ai-models/strategy/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                requirement: '创建一个双均线策略',
                temperature: 0.7
            })
        });

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'content') {
                console.log('收到内容:', data.content);
            } else if (data.type === 'done') {
                console.log('生成完成:', data.code);
                eventSource.close();
            } else if (data.type === 'error') {
                console.error('生成错误:', data.error);
                eventSource.close();
            }
        };
        ```

    注意事项:
        - 需要有效的JWT认证Token
        - 请求体中的requirement字段至少需要10个字符
        - SSE连接保持期间不要关闭客户端
        - 如果AI模型未配置，会返回400错误
    """
    try:
        logger.info(f"开始流式生成策略，需求长度: {len(gen_request.requirement)}字符")

        # 创建策略生成器
        generator = create_strategy_generator(
            model_id=gen_request.model_id,
            model_name=gen_request.model_name,
            temperature=gen_request.temperature,
        )

        # 准备模板变量
        template_vars = gen_request.template_vars or {}

        async def event_stream():
            """生成SSE事件流"""
            async for chunk in generator.generate_strategy_stream(
                requirement=gen_request.requirement,
                prompt_category=PromptCategory.STRATEGY_GENERATION,
                **template_vars,
            ):
                # 将数据块格式化为SSE格式
                data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {data}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"流式生成策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-sync", response_model=ApiResponse)
@jwt_auth_required
async def generate_strategy_sync(request: Request, gen_request: StrategyGenerateRequest):
    """同步生成策略

    使用AI模型同步生成策略代码，一次性返回完整结果。
    适用于不需要实时显示进度的场景，如后台批量生成或简单调用。

    Args:
        request: FastAPI请求对象，包含用户信息等上下文
        gen_request: 策略生成请求体，字段说明:
            - requirement (str, 必需): 策略需求描述，10-5000字符
            - model_id (str, 可选): 指定模型ID，不传使用系统默认
            - temperature (float, 可选): 温度参数，0-2
            - template_vars (dict, 可选): 模板变量，用于替换提示词占位符

    Returns:
        ApiResponse: 统一响应格式，包含以下字段:
            - code (int): 业务状态码，0表示成功
            - message (str): 状态描述
            - data (dict): 响应数据，包含StrategyGenerateResponse

    响应数据字段(data):
        - code (str): 生成的策略代码
        - explanation (str): 策略说明文档
        - model_used (str): 实际使用的模型ID
        - tokens_used (dict): Token使用情况
            - prompt_tokens: 提示词Token数
            - completion_tokens: 生成内容Token数
            - total_tokens: 总Token数
        - elapsed_time (float): 生成耗时(秒)
        - request_id (str): 请求ID，用于追踪

    HTTP响应状态码:
        - 200: 生成成功
        - 400: 请求参数错误或未配置AI模型
        - 401: 未授权访问
        - 500: 生成失败

    业务错误码(ApiResponse.code):
        - 0: 成功
        - 1: 失败(具体原因见message字段)
            - api_authentication_error: API认证失败
            - api_rate_limit_error: 请求过于频繁
            - api_connection_error: 连接失败
            - response_parse_error: 响应解析失败
            - strategy_generation_error: 策略生成失败

    示例请求:
        ```bash
        curl -X POST "http://localhost:8000/api/ai-models/strategy/generate-sync" \
            -H "Authorization: Bearer <jwt_token>" \
            -H "Content-Type: application/json" \
            -d '{
                "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入",
                "model_id": "gpt-4",
                "temperature": 0.7
            }'
        ```

    成功响应示例:
        ```json
        {
            "code": 0,
            "message": "策略生成成功",
            "data": {
                "code": "class DualMAStrategy(Strategy):\n    def __init__(self):\n        self.fast_ma = 10\n        self.slow_ma = 20\n    ...",
                "explanation": "这是一个基于双均线的趋势跟踪策略...",
                "model_used": "gpt-4",
                "tokens_used": {
                    "prompt_tokens": 500,
                    "completion_tokens": 800,
                    "total_tokens": 1300
                },
                "elapsed_time": 3.5,
                "request_id": "req_abc123"
            }
        }
        ```

    失败响应示例:
        ```json
        {
            "code": 1,
            "message": "API认证失败: API密钥无效或已过期",
            "data": {
                "error_code": "api_authentication_error"
            }
        }
        ```

    Python调用示例:
        ```python
        import requests

        response = requests.post(
            'http://localhost:8000/api/ai-models/strategy/generate-sync',
            headers={'Authorization': 'Bearer <jwt_token>'},
            json={
                'requirement': '创建一个双均线策略',
                'temperature': 0.7
            }
        )

        result = response.json()
        if result['code'] == 0:
            print('生成成功:', result['data']['code'])
        else:
            print('生成失败:', result['message'])
        ```

    注意事项:
        - 同步接口可能需要等待数秒到数十秒，请设置合理的超时时间(建议60秒以上)
        - 生成的代码需要经过验证后才能使用
        - 建议保存request_id以便问题追踪
    """
    try:
        logger.info(f"开始同步生成策略，需求长度: {len(gen_request.requirement)}字符")
        logger.info(f"请求中的model_id: {gen_request.model_id}, model_name: {gen_request.model_name}")

        # 创建策略生成器
        generator = create_strategy_generator(
            model_id=gen_request.model_id,
            model_name=gen_request.model_name,
            temperature=gen_request.temperature,
        )

        # 准备模板变量
        template_vars = gen_request.template_vars or {}

        # 执行同步生成
        result = generator.generate_strategy(
            requirement=gen_request.requirement,
            prompt_category=PromptCategory.STRATEGY_GENERATION,
            **template_vars,
        )

        # 检查生成是否成功
        if not result.get("success"):
            error_msg = result.get("error", "生成失败")
            logger.error(f"策略生成失败: {error_msg}")
            return ApiResponse(
                code=1,
                message=f"策略生成失败: {error_msg}",
                data=None,
            )

        # 构建响应数据
        metadata = result.get("metadata", {})
        response_data = StrategyGenerateResponse(
            code=result.get("code", ""),
            explanation=result.get("raw_content"),  # 原始内容作为说明
            model_used=metadata.get("model", generator.model_id),
            tokens_used={
                "prompt_tokens": metadata.get("prompt_tokens"),
                "completion_tokens": metadata.get("completion_tokens"),
                "total_tokens": metadata.get("total_tokens"),
            },
            elapsed_time=metadata.get("elapsed_time"),
            request_id=metadata.get("request_id"),
        )

        logger.info(f"策略生成成功，耗时: {metadata.get('elapsed_time', 0):.2f}s")

        return ApiResponse(
            code=0,
            message="策略生成成功",
            data=response_data.model_dump(),
        )

    except APIAuthenticationError as e:
        logger.error(f"API认证失败: {e}")
        return ApiResponse(
            code=1,
            message=f"API认证失败: {e.message}",
            data={"error_code": e.error_code},
        )
    except APIRateLimitError as e:
        logger.error(f"API速率限制: {e}")
        return ApiResponse(
            code=1,
            message=f"请求过于频繁: {e.message}",
            data={"error_code": e.error_code},
        )
    except APIConnectionError as e:
        logger.error(f"API连接错误: {e}")
        return ApiResponse(
            code=1,
            message=f"连接失败: {e.message}",
            data={"error_code": e.error_code},
        )
    except ResponseParseError as e:
        logger.error(f"响应解析错误: {e}")
        return ApiResponse(
            code=1,
            message=f"解析失败: {e.message}",
            data={"error_code": e.error_code},
        )
    except StrategyGenerationError as e:
        logger.error(f"策略生成错误: {e}")
        return ApiResponse(
            code=1,
            message=f"生成失败: {e.message}",
            data={"error_code": e.error_code},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"同步生成策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate", response_model=ApiResponse)
@jwt_auth_required
async def validate_strategy_code(request: Request, validate_request: StrategyValidateRequest):
    """验证策略代码

    对生成的策略代码进行语法验证和基本结构检查，确保代码可以正确加载和执行。
    验证包括Python语法检查、类定义检查、必要方法检查等。

    Args:
        request: FastAPI请求对象，包含用户信息等上下文
        validate_request: 代码验证请求体，字段说明:
            - code (str, 必需): 需要验证的策略代码，至少1个字符

    Returns:
        ApiResponse: 统一响应格式，包含以下字段:
            - code (int): 业务状态码，0表示验证完成
            - message (str): 状态描述
            - data (dict): 验证结果，包含StrategyValidateResponse

    响应数据字段(data):
        - valid (bool): 代码是否有效，true表示通过验证
        - errors (list): 错误列表，如果valid为false则包含具体错误信息
        - warnings (list): 警告列表，包含非致命性建议

    HTTP响应状态码:
        - 200: 验证完成(无论验证结果如何，HTTP状态码都是200)
        - 400: 请求参数错误(如code字段缺失)
        - 401: 未授权访问
        - 500: 验证过程发生错误

    示例请求:
        ```bash
        curl -X POST "http://localhost:8000/api/ai-models/strategy/validate" \
            -H "Authorization: Bearer <jwt_token>" \
            -H "Content-Type: application/json" \
            -d '{
                "code": "class MyStrategy:\n    def __init__(self):\n        pass"
            }'
        ```

    验证通过响应示例:
        ```json
        {
            "code": 0,
            "message": "验证完成",
            "data": {
                "valid": true,
                "errors": [],
                "warnings": [
                    "警告: 代码中未找到类定义",
                    "警告: 未检测到策略基类继承"
                ]
            }
        }
        ```

    验证失败响应示例:
        ```json
        {
            "code": 0,
            "message": "验证完成",
            "data": {
                "valid": false,
                "errors": [
                    "语法错误: 第5行缩进错误",
                    "语法错误: 第8行缺少冒号"
                ],
                "warnings": [
                    "警告: 代码中未找到类定义"
                ]
            }
        }
        ```

    Python调用示例:
        ```python
        import requests

        code = '''
        class MyStrategy:
            def __init__(self):
                pass
        '''

        response = requests.post(
            'http://localhost:8000/api/ai-models/strategy/validate',
            headers={'Authorization': 'Bearer <jwt_token>'},
            json={'code': code}
        )

        result = response.json()
        if result['data']['valid']:
            print('代码验证通过')
        else:
            print('验证失败:', result['data']['errors'])
            print('警告:', result['data']['warnings'])
        ```

    验证规则说明:
        1. 语法检查: 使用Python AST解析器检查代码语法
        2. 结构检查: 检查是否包含类定义
        3. 方法检查: 检查是否包含必要的方法(如__init__)
        4. 导入检查: 检查导入语句是否合法

    注意事项:
        - 验证通过不代表代码逻辑正确，只表示代码可以执行
        - 警告信息不影响代码执行，但建议根据警告进行优化
        - 建议在保存策略前先进行验证
        - 验证过程在本地执行，不会调用外部API
    """
    try:
        logger.info(f"开始验证策略代码，代码长度: {len(validate_request.code)}字符")

        # 创建临时策略生成器用于验证
        generator = StrategyGenerator(
            api_key="dummy_key",  # 验证不需要实际API密钥
        )

        # 执行验证
        result = generator.validate_code(validate_request.code)

        # 分离错误和警告
        errors = [e for e in result.get("errors", []) if not e.startswith("警告")]
        warnings = [e for e in result.get("errors", []) if e.startswith("警告")]

        response_data = StrategyValidateResponse(
            valid=result.get("valid", False),
            errors=errors,
            warnings=warnings,
        )

        logger.info(f"代码验证完成，有效: {result.get('valid', False)}")

        return ApiResponse(
            code=0,
            message="验证完成",
            data=response_data.model_dump(),
        )

    except Exception as e:
        logger.error(f"代码验证失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 内存存储用于演示，实际项目中应使用数据库
# 策略历史记录存储
_strategy_history_db: Dict[str, Dict[str, Any]] = {}
# 策略模板存储
_strategy_templates_db: Dict[str, Dict[str, Any]] = {
    "tpl_001": {
        "id": "tpl_001",
        "name": "双均线策略模板",
        "description": "基于双均线的趋势跟踪策略模板",
        "category": "trend_following",
        "code_template": '''class {{strategy_name}}(Strategy):
    def __init__(self):
        self.fast_period = {{fast_period}}
        self.slow_period = {{slow_period}}
        
    def on_bar(self, bar):
        fast_ma = self.calculate_ma(bar.close, self.fast_period)
        slow_ma = self.calculate_ma(bar.close, self.slow_period)
        
        if fast_ma > slow_ma and not self.position:
            self.buy()
        elif fast_ma < slow_ma and self.position:
            self.sell()
''',
        "variables": [
            {"name": "strategy_name", "type": "string", "required": True},
            {"name": "fast_period", "type": "int", "default": 10},
            {"name": "slow_period", "type": "int", "default": 20},
        ],
        "tags": ["趋势", "均线", "经典"],
        "created_at": datetime.now(),
        "updated_at": None,
    },
    "tpl_002": {
        "id": "tpl_002",
        "name": "RSI超买超卖策略模板",
        "description": "基于RSI指标的超买超卖策略模板",
        "category": "oscillator",
        "code_template": '''class {{strategy_name}}(Strategy):
    def __init__(self):
        self.rsi_period = {{rsi_period}}
        self.overbought = {{overbought}}
        self.oversold = {{oversold}}
        
    def on_bar(self, bar):
        rsi = self.calculate_rsi(bar.close, self.rsi_period)
        
        if rsi < self.oversold and not self.position:
            self.buy()
        elif rsi > self.overbought and self.position:
            self.sell()
''',
        "variables": [
            {"name": "strategy_name", "type": "string", "required": True},
            {"name": "rsi_period", "type": "int", "default": 14},
            {"name": "overbought", "type": "int", "default": 70},
            {"name": "oversold", "type": "int", "default": 30},
        ],
        "tags": ["RSI", "震荡", "反转"],
        "created_at": datetime.now(),
        "updated_at": None,
    },
}


def _get_user_id_from_request(request: Request) -> str:
    """从请求中获取用户ID"""
    user = getattr(request.state, "user", None)
    if user:
        return getattr(user, "id", str(uuid.uuid4()))
    return str(uuid.uuid4())


@router.post("/validate-code", response_model=ApiResponse)
@jwt_auth_required
async def validate_code(request: Request, validation_request: CodeValidationRequest):
    """通用代码验证端点

    对任意代码进行语法验证和基本结构检查，支持多种编程语言。

    Args:
        request: FastAPI请求对象
        validation_request: 代码验证请求体，包含code和language字段

    Returns:
        ApiResponse: 包含验证结果，包括valid、errors、warnings和suggestions
    """
    try:
        logger.info(f"开始验证代码，语言: {validation_request.language}, 长度: {len(validation_request.code)}字符")

        errors = []
        warnings = []
        suggestions = []

        if validation_request.language == "python":
            import ast

            try:
                ast.parse(validation_request.code)
            except SyntaxError as e:
                errors.append(f"语法错误: 第{e.lineno}行 - {e.msg}")

            # 检查类定义
            if "class " not in validation_request.code:
                warnings.append("警告: 代码中未找到类定义")

            # 检查策略基类继承
            if "Strategy" not in validation_request.code:
                warnings.append("警告: 未检测到策略基类继承")

            # 建议
            if "# " not in validation_request.code:
                suggestions.append("建议: 添加代码注释以提高可读性")
            if "def __init__" not in validation_request.code:
                suggestions.append("建议: 添加__init__方法进行初始化")
        else:
            warnings.append(f"当前仅支持Python代码验证，{validation_request.language}语言的验证可能不完整")

        response_data = CodeValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )

        logger.info(f"代码验证完成，有效: {len(errors) == 0}")

        return ApiResponse(
            code=0,
            message="验证完成",
            data=response_data.model_dump(),
        )

    except Exception as e:
        logger.error(f"代码验证失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=ApiResponse)
@jwt_auth_required
async def get_history_list(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="筛选状态: success/failed/pending"),
    model_id: Optional[str] = Query(None, description="筛选模型ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
):
    """获取策略生成历史列表

    支持分页和多种筛选条件的策略历史记录查询。

    Args:
        request: FastAPI请求对象
        page: 页码，从1开始
        page_size: 每页数量，默认20，最大100
        status: 按状态筛选
        model_id: 按模型ID筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选

    Returns:
        ApiResponse: 包含历史记录列表和分页信息
    """
    try:
        user_id = _get_user_id_from_request(request)
        logger.info(f"获取历史列表，用户: {user_id}, 页码: {page}, 每页: {page_size}")

        # 筛选当前用户的历史记录
        user_history = [
            h for h in _strategy_history_db.values()
            if h.get("user_id") == user_id
        ]

        # 应用筛选条件
        if status:
            user_history = [h for h in user_history if h.get("status") == status]
        if model_id:
            user_history = [h for h in user_history if h.get("model_id") == model_id]
        if start_date:
            user_history = [h for h in user_history if h.get("created_at", datetime.min) >= start_date]
        if end_date:
            user_history = [h for h in user_history if h.get("created_at", datetime.max) <= end_date]

        # 按创建时间倒序排序
        user_history.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)

        # 分页
        total = len(user_history)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_history = user_history[start_idx:end_idx]

        # 转换为响应模型
        history_list = [StrategyHistoryResponse(**h).model_dump() for h in paginated_history]

        return ApiResponse(
            code=0,
            message="获取成功",
            data={
                "list": history_list,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                },
            },
        )

    except Exception as e:
        logger.error(f"获取历史列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{history_id}", response_model=ApiResponse)
@jwt_auth_required
async def get_history_detail(request: Request, history_id: str):
    """获取单条策略历史记录详情

    Args:
        request: FastAPI请求对象
        history_id: 历史记录ID

    Returns:
        ApiResponse: 包含单条历史记录详情
    """
    try:
        user_id = _get_user_id_from_request(request)
        logger.info(f"获取历史详情，ID: {history_id}, 用户: {user_id}")

        history = _strategy_history_db.get(history_id)
        if not history:
            raise HTTPException(status_code=404, detail="历史记录不存在")

        if history.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权访问该记录")

        response_data = StrategyHistoryResponse(**history)

        return ApiResponse(
            code=0,
            message="获取成功",
            data=response_data.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取历史详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{history_id}", response_model=ApiResponse)
@jwt_auth_required
async def delete_history(request: Request, history_id: str):
    """删除策略历史记录

    Args:
        request: FastAPI请求对象
        history_id: 历史记录ID

    Returns:
        ApiResponse: 删除结果
    """
    try:
        user_id = _get_user_id_from_request(request)
        logger.info(f"删除历史记录，ID: {history_id}, 用户: {user_id}")

        history = _strategy_history_db.get(history_id)
        if not history:
            raise HTTPException(status_code=404, detail="历史记录不存在")

        if history.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权删除该记录")

        del _strategy_history_db[history_id]

        return ApiResponse(
            code=0,
            message="删除成功",
            data={"id": history_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除历史记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/history/{history_id}/regenerate", response_model=ApiResponse)
@jwt_auth_required
async def regenerate_from_history(request: Request, history_id: str):
    """基于历史记录重新生成策略

    使用历史记录中的需求描述重新生成策略代码。

    Args:
        request: FastAPI请求对象
        history_id: 历史记录ID

    Returns:
        ApiResponse: 新生成的策略结果
    """
    try:
        user_id = _get_user_id_from_request(request)
        logger.info(f"基于历史重新生成，ID: {history_id}, 用户: {user_id}")

        history = _strategy_history_db.get(history_id)
        if not history:
            raise HTTPException(status_code=404, detail="历史记录不存在")

        if history.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权访问该记录")

        # 创建生成请求
        gen_request = StrategyGenerateRequest(
            requirement=history["requirement"],
            model_id=history.get("model_id"),
        )

        # 调用同步生成逻辑
        generator = create_strategy_generator(
            model_id=gen_request.model_id,
            model_name=gen_request.model_name,
            temperature=gen_request.temperature,
        )

        template_vars = gen_request.template_vars or {}
        result = generator.generate_strategy(
            requirement=gen_request.requirement,
            prompt_category=PromptCategory.STRATEGY_GENERATION,
            **template_vars,
        )

        if not result.get("success"):
            return ApiResponse(
                code=1,
                message=f"重新生成失败: {result.get('error', '未知错误')}",
                data=None,
            )

        # 创建新的历史记录
        new_history_id = f"hist_{uuid.uuid4().hex[:16]}"
        metadata = result.get("metadata", {})
        new_history = {
            "id": new_history_id,
            "user_id": user_id,
            "requirement": history["requirement"],
            "code": result.get("code", ""),
            "model_id": metadata.get("model", generator.model_id),
            "explanation": result.get("raw_content"),
            "status": "success",
            "tokens_used": {
                "prompt_tokens": metadata.get("prompt_tokens"),
                "completion_tokens": metadata.get("completion_tokens"),
                "total_tokens": metadata.get("total_tokens"),
            },
            "elapsed_time": metadata.get("elapsed_time"),
            "created_at": datetime.now(),
            "updated_at": None,
            "parent_id": history_id,
        }
        _strategy_history_db[new_history_id] = new_history

        response_data = StrategyGenerateResponse(
            code=result.get("code", ""),
            explanation=result.get("raw_content"),
            model_used=metadata.get("model", generator.model_id),
            tokens_used=new_history["tokens_used"],
            elapsed_time=metadata.get("elapsed_time"),
            request_id=metadata.get("request_id"),
        )

        return ApiResponse(
            code=0,
            message="重新生成成功",
            data=response_data.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates", response_model=ApiResponse)
@jwt_auth_required
async def get_template_list(
    request: Request,
    category: Optional[str] = Query(None, description="模板分类筛选"),
    tag: Optional[str] = Query(None, description="标签筛选"),
):
    """获取策略模板列表

    Args:
        request: FastAPI请求对象
        category: 按分类筛选
        tag: 按标签筛选

    Returns:
        ApiResponse: 包含模板列表
    """
    try:
        logger.info(f"获取模板列表，分类: {category}, 标签: {tag}")

        templates = list(_strategy_templates_db.values())

        if category:
            templates = [t for t in templates if t.get("category") == category]
        if tag:
            templates = [t for t in templates if tag in t.get("tags", [])]

        template_list = [StrategyTemplateResponse(**t).model_dump() for t in templates]

        return ApiResponse(
            code=0,
            message="获取成功",
            data={
                "list": template_list,
                "total": len(template_list),
            },
        )

    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{template_id}", response_model=ApiResponse)
@jwt_auth_required
async def get_template_detail(request: Request, template_id: str):
    """获取单个策略模板详情

    Args:
        request: FastAPI请求对象
        template_id: 模板ID

    Returns:
        ApiResponse: 包含模板详情
    """
    try:
        logger.info(f"获取模板详情，ID: {template_id}")

        template = _strategy_templates_db.get(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        response_data = StrategyTemplateResponse(**template)

        return ApiResponse(
            code=0,
            message="获取成功",
            data=response_data.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模板详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-from-template", response_model=ApiResponse)
@jwt_auth_required
async def generate_from_template(
    request: Request,
    gen_request: StrategyGenerateFromTemplateRequest,
):
    """基于模板生成策略

    使用预定义的模板和变量值生成策略代码。

    Args:
        request: FastAPI请求对象
        gen_request: 基于模板生成请求

    Returns:
        ApiResponse: 生成的策略结果
    """
    try:
        user_id = _get_user_id_from_request(request)
        logger.info(f"基于模板生成策略，模板ID: {gen_request.template_id}, 用户: {user_id}")

        template = _strategy_templates_db.get(gen_request.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        # 替换模板变量
        code_template = template["code_template"]
        for var_name, var_value in gen_request.variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            code_template = code_template.replace(placeholder, str(var_value))

        # 检查是否还有未替换的变量
        import re

        remaining_vars = re.findall(r"\{\{(\w+)\}\}", code_template)
        if remaining_vars:
            return ApiResponse(
                code=1,
                message=f"模板变量未完全替换: {', '.join(remaining_vars)}",
                data=None,
            )

        # 如果有额外需求，使用AI优化代码
        final_code = code_template
        if gen_request.additional_requirement:
            generator = create_strategy_generator(
                model_id=gen_request.model_id,
                model_name=gen_request.model_name,
                temperature=gen_request.temperature,
            )

            requirement = f"基于以下代码模板，{gen_request.additional_requirement}\n\n模板代码:\n{code_template}"
            result = generator.generate_strategy(
                requirement=requirement,
                prompt_category=PromptCategory.STRATEGY_GENERATION,
            )

            if result.get("success"):
                final_code = result.get("code", code_template)
            else:
                logger.warning(f"AI优化失败，使用原始模板: {result.get('error')}")

        # 创建历史记录
        history_id = f"hist_{uuid.uuid4().hex[:16]}"
        history = {
            "id": history_id,
            "user_id": user_id,
            "requirement": f"基于模板 {template['name']} 生成策略",
            "code": final_code,
            "model_id": gen_request.model_id or "template",
            "explanation": None,
            "status": "success",
            "tokens_used": None,
            "elapsed_time": None,
            "created_at": datetime.now(),
            "updated_at": None,
        }
        _strategy_history_db[history_id] = history

        response_data = StrategyGenerateResponse(
            code=final_code,
            explanation=f"基于模板 {template['name']} 生成",
            model_used=gen_request.model_id or "template",
            tokens_used=None,
            elapsed_time=None,
            request_id=history_id,
        )

        return ApiResponse(
            code=0,
            message="基于模板生成成功",
            data=response_data.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"基于模板生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=ApiResponse)
@jwt_auth_required
async def get_performance_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
):
    """获取性能统计

    获取策略生成的性能统计数据。

    Args:
        request: FastAPI请求对象
        days: 统计天数，默认30天

    Returns:
        ApiResponse: 包含性能统计数据
    """
    try:
        user_id = _get_user_id_from_request(request)
        logger.info(f"获取性能统计，用户: {user_id}, 天数: {days}")

        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 筛选当前用户在日期范围内的历史记录
        user_history = [
            h for h in _strategy_history_db.values()
            if h.get("user_id") == user_id
            and start_date <= h.get("created_at", datetime.min) <= end_date
        ]

        total = len(user_history)
        successful = len([h for h in user_history if h.get("status") == "success"])
        failed = len([h for h in user_history if h.get("status") == "failed"])

        # 计算平均生成时间
        elapsed_times = [h.get("elapsed_time", 0) for h in user_history if h.get("elapsed_time")]
        avg_time = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0

        # 计算Token使用量
        total_tokens = 0
        model_usage: Dict[str, int] = {}
        for h in user_history:
            tokens = h.get("tokens_used", {})
            if tokens and "total_tokens" in tokens:
                total_tokens += tokens["total_tokens"] or 0
            model_id = h.get("model_id", "unknown")
            model_usage[model_id] = model_usage.get(model_id, 0) + 1

        # 每日统计
        daily_stats_map: Dict[str, Dict[str, int]] = {}
        for h in user_history:
            date_str = h.get("created_at", datetime.now()).strftime("%Y-%m-%d")
            if date_str not in daily_stats_map:
                daily_stats_map[date_str] = {"date": date_str, "count": 0, "success": 0}
            daily_stats_map[date_str]["count"] += 1
            if h.get("status") == "success":
                daily_stats_map[date_str]["success"] += 1

        daily_stats = sorted(daily_stats_map.values(), key=lambda x: x["date"])

        response_data = PerformanceStatsResponse(
            total_generations=total,
            successful_generations=successful,
            failed_generations=failed,
            success_rate=(successful / total * 100) if total > 0 else 0,
            average_generation_time=avg_time,
            total_tokens_used=total_tokens,
            model_usage_stats=model_usage,
            daily_stats=daily_stats,
            period_start=start_date,
            period_end=end_date,
        )

        return ApiResponse(
            code=0,
            message="获取成功",
            data=response_data.model_dump(),
        )

    except Exception as e:
        logger.error(f"获取性能统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 思维链API端点 ====================

@router.get("/thinking-chains/preload", response_model=ApiResponse)
@jwt_auth_required
async def preload_thinking_chain(
    request: Request,
    chain_type: str = Query("strategy_generation", description="思维链类型: strategy_generation/indicator_generation"),
):
    """预加载思维链配置

    用于前端页面打开时快速获取激活的思维链配置，减少用户等待时间。
    返回指定类型的激活思维链配置，包含完整的步骤信息。

    Args:
        request: FastAPI请求对象
        chain_type: 思维链类型，默认为 strategy_generation

    Returns:
        ApiResponse: 包含思维链配置的响应

    示例请求:
        ```bash
        curl -X GET "http://localhost:8000/api/ai-models/strategy/thinking-chains/preload?chain_type=strategy_generation" \
            -H "Authorization: Bearer <jwt_token>"
        ```

    成功响应示例:
        ```json
        {
            "code": 0,
            "message": "获取成功",
            "data": {
                "id": "chain_xxx",
                "chain_type": "strategy_generation",
                "name": "策略生成思维链",
                "description": "标准策略生成流程",
                "steps": [
                    {
                        "title": "需求分析",
                        "description": "分析用户策略需求",
                        "status": "pending"
                    }
                ],
                "is_active": true
            }
        }
        ```
    """
    try:
        logger.info(f"预加载思维链配置, chain_type={chain_type}")
        
        chain = ThinkingChainManager.get_active_chain_by_type(chain_type)
        
        if not chain:
            return ApiResponse(
                code=1,
                message=f"未找到类型为 {chain_type} 的激活思维链配置",
                data=None,
            )
        
        return ApiResponse(
            code=0,
            message="获取成功",
            data=chain,
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"预加载思维链失败: {error_msg}")
        
        # 提供更友好的错误信息
        if "no such table" in error_msg.lower():
            friendly_msg = "数据库表不存在，请先运行初始化脚本: cd backend && uv run python scripts/init_ai_model.py"
        elif "operationalerror" in error_msg.lower():
            friendly_msg = "数据库操作错误，请检查数据库配置或运行初始化脚本"
        else:
            friendly_msg = f"系统错误: {error_msg}"
        
        return ApiResponse(
            code=500,
            message=friendly_msg,
            data={"error_detail": error_msg},
        )


@router.get("/thinking-chains", response_model=ApiResponse)
@jwt_auth_required
async def get_thinking_chains(
    request: Request,
    chain_type: Optional[str] = Query(None, description="思维链类型筛选: strategy_generation/indicator_generation"),
    is_active: Optional[bool] = Query(None, description="按激活状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("created_at", description="排序字段: created_at/updated_at/name/chain_type"),
    sort_order: str = Query("desc", description="排序顺序: asc/desc"),
):
    """获取思维链配置列表

    支持分页和多种筛选条件的思维链配置查询。

    Args:
        request: FastAPI请求对象
        chain_type: 按类型筛选，可选值: strategy_generation, indicator_generation
        is_active: 按激活状态筛选
        page: 页码，从1开始
        page_size: 每页数量，默认20，最大100
        sort_by: 排序字段，支持 created_at, updated_at, name, chain_type
        sort_order: 排序顺序，asc 或 desc

    Returns:
        ApiResponse: 包含思维链列表和分页信息

    示例请求:
        ```bash
        curl -X GET "http://localhost:8000/api/ai-models/strategy/thinking-chains?page=1&page_size=10&chain_type=strategy_generation" \
            -H "Authorization: Bearer <jwt_token>"
        ```

    成功响应示例:
        ```json
        {
            "code": 0,
            "message": "获取成功",
            "data": {
                "items": [
                    {
                        "id": "chain_xxx",
                        "chain_type": "strategy_generation",
                        "name": "策略生成思维链",
                        "description": "标准策略生成流程",
                        "steps": [...],
                        "is_active": true,
                        "created_at": "2026-03-08 10:00:00",
                        "updated_at": "2026-03-08 10:00:00"
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "pages": 1
            }
        }
        ```
    """
    try:
        logger.info(f"获取思维链列表，类型: {chain_type}, 页码: {page}, 每页: {page_size}")

        result = ThinkingChainManager.get_thinking_chains(
            chain_type=chain_type,
            is_active=is_active,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return ApiResponse(
            code=0,
            message="获取成功",
            data=result,
        )

    except Exception as e:
        logger.error(f"获取思维链列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thinking-chains/{chain_id}", response_model=ApiResponse)
@jwt_auth_required
async def get_thinking_chain_detail(request: Request, chain_id: str):
    """获取单个思维链配置详情

    Args:
        request: FastAPI请求对象
        chain_id: 思维链ID

    Returns:
        ApiResponse: 包含单个思维链配置详情

    示例请求:
        ```bash
        curl -X GET "http://localhost:8000/api/ai-models/strategy/thinking-chains/chain_xxx" \
            -H "Authorization: Bearer <jwt_token>"
        ```

    成功响应示例:
        ```json
        {
            "code": 0,
            "message": "获取成功",
            "data": {
                "id": "chain_xxx",
                "chain_type": "strategy_generation",
                "name": "策略生成思维链",
                "description": "标准策略生成流程",
                "steps": [
                    {"title": "需求分析", "description": "...", "order": 1},
                    {"title": "策略设计", "description": "...", "order": 2}
                ],
                "is_active": true,
                "created_at": "2026-03-08 10:00:00",
                "updated_at": "2026-03-08 10:00:00"
            }
        }
        ```
    """
    try:
        logger.info(f"获取思维链详情，ID: {chain_id}")

        chain = ThinkingChainManager.get_thinking_chain(chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail="思维链不存在")

        return ApiResponse(
            code=0,
            message="获取成功",
            data=chain,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取思维链详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thinking-chains", response_model=ApiResponse)
@jwt_auth_required
async def create_thinking_chain(request: Request, chain_data: ThinkingChainCreate):
    """创建思维链配置

    Args:
        request: FastAPI请求对象
        chain_data: 思维链创建数据，包含:
            - chain_type (str): 思维链类型，必需
            - name (str): 思维链名称，必需
            - description (str): 思维链描述，可选
            - steps (list): 思维链步骤列表，必需
            - is_active (bool): 是否激活，默认True

    Returns:
        ApiResponse: 包含创建的思维链信息

    示例请求:
        ```bash
        curl -X POST "http://localhost:8000/api/ai-models/strategy/thinking-chains" \
            -H "Authorization: Bearer <jwt_token>" \
            -H "Content-Type: application/json" \
            -d '{
                "chain_type": "strategy_generation",
                "name": "自定义策略思维链",
                "description": "用于生成复杂策略的思维链",
                "steps": [
                    {"title": "需求分析", "description": "分析用户需求", "order": 1},
                    {"title": "策略设计", "description": "设计策略结构", "order": 2}
                ],
                "is_active": true
            }'
        ```
    """
    try:
        logger.info(f"创建思维链，名称: {chain_data.name}, 类型: {chain_data.chain_type}")

        # 转换Pydantic模型为字典
        data = chain_data.model_dump()

        result = ThinkingChainManager.create_thinking_chain(data)
        if not result:
            return ApiResponse(
                code=1,
                message="创建思维链失败，请检查输入数据",
                data=None,
            )

        return ApiResponse(
            code=0,
            message="创建成功",
            data=result,
        )

    except Exception as e:
        logger.error(f"创建思维链失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/thinking-chains/{chain_id}", response_model=ApiResponse)
@jwt_auth_required
async def update_thinking_chain(
    request: Request,
    chain_id: str,
    chain_data: ThinkingChainUpdate,
):
    """更新思维链配置

    Args:
        request: FastAPI请求对象
        chain_id: 思维链ID
        chain_data: 思维链更新数据

    Returns:
        ApiResponse: 包含更新后的思维链信息

    示例请求:
        ```bash
        curl -X PUT "http://localhost:8000/api/ai-models/strategy/thinking-chains/chain_xxx" \
            -H "Authorization: Bearer <jwt_token>" \
            -H "Content-Type: application/json" \
            -d '{
                "name": "更新后的名称",
                "description": "更新后的描述",
                "is_active": false
            }'
        ```
    """
    try:
        logger.info(f"更新思维链，ID: {chain_id}")

        # 检查思维链是否存在
        existing = ThinkingChainManager.get_thinking_chain(chain_id)
        if not existing:
            raise HTTPException(status_code=404, detail="思维链不存在")

        # 过滤掉None值，只更新提供的字段
        update_data = {k: v for k, v in chain_data.model_dump().items() if v is not None}

        if not update_data:
            return ApiResponse(
                code=1,
                message="没有提供要更新的字段",
                data=None,
            )

        result = ThinkingChainManager.update_thinking_chain(chain_id, update_data)
        if not result:
            return ApiResponse(
                code=1,
                message="更新思维链失败",
                data=None,
            )

        return ApiResponse(
            code=0,
            message="更新成功",
            data=result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新思维链失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/thinking-chains/{chain_id}", response_model=ApiResponse)
@jwt_auth_required
async def delete_thinking_chain(request: Request, chain_id: str):
    """删除思维链配置

    Args:
        request: FastAPI请求对象
        chain_id: 思维链ID

    Returns:
        ApiResponse: 删除结果

    示例请求:
        ```bash
        curl -X DELETE "http://localhost:8000/api/ai-models/strategy/thinking-chains/chain_xxx" \
            -H "Authorization: Bearer <jwt_token>"
        ```
    """
    try:
        logger.info(f"删除思维链，ID: {chain_id}")

        # 检查思维链是否存在
        existing = ThinkingChainManager.get_thinking_chain(chain_id)
        if not existing:
            raise HTTPException(status_code=404, detail="思维链不存在")

        success = ThinkingChainManager.delete_thinking_chain(chain_id)
        if not success:
            return ApiResponse(
                code=1,
                message="删除思维链失败",
                data=None,
            )

        return ApiResponse(
            code=0,
            message="删除成功",
            data={"id": chain_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除思维链失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thinking-chains/import", response_model=ApiResponse)
@jwt_auth_required
async def import_thinking_chains_from_toml(
    request: Request,
    file: UploadFile = File(..., description="TOML配置文件"),
    update_existing: bool = Query(True, description="是否更新已存在的配置"),
):
    """从TOML文件导入思维链配置

    上传TOML格式的配置文件，批量导入思维链配置。

    Args:
        request: FastAPI请求对象
        file: TOML配置文件
        update_existing: 是否更新已存在的配置（按名称和类型匹配）

    Returns:
        ApiResponse: 导入结果，包含成功、更新、失败的数量和详细信息

    TOML文件格式示例:
        ```toml
        [[thinking_chain]]
        name = "策略生成思维链"
        chain_type = "strategy_generation"
        description = "标准策略生成流程"
        is_active = true

        [[thinking_chain.steps]]
        title = "需求分析"
        description = "分析用户需求，提取关键策略要素"
        order = 1

        [[thinking_chain.steps]]
        title = "策略设计"
        description = "设计策略结构和参数"
        order = 2
        ```

    示例请求:
        ```bash
        curl -X POST "http://localhost:8000/api/ai-models/strategy/thinking-chains/import" \
            -H "Authorization: Bearer <jwt_token>" \
            -F "file=@thinking_chain.toml" \
            -F "update_existing=true"
        ```

    成功响应示例:
        ```json
        {
            "code": 0,
            "message": "导入成功",
            "data": {
                "success": true,
                "created": 2,
                "updated": 1,
                "failed": 0,
                "errors": [],
                "items": [
                    {"id": "chain_xxx", "name": "策略生成思维链", "chain_type": "strategy_generation", "action": "created"}
                ]
            }
        }
        ```
    """
    try:
        filename = file.filename or "unknown"
        logger.info(f"导入思维链配置，文件: {filename}, 更新已有: {update_existing}")

        # 验证文件类型
        if not filename.endswith('.toml'):
            return ApiResponse(
                code=1,
                message="仅支持TOML格式文件(.toml)",
                data=None,
            )

        # 读取文件内容
        content = await file.read()
        try:
            file_content = content.decode('utf-8')
        except UnicodeDecodeError:
            return ApiResponse(
                code=1,
                message="文件编码错误，请使用UTF-8编码",
                data=None,
            )

        # 执行导入
        result = ThinkingChainManager.import_from_toml(file_content, update_existing=update_existing)

        if result["success"]:
            message = f"导入成功，新建{result['created']}条，更新{result['updated']}条"
            if result["failed"] > 0:
                message += f"，失败{result['failed']}条"
            return ApiResponse(
                code=0,
                message=message,
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message=f"导入失败，失败{result['failed']}条",
                data=result,
            )

    except Exception as e:
        logger.error(f"导入思维链配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
