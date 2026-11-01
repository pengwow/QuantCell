# AI模型配置服务层
# 提供模型可用性检查、厂商适配等功能

from typing import Any

import httpx

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)


class AIProviderAdapter:
    """AI厂商适配器基类"""

    def __init__(
        self,
        api_key: str,
        api_host: str | None = None,
        proxy_enabled: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ):
        self.api_key = api_key
        self.api_host = api_host
        self.proxy_enabled = proxy_enabled
        self.proxy_url = proxy_url
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password

    async def check_availability(self) -> dict[str, Any]:
        """检查服务可用性"""
        raise NotImplementedError

    async def fetch_models(self) -> list[dict[str, Any]]:
        """获取可用模型列表"""
        raise NotImplementedError


class OpenAICompatibleAdapter(AIProviderAdapter):
    """OpenAI兼容API适配器基类"""

    DEFAULT_API_HOST = "https://api.openai.com"
    DEFAULT_MODEL = "gpt-3.5-turbo"
    PROVIDER_NAME = "OpenAI兼容API"

    def __init__(
        self,
        api_key: str,
        api_host: str | None = None,
        proxy_enabled: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ):
        super().__init__(api_key, api_host, proxy_enabled, proxy_url, proxy_username, proxy_password)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"

        client_kwargs = {"api_key": api_key, "base_url": self.base_url}

        if proxy_enabled and proxy_url:
            client_kwargs["http_client"] = httpx.AsyncClient(
                proxy=proxy_url if proxy_enabled else None,
                auth=(proxy_username, proxy_password) if proxy_username and proxy_password else None,
            )

        self.client = AsyncOpenAI(**client_kwargs)

    async def check_availability(self) -> dict[str, Any]:
        """检查服务可用性 — 用 models.list() 验证连通性, 不依赖特定模型名"""
        try:
            models_response = await self.client.models.list(timeout=30.0)
            model_ids = [m.id for m in models_response.data]
            return {
                "available": True,
                "message": f"{self.PROVIDER_NAME}服务可用 (发现 {len(model_ids)} 个模型)",
                "model_count": len(model_ids),
            }
        except AuthenticationError:
            return {
                "available": False,
                "message": "API密钥无效或已过期",
                "error": "Invalid API key",
            }
        except RateLimitError:
            return {
                "available": False,
                "message": "请求过于频繁，请稍后再试",
                "error": "Rate limit exceeded",
            }
        except APITimeoutError:
            return {
                "available": False,
                "message": "请求超时，请检查网络连接或API地址",
                "error": "Request timeout",
            }
        except APIConnectionError:
            return {
                "available": False,
                "message": "无法连接到服务，请检查API地址",
                "error": "Connection error",
            }
        except APIError as e:
            return {
                "available": False,
                "message": f"服务返回错误: {e!s}",
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"检查{self.PROVIDER_NAME}服务可用性失败: {e}")
            return {
                "available": False,
                "message": f"检查服务可用性失败: {e!s}",
                "error": str(e),
            }

    async def fetch_models(self) -> list[dict[str, Any]]:
        """获取可用模型列表"""
        try:
            models = await self.client.models.list(timeout=30.0)
            formatted_models = []
            for model in models.data:
                formatted_models.append(
                    {
                        "id": model.id,
                        "name": model.id,
                        "description": self._get_model_description(model.id),
                        "provider": self.__class__.__name__.replace("Adapter", "").lower(),
                    }
                )
            return formatted_models
        except Exception as e:
            logger.error(f"获取{self.PROVIDER_NAME}模型列表失败: {e}")
            return []

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        return f"{self.PROVIDER_NAME}模型"


class OpenAIAdapter(OpenAICompatibleAdapter):
    """OpenAI厂商适配器"""

    DEFAULT_API_HOST = "https://api.openai.com"
    DEFAULT_MODEL = "gpt-3.5-turbo"
    PROVIDER_NAME = "OpenAI"

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        descriptions = {
            "gpt-4": "GPT-4，最强大的多模态模型",
            "gpt-4-turbo": "GPT-4 Turbo，优化的GPT-4版本",
            "gpt-4o": "GPT-4o，全能多模态模型",
            "gpt-4o-mini": "GPT-4o Mini，轻量级多模态模型",
            "gpt-3.5-turbo": "GPT-3.5 Turbo，快速且经济的选择",
        }
        for key, desc in descriptions.items():
            if key in model_id:
                return desc
        return "OpenAI模型"


