# 插件实现模式示例

## 1. 后端插件实现模式

### 1.1 基础功能插件

**适用场景**：提供简单的API端点和基础功能

**实现示例**：

```python
from fastapi import APIRouter
from plugins.plugin_base import PluginBase, LoadType
from plugins.api import PluginAPI

class BasicPlugin(PluginBase):
    """基础功能插件示例"""
    
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "basic_plugin"
        self.version = "1.0.0"
        self.description = "基础功能插件示例"
        self.author = "QuantCell Team"
        self.load_type = LoadType.HOT
        self.router = APIRouter(prefix="/api/plugins/basic")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        @self.router.get("/")
        async def basic_root():
            """基础插件根路由"""
            return {
                "message": "Hello from basic plugin!",
                "plugin_name": self.name,
                "version": self.version
            }
        
        @self.router.get("/health")
        async def health_check():
            """健康检查路由"""
            return {"status": "healthy", "plugin": self.name}
    
    async def on_enable(self):
        """插件启用时调用"""
        self.enabled = True
        self.logger.info(f"{self.name} 插件已启用")
    
    async def on_disable(self):
        """插件禁用时调用"""
        self.enabled = False
        self.logger.info(f"{self.name} 插件已禁用")
    
    def get_frontend_assets(self) -> dict:
        """获取前端资源信息"""
        return {
            "js": ["/static/plugins/basic_plugin/index.js"],
            "css": ["/static/plugins/basic_plugin/index.css"]
        }
    
    def get_config_schema(self) -> dict:
        """获取配置模式"""
        return {
            "basic_enabled": {
                "type": "boolean",
                "default": True,
                "description": "启用基础功能"
            }
        }

def register_plugin(api: PluginAPI):
    """注册插件的入口函数"""
    return BasicPlugin(api)
```

**manifest.json**：

```json
{
  "name": "data_service",
  "version": "1.0.0",
  "description": "数据服务插件示例",
  "author": "QuantCell Team",
  "main": "plugin.py",
  "load_type": "hot",
  "permissions": ["read_data", "write_data"],
  "frontend_entry": "frontend/index.html"
}
```

### 1.2 服务提供插件

**适用场景**：提供可被其他插件使用的服务

**实现示例**：

```python
from plugins.plugin_base import PluginBase, LoadType
from plugins.api import PluginAPI

class ServiceProviderPlugin(PluginBase):
    """服务提供插件示例"""
    
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "service_provider"
        self.version = "1.0.0"
        self.description = "服务提供插件示例"
        self.author = "QuantCell Team"
        self.load_type = LoadType.HOT
    
    async def on_enable(self):
        """插件启用时注册服务"""
        self.enabled = True
        # 注册服务供其他插件使用
        self.api.register_service("my_service", MyService())
        self.logger.info(f"{self.name} 插件已启用，服务已注册")
    
    async def on_disable(self):
        """插件禁用时注销服务"""
        self.enabled = False
        self.logger.info(f"{self.name} 插件已禁用")
    
    def get_frontend_assets(self) -> dict:
        """获取前端资源信息"""
        return {
            "js": ["/static/plugins/service_provider/index.js"],
            "css": ["/static/plugins/service_provider/index.css"]
        }
    
    def get_config_schema(self) -> dict:
        """获取配置模式"""
        return {
            "service_enabled": {
                "type": "boolean",
                "default": True,
                "description": "启用服务提供功能"
            }
        }

def register_plugin(api: PluginAPI):
    """注册插件的入口函数"""
    return ServiceProviderPlugin(api)
```
### 1.3 定时任务插件

**适用场景**：执行定时任务和后台处理

**实现示例**：

