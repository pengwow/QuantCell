# -*- coding: utf-8 -*-
"""
分享系统 远端客户端（PC → quantcell.top）

封装以下职责：
- HMAC-SHA256 签名（payload, secret）
- 设备 API Key 鉴权头
- 指数退避重试（最多 max_retries 次）
- 失败时抛出 RemoteShareError，调用方决定如何降级

仅当 ShareRemoteConfig.is_ready=True 时才应调用 upload / revoke。
未就绪时调用将快速失败，调用方可以回退到本地分享。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp

from utils.logger import get_logger, LogType

from .config import ShareRemoteConfig, get_remote_config

logger = get_logger(__name__, LogType.APPLICATION)


class RemoteShareError(RuntimeError):
    """远端分享服务调用失败（网络/4xx/5xx/验签失败）"""


class RemoteShareClient:
    """PC 端 → quantcell.top 的 HTTP 客户端"""

    def __init__(self, config: Optional[ShareRemoteConfig] = None) -> None:
        self.config = config or get_remote_config()

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    async def upload(self, snapshot: Dict[str, Any], token_hash: str, worker_id: int) -> Dict[str, Any]:
        """上传白名单 snapshot + 签名到 quantcell.top

        Returns:
            {"remote_id": str, "short_url": str, "raw": dict}

        Raises:
            RemoteShareError: 网络/服务/验签失败
        """
        if not self.config.is_ready:
            raise RemoteShareError("远端未就绪：share_remote 未启用或缺少 api_key/hmac_secret")

        uploaded_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "token_hash": token_hash,
            "worker_id": worker_id,
            "snapshot": snapshot,
            "uploaded_at": uploaded_at,
        }
        signature = self._sign_payload(payload)

        body = {
            **payload,
            "signature": signature,
        }
        url = f"{self.config.base_url}/api/share"

        resp = await self._request_with_retry("POST", url, body=body)
        remote_id = resp.get("id") or resp.get("remote_id")
        short_url = resp.get("short_url")
        if not remote_id or not short_url:
            raise RemoteShareError(f"远端响应缺少 id/short_url: {resp}")
        return {"remote_id": str(remote_id), "short_url": str(short_url), "raw": resp}

    async def revoke(self, remote_id: str) -> None:
        """撤销远端 share

        Raises:
            RemoteShareError: 网络/服务失败
        """
        if not self.config.is_ready:
            raise RemoteShareError("远端未就绪：share_remote 未启用或缺少 api_key/hmac_secret")

        url = f"{self.config.base_url}/api/share/{remote_id}"
        await self._request_with_retry("DELETE", url, body=None)

    async def health_check(self) -> bool:
        """探活（/healthz）—— 不需要鉴权"""
        url = f"{self.config.base_url}/healthz"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning("远端 healthz 失败: %s", e)
            return False

    # ------------------------------------------------------------------ #
    # 同步包装（让 FastAPI 同步 handler 直接调用，无需自己管理 loop）
    # ------------------------------------------------------------------ #
    def upload_sync(self, snapshot: Dict[str, Any], token_hash: str, worker_id: int) -> Dict[str, Any]:
        return asyncio.run(self.upload(snapshot, token_hash, worker_id))

    def revoke_sync(self, remote_id: str) -> None:
        asyncio.run(self.revoke(remote_id))

    def health_check_sync(self) -> bool:
        return asyncio.run(self.health_check())

    # ------------------------------------------------------------------ #
    # 内部：HMAC 签名 / HTTP 调用
    # ------------------------------------------------------------------ #
    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """对 payload 做 HMAC-SHA256 签名，hex 输出"""
        if not self.config.hmac_secret:
            raise RemoteShareError("hmac_secret 未配置")
        # 使用稳定序列化（key 排序、unicode 安全）
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        mac = hmac.new(
            self.config.hmac_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        )
        return mac.hexdigest()

    def _build_headers(self, with_body: bool, body_str: Optional[str]) -> Dict[str, str]:
        # 签名时使用 body 原文（保证接收方能复算）
        sig_input = body_str or ""
        ts = str(int(time.time()))
        request_sig = hmac.new(
            (self.config.hmac_secret or "").encode("utf-8"),
            f"{ts}.{sig_input}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Device-Key": self.config.api_key or "",
            "X-Timestamp": ts,
            "X-Request-Signature": request_sig,
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """带指数退避的重试调用"""
        body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else None
        headers = self._build_headers(with_body=body is not None, body_str=body_str)

        last_err: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method,
                        url,
                        headers=headers,
                        data=body_str,
                    ) as resp:
                        text = await resp.text()
                        if 200 <= resp.status < 300:
                            if not text:
                                return {}
                            try:
                                return json.loads(text)
                            except json.JSONDecodeError as e:
                                raise RemoteShareError(f"远端返回非 JSON (status={resp.status}): {e}")
                        # 4xx 不重试（业务错误）
                        if 400 <= resp.status < 500:
                            raise RemoteShareError(
                                f"远端拒绝请求 status={resp.status} body={text[:500]}"
                            )
                        # 5xx 可重试
                        last_err = RemoteShareError(f"远端 5xx status={resp.status} body={text[:200]}")
                        logger.warning(
                            f"远端 5xx，尝试重试 {attempt}/{self.config.max_retries} url={url}"
                        )
            except RemoteShareError:
                # 业务错误：直接抛出
                raise
            except Exception as e:  # 网络错误：可重试
                last_err = e
                logger.warning(
                    f"远端调用网络错误，尝试重试 {attempt}/{self.config.max_retries} url={url} err={e}"
                )

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_backoff * (2 ** (attempt - 1)))

        raise RemoteShareError(f"远端调用最终失败：{last_err}")


# ---------------------------------------------------------------------- #
# 同步便捷函数（无状态，一次性调用）
# ---------------------------------------------------------------------- #
def upload_sync(snapshot: Dict[str, Any], token_hash: str, worker_id: int) -> Dict[str, Any]:
    return RemoteShareClient().upload_sync(snapshot, token_hash, worker_id)


def revoke_sync(remote_id: str) -> None:
    RemoteShareClient().revoke_sync(remote_id)
