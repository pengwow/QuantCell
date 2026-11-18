"""桌面 sidecar 打包回归:数据根目录锚定 + LoggerWrapper exc_info 兼容。

来源:2026-11-18 桌面打包验证实录——
1) services.model_registry 以相对 "data" 建目录,GUI 场景 CWD=/ 只读 →
   OSError [Errno 30] → seed 失败 → 启动即崩;
2) 降级告警用 stdlib 风格 exc_info=True,LoggerWrapper 不识别 → TypeError
   在 except 块里二次爆炸,把可降级路径升级成 lifespan 启动失败。
"""

import os


def test_default_models_dir_is_absolute():
    """DEFAULT_MODELS_DIR 必须是绝对路径(CWD 无关),避免 GUI 场景 CWD=/ 只读崩溃。"""
    import services.model_registry as mr

    assert os.path.isabs(mr.DEFAULT_MODELS_DIR)
    assert mr.DEFAULT_MODELS_DIR.endswith("models")


def test_service_default_storage_is_not_cwd_relative():
    """ModelRegistryService 默认 storage 不得再是相对 'data/models'。"""
    import inspect

    from services import model_registry as mr

    default = inspect.signature(mr.ModelRegistryService.__init__).parameters["storage_path"].default
    if isinstance(default, str):
        assert os.path.isabs(default)
    # default=None 时走类内 DEFAULT_MODELS_DIR(绝对路径),由上一断言覆盖


def test_logger_wrapper_accepts_stdlib_exc_info():
    """except 块内 logger.warning(msg, exc_info=True) 不得 TypeError(打包实录放大器)。"""
    from utils.logger import LogType, get_logger

    log = get_logger("pkg_verify", LogType.APPLICATION)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        # 修复前:TypeError: warning() got an unexpected keyword argument 'exc_info'
        log.warning("seed 跳过", exc_info=True)
        log.info("plain", exc_info=None)


def test_logger_wrapper_resolve_exc_info_variants():
    from utils.logger import LogType, get_logger

    log = get_logger("pkg_verify", LogType.APPLICATION)
    try:
        raise ValueError("v")
    except ValueError as e:
        assert log._resolve_exc_info(True) is e
        assert log._resolve_exc_info(e) is e
        assert log._resolve_exc_info((ValueError, e, e.__traceback__)) is e
        assert log._resolve_exc_info(None) is None
        assert log._resolve_exc_info(False) is None
        # 之外的 tuple 形态不预测,返回 None 即不附加异常
        assert log._resolve_exc_info(("not", "exception")) is None


def test_add_missing_columns_upgrades_legacy_workers_table(monkeypatch, tmp_path):
    """存量库缺 owner_id 列时,通用补列通道自动补齐(桌面实录 /workers 500 根因)。

    本测试用独立 sqlite 文件构造旧版 workers 表(仅历史列),再跑
    add_missing_columns_from_models——它按 collector Base.metadata 对照补列。
    """
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import Session

    from collector.db.migrations import add_missing_columns_from_models

    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))  # database 模块 import 期读 env
    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE workers ("
                "id INTEGER PRIMARY KEY, name VARCHAR, status VARCHAR, "
                "strategy_id INTEGER, created_at TIMESTAMP)"
            )
        )

    with Session(eng) as session:
        add_missing_columns_from_models(session, "sqlite")
        session.commit()
        # 幂等:第二遍不得报错或重复加列
        add_missing_columns_from_models(session, "sqlite")
        session.commit()

    insp = inspect(eng)
    cols = {c["name"] for c in insp.get_columns("workers")}
    assert "owner_id" in cols  # 实录缺失列
    assert "id" in cols and cols.__len__() >= 16  # 其余模型列也已补齐
    index_names = {ix["name"] for ix in insp.get_indexes("workers")}
    assert "ix_workers_owner_id" in index_names  # index=True 的索引也要补建


def test_add_missing_columns_skips_unsupported_dialect():
    """非 sqlite/duckdb 方言直接跳过,不抛异常(守护 boot 路径)。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from collector.db.migrations import add_missing_columns_from_models

    eng = create_engine("sqlite://")
    with Session(eng) as session:
        add_missing_columns_from_models(session, "postgresql")  # 不应抛
