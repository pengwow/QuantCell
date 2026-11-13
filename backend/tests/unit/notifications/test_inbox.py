"""站内收件箱（notifications 落库 + 游标分页 + 已读水位）单元测试"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base, _import_all_models
from common.notifications import inbox
from common.notifications.inbox_models import InboxNotification, NotificationState

# 预注册全部业务模型，避免 Worker 等 relationship 在 mapper 初始化时找不到 Strategy
_import_all_models()


@pytest.fixture()
def db_session():
    """内存 SQLite，只建收件箱两张表"""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=[InboxNotification.__table__, NotificationState.__table__])
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


def _record_n(session, n: int, prefix: str = "t") -> None:
    for i in range(n):
        assert inbox.record_inbox_notification(
            title=f"{prefix}-{i}",
            content=f"{prefix}-content-{i}",
            level="info",
            source="system",
            db_session=session,
        )


class TestRecord:
    def test_record_persists_fields(self, db_session):
        assert inbox.record_inbox_notification(
            title="标题", content="内容", level="warning", source="alert", db_session=db_session
        )
        row = db_session.query(InboxNotification).one()
        assert row.title == "标题"
        assert row.level == "warning"
        assert row.source == "alert"
        assert row.created_at is not None


class TestList:
    def test_empty_inbox(self, db_session):
        data = inbox.list_inbox_notifications(limit=20, db_session=db_session)
        assert data == {"items": [], "unread_count": 0, "read_count": 0, "has_more": False}

    def test_order_desc_and_pagination(self, db_session):
        _record_n(db_session, 5)
        page1 = inbox.list_inbox_notifications(limit=2, db_session=db_session)
        # 倒序：最新在前
        assert [it["title"] for it in page1["items"]] == ["t-4", "t-3"]
        assert page1["has_more"] is True
        assert page1["unread_count"] == 5

        # 游标：取比 t-3 的 id 更旧的
        cursor = page1["items"][-1]["id"]
        page2 = inbox.list_inbox_notifications(limit=2, before_id=cursor, db_session=db_session)
        assert [it["title"] for it in page2["items"]] == ["t-2", "t-1"]
        assert page2["has_more"] is True

        page3 = inbox.list_inbox_notifications(limit=2, before_id=page2["items"][-1]["id"], db_session=db_session)
        assert [it["title"] for it in page3["items"]] == ["t-0"]
        assert page3["has_more"] is False


class TestReadWatermark:
    def test_no_state_row_means_all_unread(self, db_session):
        _record_n(db_session, 3)
        data = inbox.list_inbox_notifications(limit=20, db_session=db_session)
        assert data["unread_count"] == 3

    def test_mark_all_read_then_new_arrives(self, db_session):
        _record_n(db_session, 3)
        inbox.mark_inbox_read(db_session=db_session)
        assert inbox.list_inbox_notifications(limit=20, db_session=db_session)["unread_count"] == 0

        # 之后新落库的通知仍是未读
        _record_n(db_session, 1, prefix="new")
        data = inbox.list_inbox_notifications(limit=20, db_session=db_session)
        assert data["unread_count"] == 1
        assert data["items"][0]["title"] == "new-0"

    def test_mark_all_read_creates_state_row_on_empty_inbox(self, db_session):
        max_id = inbox.mark_inbox_read(db_session=db_session)
        assert max_id == 0
        state = db_session.query(NotificationState).one()
        assert state.id == inbox._STATE_ID
        assert state.last_read_id == 0

    def test_watermark_never_moves_back(self, db_session):
        _record_n(db_session, 3)
        inbox.mark_inbox_read(db_session=db_session)
        state = db_session.query(NotificationState).one()
        assert state.last_read_id == 3

        # 水位只前进：max 空箱(0)不会把水位拉回
        inbox.mark_inbox_read(db_session=db_session)
        assert state.last_read_id == 3


class TestDelete:
    def test_delete_single_and_not_found(self, db_session):
        _record_n(db_session, 3)
        # 删未读一条，返回删除后的未读数 2
        assert inbox.delete_notification(2, db_session=db_session) == 2
        # 剩 id 1/3，倒序为 t-2, t-0
        items = inbox.list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert [it["title"] for it in items] == ["t-2", "t-0"]
        # 再删同一条：不存在返回 None（路由层转 404）
        assert inbox.delete_notification(2, db_session=db_session) is None
        assert inbox.delete_notification(999, db_session=db_session) is None

    def test_delete_unread_decreases_unread_count(self, db_session):
        _record_n(db_session, 3)
        assert inbox.delete_notification(3, db_session=db_session) == 2
        assert inbox.list_inbox_notifications(limit=10, db_session=db_session)["unread_count"] == 2

    def test_pagination_after_delete_no_gap(self, db_session):
        """删中间行后游标分页仍不重不漏（id 水位天然兼容）"""
        _record_n(db_session, 4)
        assert inbox.delete_notification(3, db_session=db_session) == 3  # 删 t-2 (id=3)，剩 3 条未读
        page1 = inbox.list_inbox_notifications(limit=2, db_session=db_session)
        assert [it["title"] for it in page1["items"]] == ["t-3", "t-1"]
        page2 = inbox.list_inbox_notifications(limit=2, before_id=page1["items"][-1]["id"], db_session=db_session)
        assert [it["title"] for it in page2["items"]] == ["t-0"]
        assert page2["has_more"] is False


class TestClearRead:
    def test_clear_read_keeps_unread(self, db_session):
        _record_n(db_session, 5)
        inbox.mark_inbox_read(db_session=db_session)
        _record_n(db_session, 2, prefix="new")
        deleted, unread = inbox.clear_read_notifications(db_session=db_session)
        assert deleted == 5
        assert unread == 2
        data = inbox.list_inbox_notifications(limit=10, db_session=db_session)
        assert data["unread_count"] == 2
        assert data["read_count"] == 0
        assert [it["title"] for it in data["items"]] == ["new-1", "new-0"]

    def test_clear_read_without_state_row(self, db_session):
        """从未点过全部已读：无事可做，一条不删"""
        _record_n(db_session, 2)
        assert inbox.clear_read_notifications(db_session=db_session) == (0, 2)
        assert inbox.list_inbox_notifications(limit=10, db_session=db_session)["unread_count"] == 2

    def test_clear_read_empty_inbox(self, db_session):
        inbox.mark_inbox_read(db_session=db_session)
        assert inbox.clear_read_notifications(db_session=db_session) == (0, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
