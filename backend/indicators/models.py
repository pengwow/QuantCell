"""自定义技术指标SQLAlchemy模型

对应indicators表的ORM定义，用于存储用户创建的Python自定义指标
"""

from typing import Any, Dict, List, Optional
import json
import pytz

import sqlalchemy
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, Numeric, func
from sqlalchemy.orm import Session

from utils.logger import get_logger, LogType
from collector.db.database import Base, init_database_config, SessionLocal
from collector.db.models import TimezoneAwareBase

logger = get_logger(__name__, LogType.APPLICATION)


class CustomIndicator(TimezoneAwareBase):
    """自定义技术指标SQLAlchemy模型
    
    对应indicators表，存储用户编写的Python指标代码及其元数据
    """
    __tablename__ = "indicators"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    code = Column(Text, nullable=False)
    is_encrypted = Column(Boolean, default=False)
    publish_to_community = Column(Boolean, default=False)
    pricing_type = Column(String(20), default="free")
    price = Column(Numeric(10, 2), default=0)
    preview_image = Column(String(500), default="")
    review_status = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class CustomIndicatorBusiness:
    """自定义指标业务类
    
    提供CRUD操作方法，遵循项目现有模式（参考DataPoolBusiness/TaskBusiness）
    """
    
    @staticmethod
    def _format_dt(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.utc)
        return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def _to_dict(indicator: CustomIndicator) -> Dict[str, Any]:
        return {
            "id": indicator.id,
            "user_id": indicator.user_id,
            "name": indicator.name,
            "description": indicator.description,
            "code": indicator.code,
            "is_encrypted": indicator.is_encrypted,
            "publish_to_community": indicator.publish_to_community,
            "pricing_type": indicator.pricing_type,
            "price": float(indicator.price) if indicator.price else 0,
            "preview_image": indicator.preview_image,
            "review_status": indicator.review_status,
            "created_at": CustomIndicatorBusiness._format_dt(indicator.created_at),
            "updated_at": CustomIndicatorBusiness._format_dt(indicator.updated_at),
        }
    
    @staticmethod
    def create(user_id: int, name: str, code: str, description: str = "", **kwargs) -> Optional[Dict[str, Any]]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            indicator = CustomIndicator(
                user_id=user_id,
                name=name,
                code=code,
                description=description or "",
                is_encrypted=kwargs.get("is_encrypted", False),
                publish_to_community=kwargs.get("publish_to_community", False),
                pricing_type=kwargs.get("pricing_type", "free"),
                price=kwargs.get("price", 0),
                preview_image=kwargs.get("preview_image", ""),
                review_status=kwargs.get("review_status"),
            )
            db.add(indicator)
            db.commit()
            db.refresh(indicator)
            logger.info(f"指标已创建: id={indicator.id}, name={name}")
            return CustomIndicatorBusiness._to_dict(indicator)
        except Exception as e:
            db.rollback()
            logger.error(f"创建指标失败: name={name}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_by_id(indicator_id: int) -> Optional[Dict[str, Any]]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            indicator = db.query(CustomIndicator).filter_by(id=indicator_id).first()
            return CustomIndicatorBusiness._to_dict(indicator) if indicator else None
        except Exception as e:
            logger.error(f"获取指标失败: id={indicator_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_all(user_id: int = None) -> list:
        init_database_config()
        db: Session = SessionLocal()
        try:
            query = db.query(CustomIndicator)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            indicators = query.order_by(CustomIndicator.updated_at.desc()).all()
            return [CustomIndicatorBusiness._to_dict(i) for i in indicators]
        except Exception as e:
            logger.error(f"获取指标列表失败: error={e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def update(indicator_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            indicator = db.query(CustomIndicator).filter_by(id=indicator_id).first()
            if not indicator:
                logger.error(f"指标不存在: id={indicator_id}")
                return None
            for key, value in kwargs.items():
                if hasattr(indicator, key) and value is not None:
                    setattr(indicator, key, value)
            db.commit()
            db.refresh(indicator)
            logger.info(f"指标已更新: id={indicator_id}")
            return CustomIndicatorBusiness._to_dict(indicator)
        except Exception as e:
            db.rollback()
            logger.error(f"更新指标失败: id={indicator_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def delete(indicator_id: int) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            indicator = db.query(CustomIndicator).filter_by(id=indicator_id).first()
            if indicator:
                db.delete(indicator)
                db.commit()
                logger.info(f"指标已删除: id={indicator_id}, name={indicator.name}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除指标失败: id={indicator_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_code(indicator_id: int) -> Optional[str]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            indicator = db.query(CustomIndicator.code).filter_by(id=indicator_id).first()
            return indicator.code if indicator else None
        except Exception as e:
            logger.error(f"获取指标代码失败: id={indicator_id}, error={e}")
            return None
        finally:
            db.close()
