"""MCP 出站安全（P2-04）：结果脱敏 + 代码体量上限。"""

import re

from agent.core.audit import redact_secrets

__all__ = ["assert_code_size", "redact_secrets", "redact_secrets_text"]

# 同步给 tool exec/read 类结果的体量上限，避免整只巨型文件塞给外部客户端
MAX_CODE_BYTES = 512 * 1024

# 文本结果中常见密钥赋值形态（JSON / env / 日志），值段整体替换
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret|token|password|passwd|authorization)\b"
    r"(\s*[\"']?\s*[:=]\s*[\"']?)([^\s,;}\"]+)"
)
# QuantCell Agent Token 明文形态（qctk_ + 40 位 hex）无论出现在哪都打码
_QCTK_TOKEN_RE = re.compile(r"qctk_[0-9a-fA-F]{40}")


def redact_secrets_text(text: str) -> str:
    """字符串结果脱敏：键值对形态的疑似密钥值 + qctk_ 明文令牌替换为 ***。

    结构化结果请用 redact_secrets（按键名脱敏），本函数兜底纯文本场景。
    """
    return _QCTK_TOKEN_RE.sub("***", _SECRET_VALUE_RE.sub(r"\1\2***", text))


def assert_code_size(code: str, label: str = "代码") -> None:
    """超限抛 ValueError，由调用方转成错误信息返回给客户端。"""
    size = len(code.encode("utf-8"))
    if size > MAX_CODE_BYTES:
        raise ValueError(f"{label}共 {size} 字节，超过单次 {MAX_CODE_BYTES // 1024} KiB 上限，请缩小读取范围后重试")
