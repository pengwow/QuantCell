# 插件系统架构概述

## 1. 插件系统总览

QuantCell 项目采用了模块化的插件系统，允许开发者通过创建插件来扩展系统功能。插件系统分为后端插件和前端插件两部分，它们各自有独立的开发规范和运行环境，但可以通过统一的接口进行通信和集成。

### 1.1 插件系统的核心优势

- **模块化设计**：插件可以独立开发、测试和部署
- **扩展性强**：新功能可以通过插件形式添加，无需修改核心代码
- **灵活性高**：插件可以根据需要启用或禁用
- **生态丰富**：第三方开发者可以创建兼容的插件

## 2. 插件系统架构

### 2.1 后端插件系统架构

后端插件系统基于 Python 和 FastAPI 构建，主要包含以下核心组件：

#### 2.1.1 核心组件

| 组件 | 职责 | 文件路径 |
|------|------|----------|
| 插件管理器 | 扫描、加载、初始化和管理插件 | `/backend/plugins/plugin_manager.py` |
| 插件基类 | 定义插件的生命周期方法和API | `/backend/plugins/plugin_base.py` |
| 插件加载器 | 动态导入插件模块，支持热加载和重启加载 | `/backend/plugins/plugin_loader.py` |
| 事件总线 | 全局事件发布/订阅机制 | `/backend/plugins/event_bus.py` |
| 插件存储 | 插件持久化存储，基于 SQLAlchemy ORM | `/backend/plugins/plugin_store.py` |
| 插件安全 | 权限校验、路由冲突检测、沙箱执行 | `/backend/plugins/plugin_security.py` |
| 插件安装器 | 支持从 ZIP 包或 Git 仓库安装插件 | `/backend/plugins/plugin_installer.py` |
| 插件路由 | 注册插件的API路由 | 插件内部定义 |

#### 2.1.2 EventBus 事件总线

EventBus 是全局事件总线，用于插件间的松耦合通信。

**核心特性：**
- 支持 `subscribe`/`unsubscribe`/`publish`/`publish_async` 四种操作
- 使用 `threading.Lock` 保证线程安全
- 异常隔离：单个订阅者回调异常不影响其他订阅者

```python
from backend.plugins.event_bus import EventBus

bus = EventBus()

# 订阅事件
def on_data_received(data):
    print(f"收到数据: {data}")

bus.subscribe("data.received", on_data_received)

# 发布事件（同步）
bus.publish("data.received", {"symbol": "BTCUSDT", "price": 50000})

# 发布事件（异步，线程池执行）
bus.publish_async("data.received", {"symbol": "ETHUSDT", "price": 3000})

# 取消订阅
bus.unsubscribe("data.received", on_data_received)
```

#### 2.1.3 PluginStore 持久化存储

PluginStore 是插件持久化存储层，基于 SQLAlchemy ORM，采用静态方法类设计。

**核心方法：**
- `save_plugin(metadata)` - 保存或更新插件元数据
- `get_plugin(name)` - 获取单个插件信息
- `get_all_plugins()` - 获取所有插件列表
- `update_status(name, status, error_message)` - 更新插件状态
- `delete_plugin(name)` - 删除插件记录
- `update_plugin(name, **kwargs)` - 更新插件任意字段

**数据库模型字段：**
- `name` - 插件名称（唯一标识）
- `version` - 版本号
- `description` - 插件描述
- `author` - 作者
- `load_type` - 加载类型（hot/restart）
- `status` - 状态（installed/active/disabled/error）
- `install_source` - 安装来源（manual/zip/git）
- `install_path` - 安装路径
- `permissions` - 权限列表（JSON）
- `config_schema` - 配置模式（JSON）
- `frontend_entry` - 前端入口
- `error_message` - 错误信息
- `installed_at` - 安装时间
- `updated_at` - 更新时间

```python
from backend.plugins.plugin_store import PluginStore

# 保存插件
PluginStore.save_plugin({
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "我的插件",
    "author": "开发者",
    "load_type": "hot",
    "status": "installed",
    "install_source": "manual",
    "install_path": "/path/to/plugin",
    "permissions": ["database:read"],
})

# 获取插件
plugin = PluginStore.get_plugin("my-plugin")

# 获取所有插件
all_plugins = PluginStore.get_all_plugins()

# 更新状态
PluginStore.update_status("my-plugin", "active")
```