```python
import asyncio
from plugins.plugin_base import PluginBase, LoadType
from plugins.api import PluginAPI

class ScheduledTaskPlugin(PluginBase):
    """定时任务插件示例"""
    
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "scheduled_task"
        self.version = "1.0.0"
        self.description = "定时任务插件示例"
        self.author = "QuantCell Team"
        self.load_type = LoadType.HOT
        self.task = None
        self.running = False
    
    async def on_enable(self):
        """插件启用时启动定时任务"""
        self.enabled = True
        self.running = True
        self.task = asyncio.create_task(self._run_scheduled_tasks())
        self.logger.info(f"{self.name} 插件已启用，定时任务已启动")
    
    async def on_disable(self):
        """插件禁用时停止定时任务"""
        self.enabled = False
        self.running = False
        if self.task:
            self.task.cancel()
        self.logger.info(f"{self.name} 插件已禁用，定时任务已停止")
    
    async def _run_scheduled_tasks(self):
        """运行定时任务"""
        while self.running:
            try:
                self.logger.info("执行定时任务")
                # 执行定时任务逻辑
                await self._perform_task()
                # 等待10秒
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"定时任务执行失败: {e}")
                await asyncio.sleep(10)
    
    async def _perform_task(self):
        """执行具体任务"""
        # 任务逻辑
        self.logger.info("定时任务执行中...")
        # 模拟任务执行
        await asyncio.sleep(1)
        self.logger.info("定时任务执行完成")
    
    def get_frontend_assets(self) -> dict:
        """获取前端资源信息"""
        return {
            "js": ["/static/plugins/scheduled_task/index.js"],
            "css": ["/static/plugins/scheduled_task/index.css"]
        }
    
    def get_config_schema(self) -> dict:
        """获取配置模式"""
        return {
            "task_interval": {
                "type": "number",
                "default": 10,
                "description": "任务执行间隔（秒）"
            }
        }

def register_plugin(api: PluginAPI):
    """注册插件的入口函数"""
    return ScheduledTaskPlugin(api)
```

### 1.4 事件处理插件

**适用场景**：响应系统事件和其他插件事件

**实现示例**：

```python
from plugins.plugin_base import PluginBase, LoadType
from plugins.api import PluginAPI

class EventHandlerPlugin(PluginBase):
    """事件处理插件示例"""
    
    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.name = "event_handler"
        self.version = "1.0.0"
        self.description = "事件处理插件示例"
        self.author = "QuantCell Team"
        self.load_type = LoadType.HOT
        self.handler_id = None
    
    async def on_enable(self):
        """插件启用时订阅事件"""
        self.enabled = True
        # 订阅事件
        self.handler_id = self.api.subscribe("data_updated", self._handle_data_updated)
        self.logger.info(f"{self.name} 插件已启用，事件订阅完成")
    
    async def on_disable(self):
        """插件禁用时取消订阅事件"""
        self.enabled = False
        # 取消订阅事件
        if self.handler_id:
            self.api.unsubscribe(self.handler_id)
        self.logger.info(f"{self.name} 插件已禁用，事件订阅已取消")
    
    def _handle_data_updated(self, event_data):
        """处理数据更新事件"""
        self.logger.info(f"收到数据更新事件: {event_data}")
        # 处理事件逻辑
    
    def get_frontend_assets(self) -> dict:
        """获取前端资源信息"""
        return {
            "js": ["/static/plugins/event_handler/index.js"],
            "css": ["/static/plugins/event_handler/index.css"]
        }
    
    def get_config_schema(self) -> dict:
        """获取配置模式"""
        return {
            "event_enabled": {
                "type": "boolean",
                "default": True,
                "description": "启用事件处理功能"
            }
        }

def register_plugin(api: PluginAPI):
    """注册插件的入口函数"""
    return EventHandlerPlugin(api)
```

## 2. 前端插件实现模式

### 2.1 基础UI插件

**适用场景**：提供简单的UI页面和基础功能

**实现示例**：

```typescript
// frontend/src/plugins/basic-ui-plugin/index.tsx
import { PluginRegistry } from '../PluginRegistry';
import { pluginApi } from '../api/plugin';
import { usePlugins } from '../PluginContext';
import BasicPage from './components/BasicPage';

const registry = PluginRegistry.getInstance();

// 注册插件
registry.registerPlugin({
  name: 'basic_ui_plugin',
  version: '1.0.0',
  description: '基础UI插件示例',
  author: 'QuantCell Team',
  enabled: true
});

// 注册菜单
registry.registerMenu('basic_ui_plugin', {
  id: 'basic-ui',
  label: '基础UI',
  path: '/basic-ui',
  icon: 'BasicUIIcon'
});

// 注册路由
registry.registerRoute('basic_ui_plugin', {
  path: '/basic-ui',
  component: BasicPage
});

// 在组件中使用 usePlugins Hook
const BasicUIComponent: React.FC = () => {
  const { plugins, loading, error } = usePlugins();
  
  // 获取当前插件状态
  const plugin = plugins.find(p => p.name === 'basic_ui_plugin');
  
  return (
    <div>
      <h1>基础UI插件</h1>
      <p>插件状态: {plugin?.enabled ? '已启用' : '已禁用'}</p>
    </div>
  );
};

export default BasicUIComponent;
```

