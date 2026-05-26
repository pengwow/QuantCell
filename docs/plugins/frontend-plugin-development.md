# 前端插件开发指南

## 1. 架构概述

QuantCell 前端插件系统采用 **PluginContext / PluginRegistry / PluginLoader** 三层架构，取代了旧版的 PluginBase/PluginManager 继承模式。新架构的核心设计理念：

- **声明式注册**：插件通过调用方法注册菜单和路由，无需继承基类
- **运行时加载**：插件资源（JS/CSS）在运行时通过 DOM 动态注入，支持热加载
- **响应式状态**：通过 React Context + SSE 事件流实现插件状态的实时同步

### 三大核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **PluginRegistry** | `frontend/src/plugins/PluginRegistry.ts` | 单例注册中心，管理插件信息、菜单项、路由，提供发布/订阅机制 |
| **PluginContext** | `frontend/src/plugins/PluginContext.tsx` | React Context，提供全局插件状态管理，挂载时自动加载并通过 SSE 实时刷新 |
| **PluginLoader** | `frontend/src/plugins/PluginLoader.ts` | 资源加载器，动态注入插件的 JS/CSS 资源到 DOM |

### 数据流

```
┌──────────────────────────────────────────────────────────┐
│                     后端 Plugin Manager                   │
│   install / uninstall / enable / disable / SSE events    │
└──────────────────────┬───────────────────────────────────┘
                       │ REST API + SSE
                       ▼
┌──────────────────────────────────────────────────────────┐
│              pluginApi (frontend/src/api/plugin.ts)       │
│         封装所有 HTTP 请求和 SSE 事件监听                   │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│           PluginContext (PluginProvider + usePlugins)      │
│    挂载时调用 pluginApi.getPlugins()，SSE 触发时自动刷新    │
│    同步更新 PluginRegistry 中的插件数据                     │
└──────────┬───────────────────────────────┬───────────────┘
           │                               │
           ▼                               ▼
┌─────────────────────┐      ┌─────────────────────────────┐
│   PluginRegistry    │      │       PluginLoader          │
│  菜单/路由/插件信息   │      │  动态加载插件 JS/CSS 资源     │
└─────────────────────┘      └─────────────────────────────┘
```

## 2. 目录结构

```
frontend/src/
├── api/
│   └── plugin.ts                 # 插件 REST API 封装和类型定义
├── plugins/
│   ├── index.ts                  # 插件系统统一导出
│   ├── PluginRegistry.ts         # 插件注册中心（单例）
│   ├── PluginContext.tsx          # React Context + Provider + usePlugins Hook
│   └── PluginLoader.ts           # 动态资源加载器
├── pages/
│   └── setting/
│       └── PluginManagement.tsx  # 插件管理页面（设置模块内）
└── App.tsx                       # 根组件，挂载 PluginProvider
```

### 文件说明

| 文件 | 说明 |
|------|------|
| `api/plugin.ts` | 定义 `PluginInfo` 等类型，封装 `pluginApi` 对象的所有 REST 方法，以及 `listenPluginEvents` SSE 监听函数 |
| `plugins/PluginRegistry.ts` | 单例模式的注册中心，导出 `pluginRegistry` 实例和 `PluginMenuItem`、`PluginRoute` 类型 |
| `plugins/PluginContext.tsx` | 导出 `PluginProvider` 组件和 `usePlugins()` Hook |
| `plugins/PluginLoader.ts` | 导出 `loadPluginAssets()` 和 `unloadPluginAssets()` 函数 |
| `plugins/index.ts` | 统一导出入口，外部模块应从 `@/plugins` 导入 |
| `pages/setting/PluginManagement.tsx` | 插件管理 UI，路由路径 `/setting/plugins` |

## 3. TypeScript 类型定义

所有插件相关类型定义在 `frontend/src/api/plugin.ts` 中。

### 3.1 核心类型

```typescript
export type PluginStatus = 'installed' | 'enabled' | 'disabled' | 'pending_restart' | 'error';
export type LoadType = 'hot' | 'restart';
export type InstallSource = 'zip' | 'git' | 'manual';
```

### 3.2 PluginInfo

插件的完整信息结构，由后端返回：

```typescript
export interface PluginInfo {
  name: string;                    // 插件唯一标识
  version: string;                 // 语义化版本号
  description: string;             // 插件描述
  author: string;                  // 作者
  load_type: LoadType;             // 加载方式：hot（热加载）或 restart（需重启）
  status: PluginStatus;            // 当前状态
  install_source: InstallSource;   // 安装来源
  install_path: string;            // 安装路径
  permissions: string[];           // 所需权限列表
  config_schema: Record<string, unknown> | null;  // 配置 Schema
  frontend_entry: string | null;   // 前端入口文件路径
  installed_at: string;            // 安装时间（ISO 8601 格式）
  updated_at: string;              // 更新时间（ISO 8601 格式）
  error_message: string | null;    // 错误信息（status 为 error 时有值）
}
```

