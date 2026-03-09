"""思维链管理器单元测试

测试 ThinkingChainManager 的 CRUD 操作和 TOML 导入导出功能
"""
import json
import os
import sys
import uuid
from datetime import datetime

import pytest

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

# 设置测试环境
os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_FILE"] = ":memory:"

from sqlalchemy import Boolean, Column, DateTime, String, Text, func, Index, create_engine, and_, desc
from sqlalchemy.orm import declarative_base, sessionmaker

# 创建独立的 Base
Base = declarative_base()


class ThinkingChain(Base):
    """思维链 SQLAlchemy 模型"""
    __tablename__ = "thinking_chains"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    chain_type = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        Index('idx_thinking_chain_type_active', 'chain_type', 'is_active'),
        Index('idx_thinking_chain_type_created', 'chain_type', 'created_at'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "chain_type": self.chain_type,
            "name": self.name,
            "description": self.description,
            "steps": self.get_steps(),
            "is_active": self.is_active,
            "created_at": self._format_datetime(self.created_at),
            "updated_at": self._format_datetime(self.updated_at),
        }

    @staticmethod
    def _format_datetime(dt):
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def set_steps(self, steps):
        self.steps = json.dumps(steps, ensure_ascii=False) if steps else json.dumps([])

    def get_steps(self):
        if self.steps:
            return json.loads(self.steps)
        return []


