"""策略生成服务模块

提供基于AI的策略生成功能，支持同步和流式两种调用方式。
集成提示词管理器，支持完整的错误处理和日志记录。
集成思维链管理，支持策略生成过程的可视化追踪。
"""

import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from openai import (
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from openai import APIConnectionError as OpenAIAPIConnectionError

from ai_model.performance_monitor import get_performance_monitor
from ai_model.prompts import PromptCategory, PromptManager
from ai_model.thinking_chain import ThinkingChainManager


class StrategyGenerationError(Exception):
    """策略生成错误基类"""

    def __init__(self, message: str, error_code: str = "unknown"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class APIConnectionError(StrategyGenerationError):
    """API连接错误"""

    def __init__(self, message: str):
        super().__init__(message, "api_connection_error")


class APIAuthenticationError(StrategyGenerationError):
    """API认证错误"""

    def __init__(self, message: str):
        super().__init__(message, "api_authentication_error")


class APIRateLimitError(StrategyGenerationError):
    """API速率限制错误"""

    def __init__(self, message: str):
        super().__init__(message, "api_rate_limit_error")


class ResponseParseError(StrategyGenerationError):
    """响应解析错误"""

    def __init__(self, message: str):
        super().__init__(message, "response_parse_error")


class StrategyGenerator:
    """策略生成器

    基于OpenAI兼容API的策略生成服务，支持同步和流式生成。
    集成提示词管理器，提供完整的错误处理和日志记录。
    集成思维链管理，支持策略生成过程的可视化追踪。

    Attributes:
        api_key: API密钥
        api_host: API主机地址
        model_id: 模型ID
        temperature: 生成温度参数
        prompt_manager: 提示词管理器实例
        thinking_chain: 当前使用的思维链配置
        thinking_chain_state: 思维链状态管理
    """

    DEFAULT_API_HOST = "https://api.openai.com"
    DEFAULT_MODEL = "gpt-4"
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_TIMEOUT = 120.0  # 默认超时时间（秒），流式请求需要更长时间

    # 思维链步骤定义
    THINKING_CHAIN_STEPS = [
        {"key": "analyze_requirement", "title": "分析需求", "description": "分析用户策略需求，提取关键要素"},
        {"key": "design_strategy", "title": "设计策略", "description": "根据需求设计交易策略逻辑"},
        {"key": "generate_code", "title": "生成代码", "description": "将策略逻辑转换为可执行代码"},
        {"key": "optimize", "title": "优化完善", "description": "优化代码结构和性能"},
    ]

    def __init__(
        self,
        api_key: str,
        api_host: Optional[str] = None,
        model_id: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        chain_type: str = "strategy_generation",
    ):
        """初始化策略生成器

        Args:
            api_key: OpenAI API密钥
            api_host: API主机地址，默认为OpenAI官方API
            model_id: 使用的模型ID（用于内部标识），默认为gpt-4
            model_name: 使用的模型名称（用于API调用），默认为model_id的值
            temperature: 生成温度(0-2)，默认为0.7
            chain_type: 思维链类型，默认为strategy_generation
        """
        self.api_key = api_key
        self.api_host = (api_host or self.DEFAULT_API_HOST).rstrip("/")
        self.model_id = model_id or self.DEFAULT_MODEL
        self.model_name = model_name or self.model_id  # 如果没有提供model_name，使用model_id
        self.temperature = temperature or self.DEFAULT_TEMPERATURE
        self.chain_type = chain_type

        # 初始化OpenAI客户端，设置超时时间
        # 流式请求需要更长的超时时间，因为数据是逐步返回的
        self._client = OpenAI(
            api_key=api_key,
            base_url=self._get_base_url(),
            timeout=self.DEFAULT_TIMEOUT,
        )

        # 初始化提示词管理器
        self._prompt_manager = PromptManager()

        # 初始化性能监控器
        self._performance_monitor = get_performance_monitor()

        # 初始化思维链状态管理
        self._thinking_chain = None
        self._thinking_chain_steps = []
        self._current_step_index = 0
        self._thinking_chain_state = {}

        # 加载思维链配置
        self._load_thinking_chain()

        logger.info(
            f"StrategyGenerator初始化完成，模型ID: {self.model_id}, "
            f"模型名称: {self.model_name}, "
            f"API主机: {self.api_host}, "
            f"思维链类型: {self.chain_type}"
        )

    def _load_thinking_chain(self) -> None:
        """加载思维链配置

        从数据库加载对应类型的思维链配置，如果没有则使用默认配置
        """
        try:
            chain = ThinkingChainManager.get_active_chain_by_type(self.chain_type)
            if chain:
                self._thinking_chain = chain
                self._thinking_chain_steps = chain.get("steps", [])
                logger.info(f"思维链配置加载成功: {chain.get('name', 'unknown')}, 步骤数: {len(self._thinking_chain_steps)}")
            else:
                # 使用默认配置
                self._thinking_chain_steps = self.THINKING_CHAIN_STEPS
                logger.info(f"使用默认思维链配置，步骤数: {len(self._thinking_chain_steps)}")
        except Exception as e:
            logger.warning(f"加载思维链配置失败: {e}，使用默认配置")
            self._thinking_chain_steps = self.THINKING_CHAIN_STEPS

    def _init_thinking_chain_state(self) -> Dict[str, Any]:
        """初始化思维链状态

        Returns:
            思维链初始状态字典
        """
        steps = []
        for i, step in enumerate(self._thinking_chain_steps):
            steps.append({
                "key": step.get("key", f"step_{i}"),
                "title": step.get("title", f"步骤{i+1}"),
                "description": step.get("description", ""),
                "order": i + 1,
                "status": "pending",
            })

        self._thinking_chain_state = {
            "steps": steps,
            "current_step": 0,
            "total_steps": len(steps),
            "overall_status": "pending",
        }
        self._current_step_index = 0
        return self._thinking_chain_state

    def _update_step_status(self, step_index: int, status: str, message: Optional[str] = None) -> Dict[str, Any]:
        """更新思维链步骤状态

        Args:
            step_index: 步骤索引
            status: 状态 (pending/processing/completed/error)
            message: 可选的状态消息

        Returns:
            更新后的思维链状态
        """
        if not self._thinking_chain_state or "steps" not in self._thinking_chain_state:
            return {}

        steps = self._thinking_chain_state["steps"]
        if 0 <= step_index < len(steps):
            steps[step_index]["status"] = status
            if message:
                steps[step_index]["message"] = message

        # 更新当前步骤索引
        self._current_step_index = step_index
        self._thinking_chain_state["current_step"] = step_index + 1

        # 计算进度
        completed_steps = sum(1 for s in steps if s["status"] == "completed")
        progress = (completed_steps / len(steps)) * 100 if steps else 0
        self._thinking_chain_state["progress"] = round(progress, 1)

        # 更新整体状态
        if any(s["status"] == "error" for s in steps):
            self._thinking_chain_state["overall_status"] = "error"
        elif all(s["status"] == "completed" for s in steps):
            self._thinking_chain_state["overall_status"] = "completed"
        elif any(s["status"] == "processing" for s in steps):
            self._thinking_chain_state["overall_status"] = "processing"
        else:
            self._thinking_chain_state["overall_status"] = "pending"

        return self._thinking_chain_state

    def _get_current_step_info(self) -> Dict[str, Any]:
        """获取当前步骤信息

        Returns:
            当前步骤的信息字典
        """
        if not self._thinking_chain_state or "steps" not in self._thinking_chain_state:
            return {}

        steps = self._thinking_chain_state["steps"]
        current_step = self._current_step_index

        if 0 <= current_step < len(steps):
            step = steps[current_step]
            return {
                "current_step": current_step + 1,
                "total_steps": len(steps),
                "step_title": step.get("title", ""),
                "step_key": step.get("key", ""),
                "status": step.get("status", "pending"),
                "progress": self._thinking_chain_state.get("progress", 0),
            }
        return {}

    def _get_base_url(self) -> str:
        """获取基础URL，确保包含/v1路径"""
        base_url = self.api_host
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return base_url

    def generate_strategy(
        self,
        requirement: str,
        prompt_category: PromptCategory = PromptCategory.STRATEGY_GENERATION,
        **template_vars: Any,
    ) -> Dict[str, Any]:
        """同步生成策略

        根据用户需求生成完整的策略代码，返回包含代码和元数据的字典。

        Args:
            requirement: 用户的策略需求描述
            prompt_category: 提示词模板分类，默认为策略生成
            **template_vars: 模板变量，用于替换提示词中的占位符

        Returns:
            Dict包含以下字段:
                - success: 是否成功
                - code: 生成的策略代码
                - raw_content: 原始响应内容
                - metadata: 包含模型、耗时等元数据
                - error: 错误信息(如果失败)

        Raises:
            APIAuthenticationError: API密钥无效
            APIConnectionError: 连接失败
            APIRateLimitError: 请求过于频繁
            ResponseParseError: 响应解析失败
        """
        start_time = time.time()
        request_id = f"req_{int(start_time * 1000)}"

        logger.info(
            f"[{request_id}] 开始生成策略，模型ID: {self.model_id}, 模型名称: {self.model_name}, "
            f"需求长度: {len(requirement)}字符"
        )

        try:
            # 构建完整提示词
            prompt = self._build_prompt(requirement, prompt_category, **template_vars)
            logger.debug(f"[{request_id}] 提示词长度: {len(prompt)}字符")

            # 调用API（使用model_name进行API调用）
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一个专业的量化交易策略生成专家。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.DEFAULT_MAX_TOKENS,
            )

            # 提取响应内容
            content = response.choices[0].message.content
            elapsed_time = time.time() - start_time

            logger.info(
                f"[{request_id}] API调用成功，耗时: {elapsed_time:.2f}s, "
                f"Token使用: {response.usage.total_tokens if response.usage else 'N/A'}"
            )

            # 解析响应
            result = self._parse_response(content or "")
            result["metadata"] = {
                "request_id": request_id,
                "model": self.model_id,
                "elapsed_time": elapsed_time,
                "total_tokens": response.usage.total_tokens if response.usage else None,
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens
                if response.usage
                else None,
            }

            # 记录性能指标
            total_tokens = response.usage.total_tokens if response.usage else None
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=result.get("success", False),
                generation_time=elapsed_time,
                tokens_used=total_tokens,
                error_code=None,
            )

            return result

        except AuthenticationError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API认证失败: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_authentication_error",
            )
            raise APIAuthenticationError(f"API密钥无效或已过期: {str(e)}")
        except RateLimitError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API速率限制: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_rate_limit_error",
            )
            raise APIRateLimitError(f"请求过于频繁，请稍后再试: {str(e)}")
        except APITimeoutError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API请求超时: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_timeout_error",
            )
            raise APIConnectionError(f"请求超时，请检查网络连接: {str(e)}")
        except OpenAIAPIConnectionError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API连接错误: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_connection_error",
            )
            raise APIConnectionError(f"无法连接到API服务: {str(e)}")
        except APIError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API错误: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_error",
            )
            raise StrategyGenerationError(f"API服务错误: {str(e)}", "api_error")
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] 策略生成失败: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="generation_failed",
            )
            raise StrategyGenerationError(f"策略生成失败: {str(e)}", "generation_failed")

    def _create_thinking_chain_event(self, step_index: int, status: str, message: Optional[str] = None) -> Dict[str, Any]:
        """创建思维链状态更新事件

        Args:
            step_index: 步骤索引
            status: 状态 (pending/processing/completed/error)
            message: 可选的状态消息

        Returns:
            SSE事件格式的字典
        """
        # 更新步骤状态
        self._update_step_status(step_index, status, message)
        step_info = self._get_current_step_info()

        return {
            "type": "thinking_chain",
            "data": {
                "current_step": step_info.get("current_step", step_index + 1),
                "total_steps": step_info.get("total_steps", len(self._thinking_chain_steps)),
                "step_title": step_info.get("step_title", ""),
                "step_description": self._thinking_chain_steps[step_index].get("description", "") if 0 <= step_index < len(self._thinking_chain_steps) else "",
                "step_key": step_info.get("step_key", ""),
                "status": status,
                "progress": step_info.get("progress", 0),
                "message": message,
            },
        }

    async def generate_strategy_stream(
        self,
        requirement: str,
        prompt_category: PromptCategory = PromptCategory.STRATEGY_GENERATION,
        **template_vars: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式生成策略

        以流式方式生成策略代码，适用于需要实时显示生成进度的场景。
        集成思维链状态管理，在生成过程中发送思维链状态更新事件。

        Args:
            requirement: 用户的策略需求描述
            prompt_category: 提示词模板分类，默认为策略生成
            **template_vars: 模板变量，用于替换提示词中的占位符

        Yields:
            Dict包含以下字段:
                - type: 消息类型 ("content", "done", "error", "thinking_chain")
                - content: 生成的内容片段(仅type=content时)
                - code: 完整提取的代码(仅type=done时)
                - metadata: 生成元数据(仅type=done时)
                - error: 错误信息(仅type=error时)
                - data: 思维链状态数据(仅type=thinking_chain时)

        Raises:
            APIAuthenticationError: API密钥无效
            APIConnectionError: 连接失败
            APIRateLimitError: 请求过于频繁
        """
        start_time = time.time()
        request_id = f"stream_{int(start_time * 1000)}"

        logger.info(
            f"[{request_id}] 开始流式生成策略，模型ID: {self.model_id}, 模型名称: {self.model_name}"
        )

        # 初始化思维链状态
        self._init_thinking_chain_state()

        try:
            # 步骤1: 分析需求 - 开始
            yield self._create_thinking_chain_event(0, "processing", "正在分析策略需求...")
            logger.info(f"[{request_id}] 思维链步骤1: 分析需求 - 开始")

            # 构建完整提示词
            prompt = self._build_prompt(requirement, prompt_category, **template_vars)

            # 步骤1: 分析需求 - 完成
            yield self._create_thinking_chain_event(0, "completed", "需求分析完成")
            logger.info(f"[{request_id}] 思维链步骤1: 分析需求 - 完成")

            # 步骤2: 设计策略 - 开始
            yield self._create_thinking_chain_event(1, "processing", "正在设计交易策略逻辑...")
            logger.info(f"[{request_id}] 思维链步骤2: 设计策略 - 开始")

            # 流式调用API（使用model_name进行API调用）
            stream = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一个专业的量化交易策略生成专家。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.DEFAULT_MAX_TOKENS,
                stream=True,
            )

            # 步骤2: 设计策略 - 完成
            yield self._create_thinking_chain_event(1, "completed", "策略设计完成")
            logger.info(f"[{request_id}] 思维链步骤2: 设计策略 - 完成")

            # 步骤3: 生成代码 - 开始
            yield self._create_thinking_chain_event(2, "processing", "正在生成策略代码...")
            logger.info(f"[{request_id}] 思维链步骤3: 生成代码 - 开始")

            full_content = ""
            chunk_count = 0

            for chunk in stream:
                chunk_count += 1
                delta = chunk.choices[0].delta.content

                if delta:
                    full_content += delta
                    yield {
                        "type": "content",
                        "content": delta,
                        "request_id": request_id,
                    }

            # 步骤3: 生成代码 - 完成
            yield self._create_thinking_chain_event(2, "completed", "代码生成完成")
            logger.info(f"[{request_id}] 思维链步骤3: 生成代码 - 完成")

            elapsed_time = time.time() - start_time
            logger.info(
                f"[{request_id}] 流式生成完成，耗时: {elapsed_time:.2f}s, "
                f"接收{chunk_count}个数据块"
            )

            # 步骤4: 优化完善 - 开始
            yield self._create_thinking_chain_event(3, "processing", "正在优化代码结构...")
            logger.info(f"[{request_id}] 思维链步骤4: 优化完善 - 开始")

            # 解析完整响应
            result = self._parse_response(full_content)

            # 步骤4: 优化完善 - 完成
            yield self._create_thinking_chain_event(3, "completed", "代码优化完成")
            logger.info(f"[{request_id}] 思维链步骤4: 优化完善 - 完成")

            # 记录性能指标（流式请求没有token使用量）
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=result.get("success", False),
                generation_time=elapsed_time,
                tokens_used=None,
                error_code=None,
            )

            yield {
                "type": "done",
                "code": result.get("code"),
                "raw_content": full_content,
                "metadata": {
                    "request_id": request_id,
                    "model": self.model_id,
                    "elapsed_time": elapsed_time,
                    "chunk_count": chunk_count,
                },
            }

        except AuthenticationError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API认证失败: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_authentication_error",
            )
            # 更新思维链状态为错误
            if self._thinking_chain_state:
                yield self._create_thinking_chain_event(self._current_step_index, "error", f"API认证失败: {str(e)}")
            yield {
                "type": "error",
                "error": f"API密钥无效或已过期: {str(e)}",
                "error_code": "api_authentication_error",
                "request_id": request_id,
            }
        except RateLimitError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API速率限制: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_rate_limit_error",
            )
            # 更新思维链状态为错误
            if self._thinking_chain_state:
                yield self._create_thinking_chain_event(self._current_step_index, "error", f"API速率限制: {str(e)}")
            yield {
                "type": "error",
                "error": f"请求过于频繁，请稍后再试: {str(e)}",
                "error_code": "api_rate_limit_error",
                "request_id": request_id,
            }
        except APITimeoutError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API请求超时: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_timeout_error",
            )
            # 更新思维链状态为错误
            if self._thinking_chain_state:
                yield self._create_thinking_chain_event(self._current_step_index, "error", f"请求超时: {str(e)}")
            yield {
                "type": "error",
                "error": f"请求超时，请检查网络连接: {str(e)}",
                "error_code": "api_connection_error",
                "request_id": request_id,
            }
        except OpenAIAPIConnectionError as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] API连接错误: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="api_connection_error",
            )
            # 更新思维链状态为错误
            if self._thinking_chain_state:
                yield self._create_thinking_chain_event(self._current_step_index, "error", f"API连接错误: {str(e)}")
            yield {
                "type": "error",
                "error": f"无法连接到API服务: {str(e)}",
                "error_code": "api_connection_error",
                "request_id": request_id,
            }
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[{request_id}] 流式生成失败: {e}")
            self._performance_monitor.record_request(
                model_id=self.model_id,
                success=False,
                generation_time=elapsed_time,
                tokens_used=None,
                error_code="generation_failed",
            )
            # 更新思维链状态为错误
            if self._thinking_chain_state:
                yield self._create_thinking_chain_event(self._current_step_index, "error", f"生成失败: {str(e)}")
            yield {
                "type": "error",
                "error": f"策略生成失败: {str(e)}",
                "error_code": "generation_failed",
                "request_id": request_id,
            }

    def _build_prompt(
        self,
        requirement: str,
        category: PromptCategory,
        **template_vars: Any,
    ) -> str:
        """构建完整提示词

        使用提示词管理器渲染模板，并注入用户需求。

        Args:
            requirement: 用户需求描述
            category: 提示词分类
            **template_vars: 额外的模板变量

        Returns:
            完整的提示词字符串
        """
        # 默认变量
        default_vars = {
            "user_description": requirement,
            "strategy_name": template_vars.get("strategy_name", "GeneratedStrategy"),
            "strategy_description": template_vars.get(
                "strategy_description", "AI生成的策略"
            ),
            "symbol": template_vars.get("symbol", "BTC/USDT"),
            "timeframe": template_vars.get("timeframe", "1h"),
            "initial_capital": template_vars.get("initial_capital", "10000"),
            "risk_percent": template_vars.get("risk_percent", "2"),
        }

        # 合并用户提供的变量
        default_vars.update(template_vars)

        return self._prompt_manager.render(category, **default_vars)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """解析API响应

        从响应内容中提取代码块和元数据。

        Args:
            content: API返回的原始内容

        Returns:
            Dict包含:
                - success: 解析是否成功
                - code: 提取的代码
                - raw_content: 原始内容
                - error: 错误信息(如果失败)
        """
        if not content or not content.strip():
            return {
                "success": False,
                "code": None,
                "raw_content": content,
                "error": "响应内容为空",
            }

        try:
            code = self._extract_code(content)

            if not code:
                return {
                    "success": False,
                    "code": None,
                    "raw_content": content,
                    "error": "未能从响应中提取到代码块",
                }

            return {
                "success": True,
                "code": code,
                "raw_content": content,
                "error": None,
            }

        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return {
                "success": False,
                "code": None,
                "raw_content": content,
                "error": f"解析失败: {str(e)}",
            }

    def _extract_code(self, content: str) -> Optional[str]:
        """从响应内容中提取代码块

        支持多种代码块格式:
        - ```python ... ```
        - ``` ... ```
        - 直接返回纯文本(如果没有代码块标记)

        Args:
            content: 原始响应内容

        Returns:
            提取的代码字符串，如果没有找到代码块则返回None
        """
        if not content:
            return None

        # 尝试匹配带语言标识的代码块
        patterns = [
            r"```python\s*\n(.*?)\n```",  # ```python ... ```
            r"```\s*\n(.*?)\n```",  # ``` ... ```
            r"```python\s*(.*?)\s*```",  # ```python ... ``` (单行)
            r"```\s*(.*?)\s*```",  # ``` ... ``` (单行)
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                code = match.group(1).strip()
                if code:
                    return code

        # 如果没有找到代码块标记，检查内容是否像Python代码
        # 通过检查是否包含常见的Python关键字来判断
        python_indicators = [
            r"^\s*(class|def|import|from)\s+",
            r"^\s*#.*",
            r"^\s*\"\"\"",
            r"^\s*'''",
        ]

        for indicator in python_indicators:
            if re.search(indicator, content, re.MULTILINE):
                return content.strip()

        # 如果都不匹配，返回整个内容(可能是纯代码)
        return content.strip() if content.strip() else None

    def validate_code(self, code: str) -> Dict[str, Any]:
        """验证生成的代码

        对生成的代码进行基本语法验证。

        Args:
            code: 生成的Python代码

        Returns:
            Dict包含:
                - valid: 是否有效
                - errors: 错误列表
        """
        if not code:
            return {"valid": False, "errors": ["代码为空"]}

        errors = []

        # 检查基本语法
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            errors.append(f"语法错误: {e.msg} (第{e.lineno}行)")
        except Exception as e:
            errors.append(f"编译错误: {str(e)}")

        # 检查必要的结构
        if "class" not in code:
            errors.append("警告: 代码中未找到类定义")

        if "def " not in code:
            errors.append("警告: 代码中未找到函数定义")

        return {
            "valid": len([e for e in errors if not e.startswith("警告")]) == 0,
            "errors": errors,
        }
