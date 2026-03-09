# AI模型配置服务层
# 提供模型可用性检查、厂商适配等功能

from typing import Any, Dict, List, Optional

import httpx
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from openai import AsyncOpenAI, APIError, APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError


class AIProviderAdapter:
    """AI厂商适配器基类"""
    
    def __init__(self, api_key: str, api_host: Optional[str] = None, 
                 proxy_enabled: Optional[bool] = None, proxy_url: Optional[str] = None,
                 proxy_username: Optional[str] = None, proxy_password: Optional[str] = None):
        self.api_key = api_key
        self.api_host = api_host
        self.proxy_enabled = proxy_enabled
        self.proxy_url = proxy_url
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查服务可用性"""
        raise NotImplementedError
    
    async def fetch_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        raise NotImplementedError


class OpenAICompatibleAdapter(AIProviderAdapter):
    """OpenAI兼容API适配器基类"""
    
    DEFAULT_API_HOST = "https://api.openai.com"
    DEFAULT_MODEL = "gpt-3.5-turbo"
    PROVIDER_NAME = "OpenAI兼容API"
    
    def __init__(self, api_key: str, api_host: Optional[str] = None,
                 proxy_enabled: Optional[bool] = None, proxy_url: Optional[str] = None,
                 proxy_username: Optional[str] = None, proxy_password: Optional[str] = None):
        super().__init__(api_key, api_host, proxy_enabled, proxy_url, proxy_username, proxy_password)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip('/')
        if not self.base_url.endswith('/v1'):
            self.base_url = f"{self.base_url}/v1"
        
        client_kwargs = {
            'api_key': api_key,
            'base_url': self.base_url
        }
        
        if proxy_enabled and proxy_url:
            client_kwargs['http_client'] = httpx.AsyncClient(
                proxy=proxy_url if proxy_enabled else None,
                auth=(proxy_username, proxy_password) if proxy_username and proxy_password else None
            )
        
        self.client = AsyncOpenAI(**client_kwargs)
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查服务可用性"""
        try:
            response = await self.client.chat.completions.create(
                model=self.DEFAULT_MODEL,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
                timeout=30.0
            )
            return {
                "available": True,
                "message": f"{self.PROVIDER_NAME}服务可用",
                "response": response.choices[0].message.content if response.choices else None
            }
        except AuthenticationError:
            return {
                "available": False,
                "message": "API密钥无效或已过期",
                "error": "Invalid API key"
            }
        except RateLimitError:
            return {
                "available": False,
                "message": "请求过于频繁，请稍后再试",
                "error": "Rate limit exceeded"
            }
        except APITimeoutError:
            return {
                "available": False,
                "message": "请求超时，请检查网络连接或API地址",
                "error": "Request timeout"
            }
        except APIConnectionError:
            return {
                "available": False,
                "message": "无法连接到服务，请检查API地址",
                "error": "Connection error"
            }
        except APIError as e:
            return {
                "available": False,
                "message": f"服务返回错误: {str(e)}",
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"检查{self.PROVIDER_NAME}服务可用性失败: {e}")
            return {
                "available": False,
                "message": f"检查服务可用性失败: {str(e)}",
                "error": str(e)
            }
    
    async def fetch_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        try:
            models = await self.client.models.list(timeout=30.0)
            formatted_models = []
            for model in models.data:
                formatted_models.append({
                    "id": model.id,
                    "name": model.id,
                    "description": self._get_model_description(model.id),
                    "provider": self.__class__.__name__.replace("Adapter", "").lower()
                })
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
            "gpt-3.5-turbo": "GPT-3.5 Turbo，快速且经济的选择"
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
            "deepseek-coder": "DeepSeek Coder，代码生成模型"
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
            "qwen-max": "Qwen Max，通义千问最高版"
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
    
    def __init__(self, api_key: str, api_host: Optional[str] = None):
        super().__init__(api_key or "ollama", api_host)
    
    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        return f"Ollama本地模型: {model_id}"


