"""Fernet AES-128-CBC + HMAC 加密，密钥派生自机器指纹。

ponytail: 机器指纹 = SHA256(/etc/machine-id + hostname + MAC)[:32 hex]
         派生密钥 = SHA256(fingerprint + 'quantcell-salt-v1')
         用 cryptography.fernet.Fernet 包装
         升级到 AES-256：换 Fernet44（cryptography 不支持）或自行实现 AES-GCM
"""
import base64
import hashlib
import socket
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from credentials.exceptions import CredentialsError


_SALT = b"quantcell-salt-v1"


def get_machine_fingerprint() -> str:
    """获取机器指纹（SHA256 hex 前 32 字符）。

    ponytail: 跨平台用 /etc/machine-id（Linux） + hostname + MAC
    """
    parts: list[str] = []

    # Linux 机器 ID
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        parts.append(machine_id_path.read_text().strip())

    # 跨平台 hostname
    parts.append(socket.gethostname())

    # MAC 地址（uuid.getnode 在 macOS/Linux/Windows 均可用）
    try:
        mac_int = uuid.getnode()
        if (mac_int >> 40) != 0:  # 真实 MAC，非 fake
            mac = ":".join(f"{(mac_int >> i) & 0xFF:02x}" for i in range(0, 48, 8))
            parts.append(mac)
    except Exception:
        pass

    raw = "|".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _derive_key() -> bytes:
    """从机器指纹派生 Fernet 密钥（base64 编码的 32 字节）。"""
    fp = get_machine_fingerprint()
    return base64.urlsafe_b64encode(hashlib.sha256(fp.encode() + _SALT).digest())


def encrypt_secret(plain: str) -> bytes:
    """加密字符串。"""
    return Fernet(_derive_key()).encrypt(plain.encode())


def decrypt_secret(cipher: bytes) -> str:
    """解密字符串，篡改抛 CredentialsError。"""
    try:
        return Fernet(_derive_key()).decrypt(cipher).decode()
    except InvalidToken as e:
        raise CredentialsError("密文无效或机器指纹不匹配") from e