### 2.2 配置管理插件

**适用场景**：提供可配置的功能和设置界面

**实现示例**：

```typescript
import React from 'react';
import { PluginRegistry } from '../PluginRegistry';
import { pluginApi } from '../api/plugin';
import { usePlugins } from '../PluginContext';
import ConfigPage from './components/ConfigPage';

const registry = PluginRegistry.getInstance();

// 注册插件
registry.registerPlugin({
  name: 'config_plugin',
  version: '1.0.0',
  description: '配置管理插件示例',
  author: 'QuantCell Team',
  enabled: true
});

// 注册菜单
registry.registerMenu('config_plugin', {
  id: 'config',
  label: '配置管理',
  path: '/config',
  icon: 'ConfigIcon'
});

// 注册路由
registry.registerRoute('config_plugin', {
  path: '/config',
  component: ConfigPage
});

// 在组件中使用 usePlugins Hook 和配置管理
const ConfigComponent: React.FC = () => {
  const { plugins, loading, error, getConfig, setConfig } = usePlugins();
  
  // 获取当前插件状态
  const plugin = plugins.find(p => p.name === 'config_plugin');
  
  // 获取配置值
  const enabled = getConfig('config_plugin_enabled');
  const mode = getConfig('config_plugin_mode');
  
  // 设置配置值
  const handleToggle = () => {
    setConfig('config_plugin_enabled', !enabled);
  };
  
  return (
    <div>
      <h1>配置管理插件</h1>
      <p>插件状态: {plugin?.enabled ? '已启用' : '已禁用'}</p>
      <div>
        <h2>配置项</h2>
        <label>
          <input 
            type="checkbox" 
            checked={enabled} 
            onChange={handleToggle}
          />
          启用配置管理插件
        </label>
        <p>当前模式: {mode}</p>
      </div>
    </div>
  );
};

export default ConfigComponent;
```

### 2.3 数据可视化插件

**适用场景**：提供数据可视化界面和图表

**实现示例**：

```typescript
import React, { useState, useEffect } from 'react';
import { PluginRegistry } from '../PluginRegistry';
import { pluginApi } from '../api/plugin';
import { usePlugins } from '../PluginContext';
import VisualizationPage from './components/VisualizationPage';

const registry = PluginRegistry.getInstance();

// 注册插件
registry.registerPlugin({
  name: 'visualization_plugin',
  version: '1.0.0',
  description: '数据可视化插件示例',
  author: 'QuantCell Team',
  enabled: true
});

// 注册菜单
registry.registerMenu('visualization_plugin', {
  id: 'visualization',
  label: '数据可视化',
  path: '/visualization',
  icon: 'VisualizationIcon'
});

// 注册路由
registry.registerRoute('visualization_plugin', {
  path: '/visualization',
  component: VisualizationPage
});

// 在组件中使用 usePlugins Hook
const VisualizationComponent: React.FC = () => {
  const { plugins, loading, error, getConfig } = usePlugins();
  
  // 获取当前插件状态
  const plugin = plugins.find(p => p.name === 'visualization_plugin');
  
  // 获取配置值
  const refreshInterval = getConfig('visualization_refresh_interval') || 5;
  
  return (
    <div>
      <h1>数据可视化插件</h1>
      <p>插件状态: {plugin?.enabled ? '已启用' : '已禁用'}</p>
      <p>刷新间隔: {refreshInterval} 秒</p>
      <VisualizationPage refreshInterval={refreshInterval} />
    </div>
  );
};

export default VisualizationComponent;
```

### 2.4 交互功能插件

**适用场景**：提供复杂的用户交互和动态功能