### 3.3 PluginMenuItem

菜单项注册结构：

```typescript
export interface PluginMenuItem {
  key: string;          // 菜单项唯一标识
  label: string;        // 显示文本
  icon?: ReactNode;     // 图标（可选）
  pluginName: string;   // 所属插件名称
}
```

### 3.4 PluginRoute

路由注册结构：

```typescript
export interface PluginRoute {
  path: string;          // 路由路径
  element: ReactNode;    // 路由组件
  pluginName: string;    // 所属插件名称
}
```

### 3.5 PluginEvent

SSE 事件结构：

```typescript
export interface PluginEvent {
  event: string;       // 事件类型：plugin_loaded / plugin_unloaded / plugin_installed / plugin_uninstalled / plugin_error / message
  data: {
    name: string;      // 插件名称
    status: string;    // 插件状态
    error?: string;    // 错误信息（可选）
  };
}
```

## 4. 核心 API 参考

### 4.1 PluginRegistry

单例实例通过 `pluginRegistry` 导出，是插件系统的注册中心。

```typescript
import { pluginRegistry } from '@/plugins';
```

#### 方法列表

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `registerPlugin(plugin)` | `PluginInfo` | `void` | 注册插件信息到注册中心 |
| `unregisterPlugin(name)` | `string` | `void` | 注销插件，同时清除其菜单和路由 |
| `registerMenu(item)` | `PluginMenuItem` | `void` | 注册菜单项（按 key 去重） |
| `registerRoute(route)` | `PluginRoute` | `void` | 注册路由（按 path 去重） |
| `getPlugin(name)` | `string` | `PluginInfo \| undefined` | 获取指定插件信息 |
| `getAllPlugins()` | - | `PluginInfo[]` | 获取所有已注册插件 |
| `getMenuItems()` | - | `PluginMenuItem[]` | 获取所有菜单项 |
| `getRoutes()` | - | `PluginRoute[]` | 获取所有路由 |
| `subscribe(listener)` | `() => void` | `() => void` | 订阅变更通知，返回取消订阅函数 |

#### 使用示例

```typescript
import { pluginRegistry, type PluginMenuItem, type PluginRoute } from '@/plugins';

// 注册菜单
const menuItem: PluginMenuItem = {
  key: 'my-plugin-home',
  label: '我的插件',
  icon: <AppstoreOutlined />,
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

// 监听变更
const unsubscribe = pluginRegistry.subscribe(() => {
  console.log('插件注册中心数据已变更');
});
// 取消订阅
unsubscribe();
```

### 4.2 usePlugins Hook

在 React 组件中获取插件状态和操作方法。

```typescript
import { usePlugins } from '@/plugins';
```

#### 返回值

```typescript
interface PluginContextValue {
  plugins: PluginInfo[];                       // 当前插件列表
  loading: boolean;                            // 是否正在加载
  refresh: () => Promise<void>;                // 手动刷新插件列表
  enablePlugin: (name: string) => Promise<void>;   // 启用插件
  disablePlugin: (name: string) => Promise<void>;  // 禁用插件
}
```

#### 使用示例

```typescript
import { usePlugins } from '@/plugins';

function MyComponent() {
  const { plugins, loading, refresh, enablePlugin, disablePlugin } = usePlugins();

  if (loading) return <Spin />;

  return (
    <div>
      {plugins.map((p) => (
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

> **注意**：`usePlugins()` 必须在 `<PluginProvider>` 内部使用，否则将返回默认空值。

### 4.3 pluginApi

封装所有插件管理的 REST API 调用。

```typescript
import { pluginApi } from '@/api/plugin';
```

#### 方法列表

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `getPlugins()` | - | `Promise<PluginInfo[]>` | 获取所有插件列表 |
| `getPlugin(name)` | `string` | `Promise<PluginInfo>` | 获取指定插件详情 |
| `installFromZip(file)` | `File` | `Promise<any>` | 通过 ZIP 文件安装插件 |
| `installFromGit(url, branch?)` | `string, string?` | `Promise<any>` | 通过 Git 仓库安装插件 |
| `uninstallPlugin(name)` | `string` | `Promise<any>` | 卸载插件 |
| `enablePlugin(name)` | `string` | `Promise<any>` | 启用插件 |
| `disablePlugin(name)` | `string` | `Promise<any>` | 禁用插件 |
| `getPluginConfig(name)` | `string` | `Promise<any>` | 获取插件配置 |

#### 使用示例

```typescript
import { pluginApi } from '@/api/plugin';

