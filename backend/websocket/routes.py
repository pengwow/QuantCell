# WebSocket路由处理

import json
import time
from typing import Optional, Set

from fastapi import WebSocket, WebSocketDisconnect, APIRouter, Query
from loguru import logger

from backend.websocket.manager import manager
from backend.collector.utils.task_manager import task_manager


router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    topics: Optional[str] = Query(None)
):
    """WebSocket主端点
    
    Args:
        websocket: WebSocket连接对象
        client_id: 客户端ID
        topics: 订阅的主题列表，逗号分隔
    """
    # 解析主题列表
    topic_set: Set[str] = set()
    if topics:
        topic_set = set(topics.split(","))
    
    # 处理连接
    client_id = await manager.connect(websocket, client_id, topic_set)
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            
            try:
                # 解析消息
                message = json.loads(data)
                await handle_message(message, client_id)
            except json.JSONDecodeError as e:
                logger.error(f"无效的JSON消息: {e}")
                # 发送错误消息
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "id": f"error_{client_id}",
                        "timestamp": int(time.time() * 1000),
                        "error": {
                            "code": "INVALID_MESSAGE",
                            "message": "无效的消息格式",
                            "details": str(e)
                        }
                    },
                    client_id
                )
    except WebSocketDisconnect:
        # 处理连接断开
        await manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket处理错误: {e}")
        # 处理连接断开
        await manager.disconnect(client_id)


@router.websocket("/ws/task")
async def websocket_task_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    topics: Optional[str] = Query(None)
):
    """任务相关WebSocket端点
    
    Args:
        websocket: WebSocket连接对象
        client_id: 客户端ID
        topics: 订阅的主题列表，逗号分隔
    """
    # 解析主题列表
    topic_set: Set[str] = set()
    if topics:
        topic_set = set(topics.split(","))
    else:
        # 默认订阅任务相关主题
        topic_set = {"task:progress", "task:status"}
    
    # 处理连接
    client_id = await manager.connect(websocket, client_id, topic_set)
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            
            try:
                # 解析消息
                message = json.loads(data)
                await handle_message(message, client_id)
            except json.JSONDecodeError as e:
                logger.error(f"无效的JSON消息: {e}")
                # 发送错误消息
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "id": f"error_{client_id}",
                        "timestamp": int(time.time() * 1000),
                        "error": {
                            "code": "INVALID_MESSAGE",
                            "message": "无效的消息格式",
                            "details": str(e)
                        }
                    },
                    client_id
                )
    except WebSocketDisconnect:
        # 处理连接断开
        await manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket处理错误: {e}")
        # 处理连接断开
        await manager.disconnect(client_id)


async def handle_message(message: dict, client_id: str):
    """处理接收到的消息
    
    Args:
        message: 消息内容
        client_id: 客户端ID
    """
    message_type = message.get("type")
    message_id = message.get("id")
    
    if message_type == "ping":
        # 处理心跳消息
        await handle_ping(message, client_id)
    elif message_type == "subscribe":
        # 处理订阅请求
        await handle_subscribe(message, client_id)
    elif message_type == "unsubscribe":
        # 处理取消订阅请求
        await handle_unsubscribe(message, client_id)
    elif message_type == "get_task":
        # 处理获取任务请求
        await handle_get_task(message, client_id)
    elif message_type == "get_tasks":
        # 处理获取任务列表请求
        await handle_get_tasks(message, client_id)
    else:
        # 处理未知消息类型
        await manager.send_personal_message(
            {
                "type": "error",
                "id": message_id or f"error_{client_id}",
                "timestamp": int(time.time() * 1000),
                "error": {
                    "code": "UNKNOWN_MESSAGE_TYPE",
                    "message": f"未知的消息类型: {message_type}"
                }
            },
            client_id
        )


async def handle_ping(message: dict, client_id: str):
    """处理心跳消息
    
    Args:
        message: 消息内容
        client_id: 客户端ID
    """
    message_id = message.get("id")
    
    # 更新最后心跳时间
    manager.update_last_ping(client_id)
    
    # 发送pong消息
    await manager.send_personal_message(
        {
            "type": "pong",
            "id": message_id,
            "timestamp": int(time.time() * 1000),
            "data": {
                "server_time": int(time.time() * 1000)
            }
        },
        client_id
    )


async def handle_subscribe(message: dict, client_id: str):
    """处理订阅请求
    
    Args:
        message: 消息内容
        client_id: 客户端ID
    """
    message_id = message.get("id")
    topics = message.get("data", {}).get("topics", [])
    
    if not isinstance(topics, list):
        await manager.send_personal_message(
            {
                "type": "error",
                "id": message_id,
                "timestamp": int(time.time() * 1000),
                "error": {
                    "code": "INVALID_TOPICS",
                    "message": "无效的主题列表"
                }
            },
            client_id
        )
        return
    
    # 处理订阅
    for topic in topics:
        await manager.subscribe(client_id, topic)


async def handle_unsubscribe(message: dict, client_id: str):
    """处理取消订阅请求
    
    Args:
        message: 消息内容
        client_id: 客户端ID
    """
    message_id = message.get("id")
    topics = message.get("data", {}).get("topics", [])
    
    if not isinstance(topics, list):
        await manager.send_personal_message(
            {
                "type": "error",
                "id": message_id,
                "timestamp": int(time.time() * 1000),
                "error": {
                    "code": "INVALID_TOPICS",
                    "message": "无效的主题列表"
                }
            },
            client_id
        )
        return
    
    # 处理取消订阅
    for topic in topics:
        await manager.unsubscribe(client_id, topic)


async def handle_get_task(message: dict, client_id: str):
    """处理获取任务请求
    
    Args:
        message: 消息内容
        client_id: 客户端ID
    """
    message_id = message.get("id")
    task_id = message.get("data", {}).get("task_id")
    
    if not task_id:
        await manager.send_personal_message(
            {
                "type": "error",
                "id": message_id,
                "timestamp": int(time.time() * 1000),
                "error": {
                    "code": "MISSING_TASK_ID",
                    "message": "缺少任务ID"
                }
            },
            client_id
        )
        return
    
    # 获取任务信息
    task = task_manager.get_task(task_id)
    
    if not task:
        await manager.send_personal_message(
            {
                "type": "error",
                "id": message_id,
                "timestamp": int(time.time() * 1000),
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"任务不存在: {task_id}"
                }
            },
            client_id
        )
        return
    
    # 发送任务信息
    await manager.send_personal_message(
        {
            "type": "task_info",
            "id": message_id,
            "timestamp": int(time.time() * 1000),
            "data": task
        },
        client_id
    )


async def handle_get_tasks(message: dict, client_id: str):
    """处理获取任务列表请求
    
    Args:
        message: 消息内容
        client_id: 客户端ID
    """
    message_id = message.get("id")
    
    # 获取任务列表
    tasks = task_manager.get_all_tasks()
    
    # 发送任务列表
    await manager.send_personal_message(
        {
            "type": "task_list",
            "id": message_id,
            "timestamp": int(time.time() * 1000),
            "data": {
                "tasks": tasks
            }
        },
        client_id
    )

