"""指标版本快照业务（P2-08）

每次创建/保存/回滚指标时在 indicator_versions 表写入一个代码快照，
version_no 单调递增；indicators.version 列记录当前版本号。
回滚不删除历史：把旧快照内容写回 indicators 后再生成一个 source="rollback"
的新快照，保证任何时刻都能继续向前回溯。
"""

from typing import TYPE_CHECKING, Any

import pytz
from sqlalchemy import func

# 模块属性访问而非 from-import：测试通过 monkeypatch db_module.SessionLocal 注入内存库
from collector.db import database as db_module
from collector.db.database import init_database_config
from indicators.models import CustomIndicator, CustomIndicatorBusiness, IndicatorVersion
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__, LogType.APPLICATION)


class IndicatorVersionBusiness:
    """指标版本快照读写（与 CustomIndicatorBusiness 同风格：静态方法 + 每次开 session）"""

    @staticmethod
    def _format_dt(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.utc)
        return dt.astimezone(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _to_dict(version: IndicatorVersion, current_version: int | None = None) -> dict[str, Any]:
        return {
            "id": version.id,
            "indicator_id": version.indicator_id,
            "version_no": version.version_no,
            "name": version.name,
            "description": version.description,
            "source": version.source,
            "is_current": version.version_no == current_version,
            "created_at": IndicatorVersionBusiness._format_dt(version.created_at),
        }

    @staticmethod
    def record_version(indicator_id: int, source: str = "save") -> int | None:
        """为指标的当前内容生成一个新快照，返回新版本号。

        单一规则：首个快照版本号 = indicators.version（建指标时为 1），
        之后每快照一次 max(当前版本, 已有最大快照号) + 1。
        """
        init_database_config()
        db: Session = db_module.SessionLocal()
        try:
            indicator = db.query(CustomIndicator).filter_by(id=indicator_id).first()
            if not indicator:
                logger.error(f"记录指标版本失败，指标不存在: id={indicator_id}")
                return None
            last_no = db.query(func.max(IndicatorVersion.version_no)).filter_by(indicator_id=indicator_id).scalar()
            next_no = (indicator.version or 1) if not last_no else max(indicator.version or 1, last_no) + 1
            db.add(
                IndicatorVersion(
                    indicator_id=indicator_id,
                    version_no=next_no,
                    name=indicator.name or "",
                    description=indicator.description or "",
                    code=indicator.code or "",
                    source=source,
                )
            )
            indicator.version = next_no
            db.commit()
            logger.info(f"指标版本已记录: id={indicator_id}, v{next_no}, source={source}")
            return next_no
        except Exception as e:
            db.rollback()
            logger.error(f"记录指标版本失败: id={indicator_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def list_versions(indicator_id: int) -> list[dict[str, Any]]:
        """版本列表（新版本在前），is_current 标记 indicators.version 指向的版本。"""
        init_database_config()
        db: Session = db_module.SessionLocal()
        try:
            current = db.query(CustomIndicator.version).filter_by(id=indicator_id).scalar()
            rows = (
                db.query(IndicatorVersion)
                .filter_by(indicator_id=indicator_id)
                .order_by(IndicatorVersion.version_no.desc())
                .all()
            )
            return [IndicatorVersionBusiness._to_dict(r, current) for r in rows]
        except Exception as e:
            logger.error(f"获取指标版本列表失败: id={indicator_id}, error={e}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_version(indicator_id: int, version_no: int) -> dict[str, Any] | None:
        """取单个快照（含 code，供 diff/查看）。"""
        init_database_config()
        db: Session = db_module.SessionLocal()
        try:
            row = db.query(IndicatorVersion).filter_by(indicator_id=indicator_id, version_no=version_no).first()
            if not row:
                return None
            result = IndicatorVersionBusiness._to_dict(row)
            result["code"] = row.code
            return result
        except Exception as e:
            logger.error(f"获取指标版本失败: id={indicator_id}, v={version_no}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def diff_versions(indicator_id: int, version_a: int, version_b: int) -> dict[str, Any] | None:
        """取两个版本的代码内容，diff 渲染交给前端 Monaco DiffEditor。"""
        a = IndicatorVersionBusiness.get_version(indicator_id, version_a)
        b = IndicatorVersionBusiness.get_version(indicator_id, version_b)
        if a is None or b is None:
            return None
        return {"a": a, "b": b}

    @staticmethod
    def rollback(indicator_id: int, version_no: int) -> dict[str, Any] | None:
        """回滚到指定版本：旧快照内容写回 indicators，再生成 source="rollback" 的新快照。

        同一个事务内完成"写回 + 新快照"，返回回滚后的指标 dict（含新版本号）。
        """
        init_database_config()
        db: Session = db_module.SessionLocal()
        try:
            snapshot = db.query(IndicatorVersion).filter_by(indicator_id=indicator_id, version_no=version_no).first()
            indicator = db.query(CustomIndicator).filter_by(id=indicator_id).first()
            if not snapshot or not indicator:
                logger.error(f"回滚指标失败: id={indicator_id}, v={version_no} 不存在")
                return None

            indicator.name = snapshot.name
            indicator.description = snapshot.description or ""
            indicator.code = snapshot.code
            indicator.version = snapshot.version_no
            db.flush()

            # 新快照版本号 = 当前最大 + 1，避免 rollback 记录与已有版本号冲突
            last_no = (
                db.query(func.max(IndicatorVersion.version_no)).filter_by(indicator_id=indicator_id).scalar()
                or snapshot.version_no
            )
            new_no = last_no + 1
            db.add(
                IndicatorVersion(
                    indicator_id=indicator_id,
                    version_no=new_no,
                    name=indicator.name,
                    description=indicator.description,
                    code=indicator.code,
                    source="rollback",
                )
            )
            indicator.version = new_no
            db.commit()
            result = CustomIndicatorBusiness._to_dict(indicator)
            logger.info(f"指标已回滚: id={indicator_id}, v{version_no} -> v{new_no}")
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"回滚指标失败: id={indicator_id}, v={version_no}, error={e}")
            return None
        finally:
            db.close()
