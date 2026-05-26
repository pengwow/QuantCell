# 前端插件能力详细规范

本文档详细描述了 QuantCell 前端插件系统的能力、接口和使用规范。前端插件系统基于 **PluginContext/PluginRegistry/PluginLoader** 模式，提供完整的插件管理能力。

## 1. 前端插件系统架构

### 1.1 核心组件

| 组件 | 描述 | 职责 |
|------|------|------|
| `PluginContext` | 全局状态管理 | 提供 `PluginProvider` 组件和 `usePlugins()` Hook，管理插件列表和状态 |
| `PluginRegistry` | 单例注册中心 | 负责插件、菜单和路由的注册与管理，支持发布订阅模式 |
| `PluginLoader` | 动态资源加载 | 支持动态加载插件的 CSS 和 JavaScript 资源 |
| `pluginApi` | API 客户端 | 封装所有插件相关 API 调用（安装、卸载、启用、禁用等） |
| `listenPluginEvents` | SSE 事件监听 | 实时监听插件状态变化事件（plugin_loaded/unloaded/installed/uninstalled/error） |
| `PluginManagement` | 插件管理 UI | 提供完整的插件管理界面（/setting/plugins 路由） |

### 1.2 插件目录结构

```
frontend/
└── src/
    └── plugins/
        ├── index.ts               # 插件系统入口
        ├── PluginContext.tsx       # 全局状态管理（PluginProvider + usePlugins()）
        ├── PluginRegistry.ts      # 单例注册中心
        ├── PluginLoader.ts        # 动态资源加载
        ├── types.ts               # 类型定义
        └── api/
            └── plugin.ts          # API 客户端和 SSE 事件监听
```

## 2. 全局状态管理（PluginContext）规范

### 2.1 PluginProvider 组件

`PluginProvider` 是一个 React 组件，提供插件状态的全局上下文：

```typescript
import { PluginProvider } from '../plugins/PluginContext';

function App() {
  return (
    <PluginProvider>
      <YourApp />
    </PluginProvider>
  );
}
```

### 2.2 usePlugins() Hook

`usePlugins()` Hook 提供插件状态和方法：

```typescript
const {
  plugins,           // 插件列表
  loading,           // 加载状态
  error,             // 错误信息
  refreshPlugins,    // 刷新插件列表
  installPlugin,     // 安装插件
  uninstallPlugin,   // 卸载插件
  enablePlugin,      // 启用插件
  disablePlugin,     // 禁用插件
  loadPluginAssets,  // 加载插件资源
  unloadPluginAssets // 卸载插件资源
} = usePlugins();
```

### 2.3 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `refreshPlugins` | 刷新插件列表 | 无 | `Promise<void>` |
| `installPlugin` | 安装插件 | `file: File` | `Promise<boolean>` |
| `uninstallPlugin` | 卸载插件 | `name: string` | `Promise<boolean>` |
| `enablePlugin` | 启用插件 | `name: string` | `Promise<boolean>` |
| `disablePlugin` | 禁用插件 | `name: string` | `Promise<boolean>` |
| `loadPluginAssets` | 加载插件资源 | `name: string` | `Promise<void>` |
| `unloadPluginAssets` | 卸载插件资源 | `name: string` | `void` |
| `getConfig` | 获取插件配置值 | `key: string` | `any` |
| `setConfig` | 设置插件配置值 | `key: string`, `value: any` | `void` |

## 3. 单例注册中心（PluginRegistry）规范

### 3.1 获取实例

```typescript
import { PluginRegistry } from '../plugins/PluginRegistry';

const registry = PluginRegistry.getInstance();
```

### 3.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `registerPlugin` | 注册插件 | `plugin: Plugin` | `void` |
| `unregisterPlugin` | 注销插件 | `name: string` | `void` |
| `registerMenu` | 注册菜单 | `pluginName: string`, `menu: MenuConfig` | `void` |
| `unregisterMenu` | 注销菜单 | `pluginName: string`, `menuId: string` | `void` |
| `registerRoute` | 注册路由 | `pluginName: string`, `route: RouteConfig` | `void` |
| `unregisterRoute` | 注销路由 | `pluginName: string`, `path: string` | `void` |
| `getPlugin` | 获取插件 | `name: string` | `Plugin | undefined` |
| `getPlugins` | 获取所有插件 | 无 | `Plugin[]` |
| `getMenus` | 获取所有菜单 | 无 | `MenuConfig[]` |
| `getRoutes` | 获取所有路由 | 无 | `RouteConfig[]` |
| `subscribe` | 订阅事件 | `event: string`, `callback: Function` | `string` (handler_id) |
| `notify` | 发布事件 | `event: string`, `data?: any` | `void` |

