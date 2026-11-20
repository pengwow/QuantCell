"""站内收件箱（落库 + 过滤分页 + 逐行 read_at 已读）单元测试

语义基线（迁移 48 起）：未读 = read_at IS NULL；notification_state 水位表已停用。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base, _import_all_models
from common.notifications import inbox
from common.notifications.inbox_models import TASK_TYPES, AsyncTaskRecord, InboxNotification

# 预注册全部业务模型，避免 Worker 等 relationship 在 mapper 初始化时找不到 Strategy
_import_all_models()


@pytest.fixture()
def db_session():
    """内存 SQLite，只建收件箱 + 影子表"""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng,
        tables=[InboxNotification.__table__, AsyncTaskRecord.__table__],
    )
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


def _record_n(session, n: int, prefix: str = "t", source: str = "system") -> None:
    for i in range(n):
        assert inbox.record_inbox_notification(
            title=f"{prefix}-{i}",
            content=f"{prefix}-content-{i}",
            level="info",
            source=source,
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
        assert row.read_at is None
        assert row.processed_at is None


class TestList:
    def test_empty_inbox(self, db_session):
        data = inbox.list_inbox_notifications(limit=20, db_session=db_session)
        assert data == {"items": [], "unread_count": 0, "read_count": 0, "has_more": False}

    def test_order_desc_and_pagination(self, db_session):
        _record_n(db_session, 5)
        page1 = inbox.list_inbox_notifications(limit=2, db_session=db_session)
        assert [it["title"] for it in page1["items"]] == ["t-4", "t-3"]
        assert page1["has_more"] is True
        assert page1["unread_count"] == 5

        cursor = page1["items"][-1]["id"]
        page2 = inbox.list_inbox_notifications(limit=2, before_id=cursor, db_session=db_session)
        assert [it["title"] for it in page2["items"]] == ["t-2", "t-1"]

        page3 = inbox.list_inbox_notifications(limit=2, before_id=page2["items"][-1]["id"], db_session=db_session)
        assert [it["title"] for it in page3["items"]] == ["t-0"]
        assert page3["has_more"] is False

    def test_items_carry_read_processed_flags(self, db_session):
        _record_n(db_session, 2)
        items = inbox.list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["read"] is False
        assert items[0]["processed"] is False

    def test_filter_task_type(self, db_session):
        _record_n(db_session, 2, prefix="rl", source="rl_train")
        _record_n(db_session, 3, prefix="sys", source="system")
        data = inbox.list_inbox_notifications(limit=20, task_type="rl_train", db_session=db_session)
        assert [it["title"] for it in data["items"]] == ["rl-1", "rl-0"]
        # 全局计数不受过滤影响
        assert data["unread_count"] == 5


class TestReadAt:
    def test_all_unread_initially(self, db_session):
        _record_n(db_session, 3)
        assert inbox.list_inbox_notifications(limit=20, db_session=db_session)["unread_count"] == 3

    def test_mark_all_read(self, db_session):
        _record_n(db_session, 3)
        assert inbox.mark_inbox_read(db_session=db_session) == 3
        data = inbox.list_inbox_notifications(limit=20, db_session=db_session)
        assert data["unread_count"] == 0
        assert data["read_count"] == 3
        assert all(it["read"] for it in data["items"])

    def test_mark_all_read_then_new_arrives(self, db_session):
        _record_n(db_session, 3)
        inbox.mark_inbox_read(db_session=db_session)
        _record_n(db_session, 1, prefix="new")
        data = inbox.list_inbox_notifications(limit=20, db_session=db_session)
        assert data["unread_count"] == 1
        assert data["items"][0]["title"] == "new-0"

    def test_unread_filter(self, db_session):
        _record_n(db_session, 3)
        inbox.mark_inbox_read(db_session=db_session)
        _record_n(db_session, 2, prefix="new")
        only_unread = inbox.list_inbox_notifications(limit=20, unread=True, db_session=db_session)
        assert [it["title"] for it in only_unread["items"]] == ["new-1", "new-0"]
        only_read = inbox.list_inbox_notifications(limit=20, unread=False, db_session=db_session)
        assert [it["title"] for it in only_read["items"]] == ["t-2", "t-1", "t-0"]

    def test_single_read_sets_processed_for_task_sources(self, db_session):
        _record_n(db_session, 1, prefix="rl", source="rl_train")
        _record_n(db_session, 1, prefix="sys", source="system")
        # 按 title 精确定位，不依赖列表倒序位置（items[0] 是最后落库的 sys-0）
        by_title = {it["title"]: it for it in inbox.list_inbox_notifications(limit=20, db_session=db_session)["items"]}

        got = inbox.mark_notification_read(by_title["rl-0"]["id"], db_session=db_session)
        assert got["read"] is True and got["processed"] is True  # 任务类：已读即归档

        got2 = inbox.mark_notification_read(by_title["sys-0"]["id"], db_session=db_session)
        assert got2["read"] is True and got2["processed"] is False  # 非任务类不置 processed

    def test_single_read_idempotent(self, db_session):
        _record_n(db_session, 1, source="backtest")
        item = inbox.list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        first = inbox.mark_notification_read(item["id"], db_session=db_session)
        second = inbox.mark_notification_read(item["id"], db_session=db_session)
        assert first == second

    def test_single_read_not_found(self, db_session):
        assert inbox.mark_notification_read(999, db_session=db_session) is None


class TestDelete:
    def test_delete_single_and_not_found(self, db_session):
        _record_n(db_session, 3)
        assert inbox.delete_notification(2, db_session=db_session) == 2
        items = inbox.list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert [it["title"] for it in items] == ["t-2", "t-0"]
        assert inbox.delete_notification(2, db_session=db_session) is None
        assert inbox.delete_notification(999, db_session=db_session) is None

    def test_delete_unread_decreases_unread_count(self, db_session):
        _record_n(db_session, 3)
        assert inbox.delete_notification(3, db_session=db_session) == 2
        assert inbox.list_inbox_notifications(limit=10, db_session=db_session)["unread_count"] == 2

    def test_pagination_after_delete_no_gap(self, db_session):
        _record_n(db_session, 4)
        assert inbox.delete_notification(3, db_session=db_session) == 3
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

    def test_clear_read_nothing_read(self, db_session):
        _record_n(db_session, 2)
        assert inbox.clear_read_notifications(db_session=db_session) == (0, 2)
        assert inbox.list_inbox_notifications(limit=10, db_session=db_session)["unread_count"] == 2

    def test_clear_read_empty_inbox(self, db_session):
        assert inbox.clear_read_notifications(db_session=db_session) == (0, 0)


class TestAsyncTaskRecord:
    """异步任务终态影子表（补偿扫描数据源，Task 1 引入，此处补语义断言）"""

    def test_task_types_constant(self):
        assert TASK_TYPES == ("rl_train", "factor_job", "collector_task", "backtest", "research")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
