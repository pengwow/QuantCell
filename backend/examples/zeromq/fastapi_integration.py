#!/usr/bin/env python3
"""
FastAPI 集成 ZeroMQ 示例

此脚本演示如何在 FastAPI 应用中集成 ZeroMQ
"""

from fastapi import FastAPI, HTTPException
import zmq
import json
import threading
import asyncio

app = FastAPI(
    title="ZeroMQ 集成示例",
    description="演示如何在 FastAPI 中集成 ZeroMQ",
    version="1.0.0"
)

# ZeroMQ 上下文
context = zmq.Context()

# 全局变量存储接收到的消息
received_messages = []
message_lock = threading.Lock()


def message_receiver():
    """
    后台线程，用于接收 ZeroMQ 消息
    """
    global received_messages
    
    # 创建 SUB 套接字
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "updates")
    
    print("ZeroMQ 消息接收器已启动")
    
    try:
        while True:
            # 接收消息
            message_parts = socket.recv_multipart()
            topic = message_parts[0].decode()
            message_data = message_parts[1].decode()
            message = json.loads(message_data)
            
            # 存储消息
            with message_lock:
                received_messages.append(message)
            
            print(f"接收器收到消息: {message['message']}")
            
            # 检查是否为结束消息
            if message['type'] == 'end':
                print("接收器收到结束消息")
    except Exception as e:
        print(f"接收器错误: {e}")
    finally:
        socket.close()


# 启动消息接收器线程
receiver_thread = threading.Thread(target=message_receiver, daemon=True)
receiver_thread.start()


@app.post("/send-message")
async def send_message(message: str, message_type: str = "notification"):
    """
    发送消息到 ZeroMQ 主题
    
    Args:
        message: 消息内容
        message_type: 消息类型
        
    Returns:
        发送结果
    """
    # 创建 PUB 套接字
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://*:5556")
    
    try:
        # 准备消息
        import time
        msg = {
            "id": int(time.time()),
            "type": message_type,
            "message": message,
            "timestamp": time.time()
        }
        
        # 发送消息
        topic = "api_updates"
        socket.send_multipart([topic.encode(), json.dumps(msg).encode()])
        
        return {
            "status": "success",
            "message": f"消息已发送: {message}",
            "details": msg
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送消息失败: {str(e)}")
    finally:
        socket.close()


@app.get("/received-messages")
async def get_received_messages():
    """
    获取已接收的消息
    
    Returns:
        已接收的消息列表
    """
    with message_lock:
        messages = received_messages.copy()
    
    return {
        "status": "success",
        "count": len(messages),
        "messages": messages
    }


@app.get("/clear-messages")
async def clear_messages():
    """
    清空已接收的消息
    
    Returns:
        清空结果
    """
    with message_lock:
        global received_messages
        received_messages = []
    
    return {
        "status": "success",
        "message": "消息已清空"
    }


@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭时的清理操作
    """
    print("关闭 ZeroMQ 上下文...")
    context.term()
    print("ZeroMQ 上下文已关闭")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
