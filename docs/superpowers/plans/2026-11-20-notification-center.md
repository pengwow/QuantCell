# 消息中心/站内通知全面优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 五类异步任务（RL/因子/采集/回测/研究）终态闭环通知 + 重启补偿扫描 + 收件箱逐行已读/任务过滤/点击跳转。

**Architecture:** 后端新增 `task_notices.py` 统一通知 Hub（同步入口、线程安全），五个任务域在状态机终态翻转处调用；`after_commit` 不引入（事务边界内直接双写）。补偿扫描写为各模块自带的 `compensate_interrupted_tasks()`，由 `core/lifespan.py` 启动时统一挂载。收件箱从「全局已读水位」升级为「逐行 read_at」语义，`notification_state` 水位表停用不删。前端加 `taskRoutes.ts` 注册中心负责「任务类型 → 详情页路径」映射与点击跳转兜底。

**Tech Stack:** FastAPI + SQLAlchemy(内存 SQLite 单测) + Alembic + React18 + zustand + antd v6（间隔组件禁用 Tailwind space-y，详见项目规则）+ bun。

**设计规格:** `docs/superpowers/specs/2026-11-20-notification-center-design.md`（本计划的唯一上游依据）

---

## File Structure

| 操作 | 文件 | 职责 |
|---|---|---|
| Create | `backend/common/notifications/task_notices.py` | 任务终态通知 Hub：文案模板 + 收件箱落库 + WS 推送 + 外部渠道 + 影子表 upsert |
| Modify | `backend/common/notifications/inbox_models.py` | InboxNotification 扩列 read_at/processed_at；新增 AsyncTaskRecord |
| Create | `backend/alembic/versions/48_notification_read_at_and_async_task_records.py` | 迁移 48 |
| Modify | `backend/common/notifications/inbox.py` | 水位语义 → read_at 逐行语义 + 过滤 + 单条已读 |
| Modify | `backend/common/notifications/routes.py` | GET /inbox 过滤参数；POST /inbox/{id}/read |
| Modify | `backend/tests/unit/notifications/test_inbox.py` | 语义重写 + 影子表测试 |
| Create | `backend/tests/unit/notifications/test_task_notices.py` | Hub 单测（文案/落库/影子表/WS 静默降级） |
| Create | `backend/tests/unit/notifications/test_notification_routes.py` | 路由层过滤/单条已读/404 TestClient 测试 |
| Modify | `backend/services/rl_task_runner.py` | RL 终态埋点 + 影子表 |
| Modify | `backend/factor/job_manager.py` | 因子终态埋点 + 影子表 |
| Modify | `backend/collector/utils/task_manager.py` | 采集终态埋点 + 内存 dict 同步 |
| Modify | `backend/backtest/routes.py` | 回测终态埋点 |
| Modify | `backend/research/loop.py` | 研究终态埋点 |
| Modify | `backend/core/lifespan.py` | 启动补偿扫描挂载 + Hub 绑定主事件循环 |
| Create | `frontend/src/utils/taskRoutes.ts` | 任务类型→详情页路由注册中心 + 跳转兜底 |
| Modify | `frontend/src/store/notificationStore.ts` | store 扩展（过滤态、任务元数据透传） |
| Modify | `frontend/src/components/NotificationInbox.tsx` | 点击跳转 + 任务过滤 tab |
| Create/Modify | `i18n/zh-CN.json`、`i18n/en-US.json` | 新增文案 key |
| Modify | `docs/testing/pages/notifications.md` | 验证项同步（项目铁则） |

**运行环境口径：** 后端命令一律 `cd backend && uv run …`；测试基线 `tests/unit/notifications/`；前端构建验证统一 `cd frontend && bun run build`（不跑 dev，防端口冲突）。

---

### Task 1: DB 基础 —— inbox 扩列 + AsyncTaskRecord 表 + Alembic 迁移 48

**Files:**
- Modify: `backend/common/notifications/inbox_models.py`
- Create: `backend/alembic/versions/48_notification_read_at_and_async_task_records.py`
- Test: `backend/tests/unit/notifications/test_inbox.py`（追加）

- [x] **Step 1: 在 test_inbox.py 追加失败测试（fixture 扩 AsyncTaskRecord 表 + 两个新断言）**

在 `test_inbox.py` 顶部 import 区（L10 后）追加：

```python
from common.notifications.inbox_models import AsyncTaskRecord
```

将 fixture 中 `tables=[...]` 一行（L24）替换为：

```python
    Base.metadata.create_all(
        eng,
        tables=[
            InboxNotification.__table__,
            NotificationState.__table__,
            AsyncTaskRecord.__table__,
        ],
    )
```

文件末尾（`if __name__ == "__main__":` 之前）追加：

```python
class TestAsyncTaskRecord:
    """异步任务终态影子表（补偿扫描数据源）"""

    def test_upsert_roundtrip(self, db_session):
        from datetime import UTC, datetime

        row = AsyncTaskRecord(
            task_type="rl_train",
            task_id="rl-abc-123",
            status="queued",
            name="PPO-LTC",
        )
        db_session.add(row)
        db_session.commit()
        got = db_session.query(AsyncTaskRecord).filter_by(task_id="rl-abc-123").one()
        assert got.status == "queued"
        assert got.created_at is not None and got.updated_at is not None

        # 状态翻转走 update（补偿扫描语义：终态覆盖）
        got.status = "succeeded"
        got.updated_at = datetime.now(UTC)
        db_session.commit()
        assert db_session.query(AsyncTaskRecord).count() == 1

    def test_task_id_unique(self, db_session):
        db_session.add(AsyncTaskRecord(task_type="backtest", task_id="dup-1", status="queued"))
        db_session.commit()
        db_session.add(AsyncTaskRecord(task_type="backtest", task_id="dup-1", status="failed"))
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()
```

在 `class TestRecord` 内（L51 之后）追加一条 read_at 默认值断言：

```python
    def test_read_at_and_processed_at_default_none(self, db_session):
        row = db_session.query(InboxNotification).first()
        assert row is not None
        assert row.read_at is None
        assert row.processed_at is None
```

- [x] **Step 2: 运行测试确认失败（模型缺列/缺类）**

Run: `cd backend && uv run pytest tests/unit/notifications/test_inbox.py -q`
Expected: FAIL，报错含 `read_at`（AttributeError）或 `cannot import name 'AsyncTaskRecord'`

- [x] **Step 3: 修改 inbox_models.py**

3a. import 行（L15）改为：

```python
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
```

3b. `InboxNotification.created_at` 列（L33）之后追加：

```python
    # 逐行已读/处理标记（迁移 48 起生效；read_at IS NULL 即未读）
    # processed_at 语义仅任务类通知使用：单条已读的瞬间置一次，用于「已读即归档任务」
    read_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
```

3c. 文件末尾追加：

```python
_TASK_TYPES = (
    "rl_train",
    "factor_job",
    "collector_task",
    "backtest",
    "research",
)


class AsyncTaskRecord(TimezoneAwareBase):
    """异步任务终态影子表（补偿扫描数据源）

    五个异步任务域注册时写 queued、开工翻 running、终态 upsert 终态值。
    服务重启后 compensate_interrupted_tasks() 据此把残留 queued/running 的行
    判定为「重启前被中断」。collector/backtest/research 自身有任务表，不写这里
    （补偿直接扫原表）；仅 rl_train/factor_job 两域以本表为补偿依据。
    """

    __tablename__ = "async_task_records"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    task_type = Column(String(32), nullable=False, index=True)  # _TASK_TYPES 之一
    # 各域自己的 task_id（uuid），跨域不加唯一（域内唯一即可，域内以 (task_type, task_id) 定位）
    task_id = Column(String(64), nullable=False, index=True, unique=True)
    # queued / running / succeeded / failed / cancelled
    status = Column(String(32), nullable=False)
    name = Column(String(200), nullable=False, default="")
    extra = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    # TimezoneAwareBase 无自动时间列，显式声明（aware 值经 __setattr__ 统一转 UTC）
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
```

- [x] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/test_inbox.py -q`
Expected: PASS（原水位语义用例不受影响：read_at 默认 None 不参与旧判定）

- [x] **Step 5: 新建迁移 48**

创建 `backend/alembic/versions/48_notification_read_at_and_async_task_records.py`：

```python
"""收件箱逐行已读语义升级 + async_task_records 任务影子表。

1) notifications 加 read_at / processed_at：
   未读判定从「id > notification_state.last_read_id 水位比较」升级为
   「read_at IS NULL」逐行标记。动机：任务终态通知需要单条已读、
   以及任务类通知已读即归档（processed_at）的逐行语义，水位表无法表达。
   notification_state 停用不删（模型与历史单行保留，代码不再读写），
   旧链路（< 48）回滚后仍可用；inbox.py 本次同步移除全部水位引用。
   存量按旧水位语义等价回填：id <= last_read_id → read_at = created_at，
   无水位行视为全部未读（不回填）。

2) 新表 async_task_records：rl_train / factor_job 两域的终态影子表，
   服务重启后补偿扫描（compensate_interrupted_tasks）依据。

幂等：按迁移 45/47 先例，inspector 检测列/表已存在则跳过
（新库 create_all 按新 schema 建立，迁移空跑）。
天花板（ponytail:）：SQLite batch 重建整表锁写；notifications 为单管理员
自部署流水表，量级远未到 online DDL 的必要。
"""

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision = "48"
down_revision = "47"
branch_labels = None
depends_on = None


def _has_table(conn, table: str) -> bool:
    return sa_inspect(conn).has_table(table)


def _add_column_if_missing(conn, table: str, column: sa.Column) -> None:
    names = {c["name"] for c in sa_inspect(conn).get_columns(table)}
    if column.name in names:
        return
    if conn.dialect.name == "sqlite":
        # SQLite 无 ADD COLUMN 事务保证差异，走 batch 兼容路径
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(column)
    else:
        op.add_column(table, column)