### 3.3 发布订阅机制

PluginRegistry 支持发布订阅模式，用于插件间通信：

```typescript
// 订阅事件
const handlerId = registry.subscribe('pluginStateChanged', (data) => {
  console.log('插件状态变化:', data);
});

// 发布事件
registry.notify('pluginStateChanged', { pluginName: 'my_plugin', enabled: true });

// 取消订阅
registry.unsubscribe(handlerId);
```

## 4. 动态资源加载（PluginLoader）规范

### 4.1 获取实例

```typescript
import { PluginLoader } from '../plugins/PluginLoader';

const loader = PluginLoader.getInstance();
```

### 4.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `loadPluginAssets` | 加载插件资源 | `pluginName: string` | `Promise<void>` |
| `unloadPluginAssets` | 卸载插件资源 | `pluginName: string` | `void` |

### 4.3 使用示例

```typescript
const loader = PluginLoader.getInstance();

// 加载插件资源
await loader.loadPluginAssets('my_plugin');

// 卸载插件资源
loader.unloadPluginAssets('my_plugin');
```

## 5. API 客户端（pluginApi）规范

### 5.1 导入

```typescript
import { pluginApi } from '../api/plugin';
```

### 5.2 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `getPlugins` | 获取所有插件 | 无 | `Promise<Plugin[]>` |
| `getPlugin` | 获取指定插件 | `name: string` | `Promise<Plugin>` |
| `installFromZip` | 从ZIP文件安装 | `file: File` | `Promise<boolean>` |
| `installFromGit` | 从Git仓库安装 | `gitUrl: string`, `branch?: string` | `Promise<boolean>` |
| `uninstallPlugin` | 卸载插件 | `name: string` | `Promise<boolean>` |
| `enablePlugin` | 启用插件 | `name: string` | `Promise<boolean>` |
| `disablePlugin` | 禁用插件 | `name: string` | `Promise<boolean>` |
| `getPluginConfig` | 获取插件配置 | `name: string` | `Promise<object>` |

### 5.3 使用示例

```typescript
import { pluginApi } from '../api/plugin';

// 获取所有插件
const plugins = await pluginApi.getPlugins();

// 从ZIP文件安装插件
const fileInput = document.querySelector('input[type="file"]');
const file = fileInput.files[0];
await pluginApi.installFromZip(file);

// 从Git仓库安装插件
await pluginApi.installFromGit('https://github.com/example/plugin.git', 'main');

// 启用插件
await pluginApi.enablePlugin('my_plugin');

// 禁用插件
await pluginApi.disablePlugin('my_plugin');

// 卸载插件
await pluginApi.uninstallPlugin('my_plugin');

// 获取插件配置
const config = await pluginApi.getPluginConfig('my_plugin');
```

## 6. SSE 事件监听（listenPluginEvents）规范

### 6.1 导入

```typescript
import { listenPluginEvents } from '../api/plugin';
```

### 6.2 事件类型

| 事件类型 | 描述 | 数据结构 |
|----------|------|----------|
| `plugin_loaded` | 插件资源加载完成 | `{ plugin_name: string }` |
| `plugin_unloaded` | 插件资源卸载完成 | `{ plugin_name: string }` |
| `plugin_installed` | 插件安装完成 | `{ plugin_name: string, version: string }` |
| `plugin_uninstalled` | 插件卸载完成 | `{ plugin_name: string }` |
| `plugin_error` | 插件发生错误 | `{ plugin_name: string, error: string }` |

### 6.3 使用示例

```typescript
import { listenPluginEvents } from '../api/plugin';

// 监听插件事件
const eventSource = listenPluginEvents((event) => {
  switch (event.type) {
    case 'plugin_loaded':
      console.log(`插件 ${event.data.plugin_name} 已加载`);
      break;
    case 'plugin_unloaded':
      console.log(`插件 ${event.data.plugin_name} 已卸载`);
      break;
    case 'plugin_installed':
      console.log(`插件 ${event.data.plugin_name} 已安装，版本: ${event.data.version}`);
      break;
    case 'plugin_uninstalled':
      console.log(`插件 ${event.data.plugin_name} 已卸载`);
      break;
    case 'plugin_error':
      console.error(`插件 ${event.data.plugin_name} 发生错误: ${event.data.error}`);
      break;
  }
});

// 关闭事件监听
eventSource.close();
```