#### 2.1.4 PluginSecurity 安全组件

PluginSecurity 提供插件权限管理和安全校验功能。

**权限枚举（PluginPermission）：**
- `database:read` - 数据库读取权限
- `database:write` - 数据库写入权限
- `api:internal` - 内部 API 访问权限
- `filesystem:read` - 文件系统读取权限
- `filesystem:write` - 文件系统写入权限
- `network:outbound` - 网络出站权限

**核心功能：**
- `validate_permissions(permissions)` - 校验权限列表是否合法
- `check_system_route_conflict(router_prefix)` - 检测路由前缀是否与系统路由冲突
- `PluginSandbox` - 插件沙箱执行环境，隔离插件执行异常

**系统保护路由前缀：**
- `/api/config` - 系统配置
- `/api/system` - 系统管理
- `/api/auth` - 认证授权
- `/api/workers` - 工作节点
- `/api/logs` - 日志管理
- `/api/notifications` - 通知管理
- `/api/system-ports` - 系统端口
- `/ws` - WebSocket

```python
from backend.plugins.plugin_security import (
    validate_permissions,
    check_system_route_conflict,
    PluginSandbox,
)

# 校验权限
valid, msg = validate_permissions(["database:read", "network:outbound"])
# valid=True, msg=""

valid, msg = validate_permissions(["invalid:permission"])
# valid=False, msg="不支持的权限: invalid:permission"

# 检测路由冲突
ok, msg = check_system_route_conflict("/api/my-plugin")
# ok=False, msg="路由前缀 /api/my-plugin 与系统核心路由冲突"

ok, msg = check_system_route_conflict("/plugins/my-plugin")
# ok=True, msg=""

# 沙箱执行
sandbox = PluginSandbox("my-plugin", logger)
result = sandbox.execute(risky_function, arg1, arg2)
# 异常时返回 None，不影响系统

success, result = sandbox.execute_safe(risky_function, arg1, arg2)
# success=False, result="ErrorType: error message"
```

#### 2.1.5 热加载/重启加载机制

插件系统支持两种加载类型，通过 `manifest.json` 中的 `load_type` 字段指定：

| 加载类型 | 说明 | 加载器类 | 使用场景 |
|----------|------|----------|----------|
| `hot` | 热加载，无需重启应用 | `HotPluginLoader` | 大多数插件，开发调试 |
| `restart` | 重启加载，需要重启应用生效 | `RestartPluginLoader` | 有特殊依赖或初始化要求的插件 |

**HotPluginLoader（热加载器）：**
- 支持在应用运行时动态加载插件
- 加载后立即生效，无需重启
- 模块名前缀：`plugins.hot.{plugin_name}`
- 适合大多数业务插件

