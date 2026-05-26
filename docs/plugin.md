# QuantCell 插件开发指南

## 1. 简介

QuantCell 插件系统允许开发者在现有框架中扩展新的菜单、页面和后端接口。插件系统支持前后端完整集成，具备以下核心能力：

- **插件生命周期管理**：安装、启用、禁用、卸载
- **热加载与重启加载**：支持运行时动态加载和需要重启的加载方式
- **多种安装方式**：ZIP 上传、Git 克隆、手动放置
- **权限与安全**：插件权限声明与沙箱隔离
- **事件通信**：通过 EventBus 实现插件间及插件与系统的事件通信
- **持久化存储**：插件元数据通过数据库持久化管理
- **前端管理 UI**：提供可视化的插件管理界面

本指南将详细介绍 QuantCell 插件的开发流程、架构设计和核心功能实现，帮助开发者快速上手插件开发。

## 2. 开发环境配置

### 2.1 前端环境

**系统要求**：
- Node.js >= 16.x
- Bun >= 1.0.0

**配置步骤**：

1. 安装依赖
   ```bash
   cd QuantCell/frontend
   bun install
   ```

2. 构建验证
   ```bash
   bun run build
   ```

### 2.2 后端环境

**系统要求**：
- Python >= 3.10
- uv >= 0.1.0

**配置步骤**：

1. 安装依赖
   ```bash
   cd QuantCell/backend
   uv install
   ```

2. 启动开发服务器
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## 3. 项目结构说明

### 3.1 项目根目录结构

```
QuantCell/
├── backend/                  # 后端代码
│   ├── plugins/              # 后端插件系统及插件目录
│   ├── main.py               # 后端入口文件
│   └── ...
├── frontend/                 # 前端代码
│   ├── src/
│   │   ├── plugins/          # 前端插件框架
│   │   ├── api/plugin.ts     # 插件 API 客户端
│   │   ├── pages/setting/
│   │   │   └── PluginManagement.tsx  # 插件管理页面
│   │   └── ...
│   └── ...
└── docs/                     # 文档目录
    └── plugin.md             # 插件开发指南
```

### 3.2 后端插件目录结构

```
backend/plugins/
├── __init__.py               # 插件系统入口，导出核心模块
├── plugin_base.py            # 插件基类 PluginBase
├── plugin_manager.py         # 插件管理器 PluginManager
├── plugin_loader.py          # 插件加载器（HotPluginLoader / RestartPluginLoader）
├── plugin_installer.py       # 插件安装器（ZIP / Git）
├── plugin_store.py           # 插件持久化存储 PluginStore
├── plugin_security.py        # 权限校验与沙箱 PluginSecurity
├── event_bus.py              # 事件总线 EventBus
├── api.py                    # 插件 API（服务注册、事件通信）
├── routes.py                 # 插件 REST API 路由
├── plugin_dev.py             # 插件独立开发/调试工具
└── example_plugin/           # 示例后端插件
    ├── __init__.py
    ├── plugin.py             # 插件入口
    └── manifest.json         # 插件清单
```

### 3.3 前端插件目录结构

```
frontend/src/
├── plugins/                  # 前端插件框架
│   ├── index.ts              # 统一导出
│   ├── PluginContext.tsx      # 插件 React Context（PluginProvider / usePlugins）
│   ├── PluginRegistry.ts     # 插件注册表（菜单、路由管理）
│   └── PluginLoader.ts       # 插件资源加载器（JS/CSS 动态加载）
├── api/
│   └── plugin.ts             # 插件 API 客户端（pluginApi + SSE 事件监听）
└── pages/setting/
    └── PluginManagement.tsx  # 插件管理页面（卡片视图、安装、启停、卸载）
```

## 4. 插件开发流程

### 4.1 后端插件开发流程

#### 步骤 1：创建插件目录

```bash
mkdir -p backend/plugins/my_backend_plugin
```

#### 步骤 2：编写插件清单

**文件路径**：`backend/plugins/my_backend_plugin/manifest.json`

```json
{
  "name": "my-backend-plugin",
  "version": "1.0.0",
  "description": "我的后端插件",
  "author": "开发者",
  "main": "plugin.py",
  "load_type": "hot",
  "min_system_version": "1.0.0",
  "permissions": [],
  "config_schema": null,
  "frontend_entry": null,
  "dependencies": []
}
```