// 从 ZIP 安装
const handleZipInstall = async (file: File) => {
  await pluginApi.installFromZip(file);
};

// 从 Git 安装
const handleGitInstall = async (url: string) => {
  await pluginApi.installFromGit(url, 'main');
};

// 卸载插件
const handleUninstall = async (name: string) => {
  await pluginApi.uninstallPlugin(name);
};
```

### 4.4 listenPluginEvents

通过 SSE 监听插件状态变更事件。

```typescript
import { listenPluginEvents } from '@/api/plugin';
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `onEvent` | `(evt: PluginEvent) => void` | 事件回调函数 |

#### 返回值

`() => void` — 取消监听函数

#### 监听的事件类型

| 事件名 | 说明 |
|--------|------|
| `plugin_loaded` | 插件已加载 |
| `plugin_unloaded` | 插件已卸载 |
| `plugin_installed` | 插件已安装 |
| `plugin_uninstalled` | 插件已移除 |
| `plugin_error` | 插件发生错误 |
| `message` | 通用消息事件 |

#### 使用示例

```typescript
import { useEffect } from 'react';
import { listenPluginEvents } from '@/api/plugin';

function usePluginEventListener() {
  useEffect(() => {
    const stop = listenPluginEvents((evt) => {
      console.log('插件事件:', evt.event, evt.data);
    });
    return stop;  // 组件卸载时自动取消
  }, []);
}
```

### 4.5 PluginLoader

动态加载和卸载插件的前端资源（JS/CSS）。

```typescript
import { loadPluginAssets, unloadPluginAssets } from '@/plugins';
```

#### loadPluginAssets

加载插件的 CSS 和 JS 资源。资源路径规则：

- CSS：`/api/plugins/{name}/assets/index.css`
- JS：`/api/plugins/{name}/assets/index.js`

加载失败时，CSS 不会阻塞插件运行，JS 失败会抛出错误。内部维护已加载资源的 Set，避免重复加载。

```typescript
import { loadPluginAssets } from '@/plugins';

const plugin = pluginRegistry.getPlugin('my-plugin');
if (plugin) {
  await loadPluginAssets(plugin);
}
```

#### unloadPluginAssets

卸载插件资源，移除 DOM 中带有对应 `data-plugin` 属性的 `<script>` 和 `<link>` 标签。

```typescript
import { unloadPluginAssets } from '@/plugins';

unloadPluginAssets('my-plugin');
```

## 5. 插件开发流程

### 5.1 开发步骤

```
1. 创建插件组件
2. 在组件初始化时注册菜单和路由
3. 通过 pluginApi 调用后端接口
4. 通过 usePlugins() 获取插件状态
5. 打包为 JS/CSS 资源，部署到后端插件目录
```

### 5.2 注册菜单和路由

插件在加载后需要向 `PluginRegistry` 注册自己的菜单和路由，以便系统侧边栏和路由表能够识别。

```typescript
import { pluginRegistry } from '@/plugins';
import { AppstoreOutlined } from '@ant-design/icons';
import MyPluginPage from './MyPluginPage';

export function registerMyPlugin() {
  // 注册菜单项
  pluginRegistry.registerMenu({
    key: 'my-plugin',
    label: '我的插件',
    icon: <AppstoreOutlined />,
    pluginName: 'my-plugin',
  });

  // 注册路由
  pluginRegistry.registerRoute({
    path: '/plugins/my-plugin',
    element: <MyPluginPage />,
    pluginName: 'my-plugin',
  });
}
```

### 5.3 调用后端 API

插件的业务数据通过后端 REST API 获取。使用项目统一的 `apiRequest` 封装：

```typescript
import { apiRequest } from '@/api';

// 获取插件数据
export const myPluginApi = {
  getData: () => apiRequest.get('/plugins/my-plugin/data'),
  submitData: (data: any) => apiRequest.post('/plugins/my-plugin/data', data),
};
```

### 5.4 获取插件状态

在 React 组件中使用 `usePlugins()` Hook 获取插件列表和操作方法：

```typescript
import { usePlugins } from '@/plugins';

function PluginStatusBadge() {
  const { plugins } = usePlugins();
  const myPlugin = plugins.find((p) => p.name === 'my-plugin');

  if (!myPlugin) return null;

  return <Tag>{myPlugin.status}</Tag>;
}
```

### 5.5 加载插件资源

