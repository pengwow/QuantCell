# 后端插件能力详细规范

## 1. 后端插件系统架构

### 1.1 核心组件

| 组件 | 描述 | 职责 |
|------|------|------|
| `PluginBase` | 插件基类 | 提供插件生命周期方法（`on_enable`/`on_disable`/`get_frontend_assets`/`get_config_schema`/`get_metadata`）和基础功能，包含 `load_type` 属性 |
| `PluginManager` | 插件管理器 | 负责扫描、加载、管理插件，支持热加载（HotPluginLoader）和重启加载（RestartPluginLoader） |
| `PluginAPI` | 插件API | 提供插件间通信和服务访问 |
| `EventBus` | 事件总线 | 提供线程安全的发布/订阅事件系统，支持 `subscribe`/`unsubscribe`/`publish`/`publish_async`，使用 `threading.Lock` 确保线程安全 |
| `PluginStore` | 插件存储 | 基于 SQLAlchemy ORM 的持久化存储，支持 `save_plugin`/`get_plugin`/`get_all_plugins`/`update_status`/`delete_plugin` |
| `PluginSecurity` | 安全机制 | 提供权限枚举（`PluginPermission`）、权限校验（`validate_permissions`）、路由冲突检测（`check_system_route_conflict`）和沙箱执行（`PluginSandbox`） |
| `PluginInstaller` | 安装器 | 支持从 ZIP 文件（`install_from_zip`）、字节数据（`install_from_zip_bytes`）和 Git 仓库（`install_from_git`）安装插件 |

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
    ├── plugin_manager.py
    ├── event_bus.py            # 事件总线
    ├── plugin_store.py         # 插件存储
    ├── plugin_security.py      # 安全机制
    ├── plugin_installer.py     # 安装器
    ├── plugin_dev.py           # 插件独立开发服务器
    └── loader/
        ├── __init__.py
        ├── base.py             # 加载器基类
        ├── hot_loader.py       # 热加载器
        └── restart_loader.py   # 重启加载器
```

## 2. 插件基类（PluginBase）规范

### 2.1 构造函数

```python
def __init__(self, api: PluginAPI):
    """初始化插件
    
    Args:
        api: 插件API实例，用于访问系统服务
    """
    self.api = api
    self.name: str = ""  # 插件名称
    self.version: str = "0.1.0"  # 插件版本
    self.description: str = ""  # 插件描述
    self.author: str = ""  # 插件作者
    self.load_type: LoadType = LoadType.HOT  # 加载类型：hot（热加载）或 restart（重启加载）
    self.enabled: bool = False  # 启用状态
    self.frontend_dir: Path = Path(__file__).parent / "frontend"  # 前端资源目录
```

### 2.2 生命周期方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `on_load` | 插件加载时调用 | 无 | `None` |
| `on_enable` | 插件启用时调用 | 无 | `None` |
| `on_disable` | 插件禁用时调用 | 无 | `None` |
| `on_unload` | 插件卸载时调用 | 无 | `None` |
| `get_frontend_assets` | 获取前端资源信息 | 无 | `dict` |
| `get_config_schema` | 获取配置模式 | 无 | `dict` |
| `get_metadata` | 获取插件元数据 | 无 | `dict` |

### 2.3 核心属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `name` | `str` | 插件名称 |
| `version` | `str` | 插件版本 |
| `description` | `str` | 插件描述 |
| `author` | `str` | 插件作者 |
| `load_type` | `LoadType` | 加载类型：`LoadType.HOT`（热加载）或 `LoadType.RESTART`（重启加载） |
| `enabled` | `bool` | 启用状态 |
| `frontend_dir` | `Path` | 前端资源目录 |

## 3. 插件管理器（PluginManager）规范

### 3.1 构造函数

```python
def __init__(self, plugin_dir: str = None):
    """初始化插件管理器
    
    Args:
        plugin_dir: 插件目录，默认为backend/plugins
    """
    self.plugin_dir = Path(plugin_dir) if plugin_dir else Path(__file__).parent.parent.parent / "data" / "plugins"
    self.plugins: Dict[str, PluginBase] = {}
    self.api = PluginAPI(self)
    self.loader = PluginLoader(self)
    self.store = PluginStore()
    self.installer = PluginInstaller(self)
    self.security = PluginSecurity()
