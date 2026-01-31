# 前端插件能力详细规范

## 1. 前端插件系统架构

### 1.1 核心组件

| 组件 | 描述 | 职责 |
|------|------|------|
| `PluginBase` | 插件基类 | 提供插件生命周期方法和UI注册能力 |
| `PluginManager` | 插件管理器 | 负责加载、管理和热重载插件 |
| `pluginManager` | 管理器实例 | 全局插件管理器单例 |

### 1.2 插件目录结构

```
frontend/
src/
└── plugins/
    ├── example-plugin/
    │   ├── components/         # 插件组件目录
    │   │   └── ExamplePage.tsx # 示例页面组件
    │   ├── index.tsx            # 插件入口文件
    │   └── manifest.json        # 插件清单文件
    ├── PluginBase.tsx           # 插件基类
    ├── PluginManager.tsx        # 插件管理器
    └── index.tsx                # 插件系统入口
```

## 2. 插件基类（PluginBase）规范

### 2.1 构造函数

```typescript
constructor(name: string, version: string, description?: string, author?: string) {
  this.name = name;
  this.version = version;
  this.description = description;
  this.author = author;
  this.isActive = false;
  this.menus = [];
  this.routes = [];
  this.systemConfigs = [];
  this.configMenuName = `${name} ${'settings'}`;
}
```

### 2.2 核心属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `name` | `string` | 插件名称 |
| `version` | `string` | 插件版本 |
| `description` | `string` | 插件描述 |
| `author` | `string` | 插件作者 |
| `isActive` | `boolean` | 插件是否激活 |
| `menus` | `MenuGroup[]` | 插件注册的菜单 |
| `routes` | `RouteConfig[]` | 插件注册的路由 |
| `systemConfigs` | `SystemConfigItem[]` | 插件注册的系统配置 |
| `configMenuName` | `string` | 插件配置子菜单名称 |

### 2.3 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `register` | 注册插件 | 无 | `void` |
| `start` | 启动插件 | 无 | `void` |
| `stop` | 停止插件 | 无 | `void` |
| `addMenu` | 添加菜单 | `menuGroup: MenuGroup` | `void` |
| `addRoute` | 添加路由 | `route: RouteConfig` | `void` |
| `getInfo` | 获取插件信息 | 无 | `PluginInfo` |
| `getMenus` | 获取插件菜单 | 无 | `MenuGroup[]` |
| `getRoutes` | 获取插件路由 | 无 | `RouteConfig[]` |
| `addSystemConfig` | 添加系统配置项 | `config: SystemConfigItem` | `void` |
| `getSystemConfigs` | 获取插件系统配置 | 无 | `SystemConfigItem[]` |
| `setConfigMenuName` | 设置配置菜单名称 | `name: string` | `void` |
| `getConfigMenuName` | 获取配置菜单名称 | 无 | `string` |
| `getConfig` | 获取插件配置值 | `key: string` | `any` |
| `setConfig` | 设置插件配置值 | `key: string`, `value: any` | `void` |

## 3. 类型定义

### 3.1 菜单项类型（MenuItem）

```typescript
export interface MenuItem {
  path: string;      // 菜单项路径
  name: string;      // 菜单项名称
  icon?: React.ReactNode; // 菜单项图标（可选）
}
```

### 3.2 菜单组类型（MenuGroup）

```typescript
export interface MenuGroup {
  group: string;     // 菜单组名称
  items: MenuItem[]; // 菜单项列表
}
```

### 3.3 路由配置类型（RouteConfig）

```typescript
export interface RouteConfig {
  path: string;              // 路由路径
  element: React.ReactNode;  // 路由组件
}
```

### 3.4 系统配置项类型（SystemConfigItem）

```typescript
export interface SystemConfigItem {
  key: string;                // 配置键名
  value: string | number | boolean; // 配置值
  description: string;        // 配置描述
  type: 'string' | 'number' | 'boolean' | 'select'; // 配置类型
  options?: string[];         // 当type为select时的选项
}
```

### 3.5 插件信息类型（PluginInfo）

