"""
Share CRUD 单元测试
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


def test_record_view_increments_count(db_session, sample_worker):
    """record_view 后 view_count +1 且创建 ShareView"""
    from share import crud
    from share.models import ShareView

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )
    crud.record_view(db_session, share, "1.2.3.4", "test-agent", success=True)
    assert share.view_count == 1

    views = db_session.query(ShareView).filter(ShareView.token_id == share.id).all()
    assert len(views) == 1
    assert views[0].ip == "1.2.3.4"
    assert views[0].user_agent == "test-agent"


def test_record_view_dedup_same_ip_same_day(db_session, sample_worker):
    """同一 IP 当天重复访问（含刷新）只计 1 次，但审计日志每次都记"""
    from share import crud
    from share.models import ShareView

    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )

    # 第一次访问
    counted_1 = crud.record_view(db_session, share, "1.2.3.4", "ua-1", success=True)
    assert counted_1 is True
    assert share.view_count == 1

    # 同一 IP 当天第二次访问（刷新页面）—— 不应计数
    counted_2 = crud.record_view(db_session, share, "1.2.3.4", "ua-1", success=True)
    assert counted_2 is False
    assert share.view_count == 1

    # 同一 IP 当天第三次访问 —— 仍不应计数
    counted_3 = crud.record_view(db_session, share, "1.2.3.4", "ua-1", success=True)
    assert counted_3 is False
    assert share.view_count == 1

    # 审计日志每次都应记录
    views = db_session.query(ShareView).filter(ShareView.token_id == share.id).all()
    assert len(views) == 3


def test_record_view_different_ips_same_day(db_session, sample_worker):
    """不同 IP 在同一天访问各算一次"""
    from share import crud

    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )

    crud.record_view(db_session, share, "1.1.1.1", "ua", success=True)
    crud.record_view(db_session, share, "2.2.2.2", "ua", success=True)
    crud.record_view(db_session, share, "3.3.3.3", "ua", success=True)
    assert share.view_count == 3

    # 再次访问任一 IP 不应再计数
    crud.record_view(db_session, share, "1.1.1.1", "ua", success=True)
    crud.record_view(db_session, share, "2.2.2.2", "ua", success=True)
    assert share.view_count == 3


def test_record_view_dedup_cross_day(db_session, sample_worker):
    """跨天后同一 IP 访问应再次计数"""
    from datetime import timedelta
    from share import crud
    from share.models import ShareView

    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )

    # 第一天访问
    crud.record_view(db_session, share, "1.2.3.4", "ua", success=True)
    assert share.view_count == 1

    # 把历史的访问记录时间回拨到昨天，模拟跨天
    views = db_session.query(ShareView).filter(ShareView.token_id == share.id).all()
    for v in views:
        v.viewed_at = v.viewed_at - timedelta(days=1)
    db_session.add_all(views)
    db_session.commit()

    # "今天"同一 IP 再次访问 —— 应再次计数
    counted = crud.record_view(db_session, share, "1.2.3.4", "ua", success=True)
    assert counted is True
    assert share.view_count == 2


def test_record_view_failed_access_does_not_count(db_session, sample_worker):
    """失败的访问尝试（如 404）不计入 view_count"""
    from share import crud

    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )

    counted = crud.record_view(db_session, share, "1.2.3.4", "ua", success=False)
    assert counted is False
    assert share.view_count == 0


def test_record_view_no_ip_each_visit_counts(db_session, sample_worker):
    """无 IP 来源时（无法识别访问者）按每次访问都计数，避免丢失来源信息"""
    from share import crud

    share, _ = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=False,
    )

    crud.record_view(db_session, share, None, "ua", success=True)
    crud.record_view(db_session, share, None, "ua", success=True)
    assert share.view_count == 2


def test_consume_one_time_marks_revoked(db_session, sample_worker):
    """一次性 token 被消费后 revoked_at 不为空"""
    from share import crud

    share, plain = crud.create_share_token(
        db=db_session,
        worker_id=sample_worker.id,
        created_by="u1",
        expires_in_seconds=None,
        one_time=True,
    )
    assert share.is_revoked() is False
    crud.consume_one_time(db_session, share)
    assert share.is_revoked() is True
    assert share.is_active(datetime.now()) is False


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
    from share.models import ShareToken

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
