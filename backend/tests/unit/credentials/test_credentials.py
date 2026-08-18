"""Credentials 模块单元测试

覆盖加密/解密、凭证存储 CRUD、服务层业务编排。
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from credentials.account import Account
from credentials.crypto import decrypt_secret, encrypt_secret, get_machine_fingerprint
from credentials.exceptions import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    CredentialsError,
)
from credentials.service import CredentialsService
from credentials.store import CredentialsStore


class TestCrypto:
    """加密模块测试"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密解密往返验证"""
        plain = "my_secret_api_key_123"
        cipher = encrypt_secret(plain)
        assert isinstance(cipher, bytes)
        assert len(cipher) > 0
        decrypted = decrypt_secret(cipher)
        assert decrypted == plain

    def test_encrypt_decrypt_empty_string(self):
        """空字符串加密解密"""
        plain = ""
        cipher = encrypt_secret(plain)
        decrypted = decrypt_secret(cipher)
        assert decrypted == ""

    def test_decrypt_invalid_token(self):
        """无效密文解密抛 CredentialsError"""
        invalid_cipher = b"invalid_fernet_token"
        with pytest.raises(CredentialsError) as exc_info:
            decrypt_secret(invalid_cipher)
        assert "密文无效或机器指纹不匹配" in str(exc_info.value)

    def test_machine_fingerprint_is_consistent(self):
        """机器指纹每次调用一致"""
        fp1 = get_machine_fingerprint()
        fp2 = get_machine_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 32  # SHA256 hex 前 32 字符


class TestCredentialsStore:
    """凭证存储 CRUD 测试"""

    @pytest.fixture
    def temp_db(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_credentials.db")
            yield db_path

    def test_create_and_get_credential(self, temp_db):
        """创建凭证并查询"""
        store = CredentialsStore(temp_db)
        cred_id = store.create_credential(
            api_key_enc=b"encrypted_key",
            api_secret_enc=b"encrypted_secret",
            fingerprint_hash="test_fingerprint",
        )
        assert cred_id is not None
        assert len(cred_id) == 36  # UUID4

    def test_create_and_get_account(self, temp_db):
        """创建账号并查询"""
        store = CredentialsStore(temp_db)
        cred_id = store.create_credential(
            api_key_enc=b"key1",
            api_secret_enc=b"secret1",
            fingerprint_hash="fp1",
        )
        acct_id = store.create_account("test_account", "binance", cred_id)
        assert acct_id is not None

        acct = store.get_account_by_name("test_account")
        assert acct["name"] == "test_account"
        assert acct["exchange"] == "binance"
        assert acct["credential_id"] == cred_id

    def test_create_duplicate_account(self, temp_db):
        """重复账号名抛 AccountAlreadyExistsError"""
        store = CredentialsStore(temp_db)
        cred_id = store.create_credential(
            api_key_enc=b"key1",
            api_secret_enc=b"secret1",
            fingerprint_hash="fp1",
        )
        store.create_account("duplicate_name", "binance", cred_id)
        with pytest.raises(AccountAlreadyExistsError):
            store.create_account("duplicate_name", "binance", cred_id)

    def test_get_nonexistent_account(self, temp_db):
        """不存在的账号抛 AccountNotFoundError"""
        store = CredentialsStore(temp_db)
        with pytest.raises(AccountNotFoundError):
            store.get_account_by_name("nonexistent")

    def test_list_accounts(self, temp_db):
        """列出所有账号"""
        store = CredentialsStore(temp_db)
        cred_id = store.create_credential(b"key1", b"secret1", "fp1")
        store.create_account("acct1", "binance", cred_id)
        store.create_account("acct2", "okx", cred_id)

        accounts = store.list_accounts()
        assert len(accounts) == 2
        names = [a["name"] for a in accounts]
        assert "acct1" in names
        assert "acct2" in names

    def test_soft_delete_account(self, temp_db):
        """软删除账号"""
        store = CredentialsStore(temp_db)
        cred_id = store.create_credential(b"key1", b"secret1", "fp1")
        store.create_account("delete_me", "binance", cred_id)

        # 删除前
        assert len(store.list_accounts()) == 1

        # 删除
        store.soft_delete_account("delete_me")

        # 删除后
        assert len(store.list_accounts()) == 0

        # 再次删除抛异常
        with pytest.raises(AccountNotFoundError):
            store.soft_delete_account("delete_me")

    def test_get_credential_by_account(self, temp_db):
        """按账号名取凭证"""
        store = CredentialsStore(temp_db)
        cred_id = store.create_credential(b"key_enc", b"secret_enc", "fp1")
        store.create_account("my_account", "binance", cred_id)

        cred = store.get_credential_by_account("my_account")
        assert cred["api_key_enc"] == b"key_enc"
        assert cred["api_secret_enc"] == b"secret_enc"
        assert cred["fingerprint_hash"] == "fp1"


class TestCredentialsService:
    """凭证服务层测试"""

    @pytest.fixture
    def temp_db(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "service_test.db")
            yield db_path

    def test_add_account(self, temp_db):
        """新增账号（加密入库）"""
        service = CredentialsService(db_path=temp_db)
        account = service.add_account(
            name="test_account",
            exchange="binance",
            api_key="test_api_key",
            api_secret="test_api_secret",
        )
        assert isinstance(account, Account)
        assert account.name == "test_account"
        assert account.exchange == "binance"

    def test_get_credential_roundtrip(self, temp_db):
        """添加账号后解密取回"""
        service = CredentialsService(db_path=temp_db)
        service.add_account(
            name="roundtrip_test",
            exchange="binance",
            api_key="my_key_123",
            api_secret="my_secret_456",
        )
        api_key, api_secret = service.get_credential("roundtrip_test")
        assert api_key == "my_key_123"
        assert api_secret == "my_secret_456"

    def test_list_accounts_no_secret(self, temp_db):
        """列出账号不含 secret"""
        service = CredentialsService(db_path=temp_db)
        service.add_account("acct1", "binance", "key1", "secret1")
        service.add_account("acct2", "okx", "key2", "secret2")

        accounts = service.list_accounts()
        assert len(accounts) == 2
        names = {a.name for a in accounts}
        assert names == {"acct1", "acct2"}

    def test_remove_account(self, temp_db):
        """软删除账号"""
        service = CredentialsService(db_path=temp_db)
        service.add_account("remove_me", "binance", "key", "secret")
        assert len(service.list_accounts()) == 1

        service.remove_account("remove_me")
        assert len(service.list_accounts()) == 0

        with pytest.raises(AccountNotFoundError):
            service.get_credential("remove_me")

    def test_get_nonexistent_credential(self, temp_db):
        """获取不存在的凭证"""
        service = CredentialsService(db_path=temp_db)
        with pytest.raises(AccountNotFoundError):
            service.get_credential("nonexistent")