## 7. 插件管理 UI（PluginManagement）规范

### 7.1 路由配置

插件管理界面位于 `/setting/plugins` 路由，提供完整的插件管理功能。

### 7.2 功能特性

- **卡片视图**：以卡片形式展示所有已安装的插件
- **安装功能**：支持从ZIP文件和Git仓库安装插件
- **启停控制**：启用/禁用插件
- **卸载功能**：卸载不需要的插件
- **详情查看**：查看插件详细信息、配置和状态

### 7.3 组件结构

```typescript
// PluginManagement.tsx
import React from 'react';
import { usePlugins } from '../PluginContext';
import { pluginApi } from '../api/plugin';

const PluginManagement: React.FC = () => {
  const { plugins, loading, error, refreshPlugins } = usePlugins();
  
  // 渲染插件卡片列表
  // 安装、卸载、启用、禁用等操作
  // 详情查看
};

export default PluginManagement;
```

## 8. 类型定义

### 8.1 插件类型（Plugin）

```typescript
export interface Plugin {
  name: string;           // 插件名称
  version: string;        // 插件版本
  description?: string;   // 插件描述
  author?: string;        // 插件作者
  load_type?: 'hot' | 'restart';  // 加载类型
  enabled: boolean;       // 启用状态
  frontend_entry?: string;  // 前端入口文件路径
  config?: object;        // 插件配置
}
```

### 8.2 菜单配置类型（MenuConfig）

```typescript
export interface MenuConfig {
  id: string;           // 菜单ID
  label: string;        // 菜单标签
  path: string;         // 路由路径
  icon?: string;        // 图标
  group?: string;       // 菜单分组
}
```

### 8.3 路由配置类型（RouteConfig）

```typescript
export interface RouteConfig {
  path: string;                    // 路由路径
  component: React.ComponentType;  // React组件
  exact?: boolean;                 // 精确匹配
  meta?: object;                   // 路由元数据
}
```

### 8.4 插件事件类型（PluginEvent）

```typescript
export interface PluginEvent {
  type: 'plugin_loaded' | 'plugin_unloaded' | 'plugin_installed' | 'plugin_uninstalled' | 'plugin_error';
  data: {
    plugin_name: string;
    version?: string;
    error?: string;
  };
  timestamp: string;
}
```

## 9. 插件清单文件（manifest.json）规范

### 9.1 必需字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `string` | 插件名称（唯一标识符） |
| `version` | `string` | 插件版本（遵循语义化版本 X.Y.Z） |
| `description` | `string` | 插件描述 |

### 9.2 可选字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `author` | `string` | 插件作者 |
| `load_type` | `string` | 加载类型：`hot`（热加载）或 `restart`（重启加载），默认为 `hot` |
| `frontend_entry` | `string` | 前端入口文件路径，默认为 `frontend/index.html` |
| `permissions` | `array` | 所需权限列表 |
| `config_schema` | `object` | 配置模式定义 |

### 9.3 示例

```json
{
  "name": "example_plugin",
  "version": "1.0.0",
  "description": "示例插件，演示插件系统的基本功能",
  "author": "QuantCell Team",
  "load_type": "hot",
  "frontend_entry": "frontend/index.html",
  "permissions": ["database:read"],
  "config_schema": {}
}
```

## 10. 插件实现规范

### 10.1 核心要求

1. **必须**提供 `manifest.json` 清单文件
2. **必须**包含 `frontend_entry` 指向前端入口文件
3. **必须**通过 `PluginRegistry` 注册菜单和路由
4. **建议**使用 `usePlugins()` Hook 获取插件状态
5. **不再**需要继承 `PluginBase` 类

### 10.2 前端入口文件

```typescript
// frontend/index.tsx
import { PluginRegistry } from '../plugins/PluginRegistry';
import ExamplePage from './components/ExamplePage';

const registry = PluginRegistry.getInstance();

// 注册插件
registry.registerPlugin({
  name: 'example_plugin',
  version: '1.0.0',
  description: '示例插件',
  author: 'QuantCell Team',
  enabled: true
});

// 注册菜单
registry.registerMenu('example_plugin', {
  id: 'example',
  label: '示例插件',
  path: '/example',
  icon: 'ExampleIcon'
});

// 注册路由
registry.registerRoute('example_plugin', {
  path: '/example',
  component: ExamplePage
});
```

## 11. 插件生命周期管理

### 11.1 生命周期流程

