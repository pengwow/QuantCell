"""凭证层异常。"""


class CredentialsError(Exception):
    """凭证层基础异常。"""


class AccountNotFoundError(CredentialsError):
    """账号不存在。"""


class AccountAlreadyExistsError(CredentialsError):
    """账号已存在。"""


class FingerprintMismatchError(CredentialsError):
    """机器指纹不匹配（备份文件来自其他机器）。"""