对于需要动态加载的插件（热加载类型），使用 `loadPluginAssets`：

```typescript
import { loadPluginAssets, pluginRegistry } from '@/plugins';

async function initPlugin(pluginName: string) {
  const plugin = pluginRegistry.getPlugin(pluginName);
  if (plugin && plugin.load_type === 'hot') {
    await loadPluginAssets(plugin);
  }
}
```

## 6. 完整示例

以下示例演示如何创建一个完整的前端插件，包含页面组件、API 调用和菜单/路由注册。

### 6.1 插件入口文件

```typescript
// my-plugin/index.ts
import { pluginRegistry } from '@/plugins';
import { ApiOutlined } from '@ant-design/icons';
import MyPluginPage from './MyPluginPage';

export function initMyPlugin() {
  pluginRegistry.registerMenu({
    key: 'my-plugin',
    label: '数据看板',
    icon: <ApiOutlined />,
    pluginName: 'my-plugin',
  });

  pluginRegistry.registerRoute({
    path: '/plugins/my-plugin',
    element: <MyPluginPage />,
    pluginName: 'my-plugin',
  });
}
```

### 6.2 API 服务文件

```typescript
// my-plugin/api.ts
import { apiRequest } from '@/api';

export interface DashboardData {
  total_trades: number;
  pnl: number;
  win_rate: number;
}

export const myPluginApi = {
  getDashboard: (): Promise<DashboardData> =>
    apiRequest.get('/plugins/my-plugin/dashboard'),
};
```

### 6.3 页面组件

```typescript
// my-plugin/MyPluginPage.tsx
import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Spin, App } from 'antd';
import { usePlugins } from '@/plugins';
import { myPluginApi, type DashboardData } from './api';

export default function MyPluginPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const { plugins } = usePlugins();
  const { message } = App.useApp();

  const myPlugin = plugins.find((p) => p.name === 'my-plugin');
  const isEnabled = myPlugin?.status === 'enabled';

  useEffect(() => {
    if (!isEnabled) return;

    myPluginApi
      .getDashboard()
      .then(setData)
      .catch((err) => message.error(`加载失败: ${err.message}`))
      .finally(() => setLoading(false));
  }, [isEnabled, message]);

  if (!isEnabled) {
    return <Card>插件未启用</Card>;
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic title="总交易数" value={data?.total_trades ?? 0} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="盈亏"
              value={data?.pnl ?? 0}
              precision={2}
              prefix="$"
              valueStyle={{ color: (data?.pnl ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="胜率"
              value={data?.win_rate ?? 0}
              precision={1}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
```

### 6.4 插件目录结构

```
my-plugin/
├── index.ts           # 入口，注册菜单和路由
├── api.ts             # API 封装
└── MyPluginPage.tsx   # 页面组件
```

## 7. 插件管理 UI

插件管理功能集成在系统设置模块中，路由路径为 `/setting/plugins`。

### 7.1 功能概览

| 功能 | 说明 |
|------|------|
| **插件列表** | 卡片视图展示所有已安装插件，显示名称、版本、描述、状态、加载方式 |
| **安装插件** | 支持两种方式：ZIP 文件上传、Git 仓库地址 |
| **启停控制** | 通过 Switch 开关启用/禁用插件 |
| **卸载插件** | 二次确认后卸载插件 |
| **插件详情** | 查看插件完整信息（权限、安装来源、配置 Schema 等） |

### 7.2 状态说明

| 状态 | 显示文本 | 颜色 | 说明 |
|------|----------|------|------|
| `installed` | 已安装 | 默认 | 插件已安装但未启用 |
| `enabled` | 运行中 | 绿色 | 插件正在运行 |
| `disabled` | 已停止 | 橙色 | 插件已被禁用 |
| `pending_restart` | 待重启 | 蓝色（闪烁） | 插件需要重启后端才能生效 |
| `error` | 错误 | 红色 | 插件运行异常 |

### 7.3 安装方式

**ZIP 上传**：将插件打包为 `.zip` 文件，在管理页面拖拽或点击上传。

**Git 安装**：输入 Git 仓库地址（可选指定分支），系统自动克隆并安装。

### 7.4 使用 PluginProvider

插件管理页面通过 `usePlugins()` 获取数据，这要求根组件已挂载 `PluginProvider`：

```typescript
// App.tsx
import { PluginProvider } from '@/plugins';

function App() {
  return (
    <PluginProvider>
      {/* 应用内容 */}
    </PluginProvider>
  );
}
```

`PluginProvider` 在挂载时会：

