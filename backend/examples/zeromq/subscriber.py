#!/usr/bin/env python3
"""
ZeroMQ 消息消费示例

此脚本演示如何使用 ZeroMQ 的 SUB 模式接收消息
"""

import zmq
import json


def main():
    """主函数"""
    # 创建 ZeroMQ 上下文
    context = zmq.Context()
    
    # 创建 SUB 套接字
    socket = context.socket(zmq.SUB)
    
    # 连接到发布者
    socket.connect("tcp://localhost:5555")
    
    # 设置订阅主题（空字符串表示订阅所有主题）
    topic = "updates"
    socket.setsockopt_string(zmq.SUBSCRIBE, topic)
    
    print(f"ZeroMQ 消息消费者已启动，订阅主题: {topic}")
    print("等待接收消息...")
    print("按 Ctrl+C 退出...")
    
    try:
        # 接收消息循环
        while True:
            # 接收消息
            message_parts = socket.recv_multipart()
            
            # 解析消息部分
            received_topic = message_parts[0].decode()
            message_data = message_parts[1].decode()
            
            # 解析 JSON 消息
            message = json.loads(message_data)
            
            # 处理消息
            print(f"接收到消息:")
            print(f"  主题: {received_topic}")
            print(f"  ID: {message['id']}")
            print(f"  类型: {message['type']}")
            print(f"  内容: {message['message']}")
            print(f"  时间戳: {message['timestamp']}")
            print()
            
            # 检查是否为结束消息
            if message['type'] == 'end':
                print("收到结束消息，退出程序")
                break
                
    except KeyboardInterrupt:
        print("\n用户中断，退出程序")
    finally:
        # 关闭套接字和上下文
        socket.close()
        context.term()
        print("ZeroMQ 上下文已关闭")


if __name__ == "__main__":
    main()