```typescript
export interface PluginInfo {
  name: string;       // 插件名称
  version: string;    // 插件版本
  description?: string; // 插件描述
  author?: string;    // 插件作者
}
```

### 3.6 插件类型（Plugin）

```typescript
export interface Plugin {
  name: string;       // 插件名称
  instance: PluginBase; // 插件实例
}
```

## 4. 插件管理器（PluginManager）规范

### 4.1 核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `init` | 初始化插件管理器 | 无 | `Promise<void>` |
| `loadPlugins` | 加载所有插件 | 无 | `Promise<void>` |
| `loadPlugin` | 加载指定插件 | `pluginName: string` | `Promise<void>` |
| `startAllPlugins` | 启动所有插件 | 无 | `void` |
| `stopAllPlugins` | 停止所有插件 | 无 | `void` |
| `getPlugins` | 获取所有插件 | 无 | `Map<string, Plugin>` |
| `getPlugin` | 获取指定插件 | `pluginName: string` | `Plugin | undefined` |
| `getAllMenus` | 获取所有插件菜单 | 无 | `MenuGroup[]` |
| `getAllRoutes` | 获取所有插件路由 | 无 | `RouteConfig[]` |
| `getAllPluginConfigs` | 获取所有插件系统配置 | 无 | `Array<{name: string, configs: any[], menuName: string}>` |
| `reloadPlugin` | 刷新指定插件 | `pluginName: string` | `Promise<void>` |
| `reloadAllPlugins` | 刷新所有插件 | 无 | `Promise<void>` |
| `installPlugin` | 安装新插件 | `pluginName: string` | `Promise<void>` |
| `uninstallPlugin` | 卸载插件 | `pluginName: string` | `Promise<void>` |
| `setupHotReload` | 设置热重载 | 无 | `void` |

### 4.2 单例模式

插件管理器使用单例模式，通过 `getInstance` 方法获取实例：

```typescript
public static getInstance(): PluginManager {
  if (!PluginManager.instance) {
    PluginManager.instance = new PluginManager();
  }
  return PluginManager.instance;
}

// 导出插件管理器实例
export const pluginManager = PluginManager.getInstance();
```

## 5. 插件清单文件（manifest.json）规范

### 5.1 必需字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `string` | 插件名称（唯一标识符） |
| `version` | `string` | 插件版本（遵循语义化版本） |
| `description` | `string` | 插件描述 |
| `author` | `string` | 插件作者 |

### 5.2 可选字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `main` | `string` | 插件主入口文件路径 |
| `dependencies` | `array` | 插件依赖列表 |

### 5.3 示例

```json
{
  "name": "example-plugin",
  "version": "1.0.0",
  "description": "示例前端插件",
  "author": "QuantCell Team",
  "main": "index.tsx",
  "dependencies": []
}
```

## 6. 插件实现规范

### 6.1 核心要求

1. **必须**继承 `PluginBase` 类
2. **必须**提供 `registerPlugin` 函数作为插件入口
3. **必须**在 `manifest.json` 中定义插件信息
4. **建议**在 `register` 方法中注册菜单和路由

### 6.2 插件入口函数

```typescript
export function registerPlugin(): ExamplePlugin {
  return new ExamplePlugin();
}
```

### 6.3 菜单和路由注册

插件可以在 `register` 方法中注册菜单和路由：

```typescript
public register(): void {
  super.register();
  
  // 添加菜单
  this.addMenu({
    group: '插件示例',
    items: [
      {
        path: '/plugins/example',
        name: '示例页面',
        icon: undefined // 使用默认图标
      }
    ]
  });
  
  // 添加路由
  this.addRoute({
    path: '/plugins/example',
    element: <ExamplePage />
  });
}
```

## 7. 插件生命周期管理

### 7.1 生命周期流程

1. **初始化**：插件管理器初始化
2. **加载**：动态导入插件模块
3. **注册**：调用插件的 `register` 方法
4. **启动**：调用插件的 `start` 方法
5. **运行**：插件处于活动状态
6. **停止**：调用插件的 `stop` 方法
7. **卸载**：从插件管理器中移除插件

### 7.2 生命周期事件