1. 调用 `pluginApi.getPlugins()` 加载插件列表
2. 将每个插件注册到 `pluginRegistry`
3. 启动 SSE 监听，插件状态变更时自动刷新

## 8. 最佳实践

### 8.1 组件设计

- **单一职责**：每个插件页面组件只负责一个功能模块
- **状态提升**：将共享状态放在 `usePlugins()` 或 React Context 中管理
- **懒加载**：对于复杂组件使用 `React.lazy` 和 `Suspense` 按需加载

```typescript
import { lazy, Suspense } from 'react';
import { Spin } from 'antd';

const HeavyPluginPage = lazy(() => import('./HeavyPluginPage'));

// 注册路由时使用 Suspense 包裹
pluginRegistry.registerRoute({
  path: '/plugins/heavy-plugin',
  element: (
    <Suspense fallback={<Spin size="large" />}>
      <HeavyPluginPage />
    </Suspense>
  ),
  pluginName: 'heavy-plugin',
});
```

### 8.2 错误处理

- API 调用使用 `try/catch` 捕获错误，通过 `App.useApp()` 的 `message` 展示提示
- 组件内使用 `usePlugins()` 检查插件状态后再执行操作
- 资源加载失败时 `PluginLoader` 已内置容错（CSS 不阻塞）

```typescript
import { App } from 'antd';

function MyComponent() {
  const { message } = App.useApp();

  const handleAction = async () => {
    try {
      await somePluginApi();
      message.success('操作成功');
    } catch (err) {
      message.error(`操作失败: ${(err as Error).message}`);
    }
  };
}
```

### 8.3 性能优化

- **避免重复请求**：利用 `usePlugins()` 返回的 `plugins` 数据，避免组件内重复调用 `pluginApi.getPlugins()`
- **资源去重**：`PluginLoader` 内部已维护 `loadedScripts` 和 `loadedLinks` 集合，不会重复加载同一资源
- **事件节流**：SSE 事件触发 `refresh()` 时，`PluginContext` 内部通过 `useCallback` 和 `useMemo` 避免不必要的重渲染

### 8.4 路由命名规范

- 路由路径统一使用 `/plugins/{plugin-name}` 前缀
- 菜单 key 使用 `{plugin-name}` 或 `{plugin-name}-{page}` 格式
- 避免与系统内置路由冲突

### 8.5 权限与安全

- 插件所需权限在 `PluginInfo.permissions` 中声明，由后端管理
- 前端不直接处理权限校验，依赖后端 API 的鉴权机制
- 敏感操作（卸载、禁用）需用户二次确认

## 9. 常见问题

### Q1: 插件安装后页面没有显示菜单

**可能原因**：
- 插件的 `frontend_entry` 为 `null`，没有前端资源
- JS 资源加载失败（检查浏览器 Network 面板）
- 插件未在 JS 入口中调用 `pluginRegistry.registerMenu()`

**排查步骤**：
1. 在插件管理页面确认插件状态为 `enabled`
2. 打开浏览器开发者工具，查看 Console 和 Network 面板是否有错误
3. 确认 `/api/plugins/{name}/assets/index.js` 能正常访问

### Q2: 启用插件后提示"待重启"

这是因为插件的 `load_type` 为 `restart`，需要重启后端服务才能生效。热加载（`hot`）类型的插件启用后可立即使用。

### Q3: 如何在插件中使用项目的通用组件和 API

插件代码与主应用共享同一运行环境，可以直接导入：

```typescript
import { apiRequest } from '@/api';
import { usePlugins } from '@/plugins';
// 也可以导入项目中的通用组件
import { PageHeader } from '@/components';
```

### Q4: 插件卸载后菜单和路由仍然显示

正常情况下 `pluginRegistry.unregisterPlugin(name)` 会清除该插件的所有菜单和路由。如果出现残留，可能是：

- 插件 JS 资源未正确卸载，仍在内存中注册了菜单/路由
- 需要刷新页面让 `PluginProvider` 重新加载插件列表

### Q5: 如何调试插件的 SSE 事件

在浏览器 Console 中手动监听：

```javascript
const es = new EventSource('/api/plugins/events');
es.onmessage = (e) => console.log('message:', JSON.parse(e.data));
['plugin_loaded', 'plugin_unloaded', 'plugin_installed', 'plugin_uninstalled', 'plugin_error']
  .forEach((evt) => es.addEventListener(evt, (e) => console.log(evt, JSON.parse(e.data))));
```

### Q6: 多个插件注册了相同路径的路由会怎样

`PluginRegistry.registerRoute()` 按 `path` 去重，只有第一个注册的路由会生效，后续相同路径的注册会被忽略。请确保每个插件使用唯一的路由路径。