**manifest.json 字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 插件名称，仅允许字母、数字、下划线、连字符 |
| `version` | string | 是 | 版本号，需符合 X.Y.Z 格式 |
| `description` | string | 否 | 插件描述 |
| `author` | string | 否 | 作者 |
| `main` | string | 否 | 入口文件，默认 `plugin.py` |
| `load_type` | string | 否 | 加载方式：`hot`（热加载）或 `restart`（重启加载），默认 `hot` |
| `min_system_version` | string | 否 | 最低系统版本要求 |
| `permissions` | string[] | 否 | 声明的权限列表 |
| `config_schema` | object | 否 | 配置项 JSON Schema |
| `frontend_entry` | string | 否 | 前端资源入口路径 |
| `dependencies` | string[] | 否 | 依赖的其他插件 |

#### 步骤 3：实现插件类

**文件路径**：`backend/plugins/my_backend_plugin/plugin.py`

```python
from fastapi import APIRouter
from plugins.plugin_base import PluginBase


class MyBackendPlugin(PluginBase):
    def __init__(self):
        super().__init__("my-backend-plugin", "1.0.0")
        self.router = APIRouter(prefix="/api/plugins/my-backend")
        self._setup_routes()

    def _setup_routes(self):
        @self.router.get("/")
        def plugin_root():
            return {
                "message": "Hello from my backend plugin!",
                "plugin_name": self.name,
                "version": self.version,
            }

    def register(self, plugin_manager):
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")

    def start(self):
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")

    def stop(self):
        super().stop()
        self.logger.info(f"{self.name} 插件停止成功")


def register_plugin():
    return MyBackendPlugin()
```

> **重要约定**：每个后端插件的入口文件必须包含 `register_plugin()` 函数，且返回值必须是 `PluginBase` 的实例。

#### 步骤 4（可选）：独立开发调试

QuantCell 提供了插件独立开发工具 `plugin_dev.py`，无需启动完整系统即可调试插件：

```bash
cd QuantCell/backend
python -m plugins.plugin_dev run --plugin-dir plugins/my_backend_plugin --port 9000 --reload
```

启动后可访问：
- 健康检查：`GET http://localhost:9000/dev/health`
- 手动重载：`POST http://localhost:9000/dev/reload`

启用 `--reload` 参数后，工具会自动监控 `manifest.json` 和入口文件的变更，文件修改时自动重载插件。

### 4.2 前端插件开发流程

前端插件采用与后端完全不同的架构。前端不再需要继承 `PluginBase` 类，而是通过以下三个核心机制实现：

- **pluginApi**：调用后端插件 REST API
- **PluginRegistry**：注册菜单和路由
- **usePlugins()**：获取插件状态

#### 步骤 1：创建插件页面组件

**文件路径**：`frontend/src/plugins/my-frontend-plugin/components/MyPage.tsx`

```tsx
import React from 'react';
import { Card, Typography } from 'antd';

const { Title, Paragraph } = Typography;

export const MyPage: React.FC = () => {
  return (
    <div style={{ padding: '20px' }}>
      <Card title="我的插件页面">
        <Title level={3}>欢迎使用我的插件</Title>
        <Paragraph>
          这是一个使用 QuantCell 插件系统开发的前端插件页面。
        </Paragraph>
      </Card>
    </div>
  );
};
```

#### 步骤 2：注册菜单和路由

**文件路径**：`frontend/src/plugins/my-frontend-plugin/index.ts`

```tsx
import { pluginRegistry } from '@/plugins';
import { MyPage } from './components/MyPage';

// 注册菜单项
pluginRegistry.registerMenu({
  key: 'my-frontend-plugin',
  label: '我的页面',
  pluginName: 'my-frontend-plugin',
});

// 注册路由
pluginRegistry.registerRoute({
  path: '/plugins/my-frontend',
  element: <MyPage />,
  pluginName: 'my-frontend-plugin',
});
```

#### 步骤 3：在页面中使用插件状态

在任何需要感知插件状态的组件中，使用 `usePlugins()` Hook：

```tsx
import { usePlugins } from '@/plugins';

function MyComponent() {
  const { plugins, loading, refresh, enablePlugin, disablePlugin } = usePlugins();

  if (loading) return <div>加载中...</div>;

  return (
    <ul>
      {plugins.map((p) => (
        <li key={p.name}>
          {p.name} - {p.status}
        </li>
      ))}
    </ul>
  );
}
```

## 5. 核心功能模块

### 5.1 后端核心组件

#### PluginBase 基类

**文件路径**：`backend/plugins/plugin_base.py`