1. **安装**：通过 API 或插件管理界面安装插件
2. **加载**：`PluginLoader` 加载插件的 CSS 和 JavaScript 资源
3. **注册**：插件通过 `PluginRegistry` 注册菜单和路由
4. **启用**：通过 API 或插件管理界面启用插件
5. **运行**：插件处于活动状态
6. **禁用**：通过 API 或插件管理界面禁用插件
7. **卸载**：`PluginLoader` 卸载插件资源

### 11.2 生命周期事件

| 事件 | 触发时机 | 处理方法 |
|------|----------|----------|
| `loadPluginAssets` | 插件资源加载时 | `PluginLoader.loadPluginAssets()` |
| `unloadPluginAssets` | 插件资源卸载时 | `PluginLoader.unloadPluginAssets()` |
| `enablePlugin` | 插件启用时 | `usePlugins().enablePlugin()` |
| `disablePlugin` | 插件禁用时 | `usePlugins().disablePlugin()` |

## 12. 热重载机制

### 12.1 开发环境热重载

在开发环境中，插件管理器通过 Vite 的热更新机制实现插件热重载：

```typescript
// 开发环境热重载
if (import.meta.env.DEV && import.meta.hot) {
  console.log('启用插件热重载');
  
  // 简化热重载逻辑：当任何文件变化时，重新加载所有插件
  import.meta.hot.on('vite:beforeUpdate', () => {
    // 这里简化处理，实际项目中可以根据变化的文件路径更精确地刷新插件
    const loader = PluginLoader.getInstance();
    // 重新加载插件
  });
}
```

### 12.2 手动热重载

插件管理器提供了手动热重载插件的方法：

```typescript
const loader = PluginLoader.getInstance();

// 重新加载指定插件资源
await loader.loadPluginAssets('example_plugin');

// 重新加载所有插件资源
// 需要遍历插件列表逐个加载
```

## 13. 插件配置管理

### 13.1 系统配置注册

插件可以通过后端 API 注册系统配置项：

```python
# 后端插件注册配置
class ExamplePlugin(PluginBase):
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "example_plugin"
        # ...
    
    def get_config_schema(self) -> dict:
        """获取配置模式"""
        return {
            "example_enabled": {
                "type": "boolean",
                "default": True,
                "description": "启用示例功能"
            },
            "example_mode": {
                "type": "select",
                "options": ["standard", "advanced", "expert"],
                "default": "standard",
                "description": "示例模式"
            }
        }
```

### 13.2 配置值获取和设置

插件可以获取和设置配置值：

```typescript
// 获取配置值
const enabled = getConfig('example_enabled');

// 设置配置值
setConfig('example_enabled', true);
```

## 14. 插件间通信机制

### 14.1 插件实例访问

插件可以通过 `PluginRegistry` 访问其他插件：

```typescript
import { PluginRegistry } from '../plugins/PluginRegistry';

const registry = PluginRegistry.getInstance();

// 获取其他插件
const otherPlugin = registry.getPlugin('other_plugin');

// 获取所有插件
const allPlugins = registry.getPlugins();
```

### 14.2 事件系统

插件可以通过 `PluginRegistry` 的发布订阅机制进行通信：

```typescript
// 订阅事件
const handlerId = registry.subscribe('dataUpdated', (data) => {
  console.log('收到数据更新事件:', data);
});

// 发布事件
registry.notify('dataUpdated', { key: 'value' });

// 取消订阅
registry.unsubscribe(handlerId);
```

### 14.3 前端状态共享

插件可以通过 React Context 进行状态共享：

```typescript
import { usePlugins } from '../plugins/PluginContext';

const { plugins, refreshPlugins } = usePlugins();

// 获取插件状态
const myPlugin = plugins.find(p => p.name === 'my_plugin');

// 刷新插件列表
await refreshPlugins();
```

## 15. 插件开发最佳实践

### 15.1 代码组织

- **组件化**：将UI拆分为可复用组件
- **模块化**：将功能分解为多个模块
- **类型安全**：充分利用 TypeScript 的类型系统
- **文档化**：为公共API提供清晰的文档

### 15.2 性能优化

- **代码分割**：使用动态导入减少初始加载时间
- **懒加载**：对大型组件使用 React.lazy
- **缓存**：合理使用 React.memo 和 useMemo
- **虚拟滚动**：对长列表使用虚拟滚动

### 15.3 用户体验

- **响应式设计**：确保插件在不同屏幕尺寸下正常显示
- **加载状态**：提供清晰的加载状态指示
- **错误处理**：妥善处理错误并向用户提供反馈
- **无障碍**：遵循 WCAG 无障碍标准

