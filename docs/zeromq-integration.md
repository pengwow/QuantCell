# ZeroMQ 集成指南

## 1. 概述

本指南介绍如何在 QuantCell 项目中集成 ZeroMQ 作为消息队列系统，用于实现服务间的异步通信。

## 2. 安装依赖

### 2.1 安装 ZeroMQ Python 绑定

在 `backend` 目录下执行以下命令：

```bash
cd backend
uv add pyzmq
```

### 2.2 验证安装

```bash
cd backend
python -c "import zmq; print(f'ZeroMQ 版本: {zmq.zmq_version()}')"
```

## 3. 示例代码

示例代码位于 `backend/examples/zeromq/` 目录下：

- `publisher.py` - 消息推送示例
- `subscriber.py` - 消息消费示例
- `fastapi_integration.py` - FastAPI 集成示例

## 4. 运行示例

### 4.1 基本消息传递示例

1. **启动消息消费者**：

```bash
cd backend
python examples/zeromq/subscriber.py
```

2. **启动消息发布者**：

```bash
cd backend
python examples/zeromq/publisher.py
```

### 4.2 FastAPI 集成示例

1. **启动消息发布者**（提供测试消息）：

```bash
cd backend
python examples/zeromq/publisher.py
```

2. **启动 FastAPI 应用**：

```bash
cd backend
python examples/zeromq/fastapi_integration.py
```

3. **访问 API 文档**：

打开浏览器，访问 `http://localhost:8000/docs`

## 5. API 接口说明

### 5.1 `/send-message` (POST)

发送消息到 ZeroMQ 主题。

**参数**：
- `message` (必填)：消息内容
- `message_type` (可选)：消息类型，默认为 "notification"

**响应**：
```json
{
  "status": "success",
  "message": "消息已发送: 测试消息",
  "details": {
    "id": 1678901234,
    "type": "notification",
    "message": "测试消息",
    "timestamp": 1678901234.56789
  }
}
```

### 5.2 `/received-messages` (GET)

获取已接收的消息列表。

**响应**：
```json
{
  "status": "success",
  "count": 5,
  "messages": [
    {
      "id": 1,
      "type": "notification",
      "message": "这是第 1 条测试消息",
      "timestamp": 1678901234.12345
    },
    // 更多消息...
  ]
}
```

### 5.3 `/clear-messages` (GET)

清空已接收的消息列表。

**响应**：
```json
{
  "status": "success",
  "message": "消息已清空"
}
```

## 6. 代码结构说明

### 6.1 消息发布者 (publisher.py)

- 使用 ZeroMQ 的 PUB 模式发送消息
- 绑定到 `tcp://*:5555` 端口
- 发送带有 "updates" 主题的 JSON 格式消息

### 6.2 消息消费者 (subscriber.py)

- 使用 ZeroMQ 的 SUB 模式接收消息
- 连接到 `tcp://localhost:5555`
- 订阅 "updates" 主题的消息

### 6.3 FastAPI 集成 (fastapi_integration.py)

- 创建后台线程接收 ZeroMQ 消息
- 提供 REST API 发送消息和查询接收的消息
- 在应用关闭时清理 ZeroMQ 资源

## 7. 高级用法

### 7.1 多主题订阅

可以通过设置不同的订阅主题来实现消息过滤：

```python
# 订阅多个主题
socket.setsockopt_string(zmq.SUBSCRIBE, "news")
socket.setsockopt_string(zmq.SUBSCRIBE, "weather")
```

### 7.2 请求-响应模式

除了 PUB-SUB 模式，ZeroMQ 还支持 REQ-REP 模式：

```python
# 请求端
req_socket = context.socket(zmq.REQ)
req_socket.connect("tcp://localhost:5559")
req_socket.send(b"Hello")
response = req_socket.recv()

# 响应端
rep_socket = context.socket(zmq.REP)
rep_socket.bind("tcp://*:5559")
request = rep_socket.recv()
rep_socket.send(b"World")
```

### 7.3 推拉模式

用于任务分发：

```python
# 推送端
push_socket = context.socket(zmq.PUSH)
push_socket.bind("tcp://*:5560")

# 拉取端
pull_socket = context.socket(zmq.PULL)
pull_socket.connect("tcp://localhost:5560")
```

## 8. 注意事项

1. **资源管理**：
   - 始终在使用完套接字后关闭它们
   - 在应用退出时终止 ZeroMQ 上下文

2. **线程安全**：
   - ZeroMQ 套接字不是线程安全的，每个线程应使用自己的套接字
   - 使用锁来保护共享资源

3. **错误处理**：
   - 实现适当的错误处理机制
   - 处理网络中断和连接问题

4. **性能考虑**：
   - 对于高吞吐量场景，考虑使用 ZeroMQ 的批量消息
   - 调整套接字选项以优化性能

## 9. 故障排除

### 9.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 无法连接到发布者 | 发布者未运行或端口被占用 | 确保发布者正在运行，检查端口是否被占用 |
| 消息接收不到 | 订阅主题不匹配 | 确保订阅的主题与发布的主题一致 |
| 应用崩溃 | ZeroMQ 资源未正确释放 | 实现 try-finally 块确保资源释放 |

### 9.2 调试技巧

- 启用 ZeroMQ 调试日志：
  ```python
  import zmq
  zmq.utils.jsonapi.jsonmod = json
  ```

- 使用 `zmq.POLLIN` 进行非阻塞检查：
  ```python
  poller = zmq.Poller()
  poller.register(socket, zmq.POLLIN)
  socks = dict(poller.poll(timeout=1000))
  if socket in socks and socks[socket] == zmq.POLLIN:
      message = socket.recv()
  ```

## 10. 总结

ZeroMQ 是一个强大的消息队列库，提供了多种通信模式，可以轻松集成到 FastAPI 应用中。本指南提供的示例代码展示了基本的 PUB-SUB 模式使用方法，您可以根据实际需求扩展这些示例。

通过 ZeroMQ，您可以实现：
- 服务间的异步通信
- 消息的发布和订阅
- 任务的分发和处理
- 系统各组件的解耦

这些功能对于构建可扩展、可靠的分布式系统非常重要。