所有后端插件必须继承 `PluginBase`，它定义了插件的生命周期和元数据接口。

**核心属性与方法**：

| 成员 | 类型 | 描述 |
|------|------|------|
| `name` | `str` | 插件名称 |
| `version` | `str` | 插件版本 |
| `load_type` | `str` | 加载方式，`hot` 或 `restart` |
| `is_active` | `bool` | 是否处于激活状态 |
| `logger` | `Logger` | 带插件名称绑定的日志器 |
| `register(plugin_manager)` | 方法 | 注册插件，注入 plugin_manager 引用 |
| `start()` | 方法 | 启动插件 |
| `stop()` | 方法 | 停止插件 |
| `on_enable()` | 方法 | 启用时回调 |
| `on_disable()` | 方法 | 禁用时回调 |
| `get_frontend_assets()` | 方法 | 返回前端资源信息 |
| `get_config_schema()` | 方法 | 返回配置 JSON Schema |
| `get_info()` | 方法 | 获取基本插件信息 |
| `get_metadata()` | 方法 | 获取完整插件元数据 |

#### PluginManager 管理器

**文件路径**：`backend/plugins/plugin_manager.py`

`PluginManager` 是插件系统的核心管理器，负责插件的全生命周期管理。

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `scan_plugins` | 扫描插件目录发现新插件 | - | `List[str]` |
| `load_plugin` | 加载指定插件 | `plugin_name: str` | `Optional[PluginBase]` |
| `load_all_plugins` | 从数据库加载所有已注册插件 | - | `None` |
| `unload_plugin` | 卸载指定插件 | `plugin_name: str` | `bool` |
| `install_plugin` | 安装插件（校验 + 注册 + 加载） | `plugin_dir_path, manifest, source_type` | `bool` |
| `uninstall_plugin` | 卸载并删除插件 | `plugin_name: str` | `bool` |
| `enable_plugin` | 启用插件 | `plugin_name: str` | `bool` |
| `disable_plugin` | 禁用插件 | `plugin_name: str` | `bool` |
| `install_from_zip` | 从 ZIP 文件安装 | `zip_file_path: str` | `tuple[bool, str]` |
| `install_from_zip_bytes` | 从 ZIP 字节数据安装 | `zip_bytes: bytes` | `tuple[bool, str]` |
| `install_from_git` | 从 Git 仓库安装 | `git_url, branch` | `tuple[bool, str]` |
| `register_plugins` | 注册所有已加载插件的路由到 FastAPI | `app: FastAPI` | `None` |
| `stop_all_plugins` | 停止所有插件 | - | `None` |

#### PluginLoader 加载器

**文件路径**：`backend/plugins/plugin_loader.py`

系统根据 `manifest.json` 中的 `load_type` 字段自动选择加载器：

- **HotPluginLoader**：热加载器，支持运行时动态加载/卸载插件，无需重启应用。加载的模块注册在 `plugins.hot.<name>` 命名空间下。
- **RestartPluginLoader**：重启加载器，适用于需要在启动时初始化的插件。加载的模块注册在 `plugins.restart.<name>` 命名空间下。

两种加载器都会自动将插件的 `APIRouter`（如果存在）注册到 FastAPI 应用中。

### 5.2 前端核心组件

#### PluginContext（插件上下文）

**文件路径**：`frontend/src/plugins/PluginContext.tsx`

提供 React Context，管理插件列表状态和插件操作方法。

**导出成员**：

| 名称 | 类型 | 描述 |
|------|------|------|
| `PluginProvider` | React 组件 | 插件上下文 Provider，包裹在应用顶层 |
| `usePlugins()` | Hook | 获取插件上下文，返回以下对象 |

**`usePlugins()` 返回值**：

```typescript
interface PluginContextValue {
  plugins: PluginInfo[];               // 当前插件列表
  loading: boolean;                     // 是否正在加载
  refresh: () => Promise<void>;         // 刷新插件列表
  enablePlugin: (name: string) => Promise<void>;   // 启用插件
  disablePlugin: (name: string) => Promise<void>;  // 禁用插件
}
```

`PluginProvider` 在初始化时会自动调用后端 API 获取插件列表，并通过 SSE 监听插件事件（安装、卸载、加载、错误等），保持前端状态与后端同步。

#### PluginRegistry（插件注册表）

**文件路径**：`frontend/src/plugins/PluginRegistry.ts`

