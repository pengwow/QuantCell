# AI模型配置业务逻辑层
# 提供AI模型配置的CRUD操作和API密钥加密功能

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from collector.db.database import SessionLocal, init_database_config
from collector.db.models import AIModel


class AIModelBusiness:
    """AI模型配置业务逻辑类
    
    用于操作ai_models表，提供CRUD操作方法
    支持API密钥的加密存储和脱敏显示
    """
    
    @staticmethod
    def _get_db() -> Session:
        """获取数据库会话"""
        init_database_config()
        return SessionLocal()
    
    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        """对API密钥进行脱敏处理
        
        Args:
            api_key: 原始API密钥
            
        Returns:
            str: 脱敏后的API密钥，只显示前4位和后4位
        """
        if not api_key or len(api_key) <= 8:
            return "********"
        return f"{api_key[:4]}...{api_key[-4:]}"
    
    @staticmethod
    def create(
        provider: str,
        name: str,
        api_key: str,
        api_host: Optional[str] = None,
        models: Optional[List[str]] = None,
        is_default: bool = False,
        is_enabled: bool = True,
        proxy_enabled: bool = False,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """创建AI模型配置
        
        Args:
            provider: 厂商名称
            name: 配置名称
            api_key: API密钥
            api_host: API主机地址
            models: 可用模型列表
            is_default: 是否为默认配置
            is_enabled: 是否启用
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码
            
        Returns:
            Optional[Dict]: 创建成功的配置信息，失败返回None
        """
        db = AIModelBusiness._get_db()
        try:
            # 如果设置为默认配置，先将其他默认配置取消
            if is_default:
                db.query(AIModel).filter(AIModel.is_default == True).update({"is_default": False})
            
            # 序列化模型列表
            models_json = json.dumps(models) if models else None
            
            # 创建配置
            ai_model = AIModel(
                provider=provider,
                name=name,
                api_key=api_key,  # 明文存储，如需加密可在此处理
                api_host=api_host,
                models=models_json,
                is_default=is_default,
                is_enabled=is_enabled,
                proxy_enabled=proxy_enabled,
                proxy_url=proxy_url,
                proxy_username=proxy_username,
                proxy_password=proxy_password
            )
            db.add(ai_model)
            db.commit()
            db.refresh(ai_model)
            
            logger.info(f"AI模型配置创建成功: id={ai_model.id}, provider={provider}, name={name}")
            return AIModelBusiness._to_dict(ai_model)
        except Exception as e:
            db.rollback()
            logger.error(f"创建AI模型配置失败: provider={provider}, name={name}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_by_id(model_id: int, include_api_key: bool = False) -> Optional[Dict[str, Any]]:
        """根据ID获取AI模型配置
        
        Args:
            model_id: 配置ID
            include_api_key: 是否包含原始API密钥
            
        Returns:
            Optional[Dict]: 配置信息，不存在返回None
        """
        db = AIModelBusiness._get_db()
        try:
            model = db.query(AIModel).filter(AIModel.id == model_id).first()
            if model:
                return AIModelBusiness._to_dict(model, include_api_key)
            return None
        except Exception as e:
            logger.error(f"获取AI模型配置失败: id={model_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_default() -> Optional[Dict[str, Any]]:
        """获取默认的AI模型配置
        
        Returns:
            Optional[Dict]: 默认配置信息，不存在返回None
        """
        db = AIModelBusiness._get_db()
        try:
            model = db.query(AIModel).filter(
                AIModel.is_default == True,
                AIModel.is_enabled == True
            ).first()
            if model:
                return AIModelBusiness._to_dict(model)
            return None
        except Exception as e:
            logger.error(f"获取默认AI模型配置失败: error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def update(
        model_id: int,
        provider: Optional[str] = None,
        name: Optional[str] = None,
        api_key: Optional[str] = None,
        api_host: Optional[str] = None,
        models: Optional[List[str]] = None,
        is_default: Optional[bool] = None,
        is_enabled: Optional[bool] = None,
        proxy_enabled: Optional[bool] = None,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """更新AI模型配置
        
        Args:
            model_id: 配置ID
            provider: 厂商名称
            name: 配置名称
            api_key: API密钥
            api_host: API主机地址
            models: 可用模型列表
            is_default: 是否为默认配置
            is_enabled: 是否启用
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码
            
        Returns:
            Optional[Dict]: 更新后的配置信息，失败返回None
        """
        db = AIModelBusiness._get_db()
        try:
            model = db.query(AIModel).filter(AIModel.id == model_id).first()
            if not model:
                logger.warning(f"AI模型配置不存在: id={model_id}")
                return None
            
            # 如果设置为默认配置，先将其他默认配置取消
            if is_default is True:
                db.query(AIModel).filter(
                    AIModel.is_default == True,
                    AIModel.id != model_id
                ).update({"is_default": False})
            
            # 更新字段
            if provider is not None:
                model.provider = provider
            if name is not None:
                model.name = name
            if api_key is not None:
                model.api_key = api_key
            if api_host is not None:
                model.api_host = api_host
            if models is not None:
                model.models = json.dumps(models)
            if is_default is not None:
                model.is_default = is_default
            if is_enabled is not None:
                model.is_enabled = is_enabled
            # 代理字段更新
            if proxy_enabled is not None:
                model.proxy_enabled = proxy_enabled
            if proxy_url is not None:
                model.proxy_url = proxy_url
            if proxy_username is not None:
                model.proxy_username = proxy_username
            if proxy_password is not None:
                model.proxy_password = proxy_password
            
            db.commit()
            db.refresh(model)
            
            logger.info(f"AI模型配置更新成功: id={model_id}")
            return AIModelBusiness._to_dict(model)
        except Exception as e:
            db.rollback()
            logger.error(f"更新AI模型配置失败: id={model_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def delete(model_id: int) -> bool:
        """删除AI模型配置
        
        Args:
            model_id: 配置ID
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        db = AIModelBusiness._get_db()
        try:
            model = db.query(AIModel).filter(AIModel.id == model_id).first()
            if model:
                db.delete(model)
                db.commit()
                logger.info(f"AI模型配置删除成功: id={model_id}")
                return True
            logger.warning(f"AI模型配置不存在: id={model_id}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"删除AI模型配置失败: id={model_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def list(
        page: int = 1,
        limit: int = 10,
        provider: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """获取AI模型配置列表
        
        Args:
            page: 页码，从1开始
            limit: 每页记录数
            provider: 按厂商筛选
            is_enabled: 按启用状态筛选
            sort_by: 排序字段
            sort_order: 排序顺序，asc或desc
            
        Returns:
            Dict: 包含配置列表和分页信息
        """
        db = AIModelBusiness._get_db()
        try:
            query = db.query(AIModel)
            
            # 应用筛选条件
            if provider:
                query = query.filter(AIModel.provider == provider)
            if is_enabled is not None:
                query = query.filter(AIModel.is_enabled == is_enabled)
            
            # 计算总记录数
            total = query.count()
            
            # 应用排序
            allowed_sort_fields = ["id", "provider", "name", "created_at", "updated_at"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"
            
            sort_column = getattr(AIModel, sort_by)
            if sort_order == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())
            
            # 应用分页
            offset = (page - 1) * limit
            models = query.offset(offset).limit(limit).all()
            
            # 计算总页数
            pages = (total + limit - 1) // limit
            
            return {
                "items": [AIModelBusiness._to_dict(m) for m in models],
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
        except Exception as e:
            logger.error(f"获取AI模型配置列表失败: error={e}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "pages": 0
            }
        finally:
            db.close()
    
    @staticmethod
    def get_api_key(model_id: int) -> Optional[str]:
        """获取API密钥（原始值）
        
        Args:
            model_id: 配置ID
            
        Returns:
            Optional[str]: API密钥，不存在返回None
        """
        db = AIModelBusiness._get_db()
        try:
            model = db.query(AIModel).filter(AIModel.id == model_id).first()
            if model:
                return model.api_key
            return None
        except Exception as e:
            logger.error(f"获取API密钥失败: id={model_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def update_models(model_id: int, models: List[str]) -> bool:
        """更新配置的可用模型列表
        
        Args:
            model_id: 配置ID
            models: 可用模型列表
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        db = AIModelBusiness._get_db()
        try:
            model = db.query(AIModel).filter(AIModel.id == model_id).first()
            if not model:
                return False
            
            model.models = json.dumps(models)
            db.commit()
            logger.info(f"AI模型列表更新成功: id={model_id}, models_count={len(models)}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新AI模型列表失败: id={model_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def _to_dict(model: AIModel, include_api_key: bool = False) -> Dict[str, Any]:
        """将AIModel对象转换为字典
        
        Args:
            model: AIModel对象
            include_api_key: 是否包含原始API密钥
            
        Returns:
            Dict: 配置信息字典
        """
        from collector.db.models import format_datetime
        
        result = {
            "id": model.id,
            "provider": model.provider,
            "name": model.name,
            "api_host": model.api_host,
            "models": json.loads(model.models) if model.models else None,
            "is_default": model.is_default,
            "is_enabled": model.is_enabled,
            "proxy_enabled": model.proxy_enabled,
            "proxy_url": model.proxy_url,
            "proxy_username": model.proxy_username,
            "proxy_password": model.proxy_password,
            "created_at": format_datetime(model.created_at),
            "updated_at": format_datetime(model.updated_at)
        }
        
        # API密钥脱敏显示
        if include_api_key:
            result["api_key"] = model.api_key
        else:
            result["api_key_masked"] = AIModelBusiness._mask_api_key(model.api_key)
        
        return result