**实现示例**：

```typescript
import React, { useState } from 'react';
import { PluginRegistry } from '../PluginRegistry';
import { pluginApi } from '../api/plugin';
import { usePlugins } from '../PluginContext';
import InteractivePage from './components/InteractivePage';

const registry = PluginRegistry.getInstance();

// 注册插件
registry.registerPlugin({
  name: 'interactive_plugin',
  version: '1.0.0',
  description: '交互功能插件示例',
  author: 'QuantCell Team',
  enabled: true
});

// 注册菜单
registry.registerMenu('interactive_plugin', {
  id: 'interactive',
  label: '交互功能',
  path: '/interactive',
  icon: 'InteractiveIcon'
});

// 注册路由
registry.registerRoute('interactive_plugin', {
  path: '/interactive',
  component: InteractivePage
});

// 在组件中使用 usePlugins Hook
const InteractiveComponent: React.FC = () => {
  const { plugins, loading, error } = usePlugins();
  
  // 获取当前插件状态
  const plugin = plugins.find(p => p.name === 'interactive_plugin');
  
  return (
    <div>
      <h1>交互功能插件</h1>
      <p>插件状态: {plugin?.enabled ? '已启用' : '已禁用'}</p>
      <InteractivePage />
    </div>
  );
};

export default InteractiveComponent;
```

## 3. 插件实现最佳实践

### 3.1 代码组织

**后端插件**：
- 将路由和业务逻辑分离
- 使用模块化设计，将功能分解为多个文件
- 遵循 Python 代码风格规范（PEP 8）

**前端插件**：
- 使用组件化设计，拆分复杂UI
- 遵循 TypeScript 类型规范
- 保持代码风格一致性

### 3.2 错误处理

**后端插件**：
- 使用 try-except 捕获异常
- 记录详细的错误日志
- 提供友好的错误响应

**前端插件**：
- 使用 try-catch 捕获异常
- 实现错误边界组件
- 向用户展示友好的错误提示

### 3.3 性能优化

**后端插件**：
- 使用异步处理 IO 密集型操作
- 合理使用缓存减少重复计算
- 优化数据库查询

**前端插件**：
- 使用 React.memo 和 useMemo 减少不必要的渲染
- 实现组件懒加载
- 优化状态管理和更新

### 3.4 安全性

**后端插件**：
- 验证所有用户输入
- 遵循最小权限原则
- 避免 SQL 注入和 XSS 攻击

**前端插件**：
- 验证用户输入
- 避免直接操作 DOM
- 使用安全的 API 调用方式

### 3.5 文档化

**后端插件**：
- 为公共 API 添加文档字符串
- 提供插件使用说明
- 记录配置选项和依赖

**前端插件**：
- 使用 TypeScript 类型注释
- 为组件和函数添加 JSDoc 注释
- 提供插件功能说明

## 4. 插件开发工作流

### 4.1 后端插件开发流程

1. **创建插件目录**：在 `backend/plugins/` 下创建插件目录
2. **编写 manifest.json**：定义插件基本信息
3. **实现插件类**：继承 `PluginBase` 并实现核心方法
4. **注册路由**：根据需要注册 API 路由
5. **测试插件**：启动服务并测试插件功能
6. **部署插件**：将插件目录复制到生产环境

### 4.2 前端插件开发流程

1. **创建插件目录**：在 `frontend/src/plugins/` 下创建插件目录
2. **编写 manifest.json**：定义插件基本信息
3. **创建组件**：实现插件所需的 React 组件
4. **注册菜单和路由**：通过 `PluginRegistry.registerMenu()` 和 `PluginRegistry.registerRoute()` 注册
5. **获取插件状态**：通过 `usePlugins()` Hook 获取插件状态和操作
6. **测试插件**：启动开发服务器并测试插件功能
7. **构建部署**：运行构建命令并部署到生产环境

## 5. 插件示例总结

