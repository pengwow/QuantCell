# 插件实现模式示例

## 1. 后端插件实现模式

### 1.1 基础功能插件

**适用场景**：提供简单的API端点和基础功能

**实现示例**：

```python
from fastapi import APIRouter
from plugins.plugin_base import PluginBase

class BasicPlugin(PluginBase):
    """基础功能插件示例"""
    
    def __init__(self):
        super().__init__("basic-plugin", "1.0.0")
        self.router = APIRouter(prefix="/api/plugins/basic")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        @self.router.get("/")
        def basic_root():
            """基础插件根路由"""
            return {
                "message": "Hello from basic plugin!",
                "plugin_name": self.name,
                "version": self.version
            }
        
        @self.router.get("/health")
        def health_check():
            """健康检查路由"""
            return {"status": "healthy", "plugin": self.name}
    
    def register(self, plugin_manager):
        """注册插件"""
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")
    
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
    return BasicPlugin()
```

**manifest.json**：

```json
{
  "name": "basic-plugin",
  "version": "1.0.0",
  "description": "基础功能插件示例",
  "author": "QuantCell Team",
  "main": "plugin.py",
  "dependencies": []
}
```

### 1.2 服务提供插件

**适用场景**：提供可被其他插件使用的服务

**实现示例**：

```python
from plugins.plugin_base import PluginBase

class DataServicePlugin(PluginBase):
    """数据服务插件示例"""
    
    def __init__(self):
        super().__init__("data-service-plugin", "1.0.0")
        self.data_service = DataService()
    
    def register(self, plugin_manager):
        """注册插件"""
        super().register(plugin_manager)
        
        # 注册服务供其他插件使用
        if hasattr(plugin_manager, 'plugin_api'):
            plugin_manager.plugin_api.register_service("data_service", self.data_service)
            self.logger.info("数据服务注册成功")
        
        self.logger.info(f"{self.name} 插件注册成功")
    
    def start(self):
        """启动插件"""
        super().start()
        self.data_service.initialize()
        self.logger.info(f"{self.name} 插件启动成功")
    
    def stop(self):
        """停止插件"""
        super().stop()
        self.data_service.shutdown()
        self.logger.info(f"{self.name} 插件停止成功")

class DataService:
    """数据服务实现"""
    
    def __init__(self):
        self.data = {}
    
    def initialize(self):
        """初始化服务"""
        self.data = {"key1": "value1", "key2": "value2"}
    
    def shutdown(self):
        """关闭服务"""
        self.data = {}
    
    def get_data(self, key):
        """获取数据"""
        return self.data.get(key)
    
    def set_data(self, key, value):
        """设置数据"""
        self.data[key] = value
        return True
    
    def get_all_data(self):
        """获取所有数据"""
        return self.data

def register_plugin():
    """注册插件的入口函数"""
    return DataServicePlugin()
```

### 1.3 定时任务插件

**适用场景**：执行定时任务和后台处理

**实现示例**：

```python
import asyncio
from plugins.plugin_base import PluginBase

class ScheduledTaskPlugin(PluginBase):
    """定时任务插件示例"""
    
    def __init__(self):
        super().__init__("scheduled-task-plugin", "1.0.0")
        self.task = None
        self.running = False
    
    def register(self, plugin_manager):
        """注册插件"""
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")
    
    def start(self):
        """启动插件"""
        super().start()
        self.running = True
        self.task = asyncio.create_task(self._run_scheduled_tasks())
        self.logger.info(f"{self.name} 插件启动成功")
    
    def stop(self):
        """停止插件"""
        super().stop()
        self.running = False
        if self.task:
            self.task.cancel()
        self.logger.info(f"{self.name} 插件停止成功")
    
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

def register_plugin():
    """注册插件的入口函数"""
    return ScheduledTaskPlugin()
```

### 1.4 事件处理插件

**适用场景**：响应系统事件和其他插件事件

**实现示例**：

```python
from plugins.plugin_base import PluginBase

class EventHandlerPlugin(PluginBase):
    """事件处理插件示例"""
    
    def __init__(self):
        super().__init__("event-handler-plugin", "1.0.0")
    
    def register(self, plugin_manager):
        """注册插件"""
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功")
    
    def start(self):
        """启动插件"""
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")
        # 订阅事件
        self._subscribe_to_events()
    
    def stop(self):
        """停止插件"""
        super().stop()
        self.logger.info(f"{self.name} 插件停止成功")
    
    def _subscribe_to_events(self):
        """订阅事件"""
        # 这里可以实现事件订阅逻辑
        # 例如：self.plugin_manager.event_bus.subscribe("data_updated", self._handle_data_updated)
        self.logger.info("事件订阅完成")
    
    def _handle_data_updated(self, event_data):
        """处理数据更新事件"""
        self.logger.info(f"收到数据更新事件: {event_data}")
        # 处理事件逻辑

def register_plugin():
    """注册插件的入口函数"""
    return EventHandlerPlugin()
```

## 2. 前端插件实现模式

### 2.1 基础UI插件

**适用场景**：提供简单的UI页面和基础功能

**实现示例**：

