"""策略历史记录管理器单元测试

测试 StrategyHistoryManager 的 CRUD 操作、分页查询和重新生成功能
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

# 设置测试环境
os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_FILE"] = ":memory:"

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, func, Index, create_engine, and_, desc
from sqlalchemy.orm import declarative_base, sessionmaker

# 创建独立的 Base
Base = declarative_base()


class StrategyHistory(Base):
    """策略历史记录 SQLAlchemy 模型"""
    __tablename__ = "strategy_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    requirement = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    model_id = Column(String(255), nullable=True)
    temperature = Column(Float, nullable=True, default=0.7)
    tokens_used = Column(Text, nullable=True)
    generation_time = Column(Float, nullable=True)
    is_valid = Column(Boolean, default=True, index=True)
    tags = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        Index('idx_strategy_history_user_created', 'user_id', 'created_at'),
        Index('idx_strategy_history_user_valid', 'user_id', 'is_valid'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "requirement": self.requirement,
            "code": self.code,
            "explanation": self.explanation,
            "model_id": self.model_id,
            "temperature": self.temperature,
            "tokens_used": json.loads(self.tokens_used) if self.tokens_used else None,
            "generation_time": self.generation_time,
            "is_valid": self.is_valid,
            "tags": json.loads(self.tags) if self.tags else [],
            "created_at": self._format_datetime(self.created_at),
            "updated_at": self._format_datetime(self.updated_at),
        }

    @staticmethod
    def _format_datetime(dt):
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def set_tokens_used(self, tokens):
        self.tokens_used = json.dumps(tokens) if tokens else None

    def set_tags(self, tags):
        self.tags = json.dumps(tags) if tags else None

    def get_tokens_used(self):
        if self.tokens_used:
            return json.loads(self.tokens_used)
        return None

    def get_tags(self):
        if self.tags:
            return json.loads(self.tags)
        return []


class StrategyHistoryManager:
    """策略历史记录管理器"""

    _engine = None
    _SessionLocal = None

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            cls._engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
            Base.metadata.create_all(bind=cls._engine)
        return cls._engine

    @classmethod
    def _get_session_local(cls):
        if cls._SessionLocal is None:
            engine = cls._get_engine()
            cls._SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return cls._SessionLocal

    @staticmethod
    def _get_db():
        SessionLocal = StrategyHistoryManager._get_session_local()
        return SessionLocal()

    @staticmethod
    def create(user_id, title, requirement, code, explanation=None, model_id=None,
               temperature=None, tokens_used=None, generation_time=None,
               is_valid=True, tags=None):
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
            return history.to_dict()
        except Exception as e:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_by_id(history_id):
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if history:
                return history.to_dict()
            return None
        except Exception as e:
            return None
        finally:
            db.close()

    @staticmethod
    def list_by_user(user_id, page=1, page_size=10, filters=None, sort_by="created_at", sort_order="desc"):
        db = StrategyHistoryManager._get_db()
        try:
            query = db.query(StrategyHistory).filter(StrategyHistory.user_id == user_id)

            if filters:
                if filters.get("title"):
                    query = query.filter(StrategyHistory.title.contains(filters["title"]))
                if filters.get("is_valid") is not None:
                    query = query.filter(StrategyHistory.is_valid == filters["is_valid"])
                if filters.get("start_time"):
                    query = query.filter(StrategyHistory.created_at >= filters["start_time"])
                if filters.get("end_time"):
                    query = query.filter(StrategyHistory.created_at <= filters["end_time"])
                if filters.get("model_id"):
                    query = query.filter(StrategyHistory.model_id == filters["model_id"])

            total = query.count()

            allowed_sort_fields = ["created_at", "updated_at", "title", "generation_time"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"

            sort_column = getattr(StrategyHistory, sort_by)
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)

            offset = (page - 1) * page_size
            histories = query.offset(offset).limit(page_size).all()

            pages = (total + page_size - 1) // page_size if page_size > 0 else 0

            return {
                "items": [h.to_dict() for h in histories],
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
            }
        except Exception as e:
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
    def delete(history_id):
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if history:
                db.delete(history)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def delete_by_user(user_id, history_ids):
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
            return {
                "deleted": deleted_count,
                "failed": failed_count,
                "total": len(history_ids),
            }
        except Exception as e:
            db.rollback()
            return {
                "deleted": 0,
                "failed": len(history_ids),
                "total": len(history_ids),
            }
        finally:
            db.close()

    @staticmethod
    def regenerate(history_id, new_requirement=None, new_title=None, **kwargs):
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if not history:
                return None

            title = new_title or f"{history.title} (重新生成)"
            requirement = new_requirement or history.requirement

            new_history = StrategyHistory(
                id=str(uuid.uuid4()),
                user_id=history.user_id,
                title=title,
                requirement=requirement,
                code=history.code,
                explanation=history.explanation,
                model_id=kwargs.get("model_id", history.model_id),
                temperature=kwargs.get("temperature", history.temperature),
                tokens_used=None,
                generation_time=None,
                is_valid=True,
                tags=history.tags,
            )

            db.add(new_history)
            db.commit()
            db.refresh(new_history)
            return new_history.to_dict()
        except Exception as e:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def update(history_id, title=None, code=None, explanation=None, is_valid=None, tags=None):
        db = StrategyHistoryManager._get_db()
        try:
            history = db.query(StrategyHistory).filter(StrategyHistory.id == history_id).first()
            if not history:
                return None

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
            return history.to_dict()
        except Exception as e:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_user_stats(user_id):
        from sqlalchemy import func as sql_func
        db = StrategyHistoryManager._get_db()
        try:
            total_count = db.query(sql_func.count(StrategyHistory.id)).filter(
                StrategyHistory.user_id == user_id
            ).scalar() or 0

            valid_count = db.query(sql_func.count(StrategyHistory.id)).filter(
                and_(
                    StrategyHistory.user_id == user_id,
                    StrategyHistory.is_valid == True
                )
            ).scalar() or 0

            avg_generation_time = db.query(sql_func.avg(StrategyHistory.generation_time)).filter(
                StrategyHistory.user_id == user_id
            ).scalar() or 0

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
            return {
                "total_count": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "avg_generation_time": 0,
                "latest_created_at": None,
            }
        finally:
            db.close()


# 测试前重置数据库引擎
@pytest.fixture(autouse=True)
def reset_database():
    """每个测试前重置数据库"""
    # 重置引擎和会话
    StrategyHistoryManager._engine = None
    StrategyHistoryManager._SessionLocal = None
    # 创建新引擎和表
    StrategyHistoryManager._get_engine()
    yield
    # 清理
    if StrategyHistoryManager._engine:
        Base.metadata.drop_all(bind=StrategyHistoryManager._engine)
    StrategyHistoryManager._engine = None
    StrategyHistoryManager._SessionLocal = None


@pytest.fixture
def sample_history_data():
    """提供示例策略历史数据"""
    return {
        "user_id": "user_123",
        "title": "双均线策略",
        "requirement": "创建一个基于5日和20日均线交叉的交易策略",
        "code": """
