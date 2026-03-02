# 交易所配置业务逻辑层
# 提供交易所配置的CRUD操作和API密钥加密功能

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from collector.db.database import SessionLocal, init_database_config
from collector.db.models import ExchangeConfig


class ExchangeConfigBusiness:
    """交易所配置业务逻辑类
    
    用于操作exchange_configs表，提供CRUD操作方法
    支持API密钥的加密存储和脱敏显示
    """
    
    @staticmethod
    def _get_db() -> Session:
        """获取数据库会话"""
        init_database_config()
        return SessionLocal()
    
    @staticmethod
    def _mask_api_key(api_key: Optional[str]) -> Optional[str]:
        """对API密钥进行脱敏处理
        
        Args:
            api_key: 原始API密钥
            
        Returns:
            str: 脱敏后的API密钥，只显示前4位和后4位
        """
        if not api_key or len(api_key) <= 8:
            return "********" if api_key else None
        return f"{api_key[:4]}...{api_key[-4:]}"
    
    @staticmethod
    def create(
        exchange_id: str,
        name: str,
        trading_mode: str = "spot",
        quote_currency: str = "USDT",
        commission_rate: float = 0.001,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        proxy_enabled: bool = False,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
        is_default: bool = False,
        is_enabled: bool = True
    ) -> Optional[Dict[str, Any]]:
        """创建交易所配置
        
        Args:
            exchange_id: 交易所ID
            name: 交易所名称
            trading_mode: 交易模式
            quote_currency: 计价货币
            commission_rate: 手续费率
            api_key: API密钥
            api_secret: API密钥密钥
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码
            is_default: 是否为默认配置
            is_enabled: 是否启用
            
        Returns:
            Optional[Dict]: 创建成功的配置信息，失败返回None
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            # 如果设置为默认配置，先将其他默认配置取消
            if is_default:
                db.query(ExchangeConfig).filter(ExchangeConfig.is_default == True).update({"is_default": False})
            
            # 创建配置
            config = ExchangeConfig(
                exchange_id=exchange_id,
                name=name,
                trading_mode=trading_mode,
                quote_currency=quote_currency,
                commission_rate=commission_rate,
                api_key=api_key,
                api_secret=api_secret,
                proxy_enabled=proxy_enabled,
                proxy_url=proxy_url,
                proxy_username=proxy_username,
                proxy_password=proxy_password,
                is_default=is_default,
                is_enabled=is_enabled
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            
            logger.info(f"交易所配置创建成功: id={config.id}, exchange_id={exchange_id}, name={name}")
            return ExchangeConfigBusiness._to_dict(config)
        except Exception as e:
            db.rollback()
            logger.error(f"创建交易所配置失败: exchange_id={exchange_id}, name={name}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_by_id(config_id: int, include_api_key: bool = False) -> Optional[Dict[str, Any]]:
        """根据ID获取交易所配置
        
        Args:
            config_id: 配置ID
            include_api_key: 是否包含原始API密钥
            
        Returns:
            Optional[Dict]: 配置信息，不存在返回None
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            config = db.query(ExchangeConfig).filter(ExchangeConfig.id == config_id).first()
            if config:
                return ExchangeConfigBusiness._to_dict(config, include_api_key)
            return None
        except Exception as e:
            logger.error(f"获取交易所配置失败: id={config_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_by_exchange_id(exchange_id: str, include_api_key: bool = False) -> Optional[Dict[str, Any]]:
        """根据交易所ID获取配置
        
        Args:
            exchange_id: 交易所ID
            include_api_key: 是否包含原始API密钥
            
        Returns:
            Optional[Dict]: 配置信息，不存在返回None
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            config = db.query(ExchangeConfig).filter(ExchangeConfig.exchange_id == exchange_id).first()
            if config:
                return ExchangeConfigBusiness._to_dict(config, include_api_key)
            return None
        except Exception as e:
            logger.error(f"获取交易所配置失败: exchange_id={exchange_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_default() -> Optional[Dict[str, Any]]:
        """获取默认的交易所配置
        
        Returns:
            Optional[Dict]: 默认配置信息，不存在返回None
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            config = db.query(ExchangeConfig).filter(
                ExchangeConfig.is_default == True,
                ExchangeConfig.is_enabled == True
            ).first()
            if config:
                return ExchangeConfigBusiness._to_dict(config)
            return None
        except Exception as e:
            logger.error(f"获取默认交易所配置失败: error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def update(
        config_id: int,
        exchange_id: Optional[str] = None,
        name: Optional[str] = None,
        trading_mode: Optional[str] = None,
        quote_currency: Optional[str] = None,
        commission_rate: Optional[float] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        proxy_enabled: Optional[bool] = None,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
        is_default: Optional[bool] = None,
        is_enabled: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """更新交易所配置
        
        Args:
            config_id: 配置ID
            exchange_id: 交易所ID
            name: 交易所名称
            trading_mode: 交易模式
            quote_currency: 计价货币
            commission_rate: 手续费率
            api_key: API密钥
            api_secret: API密钥密钥
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码
            is_default: 是否为默认配置
            is_enabled: 是否启用
            
        Returns:
            Optional[Dict]: 更新后的配置信息，失败返回None
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            config = db.query(ExchangeConfig).filter(ExchangeConfig.id == config_id).first()
            if not config:
                logger.warning(f"交易所配置不存在: id={config_id}")
                return None
            
            # 如果设置为默认配置，先将其他默认配置取消
            if is_default is True:
                db.query(ExchangeConfig).filter(
                    ExchangeConfig.is_default == True,
                    ExchangeConfig.id != config_id
                ).update({"is_default": False})
            
            # 更新字段
            if exchange_id is not None:
                config.exchange_id = exchange_id
            if name is not None:
                config.name = name
            if trading_mode is not None:
                config.trading_mode = trading_mode
            if quote_currency is not None:
                config.quote_currency = quote_currency
            if commission_rate is not None:
                config.commission_rate = commission_rate
            if api_key is not None:
                config.api_key = api_key
            if api_secret is not None:
                config.api_secret = api_secret
            if proxy_enabled is not None:
                config.proxy_enabled = proxy_enabled
            if proxy_url is not None:
                config.proxy_url = proxy_url
            if proxy_username is not None:
                config.proxy_username = proxy_username
            if proxy_password is not None:
                config.proxy_password = proxy_password
            if is_default is not None:
                config.is_default = is_default
            if is_enabled is not None:
                config.is_enabled = is_enabled
            
            db.commit()
            db.refresh(config)
            
            logger.info(f"交易所配置更新成功: id={config_id}")
            return ExchangeConfigBusiness._to_dict(config)
        except Exception as e:
            db.rollback()
            logger.error(f"更新交易所配置失败: id={config_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def delete(config_id: int) -> bool:
        """删除交易所配置
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            config = db.query(ExchangeConfig).filter(ExchangeConfig.id == config_id).first()
            if config:
                db.delete(config)
                db.commit()
                logger.info(f"交易所配置删除成功: id={config_id}")
                return True
            logger.warning(f"交易所配置不存在: id={config_id}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"删除交易所配置失败: id={config_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def list(
        page: int = 1,
        limit: int = 10,
        exchange_id: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """获取交易所配置列表
        
        Args:
            page: 页码，从1开始
            limit: 每页记录数
            exchange_id: 按交易所ID筛选
            is_enabled: 按启用状态筛选
            sort_by: 排序字段
            sort_order: 排序顺序，asc或desc
            
        Returns:
            Dict: 包含配置列表和分页信息
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            query = db.query(ExchangeConfig)
            
            # 应用筛选条件
            if exchange_id:
                query = query.filter(ExchangeConfig.exchange_id == exchange_id)
            if is_enabled is not None:
                query = query.filter(ExchangeConfig.is_enabled == is_enabled)
            
            # 计算总记录数
            total = query.count()
            
            # 应用排序
            allowed_sort_fields = ["id", "exchange_id", "name", "created_at", "updated_at"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"
            
            sort_column = getattr(ExchangeConfig, sort_by)
            if sort_order == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())
            
            # 应用分页
            offset = (page - 1) * limit
            configs = query.offset(offset).limit(limit).all()
            
            # 计算总页数
            pages = (total + limit - 1) // limit
            
            return {
                "items": [ExchangeConfigBusiness._to_dict(c) for c in configs],
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
        except Exception as e:
            logger.error(f"获取交易所配置列表失败: error={e}")
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
    def get_api_credentials(config_id: int) -> Optional[Dict[str, str]]:
        """获取API认证信息（原始值）
        
        Args:
            config_id: 配置ID
            
        Returns:
            Optional[Dict]: 包含api_key和api_secret的字典，不存在返回None
        """
        db = ExchangeConfigBusiness._get_db()
        try:
            config = db.query(ExchangeConfig).filter(ExchangeConfig.id == config_id).first()
            if config:
                return {
                    "api_key": config.api_key,
                    "api_secret": config.api_secret
                }
            return None
        except Exception as e:
            logger.error(f"获取API认证信息失败: id={config_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def _to_dict(config: ExchangeConfig, include_api_key: bool = False) -> Dict[str, Any]:
        """将ExchangeConfig对象转换为字典
        
        Args:
            config: ExchangeConfig对象
            include_api_key: 是否包含原始API密钥
            
        Returns:
            Dict: 配置信息字典
        """
        from collector.db.models import format_datetime
        
        result = {
            "id": config.id,
            "exchange_id": config.exchange_id,
            "name": config.name,
            "trading_mode": config.trading_mode,
            "quote_currency": config.quote_currency,
            "commission_rate": config.commission_rate,
            "proxy_enabled": config.proxy_enabled,
            "proxy_url": config.proxy_url,
            "proxy_username": config.proxy_username,
            "proxy_password": config.proxy_password,
            "is_default": config.is_default,
            "is_enabled": config.is_enabled,
            "created_at": format_datetime(config.created_at),
            "updated_at": format_datetime(config.updated_at)
        }
        
        # API密钥脱敏显示
        if include_api_key:
            result["api_key"] = config.api_key
            result["api_secret"] = config.api_secret
        else:
            result["api_key_masked"] = ExchangeConfigBusiness._mask_api_key(config.api_key)
            result["api_secret_masked"] = ExchangeConfigBusiness._mask_api_key(config.api_secret)
        
        return result
