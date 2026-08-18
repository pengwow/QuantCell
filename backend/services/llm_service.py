"""LLM Service — axon_quant.llm LLM 后端服务

包装 axon_quant.llm.LLMBackend，提供 LLM 调用功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant.llm import (
        LLMBackend as _LLMBackend,
    )
    from axon_quant.llm import (
        LLMConfig as _LLMConfig,
    )
    from axon_quant.llm import (
        LLMMessage as _LLMMessage,
    )
    from axon_quant.llm import (
        make_backend as _make_backend,
    )

    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _LLMBackend = None
    _LLMConfig = None
    _LLMMessage = None
    _make_backend = None


class LLMServiceWrapper:
    """LLM 服务包装器

    包装 axon_quant.llm.LLMBackend，提供 LLM 调用功能。

    Example:
        >>> svc = LLMServiceWrapper({
        ...     "backends": [{
        ...         "base_url": "https://api.example.com/v1",
        ...         "api_key": "sk-xxx",
        ...         "model": "model-name",
        ...     }]
        ... })
        >>> response = svc.chat([{"role": "user", "content": "Hi!"}])
    """

    def __init__(self, config: dict[str, Any]):
        """初始化 LLM 服务

        Args:
            config: 配置字典，包含:
                - backends: 后端列表，每个包含:
                    - base_url: API 基础 URL
                    - api_key: API Key
                    - model: 模型名称
        """
        if not AXON_AVAILABLE:
            msg = "axon_quant.llm 不可用，请安装 axon_quant: pip install axon_quant"
            raise RuntimeError(msg)

        self._backend = _make_backend(config)
        logger.info("LLMService 已初始化")

    def chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """发送聊天请求

        Args:
            messages: 消息列表，每个包含:
                - role: "user" 或 "assistant"
                - content: 消息内容

        Returns:
            响应字典，包含:
                - content: 响应内容
                - 其他元数据
        """
        # 转换消息格式
        llm_messages = [_LLMMessage(m["role"], m["content"]) for m in messages]

        # 发送请求
        response = self._backend.chat(llm_messages)
        return response


class LLMServiceProxy:
    """LLM 服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._available = AXON_AVAILABLE
        if self._available and config:
            try:
                self._service = LLMServiceWrapper(config)
            except Exception as e:
                logger.error(f"创建 LLMService 失败: {e}")
                self._available = False
                self._service = None
        else:
            self._service = None
            if not self._available:
                logger.warning("axon_quant.llm 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.llm 是否可用"""
        return self._available

    def chat(self, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        """发送聊天请求"""
        if not self._available or not self._service:
            return None
        return self._service.chat(messages)