class DeepSeekAdapter(OpenAICompatibleAdapter):
    """DeepSeek厂商适配器"""

    DEFAULT_API_HOST = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-chat"
    PROVIDER_NAME = "DeepSeek"

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        descriptions = {
            "deepseek-chat": "DeepSeek Chat，通用对话模型",
            "deepseek-coder": "DeepSeek Coder，代码生成模型",
        }
        return descriptions.get(model_id, "DeepSeek模型")


class SiliconFlowAdapter(OpenAICompatibleAdapter):
    """SiliconFlow厂商适配器"""

    DEFAULT_API_HOST = "https://api.siliconflow.cn"
    DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
    PROVIDER_NAME = "SiliconFlow"

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        return f"SiliconFlow模型: {model_id}"


class OpenRouterAdapter(OpenAICompatibleAdapter):
    """OpenRouter厂商适配器"""

    DEFAULT_API_HOST = "https://openrouter.ai/api"
    DEFAULT_MODEL = "openai/gpt-3.5-turbo"
    PROVIDER_NAME = "OpenRouter"

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        return f"OpenRouter模型: {model_id}"


class DashScopeAdapter(OpenAICompatibleAdapter):
    """DashScope(阿里云百炼)厂商适配器"""

    DEFAULT_API_HOST = "https://dashscope.aliyuncs.com/compatible-mode"
    DEFAULT_MODEL = "qwen-turbo"
    PROVIDER_NAME = "DashScope"

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        descriptions = {
            "qwen-turbo": "Qwen Turbo，通义千问快速版",
            "qwen-plus": "Qwen Plus，通义千问增强版",
            "qwen-max": "Qwen Max，通义千问最高版",
        }
        for key, desc in descriptions.items():
            if key in model_id:
                return desc
        return f"DashScope模型: {model_id}"


class OllamaAdapter(OpenAICompatibleAdapter):
    """Ollama本地模型适配器"""

    DEFAULT_API_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "llama2"
    PROVIDER_NAME = "Ollama"

    def __init__(self, api_key: str, api_host: str | None = None):
        super().__init__(api_key or "ollama", api_host)

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        return f"Ollama本地模型: {model_id}"


class LayaAdapter(OpenAICompatibleAdapter):
    """Laya AI 决策模型（自托管服务，OpenAI 兼容 /v1 接口）。

    与生成式模型不同：laya 是单次前向的 System 1 决策模型，
    api_host 必填且填裸地址（不含 /v1），api_key 自托管无鉴权时可空。
    """

    DEFAULT_API_HOST = "http://127.0.0.1:8787"
    DEFAULT_MODEL = "laya"
    PROVIDER_NAME = "Laya AI"

    def __init__(
        self,
        api_key: str,
        api_host: str | None = None,
        proxy_enabled: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ):
        # OpenAI SDK 不接受空 api_key，自托管无鉴权场景用占位符
        super().__init__(api_key or "laya", api_host, proxy_enabled, proxy_url, proxy_username, proxy_password)

    def _get_model_description(self, model_id: str) -> str:
        """Laya 的三个 checkpoint 说明"""
        descriptions = {
            "laya": "Laya 英文决策模型（421M）",
            "laya-multilingual": "Laya 多语言决策模型（100+ 语言）",
            "laya-typed-decisions": "Laya 结构化决策模型",
        }
        return descriptions.get(model_id, f"Laya 决策模型: {model_id}")