**RestartPluginLoader（重启加载器）：**
- 插件安装后需要重启应用才能生效
- 加载失败时仅记录警告，不影响系统启动
- 模块名前缀：`plugins.restart.{plugin_name}`
- 适合有特殊系统级依赖的插件

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "load_type": "hot",
  "main": "plugin.py"
}
```

#### 2.1.6 工作流程

**后端插件安装流程：**

1. **接收安装请求**：通过 API 接收 ZIP 包或 Git 仓库地址
2. **解压/克隆**：将插件文件解压或克隆到临时目录
3. **读取 manifest.json**：解析插件清单文件
4. **校验权限**：调用 `validate_permissions` 校验权限声明
5. **校验版本**：检查 `min_system_version` 与系统版本兼容性
6. **路由冲突检测**：调用 `check_system_route_conflict` 检测路由前缀
7. **安装到数据库**：调用 `PluginStore.save_plugin` 保存元数据
8. **发布事件**：通过 `EventBus` 发布 `plugin.installed` 事件
9. **根据 load_type 选择加载器**：hot 使用 `HotPluginLoader`，restart 使用 `RestartPluginLoader`
10. **动态导入模块**：使用 `importlib` 动态导入插件入口文件
11. **注册路由**：将插件的 `APIRouter` 注册到 FastAPI 应用
12. **更新状态**：更新插件状态为 `active`

**后端插件运行时流程：**

1. **应用启动**：`PluginManager` 初始化
2. **从数据库加载**：调用 `PluginStore.get_all_plugins` 获取所有已安装插件
3. **过滤禁用插件**：跳过状态为 `disabled` 的插件
4. **选择加载器**：根据 `load_type` 选择 `HotPluginLoader` 或 `RestartPluginLoader`
5. **动态导入**：加载并执行插件入口模块
6. **创建实例**：调用 `register_plugin()` 创建 `PluginBase` 实例
7. **注册路由**：将插件路由注册到 FastAPI
8. **发布事件**：发布 `plugin.loaded` 事件

### 2.2 前端插件系统架构

前端插件系统基于 React、TypeScript 和 Ant Design 构建，采用 React Context + 单例注册中心的架构模式。

#### 2.2.1 核心组件

| 组件 | 职责 | 文件路径 |
|------|------|----------|
| PluginContext | 全局插件状态管理（React Context） | `/frontend/src/plugins/PluginContext.tsx` |
| PluginRegistry | 单例注册中心，管理插件/菜单/路由 | `/frontend/src/plugins/PluginRegistry.ts` |
| PluginLoader | 动态资源加载器，加载插件 JS/CSS | `/frontend/src/plugins/PluginLoader.ts` |
| pluginApi | API 客户端，封装 REST API 调用 | `/frontend/src/api/plugin.ts` |
| SSE 事件推送 | 实时监听插件状态变更 | `/frontend/src/api/plugin.ts` |

#### 2.2.2 PluginContext 全局状态管理

PluginContext 使用 React Context 提供全局插件状态，通过 `PluginProvider` 组件和 `usePlugins()` Hook 消费。

**提供的状态和方法：**
- `plugins` - 插件列表（`PluginInfo[]`）
- `loading` - 加载状态
- `refresh()` - 刷新插件列表
- `enablePlugin(name)` - 启用插件
- `disablePlugin(name)` - 禁用插件

```tsx
import { PluginProvider, usePlugins } from '@/plugins';

// 在应用根组件中挂载 Provider
function App() {
  return (
    <PluginProvider>
      <MyApp />
    </PluginProvider>
  );
}

// 在子组件中使用
function PluginList() {
  const { plugins, loading, refresh, enablePlugin, disablePlugin } = usePlugins();

  if (loading) return <Spin />;

  return (
    <div>
      {plugins.map(p => (
        <div key={p.name}>
          {p.name} - {p.status}
          <button onClick={() => enablePlugin(p.name)}>启用</button>
          <button onClick={() => disablePlugin(p.name)}>禁用</button>
        </div>
      ))}
      <button onClick={refresh}>刷新</button>
    </div>
  );
}
```

#### 2.2.3 PluginRegistry 单例注册中心

PluginRegistry 是前端插件注册中心的单例实例，管理插件元数据、菜单项和路由。

**核心方法：**
- `registerPlugin(plugin)` - 注册插件
- `unregisterPlugin(name)` - 注销插件
- `registerMenu(item)` - 注册菜单项
- `registerRoute(route)` - 注册路由
- `getPlugin(name)` - 获取插件信息
- `getAllPlugins()` - 获取所有插件
- `getMenuItems()` - 获取所有菜单项
- `getRoutes()` - 获取所有路由
- `subscribe(listener)` - 订阅变更通知

```typescript
import { pluginRegistry, type PluginMenuItem, type PluginRoute } from '@/plugins';

// 注册插件
pluginRegistry.registerPlugin({
  name: 'my-plugin',
  version: '1.0.0',
  status: 'active',
  description: '我的插件',
  load_type: 'hot',
});

// 注册菜单项
const menuItem: PluginMenuItem = {
  key: 'my-plugin',
  label: '我的插件',
  icon: <SettingOutlined />,
  pluginName: 'my-plugin',
};
pluginRegistry.registerMenu(menuItem);

// 注册路由
const route: PluginRoute = {
  path: '/plugins/my-plugin',
  element: <MyPluginPage />,
  pluginName: 'my-plugin',
};
pluginRegistry.registerRoute(route);

