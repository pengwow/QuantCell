#!/usr/bin/env python3
"""
ZeroMQ 消息推送示例

此脚本演示如何使用 ZeroMQ 的 PUB 模式发送消息
"""

import zmq
import time
import json


def main():
    """主函数"""
    # 创建 ZeroMQ 上下文
    context = zmq.Context()
    
    # 创建 PUB 套接字
    socket = context.socket(zmq.PUB)
    
    # 绑定到端口
    socket.bind("tcp://*:5555")
    
    print("ZeroMQ 消息推送服务器已启动，绑定到端口 5555")
    print("按 Ctrl+C 退出...")
    
    try:
        # 发送消息循环
        for i in range(1, 11):
            # 准备消息数据
            message = {
                "id": i,
                "type": "notification",
                "message": f"这是第 {i} 条测试消息",
                "timestamp": time.time()
            }
            
            # 转换为 JSON 字符串
            json_message = json.dumps(message)
            
            # 发送消息（带有主题前缀）
            topic = "updates"
            socket.send_multipart([topic.encode(), json_message.encode()])
            
            print(f"发送消息: {json_message}")
            
            # 等待 1 秒
            time.sleep(1)
            
        # 发送结束消息
        end_message = {
            "id": 0,
            "type": "end",
            "message": "消息发送完毕",
            "timestamp": time.time()
        }
        json_end_message = json.dumps(end_message)
        socket.send_multipart(["updates".encode(), json_end_message.encode()])
        print(f"发送结束消息: {json_end_message}")
        
    except KeyboardInterrupt:
        print("\n用户中断，退出程序")
    finally:
        # 关闭套接字和上下文
        socket.close()
        context.term()
        print("ZeroMQ 上下文已关闭")


if __name__ == "__main__":
    main()
