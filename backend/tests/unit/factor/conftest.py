"""因子档案测试公共 fixtures：内存 SQLite + 临时快照/归档目录。"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# factor 包 __init__ 链式导入会注册 worker.models（Worker.relationship("Strategy") 为字符串引用），
# 必须同时注册 strategy.models，否则实例化映射对象触发全局 mapper 配置时会失败
import strategy.models
from collector.db.database import Base
from factor.models import FactorCatalog, FactorMiningRun, FactorSnapshot


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[FactorCatalog.__table__, FactorSnapshot.__table__, FactorMiningRun.__table__],
    )
    Session = sessionmaker(bind=eng)
    with Session() as s:
        yield s


@pytest.fixture
def dirs(tmp_path):
    return {"snapshots": tmp_path / "snapshots", "trash": tmp_path / "trash", "backend": tmp_path}


@pytest.fixture
def svc(db_session, monkeypatch):
    """FactorService 绑定测试内存 DB：patch get_db_session 让其返回测试 session。

    同时 mock 掉沙箱校验（单元测试不跑真实子进程沙箱，避免 CPU 限额误报），
    并灌入内置因子种子（测试 DB 初始为空）。
    """
    from factor.catalog_service import FactorCatalogService
    from factor.service import FactorService

    @contextmanager
    def _fake_get_db_session():
        yield db_session

    monkeypatch.setattr("factor.service.get_db_session", _fake_get_db_session)
    monkeypatch.setattr("factor.catalog_service.get_db_session", _fake_get_db_session, raising=False)
    s = FactorService()
    # mock 沙箱：validate 只做静态检查（保留安全策略），run 返回固定面板避免子进程超时
    from factor.sandbox import FactorSandbox

    _real_sandbox = FactorSandbox()

    def _mock_validate(code):
        # 保留静态安全校验（拒绝 import os 等），跳过真实执行
        _real_sandbox.check_static(code)

    def _mock_run(code, frames):
        # 先做静态安全校验（拒绝 import os 等）
        _real_sandbox.check_static(code)
        import re

        # 模拟运行时错误：引用不存在的列
        if "missing_col" in code:
            from factor.sandbox import SandboxRuntimeError

            raise SandboxRuntimeError("name 'missing_col' is not defined")
        # 解析 df["col"].pct_change(n) 模式，语义相同的 code 返回相关面板
        m = re.search(r'df\["(\w+)"\]\.pct_change\((\d+)\)', code)
        if m:
            col, window = m.group(1), int(m.group(2))
            sample_df = next(iter(frames.values()), None)
            if sample_df is not None and col in sample_df.columns and window > 0:
                # 线性变换（*100 +3）不改变截面相关性，去重逻辑能命中
                return {sym: df[col].pct_change(window) for sym, df in frames.items()}
        # 兜底：按 code hash 派生
        import hashlib

        h = int(hashlib.md5(code.encode()).hexdigest()[:8], 16)
        cols = ["close", "volume", "open", "high", "low"]
        col = cols[h % len(cols)]
        window = 3 + (h % 18)
        return {sym: df[col].pct_change(window) for sym, df in frames.items()}

    monkeypatch.setattr(s._sandbox, "validate", _mock_validate)
    monkeypatch.setattr(s._sandbox, "run", _mock_run)
    # 灌入内置因子种子（测试 DB 初始为空）
    from factor.engine import FACTOR_META
    from factor.models import FactorCatalog

    for name, meta in FACTOR_META.items():
        db_session.add(
            FactorCatalog(
                name=name,
                kind="builtin",
                label=meta["label"],
                description=meta.get("expression") or None,
                category=meta.get("category"),
                expression=meta.get("expression") or None,
                is_builtin=True,
                supported=bool(meta.get("supported", True)),
                lifecycle_status="DISCOVERED",
            )
        )
    db_session.commit()
    s._reload_from_db()
    return s
