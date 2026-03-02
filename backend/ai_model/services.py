# AI模型配置服务层
# 提供模型可用性检查、厂商适配等功能

from typing import Any, Dict, List, Optional

import httpx
from loguru import logger


class AIProviderAdapter:
    """AI厂商适配器基类"""
    
    def __init__(self, api_key: str, api_host: Optional[str] = None):
        self.api_key = api_key
        self.api_host = api_host
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查服务可用性"""
        raise NotImplementedError
    
    async def fetch_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        raise NotImplementedError


class OpenAIAdapter(AIProviderAdapter):
    """OpenAI厂商适配器"""
    
    DEFAULT_API_HOST = "https://api.openai.com"
    
    def __init__(self, api_key: str, api_host: Optional[str] = None):
        super().__init__(api_key, api_host)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查OpenAI服务可用性"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 尝试获取模型列表来验证可用性
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    return {
                        "available": True,
                        "message": "OpenAI服务可用",
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
            logger.error(f"检查OpenAI服务可用性失败: {e}")
            return {
                "available": False,
                "message": f"检查服务可用性失败: {str(e)}",
                "error": str(e)
            }
    
    async def fetch_models(self) -> List[Dict[str, Any]]:
        """获取OpenAI可用模型列表"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    # 过滤并格式化模型信息
                    formatted_models = []
                    for model in models:
                        model_id = model.get("id", "")
                        # 只保留主要的对话模型
                        if any(keyword in model_id for keyword in ["gpt-4", "gpt-3.5"]):
                            formatted_models.append({
                                "id": model_id,
                                "name": model_id,
                                "description": self._get_model_description(model_id),
                                "provider": "openai"
                            })
                    return formatted_models
                else:
                    logger.error(f"获取OpenAI模型列表失败: HTTP {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"获取OpenAI模型列表失败: {e}")
            return []
    
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


class AnthropicAdapter(AIProviderAdapter):
    """Anthropic厂商适配器"""
    
    DEFAULT_API_HOST = "https://api.anthropic.com"
    
    def __init__(self, api_key: str, api_host: Optional[str] = None):
        super().__init__(api_key, api_host)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip('/')
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查Anthropic服务可用性"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 尝试调用模型列表接口
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    # 格式化模型信息
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


class DeepSeekAdapter(AIProviderAdapter):
    """DeepSeek厂商适配器"""
    
    DEFAULT_API_HOST = "https://api.deepseek.com"
    
    def __init__(self, api_key: str, api_host: Optional[str] = None):
        super().__init__(api_key, api_host)
        self.base_url = (api_host or self.DEFAULT_API_HOST).rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def check_availability(self) -> Dict[str, Any]:
        """检查DeepSeek服务可用性"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # DeepSeek的模型列表接口
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    return {
                        "available": True,
                        "message": "DeepSeek服务可用",
                        "models_count": len(models)
                    }
                elif response.status_code == 401:
                    return {
                        "available": False,
                        "message": "API密钥无效或已过期",
                        "error": "Invalid API key"
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
            logger.error(f"检查DeepSeek服务可用性失败: {e}")
            return {
                "available": False,
                "message": f"检查服务可用性失败: {str(e)}",
                "error": str(e)
            }
    
    async def fetch_models(self) -> List[Dict[str, Any]]:
        """获取DeepSeek可用模型列表"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
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
                            "provider": "deepseek"
                        })
                    return formatted_models
                else:
                    logger.error(f"获取DeepSeek模型列表失败: HTTP {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"获取DeepSeek模型列表失败: {e}")
            return []
    
    def _get_model_description(self, model_id: str) -> str:
        """获取模型描述"""
        descriptions = {
            "deepseek-chat": "DeepSeek Chat，通用对话模型",
            "deepseek-coder": "DeepSeek Coder，代码生成模型"
        }
        return descriptions.get(model_id, "DeepSeek模型")


class AIModelService:
    """AI模型配置服务类
    
    提供模型可用性检查、厂商适配等功能
    """
    
    # 支持的厂商适配器映射
    ADAPTERS = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "deepseek": DeepSeekAdapter
    }
    
    @staticmethod
    def get_adapter(provider: str, api_key: str, api_host: Optional[str] = None) -> Optional[AIProviderAdapter]:
        """获取厂商适配器
        
        Args:
            provider: 厂商名称
            api_key: API密钥
            api_host: API主机地址
            
        Returns:
            Optional[AIProviderAdapter]: 适配器实例，不支持返回None
        """
        adapter_class = AIModelService.ADAPTERS.get(provider.lower())
        if adapter_class:
            return adapter_class(api_key, api_host)
        return None
    
    @staticmethod
    async def check_provider_availability(
        provider: str,
        api_key: str,
        api_host: Optional[str] = None
    ) -> Dict[str, Any]:
        """检查厂商服务可用性
        
        Args:
            provider: 厂商名称
            api_key: API密钥
            api_host: API主机地址
            
        Returns:
            Dict: 检查结果，包含available、message、models等字段
        """
        adapter = AIModelService.get_adapter(provider, api_key, api_host)
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
            {"id": "deepseek", "name": "DeepSeek", "description": "DeepSeek系列模型"}
        ]
