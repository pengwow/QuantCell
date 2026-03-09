"""策略历史记录管理器

提供策略历史记录的 CRUD 操作和重新生成功能
"""
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from sqlalchemy import and_, desc, func, create_engine
from sqlalchemy.orm import Session, sessionmaker

try:
    from ai_model.strategy_history_models import StrategyHistory, Base
except ImportError:
    # 用于直接运行测试时
    from strategy_history_models import StrategyHistory, Base


# 数据库配置
_engine = None
_SessionLocal = None


def _get_engine():
    """获取数据库引擎（延迟初始化）"""
    global _engine
    if _engine is None:
        import os
        db_type = os.environ.get("DB_TYPE", "sqlite")
        default_db_path = os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(default_db_path, exist_ok=True)
        
        if db_type == "sqlite":
            db_file = os.environ.get("DB_FILE", os.path.join(default_db_path, "quantcell.db"))
            _engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
        else:
            db_file = os.environ.get("DB_FILE", os.path.join(default_db_path, "quantcell.db"))
            _engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
        
        # 绑定 Base metadata
        Base.metadata.bind = _engine
    
    return _engine


def _get_session_local():
    """获取会话工厂（延迟初始化）"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = _get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


class StrategyHistoryManager:
    """策略历史记录管理器

    用于操作 strategy_history 表，提供 CRUD 操作方法
    支持策略历史记录的创建、查询、删除和重新生成
    """

    @staticmethod
    def _get_db() -> Session:
        """获取数据库会话"""
        SessionLocal = _get_session_local()
        return SessionLocal()

    @staticmethod
    def create(
        user_id: str,
        title: str,
        requirement: str,
        code: str,
        explanation: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: Optional[float] = None,
        tokens_used: Optional[Dict[str, Any]] = None,
        generation_time: Optional[float] = None,
        is_valid: bool = True,
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """创建策略历史记录

        Args:
            user_id: 用户 ID
            title: 策略标题
            requirement: 用户需求描述
            code: 生成的策略代码
            explanation: 策略解释说明
            model_id: 使用的 AI 模型 ID
            temperature: 温度参数
            tokens_used: Token 使用量字典
            generation_time: 生成耗时（秒）
            is_valid: 代码是否有效
            tags: 标签列表

        Returns:
            Optional[Dict]: 创建成功的记录信息，失败返回 None
        """
        db = StrategyHistoryManager._get_db()
        try:
            history = StrategyHistory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                requirement=requirement,
                code=code,
                explanation=explanation,
                model_id=model_id,
                temperature=temperature,
                tokens_used=json.dumps(tokens_used) if tokens_used else None,
                generation_time=generation_time,
                is_valid=is_valid,
                tags=json.dumps(tags) if tags else None,
            )
            db.add(history)
            db.commit()
            db.refresh(history)

            logger.info(f"策略历史记录创建成功: id={history.id}, user_id={user_id}, title={title}")
            return history.to_dict()
        except Exception as e:
            db.rollback()
            logger.error(f"创建策略历史记录失败: user_id={user_id}, title={title}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_by_id(history_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取策略历史记录

        Args:
            history_id: 记录 ID

        Returns:
            Optional[Dict]: 记录信息，不存在返回 None
        """
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if history:
                return history.to_dict()
            return None
        except Exception as e:
            logger.error(f"获取策略历史记录失败: id={history_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def list_by_user(
        user_id: str,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """分页查询用户的策略历史记录

        Args:
            user_id: 用户 ID
            page: 页码，从 1 开始
            page_size: 每页记录数
            filters: 过滤条件，支持 title、is_valid、tags、start_time、end_time
            sort_by: 排序字段
            sort_order: 排序顺序，asc 或 desc

        Returns:
            Dict: 包含记录列表和分页信息
        """
        db = StrategyHistoryManager._get_db()
        try:
            query = db.query(StrategyHistory).filter(StrategyHistory.user_id == user_id)

            # 应用过滤条件
            if filters:
                # 标题模糊搜索
                if filters.get("title"):
                    query = query.filter(StrategyHistory.title.contains(filters["title"]))

                # 是否有效
                if filters.get("is_valid") is not None:
                    query = query.filter(StrategyHistory.is_valid == filters["is_valid"])

                # 标签过滤（需要解析 JSON）
                if filters.get("tags"):
                    tags = filters["tags"]
                    if isinstance(tags, list):
                        # 对于 SQLite/DuckDB，使用简单的字符串包含检查
                        tag_conditions = []
                        for tag in tags:
                            tag_conditions.append(StrategyHistory.tags.contains(tag))
                        if tag_conditions:
                            query = query.filter(and_(*tag_conditions))

                # 时间范围过滤
                if filters.get("start_time"):
                    query = query.filter(StrategyHistory.created_at >= filters["start_time"])
                if filters.get("end_time"):
                    query = query.filter(StrategyHistory.created_at <= filters["end_time"])

                # 模型 ID 过滤
                if filters.get("model_id"):
                    query = query.filter(StrategyHistory.model_id == filters["model_id"])

            # 计算总记录数
            total = query.count()

            # 验证排序字段
            allowed_sort_fields = ["created_at", "updated_at", "title", "generation_time"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"

            # 应用排序
            sort_column = getattr(StrategyHistory, sort_by)
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)

            # 应用分页
            offset = (page - 1) * page_size
            histories = query.offset(offset).limit(page_size).all()

            # 计算总页数
            pages = (total + page_size - 1) // page_size if page_size > 0 else 0

            return {
                "items": [h.to_dict() for h in histories],
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
            }
        except Exception as e:
            logger.error(f"查询策略历史记录失败: user_id={user_id}, error={e}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "pages": 0,
            }
        finally:
            db.close()

    @staticmethod
    def delete(history_id: str) -> bool:
        """删除策略历史记录

        Args:
            history_id: 记录 ID

        Returns:
            bool: 删除成功返回 True，失败返回 False
        """
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if history:
                db.delete(history)
                db.commit()
                logger.info(f"策略历史记录删除成功: id={history_id}")
                return True
            logger.warning(f"策略历史记录不存在: id={history_id}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"删除策略历史记录失败: id={history_id}, error={e}")
            return False
        finally:
            db.close()

    @staticmethod
    def delete_by_user(user_id: str, history_ids: List[str]) -> Dict[str, Any]:
        """批量删除用户的策略历史记录

        Args:
            user_id: 用户 ID
            history_ids: 记录 ID 列表

        Returns:
            Dict: 删除结果统计
        """
        db = StrategyHistoryManager._get_db()
        try:
            deleted_count = 0
            failed_count = 0

            for history_id in history_ids:
                history = db.query(StrategyHistory).filter(
                    and_(
                        StrategyHistory.id == history_id,
                        StrategyHistory.user_id == user_id
                    )
                ).first()
                if history:
                    db.delete(history)
                    deleted_count += 1
                else:
                    failed_count += 1

            db.commit()
            logger.info(f"批量删除策略历史记录: user_id={user_id}, deleted={deleted_count}, failed={failed_count}")
            return {
                "deleted": deleted_count,
                "failed": failed_count,
                "total": len(history_ids),
            }
        except Exception as e:
            db.rollback()
            logger.error(f"批量删除策略历史记录失败: user_id={user_id}, error={e}")
            return {
                "deleted": 0,
                "failed": len(history_ids),
                "total": len(history_ids),
            }
        finally:
            db.close()

    @staticmethod
    def regenerate(
        history_id: str,
        new_requirement: Optional[str] = None,
        new_title: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """基于历史记录重新生成策略

        基于已有历史记录创建一条新的记录，可以修改需求描述

        Args:
            history_id: 原历史记录 ID
            new_requirement: 新的需求描述，如果不提供则使用原需求
            new_title: 新的标题，如果不提供则基于原标题生成
            **kwargs: 其他可选参数，如 model_id、temperature 等

        Returns:
            Optional[Dict]: 新创建的记录信息，失败返回 None
        """
        db = StrategyHistoryManager._get_db()
        try:
            # 获取原历史记录
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if not history:
                logger.warning(f"原策略历史记录不存在: id={history_id}")
                return None

            # 构建新记录的数据
            title = new_title or f"{history.title} (重新生成)"
            requirement = new_requirement or history.requirement

            # 创建新记录
            new_history = StrategyHistory(
                id=str(uuid.uuid4()),
                user_id=history.user_id,
                title=title,
                requirement=requirement,
                code=history.code,  # 暂时复制原代码，实际应该调用生成服务
                explanation=history.explanation,
                model_id=kwargs.get("model_id", history.model_id),
                temperature=kwargs.get("temperature", history.temperature),
                tokens_used=None,  # 重新生成后更新
                generation_time=None,  # 重新生成后更新
                is_valid=True,  # 重新生成后验证
                tags=history.tags,
            )

            db.add(new_history)
            db.commit()
            db.refresh(new_history)

            logger.info(f"策略历史记录重新生成成功: original_id={history_id}, new_id={new_history.id}")
            return new_history.to_dict()
        except Exception as e:
            db.rollback()
            logger.error(f"重新生成策略历史记录失败: id={history_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def update(
        history_id: str,
        title: Optional[str] = None,
        code: Optional[str] = None,
        explanation: Optional[str] = None,
        is_valid: Optional[bool] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新策略历史记录

        Args:
            history_id: 记录 ID
            title: 策略标题
            code: 策略代码
            explanation: 策略解释
            is_valid: 是否有效
            tags: 标签列表

        Returns:
            Optional[Dict]: 更新后的记录信息，失败返回 None
        """
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if not history:
                logger.warning(f"策略历史记录不存在: id={history_id}")
                return None

            # 更新字段
            if title is not None:
                history.title = title
            if code is not None:
                history.code = code
            if explanation is not None:
                history.explanation = explanation
            if is_valid is not None:
                history.is_valid = is_valid
            if tags is not None:
                history.tags = json.dumps(tags)

            db.commit()
            db.refresh(history)

            logger.info(f"策略历史记录更新成功: id={history_id}")
            return history.to_dict()
        except Exception as e:
            db.rollback()
            logger.error(f"更新策略历史记录失败: id={history_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_user_stats(user_id: str) -> Dict[str, Any]:
        """获取用户的策略历史统计信息

        Args:
            user_id: 用户 ID

        Returns:
            Dict: 统计信息
        """
        db = StrategyHistoryManager._get_db()
        try:
            # 总记录数
            total_count = db.query(func.count(StrategyHistory.id)).filter(
                StrategyHistory.user_id == user_id
            ).scalar() or 0

            # 有效记录数
            valid_count = db.query(func.count(StrategyHistory.id)).filter(
                and_(
                    StrategyHistory.user_id == user_id,
                    StrategyHistory.is_valid == True
                )
            ).scalar() or 0

            # 平均生成时间
            avg_generation_time = db.query(func.avg(StrategyHistory.generation_time)).filter(
                StrategyHistory.user_id == user_id
            ).scalar() or 0

            # 最近生成时间
            latest = db.query(StrategyHistory).filter(
                StrategyHistory.user_id == user_id
            ).order_by(desc(StrategyHistory.created_at)).first()

            return {
                "total_count": total_count,
                "valid_count": valid_count,
                "invalid_count": total_count - valid_count,
                "avg_generation_time": round(avg_generation_time, 2) if avg_generation_time else 0,
                "latest_created_at": latest.to_dict()["created_at"] if latest else None,
            }
        except Exception as e:
            logger.error(f"获取用户策略历史统计失败: user_id={user_id}, error={e}")
            return {
                "total_count": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "avg_generation_time": 0,
                "latest_created_at": None,
            }
        finally:
            db.close()