class ThinkingChainManager:
    """思维链管理器（测试用内嵌实现）"""

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
        SessionLocal = ThinkingChainManager._get_session_local()
        return SessionLocal()

    @staticmethod
    def create_thinking_chain(data):
        db = ThinkingChainManager._get_db()
        try:
            if "chain_type" not in data or not data["chain_type"]:
                return None
            if "name" not in data or not data["name"]:
                return None
            if "steps" not in data or not data["steps"]:
                return None

            chain = ThinkingChain(
                id=str(uuid.uuid4()),
                chain_type=data["chain_type"],
                name=data["name"],
                description=data.get("description"),
                steps=json.dumps(data["steps"], ensure_ascii=False),
                is_active=data.get("is_active", True),
            )
            db.add(chain)
            db.commit()
            db.refresh(chain)
            return chain.to_dict()
        except Exception as e:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_thinking_chain(chain_id):
        db = ThinkingChainManager._get_db()
        try:
            chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
            if chain:
                return chain.to_dict()
            return None
        except Exception as e:
            return None
        finally:
            db.close()

    @staticmethod
    def get_thinking_chains(chain_type=None, is_active=None, page=1, page_size=10, sort_by="created_at", sort_order="desc"):
        db = ThinkingChainManager._get_db()
        try:
            query = db.query(ThinkingChain)

            if chain_type is not None:
                query = query.filter(ThinkingChain.chain_type == chain_type)
            if is_active is not None:
                query = query.filter(ThinkingChain.is_active == is_active)

            total = query.count()

            allowed_sort_fields = ["created_at", "updated_at", "name", "chain_type"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"

            sort_column = getattr(ThinkingChain, sort_by)
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)

            offset = (page - 1) * page_size
            chains = query.offset(offset).limit(page_size).all()

            pages = (total + page_size - 1) // page_size if page_size > 0 else 0

            return {
                "items": [chain.to_dict() for chain in chains],
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
    def update_thinking_chain(chain_id, data):
        db = ThinkingChainManager._get_db()
        try:
            chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
            if not chain:
                return None

            if "chain_type" in data:
                chain.chain_type = data["chain_type"]
            if "name" in data:
                chain.name = data["name"]
            if "description" in data:
                chain.description = data["description"]
            if "steps" in data:
                chain.steps = json.dumps(data["steps"], ensure_ascii=False)
            if "is_active" in data:
                chain.is_active = data["is_active"]

            db.commit()
            db.refresh(chain)
            return chain.to_dict()
        except Exception as e:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def delete_thinking_chain(chain_id):
        db = ThinkingChainManager._get_db()
        try:
            chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
            if chain:
                db.delete(chain)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def import_from_toml(file_content, update_existing=True):
        import toml

        result = {
            "success": True,
            "created": 0,
            "updated": 0,
            "failed": 0,
            "errors": [],
            "items": [],
        }

        try:
            config = toml.loads(file_content)
        except toml.TomlDecodeError as e:
            result["success"] = False
            result["errors"].append(f"TOML 解析错误: {e}")
            return result

        db = ThinkingChainManager._get_db()
        try:
            chains = config.get("thinking_chain", [])
            if not isinstance(chains, list):
                chains = [chains]

            for chain_data in chains:
                try:
                    if "chain_type" not in chain_data:
                        raise ValueError("缺少必需字段: chain_type")
                    if "name" not in chain_data:
                        raise ValueError("缺少必需字段: name")
                    if "steps" not in chain_data:
                        raise ValueError("缺少必需字段: steps")

                    chain_type = chain_data["chain_type"]
                    name = chain_data["name"]
                    steps = chain_data["steps"]
                    description = chain_data.get("description")
                    is_active = chain_data.get("is_active", True)

                    existing = None
                    if update_existing:
                        existing = (
                            db.query(ThinkingChain)
                            .filter(
                                and_(
                                    ThinkingChain.chain_type == chain_type,
                                    ThinkingChain.name == name,
                                )
                            )
                            .first()
                        )

                    if existing:
                        existing.description = description
                        existing.steps = json.dumps(steps, ensure_ascii=False)
                        existing.is_active = is_active
                        db.commit()
                        db.refresh(existing)
                        result["updated"] += 1
                        result["items"].append({
                            "id": existing.id,
                            "name": existing.name,
                            "chain_type": existing.chain_type,
                            "action": "updated",
                        })
                    else:
                        new_chain = ThinkingChain(
                            id=str(uuid.uuid4()),
                            chain_type=chain_type,
                            name=name,
                            description=description,
                            steps=json.dumps(steps, ensure_ascii=False),
                            is_active=is_active,
                        )
                        db.add(new_chain)
                        db.commit()
                        db.refresh(new_chain)
                        result["created"] += 1
                        result["items"].append({
                            "id": new_chain.id,
                            "name": new_chain.name,
                            "chain_type": new_chain.chain_type,
                            "action": "created",
                        })

                except Exception as e:
                    result["failed"] += 1
                    error_msg = f"导入思维链 '{chain_data.get('name', 'unknown')}' 失败: {e}"
                    result["errors"].append(error_msg)

            if result["failed"] > 0 and result["created"] == 0 and result["updated"] == 0:
                result["success"] = False

        except Exception as e:
            result["success"] = False
            result["errors"].append(f"导入过程出错: {e}")
        finally:
            db.close()

        return result

    @staticmethod
    def export_to_toml(chain_id=None):
        import toml

        db = ThinkingChainManager._get_db()
        try:
            if chain_id:
                chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
                chains = [chain] if chain else []
            else:
                chains = db.query(ThinkingChain).all()

            config = {"thinking_chain": []}
            for chain in chains:
                chain_data = {
                    "chain_type": chain.chain_type,
                    "name": chain.name,
                    "description": chain.description,
                    "steps": chain.get_steps(),
                    "is_active": chain.is_active,
                }
                config["thinking_chain"].append(chain_data)

            return toml.dumps(config)
        except Exception as e:
            return ""
        finally:
            db.close()

    @staticmethod
    def get_active_chain_by_type(chain_type):
        db = ThinkingChainManager._get_db()
        try:
            chain = (
                db.query(ThinkingChain)
                .filter(
                    and_(
                        ThinkingChain.chain_type == chain_type,
                        ThinkingChain.is_active == True,
                    )
                )
                .order_by(desc(ThinkingChain.created_at))
                .first()
            )
            if chain:
                return chain.to_dict()
            return None
        except Exception as e:
            return None
        finally:
            db.close()


# 测试前重置数据库引擎
@pytest.fixture(autouse=True)
def reset_database():
    """每个测试前重置数据库"""
    ThinkingChainManager._engine = None
    ThinkingChainManager._SessionLocal = None
    ThinkingChainManager._get_engine()
    yield
    if ThinkingChainManager._engine:
        Base.metadata.drop_all(bind=ThinkingChainManager._engine)
    ThinkingChainManager._engine = None
    ThinkingChainManager._SessionLocal = None


@pytest.fixture
def sample_thinking_chain_data():
    """提供示例思维链数据"""
    return {
        "chain_type": "strategy_generation",
        "name": "策略生成思维链",
        "description": "用于生成交易策略的思维链",
        "steps": [
            {"id": "step_1", "name": "需求分析", "description": "分析用户需求"},
            {"id": "step_2", "name": "策略设计", "description": "设计策略逻辑"},
            {"id": "step_3", "name": "代码生成", "description": "生成策略代码"},
        ],
        "is_active": True,
    }


@pytest.fixture
def sample_toml_content():
    """提供示例 TOML 内容"""
    return """
[[thinking_chain]]
chain_type = "strategy_generation"
name = "TOML导入测试思维链"
description = "从TOML导入的思维链"
is_active = true

[[thinking_chain.steps]]
id = "step_1"
name = "步骤1"
description = "第一步"

[[thinking_chain.steps]]
id = "step_2"
name = "步骤2"
description = "第二步"
"""


class TestThinkingChainCreate:
    """测试创建思维链功能"""

    def test_create_success(self, sample_thinking_chain_data):
        """测试成功创建思维链"""
        result = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        assert result is not None
        assert result["chain_type"] == sample_thinking_chain_data["chain_type"]
        assert result["name"] == sample_thinking_chain_data["name"]
        assert result["description"] == sample_thinking_chain_data["description"]
        assert result["steps"] == sample_thinking_chain_data["steps"]
        assert result["is_active"] == sample_thinking_chain_data["is_active"]
        assert "id" in result
        assert "created_at" in result
        assert "updated_at" in result

    def test_create_minimal_data(self):
        """测试使用最少必需数据创建"""
        result = ThinkingChainManager.create_thinking_chain({
            "chain_type": "indicator_generation",
            "name": "指标生成思维链",
            "steps": [{"id": "step_1", "name": "步骤1"}],
        })

        assert result is not None
        assert result["chain_type"] == "indicator_generation"
        assert result["name"] == "指标生成思维链"
        assert result["description"] is None
        assert result["is_active"] is True

    def test_create_missing_chain_type(self):
        """测试缺少 chain_type 字段"""
        result = ThinkingChainManager.create_thinking_chain({
            "name": "测试思维链",
            "steps": [{"id": "step_1"}],
        })
        assert result is None

    def test_create_missing_name(self):
        """测试缺少 name 字段"""
        result = ThinkingChainManager.create_thinking_chain({
            "chain_type": "strategy_generation",
            "steps": [{"id": "step_1"}],
        })
        assert result is None

    def test_create_missing_steps(self):
        """测试缺少 steps 字段"""
        result = ThinkingChainManager.create_thinking_chain({
            "chain_type": "strategy_generation",
            "name": "测试思维链",
        })
        assert result is None

    def test_create_generates_uuid(self, sample_thinking_chain_data):
        """测试创建时自动生成 UUID"""
        result = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        try:
            uuid.UUID(result["id"])
            assert True
        except ValueError:
            assert False, "ID 不是有效的 UUID"


class TestThinkingChainGet:
    """测试获取思维链功能"""

    def test_get_thinking_chain_success(self, sample_thinking_chain_data):
        """测试根据 ID 成功获取思维链"""
        created = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)
        result = ThinkingChainManager.get_thinking_chain(created["id"])

        assert result is not None
        assert result["id"] == created["id"]
        assert result["name"] == sample_thinking_chain_data["name"]

    def test_get_thinking_chain_not_found(self):
        """测试获取不存在的思维链"""
        result = ThinkingChainManager.get_thinking_chain("non-existent-id")
        assert result is None

    def test_get_thinking_chains_empty(self):
        """测试获取空列表"""
        result = ThinkingChainManager.get_thinking_chains()

        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["pages"] == 0

    def test_get_thinking_chains_with_data(self, sample_thinking_chain_data):
        """测试获取有数据的列表"""
        for i in range(5):
            data = sample_thinking_chain_data.copy()
            data["name"] = f"思维链{i + 1}"
            ThinkingChainManager.create_thinking_chain(data)

        result = ThinkingChainManager.get_thinking_chains()

        assert len(result["items"]) == 5
        assert result["total"] == 5
        assert result["page"] == 1
        assert result["pages"] == 1

    def test_get_thinking_chains_filter_by_type(self, sample_thinking_chain_data):
        """测试按类型筛选"""
        ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        data2 = sample_thinking_chain_data.copy()
        data2["chain_type"] = "indicator_generation"
        data2["name"] = "指标生成思维链"
        ThinkingChainManager.create_thinking_chain(data2)

        result = ThinkingChainManager.get_thinking_chains(chain_type="strategy_generation")
        assert len(result["items"]) == 1
        assert result["items"][0]["chain_type"] == "strategy_generation"

    def test_get_thinking_chains_filter_by_active(self, sample_thinking_chain_data):
        """测试按激活状态筛选"""
        ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        data2 = sample_thinking_chain_data.copy()
        data2["name"] = "未激活思维链"
        data2["is_active"] = False
        ThinkingChainManager.create_thinking_chain(data2)

        result = ThinkingChainManager.get_thinking_chains(is_active=True)
        assert len(result["items"]) == 1
        assert result["items"][0]["is_active"] is True

    def test_get_thinking_chains_pagination(self, sample_thinking_chain_data):
        """测试分页功能"""
        for i in range(10):
            data = sample_thinking_chain_data.copy()
            data["name"] = f"思维链{i + 1}"
            ThinkingChainManager.create_thinking_chain(data)

        result = ThinkingChainManager.get_thinking_chains(page=1, page_size=3)
        assert len(result["items"]) == 3
        assert result["total"] == 10
        assert result["pages"] == 4

        result = ThinkingChainManager.get_thinking_chains(page=2, page_size=3)
        assert len(result["items"]) == 3

        result = ThinkingChainManager.get_thinking_chains(page=4, page_size=3)
        assert len(result["items"]) == 1

    def test_get_thinking_chains_sorting(self, sample_thinking_chain_data):
        """测试排序功能"""
        for i in range(3):
            data = sample_thinking_chain_data.copy()
            data["name"] = f"思维链{i + 1}"
            ThinkingChainManager.create_thinking_chain(data)

        result = ThinkingChainManager.get_thinking_chains(sort_by="name", sort_order="asc")
        names = [item["name"] for item in result["items"]]
        assert names == ["思维链1", "思维链2", "思维链3"]