def upgrade() -> None:
    conn = op.get_bind()

    # 1) notifications 扩列
    _add_column_if_missing(
        conn, "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        conn, "notifications", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # 2) 存量水位回填（语义等价）：水位行存在才回填
    if _has_table(conn, "notification_state") and _has_table(conn, "notifications"):
        conn.execute(
            sa.text(
                """
                UPDATE notifications
                SET read_at = created_at
                WHERE read_at IS NULL
                  AND id <= (
                      SELECT COALESCE(MAX(last_read_id), 0)
                      FROM notification_state WHERE id = 1
                  )
                """
            )
        )

    # 3) async_task_records 影子表
    if not _has_table(conn, "async_task_records"):
        op.create_table(
            "async_task_records",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("task_type", sa.String(32), nullable=False),
            sa.Column("task_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("extra", sa.JSON, nullable=True),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_async_task_records_task_type", "async_task_records", ["task_type"])
        op.create_index(
            "uq_async_task_records_task_id", "async_task_records", ["task_id"], unique=True
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _has_table(conn, "async_task_records"):
        op.drop_index("uq_async_task_records_task_id", table_name="async_task_records")
        op.drop_index("ix_async_task_records_task_type", table_name="async_task_records")
        op.drop_table("async_task_records")
    # read_at/processed_at 不回滚：回滚会销毁升级后产生的逐行已读数据，
    # 列可空无害（旧代码路径不引用）
```

- [x] **Step 6: 对本地开发库验证迁移可进可退**

Run: `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: 三条命令均无 traceback；最后一句 `Running upgrade 47 -> 48`（若当前库已滞后多个 head，会先补跑既有迁移，属正常）

- [x] **Step 7: 全量通知测试回归 + Commit**

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS

```bash
git add backend/common/notifications/inbox_models.py backend/alembic/versions/48_notification_read_at_and_async_task_records.py backend/tests/unit/notifications/test_inbox.py
git commit -m "feat(notifications): inbox 逐行已读列与 AsyncTaskRecord 影子表（迁移 48）"
```

---

### Task 2: inbox.py 水位语义 → 逐行 read_at 语义 + 路由过滤/单条已读

**Files:**
- Modify: `backend/common/notifications/inbox_models.py`（仅一处重命名）
- Modify: `backend/common/notifications/inbox.py:1-134`（整文件重写）
- Modify: `backend/common/notifications/routes.py:15-18,196-227`（三处）
- Create: `backend/tests/unit/notifications/test_notification_routes.py`
- Modify: `backend/tests/unit/notifications/test_inbox.py`（TestClass 重写）

- [x] **Step 1: 公开任务类型常量（inbox_models.py 一行重命名）**

```python
# 名字从 _TASK_TYPES 改为 TASK_TYPES：inbox.py / task_notices.py 均要引用，
# 跨模块用下划线名是反模式；同时把「异步任务域」语义写到注释里
TASK_TYPES = (
    "rl_train",
    "factor_job",
    "collector_task",
    "backtest",
    "research",
)
```

同时 InboxNotification 旁的 `AsyncTaskRecord.task_type` 注释中 `_TASK_TYPES` 同步改为 `TASK_TYPES`。

- [x] **Step 2: 重写 test_inbox.py 已读语义用例并新增过滤/单条已读用例（先失败）**

`test_inbox.py` 全文替换为：

```python
"""站内收件箱（落库 + 过滤分页 + 逐行 read_at 已读）单元测试

语义基线（迁移 48 起）：未读 = read_at IS NULL；notification_state 水位表已停用。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base, _import_all_models
from common.notifications import inbox
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification, TASK_TYPES

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
        rl_item = inbox.list_inbox_notifications(limit=20, db_session=db_session)["items"][0]
        sys_item = inbox.list_inbox_notifications(limit=20, db_session=db_session)["items"][1]

        got = inbox.mark_notification_read(rl_item["id"], db_session=db_session)
        assert got["read"] is True and got["processed"] is True  # 任务类：已读即归档

        got2 = inbox.mark_notification_read(sys_item["id"], db_session=db_session)
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
```

- [x] **Step 3: 运行确认失败**

Run: `cd backend && uv run pytest tests/unit/notifications/test_inbox.py -q`
Expected: FAIL —— `AttributeError: module 'common.notifications.inbox' has no attribute 'list_inbox_notifications' ... unexpected keyword argument 'task_type'`（或 mark_notification_read 不存在）

- [x] **Step 4: 重写 inbox.py（全文）**

`backend/common/notifications/inbox.py` 全文替换为：

```python
"""站内收件箱读写：落库、过滤分页查询、逐行 read_at 已读

单管理员自部署场景，全站共享一个收件箱（无 user_id 隔离）。
未读判定 = read_at IS NULL（迁移 48 起的逐行语义）。
旧的 notification_state 全局水位表停用：水位只能表达「全部已读」，
无法支持单条已读与「任务类通知已读即归档（processed_at）」。
"""

import typing
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update

from utils.db_session import use_db_session
from utils.logger import LogType, get_logger

from .inbox_models import InboxNotification, TASK_TYPES

logger = get_logger(__name__, LogType.APPLICATION)


def _now() -> datetime:
    return datetime.now(UTC)


def record_inbox_notification(
    title: str,
    content: str,
    level: str,
    source: str,
    db_session: typing.Any | None = None,
) -> bool:
    """落库一条站内通知。写库失败仅记日志，不阻塞渠道投递主链路。"""
    try:
        with use_db_session(db_session) as db:
            db.add(InboxNotification(title=title, content=content, level=level, source=source))
            db.commit()
        return True
    except Exception as e:  # 不能让落库失败影响通知投递
        logger.error(f"站内通知落库失败(不影响投递): {e}")
        return False


def _to_dict(row: InboxNotification) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "level": row.level,
        "source": row.source,
        # 派生布尔：read 由 read_at 推出，任务类过滤与点击跳转依赖 source
        "read": row.read_at is not None,
        "processed": row.processed_at is not None,
        # sqlite 存的是 naive UTC，按 alerts_routes 惯例补 Z 后缀声明 UTC
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    }


def _count_unread(db: typing.Any) -> int:
    """当前未读数 = read_at IS NULL 的条数。"""
    stmt = (
        select(func.count())
        .select_from(InboxNotification)
        .where(InboxNotification.read_at.is_(None))
    )
    return int(db.execute(stmt).scalar() or 0)


def list_inbox_notifications(
    limit: int = 20,
    before_id: int | None = None,
    unread: bool | None = None,
    task_type: str | None = None,
    db_session: typing.Any | None = None,
) -> dict:
    """游标分页拉取收件箱：按 id 倒序，before_id 表示取比它更旧的一页。

    unread=True 仅未读 / False 仅已读 / None 全量；task_type 匹配 source 列
    （五个任务域常量见 TASK_TYPES）。返回 {items, unread_count, read_count, has_more}。
    """
    with use_db_session(db_session) as db:
        # 多取一条判断 has_more，再截掉
        query = select(InboxNotification).order_by(InboxNotification.id.desc()).limit(limit + 1)
        if before_id is not None:
            query = query.where(InboxNotification.id < before_id)
        if unread is True:
            query = query.where(InboxNotification.read_at.is_(None))
        elif unread is False:
            query = query.where(InboxNotification.read_at.is_not(None))
        if task_type:
            query = query.where(InboxNotification.source == task_type)
        rows = db.execute(query).scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        unread_count = _count_unread(db)
        total = int(db.execute(select(func.count()).select_from(InboxNotification)).scalar() or 0)

        return {
            "items": [_to_dict(r) for r in rows],
            "unread_count": unread_count,
            "read_count": max(total - unread_count, 0),
            "has_more": has_more,
        }


def mark_inbox_read(db_session: typing.Any | None = None) -> int:
    """全部已读：批量置 read_at；返回置位行数。幂等：已读行不动。"""
    with use_db_session(db_session) as db:
        result = db.execute(
            update(InboxNotification)
            .where(InboxNotification.read_at.is_(None))
            .values(read_at=_now())
        )
        db.commit()
        return int(result.rowcount or 0)


def mark_notification_read(notification_id: int, db_session: typing.Any | None = None) -> dict | None:
    """单条已读：置 read_at；任务类通知首次已读时同时置 processed_at（已读即归档）。

    幂等：已有 read_at 的行不再动 processed_at。返回条目 dict；不存在返回 None。
    """
    with use_db_session(db_session) as db:
        row = db.get(InboxNotification, notification_id)
        if row is None:
            return None
        if row.read_at is None:
            row.read_at = _now()
            if row.source in TASK_TYPES and row.processed_at is None:
                row.processed_at = _now()
            db.commit()
        return _to_dict(row)


def delete_notification(notification_id: int, db_session: typing.Any | None = None) -> int | None:
    """删除单条站内通知（物理删除，通知是流水非审计数据）。

    返回删除后的全局未读数；条目不存在返回 None（路由层转 404）。
    """
    with use_db_session(db_session) as db:
        row = db.get(InboxNotification, notification_id)
        if row is None:
            return None
        db.delete(row)
        db.commit()
        return _count_unread(db)


def clear_read_notifications(db_session: typing.Any | None = None) -> tuple[int, int]:
    """清空已读：物理删除 read_at 非空的流水，保留未读。

    返回 (删除条数, 清空后的未读数)。
    """
    with use_db_session(db_session) as db:
        result = db.execute(delete(InboxNotification).where(InboxNotification.read_at.is_not(None)))
        db.commit()
        return int(result.rowcount or 0), _count_unread(db)
```

- [x] **Step 5: 路由层测试先行（新建 test_notification_routes.py）**

```python
"""通知路由层集成测试：inbox 过滤参数透传、单条已读、全部已读返回值

inbox 函数级语义由 test_inbox.py 守护；这里只验证 FastAPI 层的参数接线。
"""

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import utils.auth as auth_mod
import utils.rbac as rbac
from collector.db.database import Base, _import_all_models
from common.notifications import inbox
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification
from common.notifications.routes import router

_import_all_models()


@pytest.fixture()
def env():
    """内存 SQLite + TestClient；路由内 use_db_session 替换为内存会话工厂"""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng, tables=[InboxNotification.__table__, AsyncTaskRecord.__table__]
    )
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()

    @contextmanager
    def fake_use_db_session(_db_session=None):
        yield session

    orig = inbox.use_db_session
    inbox.use_db_session = fake_use_db_session
    try:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[auth_mod.get_current_user] = lambda: {"user_id": 1}
        app.dependency_overrides[rbac.is_guest_user] = lambda request: False
        yield TestClient(app), session
    finally:
        inbox.use_db_session = orig
        session.close()


def _seed(session) -> None:
    assert inbox.record_inbox_notification(
        title="RL完成", content="x", level="success", source="rl_train", db_session=session
    )
    assert inbox.record_inbox_notification(
        title="系统", content="y", level="info", source="system", db_session=session
    )


class TestInboxRoutes:
    def test_task_type_filter(self, env):
        client, session = env
        _seed(session)
        resp = client.get("/api/v1/notifications/inbox", params={"task_type": "rl_train"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert [it["title"] for it in items] == ["RL完成"]

    def test_unread_filter(self, env):
        client, session = env
        _seed(session)
        inbox.mark_inbox_read(db_session=session)
        _seed_new(session)
        resp = client.get("/api/v1/notifications/inbox", params={"unread": "true"})
        assert resp.status_code == 200
        assert [it["title"] for it in resp.json()["data"]["items"]] == ["again"]


def _seed_new(session) -> None:
    assert inbox.record_inbox_notification(
        title="again", content="z", level="info", source="system", db_session=session
    )


class TestSingleReadRoute:
    def test_read_then_404(self, env):
        client, session = env
        _seed(session)
        resp = client.get("/api/v1/notifications/inbox")
        first_id = resp.json()["data"]["items"][0]["id"]

        ok = client.post(f"/api/v1/notifications/inbox/{first_id}/read")
        assert ok.status_code == 200
        assert ok.json()["data"]["read"] is True

        missing = client.post("/api/v1/notifications/inbox/999/read")
        assert missing.status_code == 404

    def test_read_all_returns_marked(self, env):
        client, session = env
        _seed(session)
        resp = client.post("/api/v1/notifications/inbox/read-all")
        assert resp.status_code == 200
        assert resp.json()["data"]["marked"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [x] **Step 6: 修改 routes.py（三处）**

6a. 模块 docstring 的端点清单（L15-18 区）追加一行：

```
    - POST /api/notifications/inbox/{id}/read: 单条站内通知已读
```

6b. `GET /inbox`（L196-211）整函数替换为：

```python
@router.get("/inbox", response_model=ApiResponse)
async def list_inbox_notifications(
    http_request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    before_id: int | None = Query(default=None, description="游标：取 id 小于该值的更旧一页"),
    unread: bool | None = Query(default=None, description="true 仅未读 / false 仅已读 / 不传全量"),
    task_type: str | None = Query(
        default=None,
        description="任务类型过滤（rl_train/factor_job/collector_task/backtest/research），匹配通知 source",
    ),
    current_user: dict = Depends(get_current_user),
):
    """站内收件箱列表（按 id 倒序游标分页，携带全局未读数，支持任务类型/已读过滤）"""
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权查看站内收件箱")
    try:
        data = inbox.list_inbox_notifications(
            limit=limit, before_id=before_id, unread=unread, task_type=task_type
        )
        return ApiResponse(code=0, message="获取站内收件箱成功", data=data)
    except Exception as e:
        logger.error(f"获取站内收件箱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

6c. `POST /inbox/read-all`（L214-227）中 `inbox.mark_inbox_read()` 返回值透传 —— 函数体 try 块替换为：

```python
    try:
        marked = inbox.mark_inbox_read()
        return ApiResponse(
            code=0, message="站内收件箱已全部标记为已读", data={"ok": True, "marked": marked}
        )
    except Exception as e:
        logger.error(f"站内收件箱全部已读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

6d. 在 `POST /inbox/read-all` 端点与 `DELETE /inbox/read` 端点之间插入新端点：

```python
@router.post("/inbox/{notification_id}/read", response_model=ApiResponse)
async def mark_notification_read(
    http_request: Request,
    notification_id: int,
    current_user: dict = Depends(get_current_user),
):
    """单条站内通知已读（任务类通知已读即归档，置 processed_at）"""
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权操作站内收件箱")
    try:
        item = inbox.mark_notification_read(notification_id)
        if item is None:
            raise HTTPException(status_code=404, detail="通知不存在或已删除")
        return ApiResponse(code=0, message="通知已标记为已读", data=item)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"通知单条已读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [x] **Step 7: 运行全部通知测试确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS

- [x] **Step 8: Commit**

```bash
git add backend/common/notifications/inbox.py backend/common/notifications/inbox_models.py backend/common/notifications/routes.py backend/tests/unit/notifications/test_inbox.py backend/tests/unit/notifications/test_notification_routes.py
git commit -m "feat(notifications): inbox 逐行已读语义 + 任务过滤/单条已读 API"
```

---

### Task 3: task_notices.py 通知 Hub（TDD）

**Files:**
- Create: `backend/common/notifications/task_notices.py`
- Test: `backend/tests/unit/notifications/test_task_notices.py`

**契约来源（spec §5）：** 终态仅三值 `SUCCEEDED/FAILED/INTERRUPTED`；收件箱 `source=task_type`；WS payload `data.metadata` 携带 `{task_type, task_id, task_status, name}`（经 `WebSocketChannel.send` 直传，见 channels.py:446）；影子表只服务 `rl_train/factor_job` 两域（其余三域有自己的任务表，模型 docstring 已声明）。外部渠道：SUCCEEDED 只推 WS；FAILED/INTERRUPTED 追加 WECOM/FEISHU（未配置渠道在渠道层自动返回失败，无害）。

**既有依赖事实（已核实）：**
- `common/notifications/models.py`：`NotificationChannel(EMAIL/WECOM/FEISHU/WEBSOCKET)`、`NotificationLevel(INFO/SUCCESS/WARNING/ERROR/CRITICAL，小写 value)`、`NotificationCategory.TASK`；`NotificationMessage` 全字段有默认，必填仅 title/content。
- `common/notifications/service.py:131`：`await notification_service.send(message, channels=[...])`，模块级单例 `notification_service`（routes.py:39 引用）。
- `websocket/manager.py`：全局 `manager`，`async broadcast(message: dict, topic: str | None = None)`；`WebSocketChannel._get_manager` 延迟导入同一实例（channels.py:408）。

- [x] **Step 1: 新建 test_task_notices.py（先失败）**

```python
"""任务终态通知 Hub 单测：影子表翻转 / 收件箱文案 / loop 调度三态"""

import asyncio
import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import common.notifications.inbox as inbox_mod
import common.notifications.task_notices as task_notices
import common.notifications.websocket as ws_mod
from collector.db.database import Base, _import_all_models
from common.notifications.inbox import list_inbox_notifications
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification

_import_all_models()


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng, tables=[InboxNotification.__table__, AsyncTaskRecord.__table__]
    )
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def patched_sessions(monkeypatch, db_session):
    """Hub 与收件箱的落库统一走内存会话；顺手解绑主 loop，隔离调度行为"""
    task_notices.bind_event_loop(None)

    @contextmanager
    def fake(_ignored=None):
        yield db_session

    monkeypatch.setattr(task_notices, "use_db_session", fake)
    monkeypatch.setattr(inbox_mod, "use_db_session", fake)


class TestNotifyTaskEvent:
    def test_succeeded_writes_inbox_and_shadow(self, patched_sessions, db_session):
        task_notices.upsert_async_task_record("rl_train", "t-1", "queued", name="PPO运行")
        task_notices.notify_task_event(
            "rl_train", "t-1", task_notices.TASK_STATUS_SUCCEEDED, name="PPO运行"
        )

        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["title"] == "RL训练任务已完成"
        assert item["level"] == "success"
        assert item["source"] == "rl_train"

        row = db_session.query(AsyncTaskRecord).filter_by(task_id="t-1").one()
        assert row.status == "succeeded"

    def test_failed_includes_error_text(self, patched_sessions, db_session):
        task_notices.notify_task_event(
            "factor_job",
            "f-9",
            task_notices.TASK_STATUS_FAILED,
            name="RS族计算",
            error="因子列缺失ecie\nTraceback(略)",
        )
        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["level"] == "error"
        assert "RS族计算" in item["content"]
        assert "因子列缺失" in item["content"]
        row = db_session.query(AsyncTaskRecord).filter_by(task_id="f-9").one()
        assert row.status == "failed"

    def test_backtest_does_not_touch_shadow_table(self, patched_sessions, db_session):
        """影子表只服务 rl_train/factor_job；回测等域有自己的任务表"""
        task_notices.notify_task_event(
            "backtest", "b-1", task_notices.TASK_STATUS_SUCCEEDED, name="BTC回测"
        )
        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["title"] == "回测任务已完成"
        assert db_session.query(AsyncTaskRecord).count() == 0

    def test_interrupted_level_and_shadow(self, patched_sessions, db_session):
        task_notices.upsert_async_task_record("factor_job", "f-1", "running", name="RS族计算")
        task_notices.notify_task_event(
            "factor_job", "f-1", task_notices.TASK_STATUS_INTERRUPTED, name="RS族计算"
        )
        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["level"] == "warning"
        assert db_session.query(AsyncTaskRecord).filter_by(task_id="f-1").one().status == "interrupted"

    def test_invalid_status_raises(self, patched_sessions):
        with pytest.raises(ValueError):
            task_notices.notify_task_event("rl_train", "x", "RUNNING")

    def test_shadow_rows_not_duplicated(self, patched_sessions, db_session):
        task_notices.upsert_async_task_record("rl_train", "u-1", "queued")
        task_notices.upsert_async_task_record("rl_train", "u-1", "running")
        task_notices.notify_task_event("rl_train", "u-1", task_notices.TASK_STATUS_SUCCEEDED)
        assert db_session.query(AsyncTaskRecord).filter_by(task_id="u-1").count() == 1


class TestDispatch:
    """实时投递调度：无 loop 静默降级 / 绑定 loop 后经 WebSocketChannel 到 broadcast"""

    def test_no_loop_only_inbox(self, patched_sessions, db_session):
        """脚本/回测进程场景：无事件循环也不崩，只保留收件箱"""
        task_notices.bind_event_loop(None)
        task_notices.notify_task_event("rl_train", "n-1", task_notices.TASK_STATUS_SUCCEEDED, name="m")
        assert list_inbox_notifications(limit=10, db_session=db_session)["unread_count"] == 1

    @pytest.fixture()
    def worker_loop(self):
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        yield loop
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=3)
        loop.close()

    def test_dispatch_reaches_broadcast(self, patched_sessions, worker_loop, monkeypatch):
        task_notices.bind_event_loop(worker_loop)

        captured: list[dict] = []

        async def fake_broadcast(message, topic=None):
            captured.append(message)

        monkeypatch.setattr(ws_mod.manager, "broadcast", fake_broadcast)

        task_notices.notify_task_event("rl_train", "w-1", task_notices.TASK_STATUS_SUCCEEDED, name="m")

        # 等 worker loop 跑完投递协程（跨线程同步点）
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.3), worker_loop).result(timeout=5)

        assert len(captured) == 1
        payload = captured[0]
        assert payload["type"] == "notification"
        assert payload["data"]["metadata"]["task_type"] == "rl_train"
        assert payload["data"]["level"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [x] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/unit/notifications/test_task_notices.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'common.notifications.task_notices'`

- [x] **Step 3: 新建 task_notices.py**

```python
"""任务终态通知 Hub（spec §5）：五个异步任务域统一出口

任务模块只在「状态机终态翻转处」调用本模块，职责集中在这里：
1. upsert_async_task_record：写/翻 async_task_records 影子行
   （rl_train/factor_job 两域服务重启后补偿扫描的数据源；其余三域有自己的任务表）
2. notify_task_event：终态通知统一入口（仅接受 SUCCEEDED/FAILED/INTERRUPTED）
   - record_inbox_notification 落站内收件箱（source=task_type，前端过滤键）
   - 实时推送：协程上下文内调用走当前 running loop；工作线程调用走
     lifespan 绑定的主 loop（bind_event_loop）；两处都没有（独立脚本/回测
     进程）时静默跳过，只保留收件箱
   - FAILED/INTERRUPTED 追加企业微信/飞书外发（未配置渠道在渠道层自动失败，无害）

线程安全：公开函数均为同步函数、可在任意线程调用；收件箱与影子表各自
开会话落库，不跨线程共享 session；投递失败不影响收件箱落库结果。
"""

import asyncio
import threading
import typing

from sqlalchemy import select

from common.notifications.inbox import record_inbox_notification
from common.notifications.inbox_models import AsyncTaskRecord
from common.notifications.models import (
    NotificationCategory,
    NotificationChannel,
    NotificationLevel,
    NotificationMessage,
)
from utils.db_session import use_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

TASK_STATUS_SUCCEEDED = "SUCCEEDED"
TASK_STATUS_FAILED = "FAILED"
TASK_STATUS_INTERRUPTED = "INTERRUPTED"
_TASK_STATUSES = (TASK_STATUS_SUCCEEDED, TASK_STATUS_FAILED, TASK_STATUS_INTERRUPTED)

# 终态 → (收件箱 level, 影子行 status)
_NOTIFICATION_TO_SHADOW = {
    TASK_STATUS_SUCCEEDED: (NotificationLevel.SUCCESS, "succeeded"),
    TASK_STATUS_FAILED: (NotificationLevel.ERROR, "failed"),
    TASK_STATUS_INTERRUPTED: (NotificationLevel.WARNING, "interrupted"),
}

_TASK_TYPE_LABELS = {
    "rl_train": "RL训练",
    "factor_job": "因子计算",
    "collector_task": "数据采集",
    "backtest": "回测",
    "research": "深度研究",
}

_STATUS_LABELS = {
    TASK_STATUS_SUCCEEDED: "已完成",
    TASK_STATUS_FAILED: "失败",
    TASK_STATUS_INTERRUPTED: "已中断",
}

# 影子表只服务这两个域：collector/backtest/research 有自己的任务表，
# 补偿扫描（任务 6）直接扫原表；这里写影子行反而制造双份事实源
_SHADOWED_TASK_TYPES = frozenset({"rl_train", "factor_job"})

_SUCCESS_CHANNELS: list[NotificationChannel] = [NotificationChannel.WEBSOCKET]
_FAILURE_CHANNELS: list[NotificationChannel] = [
    NotificationChannel.WEBSOCKET,
    NotificationChannel.WECOM,
    NotificationChannel.FEISHU,
]

# lifespan 启动时绑定，供工作线程投递实时消息/外发渠道
_bound_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def bind_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _bound_loop
    with _loop_lock:
        _bound_loop = loop


def upsert_async_task_record(
    task_type: str,
    task_id: str,
    status: str,
    *,
    name: str | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """写/翻影子行（注册态 queued/running 与终态翻转共用；失败仅记日志不阻塞主链路）"""
    try:
        with use_db_session() as db:
            row = (
                db.execute(
                    select(AsyncTaskRecord).where(
                        AsyncTaskRecord.task_type == task_type,
                        AsyncTaskRecord.task_id == task_id,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if row is None:
                row = AsyncTaskRecord(task_type=task_type, task_id=task_id, status=status)
                db.add(row)
            row.status = status
            if name is not None:
                row.name = name
            if error is not None:
                row.error = error
            if extra is not None:
                row.extra = extra
            db.commit()
    except Exception as e:  # 影子表缺失只影响补偿扫描，不允许拖垮任务本身
        logger.error(f"影子行 upsert 失败 task={task_type}/{task_id}: {e}")


def notify_task_event(
    task_type: str,
    task_id: str,
    status: str,
    *,
    name: str | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """任务终态统一通知入口（同步、线程安全）。

    仅接受终态三值；queued/running 作为非终态由埋点直接调
    upsert_async_task_record，不发通知。
    """
    if status not in _TASK_STATUSES:
        raise ValueError(f"任务通知仅支持终态 {_TASK_STATUSES}，收到 {status!r}")

    label = _TASK_TYPE_LABELS.get(task_type, task_type)
    level, shadow_status = _NOTIFICATION_TO_SHADOW[status]

    if task_type in _SHADOWED_TASK_TYPES:
        upsert_async_task_record(
            task_type, task_id, shadow_status, name=name, error=error, extra=extra
        )

    display_name = name or task_id
    content = display_name
    if error:
        # 错误详情截断 500 字，防 IM/收件箱被长栈刷屏
        content = f"{display_name}\n{error[:500]}"
    title = f"{label}任务{_STATUS_LABELS[status]}"

    record_inbox_notification(title=title, content=content, level=level.value, source=task_type)

    message = NotificationMessage(
        title=title,
        content=content,
        level=level,
        category=NotificationCategory.TASK,
        metadata={
            "task_type": task_type,
            "task_id": task_id,
            "task_status": status,
            "name": name or "",
        },
    )
    _dispatch(message, _SUCCESS_CHANNELS if status == TASK_STATUS_SUCCEEDED else _FAILURE_CHANNELS)


def _dispatch(message: NotificationMessage, channels: list[NotificationChannel]) -> None:
    """实时投递调度：协程上下文走当前 loop；工作线程走绑定的主 loop；都没有则跳过"""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        running.create_task(_deliver(message, channels))
    elif _bound_loop is not None and _bound_loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(_deliver(message, channels), _bound_loop)
        fut.add_done_callback(_log_delivery_failure)


def _log_delivery_failure(fut: typing.Any) -> None:
    try:
        fut.result()
    except Exception as e:
        logger.error(f"任务通知实时投递失败(不影响收件箱): {e}")


async def _deliver(message: NotificationMessage, channels: list[NotificationChannel]) -> None:
    from common.notifications.service import notification_service  # 避免模块顶层循环依赖

    try:
        await notification_service.send(message, channels=channels)
    except Exception as e:
        logger.error(f"任务通知渠道投递失败(不影响收件箱): {e}")
```

**注意 websocket.run_thread 安全：** WS 渠道由 `NotificationService.send` 经 `WebSocketChannel` 到 `websocket/manager.py::manager.broadcast`，全程 asyncio 原生，无额外线程动作，符合项目规则。

- [x] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS（含 Task 1/2 既有用例）

- [x] **Step 5: Commit**

```bash
git add backend/common/notifications/task_notices.py backend/tests/unit/notifications/test_task_notices.py
git commit -m "feat(notifications): 任务终态通知 Hub task_notices"
```

### Task 4: RL / 因子任务埋点（影子表唯一写入方）

`rl_train` / `factor_job` 是仅有的两类写 `async_task_records` 影子表的域
（collector / backtest / research 有自己的任务表，Task 5 只发通知不写影子行）。
挂钩位置都在**已有终态收口点**，不新建状态机。

**Files:**
- Modify: `backend/services/rl_task_runner.py`（4 处挂钩）
- Modify: `backend/factor/job_manager.py`（4 处挂钩）
- Test: `backend/tests/unit/notifications/test_task_hooks.py`（新建）

- [x] **Step 1: 写失败测试（test_task_hooks.py 全文）**

fixture 与 `test_task_notices.py` 同款：内存 SQLite + patch 两处 `use_db_session`。
RL / factor 的状态机跑在工作线程，fake 闭包让两处落库共享同一个 session；
测试全程主线程只做轮询等待，不与工作线程并发操作 session。

```python
"""RL / 因子任务埋点行为测试：影子表 upsert + 终态通知落收件箱。"""

from __future__ import annotations

import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import common.notifications.inbox as inbox_mod
import common.notifications.task_notices as task_notices
import services.rl_task_runner as rl_runner
from collector.db.database import Base, _import_all_models
from common.notifications.inbox import list_inbox_notifications
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification
from factor.job_manager import FactorJobManager

_import_all_models()


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng, tables=[InboxNotification.__table__, AsyncTaskRecord.__table__]
    )
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def patched_sessions(monkeypatch, db_session):
    """影子表与收件箱落库统一走内存会话；解绑主 loop 隔离调度行为"""
    task_notices.bind_event_loop(None)

    @contextmanager
    def fake(_ignored=None):
        yield db_session

    monkeypatch.setattr(task_notices, "use_db_session", fake)
    monkeypatch.setattr(inbox_mod, "use_db_session", fake)


def _wait_terminal(task_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = rl_runner.get_task(task_id)
        if task is not None and task.terminal:
            return task
        time.sleep(0.05)
    raise AssertionError(f"RL 任务 {task_id} 未在 {timeout}s 内进入终态")


def _shadow_rows(db):
    return {r.task_id: r.status for r in db.execute(select(AsyncTaskRecord)).scalars().all()}


class TestRlTaskHooks:
    def test_done_upserts_and_notifies(self, patched_sessions, db_session):
        rl_runner.reset_tasks()
        tid = rl_runner.submit_train_task({}, train_fn=lambda c, r: SimpleNamespace(model_path=None))
        task = _wait_terminal(tid)
        assert task.status == "done"

        rows = _shadow_rows(db_session)
        assert rows[tid] == "succeeded"
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert len(items) == 1
        assert items[0]["source"] == "rl_train"
        assert items[0]["title"] == "RL训练任务已完成"

    def test_running_upsert_seen_by_train_fn(self, patched_sessions, db_session):
        rl_runner.reset_tasks()
        seen = {}

        def fake_train(config, reporter):
            # 此刻主线程在轮询 sleep，session 无并发使用
            seen["rows"] = _shadow_rows(db_session)
            return SimpleNamespace(model_path=None)

        tid = rl_runner.submit_train_task({}, train_fn=fake_train)
        _wait_terminal(tid)
        # train_fn 运行时任务已翻 running：影子行应已同步翻转
        assert seen["rows"][tid] == "running"

    def test_error_maps_to_failed(self, patched_sessions, db_session):
        rl_runner.reset_tasks()

        def boom(config, reporter):
            raise RuntimeError("boom")

        tid = rl_runner.submit_train_task({}, train_fn=boom)
        task = _wait_terminal(tid)
        assert task.status == "error"

        assert _shadow_rows(db_session)[tid] == "failed"
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["level"] == "error"
        assert "boom" in items[0]["content"]

    def test_cancelled_quiet_shadow_only(self, patched_sessions, db_session):
        """cancelled 用户自己发起：只落影子行，不发通知"""
        rl_runner.reset_tasks()
        task = rl_runner.TrainTask(task_id="rltrain_case_cancel")
        with rl_runner._registry_lock:
            rl_runner._tasks[task.task_id] = task
        rl_runner._finish(task, "cancelled", message="已取消")

        assert _shadow_rows(db_session)["rltrain_case_cancel"] == "cancelled"
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items == []


class TestFactorJobHooks:
    def test_completed_maps_to_succeeded(self, patched_sessions, db_session):
        # daemon 后台线程（sweeper/lease）随进程退出，测试无需显式清理
        mgr = FactorJobManager(heartbeat_interval=999)
        job_id = mgr.submit("mining", {}, runner=lambda on_p, on_p2, on_ev: {"n": 1})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = mgr.get_status(job_id)
            if status and status["status"] == "completed":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("factor job 未完成")

        assert list(_shadow_rows(db_session).values()) == ["succeeded"]
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["source"] == "factor_job"

    def test_failed_maps_to_failed(self, patched_sessions, db_session):
        mgr = FactorJobManager(heartbeat_interval=999)

        def boom(on_p, on_p2, on_ev):
            raise RuntimeError("挖掘失败")

        job_id = mgr.submit("mining", {}, runner=boom)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = mgr.get_status(job_id)
            if status and status["status"] == "failed":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("factor job 未落失败终态")

        assert list(_shadow_rows(db_session).values()) == ["failed"]
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["level"] == "error"
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest tests/unit/notifications/test_task_hooks.py -v`
Expected: FAIL — RL 用例 KeyError（影子行不存在）、factor 用例 `assert [] == ['succeeded']`；
`test_cancelled_quiet_shadow_only` 同样 FAIL（无影子行写入）。

- [x] **Step 3: rl_task_runner.py 四处挂钩**

3a. 顶部 import（`from utils.logger import ...` 之后）：

```python
from common.notifications.task_notices import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    notify_task_event,
    upsert_async_task_record,
)
```

3b. `submit_train_task` 注册后落 queued 影子行：

```python
    task = TrainTask(task_id=f"rltrain_{uuid.uuid4().hex[:12]}")
    with _registry_lock:
        _tasks[task.task_id] = task
    upsert_async_task_record("rl_train", task.task_id, "queued")
    runner = train_fn or _default_train
```

3c. `_run_task` 置 running 后落影子行：

```python
        with task.lock:
            task.status = "running"
            task.started_at = time.monotonic()
        upsert_async_task_record("rl_train", task.task_id, "running")
```

3d. `_finish` 上方新增映射 + `_finish` 末尾挂钩（cancelled 不发通知只记影子行；
`_finish` 已有终态防重 return，挂钩天然不会重复触发）：

```python
#: RL 内部状态 → 通知中心终态（task_notices 仅接受 SUCCEEDED/FAILED/INTERRUPTED）
_RL_NOTIFY_STATUS = {"done": TASK_STATUS_SUCCEEDED, "error": TASK_STATUS_FAILED}


def _report_terminal(task: TrainTask) -> None:
    """终态挂钩：done/error 发通知并写影子行；cancelled 只写影子行（用户自己取消）"""
    if task.status == "cancelled":
        upsert_async_task_record("rl_train", task.task_id, "cancelled")
        return
    notify_status = _RL_NOTIFY_STATUS.get(task.status)
    if notify_status:
        notify_task_event(
            "rl_train",
            task.task_id,
            notify_status,
            error=task.error,
            extra={"model_path": task.model_path},
        )
```

```python
    task._broadcast_state()
    task.log(f"任务结束: {status}")
    _report_terminal(task)
```

3e. `cancel_task` 的 queued 直落分支（它绕过 `_finish`，须单独挂钩）：

```python
    if queued_abort:
        upsert_async_task_record("rl_train", task.task_id, "cancelled")
        task._broadcast_state()
```

- [x] **Step 4: 跑 RL 用例确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/test_task_hooks.py::TestRlTaskHooks -v`
Expected: PASS（4 passed）

- [x] **Step 5: factor/job_manager.py 挂钩**

5a. 顶部 import（`from factor.job_lease import ...` 之前）：

```python
from common.notifications.task_notices import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    notify_task_event,
    upsert_async_task_record,
)
```

5b. `FactorJobManager` 新增方法（放 `_update` 之前）：

```python
    def _report_status(self, job: FactorJob) -> None:
        """通知中心挂钩：running 落影子行；completed/failed 发终态通知。

        JobStatus 无取消语义（仅四值），cancelled 不存在；影子表只写
        rl_train/factor_job 两域（见 task_notices._SHADOWED_TASK_TYPES）。
        """
        status = str(job.status)
        if status == "running":
            upsert_async_task_record("factor_job", job.job_id, "running")
        elif status == "completed":
            notify_task_event(
                "factor_job", job.job_id, TASK_STATUS_SUCCEEDED, extra={"kind": job.kind}
            )
        elif status == "failed":
            notify_task_event(
                "factor_job",
                job.job_id,
                TASK_STATUS_FAILED,
                error=job.error,
                extra={"kind": job.kind},
            )
```

5c. `submit` 落 queued 影子行 + `_run` 三处翻转点挂钩：

```python
        self._emit(job)
        upsert_async_task_record("factor_job", job_id, "queued")
        self._executor.submit(self._run, job, runner, on_terminal, on_event_cb)
```

```python
        try:
            self._update(job.job_id, status=JobStatus.RUNNING, progress=0.0, stage="running")
            self._report_status(job)
```

```python
            self._update(
                job.job_id,
                status=JobStatus.COMPLETED,
                progress=100.0,
                stage="completed",
                message="完成",
            )
            self._report_status(job)
            if on_terminal is not None:
```

```python
            self._update(job.job_id, status=JobStatus.FAILED, error=str(e), message="失败")
            self._report_status(job)
            if on_terminal is not None:
```

- [x] **Step 6: 跑全部挂钩用例确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/test_task_hooks.py -v`
Expected: PASS（6 passed）

- [x] **Step 7: 全量通知回归 + Commit**

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS

```bash
git add backend/services/rl_task_runner.py backend/factor/job_manager.py backend/tests/unit/notifications/test_task_hooks.py
git commit -m "feat(notifications): RL/因子任务接入终态通知与影子表"
```

### Task 5: 采集/回测/研究三域终态埋点（只发通知，不写影子表）

**Files:**
- Modify: `backend/collector/utils/task_manager.py`（L14 import 区 + L278 `complete_task` + L414 `fail_task`）
- Modify: `backend/backtest/routes.py`（L38 import 区 + 新挂钩 + L341-392 `run_backtest_async`）
- Modify: `backend/research/loop.py`（L40 import 区 + 模块级挂钩 + L322-331 `_finish`）
- Test: `backend/tests/unit/notifications/test_domain_hooks.py`

三域 与 rl/factor 的差别：都有自己的任务表（`TaskBusiness` / `backtest_tasks` / `research_sessions`），
**不写 `async_task_records` 影子行**（Hub 内 `_SHADOWED_TASK_TYPES` 已只放行 rl_train/factor_job）。
测试不拉起各域主流程（不落业务库、不建 WS 连接）：每个域提取一个纯映射挂钩函数，
monkeypatch 各模块命名空间里的 `notify_task_event` 收集调用断言；另配 `inspect.getsource`
接线检查防止「函数写了没接上」。

- [x] **Step 1: 写失败测试 `tests/unit/notifications/test_domain_hooks.py`**

```python
"""采集/回测/研究三域终态挂钩单测。

三域有自己的任务表（不写 async_task_records 影子行），挂钩只做
「内部状态 → task_notices 终态」映射转发。统一 monkeypatch 各模块
命名空间里的 notify_task_event 收集调用断言，不触发任何业务库写入；
inspect.getsource 接线检查确保挂钩真的被终态收口函数调用。
"""

import inspect

from backtest import routes as backtest_routes
from collector.utils import task_manager
from research import loop as research_loop


def _collect_calls(monkeypatch, target: str):
    calls = []

    def fake(task_type, task_id, status, *, name=None, error=None, extra=None):
        calls.append((task_type, task_id, status, name, error))

    monkeypatch.setattr(target, fake)
    return calls


# ---------- collector ----------

class TestCollectorHook:
    def test_complete_succeeded(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "collector.utils.task_manager.notify_task_event")
        task_manager._notify_terminal("t-1", task_manager.TASK_STATUS_SUCCEEDED, name="crypto_download")
        assert calls == [("collector_task", "t-1", "SUCCEEDED", "crypto_download", None)]

    def test_failed_with_error(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "collector.utils.task_manager.notify_task_event")
        task_manager._notify_terminal("t-2", task_manager.TASK_STATUS_FAILED, name="crypto_download", error="超时")
        assert calls == [("collector_task", "t-2", "FAILED", "crypto_download", "超时")]

    def test_wired_into_terminal_exits(self):
        # complete_task / fail_task 是采集任务唯一的两个终态收口，都必须调挂钩
        assert "_notify_terminal" in inspect.getsource(task_manager.TaskManager.complete_task)
        assert "_notify_terminal" in inspect.getsource(task_manager.TaskManager.fail_task)


# ---------- backtest ----------

class TestBacktestHook:
    def test_success_status_maps_succeeded(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "backtest.routes.notify_task_event")
        backtest_routes.notify_backtest_result("b-1", {"status": "success"}, name="DualMA")
        backtest_routes.notify_backtest_result("b-2", {"status": "completed"}, name="DualMA")
        assert calls == [
            ("backtest", "b-1", "SUCCEEDED", "DualMA", None),
            ("backtest", "b-2", "SUCCEEDED", "DualMA", None),
        ]

    def test_stopped_is_silent(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "backtest.routes.notify_task_event")
        backtest_routes.notify_backtest_result("b-3", {"status": "stopped", "message": "用户终止"}, name="DualMA")
        assert calls == []

    def test_other_status_maps_failed(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "backtest.routes.notify_task_event")
        backtest_routes.notify_backtest_result("b-4", {"status": "error", "message": "代理不可用"}, name="DualMA")
        backtest_routes.notify_backtest_result("b-5", {"status": None}, name="DualMA")
        assert calls == [
            ("backtest", "b-4", "FAILED", "DualMA", "代理不可用"),
            ("backtest", "b-5", "FAILED", "DualMA", "回测失败"),
        ]

    def test_wired_into_run_backtest_async(self):
        # run_backtest_async 是闭包拿不到引用，对整个 routes 源码做接线检查
        src = inspect.getsource(backtest_routes)
        assert "notify_backtest_result(task_id, result" in src
        assert "notify_task_event(\n                        \"backtest\"" in src


# ---------- research ----------

class TestResearchHook:
    def test_completed_maps_succeeded(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "research.loop.notify_task_event")
        research_loop._notify_session_terminal(7, "主力因子挖掘", "completed")
        assert calls == [("research", "7", "SUCCEEDED", "主力因子挖掘", None)]

    def test_failed_maps_failed_with_error(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "research.loop.notify_task_event")
        research_loop._notify_session_terminal(8, "主力因子挖掘", "failed", error="LLM 超时")
        assert calls == [("research", "8", "FAILED", "主力因子挖掘", "LLM 超时")]

    def test_cancelled_is_silent(self, monkeypatch):
        # cancel/pause 是用户主动操作，无信息增量（spec §4）
        calls = _collect_calls(monkeypatch, "research.loop.notify_task_event")
        research_loop._notify_session_terminal(9, "主力因子挖掘", "cancelled")
        assert calls == []

    def test_wired_into_finish(self):
        assert "_notify_session_terminal" in inspect.getsource(research_loop.ResearchLoop._finish)


if __name__ == "__main__":
    raise SystemExit("请用 pytest 运行: uv run pytest tests/unit/notifications/test_domain_hooks.py -v")
```

- [x] **Step 2: 跑测试确认失败（三个挂钩函数都不存在）**

Run: `cd backend && uv run pytest tests/unit/notifications/test_domain_hooks.py -v`
Expected: FAIL/ERROR — `AttributeError: module 'collector.utils.task_manager' has no attribute '_notify_terminal'`（完成情况对 backtest/research 同理）。

- [x] **Step 3: collector 埋点**

3a. [task_manager.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/collector/utils/task_manager.py) 顶部 L16（`from websocket.manager import manager` 之后）追加：

```python
from common.notifications.task_notices import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    notify_task_event,
)
```

3b. `class TaskStatus` 定义块之后（L26 与 L28 之间，即 `class TaskManager` 之前）加模块级挂钩：

```python
def _notify_terminal(task_id: str, status: str, *, name: str, error: str | None = None) -> None:
    """采集任务终态唯一通知出口；complete_task/fail_task 各调一次

    name 用任务类型标识（如 crypto_download）：TaskInfo 没有
    独立 name 字段，params 里的名字不可靠。
    """
    notify_task_event("collector_task", task_id, status, name=name or None, error=error)
```

3c. `complete_task` 内，`TaskBusiness.complete(task_id)` 的 try/except 块（L367-373）之后、WebSocket 推送 try 块（L375）之前插入（注意 complete_task 里 L378-380 有 WS 未连接的提前 `return True`，挂钩必须放在它之前）：

```python
        # 终态通知（WS 未连接的提前 return 在其后，不影响本挂钩）
        _notify_terminal(
            task_id, TASK_STATUS_SUCCEEDED, name=self._tasks[task_id].get("task_type", "")
        )
```

3d. `fail_task` 内，`TaskBusiness.fail(task_id, error_message)` 的 try/except 块（L433-439）之后、WebSocket 推送 try 块（L441）之前插入：

```python
        _notify_terminal(
            task_id,
            TASK_STATUS_FAILED,
            name=self._tasks[task_id].get("task_type", ""),
            error=error_message,
        )
```

- [x] **Step 4: 跑 collector 用例确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/test_domain_hooks.py::TestCollectorHook -v`
Expected: 3 passed。

- [x] **Step 5: backtest 埋点**

5a. [routes.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/backtest/routes.py) 顶部 L38（`from utils.rbac import is_guest_user` 之后）追加：

```python
from common.notifications.task_notices import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    notify_task_event,
)
```

5b. import 区结束（L54 `from .service import BacktestService` 之后）、`router` 定义之前加挂钩函数：

```python
def notify_backtest_result(task_id: str, result: dict, *, name: str) -> None:
    """回测结果 → 终态通知唯一出口

    status∈{success,completed} 发成功；stopped 是用户主动终止不发；
    其余一律按失败发（未知状态也报，避免静默丢通知）。
    """
    status = result.get("status")
    if status == "stopped":
        return
    if status in ("success", "completed"):
        notify_task_event("backtest", task_id, TASK_STATUS_SUCCEEDED, name=name or None)
    else:
        notify_task_event(
            "backtest",
            task_id,
            TASK_STATUS_FAILED,
            name=name or None,
            error=str(result.get("message") or "回测失败"),
        )
```

5c. `run_backtest_async` 闭包：`result = backtest_service.run_backtest(...)`（L359）与 `logger.info(f"[任务 {task_id}] 回测执行完成...")`（L361）之间插入两行：

```python
                    # 终态通知唯一出口：stopped 由挂钩内部静默
                    notify_backtest_result(
                        task_id, result, name=str(strategy_config_dict.get("strategy_name") or "")
                    )
```

5d. 同闭包 `except Exception as e:` 分支，`progress_tracker.fail_progress(...)`（L388）之后插入：

```python
                    notify_task_event(
                        "backtest",
                        task_id,
                        TASK_STATUS_FAILED,
                        name=str(strategy_config_dict.get("strategy_name") or ""),
                        error=f"回测执行发生异常: {e}",
                    )
```

- [x] **Step 6: 跑 backtest 用例确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/test_domain_hooks.py::TestBacktestHook -v`
Expected: 4 passed。

- [x] **Step 7: research 埋点**

7a. [loop.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/research/loop.py) 顶部 L40（`from utils.logger import ...` 之后）追加：

```python
from common.notifications.task_notices import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    notify_task_event,
)
```

7b. `class Budget` 之前（L58 前）加模块级挂钩：

```python
#: 研究会话内部状态 → 通知终态；cancel/pause 是用户主动操作，不映射不发
_RESEARCH_NOTIFY_STATUS = {"completed": TASK_STATUS_SUCCEEDED, "failed": TASK_STATUS_FAILED}


def _notify_session_terminal(
    session_id: int, name: str, status: str, *, error: str | None = None
) -> None:
    """研究会话终态通知唯一出口（_finish 的 CAS 写成功后调用）"""
    notify_status = _RESEARCH_NOTIFY_STATUS.get(status)
    if notify_status is None:
        return
    notify_task_event("research", str(session_id), notify_status, name=name or None, error=error)
```

7c. `_finish`（L322-331）整体替换为（CAS 失败提前 return、成功才挂通知）：

```python
    def _finish(self, status: str, *, error: str | None = None) -> None:
        with self._db() as db:
            row = self._session_row(db)
            if row.status in {"completed", "failed", "cancelled"}:
                return
            name = row.name
            try:
                service.set_session_status(db, row, status, error=error)
            except service.ResearchError:
                # 外部已按暂停/取消/延期改过状态（CAS 失败），不覆盖也不发通知
                logger.info(f"[研究] 会话 {self.session_id} 收尾状态被并发改写，跳过 {status}")
                return
            # CAS 写成功 = 本进程夺得终态，只在此发一次通知
            _notify_session_terminal(self.session_id, name, status, error=error)
```

- [x] **Step 8: 跑整套确认通过**

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS（Task 3/4 的 test_task_notices.py、test_task_hooks.py、test_inbox.py 不受影响）。

- [x] **Step 9: Commit**

```bash
git add backend/collector/utils/task_manager.py backend/backtest/routes.py backend/research/loop.py backend/tests/unit/notifications/test_domain_hooks.py
git commit -m "feat(notifications): 采集/回测/研究三域终态通知埋点"
```

### Task 6: 五域启动补偿扫描 + lifespan 挂载

**Files:**
- Modify: `backend/services/rl_task_runner.py`（Task 4 import 块追加 + 文件尾部补偿函数）
- Modify: `backend/factor/job_manager.py`（同上）
- Modify: `backend/collector/utils/task_manager.py`（L7 datetime + 模块级补偿函数）
- Modify: `backend/backtest/routes.py`（`notify_backtest_result` 之后加补偿函数）
- Modify: `backend/research/loop.py`（`_notify_session_terminal` 之后加补偿函数）
- Modify: `backend/core/lifespan.py`（L479 后挂载补偿 + L491 shutdown 解绑 Hub）
- Test: `backend/tests/unit/notifications/test_compensation.py`

**补偿契约（五域统一）**：各模块暴露 `compensate_interrupted_tasks() -> int`（research 为
`compensate_interrupted_sessions()`），返回收口数；内部「扫非终态行 → 翻转落库 → 逐行发
INTERRUPTED 通知」。差异：

| 域 | 扫描表 | 非终态条件 | 落库终态值 |
|---|---|---|---|
| rl_train / factor_job | `async_task_records` 影子表 | status ∈ (queued, running) | `interrupted` |
| collector_task | `tasks` | status ∈ (pending, running) | `failed`（值域无 interrupted，不新造状态） |
| backtest | `backtest_tasks` | status ∈ (pending, running) | `failed`（同上） |
| research | `research_sessions` | status=running 且心跳超 10 分钟 | `failed` |

research 用心跳阈值 `_HEARTBEAT_STALE_SECONDS = 600` 防多进程误杀：心跳由持有作业的进程
守护线程（factor/job_lease.py）刷新，新鲜心跳 = 其它进程正在跑，不动；pending 不动（无心跳线，
无法与其它进程排队区分）；paused/delayed 不动（用户主动态）。

- [x] **Step 1: 写失败测试 `tests/unit/notifications/test_compensation.py`**

```python
"""五域启动补偿扫描单测。

补偿函数把重启后残留的非终态任务统一收口为「已中断」并发 INTERRUPTED
通知。统一 monkeypatch 各模块命名空间里的 notify_task_event 与 session
工厂（use_db_session / get_db_session / _collector_db_session），用内存
SQLite 真跑扫描查询；不触任何真实业务库。
"""

import contextlib
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base
from collector.db.models import BacktestTask, Task
from common.notifications.inbox_models import AsyncTaskRecord
from research.models import ResearchSession


@pytest.fixture()
def comp_sessionmaker():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Task.__table__,
            BacktestTask.__table__,
            ResearchSession.__table__,
            AsyncTaskRecord.__table__,
        ],
    )
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield maker
    engine.dispose()


@contextlib.contextmanager
def _fake_db_session(maker):
    db = maker()
    try:
        yield db
    finally:
        db.close()


def _patch_notify(monkeypatch, target: str):
    calls = []

    def fake(task_type, task_id, status, *, name=None, error=None, extra=None):
        calls.append((task_type, task_id, status, name, error))

    monkeypatch.setattr(target, fake, raising=False)
    return calls


class TestShadowCompensation:
    """rl_train / factor_job：以 async_task_records 影子表为补偿依据"""

    @pytest.mark.parametrize(
        "module_path,task_type",
        [("services.rl_task_runner", "rl_train"), ("factor.job_manager", "factor_job")],
    )
    def test_interrupts_stale_rows(self, comp_sessionmaker, monkeypatch, module_path, task_type):
        import importlib

        mod = importlib.import_module(module_path)
        with comp_sessionmaker() as db:
            db.add_all(
                [
                    AsyncTaskRecord(task_type=task_type, task_id="a1", status="queued", name="A-1"),
                    AsyncTaskRecord(task_type=task_type, task_id="a2", status="running", name="A-2"),
                    AsyncTaskRecord(task_type=task_type, task_id="a3", status="succeeded", name="A-3"),
                    AsyncTaskRecord(task_type="other", task_id="x1", status="running", name="X"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, f"{module_path}.notify_task_event")
        monkeypatch.setattr(
            f"{module_path}.use_db_session", lambda: _fake_db_session(comp_sessionmaker), raising=False
        )

        assert mod.compensate_interrupted_tasks() == 2

        with comp_sessionmaker() as db:
            statuses = {r.task_id: r.status for r in db.query(AsyncTaskRecord).all()}
        assert statuses["a1"] == "interrupted"
        assert statuses["a2"] == "interrupted"
        assert statuses["a3"] == "succeeded"  # 已终态不重碰
        assert statuses["x1"] == "running"  # 其它域不误伤

        assert [(c[1], c[2]) for c in calls] == [("a1", "INTERRUPTED"), ("a2", "INTERRUPTED")]
        assert all(c[0] == task_type for c in calls)


class TestCollectorCompensation:
    def test_marks_stale_failed(self, comp_sessionmaker, monkeypatch):
        from collector.utils import task_manager

        with comp_sessionmaker() as db:
            db.add_all(
                [
                    Task(task_id="c1", task_type="crypto_download", status="pending", params="{}"),
                    Task(task_id="c2", task_type="crypto_download", status="running", params="{}"),
                    Task(task_id="c3", task_type="crypto_download", status="completed", params="{}"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, "collector.utils.task_manager.notify_task_event")
        monkeypatch.setattr(
            task_manager, "_collector_db_session", comp_sessionmaker, raising=False
        )

        assert task_manager.compensate_interrupted_tasks() == 2

        with comp_sessionmaker() as db:
            rows = {r.task_id: r.status for r in db.query(task_manager.Task).all()}
        assert rows == {"c1": "failed", "c2": "failed", "c3": "completed"}
        assert [(c[1], c[2]) for c in calls] == [("c1", "INTERRUPTED"), ("c2", "INTERRUPTED")]
        assert all(c[3] == "crypto_download" for c in calls)


class TestBacktestCompensation:
    def test_marks_stale_failed(self, comp_sessionmaker, monkeypatch):
        from backtest import routes as backtest_routes

        with comp_sessionmaker() as db:
            db.add_all(
                [
                    BacktestTask(id="b1", strategy_name="DualMA", backtest_config="{}", status="pending"),
                    BacktestTask(id="b2", strategy_name="DualMA", backtest_config="{}", status="running"),
                    BacktestTask(id="b3", strategy_name="DualMA", backtest_config="{}", status="completed"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, "backtest.routes.notify_task_event")
        monkeypatch.setattr(
            backtest_routes, "get_db_session", lambda: _fake_db_session(comp_sessionmaker)
        )

        assert backtest_routes.compensate_interrupted_tasks() == 2

        with comp_sessionmaker() as db:
            rows = {r.id: r.status for r in db.query(BacktestTask).all()}
        assert rows == {"b1": "failed", "b2": "failed", "b3": "completed"}
        assert [(c[1], c[2]) for c in calls] == [("b1", "INTERRUPTED"), ("b2", "INTERRUPTED")]
        assert all(c[3] == "DualMA" for c in calls)


class TestResearchCompensation:
    def test_stale_heartbeat_interrupted(self, comp_sessionmaker, monkeypatch):
        from research import loop as research_loop

        now = time.time()
        with comp_sessionmaker() as db:
            db.add_all(
                [
                    ResearchSession(owner_id="u1", name="跑一半", status="running", heartbeat_at=now - 3600),
                    ResearchSession(owner_id="u1", name="活跃中", status="running", heartbeat_at=now),
                    ResearchSession(owner_id="u1", name="已完成", status="completed"),
                    ResearchSession(owner_id="u1", name="排队中", status="pending"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, "research.loop.notify_task_event")
        monkeypatch.setattr(
            research_loop, "get_db_session", lambda: _fake_db_session(comp_sessionmaker)
        )

        assert research_loop.compensate_interrupted_sessions() == 1

        with comp_sessionmaker() as db:
            rows = {r.name: r.status for r in db.query(ResearchSession).all()}
        assert rows == {"跑一半": "failed", "活跃中": "running", "已完成": "completed", "排队中": "pending"}
        assert [(c[1], c[2]) for c in calls] == [("1", "INTERRUPTED")]
        assert calls[0][3] == "跑一半"

    def test_pending_without_heartbeat_untouched(self, comp_sessionmaker, monkeypatch):
        # pending 无心跳线：不误杀（多进程排队中无法区分），只处理 running+过期心跳
        from research import loop as research_loop

        with comp_sessionmaker() as db:
            db.add(ResearchSession(owner_id="u1", name="排队", status="pending"))
            db.commit()

        calls = _patch_notify(monkeypatch, "research.loop.notify_task_event")
        monkeypatch.setattr(
            research_loop, "get_db_session", lambda: _fake_db_session(comp_sessionmaker)
        )
        assert research_loop.compensate_interrupted_sessions() == 0
        assert calls == []


if __name__ == "__main__":
    raise SystemExit("请用 pytest 运行: uv run pytest tests/unit/notifications/test_compensation.py -v")
```

- [x] **Step 2: 跑测试确认失败（补偿函数均不存在）**

Run: `cd backend && uv run pytest tests/unit/notifications/test_compensation.py -v`
Expected: FAIL/ERROR — `AttributeError: module 'services.rl_task_runner' has no attribute 'compensate_interrupted_tasks'`（其余域同理）。

- [x] **Step 3: rl / factor 影子表补偿**

**3a. rl_task_runner.py**：Task 4 加的 `from common.notifications.task_notices import (...)` 元组内追加一行 `TASK_STATUS_INTERRUPTED,`（放 `TASK_STATUS_FAILED,` 之后，保持字母序），其下追加：

```python
from common.notifications.inbox_models import AsyncTaskRecord
from utils.db_session import use_db_session
```

文件尾部（`_report_terminal` 定义之后、模块级单例区之前）追加：

```python
def compensate_interrupted_tasks() -> int:
    """重启补偿：影子表残留 queued/running 的 RL 任务置 interrupted 并补发中断通知

    内存 registry 重启即空（见文件头 ponytail 注释），影子表是重启前任务
    存在的唯一事实源头（spec §4.2）。
    """
    try:
        with use_db_session() as db:
            rows = (
                db.query(AsyncTaskRecord)
                .filter(
                    AsyncTaskRecord.task_type == "rl_train",
                    AsyncTaskRecord.status.in_(("queued", "running")),
                )
                .all()
            )
            stale = [(r.task_id, r.name or "") for r in rows]
            for row in rows:
                row.status = "interrupted"
            db.commit()
    except Exception:
        logger.exception("[RL] 启动补偿扫描失败")
        return 0
    for task_id, name in stale:
        notify_task_event(
            "rl_train",
            task_id,
            TASK_STATUS_INTERRUPTED,
            name=name or None,
            error="服务重启，训练任务被中断",
        )
    return len(stale)
```

**3b. factor/job_manager.py**：同样在其 `from common.notifications.task_notices import (...)` 元组内追加 `TASK_STATUS_INTERRUPTED,`，其下追加同样的两行 import；文件尾部追加：

```python
def compensate_interrupted_tasks() -> int:
    """重启补偿：影子表残留 queued/running 的因子任务置 interrupted 并补发中断通知"""
    try:
        with use_db_session() as db:
            rows = (
                db.query(AsyncTaskRecord)
                .filter(
                    AsyncTaskRecord.task_type == "factor_job",
                    AsyncTaskRecord.status.in_(("queued", "running")),
                )
                .all()
            )
            stale = [(r.task_id, r.name or "") for r in rows]
            for row in rows:
                row.status = "interrupted"
            db.commit()
    except Exception:
        logger.exception("[因子] 启动补偿扫描失败")
        return 0
    for task_id, name in stale:
        notify_task_event(
            "factor_job",
            task_id,
            TASK_STATUS_INTERRUPTED,
            name=name or None,
            error="服务重启，因子计算任务被中断",
        )
    return len(stale)
```

- [x] **Step 4: 跑影子域用例确认通过**

Run: `cd backend && uv run pytest "tests/unit/notifications/test_compensation.py::TestShadowCompensation" -v`
Expected: 2 passed。

- [x] **Step 5: collector 补偿**

5a. [task_manager.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/collector/utils/task_manager.py) L7 `from datetime import datetime` 改为（补偿要写 aware 终态时间戳）：

```python
from datetime import UTC, datetime
```

5b. 文件尾部追加（`TaskManager` 类外、模块级单例之后）：

```python
def _collector_db_session():
    """采集任务库 session 工厂（补偿扫描用；测试注入内存库工厂）"""
    from collector.db.database import SessionLocal, init_database_config

    init_database_config()
    return SessionLocal()


def compensate_interrupted_tasks() -> int:
    """重启补偿：tasks 表残留 pending/running 的行置 failed 并补发中断通知

    采集链路无租约（单进程内存 dict 驱动），重启即中断。
    业务表没有 interrupted 状态值，落库置 failed 避免前端枚举失配；
    通知级别用 INTERRUPTED（warning，见 Hub 的 level 映射）。
    """
    try:
        db = _collector_db_session()
        try:
            rows = db.query(Task).filter(Task.status.in_(("pending", "running"))).all()
            stale = [(r.task_id, r.task_type) for r in rows]
            for row in rows:
                row.status = "failed"
                row.error_message = "服务重启，任务被中断"
                row.end_time = datetime.now(UTC)
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("[采集] 启动补偿扫描失败")
        return 0
    for task_id, task_type in stale:
        notify_task_event(
            "collector_task",
            task_id,
            TASK_STATUS_INTERRUPTED,
            name=task_type or None,
            error="服务重启，任务被中断",
        )
    return len(stale)
```

- [x] **Step 6: backtest 补偿**

[routes.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/backtest/routes.py) 中 `notify_backtest_result` 函数之后追加（`get_db_session` / `BacktestTask` / `datetime, UTC` / `logger` 顶部 import 均已有）：

```python
def compensate_interrupted_tasks() -> int:
    """重启补偿：backtest_tasks 残留 pending/running 的行置 failed 并补发中断通知

    回测跑在后台线程，进程重启即全部中断；status 值域无 interrupted，落库置 failed。
    """
    try:
        with get_db_session() as db:
            rows = db.query(BacktestTask).filter(BacktestTask.status.in_(("pending", "running"))).all()
            stale = [(r.id, r.strategy_name) for r in rows]
            for row in rows:
                row.status = "failed"
                row.completed_at = datetime.now(UTC)
            db.commit()
    except Exception:
        logger.exception("[回测] 启动补偿扫描失败")
        return 0
    for task_id, strategy_name in stale:
        notify_task_event(
            "backtest",
            task_id,
            TASK_STATUS_INTERRUPTED,
            name=strategy_name or None,
            error="服务重启，回测被中断",
        )
    return len(stale)
```

- [x] **Step 7: research 补偿**

[loop.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/research/loop.py) 中 `_notify_session_terminal` 之后追加（`time` / `get_db_session` / `ResearchSession` / `service` 均已 import）：

```python
#: 心跳超此秒数视为租约丢失（持有进程的守护线程 15s 刷一次，10 分钟余量充足）
_HEARTBEAT_STALE_SECONDS = 600.0


def compensate_interrupted_sessions() -> int:
    """重启补偿：running 且心跳超阈值的会话置 failed 并补发中断通知

    多进程部署下心跳新鲜 = 其它进程正在跑，不能动（防误杀）；
    pending 不动（从未开工、无心跳线，无法与其它进程排队区分）；
    paused/delayed 不动（用户主动态）。
    """
    now = time.time()
    sent = 0
    try:
        with get_db_session() as db:
            rows = (
                db.query(ResearchSession)
                .filter(
                    ResearchSession.status == "running",
                    ResearchSession.heartbeat_at.isnot(None),
                    ResearchSession.heartbeat_at < now - _HEARTBEAT_STALE_SECONDS,
                )
                .all()
            )
            for row in rows:
                try:
                    service.set_session_status(db, row, "failed", error="服务重启/租约丢失，研究会话被中断")
                except service.ResearchError:
                    # 补偿瞬间被其它进程/请求改了状态：CAS 落败即跳过，不覆盖
                    logger.info(f"[研究] 会话 {row.id} 补偿时状态已被改写，跳过")
                    continue
                notify_task_event(
                    "research",
                    str(row.id),
                    TASK_STATUS_INTERRUPTED,
                    name=row.name or None,
                    error="服务重启，研究会话被中断",
                )
                sent += 1
    except Exception:
        logger.exception("[研究] 启动补偿扫描失败")
        return sent
    return sent
```

- [x] **Step 8: lifespan 挂载（绑定事件循环 + 启动补偿 + 关闭解绑）**

8a. [lifespan.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/core/lifespan.py) 启动段 `shutdown_watchdog.arm()`（L479）之后、`yield` 之前插入（Hub 绑定必须早于任何任务域投递事件；补偿是同步 DB 扫描，丢线程池跑不阻塞启动）：

```python
    # 通知 Hub 绑定主事件循环：任务域在工作线程里调用 notify_task_event 时，
    # WS 推送经此调度回 asyncio 侧（Task 3 的 bind_event_loop 契约）
    from common.notifications import task_notices  # 局部 import：避免 lifespan 顶层拉起通知链路

    task_notices.bind_event_loop(asyncio.get_running_loop())

    def _run_task_compensations() -> None:
        # 函数内 import：五个任务域模块较重（引擎/采集栈），且 lifespan 顶层
        # import 会放大环引风险（routes → services → lifespan 的模块图不稳定）
        from backtest.routes import compensate_interrupted_tasks as _backtest_comp
        from collector.utils.task_manager import compensate_interrupted_tasks as _collector_comp
        from factor.job_manager import compensate_interrupted_tasks as _factor_comp
        from research.loop import compensate_interrupted_sessions as _research_comp
        from services.rl_task_runner import compensate_interrupted_tasks as _rl_comp

        for task_type, fn in (
            ("rl_train", _rl_comp),
            ("factor_job", _factor_comp),
            ("collector_task", _collector_comp),
            ("backtest", _backtest_comp),
            ("research", _research_comp),
        ):
            try:
                n = fn()
            except Exception:
                logger.exception(f"[启动补偿] {task_type} 扫描异常")
                continue
            if n:
                logger.info(f"[启动补偿] {task_type} 收口中断任务 {n} 个")

    await asyncio.to_thread(_run_task_compensations)
```

8b. 关闭段 `logger.info("========== 应用开始关闭 ==========")`（L491）之后插入：

```python
    # 解绑通知 Hub 事件循环：关闭后不再接受跨线程投递，未决投递自然排空
    from common.notifications import task_notices

    task_notices.bind_event_loop(None)
```

- [x] **Step 9: 跑全部补偿用例 + 全量通知回归**

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS（Task 3/4/5 的既有用例不受影响）。

- [x] **Step 10: Commit**

```bash
git add backend/services/rl_task_runner.py backend/factor/job_manager.py backend/collector/utils/task_manager.py backend/backtest/routes.py backend/research/loop.py backend/core/lifespan.py backend/tests/unit/notifications/test_compensation.py
git commit -m "feat(notifications): 五域启动补偿扫描与 lifespan 挂载"
```

### Task 7: 前端 —— taskRoutes 注册中心 + 收件箱点击跳转/单条已读 + 任务过滤 + toast 跳转

**契约回顾（上游已定，本任务照抄不改）：**
- 后端 `_to_dict` 返回 `id/title/content/level/source/read/processed/created_at`（详见 Task 2 inbox.py 代码块，无 metadata 字段）。
- WS 实时推送 `{type:'notification', data:{..., metadata:{task_type, task_id, status}}}`（Task 3 `_deliver` 落地，见 L1085 断言）。
- REST：`GET /notifications/inbox?limit&before_id&unread&task_type`、`POST /notifications/inbox/{id}/read`（Task 2 routes.py 落定）。
- 五任务域 key：`rl_train / factor_job / collector_task / backtest / research`，与后端 `TASK_TYPES` 对齐。
- 路由事实（`frontend/src/router/DynamicRouter.tsx` L82-112）：`/backtest`、`/backtest/detail/:backtestId`、`/model-hub?tab=train`（现成重定向目标，query 已被路由支持）、`/factor-analysis`、`/data-management`、`/research/:id`、`/notifications`。

**跳转兜底设计（收件箱 REST 行无 task_id 的必然结果）：**
- WS 行（有 metadata.task_id）→ 尽量跳详情页；
- REST 行（无 metadata）→ rl_train/factor_job/collector_task 跳列表页即可，research 跳 `/research`，backtest 跳 `/backtest`；
- 回测例外：失败无论有无 id 都回 `/backtest` 列表页（详情页缺产物视图，失败原因看列表页）。

**Files:**
- Create: `frontend/src/utils/taskRoutes.ts`
- Modify: `frontend/src/api/index.ts`（InboxNotificationItem 扩字段 + getInbox 过滤参数 + markInboxItemRead）
- Modify: `frontend/src/store/notificationStore.ts`（loadList 过滤参数 + markRead + 已读语义修正）
- Modify: `frontend/src/App.tsx`（NotificationBridge 透传 metadata + toast onClick 跳转）
- Modify: `frontend/src/components/NotificationInbox.tsx`（行点击 = 已读 + 跳转；未读视觉）
- Modify: `frontend/src/pages/notifications/InboxPage.tsx`（未读/已读 Segmented + 任务域 Select）
- Modify: `i18n/zh-CN.json`、`i18n/en-US.json`（文件在仓库根 `i18n/`，由 `frontend/src/i18n/config.ts` L9-10 引入）

前端无单测基础设施（项目铁则：验证 = `cd frontend && bun run build`），本任务的红绿循环 = TypeScript 类型检查：Step 2 扩 required 字段后 build 必红（App.tsx 构造点缺字段），Step 4 修复后转绿。

- [x] **Step 1: 创建 taskRoutes.ts**

创建 `frontend/src/utils/taskRoutes.ts`：

```ts
/**
 * 任务类型 → 前端详情页路径 注册中心
 *
 * 后端五类异步任务（source ∈ task_notices.TASK_TYPES）的终态通知点击后的跳转
 * 落点全部收敛在这里。设计约束（设计规格 §4.1/§7）：
 * - 收件箱 REST 列表不携带 task_id（InboxNotification 未扩列），只有 WS 实时
 *   推送的 metadata 里有 { task_type, task_id, status }。
 *   兜底链 = metadata.task_id 有则跳详情，无则跳列表页。
 * - 回测例外：失败详情页缺少产物视图，无论有无 id 都回列表页看失败原因。
 */

export interface TaskRouteCtx {
  /** 任务域内 uuid（WS metadata.task_id 可携带；REST 列表行恒为 null） */
  id: string | null;
  /** WS metadata 透传的扩展信息（backtest 的 status 等） */
  detail?: Record<string, unknown>;
}

type TaskRouteResolver = (ctx: TaskRouteCtx) => string;

/** key 与后端 task_notices.TASK_TYPES 五域对齐 */
const TASK_ROUTE_RESOLVERS: Record<string, TaskRouteResolver> = {
  backtest: ({ id, detail }) => {
    if (detail?.status === 'failed') return '/backtest';
    return id ? `/backtest/detail/${id}` : '/backtest';
  },
  rl_train: () => '/model-hub?tab=train',
  factor_job: () => '/factor-analysis',
  collector_task: () => '/data-management',
  research: ({ id }) => (id ? `/research/${id}` : '/research'),
};

/** source 是否任务类通知（点击跳转的适用范围） */
export const isTaskSource = (source: string): boolean => source in TASK_ROUTE_RESOLVERS;

/** 完整任务域列表（收件箱页任务过滤器选项顺序） */
export const TASK_SOURCES = Object.keys(TASK_ROUTE_RESOLVERS);

/**
 * 任务通知点击跳转路由；非任务类通知返回 null（行/浮层不跳转）。
 */
export function taskNotificationRoute(source: string, ctx: TaskRouteCtx): string | null {
  const resolver = TASK_ROUTE_RESOLVERS[source];
  return resolver ? resolver(ctx) : null;
}
```

- [x] **Step 2: 扩 api/index.ts 类型与接口，跑 build 确认红**

2a. `frontend/src/api/index.ts` L1077 附近的 `InboxNotificationItem` 整体替换为：

```ts
/** 站内收件箱条目（与后端 common/notifications/inbox.py::_to_dict 对齐；
 * metadata 仅 WS 实时推送携带（NotificationMessage.metadata 透传），REST 列表不返回 */
export interface InboxNotificationItem {
  id: number;
  title: string;
  content: string;
  level: string; // NotificationLevel 枚举字符串：info/success/warning/error/critical
  source: string; // NotificationCategory 或任务域：system/task/.../rl_train/factor_job/...
  created_at: string | null;
  // 迁移 48 逐行语义：read = read_at 非空；任务类首次读置 processed（已读即归档）
  read: boolean;
  processed: boolean;
  /** 任务终态元数据：{ task_type, task_id, status, name? }（仅 WS 推送） */
  metadata?: Record<string, unknown>;
}
```

2b. 同文件 `notificationApi.getInbox`（L1045 附近）签名替换为：

```ts
  getInbox: (params?: {
    limit?: number;
    before_id?: number;
    unread?: boolean;
    task_type?: string;
  }): Promise<{
    items: InboxNotificationItem[];
    unread_count: number;
    read_count: number;
    has_more: boolean;
  }> => {
    return apiRequest.get('/notifications/inbox', params);
  },
```

2c. `markInboxRead` 定义（L1057 附近）之后追加：

```ts
  /**
   * 单条已读（任务类通知首次已读同时置归档），返回更新后的条目；404 由拦截器抛出
   */
  markInboxItemRead: (id: number): Promise<InboxNotificationItem> => {
    return apiRequest.post(`/notifications/inbox/${id}/read`);
  },
```

Run: `cd frontend && bun run build`
Expected: FAIL，TS 报错指向 `App.tsx` NotificationBridge 的 `const item: InboxNotificationItem = {`（缺 `read` / `processed`）。这就是本任务的红灯。

- [x] **Step 3: notificationStore.ts 扩展（loadList 过滤参数、markRead、已读语义对齐）**

`frontend/src/store/notificationStore.ts` 修改四处：

3a. 接口 `loadList` 签名（L25）替换，并在其后追加 `markRead`：

```ts
  /** 拉取收件箱列表；beforeId 传游标（取更旧一页并追加），缺省为刷新第一页；
   * unread/taskType 为收件箱页过滤条件（翻页时调用方需原样带上，否则翻页换语义） */
  loadList: (opts?: {
    beforeId?: number;
    limit?: number;
    unread?: boolean;
    taskType?: string;
  }) => Promise<void>;
  /** 单条已读：调后端置 read_at（任务类同时归档），本地同步行状态与未读数 */
  markRead: (id: number) => Promise<void>;
```

3b. `loadList` 实现（L43-60）的 getInbox 调用替换为：

```ts
      const data = await notificationApi.getInbox({
        limit: opts?.limit ?? 20,
        before_id: beforeId,
        unread: opts?.unread,
        task_type: opts?.taskType,
      });
```

3c. `markAllRead` 实现（L62-65）替换（本地 items 的 read 标记同步翻成已读，避免列表行仍显示未读样式）：

```ts
  markAllRead: async () => {
    await notificationApi.markInboxRead();
    set((state) => ({
      unreadCount: 0,
      readCount: state.readCount + state.unreadCount,
      items: state.items.map((it) => ({ ...it, read: true })),
    }));
  },
```

3d. `removeItem` 实现（L67-77）替换（逐行 read_at 语义后直接读行的 read 标记；旧的「未读必为前缀、按 idx 比较」假设迁移 48 起不再成立）：

```ts
  removeItem: async (id) => {
    const state = get();
    const target = state.items.find((it) => it.id === id);
    const { unread_count } = await notificationApi.deleteInboxItem(id);
    set((s) => ({
      items: s.items.filter((it) => it.id !== id),
      unreadCount: unread_count,
      readCount: Math.max(state.readCount + (target?.read ? -1 : 0), 0),
    }));
  },
```

3e. `bumpUnread` 实现（L84-90）之后追加：

```ts
  markRead: async (id) => {
    const updated = await notificationApi.markInboxItemRead(id);
    set((state) => {
      const target = state.items.find((it) => it.id === id);
      const wasUnread = !!target && !target.read;
      return {
        items: state.items.map((it) =>
          it.id === id ? { ...it, read: updated.read, processed: updated.processed } : it,
        ),
        unreadCount: Math.max(state.unreadCount - (wasUnread ? 1 : 0), 0),
        readCount: state.readCount + (wasUnread ? 1 : 0),
      };
    });
  },
```

Run: `cd frontend && bun run build`
Expected: 仍 FAIL（红灯未修复，报错仍在 App.tsx——预期，Step 4 修）。

- [x] **Step 4: App.tsx —— NotificationBridge 透传 metadata + toast 点击跳转**

`frontend/src/App.tsx`：

4a. import 区 L9 替换：

```ts
import { BrowserRouter, useNavigate } from 'react-router-dom';
```

4b. L19 之后追加一行：

```ts
import { taskNotificationRoute } from './utils/taskRoutes';
```

4c. `NotificationBridge` 函数整体替换（L198-242）：

```tsx
function NotificationBridge() {
  const { notification } = AntdApp.useApp();
  const navigate = useNavigate();
  const bumpUnread = useNotificationStore((s) => s.bumpUnread);

  useEffect(() => {
    const handler = (data: unknown) => {
      const payload = data as
        | {
            title?: string;
            content?: string;
            level?: string;
            source?: string;
            created_at?: string;
            metadata?: Record<string, unknown>;
          }
        | undefined;
      if (!payload?.title) return;

      const item: InboxNotificationItem = {
        // ponytail: ws 推送无 id，用负时间戳做临时 key 避免与真实 id 冲突；刷新列表时以服务端为准
        id: -Date.now(),
        title: payload.title,
        content: payload.content ?? '',
        level: payload.level ?? 'info',
        source: payload.source ?? 'system',
        created_at: payload.created_at ?? null,
        read: false,
        processed: false,
        metadata: payload.metadata,
      };
      bumpUnread(item);

      // 任务类通知点击浮层直达详情页（兜底逻辑见 taskRoutes.ts 头注释）
      const route = taskNotificationRoute(payload.source ?? '', {
        id: typeof payload.metadata?.task_id === 'string' ? payload.metadata.task_id : null,
        detail: payload.metadata,
      });

      // 浮层按 level 分级：info/success 自动关，error/critical 常驻需手动关
      const byLevel: Record<string, (cfg: { message: string; description?: string; duration?: number; onClick?: () => void }) => void> = {
        info: notification.info,
        success: notification.success,
        warning: notification.warning,
        error: notification.error,
        critical: notification.error,
      };
      const show = byLevel[payload.level ?? 'info'] ?? notification.info;
      show({
        message: payload.title,
        description: payload.content || undefined,
        duration: payload.level === 'error' || payload.level === 'critical' ? 0 : 4.5,
        ...(route ? { onClick: () => navigate(route) } : {}),
      });
    };

    // 消息结构 {type:'notification', data:{...}}，wsService 对未知 type 走 fallback 分发
    wsService.on('notification', handler);
    return () => wsService.off('notification', handler);
  }, [notification, bumpUnread, navigate]);

  return null;
}
```

Run: `cd frontend && bun run build`
Expected: PASS（红灯转绿：read/processed 构造点补齐，metadata 仅可选透传）。

- [x] **Step 5: NotificationInbox.tsx —— 行点击已读+跳转、未读视觉**

`frontend/src/components/NotificationInbox.tsx`：

5a. import 区（L11 后）追加：

```ts
import { useNotificationStore } from '@/store/notificationStore';
```

（若 STORE 已在文件 import 则跳过；当前 NotificationInbox 团队契约是 `@/store/notificationStore` 别名路径。）

再用 `taskNotificationRoute` 与 `useNavigate`：

```ts
import { taskNotificationRoute } from '@/utils/taskRoutes';
```

并在文件既有的 `react-router-dom` import 行确认含 `useNavigate`（`InboxItemRow` 新增的 `navigate` 依赖它；若该 import 行在 `InboxItemRow` 同文件内已存在则直接复用）：

```ts
import { useNavigate } from 'react-router-dom';
```

5b. `InboxItemRow`（L34-64）整体替换：

```tsx
/** 列表行：色点 + 标题（相对/绝对时间）。任务类通知点击 = 单条已读 + 跳转详情/列表页 */
export function InboxItemRow({ item }: { item: InboxNotificationItem }) {
  const navigate = useNavigate();
  const markRead = useNotificationStore((s) => s.markRead);

  const handleClick = () => {
    // 已读失败不影响跳转（后端幂等，下次点击会再置）
    if (!item.read) void markRead(item.id).catch(() => {});
    const route = taskNotificationRoute(item.source, {
      id: typeof item.metadata?.task_id === 'string' ? item.metadata.task_id : null,
      detail: item.metadata,
    });
    if (route) navigate(route);
  };

  return (
    <div
      className="flex cursor-pointer items-start gap-2 overflow-hidden"
      onClick={handleClick}
    >
      <span
        className="mt-[7px] size-1.5 shrink-0 rounded-full"
        style={{ background: LEVEL_COLORS[item.level] ?? LEVEL_COLORS.info }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <Typography.Text
            ellipsis
            className={`text-[13px] leading-[20px] ${item.read ? 'text-foreground/60' : 'font-medium'}`}
          >
            {item.title}
          </Typography.Text>
          <Typography.Text type="secondary" className="shrink-0 text-[11px] leading-[20px]">
            {item.created_at
              ? dayjs(item.created_at).format('MM-DD HH:mm')
              : ''}
          </Typography.Text>
        </div>
        {item.content && (
          <Typography.Paragraph
            ellipsis={{ rows: 2, tooltip: item.content }}
            type="secondary"
            className="!mb-0 !text-[12px] !leading-[18px]"
          >
            {item.content}
          </Typography.Paragraph>
        )}
      </div>
    </div>
  );
}
```

（`useNotificationStore` 若因 5a 注释判断已存在则保持单条 import；文件顶部原本未引入该 store，当前由 NotificationPanel 从 store 拿数据，此处保留一行即可，不要重复 import。）

Run: 不跑（下一 Step 合并验证）。

- [x] **Step 6: InboxPage.tsx —— 读写过滤 Segmented + 任务域 Select**

`frontend/src/pages/notifications/InboxPage.tsx`：

6a. import 区：antd 行加 `Flex, Segmented, Select`（L12 的 antd import 改为）：

```tsx
import { Badge, Button, Card, Empty, Flex, Popconfirm, Segmented, Select, Space, Spin, theme, Typography } from 'antd';
```

并追加（`useCallback` 与 `useState` 均来自 react，6b 的 `reload` 依赖 `useCallback`）：

```tsx
import { useCallback, useState } from 'react';
import { TASK_SOURCES } from '@/utils/taskRoutes';
```

（`useEffect` 已有 import，无需重复引入。）

6b. 组件内（L24 解构 store 之后）追加过滤态与 reload：

```tsx
  // 过滤态是页面局部状态（不进 store：预览面板始终看全量，不受页面过滤影响）
  const [readFilter, setReadFilter] = useState<'all' | 'unread' | 'read'>('all');
  const [taskType, setTaskType] = useState<string | null>(null);

  const listParams = () => ({
    unread: readFilter === 'all' ? undefined : readFilter === 'unread',
    taskType: taskType ?? undefined,
  });

  const reload = useCallback(() => {
    void loadList({ limit: PAGE_SIZE, ...listParams() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadList, readFilter, taskType]);

  useEffect(() => {
    reload();
  }, [reload]);
```

（原挂载 `useEffect` L27-31 删除，被上面的过滤态驱动 reload 取代。）

`loadOlder`（L33-36）替换：

```tsx
  const loadOlder = () => {
    const last = items[items.length - 1];
    if (last) void loadList({ limit: PAGE_SIZE, beforeId: last.id, ...listParams() });
  };
```

6c. Card 内、`<Spin>` 之前插入过滤器行：

```tsx
        {/* 读写态 + 任务域过滤：垂直间距用 antd Flex（项目铁则禁 Tailwind space-y-*） */}
        <Flex vertical gap={12} className="mb-3">
          <Flex gap={12} wrap>
            <Segmented
              value={readFilter}
              onChange={(v) => setReadFilter(v as 'all' | 'unread' | 'read')}
              options={[
                { label: t('filter_all'), value: 'all' },
                { label: t('filter_unread'), value: 'unread' },
                { label: t('filter_read'), value: 'read' },
              ]}
            />
            <Select
              allowClear
              placeholder={t('task_filter_placeholder')}
              value={taskType}
              onChange={(v) => setTaskType(v ?? null)}
              style={{ minWidth: 140 }}
              options={TASK_SOURCES.map((s) => ({ value: s, label: t(`task_type_${s}`) }))}
            />
          </Flex>
        </Flex>
```

Run: 不跑（下一 Step 合并验证）。

- [x] **Step 7: i18n 追加文案 key**

`i18n/zh-CN.json`：`"level_error": "错误"` 行（L3636）之后追加（注意其为文件最后一个 key，需补逗号）：

```json
  "level_error": "错误",
  "filter_all": "全部",
  "filter_unread": "未读",
  "filter_read": "已读",
  "task_filter_placeholder": "全部任务类型",
  "task_type_rl_train": "RL 训练",
  "task_type_factor_job": "因子计算",
  "task_type_collector_task": "数据采集",
  "task_type_backtest": "回测",
  "task_type_research": "研究"
```

`i18n/en-US.json` 同位置（L3624 附近 `"message_center"` 文案块至文件尾，`level_error` 为最后 key）同样追加：

```json
  "level_error": "Error",
  "filter_all": "All",
  "filter_unread": "Unread",
  "filter_read": "Read",
  "task_filter_placeholder": "All task types",
  "task_type_rl_train": "RL training",
  "task_type_factor_job": "Factor job",
  "task_type_collector_task": "Data collection",
  "task_type_backtest": "Backtest",
  "task_type_research": "Research"
```

两个文件都是纯 key 追加进最外层对象末尾，不引入嵌套结构。

- [x] **Step 8: 构建终验 + 提交**

Run: `cd frontend && bun run build`
Expected: PASS，无 TS 报错、vite 产物生成成功。

Run: `git add frontend/src/utils/taskRoutes.ts frontend/src/api/index.ts frontend/src/store/notificationStore.ts frontend/src/App.tsx frontend/src/components/NotificationInbox.tsx frontend/src/pages/notifications/InboxPage.tsx i18n/zh-CN.json i18n/en-US.json && git commit -m "feat(notifications): 收件箱点击跳转/单条已读/任务过滤与 taskRoutes 注册中心"`

**完成标志：** 收件箱行（面板+页面）点击任务通知完成单条已读并跳转对应任务页；toast 点击同样跳转；收件箱页可用未读/已读与任务域过滤；`bun run build` 通过。

### Task 8: docs/testing 验证项同步 + 全量终验

**Files:**
- Modify: `docs/testing/pages/notifications.md`（前置区接口清单 + 验证表追加 N12-N16 + 历史雷区 2 条）
- Modify: `docs/testing/MANIFEST.md`（L18 行备注补种子说明；`/notifications` 已登记，无新增路由）

本任务不改动任何前后端代码，是对本次功能的验收文档同步（项目铁则：功能变更必须同一变更内更新 docs/testing）+ 全量回归守门。

- [x] **Step 1: notifications.md 前置区更新**

`docs/testing/pages/notifications.md` L5-6 两行替换为：

```markdown
- 组件：`frontend/src/pages/notifications/InboxPage.tsx`；预览面板：`frontend/src/components/NotificationInbox.tsx`；任务跳转注册：`frontend/src/utils/taskRoutes.ts`
- 接口：`GET /api/v1/notifications/inbox?limit=&before_id=&unread=&task_type=`、`POST /api/v1/notifications/inbox/{id}/read`（单条已读，任务类首次已读同时归档）、`POST /api/v1/notifications/inbox/read-all`、`DELETE /api/v1/notifications/inbox/read`、`DELETE /api/v1/notifications/inbox/{id}`
- 种子：默认数据目录**无通知**，L1 走空态分支；要验列表/已读/删除需先产生通知（运行任一策略或回测产生站内通知，或沿用已有通知的旧数据目录），在报告中注明种子来源；验任务类通知（N13/N14/N16）用任务终态产生：跑一次回测 / RL 训练 / 因子计算 / 数据采集 / 研究会话至终态，五域 key 为 `backtest` / `rl_train` / `factor_job` / `collector_task` / `research`
```

- [x] **Step 2: 验证表追加 N12-N16**

在 N11 行（L23）之后追加：

```markdown
| N12 | 点读写过滤 Segmented（`全部`/`未读`/`已读`） | 每次切换发出 `GET /api/v1/notifications/inbox` 且带 `unread=true` 或 `unread=false`；返回条目与所选态一致（未读项标题加粗、已读项灰显）；切回`全部`不带 `unread` 参数 | L2（需种子） |
| N13 | 任务域 Select 选`回测` | 请求带 `task_type=backtest`；列表仅剩 source 为 backtest 的条目；清空选择（allowClear）后恢复全量 | L2（需任务终态种子） |
| N14 | 点一条**任务类**通知行 | 该条未读时先发 `POST /api/v1/notifications/inbox/{id}/read` 返回 200 且行内样式转已读；随后跳转与域一致：RL 训练→`/model-hub?tab=train`、因子→`/factor-analysis`、采集→`/data-management`、研究→`/research`（WS 行带 task_id 时→`/research/{id}`）、回测→`/backtest`（WS 行成功态带 task_id 时→`/backtest/detail/{id}`）；非任务类行点击不跳转 | L2（需任务终态种子） |
| N15 | WS 推送送达时点浮动 toast | toast 可点击并按 N14 同表规则跳转；`source=system` 等非任务 toast 点击不跳转常背景 | 按需（需 WS 推送 + 业务事件触发） |
| N16 | 服务重启后的中断补偿 | 重启前人为留下中断任务（如 rl_train / factor_job 的 `async_task_records` 行留 queued、collector `tasks` 行留 running、`backtest_tasks` 行留 pending、research 会话留 running），重启后日志出现`任务通知补偿扫描`行，各域残留行被置终态，收件箱出现对应`已中断`/`失败`通知 | 按需（需重启场景） |
```

- [x] **Step 3: 历史雷区追加 2 条**

`docs/testing/pages/notifications.md` 历史雷区列表末尾（L30 之后）追加：

```markdown
- **收件箱 REST 行不带 task_id**：task_id 只在 WS 实时推送的 `metadata` 里（后端 InboxNotification 未扩列）。REST 列表行点击跳的是兜底列表页（回测→`/backtest`、研究→`/research`），不要断言跳详情页；只有 WS 实时插入的行才可能跳 `/backtest/detail/{id}`、`/research/{id}`。N14 断言按行来源区分
- **跳转落点由 taskRoutes.ts 统一注册**：任务域 → 路径映射在 `frontend/src/utils/taskRoutes.ts`，五域 key 与后端 `task_notices.TASK_TYPES` 必须一致；新增任务域先加 resolver，漏配时点击已读但不跳转（静默，无报错）
```

- [x] **Step 4: MANIFEST.md 备注更新**

`docs/testing/MANIFEST.md` L18 行替换为：

```markdown
| `/notifications` | 消息中心 | `pages/notifications.md` | ✅ | L1+L2 | token 注入；非空态种子靠业务事件/任务终态；任务过滤与跳转见 N12-N15 |
```

- [x] **Step 5: spec 实施注记回写（评审后简化决议落档）**

spec 是已评审的上游文档，本次实施对它做了 5 处已获批的简化/调整（详见本计划头部 Architecture 与 Task 2 的简化注释）。在 `docs/superpowers/specs/2026-11-20-notification-center-design.md` 顶部 `状态：已评审通过（方案 A：任务终态埋点 + 统一通知 Hub）` 行之后追加一段注记，防止后来者按 spec 旧形态找列/签名：

```markdown
> **实施注记（2026-11-20，以实施计划为准）**：实施时做了以下简化与调整：
> 1. §4.1 的 `task_type/task_id/detail` 三列不上——`source` 列直接承载任务域字符串；task_id/detail 仅经 WS `NotificationMessage.metadata` 携带（REST 收件箱行无 task_id，前端跳转用 source 映射 + metadata 兜底）。
> 2. §5.3 的 `pending` 过滤参数不实现——`processed_at` 仅任务类使用且已读即归档，收件箱页过滤为 `全部/未读/已读`。
> 3. §5.1 签名定稿为 `notify_task_event(task_type, task_id, status, *, name=None, error=None, extra=None)`，`status` 用大写字符串常量（`SUCCEEDED/FAILED/INTERRUPTED`），title 由 Hub 模板生成（`{label}任务{状态}`），不由调用方传入；任务域 key 定稿为 `rl_train/factor_job/collector_task/backtest/research`。
> 4. §4.2 影子表定名 `async_task_records`（states 小写 queued/running/succeeded/failed/interrupted），仅 rl_train/factor_job 两域写入。
> 5. §5.2 的 `compensate_interrupted_tasks()` 返回 `int`（补偿通知由各域函数内部经 Hub 发出），lifespan 不再统一代发。
> 实施细节与验收见 `docs/superpowers/plans/2026-11-20-notification-center.md`。
```

- [x] **Step 6: 覆盖率守门 + 后端全量回归**

Run: `node docs/testing/check-coverage.mjs`（仓库根执行）
Expected: 全绿（`/notifications` 已登记，无漏登路由）

Run: `cd backend && uv run pytest tests/unit/notifications/ -q`
Expected: 全部 PASS（test_inbox / test_task_notices / test_notification_routes / test_domain_hooks / test_compensation 共 5 个文件）

Run: `cd frontend && bun run build`
Expected: PASS（发布前例行确认；Task 8 全程只改 docs，若 Task 7 已通过可跳过）

- [x] **Step 7: 提交**

Run: `git add docs/testing/pages/notifications.md docs/testing/MANIFEST.md docs/superpowers/specs/2026-11-20-notification-center-design.md && git commit -m "docs(testing): 消息中心任务通知/过滤/跳转验证项、补偿扫描场景与 spec 实施注记"`

**完成标志：** check-coverage 全绿、notifications 全量 pytest 全绿、docs 提交完成。整个计划（Task 1-8）至此全部完成。

<!-- APPEND-HERE -->

