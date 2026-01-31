# 后端插件能力详细规范

## 1. 后端插件系统架构

### 1.1 核心组件

| 组件 | 描述 | 职责 |
|------|------|------|
| `PluginBase` | 插件基类 | 提供插件生命周期方法和基础功能 |
| `PluginManager` | 插件管理器 | 负责扫描、加载、管理插件 |
| `PluginAPI` | 插件API | 提供插件间通信和服务访问 |

### 1.2 插件目录结构

```
backend/
└── plugins/
    ├── example_plugin/
    │   ├── manifest.json       # 插件清单文件
    │   ├── plugin.py           # 插件核心实现
    │   └── routes.py           # 插件路由定义（可选）
    ├── __init__.py
    ├── api.py
    ├── plugin_base.py
    └── plugin_manager.py
```

## 2. 插件基类（PluginBase）规范

### 2.1 构造函数

```python
def __init__(self, name: str, version: str):
    """初始化插件
    
    Args:
        name: 插件名称
        version: 插件版本
    """
```

### 2.2 生命周期方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `register` | 注册插件 | `plugin_manager: Any` | `None` |
| `start` | 启动插件 | 无 | `None` |
| `stop` | 停止插件 | 无 | `None` |
| `get_info` | 获取插件信息 | 无 | `Dict[str, str]` |

### 2.3 核心属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `name` | `str` | 插件名称 |
| `version` | `str` | 插件版本 |
| `is_active` | `bool` | 插件是否激活 |
| `logger` | `Logger` | 插件日志记录器 |
| `plugin_manager` | `Any` | 插件管理器实例 |

## 3. 插件管理器（PluginManager）规范

### 3.1 构造函数

```python
def __init__(self, plugin_dir: str = None):
    """初始化插件管理器
    
    Args:
        plugin_dir: 插件目录，默认为backend/plugins
    """
```

### 3.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `scan_plugins` | 扫描插件目录 | 无 | `List[str]` |
| `load_plugin` | 加载指定插件 | `plugin_name: str` | `bool` |
| `load_all_plugins` | 加载所有插件 | 无 | `List[str]` |
| `register_plugins` | 注册插件路由 | `app: FastAPI` | `None` |
| `get_plugin` | 获取指定插件 | `plugin_name: str` | `PluginBase or None` |
| `get_all_plugins` | 获取所有插件 | 无 | `Dict[str, PluginBase]` |
| `stop_all_plugins` | 停止所有插件 | 无 | `None` |

## 4. 插件API（PluginAPI）规范

### 4.1 构造函数

```python
def __init__(self, plugin_manager: Any):
    """初始化插件API
    
    Args:
        plugin_manager: 插件管理器实例
    """
```

### 4.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `register_service` | 注册服务 | `name: str`, `service: Any` | `None` |
| `get_service` | 获取服务 | `name: str` | `Any or None` |
| `get_plugin` | 获取插件 | `plugin_name: str` | `Any or None` |
| `get_all_plugins` | 获取所有插件 | 无 | `List[str]` |
| `send_event` | 发送事件 | `event_name: str`, `data: Any = None` | `None` |
| `log` | 记录日志 | `message: str`, `level: str = "info"` | `None` |

## 5. 插件清单文件（manifest.json）规范

### 5.1 必需字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `string` | 插件名称（唯一标识符） |
| `version` | `string` | 插件版本（遵循语义化版本） |
| `description` | `string` | 插件描述 |
| `author` | `string` | 插件作者 |
| `main` | `string` | 插件主模块文件路径 |

### 5.2 可选字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `routes` | `string` | 插件路由文件路径 |
| `dependencies` | `array` | 插件依赖列表 |

### 5.3 示例

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

## 6. 插件实现规范

### 6.1 核心要求

1. **必须**继承 `PluginBase` 类
2. **必须**提供 `register_plugin` 函数作为插件入口
3. **必须**在 `manifest.json` 中定义插件信息
4. **建议**使用 `self.logger` 进行日志记录

### 6.2 插件入口函数

```python
def register_plugin() -> PluginBase:
    """注册插件的入口函数
    
    Returns:
        插件实例
    """
    return ExamplePlugin()
```

### 6.3 路由注册

插件可以通过 `router` 属性注册 FastAPI 路由：

```python
from fastapi import APIRouter

class ExamplePlugin(PluginBase):
    def __init__(self):
        super().__init__("example_plugin", "1.0.0")
        self.router = APIRouter(prefix="/api/plugins/example")
        self._setup_routes()
    
    def _setup_routes(self):
        @self.router.get("/")
        def example_root():
            return {"message": "Hello from example plugin!"}
```

