"""凭证加密层测试 — Fernet AES + 机器指纹。"""

import pytest

from credentials.crypto import decrypt_secret, encrypt_secret, get_machine_fingerprint
from credentials.exceptions import CredentialsError


def test_machine_fingerprint_is_stable():
    """同一机器两次 fingerprint 应相等。"""
    assert get_machine_fingerprint() == get_machine_fingerprint()


def test_machine_fingerprint_is_32_chars_hex():
    """fingerprint 应为 32 字符 hex（SHA256 截断）。"""
    fp = get_machine_fingerprint()
    assert len(fp) == 32
    assert all(c in "0123456789abcdef" for c in fp)


def test_encrypt_decrypt_roundtrip():
    """加密后解密应恢复原文。"""
    plain = "my_api_secret_123"
    enc = encrypt_secret(plain)
    assert enc != plain.encode()
    assert decrypt_secret(enc) == plain


def test_encrypt_uses_different_iv_each_time():
    """相同原文两次加密应产生不同密文（Fernet 自带 IV 旋转）。"""
    enc1 = encrypt_secret("same")
    enc2 = encrypt_secret("same")
    assert enc1 != enc2


def test_decrypt_raises_on_corrupted_ciphertext():
    """篡改密文应抛 CredentialsError。"""
    enc = encrypt_secret("hello")
    # 翻转第一个字节
    corrupted = bytes([enc[0] ^ 0xFF]) + enc[1:]
    with pytest.raises(CredentialsError):
        decrypt_secret(corrupted)