| 插件类型 | 后端示例 | 前端示例 | 适用场景 |
|---------|---------|---------|----------|
| 基础功能 | 基础功能插件 | 基础UI插件 | 提供简单的功能和界面 |
| 服务提供 | 服务提供插件 | - | 为其他插件提供服务 |
| 定时任务 | 定时任务插件 | - | 执行后台定时任务 |
| 事件处理 | 事件处理插件 | - | 响应系统和插件事件 |
| 配置管理 | - | 配置管理插件 | 提供可配置的功能 |
| 数据可视化 | - | 数据可视化插件 | 展示数据图表和可视化 |
| 交互功能 | - | 交互功能插件 | 提供复杂的用户交互 |

## 6. 插件开发注意事项

1. **命名规范**：插件名称应使用小写字母和连字符，避免使用空格和特殊字符
2. **版本管理**：遵循语义化版本规范（MAJOR.MINOR.PATCH）
3. **依赖管理**：明确声明插件依赖，避免与核心依赖冲突
4. **兼容性**：确保插件与系统核心版本兼容
5. **性能考虑**：避免插件占用过多资源影响系统性能
6. **安全性**：遵循安全最佳实践，避免引入安全漏洞
7. **文档完整**：提供清晰的插件文档和使用说明

## 7. 插件注册和发现

### 7.1 后端插件注册

后端插件通过 `register_plugin(api: PluginAPI)` 函数注册，插件管理器会自动发现并加载插件：

```python
def register_plugin(api: PluginAPI) -> PluginBase:
    """注册插件的入口函数"""
    return ExamplePlugin(api)
```

### 7.2 前端插件注册

前端插件通过 `PluginRegistry` 注册菜单和路由：

```typescript
import { PluginRegistry } from '../plugins/PluginRegistry';

const registry = PluginRegistry.getInstance();

registry.registerMenu('plugin_name', {
  id: 'example',
  label: '示例插件',
  path: '/example',
  icon: 'ExampleIcon'
});

registry.registerRoute('plugin_name', {
  path: '/example',
  component: ExamplePage
});
```

## 8. 插件生命周期管理

### 8.1 后端插件生命周期

1. **安装**：插件安装器解压并校验插件
2. **加载**：插件管理器根据 `load_type` 选择加载器动态导入模块
3. **注册**：调用 `register_plugin(api)` 获取实例，调用 `register()` 和 `start()`
4. **运行**：插件处理请求和事件
5. **启用/禁用**：调用 `on_enable()` / `on_disable()` 回调
6. **停止**：调用 `stop()` 方法

### 8.2 前端插件生命周期

1. **加载**：`PluginProvider` 挂载时通过 `pluginApi.getPlugins()` 获取插件列表
2. **注册**：插件信息注册到 `PluginRegistry`
3. **资源加载**：`PluginLoader.loadPluginAssets()` 加载 JS/CSS 资源
4. **运行**：插件渲染UI和处理用户交互
5. **状态更新**：SSE 事件监听自动刷新插件状态
6. **资源卸载**：`PluginLoader.unloadPluginAssets()` 移除资源

## 9. 插件通信示例

### 9.1 后端插件间通信

**服务注册与发现**：

```python
# 在插件A中注册服务
self.api.register_service("my_service", MyService())

# 在插件B中使用服务
my_service = self.api.get_service("my_service")
if my_service:
    result = my_service.do_something()
```

**事件总线通信**：

```python
from plugins.event_bus import event_bus

# 订阅事件
def on_data_updated(data):
    print(f"收到数据更新: {data}")
event_bus.subscribe("data_updated", on_data_updated)

# 发布事件
event_bus.publish("data_updated", {"key": "value"})
```

### 9.2 前端插件间通信

**通过 PluginRegistry 访问插件**：

```typescript
import { pluginRegistry } from '@/plugins';

const plugin = pluginRegistry.getPlugin('other_plugin');
if (plugin) {
  console.log('其他插件版本:', plugin.version);
}
```

**React Context 状态共享**：

```typescript
import { usePlugins } from '@/plugins';

function MyComponent() {
  const { plugins, refresh, enablePlugin, disablePlugin } = usePlugins();
  return <div>...</div>;
}

**发布订阅机制**：

```typescript
import { pluginRegistry } from '@/plugins';

// 订阅
pluginRegistry.subscribe(() => {
  console.log('插件状态变更，刷新界面');
});

// 插件注册/注销时会自动通知所有订阅者
```