| 事件 | 触发时机 | 处理方法 |
|------|----------|----------|
| `register` | 插件被注册时 | `register()` |
| `start` | 插件启动时 | `start()` |
| `stop` | 插件停止时 | `stop()` |

## 8. 热重载机制

### 8.1 开发环境热重载

在开发环境中，插件管理器通过 Vite 的热更新机制实现插件热重载：

```typescript
public setupHotReload(): void {
  if (import.meta.env.DEV && import.meta.hot) {
    console.log('启用插件热重载');
    
    // 简化热重载逻辑：当任何文件变化时，重新加载所有插件
    import.meta.hot.on('vite:beforeUpdate', () => {
      // 这里简化处理，实际项目中可以根据变化的文件路径更精确地刷新插件
      this.reloadAllPlugins();
    });
  }
}
```

### 8.2 手动热重载

插件管理器提供了手动热重载插件的方法：

```typescript
// 刷新指定插件
await pluginManager.reloadPlugin('example-plugin');

// 刷新所有插件
await pluginManager.reloadAllPlugins();
```

## 9. 插件配置管理

### 9.1 系统配置注册

插件可以注册系统配置项：

```typescript
// 添加系统配置项
this.addSystemConfig({
  key: 'example_enabled',
  value: true,
  description: '启用示例功能',
  type: 'boolean'
});

// 添加带选项的配置项
this.addSystemConfig({
  key: 'example_mode',
  value: 'standard',
  description: '示例模式',
  type: 'select',
  options: ['standard', 'advanced', 'expert']
});
```

### 9.2 配置值获取和设置

插件可以获取和设置配置值：

```typescript
// 获取配置值
const enabled = this.getConfig('example_enabled');

// 设置配置值
this.setConfig('example_enabled', true);
```

### 9.3 配置菜单

插件可以自定义配置菜单名称：

```typescript
// 设置配置菜单名称
this.setConfigMenuName('示例插件设置');

// 获取配置菜单名称
const menuName = this.getConfigMenuName();
```

## 10. 插件间通信机制

### 10.1 插件实例访问

插件可以通过插件管理器访问其他插件实例：

```typescript
// 获取指定插件
const otherPlugin = pluginManager.getPlugin('other-plugin');

// 获取所有插件
const allPlugins = pluginManager.getPlugins();
```

### 10.2 全局状态管理

插件可以使用全局状态管理库（如 Redux、MobX 等）进行通信：

```typescript
// 示例：使用 Redux
import { useDispatch, useSelector } from 'react-redux';

// 分发动作
dispatch({ type: 'EXAMPLE_ACTION', payload: data });

// 选择状态
const state = useSelector((state) => state.example);
```

### 10.3 事件总线

插件可以使用事件总线进行通信：

```typescript
// 示例：使用事件总线
import eventBus from '../utils/eventBus';

// 订阅事件
eventBus.on('exampleEvent', (data) => {
  console.log('收到事件:', data);
});

// 发布事件
eventBus.emit('exampleEvent', { key: 'value' });
```

## 11. 插件开发最佳实践

### 11.1 代码组织

- **组件化**：将UI拆分为可复用组件
- **模块化**：将功能分解为多个模块
- **类型安全**：充分利用 TypeScript 的类型系统
- **文档化**：为公共API提供清晰的文档

### 11.2 性能优化

- **代码分割**：使用动态导入减少初始加载时间
- **懒加载**：对大型组件使用 React.lazy
- **缓存**：合理使用 React.memo 和 useMemo
- **虚拟滚动**：对长列表使用虚拟滚动

### 11.3 用户体验

- **响应式设计**：确保插件在不同屏幕尺寸下正常显示
- **加载状态**：提供清晰的加载状态指示
- **错误处理**：妥善处理错误并向用户提供反馈
- **无障碍**：遵循 WCAG 无障碍标准

### 11.4 安全性

- **输入验证**：验证所有用户输入
- **XSS 防护**：避免直接插入 HTML
- **CSRF 防护**：遵循前端安全最佳实践
- **权限控制**：尊重用户权限设置

## 12. 插件兼容性要求

### 12.1 TypeScript 版本

- 支持 TypeScript 4.0+

### 12.2 React 版本