全局单例，管理前端插件的菜单项和路由。

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `registerPlugin(plugin)` | 注册插件信息 | `PluginInfo` | `void` |
| `unregisterPlugin(name)` | 注销插件及其菜单和路由 | `string` | `void` |
| `registerMenu(item)` | 注册菜单项 | `PluginMenuItem` | `void` |
| `registerRoute(route)` | 注册路由 | `PluginRoute` | `void` |
| `getPlugin(name)` | 获取插件信息 | `string` | `PluginInfo \| undefined` |
| `getAllPlugins()` | 获取所有插件 | - | `PluginInfo[]` |
| `getMenuItems()` | 获取所有菜单项 | - | `PluginMenuItem[]` |
| `getRoutes()` | 获取所有路由 | - | `PluginRoute[]` |
| `subscribe(listener)` | 订册变更监听 | `Listener` | `() => void`（取消订阅函数） |

**类型定义**：

```typescript
interface PluginMenuItem {
  key: string;
  label: string;
  icon?: ReactNode;
  pluginName: string;
}

interface PluginRoute {
  path: string;
  element: ReactNode;
  pluginName: string;
}
```

#### PluginLoader（资源加载器）

**文件路径**：`frontend/src/plugins/PluginLoader.ts`

负责动态加载插件的前端资源文件（JS/CSS）。

| 函数 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `loadPluginAssets(plugin)` | 加载插件的 JS 和 CSS 资源 | `PluginInfo` | `Promise<void>` |
| `unloadPluginAssets(pluginName)` | 移除插件的 DOM 资源元素 | `string` | `void` |

资源加载路径规则：`/api/plugins/{name}/assets/index.js` 和 `/api/plugins/{name}/assets/index.css`。

### 5.3 插件 API 客户端

**文件路径**：`frontend/src/api/plugin.ts`

前端通过 `pluginApi` 对象与后端插件系统交互。

**类型定义**：

```typescript
type PluginStatus = 'installed' | 'enabled' | 'disabled' | 'pending_restart' | 'error';
type LoadType = 'hot' | 'restart';
type InstallSource = 'zip' | 'git' | 'manual';

interface PluginInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  load_type: LoadType;
  status: PluginStatus;
  install_source: InstallSource;
  install_path: string;
  permissions: string[];
  config_schema: Record<string, unknown> | null;
  frontend_entry: string | null;
  installed_at: string;
  updated_at: string;
  error_message: string | null;
}
```

**pluginApi 方法**：

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `getPlugins()` | 获取所有插件列表 | - | `Promise<PluginInfo[]>` |
| `getPlugin(name)` | 获取指定插件详情 | `name: string` | `Promise<PluginInfo>` |
| `installFromZip(file)` | 上传 ZIP 安装插件 | `File` | `Promise` |
| `installFromGit(url, branch?)` | 通过 Git URL 安装插件 | `url: string, branch?: string` | `Promise` |
| `uninstallPlugin(name)` | 卸载插件 | `name: string` | `Promise` |
| `enablePlugin(name)` | 启用插件 | `name: string` | `Promise` |
| `disablePlugin(name)` | 禁用插件 | `name: string` | `Promise` |
| `getPluginConfig(name)` | 获取插件配置 Schema | `name: string` | `Promise` |

**SSE 事件监听**：

```typescript
import { listenPluginEvents } from '@/api/plugin';

// 监听插件事件，返回取消监听函数
const stop = listenPluginEvents((event) => {
  console.log(event.event, event.data);
});

// 取消监听
stop();
```

监听的事件类型：`plugin_loaded`、`plugin_unloaded`、`plugin_installed`、`plugin_uninstalled`、`plugin_error`。

## 6. 插件安装方式

QuantCell 支持三种插件安装方式，可通过前端管理 UI 或 REST API 操作。

### 6.1 ZIP 上传安装

上传 `.zip` 格式的插件包，后端自动完成以下流程：

1. 解压 ZIP 文件到临时目录
2. 查找 `manifest.json`（支持根目录或一级子目录）
3. 校验 manifest 字段（名称格式、版本格式、权限声明）
4. 检查插件是否已存在
5. 移动到插件目录
6. 写入数据库并加载

**REST API**：

```bash
curl -X POST http://localhost:8000/api/plugins/install/upload \
  -F "file=@my-plugin.zip"
```

**ZIP 结构要求**：

```
my-plugin.zip
├── manifest.json          # 或在一级子目录中
├── plugin.py
└── ...
```

