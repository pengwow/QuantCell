#!/usr/bin/env python3
"""
WebSocket性能测试脚本
测试WebSocket连接的并发性能和消息处理能力
"""

import asyncio
import websockets
import time
import json
import random

async def test_websocket_connection(client_id: int):
    """测试单个WebSocket连接"""
    try:
        async with websockets.connect(f"ws://localhost:8000/ws/task?client_id=test_client_{client_id}") as websocket:
            print(f"客户端 {client_id} 连接成功")
            
            # 发送订阅请求
            subscribe_message = {
                "type": "subscribe",
                "id": f"sub_{client_id}",
                "data": {
                    "topics": ["task:progress", "task:status"]
                }
            }
            await websocket.send(json.dumps(subscribe_message))
            
            # 发送心跳消息
            for i in range(5):
                ping_message = {
                    "type": "ping",
                    "id": f"ping_{client_id}_{i}"
                }
                await websocket.send(json.dumps(ping_message))
                await asyncio.sleep(1)
                
                # 接收消息
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1)
                    print(f"客户端 {client_id} 收到消息: {response[:100]}...")
                except asyncio.TimeoutError:
                    pass
                    
            print(f"客户端 {client_id} 测试完成")
            return True
    except Exception as e:
        print(f"客户端 {client_id} 连接失败: {e}")
        return False

async def test_concurrent_connections(num_connections: int):
    """测试并发WebSocket连接"""
    print(f"开始测试 {num_connections} 个并发WebSocket连接...")
    start_time = time.time()
    
    tasks = []
    for i in range(num_connections):
        task = asyncio.create_task(test_websocket_connection(i))
        tasks.append(task)
        # 避免同时连接导致服务器压力过大
        await asyncio.sleep(0.05)
    
    results = await asyncio.gather(*tasks)
    success_count = sum(results)
    end_time = time.time()
    
    print(f"测试完成: {success_count}/{num_connections} 个连接成功")
    print(f"测试耗时: {end_time - start_time:.2f} 秒")
    print(f"平均连接时间: {(end_time - start_time) / num_connections:.3f} 秒/连接")

async def test_message_throughput():
    """测试消息吞吐量"""
    print("开始测试消息吞吐量...")
    start_time = time.time()
    message_count = 100
    
    async with websockets.connect("ws://localhost:8000/ws/task") as websocket:
        # 发送多条消息
        for i in range(message_count):
            message = {
                "type": "ping",
                "id": f"ping_{i}",
                "timestamp": int(time.time() * 1000)
            }
            await websocket.send(json.dumps(message))
        
        # 接收响应
        received_count = 0
        while received_count < message_count:
            try:
                await asyncio.wait_for(websocket.recv(), timeout=0.1)
                received_count += 1
            except asyncio.TimeoutError:
                break
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"发送 {message_count} 条消息，接收 {received_count} 条响应")
    print(f"测试耗时: {duration:.2f} 秒")
    print(f"消息吞吐量: {message_count / duration:.2f} 条/秒")

if __name__ == "__main__":
    print("WebSocket性能测试")
    print("=" * 50)
    
    # 测试并发连接
    asyncio.run(test_concurrent_connections(20))
    print()
    
    # 测试消息吞吐量
    asyncio.run(test_message_throughput())
    print()
    
    print("性能测试完成!")
