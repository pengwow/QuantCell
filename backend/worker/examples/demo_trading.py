#!/usr/bin/env python3
"""
Nautilus Worker 模拟盘交易示例

演示如何使用 Worker 工厂创建模拟盘交易 Worker。
"""

import asyncio
import os
from decimal import Decimal

# 设置环境变量
os.environ["BINANCE_TESTNET_API_KEY"] = "your_testnet_api_key"
os.environ["BINANCE_TESTNET_API_SECRET"] = "your_testnet_api_secret"


async def main():
    """主函数"""
    from backend.worker.factory import create_nautilus_worker

    # 创建 Binance 模拟盘 Worker
    worker = create_nautilus_worker(
        worker_id="demo-001",
        strategy_path="strategies/sma_cross_nautilus.py",
        config={
            "symbol": "BTCUSDT",
            "order_qty": str(Decimal("0.001")),  # 小数量避免余额不足
        },
        exchange="binance",
        account_type="spot",
        trading_mode="demo",  # 模拟盘模式
    )

    # 启动 Worker
    print("启动 Worker...")
    await worker.start()

    # 运行一段时间
    print("Worker 运行中，按 Ctrl+C 停止...")
    try:
        await asyncio.sleep(60)  # 运行 60 秒
    except KeyboardInterrupt:
        print("\n收到停止信号")

    # 停止 Worker
    print("停止 Worker...")
    await worker.stop()

    print("完成")


if __name__ == "__main__":
    asyncio.run(main())
