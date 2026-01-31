# 前端插件开发指南

## 1. 前端插件目录结构

前端插件采用标准化的目录结构，每个插件是一个独立的目录，位于 `/frontend/src/plugins/` 目录下。

### 1.1 基本目录结构

```
frontend/src/plugins/
├── example-plugin/           # 插件目录
│   ├── manifest.json         # 插件清单文件
│   ├── index.tsx             # 插件主文件
│   ├── components/            # 插件组件目录（可选）
│   │   └── ExamplePage.tsx    # 插件页面组件
│   ├── hooks/                 # 插件钩子目录（可选）
│   │   └── useExample.ts
│   ├── services/              # 插件服务目录（可选）
│   │   └── exampleService.ts
│   └── utils/                 # 插件工具目录（可选）
│       └── exampleUtils.ts
├── PluginBase.tsx             # 插件基类
├── PluginManager.tsx          # 插件管理器
└── index.tsx                  # 插件系统入口
```

### 1.2 目录结构说明

- **插件目录**：插件的根目录，名称应与插件名称一致，建议使用连字符命名法
- **manifest.json**：插件清单文件，包含插件的基本信息和配置
- **index.tsx**：插件主文件，包含插件的核心实现和注册逻辑
- **components/**：插件组件目录，包含插件的React组件（可选）
- **hooks/**：插件钩子目录，包含插件的自定义React钩子（可选）
- **services/**：插件服务目录，包含插件的API调用和业务逻辑（可选）
- **utils/**：插件工具目录，包含插件的工具函数（可选）

## 2. 前端插件清单文件规范

每个前端插件都需要一个 `manifest.json` 文件，用于描述插件的基本信息和配置。

### 2.1 清单文件字段定义

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `name` | string | 是 | 插件名称，应与插件目录名称一致 |
| `version` | string | 是 | 插件版本，遵循语义化版本规范 |
| `description` | string | 是 | 插件描述，简要说明插件的功能 |
| `author` | string | 是 | 插件作者 |
| `main` | string | 是 | 插件主文件路径，默认为 `index.tsx` |
| `dependencies` | array | 否 | 插件依赖的其他插件或库 |

### 2.2 示例清单文件

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

## 3. 前端插件基类使用指南

前端插件需要继承 `PluginBase` 类，并实现必要的方法。

### 3.1 插件基类核心方法

| 方法 | 描述 | 参数 | 返回值 |
|------|------|------|--------|
| `constructor` | 初始化插件 | `name`: 插件名称<br>`version`: 插件版本<br>`description`: 插件描述（可选）<br>`author`: 插件作者（可选） | 无 |
| `register` | 注册插件 | 无 | 无 |
| `start` | 启动插件 | 无 | 无 |
| `stop` | 停止插件 | 无 | 无 |
| `getInfo` | 获取插件信息 | 无 | `PluginInfo` 对象 |
| `addMenu` | 添加菜单 | `menuGroup`: 菜单组配置 | 无 |
| `getMenus` | 获取插件菜单 | 无 | 菜单数组 |
| `addRoute` | 添加路由 | `route`: 路由配置 | 无 |
| `getRoutes` | 获取插件路由 | 无 | 路由数组 |
| `addSystemConfig` | 添加系统配置项 | `config`: 系统配置项 | 无 |
| `getSystemConfigs` | 获取插件系统配置 | 无 | 系统配置数组 |
| `setConfigMenuName` | 设置配置菜单名称 | `name`: 菜单名称 | 无 |
| `getConfigMenuName` | 获取配置菜单名称 | 无 | 菜单名称 |
| `getConfig` | 获取插件配置值 | `key`: 配置键名 | 配置值 |
| `setConfig` | 设置插件配置值 | `key`: 配置键名<br>`value`: 配置值 | 无 |

### 3.2 插件基类使用示例

```typescript
import { PluginBase } from '../PluginBase';

export class ExamplePlugin extends PluginBase {
  constructor() {
    super(
      'example-plugin', 
      '1.0.0', 
      '示例前端插件', 
      'QuantCell Team'
    );
  }

  public register(): void {
    super.register();
    console.log(`插件 ${this.name} 注册成功`);
  }

  public start(): void {
    super.start();
    console.log(`插件 ${this.name} 启动成功`);
  }

  public stop(): void {
    super.stop();
    console.log(`插件 ${this.name} 停止成功`);
  }
}

export function registerPlugin(): ExamplePlugin {
  return new ExamplePlugin();
}
```

## 4. 前端插件菜单和路由注册

前端插件可以通过插件基类的方法注册菜单和路由，以便在系统中显示和访问。

### 4.1 菜单注册

#### 4.1.1 菜单项类型定义

```typescript
// 菜单项类型定义
export interface MenuItem {
  path: string;       // 菜单项路径
  name: string;       // 菜单项名称
  icon?: React.ReactNode;  // 菜单项图标（可选）
}

// 菜单组类型定义
export interface MenuGroup {
  group: string;      // 菜单组名称
  items: MenuItem[];  // 菜单项数组
}
```

#### 4.1.2 菜单注册示例

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
  }
}
```

### 4.2 路由注册

#### 4.2.1 路由配置类型定义

```typescript
// 路由配置类型定义
export interface RouteConfig {
  path: string;           // 路由路径
  element: React.ReactNode;  // 路由组件
}
```

#### 4.2.2 路由注册示例

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

  public register(): void {
    super.register();
    
    // 添加路由
    this.addRoute({
      path: '/plugins/example',
      element: <ExamplePage />
    });
  }
}
```

### 4.3 菜单和路由注册注意事项

- **路径命名**：建议使用 `/plugins/{plugin-name}` 作为路由和菜单路径前缀
- **菜单分组**：合理组织菜单分组，避免过多顶级菜单
- **图标使用**：对于菜单项，可使用系统提供的图标或自定义图标
- **路由组件**：路由组件应使用React函数组件或类组件
- **懒加载**：对于大型插件，可使用React.lazy进行组件懒加载

## 5. 前端插件系统配置

前端插件可以通过插件基类的方法注册系统配置项，这些配置项会显示在系统设置页面中。

### 5.1 系统配置项类型定义

```typescript
// 系统配置项类型定义
export interface SystemConfigItem {
  key: string;                // 配置项键名
  value: string | number | boolean;  // 配置项值
  description: string;         // 配置项描述
  type: 'string' | 'number' | 'boolean' | 'select';  // 配置项类型
  options?: string[];          // 当type为select时的选项（可选）
}
```

### 5.2 系统配置注册示例

```typescript
import { PluginBase } from '../PluginBase';

export class ExamplePlugin extends PluginBase {
  constructor() {
    super(
      'example-plugin', 
      '1.0.0', 
      '示例前端插件', 
      'QuantCell Team'
    );
  }

  public register(): void {
    super.register();
    
    // 添加系统配置项
    this.addSystemConfig({
      key: 'example_enabled',
      value: true,
      description: '启用示例插件',
      type: 'boolean'
    });
    
    this.addSystemConfig({
      key: 'example_mode',
      value: 'normal',
      description: '示例插件模式',
      type: 'select',
      options: ['normal', 'advanced', 'expert']
    });
    
    this.addSystemConfig({
      key: 'example_timeout',
      value: 30,
      description: '示例插件超时时间（秒）',
      type: 'number'
    });
    
    this.addSystemConfig({
      key: 'example_api_url',
      value: 'https://api.example.com',
      description: '示例API地址',
      type: 'string'
    });
    
    // 设置配置菜单名称
    this.setConfigMenuName('示例插件设置');
  }
}
```

### 5.3 系统配置使用示例

```typescript
import { PluginBase } from '../PluginBase';

export class ExamplePlugin extends PluginBase {
  constructor() {
    super(
      'example-plugin', 
      '1.0.0', 
      '示例前端插件', 
      'QuantCell Team'
    );
  }

  public someMethod() {
    // 获取配置值
    const enabled = this.getConfig('example_enabled');
    const mode = this.getConfig('example_mode');
    const timeout = this.getConfig('example_timeout');
    const apiUrl = this.getConfig('example_api_url');
    
    console.log('示例插件配置:', {
      enabled,
      mode,
      timeout,
      apiUrl
    });
    
    // 设置配置值
    this.setConfig('example_enabled', false);
  }
}
```

## 6. 前端插件示例实现

以下是一个完整的前端插件示例实现。

### 6.1 插件主文件（index.tsx）

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
    
    // 添加系统配置项
    this.addSystemConfig({
      key: 'example_enabled',
      value: true,
      description: '启用示例插件',
      type: 'boolean'
    });
    
    this.addSystemConfig({
      key: 'example_mode',
      value: 'normal',
      description: '示例插件模式',
      type: 'select',
      options: ['normal', 'advanced', 'expert']
    });
    
    // 设置配置菜单名称
    this.setConfigMenuName('示例插件设置');
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

### 6.2 插件页面组件（components/ExamplePage.tsx）

```typescript
import React, { useState, useEffect } from 'react';
import { Card, CardContent, Typography, Button, Box } from '@mui/material';

export const ExamplePage: React.FC = () => {
  const [data, setData] = useState<{ message: string } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // 页面加载时获取数据
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      // 调用后端API获取数据
      const response = await fetch('/api/plugins/example/');
      if (response.ok) {
        const result = await response.json();
        setData(result);
      } else {
        console.error('获取数据失败:', response.statusText);
      }
    } catch (error) {
      console.error('获取数据错误:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        示例插件页面
      </Typography>
      
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            插件信息
          </Typography>
          {loading ? (
            <Typography>加载中...</Typography>
          ) : data ? (
            <Box>
              <Typography>消息: {data.message}</Typography>
              <Typography>插件名称: {data.plugin_name}</Typography>
              <Typography>版本: {data.version}</Typography>
            </Box>
          ) : (
            <Typography>无数据</Typography>
          )}
          <Button 
            variant="contained" 
            color="primary" 
            onClick={fetchData} 
            sx={{ mt: 2 }}
          >
            刷新数据
          </Button>
        </CardContent>
      </Card>
      
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            插件功能
          </Typography>
          <Typography paragraph>
            这是一个示例前端插件页面，演示了如何创建和使用前端插件。
          </Typography>
          <Typography paragraph>
            插件可以：
          </Typography>
          <ul>
            <li>注册自定义菜单</li>
            <li>添加自定义路由</li>
            <li>注册系统配置项</li>
            <li>调用后端API</li>
            <li>实现自定义功能</li>
          </ul>
        </CardContent>
      </Card>
    </Box>
  );
};
```

### 6.3 插件服务文件（services/exampleService.ts）

```typescript
/**
 * 示例插件服务
 */