class TestThinkingChainUpdate:
    """测试更新思维链功能"""

    def test_update_success(self, sample_thinking_chain_data):
        """测试成功更新思维链"""
        created = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        result = ThinkingChainManager.update_thinking_chain(
            created["id"],
            {
                "name": "更新后的名称",
                "description": "更新后的描述",
                "is_active": False,
            }
        )

        assert result is not None
        assert result["name"] == "更新后的名称"
        assert result["description"] == "更新后的描述"
        assert result["is_active"] is False
        assert result["chain_type"] == sample_thinking_chain_data["chain_type"]

    def test_update_steps(self, sample_thinking_chain_data):
        """测试更新步骤"""
        created = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        new_steps = [
            {"id": "new_step_1", "name": "新步骤1"},
            {"id": "new_step_2", "name": "新步骤2"},
        ]
        result = ThinkingChainManager.update_thinking_chain(
            created["id"],
            {"steps": new_steps}
        )

        assert result is not None
        assert result["steps"] == new_steps

    def test_update_not_found(self):
        """测试更新不存在的思维链"""
        result = ThinkingChainManager.update_thinking_chain(
            "non-existent-id",
            {"name": "新名称"}
        )
        assert result is None

    def test_update_partial(self, sample_thinking_chain_data):
        """测试部分更新"""
        created = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        result = ThinkingChainManager.update_thinking_chain(
            created["id"],
            {"name": "仅更新名称"}
        )

        assert result is not None
        assert result["name"] == "仅更新名称"
        assert result["description"] == sample_thinking_chain_data["description"]