## 7. 插件生命周期管理

### 7.1 生命周期流程

1. **扫描**：插件管理器扫描插件目录
2. **加载**：动态导入插件模块
3. **注册**：调用插件的 `register` 方法
4. **启动**：调用插件的 `start` 方法
5. **运行**：插件处于活动状态
6. **停止**：调用插件的 `stop` 方法

### 7.2 生命周期事件

| 事件 | 触发时机 | 处理方法 |
|------|----------|----------|
| `register` | 插件被注册时 | `register()` |
| `start` | 插件启动时 | `start()` |
| `stop` | 插件停止时 | `stop()` |

## 8. 插件间通信机制

### 8.1 服务注册与发现

插件可以注册服务供其他插件使用：

```python
# 注册服务
plugin_api.register_service("my_service", MyService())

# 发现服务
my_service = plugin_api.get_service("my_service")
```

### 8.2 事件系统

插件可以发送事件给所有插件：

```python
# 发送事件
plugin_api.send_event("data_updated", {"key": "value"})
```

## 9. 错误处理和日志记录

### 9.1 日志记录

插件应使用内置的 logger 进行日志记录：

```python
self.logger.info("插件初始化完成")
self.logger.error("操作失败", exc_info=True)
```

### 9.2 错误处理

插件应妥善处理异常，避免影响整个系统：

```python
try:
    # 插件逻辑
    pass
except Exception as e:
    self.logger.error(f"处理失败: {e}")
    # 适当的错误处理
```

## 10. 插件开发最佳实践

### 10.1 代码组织

- **模块化**：将功能分解为多个模块
- **关注点分离**：将路由、业务逻辑、数据访问分离
- **文档化**：为公共API提供清晰的文档

### 10.2 性能优化

- **延迟加载**：只在需要时加载资源
- **缓存**：合理使用缓存减少重复计算
- **异步处理**：对于IO密集型操作使用异步方法

### 10.3 安全性

- **输入验证**：验证所有用户输入
- **权限控制**：遵循最小权限原则
- **安全编码**：避免常见的安全漏洞

## 11. 插件兼容性要求

### 11.1 Python 版本

- 支持 Python 3.8+

### 11.2 依赖管理

- 插件依赖应在 `manifest.json` 中声明
- 避免与核心依赖冲突

### 11.3 API 兼容性

- 遵循文档中定义的 API 规范
- 向后兼容旧版本 API

## 12. 插件部署和集成流程

### 12.1 部署步骤

1. **创建插件目录**：在 `backend/plugins/` 下创建插件目录
2. **编写插件代码**：实现插件核心逻辑
3. **配置清单文件**：编写 `manifest.json` 文件
4. **重启服务**：插件管理器会自动加载新插件

### 12.2 集成测试

- 验证插件是否正确加载
- 测试插件路由是否可访问
- 验证插件功能是否正常

## 13. 插件能力评估标准

| 标准 | 描述 | 评分 |
|------|------|------|
| 功能完整性 | 插件功能是否完整实现 | 1-5 |
| 代码质量 | 代码是否清晰、规范 | 1-5 |
| 性能表现 | 插件性能是否良好 | 1-5 |
| 安全性 | 插件是否安全可靠 | 1-5 |
| 兼容性 | 插件是否与系统兼容 | 1-5 |
| 文档完整性 | 文档是否完整清晰 | 1-5 |

## 14. 常见问题与解决方案

### 14.1 插件加载失败

**问题**：插件管理器无法加载插件

**解决方案**：
- 检查 `manifest.json` 文件格式是否正确
- 确保插件主模块存在且包含 `register_plugin` 函数
- 检查插件依赖是否安装

### 14.2 路由注册失败

**问题**：插件路由无法访问

**解决方案**：
- 确保 `router` 属性是 `APIRouter` 实例
- 检查路由路径是否正确
- 验证插件是否正确加载

### 14.3 插件间通信失败

**问题**：插件无法访问其他插件的服务

**解决方案**：
- 确保服务已正确注册
- 检查服务名称是否正确
- 验证插件是否在服务注册后加载

## 15. 附录

### 15.1 示例插件代码

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

### 15.2 插件管理器配置

| 配置项 | 描述 | 默认值 |
|--------|------|--------|
| `plugin_dir` | 插件目录路径 | `backend/plugins` |
| `auto_load` | 是否自动加载插件 | `True` |
| `hot_reload` | 是否支持热重载 | `False` |