### 6.2 Git 克隆安装

提供 Git 仓库 URL 和可选分支名，后端自动完成以下流程：

1. `git clone --depth 1` 克隆仓库（超时 120 秒）
2. 查找并校验 `manifest.json`
3. 检查插件是否已存在
4. 移动到插件目录
5. 写入数据库并加载

**REST API**：

```bash
curl -X POST http://localhost:8000/api/plugins/install/git \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/plugin.git", "branch": "main"}'
```

### 6.3 手动安装

将插件目录直接放置到 `backend/plugins/` 目录下，系统启动时会自动扫描发现新插件。

## 7. 热加载与重启加载

插件通过 `manifest.json` 中的 `load_type` 字段指定加载方式。

### 7.1 热加载（hot）

```json
{
  "load_type": "hot"
}
```

- 插件可在运行时动态加载和卸载，无需重启应用
- 适合大多数场景，推荐作为默认选择
- 加载器：`HotPluginLoader`
- 模块命名空间：`plugins.hot.<name>`

### 7.2 重启加载（restart）

```json
{
  "load_type": "restart"
}
```

- 插件仅在应用启动时加载，运行时无法动态卸载
- 适用于需要在启动时初始化全局资源、注册中间件等场景
- 加载器：`RestartPluginLoader`
- 模块命名空间：`plugins.restart.<name>`
- 安装后状态为 `pending_restart`，需要重启应用才能生效

### 7.3 状态流转

```
安装 → installed → enabled → active（热加载自动完成）
                        ↘ disabled（手动禁用）
安装 → installed → pending_restart（重启加载，等待重启）
                        ↘ active（重启后加载）
任何状态 → error（加载失败、运行异常）
```

## 8. 前端插件管理 UI

### 8.1 访问路径

路由：`/setting/plugins`

### 8.2 功能概览

插件管理页面提供以下功能：

| 功能 | 说明 |
|------|------|
| **插件列表** | 卡片视图展示所有已安装插件，显示名称、版本、描述、状态、加载方式 |
| **安装插件** | 支持 ZIP 上传和 Git URL 两种安装方式，通过 Modal 对话框操作 |
| **启停控制** | 每个插件卡片提供 Switch 开关，可快速启用/禁用插件 |
| **卸载插件** | 卡片操作栏提供卸载按钮，带确认提示 |
| **详情查看** | 点击详情图标查看插件完整信息（版本、作者、权限、配置 Schema 等） |
| **状态提醒** | 当存在需要重启的插件时，页面顶部显示提醒横幅 |

### 8.3 状态展示

| 状态值 | 显示文本 | Badge 颜色 |
|--------|---------|-----------|
| `installed` | 已安装 | default |
| `enabled` | 运行中 | success |
| `disabled` | 已停止 | warning |
| `pending_restart` | 待重启 | processing |
| `error` | 错误 | error |

### 8.4 技术实现

- 使用 Ant Design 组件库（Card、List、Modal、Upload、Form 等）
- 通过 `usePlugins()` Hook 获取插件列表和操作方法
- 通过 `pluginApi` 调用后端 API
- 通过 `PluginRegistry` 注册菜单和路由

## 9. 后端高级功能

### 9.1 EventBus 事件总线

**文件路径**：`backend/plugins/event_bus.py`

`EventBus` 提供发布/订阅模式的事件通信机制，支持插件间以及插件与系统之间的解耦通信。

**核心方法**：

| 方法名 | 描述 | 参数 |
|--------|------|------|
| `subscribe(event_name, callback)` | 订阅事件 | 事件名称、回调函数 |
| `unsubscribe(event_name, callback)` | 取消订阅 | 事件名称、回调函数 |
| `publish(event_name, data)` | 同步发布事件 | 事件名称、数据 |
| `publish_async(event_name, data)` | 异步发布事件（线程池执行） | 事件名称、数据 |
| `get_subscribers(event_name)` | 获取事件订阅者列表 | 事件名称 |
| `clear()` | 清除所有订阅 | - |

**使用示例**：

```python
from plugins.event_bus import EventBus

event_bus = EventBus()

# 订阅事件
def on_order_created(data):
    print(f"新订单: {data}")

event_bus.subscribe("order.created", on_order_created)

# 发布事件
event_bus.publish("order.created", {"order_id": "12345", "amount": 100.0})
```

**系统内置事件**：

