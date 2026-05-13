# 端口管理机制说明

## 概述

QuantCell 从 v1.x 版本开始引入智能端口管理系统（PortManager），用于解决以下问题：
- 端口被占用导致启动失败
- 异常退出后端口未释放（僵尸进程）
- 多实例部署时的端口冲突

## 工作原理

### 自动端口分配
系统为每个服务定义了默认端口和可用范围：

| 服务 | 默认端口 | 可用范围 | 说明 |
|------|---------|---------|------|
| fastapi | 8000 | 8000-8010 | HTTP API 服务 |
| zmq_data | 5555 | 5550-5560 | ZMQ 数据通道 |
| zmq_control | 5556 | 5560-5570 | ZMQ 控制通道 |
| zmq_status | 5557 | 5570-5580 | ZMQ 状态通道 |
| zmq_broadcast | 5558 | 5580-5590 | ZMQ 广播通道 |

启动时，PortManager 会：
1. 尝试绑定默认端口
2. 如果失败，自动在范围内查找下一个可用端口
3. 将最终使用的端口配置保存到 `data/port_config.json`
4. 所有组件通过统一接口获取端口配置

### 异常恢复
- **僵尸进程检测**: 启动时检查端口是否被上一次异常退出的进程占用
- **自动清理**: 如果是自身僵尸进程，尝试终止（SIGTERM → SIGKILL）
- **智能切换**: 其他进程占用时，自动切换到其他可用端口

## 环境变量配置

### USE_STATIC_PORTS
**类型**: 布尔值 (true/false)
**默认值**: false
**说明**: 强制使用硬编码的默认端口，禁用动态分配。用于调试或特殊部署场景。

```bash
export USE_STATIC_PORTS=true
python main.py  # 将始终使用 8000 端口，失败则报错
```

### PORT_CONFIG_PATH
**类型**: 字符串（文件路径）
**默认值**: data/port_config.json
**说明**: 自定义端口配置文件的存储位置。

```bash
export PORT_CONFIG_PATH=/custom/path/ports.json
python main.py  # 配置将保存到 /custom/path/ports.json
```

### WORKER_API_URL
**类型**: URL 字符串
**默认值**: http://localhost:{动态端口}
**说明**: CLI 工具连接的后端 API 地址。如果不设置，会自动从 PortManager 获取。

```bash
export WORKER_API_URL=http://192.168.1.100:8000
python scripts/worker_cli.py list  # 连接到指定地址
```

## 配置文件格式

### port_config.json 示例
```json
{
  "fastapi": 8000,
  "zmq_data": 5555,
  "zmq_control": 5556,
  "zmq_status": 5557,
  "zmq_broadcast": 5558,
  "pid": 12345,
  "start_time": "2026-05-13T10:30:00Z",
  "last_updated": "2026-05-13T10:30:00Z"
}
```

**字段说明**:
- `fastapi`, `zmq_*`: 各服务的实际端口号
- `pid`: 启动时的进程 ID
- `start_time`: 服务启动时间（ISO 8601 格式）
- `last_updated`: 配置最后更新时间

## API 接口

### GET /api/system/ports
获取所有服务的当前端口配置。

**响应示例**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "fastapi": {"port": 8000, "service": "HTTP API Server"},
    "zmq_data": {"port": 5555, "service": "ZMQ Data Channel"},
    "metadata": {
      "pid": 12345,
      "start_time": "...",
      "config_file": "/path/to/port_config.json"
    }
  }
}
```

### GET /api/system/ports/{service_name}
获取指定服务的端口配置。

**参数**:
- `service_name`: fastapi, zmq_data, zmq_control, zmq_status, zmq_broadcast

## CLI 工具集成

Worker CLI 工具 (`scripts/worker_cli.py`) 已集成 PortManager 支持：

### 导入机制
```python
try:
    from core.port_manager import port_manager as pm
    PORT_MANAGER_AVAILABLE = True
except ImportError:
    PORT_MANAGER_AVAILABLE = False
```

### 使用示例
```python
# 获取 FastAPI 动态端口
if PORT_MANAGER_AVAILABLE:
    try:
        fastapi_port = pm.get_port("fastapi")
        base_url = f"http://localhost:{fastapi_port}"
    except Exception:
        base_url = "http://localhost:8000"  # fallback
else:
    base_url = "http://localhost:8000"  # fallback
```

### 向后兼容性
- 如果 PortManager 模块不可用，自动回退到硬编码的默认端口
- 所有动态端口获取都包含异常处理，确保不会因端口管理失败而影响核心功能
- 环境变量 `WORKER_API_URL` 始终具有最高优先级，可覆盖动态端口检测

## 故障排查

### 问题：启动时报 "Address already in use"

**原因**: 默认端口被占用

**解决方案**:
1. 系统会自动切换到其他可用端口（无需干预）
2. 查看日志确认实际使用的端口：`[PortManager] FastAPI 服务将使用端口: 8001`
3. 如果希望使用特定端口，手动指定：`python main.py --port 8001`

### 问题：前端无法连接后端

**原因**: 后端使用了非默认端口，但前端不知道

**解决方案**:
1. 确保后端已完全启动（端口 API 可用）
2. 检查浏览器控制台是否有 `[PortConfig]` 相关日志
3. 手动访问 `http://localhost:{port}/api/system/ports` 验证 API 是否正常

### 问题：端口频繁切换

**原因**: 可能存在大量僵尸进程或端口范围太小

**解决方案**:
1. 检查是否有残留进程：`ps aux | grep python`
2. 终止僵尸进程：`kill -9 <PID>`
3. 清理配置文件：`rm data/port_config.json`，重启服务

## 回滚方案

如果新的端口管理机制出现问题，可以通过以下方式回滚：

1. **删除配置文件**:
   ```bash
   rm data/port_config.json
   ```

2. **强制使用静态端口**:
   ```bash
   export USE_STATIC_PORTS=true
   python main.py
   ```

3. **所有改动都保留了原始默认值作为 fallback**，即使 PortManager 失败，系统仍可使用硬编码端口运行。

## 最佳实践

1. **生产环境**: 建议明确指定端口并通过环境变量或配置文件固定
2. **开发环境**: 使用动态端口分配，避免多开发者端口冲突
3. **CI/CD**: 设置 `USE_STATIC_PORTS=true` 确保可预测性
4. **监控**: 定期检查 `data/port_config.json` 了解端口使用情况
5. **日志**: 关注 `[PortManager]` 开头的日志信息

## 相关文件

- 核心模块: `backend/core/port_manager.py`
- 配置文件: `data/port_config.json`
- API 接口: `backend/api/system_ports.py`
- CLI 工具: `backend/scripts/worker_cli.py`
- 单元测试: `backend/tests/unit/test_port_manager.py`
