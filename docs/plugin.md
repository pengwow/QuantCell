# QuantCell 插件开发指南

## 1. 简介

QuantCell 插件系统允许开发者在现有框架中扩展新的菜单、页面和接口，支持前后端都可用的插件。

本指南将详细介绍 QuantCell 插件的开发流程、环境配置、项目结构和核心功能实现，帮助开发者快速上手插件开发。

## 2. 开发环境配置

### 2.1 前端环境

**系统要求**：
- Node.js >= 16.x
- Bun >= 1.0.0

**配置步骤**：

1. 安装依赖
   ```bash
   cd quantcell/frontend
   bun install
   ```

2. 启动开发服务器
   ```bash
   bun run dev
   ```

3. 构建生产版本
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
   cd quantcell/backend
   uv install
   ```

2. 启动开发服务器
   ```bash
   uvicorn main:app --reload
   ```

## 3. 项目结构说明

### 3.1 项目根目录结构

```
quantcell/
├── backend/                # 后端代码
│   ├── plugins/            # 后端插件目录
│   ├── main.py            # 后端入口文件
│   └── ...
├── frontend/             # 前端代码
│   ├── src/
│   │   ├── plugins/       # 前端插件目录
│   │   └── ...
│   └── ...
└── docs/                  # 文档目录
    └── README.md         # 插件开发指南
```

### 3.2 后端插件目录结构

```
backend/plugins/
├── example_plugin/        # 示例后端插件
│   ├── __init__.py
│   ├── plugin.py         # 插件入口
│   ├── plugin.py         # 插件入口
│   └── manifest.json     # 插件清单
├── plugin_base.py        # 插件基类
├── plugin_manager.py     # 插件管理器
└── api.py               # 插件 API
```

### 3.3 前端插件目录结构

```
frontend/src/plugins/
├── demo-plugin/          # 示例前端插件
│   ├── components/       # 组件目录
│   │   └── DemoPage.tsx  # 示例页面组件
│   ├── index.tsx         # 插件入口
│   └── manifest.json     # 插件清单
├── PluginBase.tsx        # 插件基类
├── PluginManager.tsx     # 插件管理器
└── index.tsx             # 插件系统入口
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
  "dependencies": []
}
```

#### 步骤 3：实现插件类

**文件路径**：`backend/plugins/my_backend_plugin/plugin.py`

```python
from plugins.plugin_base import PluginBase
from fastapi import APIRouter

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
                "version": self.version
            }
    
    def register(self, plugin_manager):
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")
    
    def start(self):
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")

def register_plugin():
    return MyBackendPlugin()
```

### 4.2 前端插件开发流程

#### 步骤 1：创建插件目录

```bash
mkdir -p frontend/src/plugins/my-frontend-plugin/components
```

#### 步骤 2：编写插件清单

**文件路径**：`frontend/src/plugins/my-frontend-plugin/manifest.json`

```json
{
  "name": "my-frontend-plugin",
  "version": "1.0.0",
  "description": "我的前端插件",
  "author": "开发者",
  "main": "index.tsx",
  "dependencies": []
}
```

#### 步骤 3：实现插件类

**文件路径**：`frontend/src/plugins/my-frontend-plugin/index.tsx`

```typescript
import { PluginBase } from '../PluginBase';
import { MyPage } from './components/MyPage';

export class MyFrontendPlugin extends PluginBase {
  constructor() {
    super(
      'my-frontend-plugin', 
      '1.0.0', 
      '我的前端插件', 
      '开发者'
    );
  }