```

### 3.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `install_plugin` | 安装插件 | `zip_path: Path` | `bool` |
| `uninstall_plugin` | 卸载插件 | `plugin_name: str` | `bool` |
| `enable_plugin` | 启用插件 | `plugin_name: str` | `bool` |
| `disable_plugin` | 禁用插件 | `plugin_name: str` | `bool` |
| `get_plugin` | 获取指定插件 | `plugin_name: str` | `PluginBase or None` |
| `get_all_plugins` | 获取所有插件 | 无 | `Dict[str, PluginBase]` |
| `load_plugins_from_directory` | 从目录加载插件 | 无 | `None` |
| `reload_plugin` | 重新加载插件 | `plugin_name: str` | `bool` |
| `stop_all_plugins` | 停止所有插件 | 无 | `None` |

## 4. 插件API（PluginAPI）规范

### 4.1 构造函数

```python
def __init__(self, plugin_manager: Any):
    """初始化插件API
    
    Args:
        plugin_manager: 插件管理器实例
    """
    self.plugin_manager = plugin_manager
    self.services: Dict[str, Any] = {}
    self.event_bus = EventBus()
```

### 4.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `register_service` | 注册服务 | `name: str`, `service: Any` | `None` |
| `get_service` | 获取服务 | `name: str` | `Any or None` |
| `get_plugin` | 获取插件 | `plugin_name: str` | `Any or None` |
| `get_all_plugins` | 获取所有插件 | 无 | `List[str]` |
| `send_event` | 发送事件 | `event_name: str`, `data: Any = None` | `None` |
| `subscribe` | 订阅事件 | `event_name: str`, `callback: Callable` | `str` |
| `unsubscribe` | 取消订阅 | `handler_id: str` | `bool` |
| `publish` | 发布事件 | `event_name: str`, `data: Any = None` | `bool` |
| `publish_async` | 异步发布事件 | `event_name: str`, `data: Any = None` | `bool` |
| `log` | 记录日志 | `message: str`, `level: str = "info"` | `None` |

## 5. 插件清单文件（manifest.json）规范

### 5.1 必需字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `string` | 插件名称（唯一标识符） |
| `version` | `string` | 插件版本（遵循语义化版本 X.Y.Z） |
| `description` | `string` | 插件描述 |

### 5.2 可选字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `author` | `string` | 插件作者 |
| `load_type` | `string` | 加载类型：`hot`（热加载）或 `restart`（重启加载），默认为 `hot` |
| `permissions` | `array` | 所需权限列表，如 `["database:read", "database:write"]` |
| `config_schema` | `object` | 配置模式定义 |
| `main` | `string` | 插件主模块文件路径，默认为 `plugin.py` |
| `frontend_entry` | `string` | 前端入口文件路径，默认为 `frontend/index.html` |

### 5.3 示例

```json
{
  "name": "example_plugin",
  "version": "1.0.0",
  "description": "示例插件，演示插件系统的基本功能",
  "author": "QuantCell Team",
  "main": "plugin.py",
  "load_type": "hot",
  "permissions": ["database:read"],
  "config_schema": {},
  "frontend_entry": "frontend/index.html"
}
```

## 6. 插件实现规范

### 6.1 核心要求

1. **必须**继承 `PluginBase` 类
2. **必须**提供 `register_plugin` 函数作为插件入口
3. **必须**在 `manifest.json` 中定义插件信息
4. **建议**使用 `self.logger` 进行日志记录
5. **必须**实现 `on_enable` 和 `on_disable` 生命周期方法

### 6.2 插件入口函数

```python
def register_plugin(api: PluginAPI) -> PluginBase:
    """注册插件的入口函数
    
    Args:
        api: 插件API实例
    
    Returns:
        插件实例
    """
    return ExamplePlugin(api)
```

### 6.3 路由注册

插件可以通过 `router` 属性注册 FastAPI 路由：

```python
from fastapi import APIRouter
from plugins.plugin_base import PluginBase
from plugins.api import PluginAPI

