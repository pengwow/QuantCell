"""自定义技术指标SQLAlchemy模型

对应indicators表的ORM定义，用于存储用户创建的Python自定义指标
"""

from typing import TYPE_CHECKING, Any

import pytz
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, func

# 模块属性访问而非 from-import：测试可通过 monkeypatch db_module.SessionLocal 注入内存库
from collector.db import database as db_module
from collector.db.database import init_database_config
from collector.db.models import TimezoneAwareBase
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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
    # 当前版本号（P2-08），快照明细见 indicator_versions 表
    version = Column(Integer, nullable=False, default=1)
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
        return dt.astimezone(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _to_dict(indicator: CustomIndicator) -> dict[str, Any]:
        return {
            "id": indicator.id,
            "user_id": indicator.user_id,
            "name": indicator.name,
            "description": indicator.description,
            "code": indicator.code,
            "version": indicator.version or 1,
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
    def create(user_id: int, name: str, code: str, description: str = "", **kwargs) -> dict[str, Any] | None:
        init_database_config()
        db: Session = db_module.SessionLocal()
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
    def get_by_id(indicator_id: int) -> dict[str, Any] | None:
        init_database_config()
        db: Session = db_module.SessionLocal()
        try:
            indicator = db.query(CustomIndicator).filter_by(id=indicator_id).first()
            return CustomIndicatorBusiness._to_dict(indicator) if indicator else None
        except Exception as e:
            logger.error(f"获取指标失败: id={indicator_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_all(user_id: int | None = None) -> list:
        init_database_config()
        db: Session = db_module.SessionLocal()
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
    def update(indicator_id: int, **kwargs) -> dict[str, Any] | None:
        init_database_config()
        db: Session = db_module.SessionLocal()
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
        db: Session = db_module.SessionLocal()
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
    def get_code(indicator_id: int) -> str | None:
        init_database_config()
        db: Session = db_module.SessionLocal()
        try:
            indicator = db.query(CustomIndicator.code).filter_by(id=indicator_id).first()
            return indicator.code if indicator else None
        except Exception as e:
            logger.error(f"获取指标代码失败: id={indicator_id}, error={e}")
            return None
        finally:
            db.close()


class IndicatorVersion(TimezoneAwareBase):
    """指标版本快照（P2-08）

    指标每次创建/保存/回滚时的代码快照，(indicator_id, version_no) 唯一，
    version_no 单调递增；indicators.version 指向当前版本。
    """

    __tablename__ = "indicator_versions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    indicator_id = Column(Integer, nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False, default="")
    description = Column(Text, default="")
    code = Column(Text, nullable=False)
    source = Column(String(20), nullable=False, default="save")  # create/save/rollback
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class IndicatorAlertRule(TimezoneAwareBase):
    """指标信号提醒规则（P2-07）

    对指定标的/周期拉取K线沙箱重算指标，将某个 plot 线的最新值与阈值比较，
    命中后经统一通知服务投递（websocket/email/feishu/wecom），按 frequency(分钟)
    去重，避免同一条件反复打扰。
    """

    __tablename__ = "indicator_alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    indicator_id = Column(Integer, nullable=False, index=True)  # 自定义指标 ID；builtin_id 非空时为 0
    # 系统内置指标标识（builtin_alerts.py 的 key，如 "sma"），与 indicator_id 二选一
    builtin_id = Column(String(50), nullable=True, index=True)
    name = Column(String(100), nullable=False, default="")
    symbol = Column(String(50), nullable=False)
    period = Column(String(20), nullable=False, default="1h")
    market_type = Column(String(20), nullable=False, default="crypto")
    crypto_type = Column(String(20), nullable=False, default="spot")
    params = Column(Text, nullable=False, default="{}")  # 指标参数，JSON 对象
    plot_name = Column(String(100), nullable=False, default="")  # 空=第一个 plot 线
    op = Column(String(20), nullable=False, default="gt")  # gt/lt/cross_up/cross_down
    threshold = Column(Numeric(24, 10), nullable=False, default=0)
    channels = Column(Text, nullable=False, default='["websocket"]')  # 通知渠道，JSON 数组
    frequency = Column(Integer, nullable=False, default=30)  # 触发去重窗口（分钟）
    enabled = Column(Boolean, nullable=False, default=True)
    last_fired_at = Column(DateTime(timezone=True))  # 上次触发时间，去重依据
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