| 事件名 | 触发时机 | 数据 |
|--------|---------|------|
| `plugin.loaded` | 插件加载成功 | `{name: str}` |
| `plugin.unloaded` | 插件卸载成功 | `{name: str}` |
| `plugin.installed` | 插件安装成功 | `{name: str}` |
| `plugin.uninstalled` | 插件卸载删除 | `{name: str}` |

插件可通过 `PluginAPI` 访问事件总线：

```python
# 在插件内部
def register(self, plugin_manager):
    super().register(plugin_manager)
    plugin_api = plugin_manager.event_bus
    plugin_api.subscribe("order.created", self.handle_order)

def handle_order(self, data):
    self.logger.info(f"收到订单事件: {data}")
```

### 9.2 PluginStore 持久化存储

**文件路径**：`backend/plugins/plugin_store.py`

`PluginStore` 基于 SQLAlchemy 提供插件元数据的持久化存储，所有插件信息（名称、版本、状态、权限、安装路径等）均通过数据库管理。

**核心方法（均为静态方法）**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `save_plugin(metadata)` | 保存/更新插件元数据 | `dict` | `bool` |
| `get_plugin(name)` | 获取指定插件信息 | `str` | `Optional[dict]` |
| `get_all_plugins()` | 获取所有插件信息 | - | `List[dict]` |
| `update_status(name, status, error_message?)` | 更新插件状态 | `str, str, Optional[str]` | `bool` |
| `delete_plugin(name)` | 删除插件记录 | `str` | `bool` |
| `update_plugin(name, **kwargs)` | 更新插件字段 | `str, **kwargs` | `bool` |

### 9.3 PluginSecurity 权限与沙箱

**文件路径**：`backend/plugins/plugin_security.py`

#### 权限声明

插件在 `manifest.json` 中声明所需权限，安装时系统会校验权限合法性。

**支持的权限枚举**：

| 权限值 | 描述 |
|--------|------|
| `database:read` | 数据库读取 |
| `database:write` | 数据库写入 |
| `api:internal` | 内部 API 调用 |
| `filesystem:read` | 文件系统读取 |
| `filesystem:write` | 文件系统写入 |
| `network:outbound` | 网络出站请求 |

#### 路由冲突检测

系统会自动检测插件路由前缀是否与核心系统路由冲突。以下路由前缀为系统保留：

- `/api/config`
- `/api/system`
- `/api/auth`
- `/api/workers`
- `/api/logs`
- `/api/notifications`
- `/api/system-ports`
- `/ws`

#### 沙箱执行

`PluginSandbox` 提供安全的插件代码执行环境，捕获异常避免影响主系统：

```python
from plugins.plugin_security import PluginSandbox

sandbox = PluginSandbox("my-plugin", logger)

# 安全执行（返回结果或 None）
result = sandbox.execute(some_function, arg1, arg2)

# 带状态的安全执行（返回 (bool, result_or_error_msg)）
success, result = sandbox.execute_safe(some_function, arg1, arg2)
```

### 9.4 PluginInstaller 安装器

**文件路径**：`backend/plugins/plugin_installer.py`

`PluginInstaller` 封装了 ZIP 和 Git 两种安装方式的完整流程。

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `install_from_zip(zip_file_path)` | 从 ZIP 文件路径安装 | `str` | `tuple[bool, str]` |
| `install_from_zip_bytes(zip_bytes, filename?)` | 从字节数据安装 | `bytes, str` | `tuple[bool, str]` |
| `install_from_git(git_url, branch?)` | 从 Git 仓库安装 | `str, Optional[str]` | `tuple[bool, str]` |
| `validate_manifest(manifest_data)` | 校验 manifest 数据 | `dict` | `tuple[bool, str]` |

安装过程中的校验规则：
- manifest 必须包含 `name` 和 `version` 字段
- `name` 仅允许字母、数字、下划线、连字符
- `version` 需符合 X.Y.Z 格式
- 权限声明必须合法
- 同名插件不允许重复安装

### 9.5 PluginAPI 服务接口

**文件路径**：`backend/plugins/api.py`

`PluginAPI` 为插件提供核心功能访问入口和插件间通信能力。

**核心方法**：

| 方法名 | 描述 |
|--------|------|
| `register_service(name, service)` | 注册服务供其他插件使用 |
| `get_service(name)` | 获取已注册的服务 |
| `get_plugin(plugin_name)` | 获取指定插件实例 |
| `get_all_plugins()` | 获取所有插件名称 |
| `send_event(event_name, data)` | 发送事件 |
| `subscribe_event(event_name, callback)` | 订阅事件 |
| `unsubscribe_event(event_name, callback)` | 取消订阅事件 |
| `get_event_bus()` | 获取 EventBus 实例 |
| `log(message, level)` | 记录日志 |

