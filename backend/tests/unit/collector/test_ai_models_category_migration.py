"""ai_models.category 幂等迁移测试"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from collector.db.migrations import update_ai_models_table

OLD_DDL = """
CREATE TABLE ai_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider VARCHAR NOT NULL, name VARCHAR NOT NULL,
    api_key TEXT NOT NULL, api_host VARCHAR, models TEXT,
    is_default BOOLEAN, is_enabled BOOLEAN, proxy_enabled BOOLEAN,
    proxy_url VARCHAR, proxy_username VARCHAR, proxy_password VARCHAR,
    created_at DATETIME, updated_at DATETIME
)
"""


def _columns(session) -> list[str]:
    return [row[1] for row in session.execute(text("PRAGMA table_info('ai_models')"))]


def test_adds_category_column():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.execute(
            text(
                "INSERT INTO ai_models (provider, name, api_key, is_default, is_enabled) "
                "VALUES ('openai', 'default', 'sk-x', 1, 1)"
            )
        )
        session.commit()
        assert "category" not in _columns(session)

        update_ai_models_table(session, "sqlite")

        assert "category" in _columns(session)
        # 存量行归入 system_two
        row = session.execute(text("SELECT category FROM ai_models WHERE provider='openai'")).fetchone()
        assert row[0] == "system_two"

        # 幂等：再跑一次不报错
        update_ai_models_table(session, "sqlite")