### 15.4 安全性

- **输入验证**：验证所有用户输入
- **XSS 防护**：避免直接插入 HTML
- **CSRF 防护**：遵循前端安全最佳实践
- **权限控制**：尊重用户权限设置

## 16. 插件兼容性要求

### 16.1 TypeScript 版本

- 支持 TypeScript 4.0+

### 16.2 React 版本

- 支持 React 17.0+

### 16.3 依赖管理

- 插件依赖应在 `manifest.json` 中声明
- 避免与核心依赖冲突
- 使用兼容的依赖版本

### 16.4 API 兼容性

- 遵循文档中定义的 API 规范
- 向后兼容旧版本 API
- 优雅处理 API 变更

## 17. 插件部署和集成流程

### 17.1 开发环境部署

1. **创建插件目录**：在 `frontend/src/plugins/` 下创建插件目录
2. **编写插件代码**：实现插件核心逻辑和UI
3. **配置清单文件**：编写 `manifest.json` 文件
4. **启动开发服务器**：插件管理器会自动加载新插件

### 17.2 生产环境部署

1. **构建插件**：运行 `bun run build` 构建前端应用
2. **注入插件列表**：在 `index.html` 中注入插件列表
3. **部署应用**：将构建产物部署到服务器

### 17.3 集成测试

- 验证插件是否正确加载
- 测试插件路由是否可访问
- 验证插件菜单是否正确显示
- 测试插件功能是否正常
- 检查插件与核心功能的兼容性

## 18. 插件能力评估标准

| 标准 | 描述 | 评分 |
|------|------|------|
| 功能完整性 | 插件功能是否完整实现 | 1-5 |
| UI 设计 | 插件界面是否美观、易用 | 1-5 |
| 代码质量 | 代码是否清晰、规范 | 1-5 |
| 性能表现 | 插件性能是否良好 | 1-5 |
| 兼容性 | 插件是否与系统兼容 | 1-5 |
| 安全性 | 插件是否安全可靠 | 1-5 |
| 文档完整性 | 文档是否完整清晰 | 1-5 |

## 19. 常见问题与解决方案

### 19.1 插件加载失败

**问题**：插件管理器无法加载插件

**解决方案**：
- 检查 `manifest.json` 文件格式是否正确
- 确保插件入口文件存在且包含 `frontend_entry` 字段
- 检查插件依赖是否安装
- 查看浏览器控制台的错误信息

### 19.2 路由注册失败

**问题**：插件路由无法访问

**解决方案**：
- 确保插件已通过 `PluginRegistry` 注册路由
- 检查路由路径是否正确
- 验证插件是否启用
- 检查路由配置是否正确

### 19.3 菜单不显示

**问题**：插件注册的菜单不显示

**解决方案**：
- 确保插件已通过 `PluginRegistry` 注册菜单
- 检查菜单格式是否正确
- 验证插件是否启用
- 查看浏览器控制台的错误信息

### 19.4 热重载不工作

**问题**：修改插件代码后热重载不生效

**解决方案**：
- 确保开发服务器正在运行
- 检查 Vite 配置是否正确
- 尝试手动刷新插件
- 查看浏览器控制台的错误信息

## 20. 附录

### 20.1 示例插件代码

```typescript
// frontend/src/plugins/example-plugin/index.tsx
import { PluginRegistry } from '../PluginRegistry';
import ExamplePage from './components/ExamplePage';

const registry = PluginRegistry.getInstance();

// 注册插件
registry.registerPlugin({
  name: 'example_plugin',
  version: '1.0.0',
  description: '示例插件',
  author: 'QuantCell Team',
  enabled: true
});

// 注册菜单
registry.registerMenu('example_plugin', {
  id: 'example',
  label: '示例插件',
  path: '/example',
  icon: 'ExampleIcon'
});

// 注册路由
registry.registerRoute('example_plugin', {
  path: '/example',
  component: ExamplePage
});
```

### 20.2 插件管理器配置

| 配置项 | 描述 | 默认值 |
|--------|------|--------|
| `hotReload` | 是否启用热重载 | `true` (开发环境) |
| `autoLoad` | 是否自动加载插件 | `true` |
| `pluginDir` | 插件目录路径 | `./src/plugins` |

### 20.3 开发工具和资源

- **IDE**：Visual Studio Code
- **包管理器**：Bun
- **构建工具**：Vite
- **类型检查**：TypeScript
- **代码格式化**：Prettier
- **代码检查**：ESLint