  public register(): void {
    super.register();
    
    // 添加菜单
    this.addMenu({
      group: '我的插件',
      items: [
        {
          path: '/plugins/my-frontend',
          name: '我的页面'
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/my-frontend',
      element: <MyPage />
    });
  }
}

export function registerPlugin(): MyFrontendPlugin {
  return new MyFrontendPlugin();
}
```

#### 步骤 4：实现页面组件

**文件路径**：`frontend/src/plugins/my-frontend-plugin/components/MyPage.tsx`

```typescript
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

export default MyPage;
```

## 5. 核心功能模块实现

### 5.1 后端核心组件

#### PluginBase 基类

**文件路径**：`backend/plugins/plugin_base.py`

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `__init__` | 初始化插件 | `name: str`, `version: str` | `None` |
| `register` | 注册插件 | `plugin_manager: PluginManager` | `None` |
| `start` | 启动插件 | - | `None` |
| `stop` | 停止插件 | - | `None` |
| `get_info` | 获取插件信息 | - | `Dict[str, str]` |

#### PluginManager 类

**文件路径**：`backend/plugins/plugin_manager.py`

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `scan_plugins` | 扫描插件目录 | - | `List[str]` |
| `load_plugin` | 加载指定插件 | `plugin_name: str` | `bool` |
| `load_all_plugins` | 加载所有插件 | - | `List[str]` |
| `register_plugins` | 注册插件路由 | `app: FastAPI` | `None` |

### 5.2 前端核心组件

#### PluginBase 类

**文件路径**：`frontend/src/plugins/PluginBase.tsx`

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `__init__` | 初始化插件 | `name: str`, `version: str`, `description?: string`, `author?: string` | `None` |
| `register` | 注册插件 | - | `None` |
| `start` | 启动插件 | - | `None` |
| `stop` | 停止插件 | - | `None` |
| `addMenu` | 添加菜单 | `menuGroup: MenuGroup` | `None` |
| `addRoute` | 添加路由 | `route: RouteConfig` | `None` |

#### PluginManager 类

**文件路径**：`frontend/src/plugins/PluginManager.tsx`

**核心方法**：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `init` | 初始化插件管理器 | - | `Promise<void>` |
| `getAllMenus` | 获取所有插件菜单 | - | `MenuGroup[]` |
| `getAllRoutes` | 获取所有插件路由 | - | `RouteConfig[]` |

## 6. 插件安装与第三方包支持

### 6.1 后端插件第三方包支持

**当前实现**：
- 后端插件系统目前没有内置的依赖安装机制
- 插件可以使用项目已安装的依赖

**使用项目依赖**：
```python
# 在插件中直接导入项目已安装的依赖
from fastapi import APIRouter
import pandas as pd
```

**处理插件特有依赖**：
```bash
# 方法 1：将依赖添加到项目的 pyproject.toml
cd quantcell/backend
uv add <dependency>

# 方法 2：在插件目录中创建虚拟环境
cd quantcell/backend/plugins/my_plugin
python -m venv venv
source venv/bin/activate
pip install <dependency>
```

### 6.2 前端插件第三方包支持

**当前实现**：
- 前端插件使用项目统一的依赖管理
- 插件可以直接使用项目已安装的依赖

**添加新依赖**：
```bash
cd quantcell/frontend
bun add <dependency>
```

### 6.3 插件打包与分发

**主流分发方式**：

1. **本地文件分发**
   - **优点**：简单直接，适合内部开发和测试
   - **缺点**：手动安装，版本管理困难
   - **使用方法**：将插件目录复制到对应插件目录

2. **Git 仓库分发**
   - **优点**：版本控制，便于更新和协作
   - **缺点**：需要手动克隆或拉取更新
   - **使用方法**：
     ```bash
     git clone <plugin-repo-url> backend/plugins/my_plugin
     ```

3. **NPM/PyPI 包分发**
   - **优点**：标准化，版本管理方便，自动安装依赖
   - **缺点**：需要发布流程，适合成熟插件
   - **使用方法**：
     ```bash
     # 后端
     uv add <plugin-package>
     
     # 前端
     bun add <plugin-package>
     ```

4. **插件市场分发**
   - **优点**：集中管理，用户友好，支持搜索和评分
   - **缺点**：需要搭建和维护市场平台
   - **使用方法**：通过平台搜索、安装和更新插件

**推荐方式**：
- 开发阶段：本地文件分发
- 测试阶段：Git 仓库分发
- 生产阶段：NPM/PyPI 包分发或插件市场分发

## 7. API 接口说明

### 7.1 后端插件 API

#### 插件注册接口

**路径**：`/api/plugins/<plugin_name>/`
**方法**：`GET`
**返回示例**：
```json
{
  "message": "Hello from example plugin!",
  "plugin_name": "example_plugin",
  "version": "1.0.0"
}
```

#### 插件测试接口

**路径**：`/api/plugins/<plugin_name>/test`
**方法**：`GET`
**返回示例**：
```json
{
  "test": "success",
  "data": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

### 7.2 前端插件 API

#### MenuGroup 接口

```typescript
interface MenuGroup {
  group: string;
  items: MenuItem[];
}
```

#### MenuItem 接口

```typescript
interface MenuItem {
  path: string;
  name: string;
  icon?: React.ReactNode;
}
```

#### RouteConfig 接口

```typescript
interface RouteConfig {
  path: string;
  element: React.ReactNode;
}
```

## 8. 示例插件说明

### 8.1 后端示例插件

**名称**：`example_plugin`
**路径**：`backend/plugins/example_plugin/`
**功能**：
- 提供两个 API 端点
- 展示插件系统的基本功能

**API 端点**：
- `GET /api/plugins/example/` - 返回插件基本信息
- `GET /api/plugins/example/test` - 返回测试数据

### 8.2 前端示例插件

**名称**：`demo-plugin`
**路径**：`frontend/src/plugins/demo-plugin/`
**功能**：
- 添加侧边栏菜单
- 实现示例页面
- 展示插件系统的基本功能

**页面内容**：
- 欢迎提示信息
- 插件功能演示
- 插件信息展示
- Ant Design 组件示例

## 9. 常见问题与解决方案

### 9.1 前端插件菜单不显示

**问题**：创建的前端插件菜单没有显示在左侧菜单中

**可能原因**：
- 插件目录名包含连字符（-），但正则表达式不支持

**解决方案**：
修改 `PluginManager.tsx` 中的正则表达式：

**文件路径**：`frontend/src/plugins/PluginManager.tsx`

```typescript
// 原代码
const match = path.match(/\./(\w+)/index\.tsx$/);

// 修改后
const match = path.match(/\./([\w-]+)/index\.tsx$/);
```

### 9.2 后端插件加载失败

**问题**：后端插件无法加载，日志显示错误

**可能原因**：
- 插件没有 `register_plugin` 函数
- 插件不是 `PluginBase` 的实例
- 依赖缺失

**解决方案**：
- 确保插件目录中有 `register_plugin` 函数
- 确保插件类继承自 `PluginBase`
- 检查并安装缺失的依赖

### 9.3 前端构建失败

**问题**：前端构建时出现 TypeScript 错误

**可能原因**：
- 类型导入语法错误
- 类型定义不匹配
- 未使用的导入

**解决方案**：
- 使用 `import type` 语法导入类型
- 确保类型定义匹配
- 移除未使用的导入
- 使用 `export type` 语法重新导出类型

### 9.4 插件路由冲突

**问题**：插件添加的路由与现有路由冲突

**解决方案**：
- 为插件路由使用唯一的前缀，如 `/plugins/<plugin-name>/`
- 在添加路由前检查是否已存在

### 9.5 插件间通信

**问题**：插件之间需要通信和数据共享

**解决方案**：
- **后端**：使用事件系统或共享状态管理
- **前端**：使用 React Context 或状态管理库（如 Zustand）

## 10. 插件测试与验证

### 10.1 后端插件测试

**手动测试**：
```bash
# 启动后端服务
cd quantcell/backend
uvicorn main:app --reload

# 使用 curl 测试
curl http://localhost:8000/api/plugins/example/
```

**自动测试**：
```bash
# 运行测试
cd quantcell/backend
pytest tests/
```

### 10.2 前端插件测试

**开发模式测试**：
```bash
# 启动前端开发服务器
cd quantcell/frontend
bun run dev

# 在浏览器中访问
# http://localhost:5173
```

**构建测试**：
```bash
# 构建前端项目
cd quantcell/frontend
bun run build
```

## 11. 最佳实践

### 11.1 插件命名规范

- 插件名称使用小写字母和连字符
- 目录名与插件名保持一致
- 版本号使用语义化版本规范

### 11.2 代码结构

- 保持插件代码模块化
- 分离核心逻辑和路由
- 提供清晰的文档注释

### 11.3 性能优化

- 插件懒加载
- 避免不必要的依赖
- 优化资源使用

### 11.4 安全性

- 验证用户输入
- 限制插件权限
- 定期更新依赖

### 11.5 插件生命周期管理

```typescript
// 前端插件生命周期示例
export class MyPlugin extends PluginBase {
  constructor() {
    super('my-plugin', '1.0.0');
  }

  public register(): void {
    // 插件注册时执行，添加菜单、路由等
    super.register();
  }

  public start(): void {
    // 插件启动时执行，初始化资源等
    super.start();
  }

  public stop(): void {
    // 插件停止时执行，清理资源等
    super.stop();
  }
}
```

## 12. 贡献指南

### 12.1 提交插件

1. 确保插件符合 QuantCell 插件规范
2. 提供完整的文档和示例
3. 提交到插件仓库

### 12.2 报告问题

- 在 GitHub Issues 中报告问题
- 提供详细的错误信息和复现步骤
- 包括环境信息和插件版本

### 12.3 代码规范

- 后端使用 PEP 8 规范
- 前端使用 TypeScript 规范
- 遵循项目现有的代码风格

## 13. 联系方式

- 项目地址：https://github.com/quantcell-project/quantcell
- 文档地址：https://quantcell-project.github.io/docs

---

**文档版本**：1.0.0
**最后更新**：2025-12-31
**作者**：pengwow