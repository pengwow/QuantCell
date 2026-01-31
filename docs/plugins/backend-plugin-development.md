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
| `get_info` | 获取插件信息 | 无 | 插件信息字典 |

### 3.2 插件基类使用示例

```python
from plugins.plugin_base import PluginBase

class ExamplePlugin(PluginBase):
    def __init__(self):
        super().__init__("example_plugin", "1.0.0")
    
    def register(self, plugin_manager):
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")
    
    def start(self):
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")
    
    def stop(self):
        super().stop()
        self.logger.info(f"{self.name} 插件停止成功")
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

## 11. 总结

后端插件开发是扩展 QuantCell 系统功能的重要方式。通过遵循本指南的规范和最佳实践，开发者可以创建高质量、可维护的后端插件。

插件开发应注重代码质量、安全性和性能，同时保持良好的文档和测试覆盖率。这样可以确保插件与系统的兼容性和稳定性，为用户提供更好的体验。