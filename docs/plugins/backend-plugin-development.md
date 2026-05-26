# 后端插件开发指南

## 1. 后端插件目录结构

后端插件采用标准化的目录结构，每个插件是一个独立的目录，位于 `/backend/plugins/` 目录下。

### 1.1 基本目录结构

```
backend/plugins/
├── example_plugin/          # 插件目录
│   ├── manifest.json        # 插件清单文件
│   ├── plugin.py            # 插件主文件
│   ├── routes.py            # 插件路由文件（可选）
│   ├── services/            # 插件服务目录（可选）
│   │   └── example_service.py
│   └── utils/               # 插件工具目录（可选）
│       └── example_utils.py
├── plugin_base.py           # 插件基类
├── plugin_manager.py        # 插件管理器
└── api.py                   # 插件API
```

### 1.2 目录结构说明

- **插件目录**：插件的根目录，名称应与插件名称一致
- **manifest.json**：插件清单文件，包含插件的基本信息和配置
- **plugin.py**：插件主文件，包含插件的核心实现
- **routes.py**：插件路由文件，定义插件的API路由（可选）
- **services/**：插件服务目录，包含插件的业务逻辑（可选）
- **utils/**：插件工具目录，包含插件的工具函数（可选）

## 2. 后端插件清单文件规范

每个后端插件都需要一个 `manifest.json` 文件，用于描述插件的基本信息和配置。

### 2.1 清单文件字段定义

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `name` | string | 是 | 插件名称，应与插件目录名称一致 |
| `version` | string | 是 | 插件版本，遵循语义化版本规范 |
| `description` | string | 是 | 插件描述，简要说明插件的功能 |
| `author` | string | 是 | 插件作者 |
| `main` | string | 是 | 插件主文件路径，默认为 `plugin.py` |
| `load_type` | string | 否 | 插件加载类型，`hot`（热加载）或 `restart`（重启加载），默认 `hot` |
| `permissions` | array | 否 | 插件权限声明数组，如 `["database:read", "network:outbound"]` |
| `config_schema` | object | 否 | 插件配置 Schema，用于前端动态渲染配置编辑表单 |
| `routes` | string | 否 | 插件路由文件路径，默认为 `routes.py` |
| `dependencies` | array | 否 | 插件依赖的其他插件或库 |

### 2.2 示例清单文件

```json
{
  "name": "example_plugin",
  "version": "1.0.0",
  "description": "Example backend plugin for QuantCell",
  "author": "QuantCell Team",
  "main": "plugin.py",
  "load_type": "hot",
  "permissions": ["database:read"],
  "config_schema": {},
  "routes": "routes.py",
  "dependencies": []
}
```

## 3. 后端插件基类使用指南

后端插件需要继承 `PluginBase` 类，并实现必要的方法。

### 3.1 插件基类核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `__init__` | 初始化插件 | `name`: 插件名称<br>`version`: 插件版本 | 无 |
| `register` | 注册插件 | `plugin_manager`: 插件管理器实例 | 无 |
| `start` | 启动插件 | 无 | 无 |
| `stop` | 停止插件 | 无 | 无 |
| `on_enable` | 启用钩子 | 无 | 无 |
| `on_disable` | 禁用钩子 | 无 | 无 |
| `get_frontend_assets` | 获取前端资源声明 | 无 | 资源字典或 `None` |
| `get_config_schema` | 获取配置Schema | 无 | Schema字典或 `None` |
| `get_info` | 获取插件信息 | 无 | 插件信息字典 |
| `get_metadata` | 获取完整元数据 | 无 | 元数据字典 |

### 3.2 插件基类使用示例

```python
from plugins.plugin_base import PluginBase

class ExamplePlugin(PluginBase):
    def __init__(self):
        super().__init__("example_plugin", "1.0.0")
        # 设置加载类型，可选 "hot" 或 "restart"
        self.load_type = "hot"
    
    def register(self, plugin_manager):
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")
    
    def start(self):
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")
    
    def stop(self):
        super().stop()
        self.logger.info(f"{self.name} 插件停止成功")
    
    def on_enable(self):
        """插件被启用时调用"""
        self.logger.info(f"{self.name} 插件已启用")
    
    def on_disable(self):
        """插件被禁用时调用"""
        self.logger.info(f"{self.name} 插件已禁用")
    
    def get_frontend_assets(self):
        """声明插件的前端静态资源路径"""
        return {"entry": "frontend/dist/index.js", "css": "frontend/dist/index.css"}
    
    def get_config_schema(self):
        """返回配置Schema，用于前端动态渲染配置编辑表单"""
        return {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "title": "API Key"}
            }
        }
    
    def get_metadata(self):
        """返回插件完整元数据"""
        return {
            "name": self.name,
            "version": self.version,
            "description": "示例插件",
            "author": "QuantCell Team",
            "load_type": self.load_type,
            "frontend_assets": self.get_frontend_assets(),
            "config_schema": self.get_config_schema()
        }
```

### 3.3 插件加载类型（load_type）

`load_type` 属性控制插件的加载方式，在 `PluginBase.__init__` 中默认设置为 `"hot"`，子类可在构造函数中覆盖。

| 值 | 说明 | 适用场景 |
|------|------|----------|
| `hot` | 热加载，插件可在运行时动态加载/卸载，无需重启应用 | 轻量级插件、纯 API 扩展、UI 组件 |
| `restart` | 重启加载，插件需要重启应用才能正确加载 | 需要重量级初始化的插件、注册全局中间件、修改核心配置 |

```python
class HeavyPlugin(PluginBase):
    def __init__(self):
        super().__init__("heavy_plugin", "1.0.0")
        # 需要重启才能加载的插件
        self.load_type = "restart"
```

### 3.4 生命周期钩子

插件的完整生命周期如下：

```
__init__() → register(plugin_manager) → start()
                                          ↓
                                    on_enable() / on_disable()（运行时可多次调用）
                                          ↓
                                        stop()
```

#### `on_enable()` / `on_disable()`

在插件被启用/禁用时由插件管理器调用。基类提供默认空实现，子类按需覆盖。

- **`on_enable()`**：插件被启用时触发，适合执行资源初始化、事件订阅等操作
- **`on_disable()`**：插件被禁用时触发，适合执行资源释放、取消事件订阅等操作

```python
from plugins.plugin_base import PluginBase
from plugins.event_bus import event_bus

class MonitorPlugin(PluginBase):
    def __init__(self):
        super().__init__("monitor_plugin", "1.0.0")
    
    def on_enable(self):
        """启用时订阅事件"""
        event_bus.subscribe("trade_executed", self._on_trade)
        self.logger.info("监控插件已启用")
    
    def on_disable(self):
        """禁用时取消订阅"""
        event_bus.unsubscribe("trade_executed", self._on_trade)
        self.logger.info("监控插件已禁用")
    
    def _on_trade(self, data):
        self.logger.info(f"收到交易事件: {data}")
```

### 3.5 前端资源声明（get_frontend_assets）

`get_frontend_assets()` 方法用于声明插件的前端静态资源路径。基类默认返回 `None`，带前端界面的插件需要覆盖此方法。

返回格式：

```python
def get_frontend_assets(self):
    return {
        "entry": "frontend/dist/index.js",
        "css": "frontend/dist/index.css"
    }
```

返回 `None` 表示该插件没有前端资源。

### 3.6 配置 Schema（get_config_schema）

`get_config_schema()` 方法返回插件的配置 Schema 字典，用于前端动态渲染配置编辑表单。基类默认返回 `None`。

```python
def get_config_schema(self):
    return {
        "type": "object",
        "properties": {
            "interval": {
                "type": "integer",
                "title": "采集间隔（秒）",
                "default": 60,
                "minimum": 10
            },
            "symbols": {
                "type": "array",
                "title": "监控币种",
                "items": {"type": "string"}
            }
        },
        "required": ["interval"]
    }
```

### 3.7 插件元数据（get_metadata）

`get_metadata()` 方法聚合插件的所有元信息，返回一个包含以下字段的字典：

| 字段 | 来源 |
|------|------|
| `name` | `self.name` |
| `version` | `self.version` |
| `description` | 子类覆盖时自定义 |
| `author` | 子类覆盖时自定义 |
| `load_type` | `self.load_type` |
| `frontend_assets` | `self.get_frontend_assets()` |
| `config_schema` | `self.get_config_schema()` |

```python
def get_metadata(self):
    return {
        "name": self.name,
        "version": self.version,
        "description": "自定义描述",
        "author": "作者名称",
        "load_type": self.load_type,
        "frontend_assets": self.get_frontend_assets(),
        "config_schema": self.get_config_schema()
    }
```

## 4. 后端插件API参考

插件API提供了核心功能访问和插件间通信的能力。

### 4.1 插件API核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `register_service` | 注册服务 | `name`: 服务名称<br>`service`: 服务实例 | 无 |
| `get_service` | 获取服务 | `name`: 服务名称 | 服务实例或None |
| `get_plugin` | 获取插件 | `plugin_name`: 插件名称 | 插件实例或None |
| `get_all_plugins` | 获取所有插件 | 无 | 插件名称列表 |
| `send_event` | 发送事件 | `event_name`: 事件名称<br>`data`: 事件数据 | 无 |
| `log` | 记录日志 | `message`: 日志消息<br>`level`: 日志级别 | 无 |

### 4.2 插件API使用示例

```python
from plugins.api import PluginAPI

class ExamplePlugin(PluginBase):
    def __init__(self):
        super().__init__("example_plugin", "1.0.0")
        self.api = None
    
    def register(self, plugin_manager):
        super().register(plugin_manager)
        # 获取插件API实例
        self.api = PluginAPI(plugin_manager)
        # 注册服务
        self.api.register_service("example_service", ExampleService())
    
    def some_method(self):
        # 获取其他插件
        other_plugin = self.api.get_plugin("other_plugin")
        # 发送事件
        self.api.send_event("example_event", {"data": "example"})
        # 记录日志
        self.api.log("Example message", "info")
```

## 5. 后端插件路由注册

后端插件可以通过 FastAPI 的 `APIRouter` 注册自定义API路由。

### 5.1 路由注册方法

1. **在插件类中定义路由**：在插件类的 `__init__` 方法中创建 `APIRouter` 实例
2. **注册路由处理函数**：使用装饰器注册路由处理函数
3. **插件管理器自动注册**：插件管理器会自动将插件的路由注册到 FastAPI 应用

### 5.2 路由注册示例

```python
from fastapi import APIRouter
from plugins.plugin_base import PluginBase

class ExamplePlugin(PluginBase):
    def __init__(self):
        super().__init__("example_plugin", "1.0.0")
        # 创建API路由
        self.router = APIRouter(prefix="/api/plugins/example")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        @self.router.get("/")
        def example_root():
            """示例根路由"""
            return {
                "message": "Hello from example plugin!",
                "plugin_name": self.name,
                "version": self.version
            }
        
        @self.router.get("/test")
        def example_test():
            """示例测试路由"""
            return {
                "test": "success",
                "data": {
                    "key1": "value1",
                    "key2": "value2"
                }
            }
```

### 5.3 路由注册注意事项

- **路由前缀**：建议使用 `/api/plugins/{plugin_name}` 作为路由前缀
- **路由命名**：路由处理函数应使用描述性的名称
- **文档字符串**：路由处理函数应包含文档字符串，用于生成API文档
- **输入验证**：所有API输入应进行验证
- **错误处理**：应适当处理异常并返回有意义的错误信息

## 6. 后端插件示例实现

以下是一个完整的后端插件示例实现。

### 6.1 插件主文件（plugin.py）

```python
from fastapi import APIRouter
from plugins.plugin_base import PluginBase

class ExamplePlugin(PluginBase):
    """示例插件，演示插件系统的基本功能"""
    
    def __init__(self):
        """初始化示例插件"""
        super().__init__("example_plugin", "1.0.0")
        # 创建API路由
        self.router = APIRouter(prefix="/api/plugins/example")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        @self.router.get("/")
        def example_root():
            """示例根路由"""
            return {
                "message": "Hello from example plugin!",
                "plugin_name": self.name,
                "version": self.version
            }
        
        @self.router.get("/test")
        def example_test():
            """示例测试路由"""
            return {
                "test": "success",
                "data": {
                    "key1": "value1",
                    "key2": "value2"
                }
            }
    
    def register(self, plugin_manager):
        """注册插件"""
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功，版本: {self.version}")
    
    def start(self):
        """启动插件"""
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")
    
    def stop(self):
        """停止插件"""
        super().stop()
        self.logger.info(f"{self.name} 插件停止成功")

def register_plugin():
    """注册插件的入口函数"""
    return ExamplePlugin()
```

### 6.2 插件路由文件（routes.py）

```python
from fastapi import APIRouter

# 创建路由实例
router = APIRouter(prefix="/api/plugins/example")

@router.get("/routes")
def example_routes():
    """示例路由文件中的路由"""
    return {
        "message": "Hello from example routes!",
        "from": "routes.py"
    }

@router.post("/data")
def example_data(data: dict):
    """示例数据处理路由"""
    return {
        "message": "Data received!",
        "data": data
    }
```

### 6.3 插件服务文件（services/example_service.py）

```python
class ExampleService:
    """示例服务类"""
    
    def get_example_data(self):
        """获取示例数据"""
        return {
            "example": "data",
            "timestamp": "2023-01-01T00:00:00Z"
        }
    
    def process_data(self, data):
        """处理数据"""
        return {
            "processed": True,
            "data": data,
            "result": f"Processed: {data}"
        }
```

## 7. 后端插件开发最佳实践

### 7.1 代码组织

- **模块化设计**：将代码按功能模块组织
- **单一职责**：每个函数和类应只负责一个功能
- **代码复用**：提取公共功能到工具类或服务类
- **文档注释**：为所有公共方法添加文档注释

### 7.2 错误处理

- **异常捕获**：适当捕获和处理异常
- **错误返回**：返回有意义的错误信息
- **日志记录**：记录关键操作和错误信息

### 7.3 性能优化

- **资源管理**：合理使用和释放资源
- **缓存策略**：对于频繁访问的数据使用缓存
- **异步处理**：对于IO密集型操作使用异步处理

### 7.4 安全性

- **输入验证**：验证所有用户输入
- **权限检查**：实现适当的权限检查
- **数据加密**：对敏感数据进行加密
- **安全日志**：记录安全相关的操作

## 8. 后端插件测试

### 8.1 测试方法

- **单元测试**：测试单个函数和类
- **集成测试**：测试插件与其他组件的集成
- **API测试**：测试插件的API端点

### 8.2 测试示例

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_example_plugin_root():
    """测试示例插件根路由"""
    response = client.get("/api/plugins/example/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Hello from example plugin!"
    assert data["plugin_name"] == "example_plugin"

def test_example_plugin_test():
    """测试示例插件测试路由"""
    response = client.get("/api/plugins/example/test")
    assert response.status_code == 200
    data = response.json()
    assert data["test"] == "success"
    assert "data" in data
```

## 9. 后端插件部署

### 9.1 插件打包

- **目录结构**：保持标准的目录结构
- **依赖管理**：明确声明插件依赖
- **版本控制**：使用语义化版本控制

### 9.2 插件安装

1. **复制插件目录**：将插件目录复制到 `/backend/plugins/` 目录
2. **重启应用**：重启FastAPI应用以加载新插件

### 9.3 插件卸载

1. **停止应用**：停止FastAPI应用
2. **删除插件目录**：删除 `/backend/plugins/` 目录下的插件目录
3. **重启应用**：重启FastAPI应用

## 10. 常见问题和解决方案

### 10.1 插件加载失败

**问题**：插件无法加载
**解决方案**：
- 检查插件目录结构是否正确
- 检查 `manifest.json` 文件是否有效
- 检查插件主文件是否存在 `register_plugin` 函数
- 检查插件是否继承自 `PluginBase` 类

### 10.2 路由注册失败

**问题**：插件的API路由无法访问
**解决方案**：
- 检查路由是否正确定义
- 检查路由前缀是否正确
- 检查插件是否正确设置了 `router` 属性

### 10.3 插件间通信失败

**问题**：插件无法与其他插件通信
**解决方案**：
- 检查插件API是否正确初始化
- 检查目标插件是否已加载
- 检查服务是否正确注册

### 10.4 性能问题

**问题**：插件运行缓慢
**解决方案**：
- 优化代码逻辑
- 使用缓存
- 实现异步处理
- 减少数据库查询

## 11. 高级功能

### 11.1 EventBus 事件总线

EventBus 是插件间通信的核心机制，采用全局单例模式，支持同步和异步事件发布，使用 `threading.Lock` 保证线程安全。

#### 导入方式

```python
from plugins.event_bus import event_bus
```

#### API 说明

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `subscribe(event_name, callback)` | 订阅事件 | `event_name`: 事件名称<br>`callback`: 回调函数 | `None` |
| `unsubscribe(event_name, callback)` | 取消订阅 | `event_name`: 事件名称<br>`callback`: 回调函数 | `None` |
| `publish(event_name, data)` | 同步发布事件 | `event_name`: 事件名称<br>`data`: 事件数据 | `None` |
| `publish_async(event_name, data)` | 异步发布事件（线程池执行） | `event_name`: 事件名称<br>`data`: 事件数据 | `None` |
| `get_subscribers(event_name)` | 获取事件订阅者列表 | `event_name`: 事件名称 | 订阅者名称列表 |
| `clear()` | 清除所有事件订阅 | 无 | `None` |

#### 使用示例

```python
from plugins.event_bus import event_bus
from plugins.plugin_base import PluginBase

class TradeLoggerPlugin(PluginBase):
    def __init__(self):
        super().__init__("trade_logger", "1.0.0")
    
    def start(self):
        super().start()
        # 订阅交易执行事件
        event_bus.subscribe("trade_executed", self._on_trade)
    
    def stop(self):
        # 停止时取消订阅
        event_bus.unsubscribe("trade_executed", self._on_trade)
        super().stop()
    
    def _on_trade(self, data):
        self.logger.info(f"交易已执行: {data}")

class SignalPlugin(PluginBase):
    def __init__(self):
        super().__init__("signal_plugin", "1.0.0")
    
    def trigger_signal(self, signal_data):
        # 同步发布交易信号
        event_bus.publish("trade_executed", signal_data)
    
    def trigger_async_report(self, report_data):
        # 异步发布报告事件（在线程池中执行回调）
        event_bus.publish_async("report_generated", report_data)
```

#### 注意事项

- **异常隔离**：单个订阅者回调抛出异常时，不影响其他订阅者的执行，异常会被记录到日志
- **线程安全**：所有操作都通过 `threading.Lock` 保护，可在多线程环境中安全使用
- **重复订阅**：同一回调函数对同一事件重复订阅会被忽略
- **异步发布**：`publish_async` 使用 `asyncio.get_event_loop().run_in_executor()` 在线程池中执行回调

### 11.2 PluginStore 持久化存储

PluginStore 是插件数据持久化的静态方法类，基于 SQLAlchemy ORM，提供插件记录的增删改查功能，JSON 字段自动序列化/反序列化。

#### 导入方式

```python
from plugins.plugin_store import PluginStore
```

#### API 说明

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `save_plugin(metadata)` | 创建或更新插件记录 | `metadata`: 插件元数据字典 | `bool` |
| `get_plugin(name)` | 按名称查询插件 | `name`: 插件名称 | 插件字典或 `None` |
| `get_all_plugins()` | 查询所有插件 | 无 | 插件字典列表 |
| `update_status(name, status, error_message)` | 更新插件状态 | `name`: 插件名称<br>`status`: 状态<br>`error_message`: 错误信息 | `bool` |
| `delete_plugin(name)` | 删除插件记录 | `name`: 插件名称 | `bool` |
| `update_plugin(name, **kwargs)` | 更新插件字段 | `name`: 插件名称<br>`**kwargs`: 要更新的字段 | `bool` |

#### 使用示例

```python
from plugins.plugin_store import PluginStore

# 保存插件记录（已存在则更新，不存在则创建）
PluginStore.save_plugin({
    "name": "my_plugin",
    "version": "1.0.0",
    "description": "我的插件",
    "author": "开发者",
    "load_type": "hot",
    "permissions": ["database:read"],
    "config_schema": {"type": "object", "properties": {}},
    "status": "installed"
})

# 查询单个插件
plugin = PluginStore.get_plugin("my_plugin")
if plugin:
    print(f"插件版本: {plugin['version']}, 状态: {plugin['status']}")

# 查询所有插件
all_plugins = PluginStore.get_all_plugins()
for p in all_plugins:
    print(f"{p['name']} v{p['version']} - {p['status']}")

# 更新插件状态
PluginStore.update_status("my_plugin", "active")

# 更新插件状态（带错误信息）
PluginStore.update_status("my_plugin", "error", "初始化失败: 连接超时")

# 更新插件字段
PluginStore.update_plugin("my_plugin", version="1.1.0", description="更新描述")

# 删除插件记录
PluginStore.delete_plugin("my_plugin")
```

#### 数据模型

PluginStore 底层使用 `Plugin` ORM 模型，主要字段包括：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | String | 插件名称（唯一） |
| `version` | String | 插件版本 |
| `description` | String | 插件描述 |
| `author` | String | 插件作者 |
| `load_type` | String | 加载类型（hot/restart） |
| `status` | String | 插件状态（installed/active/error 等） |
| `install_source` | String | 安装来源 |
| `install_path` | String | 安装路径 |
| `permissions` | JSON | 权限声明（自动序列化/反序列化） |
| `config_schema` | JSON | 配置Schema（自动序列化/反序列化） |
| `frontend_entry` | String | 前端入口文件 |
| `error_message` | String | 错误信息 |
| `installed_at` | DateTime | 安装时间 |
| `updated_at` | DateTime | 更新时间 |

### 11.3 PluginSecurity 权限声明与沙箱

PluginSecurity 模块提供插件权限管理和安全执行环境，包括权限校验、路由冲突检测和异常兜底执行。

#### 导入方式

```python
from plugins.plugin_security import PluginPermission, validate_permissions, check_system_route_conflict, PluginSandbox
```

#### 权限枚举（PluginPermission）

| 权限值 | 说明 |
|--------|------|
| `database:read` | 数据库读取权限 |
| `database:write` | 数据库写入权限 |
| `api:internal` | 内部 API 调用权限 |
| `filesystem:read` | 文件系统读取权限 |
| `filesystem:write` | 文件系统写入权限 |
| `network:outbound` | 外部网络请求权限 |

#### 权限校验

`validate_permissions()` 校验权限声明是否合法，返回 `(是否合法, 错误信息)` 元组。

```python
from plugins.plugin_security import validate_permissions

# 合法权限
ok, msg = validate_permissions(["database:read", "network:outbound"])
assert ok is True

# 不合法权限
ok, msg = validate_permissions(["database:read", "unknown:perm"])
assert ok is False
assert "不支持的权限" in msg

# 空权限列表
ok, msg = validate_permissions([])
assert ok is True
```

#### 路由冲突检测

`check_system_route_conflict()` 检查插件路由前缀是否与系统核心路由冲突，受保护的系统路由前缀包括：`/api/config`、`/api/system`、`/api/auth`、`/api/workers`、`/api/logs`、`/api/notifications`、`/api/system-ports`、`/ws`。

```python
from plugins.plugin_security import check_system_route_conflict

# 无冲突
ok, msg = check_system_route_conflict("/api/plugins/my_plugin")
assert ok is True

# 路由冲突
ok, msg = check_system_route_conflict("/api/system/extra")
assert ok is False
assert "与系统核心路由冲突" in msg
```

#### PluginSandbox 沙箱执行

PluginSandbox 提供异常兜底执行环境，防止插件代码异常影响系统稳定性。

```python
from plugins.plugin_security import PluginSandbox

sandbox = PluginSandbox("my_plugin", logger)

# execute: 异常时返回 None，错误记录到日志
result = sandbox.execute(risky_function, arg1, arg2)
if result is None:
    print("执行失败")

# execute_safe: 返回 (成功标志, 结果) 元组
success, result = sandbox.execute_safe(risky_function, arg1, arg2)
if success:
    print(f"执行成功: {result}")
else:
    print(f"执行失败: {result}")  # result 为错误信息字符串
```

#### 完整安全示例

```python
from plugins.plugin_base import PluginBase
from plugins.plugin_security import (
    PluginPermission, validate_permissions, check_system_route_conflict, PluginSandbox
)
from fastapi import APIRouter

class SecurePlugin(PluginBase):
    def __init__(self):
        super().__init__("secure_plugin", "1.0.0")
        self.permissions = ["database:read", "network:outbound"]
        self.sandbox = PluginSandbox(self.name, self.logger)
    
    def register(self, plugin_manager):
        # 校验权限声明
        ok, msg = validate_permissions(self.permissions)
        if not ok:
            self.logger.error(f"权限声明非法: {msg}")
            return
        
        # 检查路由冲突
        prefix = "/api/plugins/secure"
        ok, msg = check_system_route_conflict(prefix)
        if not ok:
            self.logger.error(f"路由冲突: {msg}")
            return
        
        self.router = APIRouter(prefix=prefix)
        super().register(plugin_manager)
    
    def safe_fetch_data(self):
        """使用沙箱安全执行外部请求"""
        success, result = self.sandbox.execute_safe(self._fetch_from_api)
        if success:
            return result
        self.logger.warning(f"数据获取失败: {result}")
        return None
    
    def _fetch_from_api(self):
        # 可能抛出异常的外部调用
        import httpx
        resp = httpx.get("https://api.example.com/data", timeout=5)
        resp.raise_for_status()
        return resp.json()
```

## 12. 总结

后端插件开发是扩展 QuantCell 系统功能的重要方式。通过遵循本指南的规范和最佳实践，开发者可以创建高质量、可维护的后端插件。

插件开发应注重代码质量、安全性和性能，同时保持良好的文档和测试覆盖率。这样可以确保插件与系统的兼容性和稳定性，为用户提供更好的体验。