"""CredentialsService 测试。"""

import pytest

from credentials.account import Account
from credentials.exceptions import AccountNotFoundError
from credentials.service import CredentialsService


@pytest.fixture
def svc(tmp_path):
    db_path = str(tmp_path / "test.db")
    return CredentialsService(db_path=db_path, fingerprint="test_fp_12345")


def test_add_account_returns_account(svc):
    """add_account 返回 Account 对象（不包含原文 secret）。"""
    acct = svc.add_account("main", "binance", "key123", "secret456")
    assert isinstance(acct, Account)
    assert acct.name == "main"
    assert acct.exchange == "binance"
    # dataclass 不应含 api_secret
    assert not hasattr(acct, "api_secret")


def test_get_credential_decrypts(svc):
    """get_credential 返回原文（已解密）。"""
    svc.add_account("main", "binance", "key123", "secret456")
    api_key, api_secret = svc.get_credential("main")
    assert api_key == "key123"
    assert api_secret == "secret456"


def test_list_accounts_no_secret(svc):
    """list_accounts 返回的 Account 不含 secret。"""
    svc.add_account("main", "binance", "key123", "secret456")
    accounts = svc.list_accounts()
    assert len(accounts) == 1
    assert accounts[0].name == "main"
    assert not hasattr(accounts[0], "api_secret")


def test_remove_account_soft_delete(svc):
    """remove_account 后 list 不再显示，但 get_credential 抛 AccountNotFoundError。"""
    svc.add_account("main", "binance", "key123", "secret456")
    svc.remove_account("main")
    assert len(svc.list_accounts()) == 0
    with pytest.raises(AccountNotFoundError):
        svc.get_credential("main")


def test_get_credential_not_found(svc):
    """不存在的账号抛 AccountNotFoundError。"""
    with pytest.raises(AccountNotFoundError):
        svc.get_credential("ghost")