class ExamplePlugin(PluginBase):
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "example_plugin"
        self.version = "1.0.0"
        self.description = "示例插件"
        self.author = "QuantCell Team"
        self.load_type = LoadType.HOT
        self.router = APIRouter(prefix="/api/plugins/example")
        self._setup_routes()
    
    def _setup_routes(self):
        @self.router.get("/")
        async def example_root():
            return {"message": "Hello from example plugin!"}
    
    async def on_enable(self):
        """插件启用时调用"""
        self.enabled = True
        self.logger.info(f"{self.name} 插件已启用")
    
    async def on_disable(self):
        """插件禁用时调用"""
        self.enabled = False
        self.logger.info(f"{self.name} 插件已禁用")
```

## 7. 插件生命周期管理

### 7.1 生命周期流程

1. **安装**：插件安装器解压插件到目录
2. **扫描**：插件管理器扫描插件目录
3. **加载**：动态导入插件模块，调用 `register_plugin` 函数
4. **启用**：调用插件的 `on_enable` 方法
5. **运行**：插件处于活动状态
6. **禁用**：调用插件的 `on_disable` 方法
7. **卸载**：插件管理器移除插件

### 7.2 生命周期事件

| 事件 | 触发时机 | 处理方法 |
|------|----------|----------|
| `on_enable` | 插件启用时 | `on_enable()` |
| `on_disable` | 插件禁用时 | `on_disable()` |

### 7.3 加载类型

| 类型 | 描述 | 使用场景 |
|------|------|----------|
| `hot` | 热加载 | 插件可以在运行时加载/卸载，无需重启系统 |
| `restart` | 重启加载 | 插件需要重启系统才能加载/卸载 |

## 8. 插件间通信机制

### 8.1 服务注册与发现

插件可以注册服务供其他插件使用：

```python
# 注册服务
plugin_api.register_service("my_service", MyService())

# 发现服务
my_service = plugin_api.get_service("my_service")
```

### 8.2 事件总线（EventBus）

`EventBus` 是全局事件总线，提供线程安全的发布/订阅事件系统，使用 `threading.Lock` 确保线程安全。

#### 8.2.1 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `subscribe` | 订阅事件 | `event_name: str`, `callback: Callable` | `str` (handler_id) |
| `unsubscribe` | 取消订阅 | `handler_id: str` | `bool` |
| `publish` | 同步发布事件 | `event_name: str`, `data: Any = None` | `bool` |
| `publish_async` | 异步发布事件 | `event_name: str`, `data: Any = None` | `bool` |

**异常隔离**：EventBus 在事件处理过程中提供异常隔离机制。当某个事件处理器抛出异常时，不会影响其他事件处理器的执行，确保系统的稳定性。

#### 8.2.2 使用示例

```python
# 订阅事件
handler_id = plugin_api.subscribe("data_updated", my_callback)

# 发布事件（同步）
plugin_api.publish("data_updated", {"key": "value"})

# 发布事件（异步）
plugin_api.publish_async("data_updated", {"key": "value"})

# 取消订阅
plugin_api.unsubscribe(handler_id)
```

### 8.3 事件系统（兼容旧版本）

插件可以发送事件给所有插件：

```python
# 发送事件
plugin_api.send_event("data_updated", {"key": "value"})
```

## 9. 插件存储（PluginStore）规范

`PluginStore` 基于 SQLAlchemy ORM 的持久化存储，支持插件元数据的增删改查。

### 9.1 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `save_plugin` | 保存插件信息 | `plugin_name: str`, `manifest: dict`, `install_path: str` | `bool` |
| `get_plugin` | 获取插件信息 | `plugin_name: str` | `dict or None` |
| `get_all_plugins` | 获取所有插件信息 | 无 | `List[dict]` |
| `update_status` | 更新插件状态 | `plugin_name: str`, `status: str` | `bool` |
| `delete_plugin` | 删除插件信息 | `plugin_name: str` | `bool` |

### 9.2 使用示例

```python
from plugins.plugin_store import PluginStore

store = PluginStore()

