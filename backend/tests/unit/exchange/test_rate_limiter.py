"""P2:限流器冒烟测试(TokenBucketRateLimiter)。

覆盖评估报告 O 区「限流」缺口的同步部分:令牌桶耗尽拒绝、状态读取。
(WS 断线重连场景需要 mock server,超出冒烟范围,见报告 P2 备注。)
"""

from __future__ import annotations

import time

from axon_quant import TokenBucketRateLimiter


def test_token_bucket_exhaustion() -> None:
    """容量 5 的桶:前 5 次 acquire 成功,第 6 次起拒绝。"""
    limiter = TokenBucketRateLimiter(5)
    assert limiter.capacity() == 5

    results = [limiter.try_acquire() for _ in range(7)]
    assert results[:5] == [True] * 5
    assert results[5:] == [False] * 2

    status = limiter.status()
    assert status["capacity"] == 5
    assert status["available"] == 0
    assert status["utilization"] == 1.0


def test_token_bucket_refill_over_time() -> None:
    """refill_rate 默认等于容量(令牌/秒):耗尽后短暂等待恢复至少 1 个令牌。"""
    limiter = TokenBucketRateLimiter(5)
    while limiter.try_acquire():
        pass  # 排空

    time.sleep(0.25)  # 等待补充(refill_rate=5/s → 0.25s 补 >1 个)
    assert limiter.try_acquire() is True


def test_status_reports_config() -> None:
    """status 字段与构造参数一致。"""
    limiter = TokenBucketRateLimiter(10)
    assert limiter.capacity() == 10
    assert limiter.available_tokens() == 10
    assert limiter.refill_rate() == 10.0

    status = limiter.status()
    assert status["capacity"] == 10
    assert status["available"] == 10
    assert status["refill_rate"] == 10.0
    assert status["utilization"] == 0.0