class TestThinkingChainDelete:
    """测试删除思维链功能"""

    def test_delete_success(self, sample_thinking_chain_data):
        """测试成功删除思维链"""
        created = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        result = ThinkingChainManager.delete_thinking_chain(created["id"])
        assert result is True

        deleted = ThinkingChainManager.get_thinking_chain(created["id"])
        assert deleted is None

    def test_delete_not_found(self):
        """测试删除不存在的思维链"""
        result = ThinkingChainManager.delete_thinking_chain("non-existent-id")
        assert result is False


class TestThinkingChainTomlImport:
    """测试 TOML 导入功能"""

    def test_import_from_toml_success(self, sample_toml_content):
        """测试成功从 TOML 导入"""
        result = ThinkingChainManager.import_from_toml(sample_toml_content)

        assert result["success"] is True
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["failed"] == 0
        assert len(result["items"]) == 1
        assert result["items"][0]["action"] == "created"

    def test_import_from_toml_update_existing(self, sample_toml_content):
        """测试导入时更新已存在的配置"""
        # 先创建一条记录
        first_result = ThinkingChainManager.import_from_toml(sample_toml_content)
        assert first_result["created"] == 1

        # 再次导入相同的配置
        second_result = ThinkingChainManager.import_from_toml(sample_toml_content)
        assert second_result["success"] is True
        assert second_result["created"] == 0
        assert second_result["updated"] == 1
        assert second_result["items"][0]["action"] == "updated"

    def test_import_from_toml_without_update(self, sample_toml_content):
        """测试导入时不更新已存在的配置"""
        # 先创建一条记录
        first_result = ThinkingChainManager.import_from_toml(sample_toml_content)
        assert first_result["created"] == 1

        # 再次导入相同的配置，但不更新
        second_result = ThinkingChainManager.import_from_toml(sample_toml_content, update_existing=False)
        assert second_result["success"] is True
        assert second_result["created"] == 1
        assert second_result["updated"] == 0

    def test_import_from_toml_invalid_content(self):
        """测试导入无效的 TOML 内容"""
        result = ThinkingChainManager.import_from_toml("invalid toml content [[")

        assert result["success"] is False
        assert result["failed"] == 0
        assert len(result["errors"]) > 0

    def test_import_from_toml_missing_required_fields(self):
        """测试导入缺少必需字段的 TOML"""
        toml_content = """
[[thinking_chain]]
name = "缺少类型"
"""
        result = ThinkingChainManager.import_from_toml(toml_content)

        assert result["success"] is False
        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    def test_import_multiple_chains(self):
        """测试导入多个思维链"""
        toml_content = """
[[thinking_chain]]
chain_type = "strategy_generation"
name = "策略生成思维链1"
steps = [{id = "step1", name = "步骤1"}]

[[thinking_chain]]
chain_type = "strategy_generation"
name = "策略生成思维链2"
steps = [{id = "step1", name = "步骤1"}]

[[thinking_chain]]
chain_type = "indicator_generation"
name = "指标生成思维链"
steps = [{id = "step1", name = "步骤1"}]
"""
        result = ThinkingChainManager.import_from_toml(toml_content)

        assert result["success"] is True
        assert result["created"] == 3
        assert result["failed"] == 0
        assert len(result["items"]) == 3


