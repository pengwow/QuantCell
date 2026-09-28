# 修改密码接口单元测试
# 策略：mock 数据库会话，直接调用路由函数，覆盖旧密码校验/新密码规则/哈希落库
# HTTP 层的 JWT 认证复用 get_current_user，已由 tests/integration/api/test_auth.py 覆盖

import pytest
from fastapi import HTTPException

from settings.routes import change_password, hash_password, verify_password


class _FakeUser:
    """User 模型的鸭子类型替身：避免实例化真实模型触发全量 mapper 配置"""

    def __init__(self):
        self.id = 1
        self.username = "alice"
        self.nickname = "Alice"
        self.is_active = True
        self.password_hash = hash_password("old-pass-123")


class _FakeQuery:
    """最小可用的 SQLAlchemy Query 替身：filter_by 后 first 返回预置用户"""

    def __init__(self, user: _FakeUser | None):
        self._user = user

    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return self._user


class _FakeDB:
    """记录 commit/rollback/close 调用的会话替身"""

    def __init__(self, user: _FakeUser | None):
        self._user = user
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, _model):
        return _FakeQuery(self._user)

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        pass

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_user() -> _FakeUser:
    return _FakeUser()


@pytest.fixture
def patched_db(mocker, fake_user):
    """patch 掉数据库初始化与会话工厂，返回 (fake_db, user)"""
    mocker.patch("collector.db.database.init_database_config")
    fake_db = _FakeDB(fake_user)
    session_factory = mocker.patch("collector.db.database.SessionLocal", return_value=fake_db)
    return fake_db, session_factory


CURRENT_USER = {"user_id": "1", "sub": "1", "user_name": "alice", "role": "user"}


def test_change_password_success(patched_db, fake_user):
    """旧密码正确：新哈希落库、commit 被调用，且新密码可验证、旧密码失效"""
    fake_db, _ = patched_db
    original_hash = fake_user.password_hash

    resp = change_password(
        body={"old_password": "old-pass-123", "new_password": "new-pass-456"},
        current_user=CURRENT_USER,
    )

    assert resp.code == 0
    assert fake_db.committed is True
    assert fake_db.closed is True
    # 哈希确实被替换（不是覆盖成同一个值）
    assert fake_user.password_hash != original_hash
    # 等价于"可用新密码登录"：新密码校验通过，旧密码已失效
    assert verify_password("new-pass-456", fake_user.password_hash) is True
    assert verify_password("old-pass-123", fake_user.password_hash) is False


def test_change_password_wrong_old_password(patched_db, fake_user):
    """旧密码错误：返回 400，不写库"""
    fake_db, _ = patched_db
    original_hash = fake_user.password_hash

    with pytest.raises(HTTPException) as exc_info:
        change_password(
            body={"old_password": "wrong-old-pass", "new_password": "new-pass-456"},
            current_user=CURRENT_USER,
        )

    assert exc_info.value.status_code == 400
    assert "旧密码不正确" in exc_info.value.detail
    assert fake_db.committed is False
    assert fake_user.password_hash == original_hash


def test_change_password_too_short(patched_db, fake_user):
    """新密码不足 6 位：返回 400，不触库"""
    _fake_db, session_factory = patched_db

    with pytest.raises(HTTPException) as exc_info:
        change_password(
            body={"old_password": "old-pass-123", "new_password": "123"},
            current_user=CURRENT_USER,
        )

    assert exc_info.value.status_code == 400
    assert "6 个字符" in exc_info.value.detail
    # 参数校验在打开数据库会话之前，会话工厂不应被调用
    session_factory.assert_not_called()


def test_change_password_same_as_old(patched_db):
    """新旧密码相同：返回 400"""
    with pytest.raises(HTTPException) as exc_info:
        change_password(
            body={"old_password": "old-pass-123", "new_password": "old-pass-123"},
            current_user=CURRENT_USER,
        )

    assert exc_info.value.status_code == 400
    assert "不能与旧密码相同" in exc_info.value.detail


def test_change_password_empty_fields(patched_db):
    """任一字段为空：返回 400"""
    for body in (
        {"old_password": "", "new_password": "new-pass-456"},
        {"old_password": "old-pass-123", "new_password": ""},
        {},
    ):
        with pytest.raises(HTTPException) as exc_info:
            change_password(body=body, current_user=CURRENT_USER)
        assert exc_info.value.status_code == 400
        assert "不能为空" in exc_info.value.detail


def test_change_password_user_not_found(mocker):
    """JWT 中的用户在 users 表不存在（或被禁用）：返回 404"""
    mocker.patch("collector.db.database.init_database_config")
    fake_db = _FakeDB(user=None)
    mocker.patch("collector.db.database.SessionLocal", return_value=fake_db)

    with pytest.raises(HTTPException) as exc_info:
        change_password(
            body={"old_password": "old-pass-123", "new_password": "new-pass-456"},
            current_user=CURRENT_USER,
        )

    assert exc_info.value.status_code == 404
    assert "不存在或已被禁用" in exc_info.value.detail
    assert fake_db.closed is True


def test_change_password_missing_user_id(patched_db):
    """登录态缺少用户标识（异常 JWT）：返回 401，不触库"""
    _fake_db, session_factory = patched_db

    with pytest.raises(HTTPException) as exc_info:
        change_password(
            body={"old_password": "old-pass-123", "new_password": "new-pass-456"},
            current_user={"role": "user"},
        )

    assert exc_info.value.status_code == 401
    session_factory.assert_not_called()
