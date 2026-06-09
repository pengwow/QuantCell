"""
Share CRUD 单元测试

覆盖：
- 基础 CRUD：create/get/list/revoke
- 一次性/过期/max_views 状态判断
- 远端字段保留（remote_id/short_url/remote_status/remote_error）
"""
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')


def test_create_share_token_basic(db_session, sample_worker):
    """基础创建：明文 token 返回 1 次，DB 中存的是 hash"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="user-1",
        expires_in_seconds=None,
        one_time=False,
    )
    assert share.id > 0
    assert isinstance(plain, str) and len(plain) >= 32
    # 数据库存的是 hash，不是明文
    assert share.token_hash != plain
    assert share.token_prefix == plain[:8]
    assert share.worker_id == sample_worker.id
    assert share.created_by == "user-1"
    assert share.one_time is False
    assert share.view_count == 0
    assert share.expires_at is None
    assert share.revoked_at is None


def test_create_share_token_with_expires(db_session, sample_worker):
    """expires_in_seconds 应正确转换为 expires_at"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="user-1",
        expires_in_seconds=3600,
        one_time=False,
    )
    assert share.expires_at is not None
    # 误差应在 5s 以内
    delta = (share.expires_at - datetime.now()).total_seconds()
    assert 3595 <= delta <= 3605


def test_create_share_token_one_time(db_session, sample_worker):
    """一次性 token 创建时 view_count 为 0"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by=None,
        expires_in_seconds=None,
        one_time=True,
    )
    assert share.one_time is True
    assert share.is_one_time_consumed() is False
    # 模拟一次访问后 view_count = 1
    share.view_count = 1
    assert share.is_one_time_consumed() is True


def test_get_share_by_token(db_session, sample_worker):
    """明文 token 应能查到"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="user-1",
        expires_in_seconds=None,
        one_time=False,
    )
    found = crud.get_share_by_token(db_session, plain)
    assert found is not None
    assert found.id == share.id


def test_get_share_by_invalid_token(db_session):
    """无效 token 返回 None"""
    from share import crud

    assert crud.get_share_by_token(db_session, "invalid-token") is None
    assert crud.get_share_by_token(db_session, "") is None


def test_revoke_share(db_session, sample_worker):
    """撤销后 is_active 返回 False"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="user-1",
        expires_in_seconds=None,
        one_time=False,
    )
    assert share.is_active(datetime.now()) is True
    crud.revoke_share(db_session, share)
    assert share.is_revoked() is True
    assert share.is_active(datetime.now()) is False


def test_revoke_share_idempotent(db_session, sample_worker):
    """重复撤销不应报错"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="user-1",
        expires_in_seconds=None,
        one_time=False,
    )
    crud.revoke_share(db_session, share)
    first_revoked_at = share.revoked_at
    crud.revoke_share(db_session, share)
    assert share.revoked_at == first_revoked_at


def test_list_shares_by_worker(db_session, sample_worker):
    """列出该 worker 的所有 share token"""
    from share import crud

    crud.create_share_token(db_session, sample_worker.id, "u1", None, False)
    crud.create_share_token(db_session, sample_worker.id, "u1", None, True)
    crud.create_share_token(db_session, sample_worker.id, "u2", 3600, False)

    shares = crud.list_shares_by_worker(db_session, sample_worker.id)
    assert len(shares) == 3
    # 按 created_at 倒序
    assert shares[0].created_at >= shares[-1].created_at


def test_token_hash_uniqueness(db_session, sample_worker):
    """不同 token 的 hash 必须不同"""
    from share import crud

    _, plain1 = crud.create_share_token(db_session, sample_worker.id, "u1", None, False)
    _, plain2 = crud.create_share_token(db_session, sample_worker.id, "u1", None, False)
    assert plain1 != plain2
    s1 = crud.get_share_by_token(db_session, plain1)
    s2 = crud.get_share_by_token(db_session, plain2)
    assert s1.id != s2.id


def test_is_expired(db_session, sample_worker):
    """过期 token 应被识别"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=3600,
        one_time=False,
    )
    # 篡改 expires_at 模拟过期
    share.expires_at = datetime.now() - timedelta(seconds=1)
    assert share.is_expired(datetime.now()) is True
    assert share.is_active(datetime.now()) is False


def test_max_views_limit(db_session, sample_worker):
    """达到 max_views 后 token 不再 active"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
        max_views=2,
    )
    share.view_count = 2
    assert share.has_reached_max_views() is True
    assert share.is_active(datetime.now()) is False


def test_remote_fields_persist(db_session, sample_worker):
    """远端相关字段（remote_id/short_url/remote_status/remote_error）持久化"""
    from share import crud

    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )
    share.remote_id = "r-123"
    share.short_url = "https://share.quantcell.top/abc"
    share.remote_status = "UPLOADED"
    share.remote_error = None
    db_session.add(share)
    db_session.commit()
    db_session.refresh(share)

    assert share.remote_id == "r-123"
    assert share.short_url == "https://share.quantcell.top/abc"
    assert share.remote_status == "UPLOADED"
    assert share.remote_error is None