class SystemOneAdapter(AIProviderAdapter):
    """Jev 兼容的 System One 决策模型（原生契约 `POST {api_host}/v1/systemone`）。

    覆盖 Jev 托管的官方 API 以及 Kev / Von / Decider / Rizzo Flow / OpenThai-SystemOne
    这些自托管替代品。它们不保证提供 `/v1/models`，故探活直接打一次最小 systemone 请求。

    注意：QuantCell 的 axon-llm 固定走 `/v1/decide`，原生 systemone 服务需经
    `scripts/local_model_servers/systemone_proxy.py` 转发后再接入。
    """

    DEFAULT_API_HOST = "http://127.0.0.1:8080"
    DEFAULT_MODEL = "jev-1"
    PROVIDER_NAME = "System One 决策模型"

    def _systemone_url(self) -> str:
        base = (self.api_host or self.DEFAULT_API_HOST).rstrip("/")
        return f"{base}/systemone" if base.endswith("/v1") else f"{base}/v1/systemone"

    async def check_availability(self) -> dict[str, Any]:
        """探活：发一个最小 noul 决策请求，比 /v1/models 更贴近真实契约。"""
        payload = {
            "state": {"body": "ping"},
            "questions": {"ping": {"type": "noul", "instructions": "is this a ping?"}},
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self._systemone_url(), json=payload, headers=headers)
            if resp.status_code != 200:
                return {
                    "available": False,
                    "message": f"服务返回状态 {resp.status_code}",
                    "error": resp.text[:300],
                }
            body = resp.json()
            if not isinstance(body.get("answers"), dict):
                return {
                    "available": False,
                    "message": "响应缺少 answers 字段，可能不是 Jev 兼容服务",
                    "error": str(body)[:300],
                }
            return {"available": True, "message": f"{self.PROVIDER_NAME}服务可用"}
        except httpx.TimeoutException:
            return {"available": False, "message": "请求超时，请检查服务地址", "error": "timeout"}
        except httpx.ConnectError:
            return {"available": False, "message": "无法连接，请检查服务地址", "error": "connect"}
        except Exception as e:
            logger.error(f"检查{self.PROVIDER_NAME}服务可用性失败: {e}")
            return {"available": False, "message": f"检查失败: {e!s}", "error": str(e)}

    async def fetch_models(self) -> list[dict[str, Any]]:
        """尽力读 /v1/models；拿不到就返回空，由前端保留自己配置的预设。"""
        base = (self.api_host or self.DEFAULT_API_HOST).rstrip("/")
        url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
            if resp.status_code != 200:
                return []
            data = resp.json().get("data")
            if not isinstance(data, list):
                return []
            return [
                {"id": m.get("id"), "name": m.get("id"), "description": "System One 决策模型"}
                for m in data
                if isinstance(m, dict) and m.get("id")
            ]
        except Exception:
            return []


# Jev 兼容的 System One 模型各自一个子类：仅用于探活报错信息可读，协议实现完全共用。
# api_host 不预设厂商域名（各家部署地址由用户填写），统一回退到本地占位。
class JevAdapter(SystemOneAdapter):
    PROVIDER_NAME = "Jev（TypeSafe 托管）"


class KevAdapter(SystemOneAdapter):
    PROVIDER_NAME = "Kev"


class VonAdapter(SystemOneAdapter):
    PROVIDER_NAME = "Von"


class DeciderAdapter(SystemOneAdapter):
    PROVIDER_NAME = "Decider"


class RizzoFlowAdapter(SystemOneAdapter):
    PROVIDER_NAME = "Rizzo Flow"


class OpenThaiSystemOneAdapter(SystemOneAdapter):
    PROVIDER_NAME = "OpenThai-SystemOne"