// 订阅变更
const unsubscribe = pluginRegistry.subscribe(() => {
  console.log('插件列表已更新');
});
```

#### 2.2.4 PluginLoader 动态资源加载器

PluginLoader 负责动态加载插件的前端资源（JS 和 CSS）。

**核心功能：**
- `loadPluginAssets(plugin)` - 加载插件的 JS 和 CSS 资源
- `unloadPluginAssets(pluginName)` - 卸载插件资源
- 自动去重，避免重复加载
- CSS 加载失败不阻塞插件运行

```typescript
import { loadPluginAssets, unloadPluginAssets } from '@/plugins';

// 加载插件资源
await loadPluginAssets({
  name: 'my-plugin',
  version: '1.0.0',
  status: 'active',
  description: '我的插件',
  load_type: 'hot',
});

// 卸载插件资源
unloadPluginAssets('my-plugin');
```

#### 2.2.5 pluginApi API 客户端

pluginApi 封装了所有与后端插件系统交互的 REST API 调用。

**API 接口：**
- `getPlugins()` - 获取插件列表
- `installPlugin(file)` - 从 ZIP 文件安装插件
- `installFromGit(url, branch)` - 从 Git 仓库安装插件
- `enablePlugin(name)` - 启用插件
- `disablePlugin(name)` - 禁用插件
- `uninstallPlugin(name)` - 卸载插件

```typescript
import { pluginApi } from '@/api/plugin';

// 获取插件列表
const plugins = await pluginApi.getPlugins();

// 从 ZIP 文件安装
const file = new File([blob], 'plugin.zip');
await pluginApi.installPlugin(file);

// 从 Git 仓库安装
await pluginApi.installFromGit('https://github.com/user/plugin.git', 'main');

// 启用/禁用插件
await pluginApi.enablePlugin('my-plugin');
await pluginApi.disablePlugin('my-plugin');

// 卸载插件
await pluginApi.uninstallPlugin('my-plugin');
```

#### 2.2.6 SSE 事件推送

前端通过 Server-Sent Events (SSE) 实时监听后端插件状态变更。

**支持的事件类型：**
- `plugin.installed` - 插件安装完成
- `plugin.loaded` - 插件加载完成
- `plugin.unloaded` - 插件卸载完成
- `plugin.uninstalled` - 插件卸载并删除

```typescript
import { listenPluginEvents } from '@/api/plugin';

// 监听插件事件
const stopListening = listenPluginEvents((event) => {
  console.log('插件事件:', event.type, event.plugin_name);
  // 收到事件后刷新插件列表
});

// 停止监听
stopListening();
```

#### 2.2.7 工作流程

**前端插件系统初始化流程：**

1. **PluginProvider 挂载**：在应用根组件中挂载 `PluginProvider`
2. **调用 API 获取列表**：通过 `pluginApi.getPlugins()` 获取已安装插件列表
3. **注册到 PluginRegistry**：将每个插件注册到 `pluginRegistry`
4. **SSE 监听**：通过 `listenPluginEvents` 建立 SSE 连接，监听插件状态变更
5. **用户操作触发刷新**：用户启用/禁用/安装/卸载插件时，自动刷新列表

**前端插件安装流程：**

1. **用户选择文件**：在 `/setting/plugins` 页面选择 ZIP 文件或输入 Git 地址
2. **调用安装 API**：通过 `pluginApi.installPlugin` 或 `pluginApi.installFromGit` 发送请求
3. **后端处理**：后端完成插件校验、安装和加载
4. **SSE 事件通知**：后端通过 SSE 推送 `plugin.installed` 事件
5. **前端刷新**：收到事件后自动调用 `refresh()` 更新插件列表

## 3. 插件系统的核心概念

### 3.1 插件生命周期

无论是后端插件还是前端插件，都遵循以下生命周期：

1. **安装**：通过 ZIP 包或 Git 仓库安装插件到系统
2. **初始化**：创建插件实例，设置插件属性
3. **注册**：将插件注册到插件管理器，配置插件的基本信息
4. **启动**：启动插件，初始化插件的内部状态和资源
5. **运行**：插件处理请求和业务逻辑
6. **停止**：停止插件，释放资源
7. **卸载**：从系统中移除插件

### 3.2 插件清单文件

每个插件都需要一个 `manifest.json` 文件，用于描述插件的基本信息和配置：

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "我的插件描述",
  "author": "开发者",
  "main": "plugin.py",
  "load_type": "hot",
  "min_system_version": "1.0.0",
  "permissions": ["database:read", "network:outbound"],
  "config_schema": {
    "api_key": {
      "type": "string",
      "description": "API 密钥",
      "required": true
    }
  },
  "frontend_entry": "/plugins/my-plugin/index.js"
}
```