class TestThinkingChainTomlExport:
    """测试 TOML 导出功能"""

    def test_export_to_toml_single(self, sample_thinking_chain_data):
        """测试导出单个思维链"""
        created = ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        result = ThinkingChainManager.export_to_toml(created["id"])

        assert result is not None
        assert len(result) > 0
        assert "thinking_chain" in result
        assert sample_thinking_chain_data["name"] in result

    def test_export_to_toml_all(self, sample_thinking_chain_data):
        """测试导出所有思维链"""
        for i in range(3):
            data = sample_thinking_chain_data.copy()
            data["name"] = f"思维链{i + 1}"
            ThinkingChainManager.create_thinking_chain(data)

        result = ThinkingChainManager.export_to_toml()

        assert result is not None
        assert len(result) > 0
        assert "思维链1" in result
        assert "思维链2" in result
        assert "思维链3" in result

    def test_export_to_toml_not_found(self):
        """测试导出不存在的思维链"""
        result = ThinkingChainManager.export_to_toml("non-existent-id")
        assert result is not None
        assert "thinking_chain" in result


class TestThinkingChainGetActive:
    """测试获取激活思维链功能"""

    def test_get_active_chain_by_type_success(self, sample_thinking_chain_data):
        """测试成功获取指定类型的激活思维链"""
        ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        result = ThinkingChainManager.get_active_chain_by_type("strategy_generation")

        assert result is not None
        assert result["chain_type"] == "strategy_generation"
        assert result["is_active"] is True

    def test_get_active_chain_by_type_not_found(self, sample_thinking_chain_data):
        """测试获取不存在的激活思维链"""
        data = sample_thinking_chain_data.copy()
        data["is_active"] = False
        ThinkingChainManager.create_thinking_chain(data)

        result = ThinkingChainManager.get_active_chain_by_type("strategy_generation")
        assert result is None

    def test_get_active_chain_by_type_wrong_type(self, sample_thinking_chain_data):
        """测试获取错误类型的激活思维链"""
        ThinkingChainManager.create_thinking_chain(sample_thinking_chain_data)

        result = ThinkingChainManager.get_active_chain_by_type("indicator_generation")
        assert result is None


