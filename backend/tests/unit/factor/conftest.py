"""因子档案测试公共 fixtures：内存 SQLite + 临时快照/归档目录。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# factor 包 __init__ 链式导入会注册 worker.models（Worker.relationship("Strategy") 为字符串引用），
# 必须同时注册 strategy.models，否则实例化映射对象触发全局 mapper 配置时会失败
import strategy.models
from collector.db.database import Base
from factor.models import FactorCatalog, FactorSnapshot


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[FactorCatalog.__table__, FactorSnapshot.__table__])
    Session = sessionmaker(bind=eng)
    with Session() as s:
        yield s


@pytest.fixture
def dirs(tmp_path):
    return {"snapshots": tmp_path / "snapshots", "trash": tmp_path / "trash", "backend": tmp_path}