class XiaomiAdapter(OpenAICompatibleAdapter):
    """小米(MiMo)厂商适配器"""

    DEFAULT_API_HOST = "https://token-plan-cn.xiaomimimo.com"
    DEFAULT_MODEL = "mimo-v2.5"
    PROVIDER_NAME = "Xiaomi"

    def _get_model_description(self, model_id: str) -> str:
        descriptions = {
            "mimo-v2.5-pro": "MiMo V2.5 Pro，小米最强多模态模型",
            "mimo-v2.5": "MiMo V2.5，小米通用对话模型",
            "mimo-v2.5-tts": "MiMo V2.5 TTS，文本转语音模型",
            "mimo-v2.5-tts-voicedesign": "MiMo V2.5 TTS声音设计，自定义音色",
            "mimo-v2.5-tts-voiceclone": "MiMo V2.5 TTS语音克隆，支持声音复刻",
            "mimo-v2-pro": "MiMo V2 Pro，增强版多模态模型",
            "mimo-v2-omni": "MiMo V2 Omni，全模态理解模型",
            "mimo-v2-tts": "MiMo V2 TTS，文本转语音基础版",
            "mimo-v2-flash": "MiMo V2 Flash，轻量快速推理模型",
        }
        return descriptions.get(model_id, f"小米MiMo模型: {model_id}")