# 保存插件信息
store.save_plugin("example_plugin", {"name": "example_plugin", "version": "1.0.0"}, "/path/to/plugin")

# 获取插件信息
plugin_info = store.get_plugin("example_plugin")

# 获取所有插件信息
all_plugins = store.get_all_plugins()

# 更新插件状态
store.update_status("example_plugin", "enabled")

# 删除插件信息
store.delete_plugin("example_plugin")
```

## 10. 插件安全（PluginSecurity）规范

`PluginSecurity` 提供权限枚举、权限校验、路由冲突检测和沙箱执行。

### 10.1 权限枚举（PluginPermission）

```python
from enum import Enum

class PluginPermission(Enum):
    """插件权限枚举"""
    DATABASE_READ = "database:read"  # 数据库读取权限
    DATABASE_WRITE = "database:write"  # 数据库写入权限
    API_INTERNAL = "api:internal"  # 内部API访问权限
    FILESYSTEM_READ = "filesystem:read"  # 文件系统读取权限
    FILESYSTEM_WRITE = "filesystem:write"  # 文件系统写入权限
    NETWORK_OUTBOUND = "network:outbound"  # 网络出站访问权限
```

### 10.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `validate_permissions` | 校验插件权限 | `permissions: List[str]` | `bool` |
| `check_system_route_conflict` | 检测路由冲突 | `route_prefix: str` | `bool` |
| `PluginSandbox` | 沙箱执行环境 | - | - |

### 10.3 使用示例

```python
from plugins.plugin_security import PluginSecurity, PluginPermission

security = PluginSecurity()

# 校验插件权限
permissions = [PluginPermission.DATABASE_READ.value, PluginPermission.DATABASE_WRITE.value]
is_valid = security.validate_permissions(permissions)

# 检测路由冲突
route_prefix = "/api/plugins/example"
has_conflict = security.check_system_route_conflict(route_prefix)

# 沙箱执行
with PluginSandbox() as sandbox:
    result = sandbox.execute(plugin_function, *args, **kwargs)
```

## 11. 插件安装器（PluginInstaller）规范

`PluginInstaller` 支持从 ZIP 文件、字节数据和 Git 仓库安装插件。

### 11.1 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `install_from_zip` | 从 ZIP 文件安装 | `zip_path: Path` | `bool` |
| `install_from_zip_bytes` | 从字节数据安装 | `zip_bytes: bytes`, `filename: str` | `bool` |
| `install_from_git` | 从 Git 仓库安装 | `git_url: str`, `branch: str = "main"` | `bool` |

### 11.2 使用示例

```python
from plugins.plugin_installer import PluginInstaller

installer = PluginInstaller(plugin_manager)

# 从 ZIP 文件安装
installer.install_from_zip(Path("/path/to/plugin.zip"))

# 从字节数据安装
with open("/path/to/plugin.zip", "rb") as f:
    zip_bytes = f.read()
installer.install_from_zip_bytes(zip_bytes, "plugin.zip")

# 从 Git 仓库安装
installer.install_from_git("https://github.com/example/plugin.git", branch="main")
```

## 12. 热加载/重启加载机制

### 12.1 加载类型

| 类型 | 描述 | 使用场景 |
|------|------|----------|
| `LoadType.HOT` | 热加载 | 插件可以在运行时加载/卸载，无需重启系统 |
| `LoadType.RESTART` | 重启加载 | 插件需要重启系统才能加载/卸载 |

### 12.2 加载器实现

- **HotPluginLoader**：热加载器，支持运行时加载/卸载插件
- **RestartPluginLoader**：重启加载器，需要重启系统才能加载/卸载插件

### 12.3 使用示例

```python
from plugins.plugin_base import PluginBase, LoadType

class ExamplePlugin(PluginBase):
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "example_plugin"
        self.load_type = LoadType.HOT  # 设置为热加载