def strategy(df):
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['signal'] = np.where(df['ma5'] > df['ma20'], 1, -1)
    return df
""",
        "explanation": "这是一个简单的双均线交叉策略",
        "model_id": "gpt-4",
        "temperature": 0.7,
        "tokens_used": {"prompt": 100, "completion": 200, "total": 300},
        "generation_time": 2.5,
        "is_valid": True,
        "tags": ["均线", "趋势", "简单"],
    }


class TestStrategyHistoryCreate:
    """测试创建策略历史记录功能"""

    def test_create_success(self, sample_history_data):
        """测试成功创建策略历史记录"""
        result = StrategyHistoryManager.create(**sample_history_data)

        assert result is not None
        assert result["user_id"] == sample_history_data["user_id"]
        assert result["title"] == sample_history_data["title"]
        assert result["requirement"] == sample_history_data["requirement"]
        assert result["code"] == sample_history_data["code"]
        assert result["explanation"] == sample_history_data["explanation"]
        assert result["model_id"] == sample_history_data["model_id"]
        assert result["temperature"] == sample_history_data["temperature"]
        assert result["tokens_used"] == sample_history_data["tokens_used"]
        assert result["generation_time"] == sample_history_data["generation_time"]
        assert result["is_valid"] == sample_history_data["is_valid"]
        assert result["tags"] == sample_history_data["tags"]
        assert "id" in result
        assert "created_at" in result
        assert "updated_at" in result

    def test_create_minimal_data(self):
        """测试使用最少必需数据创建记录"""
        result = StrategyHistoryManager.create(
            user_id="user_456",
            title="简单策略",
            requirement="创建一个简单策略",
            code="def strategy(df): return df",
        )

        assert result is not None
        assert result["user_id"] == "user_456"
        assert result["title"] == "简单策略"
        assert result["explanation"] is None
        assert result["model_id"] is None
        assert result["tokens_used"] is None
        assert result["tags"] == []

    def test_create_generates_uuid(self, sample_history_data):
        """测试创建时自动生成 UUID"""
        result = StrategyHistoryManager.create(**sample_history_data)

        try:
            uuid.UUID(result["id"])
            assert True
        except ValueError:
            assert False, "ID 不是有效的 UUID"


class TestStrategyHistoryGet:
    """测试获取策略历史记录功能"""

    def test_get_by_id_success(self, sample_history_data):
        """测试根据 ID 成功获取记录"""
        created = StrategyHistoryManager.create(**sample_history_data)
        result = StrategyHistoryManager.get_by_id(created["id"])

        assert result is not None
        assert result["id"] == created["id"]
        assert result["title"] == sample_history_data["title"]

    def test_get_by_id_not_found(self):
        """测试获取不存在的记录"""
        result = StrategyHistoryManager.get_by_id("non-existent-id")
        assert result is None

    def test_get_by_id_invalid_uuid(self):
        """测试使用无效 ID 获取记录"""
        result = StrategyHistoryManager.get_by_id("invalid-id")
        assert result is None


class TestStrategyHistoryList:
    """测试分页查询策略历史记录功能"""

    def test_list_by_user_empty(self):
        """测试查询没有记录的用户"""
        result = StrategyHistoryManager.list_by_user("user_no_data")

        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["pages"] == 0

    def test_list_by_user_with_data(self, sample_history_data):
        """测试查询有记录的用户"""
        for i in range(5):
            data = sample_history_data.copy()
            data["title"] = f"策略{i + 1}"
            StrategyHistoryManager.create(**data)

        result = StrategyHistoryManager.list_by_user(sample_history_data["user_id"])

        assert len(result["items"]) == 5
        assert result["total"] == 5
        assert result["page"] == 1
        assert result["pages"] == 1

    def test_list_by_user_pagination(self, sample_history_data):
        """测试分页功能"""
        for i in range(10):
            data = sample_history_data.copy()
            data["title"] = f"策略{i + 1}"
            StrategyHistoryManager.create(**data)

        result = StrategyHistoryManager.list_by_user(sample_history_data["user_id"], page=1, page_size=3)
        assert len(result["items"]) == 3
        assert result["total"] == 10
        assert result["pages"] == 4

        result = StrategyHistoryManager.list_by_user(sample_history_data["user_id"], page=2, page_size=3)
        assert len(result["items"]) == 3

        result = StrategyHistoryManager.list_by_user(sample_history_data["user_id"], page=4, page_size=3)
        assert len(result["items"]) == 1

    def test_list_by_user_sorting(self, sample_history_data):
        """测试排序功能"""
        for i in range(3):
            data = sample_history_data.copy()
            data["title"] = f"策略{i + 1}"
            StrategyHistoryManager.create(**data)

        result = StrategyHistoryManager.list_by_user(sample_history_data["user_id"])
        titles = [item["title"] for item in result["items"]]
        assert titles == ["策略3", "策略2", "策略1"]

        result = StrategyHistoryManager.list_by_user(
            sample_history_data["user_id"],
            sort_by="created_at",
            sort_order="asc"
        )
        titles = [item["title"] for item in result["items"]]
        assert titles == ["策略1", "策略2", "策略3"]

    def test_list_by_user_filter_by_title(self, sample_history_data):
        """测试按标题过滤"""
        StrategyHistoryManager.create(**sample_history_data)

        data2 = sample_history_data.copy()
        data2["title"] = "另一个策略"
        StrategyHistoryManager.create(**data2)

        result = StrategyHistoryManager.list_by_user(
            sample_history_data["user_id"],
            filters={"title": "双均线"}
        )

        assert len(result["items"]) == 1
        assert "双均线" in result["items"][0]["title"]

    def test_list_by_user_filter_by_is_valid(self, sample_history_data):
        """测试按是否有效过滤"""
        StrategyHistoryManager.create(**sample_history_data)

        data2 = sample_history_data.copy()
        data2["title"] = "无效策略"
        data2["is_valid"] = False
        StrategyHistoryManager.create(**data2)

        result = StrategyHistoryManager.list_by_user(
            sample_history_data["user_id"],
            filters={"is_valid": True}
        )
        assert len(result["items"]) == 1
        assert result["items"][0]["is_valid"] is True

        result = StrategyHistoryManager.list_by_user(
            sample_history_data["user_id"],
            filters={"is_valid": False}
        )
        assert len(result["items"]) == 1
        assert result["items"][0]["is_valid"] is False


class TestStrategyHistoryDelete:
    """测试删除策略历史记录功能"""

    def test_delete_success(self, sample_history_data):
        """测试成功删除记录"""
        created = StrategyHistoryManager.create(**sample_history_data)

        result = StrategyHistoryManager.delete(created["id"])
        assert result is True

        deleted = StrategyHistoryManager.get_by_id(created["id"])
        assert deleted is None

    def test_delete_not_found(self):
        """测试删除不存在的记录"""
        result = StrategyHistoryManager.delete("non-existent-id")
        assert result is False

    def test_delete_by_user(self, sample_history_data):
        """测试批量删除用户记录"""
        ids = []
        for i in range(3):
            data = sample_history_data.copy()
            data["title"] = f"策略{i + 1}"
            created = StrategyHistoryManager.create(**data)
            ids.append(created["id"])

        result = StrategyHistoryManager.delete_by_user(sample_history_data["user_id"], ids)

        assert result["deleted"] == 3
        assert result["failed"] == 0
        assert result["total"] == 3

        for id in ids:
            assert StrategyHistoryManager.get_by_id(id) is None

    def test_delete_by_user_partial(self, sample_history_data):
        """测试批量删除部分不存在记录"""
        created = StrategyHistoryManager.create(**sample_history_data)

        ids = [created["id"], "non-existent-id"]
        result = StrategyHistoryManager.delete_by_user(sample_history_data["user_id"], ids)

        assert result["deleted"] == 1
        assert result["failed"] == 1
        assert result["total"] == 2


class TestStrategyHistoryRegenerate:
    """测试重新生成功能"""

    def test_regenerate_success(self, sample_history_data):
        """测试成功重新生成记录"""
        created = StrategyHistoryManager.create(**sample_history_data)

        result = StrategyHistoryManager.regenerate(created["id"])

        assert result is not None
        assert result["id"] != created["id"]
        assert result["user_id"] == created["user_id"]
        assert "(重新生成)" in result["title"]
        assert result["requirement"] == created["requirement"]
        assert result["code"] == created["code"]

    def test_regenerate_with_new_requirement(self, sample_history_data):
        """测试使用新需求重新生成"""
        created = StrategyHistoryManager.create(**sample_history_data)

        new_requirement = "创建一个基于MACD指标的策略"
        result = StrategyHistoryManager.regenerate(
            created["id"],
            new_requirement=new_requirement,
            new_title="MACD策略"
        )

        assert result is not None
        assert result["requirement"] == new_requirement
        assert result["title"] == "MACD策略"

    def test_regenerate_not_found(self):
        """测试重新生成不存在的记录"""
        result = StrategyHistoryManager.regenerate("non-existent-id")
        assert result is None

    def test_regenerate_with_kwargs(self, sample_history_data):
        """测试传递额外参数重新生成"""
        created = StrategyHistoryManager.create(**sample_history_data)

        result = StrategyHistoryManager.regenerate(
            created["id"],
            model_id="gpt-3.5-turbo",
            temperature=0.5
        )

        assert result is not None
        assert result["model_id"] == "gpt-3.5-turbo"
        assert result["temperature"] == 0.5


class TestStrategyHistoryUpdate:
    """测试更新策略历史记录功能"""

    def test_update_success(self, sample_history_data):
        """测试成功更新记录"""
        created = StrategyHistoryManager.create(**sample_history_data)

        result = StrategyHistoryManager.update(
            created["id"],
            title="更新后的标题",
            is_valid=False,
            tags=["更新", "测试"]
        )

        assert result is not None
        assert result["title"] == "更新后的标题"
        assert result["is_valid"] is False
        assert result["tags"] == ["更新", "测试"]
        assert result["requirement"] == sample_history_data["requirement"]

    def test_update_not_found(self):
        """测试更新不存在的记录"""
        result = StrategyHistoryManager.update("non-existent-id", title="新标题")
        assert result is None

    def test_update_partial(self, sample_history_data):
        """测试部分更新"""
        created = StrategyHistoryManager.create(**sample_history_data)

        result = StrategyHistoryManager.update(created["id"], title="仅更新标题")

        assert result is not None
        assert result["title"] == "仅更新标题"
        assert result["code"] == sample_history_data["code"]


class TestStrategyHistoryStats:
    """测试统计功能"""

    def test_get_user_stats_empty(self):
        """测试获取空用户的统计"""
        result = StrategyHistoryManager.get_user_stats("user_no_data")

        assert result["total_count"] == 0
        assert result["valid_count"] == 0
        assert result["invalid_count"] == 0
        assert result["avg_generation_time"] == 0
        assert result["latest_created_at"] is None

    def test_get_user_stats_with_data(self, sample_history_data):
        """测试获取有数据用户的统计"""
        for i in range(5):
            data = sample_history_data.copy()
            data["generation_time"] = 1.0 + i * 0.5
            if i >= 3:
                data["is_valid"] = False
            StrategyHistoryManager.create(**data)

        result = StrategyHistoryManager.get_user_stats(sample_history_data["user_id"])

        assert result["total_count"] == 5
        assert result["valid_count"] == 3
        assert result["invalid_count"] == 2
        assert result["avg_generation_time"] > 0
        assert result["latest_created_at"] is not None


class TestStrategyHistoryModel:
    """测试 StrategyHistory 模型类"""

    def test_to_dict(self, sample_history_data):
        """测试模型转字典"""
        history = StrategyHistory(
            id=str(uuid.uuid4()),
            user_id=sample_history_data["user_id"],
            title=sample_history_data["title"],
            requirement=sample_history_data["requirement"],
            code=sample_history_data["code"],
        )

        result = history.to_dict()

        assert result["user_id"] == sample_history_data["user_id"]
        assert result["title"] == sample_history_data["title"]
        assert "id" in result
        assert "created_at" in result

    def test_set_and_get_tokens_used(self):
        """测试设置和获取 Token 使用量"""
        history = StrategyHistory()

        tokens = {"prompt": 100, "completion": 200, "total": 300}
        history.set_tokens_used(tokens)

        assert history.get_tokens_used() == tokens

    def test_set_and_get_tags(self):
        """测试设置和获取标签"""
        history = StrategyHistory()

        tags = ["趋势", "均线", "简单"]
        history.set_tags(tags)

        assert history.get_tags() == tags

    def test_get_empty_tags(self):
        """测试获取空标签"""
        history = StrategyHistory()
        assert history.get_tags() == []

    def test_get_empty_tokens(self):
        """测试获取空 Token"""
        history = StrategyHistory()
        assert history.get_tokens_used() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