```typescript
import React from 'react';
import { PluginBase } from '../PluginBase';

// 示例页面组件
const BasicPage: React.FC = () => {
  return (
    <div style={{ padding: '20px' }}>
      <h1>基础插件页面</h1>
      <p>这是一个基础前端插件示例页面</p>
      <div>
        <h2>插件功能</h2>
        <ul>
          <li>提供基础UI界面</li>
          <li>注册到系统菜单</li>
          <li>响应路由导航</li>
        </ul>
      </div>
    </div>
  );
};

export class BasicFrontendPlugin extends PluginBase {
  constructor() {
    super(
      'basic-frontend-plugin', 
      '1.0.0', 
      '基础前端插件示例', 
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
      group: '前端插件',
      items: [
        {
          path: '/plugins/basic',
          name: '基础插件页面',
          icon: undefined
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/basic',
      element: <BasicPage />
    });
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('基础前端插件启动成功');
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('基础前端插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): BasicFrontendPlugin {
  return new BasicFrontendPlugin();
}
```

**manifest.json**：

```json
{
  "name": "basic-frontend-plugin",
  "version": "1.0.0",
  "description": "基础前端插件示例",
  "author": "QuantCell Team",
  "main": "index.tsx",
  "dependencies": []
}
```

### 2.2 配置管理插件

**适用场景**：提供可配置的功能和设置界面

**实现示例**：

```typescript
import React from 'react';
import { PluginBase } from '../PluginBase';

// 配置页面组件
const ConfigPage: React.FC = () => {
  return (
    <div style={{ padding: '20px' }}>
      <h1>配置管理插件页面</h1>
      <p>这是一个配置管理插件示例页面</p>
      <div>
        <h2>配置项</h2>
        <p>插件注册的配置项会显示在系统设置中</p>
      </div>
    </div>
  );
};

export class ConfigPlugin extends PluginBase {
  constructor() {
    super(
      'config-plugin', 
      '1.0.0', 
      '配置管理插件示例', 
      'QuantCell Team'
    );
  }

  /**
   * 注册插件，添加菜单、路由和配置
   */
  public register(): void {
    super.register();
    
    // 添加菜单
    this.addMenu({
      group: '配置插件',
      items: [
        {
          path: '/plugins/config',
          name: '配置插件页面',
          icon: undefined
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/config',
      element: <ConfigPage />
    });
    
    // 添加系统配置项
    this.addSystemConfig({
      key: 'config_plugin_enabled',
      value: true,
      description: '启用配置管理插件',
      type: 'boolean'
    });
    
    this.addSystemConfig({
      key: 'config_plugin_mode',
      value: 'standard',
      description: '插件运行模式',
      type: 'select',
      options: ['standard', 'advanced', 'expert']
    });
    
    this.addSystemConfig({
      key: 'config_plugin_timeout',
      value: 30,
      description: '超时时间（秒）',
      type: 'number'
    });
    
    // 设置配置菜单名称
    this.setConfigMenuName('配置管理插件设置');
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    // 读取配置值
    const enabled = this.getConfig('config_plugin_enabled');
    const mode = this.getConfig('config_plugin_mode');
    const timeout = this.getConfig('config_plugin_timeout');
    
    console.log('配置管理插件启动成功');
    console.log('插件配置:', { enabled, mode, timeout });
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('配置管理插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): ConfigPlugin {
  return new ConfigPlugin();
}
```

### 2.3 数据可视化插件

**适用场景**：提供数据可视化界面和图表

**实现示例**：

```typescript
import React, { useState, useEffect } from 'react';
import { PluginBase } from '../PluginBase';

// 可视化页面组件
const VisualizationPage: React.FC = () => {
  const [data, setData] = useState<number[]>([]);

  useEffect(() => {
    // 生成模拟数据
    const generateData = () => {
      const newData = Array.from({ length: 10 }, () => Math.random() * 100);
      setData(newData);
    };

    generateData();
    const interval = setInterval(generateData, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: '20px' }}>
      <h1>数据可视化插件页面</h1>
      <p>这是一个数据可视化插件示例页面</p>
      
      <div style={{ marginTop: '20px' }}>
        <h2>数据图表</h2>
        <div style={{ 
          display: 'flex', 
          alignItems: 'end', 
          height: '300px', 
          gap: '10px',
          padding: '20px',
          border: '1px solid #ddd'
        }}>
          {data.map((value, index) => (
            <div 
              key={index}
              style={{
                width: '40px',
                height: `${value}%`,
                backgroundColor: '#4CAF50',
                borderRadius: '4px 4px 0 0',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'start',
                paddingTop: '10px',
                color: 'white',
                fontSize: '12px'
              }}
            >
              {Math.round(value)}
            </div>
          ))}
        </div>
        <p style={{ textAlign: 'center', marginTop: '10px', color: '#666' }}>
          模拟数据可视化 - 每5秒更新一次
        </p>
      </div>
    </div>
  );
};

export class VisualizationPlugin extends PluginBase {
  constructor() {
    super(
      'visualization-plugin', 
      '1.0.0', 
      '数据可视化插件示例', 
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
      group: '可视化插件',
      items: [
        {
          path: '/plugins/visualization',
          name: '数据可视化页面',
          icon: undefined
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/visualization',
      element: <VisualizationPage />
    });
    
    // 添加配置项
    this.addSystemConfig({
      key: 'visualization_refresh_interval',
      value: 5,
      description: '数据刷新间隔（秒）',
      type: 'number'
    });
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('数据可视化插件启动成功');
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('数据可视化插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): VisualizationPlugin {
  return new VisualizationPlugin();
}
```