```

## 13. 插件独立开发服务器

`plugin_dev.py` 提供插件独立开发服务器，方便插件开发者进行本地开发和调试。

### 13.1 启动命令

```bash
cd backend && python -m plugins.plugin_dev --plugin example_plugin --port 8001
```

### 13.2 参数说明

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `--plugin` | 插件名称 | 无（必填） |
| `--port` | 服务端口 | 8001 |
| `--host` | 监听地址 | 0.0.0.0 |

## 14. 错误处理和日志记录

### 14.1 日志记录

插件应使用内置的 logger 进行日志记录：

```python
self.logger.info("插件初始化完成")
self.logger.error("操作失败", exc_info=True)
```

### 14.2 错误处理

插件应妥善处理异常，避免影响整个系统：

```python
try:
    # 插件逻辑
    pass
except Exception as e:
    self.logger.error(f"处理失败: {e}")
    # 适当的错误处理
```

## 15. 插件开发最佳实践

### 15.1 代码组织

- **模块化**：将功能分解为多个模块
- **关注点分离**：将路由、业务逻辑、数据访问分离
- **文档化**：为公共API提供清晰的文档

### 15.2 性能优化

- **延迟加载**：只在需要时加载资源
- **缓存**：合理使用缓存减少重复计算
- **异步处理**：对于IO密集型操作使用异步方法

### 15.3 安全性

- **输入验证**：验证所有用户输入
- **权限控制**：遵循最小权限原则
- **安全编码**：避免常见的安全漏洞

## 16. 插件兼容性要求

### 11.1 Python 版本

- 支持 Python 3.8+

### 11.2 依赖管理

- 插件依赖应在 `manifest.json` 中声明
- 避免与核心依赖冲突

### 11.3 API 兼容性

- 遵循文档中定义的 API 规范
- 向后兼容旧版本 API

### 11.4 安全要求

- 插件必须声明所需权限（`permissions`）
- 路由前缀不得与系统核心路由冲突
- 插件代码在沙箱中执行，异常不会影响系统稳定性

## 12. 插件部署和集成流程

### 12.1 部署步骤

1. **创建插件目录**：在 `backend/plugins/` 下创建插件目录
2. **编写插件代码**：实现插件核心逻辑
3. **配置清单文件**：编写 `manifest.json` 文件
4. **安装插件**：通过 API 或插件管理界面安装插件
5. **启用插件**：通过 API 或插件管理界面启用插件

### 12.2 安装方式

- **ZIP 文件安装**：通过 `PluginInstaller.install_from_zip` 安装
- **字节数据安装**：通过 `PluginInstaller.install_from_zip_bytes` 安装
- **Git 仓库安装**：通过 `PluginInstaller.install_from_git` 安装

### 12.3 集成测试

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
from plugins.plugin_base import PluginBase, LoadType
from plugins.api import PluginAPI

class ExamplePlugin(PluginBase):
    """示例插件，演示插件系统的基本功能"""
    
    def __init__(self, api: PluginAPI):
        """初始化示例插件"""
        super().__init__(api)
        self.name = "example_plugin"
        self.version = "1.0.0"
        self.description = "示例插件，演示插件系统的基本功能"
        self.author = "QuantCell Team"
        self.load_type = LoadType.HOT
        # 创建API路由
        self.router = APIRouter(prefix="/api/plugins/example")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        @self.router.get("/")
        async def example_root():
            """示例根路由"""
            return {
                "message": "Hello from example plugin!",
                "plugin_name": self.name,
                "version": self.version
            }
        
        @self.router.get("/test")
        async def example_test():
            """示例测试路由"""
            return {
                "test": "success",
                "data": {
                    "key1": "value1",
                    "key2": "value2"
                }
            }
    
    async def on_enable(self):
        """插件启用时调用"""
        self.enabled = True
        self.logger.info(f"{self.name} 插件已启用")
    
    async def on_disable(self):
        """插件禁用时调用"""
        self.enabled = False
        self.logger.info(f"{self.name} 插件已禁用")

def register_plugin(api: PluginAPI):
    """注册插件的入口函数"""
    return ExamplePlugin(api)
```

### 15.2 插件管理器配置

| 配置项 | 描述 | 默认值 |
|--------|------|--------|
| `plugin_dir` | 插件目录路径 | `data/plugins` |
| `auto_load` | 是否自动加载插件 | `True` |
| `hot_reload` | 是否支持热重载 | `True` |