export class ExampleService {
  /**
   * 获取示例数据
   */
  static async getExampleData(): Promise<{ message: string; plugin_name: string; version: string }> {
    const response = await fetch('/api/plugins/example/');
    if (!response.ok) {
      throw new Error('获取示例数据失败');
    }
    return response.json();
  }

  /**
   * 获取测试数据
   */
  static async getTestData(): Promise<{ test: string; data: Record<string, string> }> {
    const response = await fetch('/api/plugins/example/test');
    if (!response.ok) {
      throw new Error('获取测试数据失败');
    }
    return response.json();
  }

  /**
   * 提交数据
   */
  static async submitData(data: any): Promise<{ message: string; data: any }> {
    const response = await fetch('/api/plugins/example/data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      throw new Error('提交数据失败');
    }
    return response.json();
  }
}
```

## 6. 前端插件开发最佳实践

### 6.1 代码组织

- **模块化设计**：将代码按功能模块组织
- **组件拆分**：合理拆分React组件，保持组件简洁
- **状态管理**：对于复杂状态，可使用React Context或状态管理库
- **类型定义**：使用TypeScript类型定义，提高代码可维护性
- **文档注释**：为公共组件和函数添加文档注释

### 6.2 性能优化

- **组件优化**：使用React.memo、useMemo、useCallback等优化组件性能
- **懒加载**：对于大型组件，使用React.lazy和Suspense进行懒加载
- **网络请求**：合理使用缓存，减少重复请求
- **渲染优化**：避免不必要的渲染，使用虚拟列表处理大量数据

### 6.3 用户体验

- **响应式设计**：确保插件页面在不同屏幕尺寸下正常显示
- **加载状态**：为异步操作添加加载状态
- **错误处理**：适当处理错误并显示友好的错误信息
- **动画效果**：为页面切换和交互添加适当的动画效果
- **无障碍访问**：确保插件页面符合无障碍访问标准

### 6.4 安全性

- **输入验证**：验证所有用户输入
- **API调用**：使用安全的API调用方式，处理认证和授权
- **数据保护**：对敏感数据进行适当保护
- **XSS防护**：避免使用不安全的DOM操作，防止XSS攻击

## 7. 前端插件测试

### 7.1 测试方法

- **单元测试**：测试单个组件和函数
- **集成测试**：测试插件与其他组件的集成
- **端到端测试**：测试插件的完整功能流程

### 7.2 测试示例

```typescript
// 示例组件测试
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ExamplePage } from './components/ExamplePage';