class AnthropicAdapter(AIProviderAdapter):
    """Anthropic厂商适配器"""

    DEFAULT_API_HOST = "https://api.anthropic.com"

    def __init__(
        self,
        api_key: str,
        api_host: str | None = None,
        proxy_enabled: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ):
        super().__init__(api_key, api_host, proxy_enabled, proxy_url, proxy_username, proxy_password)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip("/")
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    async def check_availability(self) -> dict[str, Any]:
        """检查Anthropic服务可用性"""
        try:
            client_kwargs = {"timeout": 30.0}
            if self.proxy_enabled and self.proxy_url:
                client_kwargs["proxy"] = self.proxy_url
                if self.proxy_username and self.proxy_password:
                    client_kwargs["auth"] = (self.proxy_username, self.proxy_password)

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(f"{self.base_url}/v1/models", headers=self.headers)

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    return {
                        "available": True,
                        "message": "Anthropic服务可用",
                        "models_count": len(models),
                    }
                elif response.status_code == 401:
                    return {
                        "available": False,
                        "message": "API密钥无效或已过期",
                        "error": "Invalid API key",
                    }
                elif response.status_code == 429:
                    return {
                        "available": False,
                        "message": "请求过于频繁，请稍后再试",
                        "error": "Rate limit exceeded",
                    }
                else:
                    return {
                        "available": False,
                        "message": f"服务返回错误: HTTP {response.status_code}",
                        "error": response.text,
                    }
        except httpx.TimeoutException:
            return {
                "available": False,
                "message": "请求超时，请检查网络连接或API地址",
                "error": "Request timeout",
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "message": "无法连接到服务，请检查API地址",
                "error": "Connection error",
            }
        except Exception as e:
            logger.error(f"检查Anthropic服务可用性失败: {e}")
            return {
                "available": False,
                "message": f"检查服务可用性失败: {e!s}",
                "error": str(e),
            }

    async def fetch_models(self) -> list[dict[str, Any]]:
        """获取Anthropic可用模型列表"""
        try:
            client_kwargs = {"timeout": 30.0}
            if self.proxy_enabled and self.proxy_url:
                client_kwargs["proxy"] = self.proxy_url
                if self.proxy_username and self.proxy_password:
                    client_kwargs["auth"] = (self.proxy_username, self.proxy_password)

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(f"{self.base_url}/v1/models", headers=self.headers)

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    formatted_models = []
                    for model in models:
                        model_id = model.get("id", "")
                        formatted_models.append(
                            {
                                "id": model_id,
                                "name": model_id,
                                "description": self._get_model_description(model_id),
                                "provider": "anthropic",
                            }
                        )
                    return formatted_models
                else:
                    logger.error(f"获取Anthropic模型列表失败: HTTP {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"获取Anthropic模型列表失败: {e}")
            return []

    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        descriptions = {
            "claude-3-opus": "Claude 3 Opus，最强大的Claude模型",
            "claude-3-sonnet": "Claude 3 Sonnet，平衡的Claude模型",
            "claude-3-haiku": "Claude 3 Haiku，快速的Claude模型",
            "claude-3-5-sonnet": "Claude 3.5 Sonnet，增强的Claude模型",
        }
        for key, desc in descriptions.items():
            if key in model_id:
                return desc
        return "Anthropic Claude模型"


class AIModelService:
    """AI模型配置服务类

    提供模型可用性检查、厂商适配等功能
    """

    # 支持的厂商适配器映射
    ADAPTERS = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "deepseek": DeepSeekAdapter,
        "siliconflow": SiliconFlowAdapter,
        "openrouter": OpenRouterAdapter,
        "dashscope": DashScopeAdapter,
        "ollama": OllamaAdapter,
        "laya": LayaAdapter,
        # Jev 协议的 System One 决策模型（自托管替代品 / 托管 API）
        "jev": JevAdapter,
        "kev": KevAdapter,
        "von": VonAdapter,
        "decider": DeciderAdapter,
        "rizzo-flow": RizzoFlowAdapter,
        "openthai-systemone": OpenThaiSystemOneAdapter,
        "xiaomi": XiaomiAdapter,
        "openai-compatible": OpenAICompatibleAdapter,
    }

    @staticmethod
    def get_adapter(
        provider: str,
        api_key: str,
        api_host: str | None = None,
        proxy_enabled: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ) -> AIProviderAdapter | None:
        """获取厂商适配器

        Args:
            provider: 厂商名称
            api_key: API密钥
            api_host: API主机地址
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码

        Returns:
            Optional[AIProviderAdapter]: 适配器实例，不支持返回None
        """
        adapter_class = AIModelService.ADAPTERS.get(provider.lower())
        if adapter_class:
            return adapter_class(
                api_key,
                api_host,
                proxy_enabled,
                proxy_url,
                proxy_username,
                proxy_password,
            )
        return None

    @staticmethod
    async def check_provider_availability(
        provider: str,
        api_key: str,
        api_host: str | None = None,
        proxy_enabled: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ) -> dict[str, Any]:
        """检查厂商服务可用性

        Args:
            provider: 厂商名称
            api_key: API密钥
            api_host: API主机地址
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码

        Returns:
            Dict: 检查结果，包含available、message、models等字段
        """
        adapter = AIModelService.get_adapter(
            provider,
            api_key,
            api_host,
            proxy_enabled,
            proxy_url,
            proxy_username,
            proxy_password,
        )
        if not adapter:
            return {
                "available": False,
                "message": f"不支持的厂商: {provider}",
                "error": "Unsupported provider",
                "supported_providers": list(AIModelService.ADAPTERS.keys()),
            }

        result = await adapter.check_availability()

        # 如果可用，获取模型列表
        if result.get("available"):
            models = await adapter.fetch_models()
            result["models"] = models

        return result

    @staticmethod
    async def fetch_available_models(provider: str, api_key: str, api_host: str | None = None) -> list[dict[str, Any]]:
        """获取厂商可用模型列表

        Args:
            provider: 厂商名称
            api_key: API密钥
            api_host: API主机地址

        Returns:
            List[Dict]: 可用模型列表
        """
        adapter = AIModelService.get_adapter(provider, api_key, api_host)
        if not adapter:
            return []

        return await adapter.fetch_models()

    @staticmethod
    def get_supported_providers() -> list[dict[str, str]]:
        """获取支持的厂商列表

        Returns:
            List[Dict]: 支持的厂商信息列表
        """
        return [
            {"id": "openai", "name": "OpenAI", "description": "OpenAI GPT系列模型"},
            {
                "id": "anthropic",
                "name": "Anthropic",
                "description": "Anthropic Claude系列模型",
            },
            {"id": "deepseek", "name": "DeepSeek", "description": "DeepSeek系列模型"},
            {
                "id": "siliconflow",
                "name": "SiliconFlow",
                "description": "SiliconFlow AI模型平台",
            },
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "description": "OpenRouter多模型聚合平台",
            },
            {
                "id": "dashscope",
                "name": "DashScope",
                "description": "阿里云百炼通义千问模型",
            },
            {"id": "ollama", "name": "Ollama", "description": "本地运行的Ollama模型"},
            {"id": "xiaomi", "name": "Xiaomi", "description": "小米MiMo系列多模态模型"},
            {
                "id": "openai-compatible",
                "name": "OpenAI兼容API",
                "description": "任意OpenAI兼容的API服务",
            },
        ]