**使用示例**：

```python
# 注册服务
plugin_api.register_service("data_provider", my_data_service)

# 获取其他插件的服务
data_service = plugin_api.get_service("data_provider")
```

## 10. REST API 接口说明

### 10.1 插件管理 API

所有接口前缀为 `/api/plugins`。

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/plugins/` | 获取所有插件列表 |
| `GET` | `/api/plugins/{name}` | 获取指定插件详情 |
| `POST` | `/api/plugins/install/upload` | 上传 ZIP 安装插件 |
| `POST` | `/api/plugins/install/git` | 通过 Git URL 安装插件 |
| `DELETE` | `/api/plugins/{name}` | 卸载插件 |
| `POST` | `/api/plugins/{name}/enable` | 启用插件 |
| `POST` | `/api/plugins/{name}/disable` | 禁用插件 |
| `GET` | `/api/plugins/{name}/assets/{path}` | 获取插件前端资源文件 |
| `GET` | `/api/plugins/{name}/config` | 获取插件配置 Schema |
| `GET` | `/api/plugins/events` | SSE 事件流（插件实时事件推送） |

### 10.2 Git 安装请求体

```json
{
  "url": "https://github.com/user/plugin.git",
  "branch": "main"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | Git 仓库地址 |
| `branch` | string | 否 | 分支名，默认使用仓库默认分支 |

### 10.3 通用响应格式

所有管理 API 返回统一格式：

```json
{
  "code": 0,
  "message": "操作成功",
  "data": { ... }
}
```

错误时返回 HTTP 状态码和详细错误信息。

## 11. 示例插件

### 11.1 后端示例插件

**名称**：`example_plugin`
**路径**：`backend/plugins/example_plugin/`
**功能**：
- 提供两个 API 端点
- 演示 PluginBase 的生命周期方法
- 展示插件系统的基本功能

**manifest.json**：
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

**API 端点**：
- `GET /api/plugins/example/` - 返回插件基本信息
- `GET /api/plugins/example/test` - 返回测试数据

### 11.2 前端插件示例

前端插件通过 `PluginRegistry` 注册菜单和路由，并通过 `usePlugins()` 获取插件状态。参见 [4.2 前端插件开发流程](#42-前端插件开发流程) 中的完整示例。

## 12. 常见问题与解决方案

### 12.1 插件安装失败 — ZIP 格式错误

**问题**：上传 ZIP 文件后提示安装失败。

**可能原因**：
- ZIP 文件损坏或不是有效的 ZIP 格式
- ZIP 中未包含 `manifest.json` 文件
- `manifest.json` 格式不正确或缺少必填字段

**解决方案**：
- 确认 ZIP 文件可以正常解压
- 确保 `manifest.json` 位于 ZIP 根目录或一级子目录中
- 检查 `manifest.json` 包含 `name` 和 `version` 字段

### 12.2 插件安装失败 — Git URL 无效

**问题**：通过 Git URL 安装插件失败。

**可能原因**：
- Git URL 不正确或无法访问
- 服务器未安装 Git
- 网络连接超时（默认 120 秒）
- 指定的分支不存在

**解决方案**：
- 确认 Git URL 可以正常访问
- 确保服务器已安装 Git 命令行工具
- 检查网络连接
- 确认分支名称正确

### 12.3 插件状态显示"待重启"

**问题**：安装插件后，插件状态显示为 `pending_restart`。

**原因**：插件的 `load_type` 设置为 `restart`，需要重启后端服务才能加载。

**解决方案**：
```bash
# 重启后端服务
cd QuantCell/backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

如果希望插件支持热加载，将 `manifest.json` 中的 `load_type` 改为 `hot`。

### 12.4 前端插件资源加载失败

**问题**：浏览器控制台提示插件 JS/CSS 资源加载失败（404 或网络错误）。

**可能原因**：
- 插件的前端资源未正确构建或放置
- `frontend_entry` 配置不正确
- 后端静态文件路径不匹配

**解决方案**：
- 确保插件的前端资源位于 `frontend/dist/` 目录下
- 检查 `manifest.json` 中的 `frontend_entry` 字段指向正确的资源路径
- 资源文件需命名为 `index.js` 和 `index.css`

### 12.5 后端插件加载失败

**问题**：后端插件无法加载，日志显示错误。

**可能原因**：
- 插件没有 `register_plugin` 函数
- `register_plugin` 返回值不是 `PluginBase` 的实例
- 依赖缺失
- manifest 校验失败（版本兼容性、权限等）

**解决方案**：
- 确保入口文件包含 `register_plugin` 函数
- 确保返回值是 `PluginBase` 的子类实例
- 检查并安装缺失的依赖
- 查看日志中的具体错误信息

### 12.6 前端构建失败

**问题**：前端构建时出现 TypeScript 错误。

**可能原因**：
- 类型导入语法错误
- 类型定义不匹配
- 未使用的导入

**解决方案**：
- 使用 `import type` 语法导入类型
- 确保类型定义匹配
- 移除未使用的导入
- 使用 `export type` 语法重新导出类型

### 12.7 插件路由冲突

**问题**：插件添加的路由与现有路由冲突。

**解决方案**：
- 为插件路由使用唯一的前缀，如 `/plugins/<plugin-name>/`
- 避免使用系统保留的路由前缀（见 [9.3 节](#93-pluginsecurity-权限与沙箱)）
- 在添加路由前检查是否已存在

### 12.8 插件间通信

**问题**：插件之间需要通信和数据共享。

**解决方案**：
- **推荐方式**：使用 `EventBus` 发布/订阅事件
- **服务注册**：通过 `PluginAPI.register_service()` 注册共享服务
- **直接引用**：通过 `PluginManager.get_plugin()` 获取其他插件实例

## 13. 插件测试与验证

### 13.1 后端插件测试

**手动测试**：
```bash
# 启动后端服务
cd QuantCell/backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 查看插件列表
curl http://localhost:8000/api/plugins/

# 查看指定插件
curl http://localhost:8000/api/plugins/example_plugin
```

**自动测试**：
```bash
cd QuantCell/backend
pytest tests/
```

**独立开发调试**：
```bash
cd QuantCell/backend
python -m plugins.plugin_dev run \
  --plugin-dir plugins/my_plugin \
  --port 9000 \
  --reload
```

### 13.2 前端插件测试

**构建验证**：
```bash
cd QuantCell/frontend
bun run build
```

**插件管理 UI 验证**：
- 启动后端服务后访问 `/setting/plugins`
- 检查插件列表是否正确显示
- 测试插件安装、启停、卸载功能

## 14. 最佳实践

### 14.1 插件命名规范

- 插件名称使用小写字母、数字、下划线和连字符
- 目录名与插件名保持一致
- 版本号使用语义化版本规范（X.Y.Z）

### 14.2 代码结构

- 保持插件代码模块化
- 分离核心逻辑和路由
- 提供清晰的文档注释
- 入口文件保持简洁，仅包含 `register_plugin()` 函数和插件类定义

### 14.3 加载方式选择

- **优先使用热加载（hot）**：大多数插件都适合热加载，便于开发和调试
- **仅在必要时使用重启加载（restart）**：需要注册中间件、修改全局配置等场景

### 14.4 权限管理

- 仅声明插件实际需要的权限
- 避免声明不必要的高权限（如 `filesystem:write`）
- 使用 `PluginSandbox` 包裹可能抛出异常的代码

### 14.5 事件通信

- 优先使用 `EventBus` 进行松耦合通信
- 订阅者应在插件 `stop()` 时取消订阅
- 事件回调中避免耗时操作，必要时使用 `publish_async`

### 14.6 性能优化

- 插件懒加载，避免在注册阶段执行重量级操作
- 避免不必要的依赖
- 前端资源保持精简

### 14.7 安全性

- 验证所有用户输入
- 遵循最小权限原则
- 定期更新依赖
- 不要在插件代码中硬编码敏感信息

## 15. 贡献指南

### 15.1 提交插件

1. 确保插件符合 QuantCell 插件规范
2. 提供完整的 manifest.json
3. 提供清晰的文档注释

### 15.2 报告问题

- 在 GitHub Issues 中报告问题
- 提供详细的错误信息和复现步骤
- 包括环境信息和插件版本

### 15.3 代码规范

- 后端使用 PEP 8 规范
- 前端使用 TypeScript 规范
- 遵循项目现有的代码风格
- 日志通过 `backend/utils/logger.py` 中的日志器记录，不使用 `print`

---

**文档版本**：2.0.0
**最后更新**：2026-05-25
**作者**：pengwow