**字段说明：**
- `name` - 插件名称（必填，仅允许字母、数字、下划线、连字符）
- `version` - 版本号（必填）
- `description` - 插件描述
- `author` - 作者
- `main` - 入口文件（默认 `plugin.py`）
- `load_type` - 加载类型：`hot`（热加载）或 `restart`（重启加载）
- `min_system_version` - 最低系统版本要求
- `permissions` - 权限声明列表
- `config_schema` - 配置项模式定义
- `frontend_entry` - 前端资源入口路径

### 3.3 插件通信

#### 3.3.1 前后端插件通信

- **REST API**：前端通过 `pluginApi` 调用后端插件的 API
- **SSE 事件**：后端通过 `EventBus` 发布事件，前端通过 `listenPluginEvents` 实时接收

#### 3.3.2 插件间通信

- **EventBus**：通过事件总线进行松耦合通信
- **插件管理器**：通过 `PluginManager` 获取其他插件实例

### 3.4 插件安全性

- **权限控制**：插件需要在 `manifest.json` 中声明所需权限，系统在安装时校验
- **路由隔离**：插件路由前缀不能与系统核心路由冲突
- **沙箱执行**：使用 `PluginSandbox` 隔离插件执行异常，防止插件崩溃影响系统
- **输入验证**：插件需要对所有输入进行验证

### 3.5 插件管理 UI

插件管理 UI 提供可视化的插件管理界面，路由为 `/setting/plugins`。

**功能特性：**

| 功能 | 说明 |
|------|------|
| 插件列表 | 以卡片视图展示所有已安装插件，显示名称、版本、状态、作者、加载类型等信息 |
| 安装插件 | 支持从 ZIP 文件或 Git 仓库地址安装插件 |
| 启停控制 | 支持启用/禁用插件，实时更新插件状态 |
| 卸载插件 | 支持卸载已安装的插件，同时清理相关数据 |
| 详情查看 | 查看插件的详细信息，包括权限、配置模式、安装路径等 |

**插件状态说明：**

| 状态 | 说明 |
|------|------|
| `installed` | 已安装，未加载 |
| `active` | 已激活，正在运行 |
| `disabled` | 已禁用 |
| `error` | 加载或运行出错 |

## 4. 插件系统的扩展点

### 4.1 后端插件扩展点

- **API 路由**：添加新的 API 端点
- **数据处理**：扩展数据采集、处理和分析功能
- **业务逻辑**：添加新的业务逻辑和规则
- **外部集成**：集成外部服务和 API

### 4.2 前端插件扩展点

- **用户界面**：添加新的页面和组件
- **菜单导航**：扩展系统菜单
- **系统配置**：添加新的系统配置项
- **数据可视化**：添加新的数据可视化组件
- **用户交互**：扩展用户交互功能

## 5. 插件系统的未来发展

### 5.1 计划中的功能

- **插件市场**：集中管理和分发插件
- **插件版本控制**：支持插件的版本升级和回滚
- **插件依赖管理**：处理插件间的依赖关系
- **插件热重载**：无需重启应用即可更新插件
- **插件国际化**：支持多语言插件

### 5.2 技术演进

- **容器化**：插件可以打包为容器镜像
- **无服务器**：支持无服务器架构的插件
- **AI 集成**：支持 AI 能力的插件

## 6. 总结

QuantCell 项目的插件系统采用了模块化、可扩展的设计理念，为系统功能的扩展提供了灵活的机制。通过统一的插件接口和规范，开发者可以快速创建兼容的插件，丰富系统的功能和生态。

插件系统的架构设计考虑了前后端分离、模块化和可扩展性等因素，为未来的功能扩展和生态建设奠定了坚实的基础。