### 2.4 交互功能插件

**适用场景**：提供复杂的用户交互和动态功能

**实现示例**：

```typescript
import React, { useState } from 'react';
import { PluginBase } from '../PluginBase';

// 交互页面组件
const InteractivePage: React.FC = () => {
  const [count, setCount] = useState(0);
  const [message, setMessage] = useState('');

  const handleIncrement = () => {
    setCount(count + 1);
  };

  const handleDecrement = () => {
    setCount(count - 1);
  };

  const handleMessageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMessage(e.target.value);
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>交互功能插件页面</h1>
      <p>这是一个交互功能插件示例页面</p>
      
      <div style={{ marginTop: '20px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px' }}>
        <h2>计数器</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <button 
            onClick={handleDecrement}
            style={{
              padding: '10px 20px',
              fontSize: '16px',
              backgroundColor: '#f44336',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            -
          </button>
          <div style={{ fontSize: '24px', minWidth: '60px', textAlign: 'center' }}>
            {count}
          </div>
          <button 
            onClick={handleIncrement}
            style={{
              padding: '10px 20px',
              fontSize: '16px',
              backgroundColor: '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            +
          </button>
        </div>
        
        <h2>消息输入</h2>
        <div style={{ marginBottom: '20px' }}>
          <input 
            type="text"
            value={message}
            onChange={handleMessageChange}
            placeholder="输入消息..."
            style={{
              padding: '10px',
              fontSize: '16px',
              width: '300px',
              border: '1px solid #ddd',
              borderRadius: '4px'
            }}
          />
        </div>
        
        {message && (
          <div style={{ 
            padding: '15px', 
            backgroundColor: '#e3f2fd', 
            borderRadius: '4px',
            borderLeft: '4px solid #2196F3'
          }}>
            <h3>输入的消息：</h3>
            <p>{message}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export class InteractivePlugin extends PluginBase {
  constructor() {
    super(
      'interactive-plugin', 
      '1.0.0', 
      '交互功能插件示例', 
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
      group: '交互插件',
      items: [
        {
          path: '/plugins/interactive',
          name: '交互功能页面',
          icon: undefined
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/interactive',
      element: <InteractivePage />
    });
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('交互功能插件启动成功');
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('交互功能插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): InteractivePlugin {
  return new InteractivePlugin();
}
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
3. **实现插件类**：继承 `PluginBase` 并实现核心方法
4. **创建组件**：实现插件所需的 React 组件
5. **注册菜单和路由**：在 `register` 方法中注册
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

后端插件通过 `register_plugin` 函数注册，插件管理器会自动发现并加载插件：

```python
def register_plugin() -> PluginBase:
    """注册插件的入口函数"""
    return ExamplePlugin()
```

### 7.2 前端插件注册

前端插件通过 `registerPlugin` 函数注册，插件管理器会自动发现并加载插件：

```typescript
export function registerPlugin(): ExamplePlugin {
  return new ExamplePlugin();
}
```

## 8. 插件生命周期管理

### 8.1 后端插件生命周期

1. **加载**：插件管理器扫描并加载插件
2. **注册**：调用 `register` 方法
3. **启动**：调用 `start` 方法
4. **运行**：插件处理请求和事件
5. **停止**：调用 `stop` 方法

### 8.2 前端插件生命周期

1. **加载**：插件管理器动态导入插件模块
2. **注册**：调用 `register` 方法
3. **启动**：调用 `start` 方法
4. **运行**：插件渲染UI和处理用户交互
5. **停止**：调用 `stop` 方法
6. **卸载**：从插件管理器中移除

## 9. 插件通信示例

### 9.1 后端插件间通信

**服务调用**：

```python
# 在插件A中注册服务
if hasattr(self.plugin_manager, 'plugin_api'):
    self.plugin_manager.plugin_api.register_service("my_service", MyService())

# 在插件B中使用服务
if hasattr(self.plugin_manager, 'plugin_api'):
    my_service = self.plugin_manager.plugin_api.get_service("my_service")
    if my_service:
        result = my_service.do_something()
```

### 9.2 前端插件间通信

**插件实例访问**：

```typescript
// 在插件中访问其他插件
import { pluginManager } from '../PluginManager';

// 获取指定插件
const otherPlugin = pluginManager.getPlugin('other-plugin');
if (otherPlugin) {
  // 调用插件方法或访问属性
  console.log('其他插件版本:', otherPlugin.instance.version);
}
```

**全局状态管理**：

```typescript
// 使用全局状态管理
import { useDispatch, useSelector } from 'react-redux';

// 分发动作
dispatch({ type: 'PLUGIN_ACTION', payload: data });

// 选择状态
const state = useSelector((state) => state.pluginState);
```