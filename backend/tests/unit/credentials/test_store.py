"""凭证存储层测试 — SQLite 加密表 CRUD。"""

import pytest

from credentials.exceptions import AccountAlreadyExistsError, AccountNotFoundError
from credentials.store import CredentialsStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    return CredentialsStore(str(db_path))


def test_create_account(store):
    """创建账号应返回 UUID。"""
    cred_id = store.create_credential(b"enc_key", b"enc_secret", "fp123")
    acct_id = store.create_account("main", "binance", cred_id)
    assert len(acct_id) == 36  # UUID4


def test_get_account_by_name(store):
    """按名字查账号。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("main", "binance", cred_id)
    acct = store.get_account_by_name("main")
    assert acct["name"] == "main"
    assert acct["exchange"] == "binance"


def test_get_account_not_found(store):
    """不存在的账号抛 AccountNotFoundError。"""
    with pytest.raises(AccountNotFoundError):
        store.get_account_by_name("ghost")


def test_duplicate_account_raises(store):
    """重复名字抛 AccountAlreadyExistsError。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("main", "binance", cred_id)
    with pytest.raises(AccountAlreadyExistsError):
        store.create_account("main", "binance", cred_id)


def test_list_accounts_excludes_soft_deleted(store):
    """软删除的账号不在列表中。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("a1", "binance", cred_id)
    store.create_account("a2", "okx", cred_id)
    store.soft_delete_account("a1")
    accounts = store.list_accounts()
    names = [a["name"] for a in accounts]
    assert "a1" not in names
    assert "a2" in names


def test_list_accounts_no_secret_fields(store):
    """list 返回的字段不含 api_key/api_secret。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("main", "binance", cred_id)
    accounts = store.list_accounts()
    assert "api_key" not in accounts[0]
    assert "api_secret" not in accounts[0]
    assert "api_key_enc" not in accounts[0]
    assert "api_secret_enc" not in accounts[0]