// 模拟fetch API
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      message: 'Hello from example plugin!',
      plugin_name: 'example-plugin',
      version: '1.0.0'
    })
  })
) as jest.Mock;

describe('ExamplePage', () => {
  test('renders example page', () => {
    render(<ExamplePage />);
    expect(screen.getByText('示例插件页面')).toBeInTheDocument();
    expect(screen.getByText('插件信息')).toBeInTheDocument();
    expect(screen.getByText('插件功能')).toBeInTheDocument();
  });

  test('fetches data on mount', async () => {
    render(<ExamplePage />);
    
    await waitFor(() => {
      expect(screen.getByText('Hello from example plugin!')).toBeInTheDocument();
      expect(screen.getByText('example-plugin')).toBeInTheDocument();
      expect(screen.getByText('1.0.0')).toBeInTheDocument();
    });
  });

  test('refreshes data on button click', async () => {
    render(<ExamplePage />);
    
    const refreshButton = screen.getByText('刷新数据');
    fireEvent.click(refreshButton);
    
    await waitFor(() => {
      expect(screen.getByText('Hello from example plugin!')).toBeInTheDocument();
    });
  });
});

// 示例服务测试
describe('ExampleService', () => {
  test('getExampleData returns correct data', async () => {
    const data = await ExampleService.getExampleData();
    expect(data).toHaveProperty('message');
    expect(data).toHaveProperty('plugin_name');
    expect(data).toHaveProperty('version');
  });

  test('getTestData returns correct data', async () => {
    const data = await ExampleService.getTestData();
    expect(data).toHaveProperty('test');
    expect(data).toHaveProperty('data');
  });

  test('submitData returns correct data', async () => {
    const testData = { key: 'value' };
    const data = await ExampleService.submitData(testData);
    expect(data).toHaveProperty('message');
    expect(data).toHaveProperty('data');
  });
});
```

## 8. 前端插件部署

### 8.1 插件打包

前端插件会与主应用一起打包，无需单独打包。在构建过程中，插件会被自动包含在应用 bundle 中。

### 8.2 插件安装

1. **复制插件目录**：将插件目录复制到 `/frontend/src/plugins/` 目录
2. **构建应用**：运行 `bun run build` 构建前端应用
3. **部署应用**：部署构建后的应用

### 8.3 插件卸载

1. **删除插件目录**：删除 `/frontend/src/plugins/` 目录下的插件目录
2. **构建应用**：运行 `bun run build` 重新构建前端应用
3. **部署应用**：部署重新构建后的应用

## 9. 常见问题和解决方案

### 9.1 插件加载失败

**问题**：插件无法加载
**解决方案**：
- 检查插件目录结构是否正确
- 检查 `manifest.json` 文件是否有效
- 检查插件主文件是否存在 `registerPlugin` 函数
- 检查插件是否继承自 `PluginBase` 类
- 检查插件是否正确导出 `registerPlugin` 函数

### 9.2 菜单和路由不显示

**问题**：插件注册的菜单和路由不显示
**解决方案**：
- 检查菜单和路由是否正确注册
- 检查路径是否正确
- 检查插件是否已启动
- 检查浏览器控制台是否有错误信息

### 9.3 API调用失败

**问题**：插件无法调用后端API
**解决方案**：
- 检查API路径是否正确
- 检查后端插件是否已加载
- 检查后端API是否正常工作
- 检查浏览器控制台是否有网络错误

### 9.4 系统配置不显示

**问题**：插件注册的系统配置不显示在系统设置页面
**解决方案**：
- 检查系统配置是否正确注册
- 检查配置项类型是否正确
- 检查插件是否已启动
- 检查系统设置页面是否正确加载插件配置

## 10. 总结

前端插件开发是扩展 QuantCell 系统功能的重要方式。通过遵循本指南的规范和最佳实践，开发者可以创建高质量、可维护的前端插件。

前端插件开发应注重用户体验、性能优化和代码质量，同时保持良好的文档和测试覆盖率。这样可以确保插件与系统的兼容性和稳定性，为用户提供更好的体验。