- 支持 React 17.0+

### 12.3 依赖管理

- 插件依赖应在 `manifest.json` 中声明
- 避免与核心依赖冲突
- 使用兼容的依赖版本

### 12.4 API 兼容性

- 遵循文档中定义的 API 规范
- 向后兼容旧版本 API
- 优雅处理 API 变更

## 13. 插件部署和集成流程

### 13.1 开发环境部署

1. **创建插件目录**：在 `frontend/src/plugins/` 下创建插件目录
2. **编写插件代码**：实现插件核心逻辑和UI
3. **配置清单文件**：编写 `manifest.json` 文件
4. **启动开发服务器**：插件管理器会自动加载新插件

### 13.2 生产环境部署

1. **构建插件**：运行 `bun run build` 构建前端应用
2. **注入插件列表**：在 `index.html` 中注入插件列表
3. **部署应用**：将构建产物部署到服务器

### 13.3 集成测试

- 验证插件是否正确加载
- 测试插件路由是否可访问
- 验证插件菜单是否正确显示
- 测试插件功能是否正常
- 检查插件与核心功能的兼容性

## 14. 插件能力评估标准

| 标准 | 描述 | 评分 |
|------|------|------|
| 功能完整性 | 插件功能是否完整实现 | 1-5 |
| UI 设计 | 插件界面是否美观、易用 | 1-5 |
| 代码质量 | 代码是否清晰、规范 | 1-5 |
| 性能表现 | 插件性能是否良好 | 1-5 |
| 兼容性 | 插件是否与系统兼容 | 1-5 |
| 安全性 | 插件是否安全可靠 | 1-5 |
| 文档完整性 | 文档是否完整清晰 | 1-5 |

## 15. 常见问题与解决方案

### 15.1 插件加载失败

**问题**：插件管理器无法加载插件

**解决方案**：
- 检查 `manifest.json` 文件格式是否正确
- 确保插件入口文件存在且包含 `registerPlugin` 函数
- 检查插件依赖是否安装
- 查看浏览器控制台的错误信息

### 15.2 路由注册失败

**问题**：插件路由无法访问

**解决方案**：
- 确保路由路径格式正确
- 检查路由组件是否正确导出
- 验证插件是否正确加载
- 查看浏览器控制台的错误信息

### 15.3 菜单不显示

**问题**：插件注册的菜单不显示

**解决方案**：
- 确保菜单格式正确
- 检查插件是否正确加载
- 验证菜单组和菜单项配置
- 查看浏览器控制台的错误信息

### 15.4 热重载不工作

**问题**：修改插件代码后热重载不生效

**解决方案**：
- 确保开发服务器正在运行
- 检查 Vite 配置是否正确
- 尝试手动刷新插件
- 查看浏览器控制台的错误信息

## 16. 附录

### 16.1 示例插件代码

```typescript
import { PluginBase } from '../PluginBase';
import { ExamplePage } from './components/ExamplePage';

export class ExamplePlugin extends PluginBase {
  constructor() {
    super(
      'example-plugin', 
      '1.0.0', 
      '示例前端插件', 
      'QuantCell Team'
    );
  }

  /**
   * 注册插件，添加菜单和路由
   */
  public register(): void {
    super.register();
    
    // 添加菜单
    this.addMenu({
      group: '插件示例',
      items: [
        {
          path: '/plugins/example',
          name: '示例页面',
          icon: undefined // 使用默认图标
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/example',
      element: <ExamplePage />
    });
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('示例插件启动成功');
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('示例插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): ExamplePlugin {
  return new ExamplePlugin();
}
```

### 16.2 插件管理器配置

| 配置项 | 描述 | 默认值 |
|--------|------|--------|
| `hotReload` | 是否启用热重载 | `true` (开发环境) |
| `autoLoad` | 是否自动加载插件 | `true` |
| `pluginDir` | 插件目录路径 | `./src/plugins` |

### 16.3 开发工具和资源

- **IDE**：Visual Studio Code
- **包管理器**：Bun
- **构建工具**：Vite
- **类型检查**：TypeScript
- **代码格式化**：Prettier
- **代码检查**：ESLint