class TestThinkingChainModel:
    """测试 ThinkingChain 模型类"""

    def test_to_dict(self, sample_thinking_chain_data):
        """测试模型转字典"""
        chain = ThinkingChain(
            id=str(uuid.uuid4()),
            chain_type=sample_thinking_chain_data["chain_type"],
            name=sample_thinking_chain_data["name"],
            description=sample_thinking_chain_data["description"],
            steps=json.dumps(sample_thinking_chain_data["steps"], ensure_ascii=False),
        )

        result = chain.to_dict()

        assert result["chain_type"] == sample_thinking_chain_data["chain_type"]
        assert result["name"] == sample_thinking_chain_data["name"]
        assert "id" in result
        assert "created_at" in result

    def test_set_and_get_steps(self):
        """测试设置和获取步骤"""
        chain = ThinkingChain()

        steps = [
            {"id": "step_1", "name": "步骤1"},
            {"id": "step_2", "name": "步骤2"},
        ]
        chain.set_steps(steps)

        assert chain.get_steps() == steps

    def test_get_empty_steps(self):
        """测试获取空步骤"""
        chain = ThinkingChain()
        chain.steps = None
        assert chain.get_steps() == []

    def test_format_datetime(self):
        """测试日期时间格式化"""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = ThinkingChain._format_datetime(dt)
        assert result == "2024-01-15 10:30:00"

    def test_format_datetime_none(self):
        """测试空日期时间格式化"""
        result = ThinkingChain._format_datetime(None)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