class AnthropicAdapter(AIProviderAdapter):
    """Anthropic厂商适配器"""
    
    DEFAULT_API_HOST = "https://api.anthropic.com"
    
    def __init__(self, api_key: str, api_host: Optional[str] = None,
                 proxy_enabled: Optional[bool] = None, proxy_url: Optional[str] = None,
                 proxy_username: Optional[str] = None, proxy_password: Optional[str] = None):
        super().__init__(api_key, api_host, proxy_enabled, proxy_url, proxy_username, proxy_password)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip('/')
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查Anthropic服务可用性"""
        try:
            client_kwargs = {'timeout': 30.0}
            if self.proxy_enabled and self.proxy_url:
                client_kwargs['proxy'] = self.proxy_url
                if self.proxy_username and self.proxy_password:
                    client_kwargs['auth'] = (self.proxy_username, self.proxy_password)
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    return {
                        "available": True,
                        "message": "Anthropic服务可用",
                        "models_count": len(models)
                    }
                elif response.status_code == 401:
                    return {
                        "available": False,
                        "message": "API密钥无效或已过期",
                        "error": "Invalid API key"
                    }
                elif response.status_code == 429:
                    return {
                        "available": False,
                        "message": "请求过于频繁，请稍后再试",
                        "error": "Rate limit exceeded"
                    }
                else:
                    return {
                        "available": False,
                        "message": f"服务返回错误: HTTP {response.status_code}",
                        "error": response.text
                    }
        except httpx.TimeoutException:
            return {
                "available": False,
                "message": "请求超时，请检查网络连接或API地址",
                "error": "Request timeout"
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "message": "无法连接到服务，请检查API地址",
                "error": "Connection error"
            }
        except Exception as e:
            logger.error(f"检查Anthropic服务可用性失败: {e}")
            return {
                "available": False,
                "message": f"检查服务可用性失败: {str(e)}",
                "error": str(e)
            }
    
    async def fetch_models(self) -> List[Dict[str, Any]]:
        """获取Anthropic可用模型列表"""
        try:
            client_kwargs = {'timeout': 30.0}
            if self.proxy_enabled and self.proxy_url:
                client_kwargs['proxy'] = self.proxy_url
                if self.proxy_username and self.proxy_password:
                    client_kwargs['auth'] = (self.proxy_username, self.proxy_password)
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    formatted_models = []
                    for model in models:
                        model_id = model.get("id", "")
                        formatted_models.append({
                            "id": model_id,
                            "name": model_id,
                            "description": self._get_model_description(model_id),
                            "provider": "anthropic"
                        })
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
            "claude-3-5-sonnet": "Claude 3.5 Sonnet，增强的Claude模型"
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
        "openai-compatible": OpenAICompatibleAdapter
    }
    
    @staticmethod
    def get_adapter(provider: str, api_key: str, api_host: Optional[str] = None,
                    proxy_enabled: Optional[bool] = None, proxy_url: Optional[str] = None,
                    proxy_username: Optional[str] = None, proxy_password: Optional[str] = None) -> Optional[AIProviderAdapter]:
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
                proxy_password
            )
        return None
    
    @staticmethod
    async def check_provider_availability(
        provider: str,
        api_key: str,
        api_host: Optional[str] = None,
        proxy_enabled: Optional[bool] = None,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None
    ) -> Dict[str, Any]:
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
            proxy_password
        )
        if not adapter:
            return {
                "available": False,
                "message": f"不支持的厂商: {provider}",
                "error": "Unsupported provider",
                "supported_providers": list(AIModelService.ADAPTERS.keys())
            }
        
        result = await adapter.check_availability()
        
        # 如果可用，获取模型列表
        if result.get("available"):
            models = await adapter.fetch_models()
            result["models"] = models
        
        return result
    
    @staticmethod
    async def fetch_available_models(
        provider: str,
        api_key: str,
        api_host: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
    def get_supported_providers() -> List[Dict[str, str]]:
        """获取支持的厂商列表
        
        Returns:
            List[Dict]: 支持的厂商信息列表
        """
        return [
            {"id": "openai", "name": "OpenAI", "description": "OpenAI GPT系列模型"},
            {"id": "anthropic", "name": "Anthropic", "description": "Anthropic Claude系列模型"},
            {"id": "deepseek", "name": "DeepSeek", "description": "DeepSeek系列模型"},
            {"id": "siliconflow", "name": "SiliconFlow", "description": "SiliconFlow AI模型平台"},
            {"id": "openrouter", "name": "OpenRouter", "description": "OpenRouter多模型聚合平台"},
            {"id": "dashscope", "name": "DashScope", "description": "阿里云百炼通义千问模型"},
            {"id": "ollama", "name": "Ollama", "description": "本地运行的Ollama模型"},
            {"id": "openai-compatible", "name": "OpenAI兼容API", "description": "任意OpenAI兼容的API服务"}
        ]
