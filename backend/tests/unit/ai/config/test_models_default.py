"""AIModelBusiness：category 传导、同类型默认唯一、get_default_model"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import strategy.models  # 先注册 Strategy 表，否则 worker.models 的 relationship 解析失败
from ai.config.models import AIModelBusiness
from collector.db.database import Base
from collector.db.models import AIModel


def _session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    # 只建 ai_models 表：全量 create_all 会因其他模块表未导入而卡在 workers→strategies 外键解析
    Base.metadata.create_all(engine, tables=[AIModel.__table__])
    factory = sessionmaker(bind=engine)
    # 每次方法调用新建 session（内存库同一 engine 共享数据），避免 finally.close() 关掉共享会话
    monkeypatch.setattr(AIModelBusiness, "_get_db", staticmethod(factory))
    return factory


def test_default_is_unique_within_same_category(monkeypatch):
    _session_factory(monkeypatch)
    AIModelBusiness.create(provider="openai", name="a", api_key="k", category="system_two", is_default=True)
    AIModelBusiness.create(provider="anthropic", name="b", api_key="k", category="system_two", is_default=True)
    AIModelBusiness.create(provider="laya", name="l", api_key="", category="system_one", is_default=True)

    assert AIModelBusiness.get_default_model("system_two")["name"] == "b"
    assert AIModelBusiness.get_default_model("system_one")["name"] == "l"


def test_get_default_model_returns_plain_api_key_only_when_requested(monkeypatch):
    _session_factory(monkeypatch)
    AIModelBusiness.create(provider="laya", name="l", api_key="secret-key", category="system_one", is_default=True)

    masked = AIModelBusiness.get_default_model("system_one")
    assert "api_key" not in masked and "api_key_masked" in masked

    plain = AIModelBusiness.get_default_model("system_one", include_api_key=True)
    assert plain["api_key"] == "secret-key"


def test_get_default_model_skips_disabled(monkeypatch):
    _session_factory(monkeypatch)
    row = AIModelBusiness.create(provider="laya", name="l", api_key="", category="system_one", is_default=True)
    AIModelBusiness.update(row["id"], is_enabled=False)
    assert AIModelBusiness.get_default_model("system_one") is None


def test_update_default_clears_only_same_category(monkeypatch):
    _session_factory(monkeypatch)
    one = AIModelBusiness.create(provider="laya", name="one", api_key="", category="system_one", is_default=True)
    AIModelBusiness.create(provider="openai", name="two", api_key="k", category="system_two", is_default=True)
    AIModelBusiness.update(one["id"], category="system_two", is_default=True)

    assert AIModelBusiness.get_default_model("system_one") is None
    assert AIModelBusiness.get_default_model("system_two")["name"] == "one"


def test_to_dict_contains_category(monkeypatch):
    _session_factory(monkeypatch)
    row = AIModelBusiness.create(provider="laya", name="l", api_key="", category="system_one")
    assert row["category"] == "system_one"
