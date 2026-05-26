# QuantCell 插件管理指南

## 1. 概述

本指南介绍 QuantCell 插件系统的打包、安装和服务管理机制，帮助开发者和管理员快速上手插件管理。

## 2. 插件打包

### 2.1 打包脚本

**文件路径**：`/Users/liupeng/workspace/quantcell/plugin_packer.py`

**功能**：将指定插件目录打包成标准化的 tar.gz 文件

### 2.2 支持的插件类型

- **后端插件**：Python 插件，位于 `backend/plugins/` 目录
- **前端插件**：TypeScript/React 插件，位于 `frontend/src/plugins/` 目录

### 2.3 使用方法

```bash
# 基本语法
python plugin_packer.py <plugin_directory>

# 示例：打包后端插件
python plugin_packer.py backend/plugins/example_plugin

# 示例：打包前端插件  
python plugin_packer.py frontend/src/plugins/demo-plugin
```

### 2.4 打包流程

1. 验证插件目录结构完整性
2. 读取插件 `manifest.json` 文件
3. 检测插件类型（前端/后端）
4. 生成标准化包文件名
5. 打包插件目录内容
6. 验证打包结果

### 2.5 包文件命名规范

```
{plugin-name}-{version}.zip
```

**示例**：
- `example-plugin-1.0.0.zip`
- `demo-plugin-1.0.0.zip`

> **格式说明**：从 v2.0 开始，插件打包格式已从 tar.gz 更新为 ZIP 格式。新格式通过 `PluginInstaller.install_from_zip` 方法安装，提供了更好的跨平台兼容性和更便捷的前端上传支持。

## 3. 插件安装

### 3.1 安装脚本

**文件路径**：`backend/plugins/plugin_installer.py`

**功能**：支持 ZIP 文件上传和 Git URL 两种安装方式

### 3.2 ZIP 文件上传安装

#### 通过前端 UI 安装

1. 进入 **设置 → 插件管理 → 安装插件**
2. 选择 **ZIP 上传** 标签页
3. 点击或拖拽 ZIP 文件到上传区域
4. 等待安装完成

#### 通过 REST API 安装

```bash
# 使用 curl 上传 ZIP 文件
curl -X POST "http://localhost:8000/api/plugins/install/upload" \
  -H "Authorization: Bearer <your_token>" \
  -F "file=@my-plugin-1.0.0.zip"
```

**安装流程**：
1. 后端接收 ZIP 文件并保存到临时目录
2. 自动解压 ZIP 文件
3. 查找并校验 `manifest.json` 文件
4. 验证插件名称、版本号、权限等信息
5. 移动到插件目录（`backend/plugins/`）
6. 调用 `PluginManager.install_plugin()` 完成注册
7. 清理临时文件

### 3.3 Git URL 安装

#### 通过前端 UI 安装

1. 进入 **设置 → 插件管理 → 安装插件**
2. 选择 **Git URL** 标签页
3. 输入 Git 仓库地址（支持 HTTPS）
4. 可选：指定分支名称
5. 点击 **安装** 按钮

#### 通过 REST API 安装

```bash
# 安装默认分支
curl -X POST "http://localhost:8000/api/plugins/install/git" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/plugin.git"}'

# 指定分支安装
curl -X POST "http://localhost:8000/api/plugins/install/git" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/plugin.git", "branch": "develop"}'
```

**安装流程**：
1. 执行 `git clone --depth 1` 浅克隆仓库（可选指定分支）
2. 查找并校验 `manifest.json` 文件
3. 验证插件信息
4. 移动到插件目录
5. 调用 `PluginManager.install_plugin()` 完成注册
6. 清理临时目录

> **注意**：Git 克隆超时时间为 120 秒，请确保网络连接正常。

### 3.4 安装注意事项

- 安装前会检查目标目录是否已存在，存在则覆盖
- 安装后会给出服务重启建议
- 前端开发模式支持热加载，生产模式需要重新构建

## 4. 服务管理

### 4.1 服务管理脚本

**文件路径**：`/Users/liupeng/workspace/quantcell/service_manager.py`

**功能**：管理前后端服务的启动、停止和重启

### 4.2 支持的服务

- **backend**：FastAPI 后端服务
- **frontend**：Vite 前端开发服务
- **all**：同时管理前后端服务

### 4.3 使用方法

```bash
# 基本语法
python service_manager.py <command> <service>

# 命令列表
# start：启动服务
# stop：停止服务  
# restart：重启服务

# 示例：重启后端服务
python service_manager.py restart backend

# 示例：重启前端服务
python service_manager.py restart frontend

# 示例：重启所有服务
python service_manager.py restart all
```

### 4.4 服务管理流程

1. 获取服务进程 ID
2. 根据命令执行相应操作
   - **start**：启动服务
   - **stop**：停止服务
   - **restart**：先停止再启动服务
3. 输出操作结果

## 5. 热加载支持

### 5.1 前端插件热加载

- **开发模式**：支持热加载，安装后自动生效
- **生产模式**：需要重新构建才能生效

```bash
# 开发模式下自动热加载
# 生产模式需要重新构建
bun run build
```

### 5.2 后端插件热加载

- **不支持热加载**：安装后需要重启后端服务才能生效

```bash
# 重启后端服务
python service_manager.py restart backend
```

## 6. 完整工作流示例

### 6.1 开发并打包插件

```bash
# 1. 开发插件（在对应目录下）

# 2. 打包后端插件
python plugin_packer.py backend/plugins/my-new-plugin

# 3. 打包前端插件
python plugin_packer.py frontend/src/plugins/my-new-plugin
```

### 6.2 安装并部署插件

```bash
# 1. 安装后端插件
python plugin_installer.py my-new-plugin-1.0.0-backend.tar.gz

# 2. 安装前端插件
python plugin_installer.py my-new-plugin-1.0.0-frontend.tar.gz

# 3. 重启后端服务
python service_manager.py restart backend

# 4. （可选）重启前端服务（如果需要）
python service_manager.py restart frontend
```

## 7. 常见问题

### 7.1 打包失败

**问题**：`插件目录缺少 manifest.json 文件`
**解决**：确保插件目录包含 `manifest.json` 文件，且包含必要字段

**问题**：`无法确定插件类型`
**解决**：确保插件目录结构符合规范，后端插件包含 `plugin.py`，前端插件包含 `index.tsx`

### 7.2 安装失败

**问题**：`插件包必须是 tar.gz 格式`
**解决**：确保使用正确的包文件格式

**问题**：`插件包结构错误`
**解决**：使用官方打包脚本生成的包文件，不要手动修改

### 7.3 服务管理问题

**问题**：`获取后端进程ID失败`
**解决**：确保服务正在运行，或手动查找并停止进程

**问题**：`停止进程失败`
**解决**：尝试手动停止进程，或使用 `kill -9 <pid>` 强制终止

## 8. 最佳实践

1. **使用标准化打包脚本**：始终使用 `plugin_packer.py` 生成插件包
2. **测试插件完整性**：打包前验证插件功能正常
3. **定期备份**：安装前备份现有插件目录
4. **版本管理**：使用语义化版本号，避免版本冲突
5. **遵循命名规范**：插件名称使用小写字母和连字符

## 9. 注意事项

- 打包和安装操作需要管理员权限
- 服务重启会导致短暂的服务不可用
- 前端生产模式需要重新构建才能加载新插件
- 后端插件安装后必须重启服务才能生效

## 10. 前端插件管理 UI

### 10.1 访问路径

```
/setting/plugins
```

### 10.2 功能概览

前端插件管理 UI 提供了完整的插件生命周期管理能力：

#### 插件列表

- **卡片视图**：每个插件显示为独立卡片
- **显示信息**：名称、版本、描述、状态、加载方式
- **状态标识**：
  - `installed`（已安装）：插件已安装但未启动
  - `enabled`（运行中）：插件正在运行
  - `disabled`（已停止）：插件已停止
  - `pending_restart`（待重启）：插件需要重启后生效
  - `error`（错误）：插件加载或运行出错

#### 安装插件

支持两种安装方式，通过 Tabs 标签页切换：

1. **ZIP 上传**：拖拽或点击上传 ZIP 文件
2. **Git URL**：输入 Git 仓库地址和可选分支

#### 启停控制

- 使用 Switch 开关控制插件启用/禁用
- `pending_restart` 和 `error` 状态的插件无法启停控制

#### 卸载插件

- 点击卡片上的删除图标
- 弹出 Popconfirm 确认对话框
- 确认后自动卸载并刷新列表

#### 详情查看

- 点击卡片上的信息图标
- 显示完整插件信息（Descriptions 组件）
- 包含：名称、版本、作者、状态、加载方式、安装来源、描述、权限、安装时间
- 如有错误信息会显示 Alert 提示
- 如有配置 Schema 会显示 JSON 预览

### 10.3 实时更新

插件管理 UI 支持 SSE（Server-Sent Events）实时更新：

- 监听事件：`plugin_loaded`、`plugin_unloaded`、`plugin_installed`、`plugin_uninstalled`、`plugin_error`
- 当插件状态变更时自动刷新列表
- 无需手动刷新页面

## 11. REST API 管理

### 11.1 API 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/plugins/` | 获取所有插件列表 |
| GET | `/api/plugins/events` | SSE 事件流（实时状态更新） |
| GET | `/api/plugins/{name}` | 获取指定插件详情 |
| POST | `/api/plugins/install/upload` | ZIP 文件上传安装 |
| POST | `/api/plugins/install/git` | Git 仓库安装 |
| DELETE | `/api/plugins/{name}` | 卸载指定插件 |
| POST | `/api/plugins/{name}/enable` | 启用插件 |
| POST | `/api/plugins/{name}/disable` | 禁用插件 |
| GET | `/api/plugins/{name}/assets/{path}` | 获取插件前端静态资源 |
| GET | `/api/plugins/{name}/config` | 获取插件配置 Schema |

### 11.2 通用响应格式

所有 API 返回统一的 `ApiResponse` 格式：

```json
{
  "code": 0,
  "message": "操作成功",
  "data": { ... }
}
```

错误响应：

```json
{
  "code": 500,
  "message": "错误信息",
  "data": null
}
```

### 11.3 API 使用示例

#### 获取插件列表

```bash
curl -X GET "http://localhost:8000/api/plugins/" \
  -H "Authorization: Bearer <your_token>"
```

响应示例：

```json
{
  "code": 0,
  "message": "获取插件列表成功",
  "data": {
    "plugins": [
      {
        "name": "my-plugin",
        "version": "1.0.0",
        "description": "示例插件",
        "author": "Developer",
        "load_type": "hot",
        "status": "enabled",
        "install_source": "zip",
        "install_path": "/path/to/plugins/my-plugin",
        "permissions": ["database.read"],
        "config_schema": null,
        "frontend_entry": null,
        "installed_at": "2025-01-15T10:30:00",
        "updated_at": "2025-01-15T10:30:00",
        "error_message": null
      }
    ]
  }
}
```

#### 启用/禁用插件

```bash
# 启用插件
curl -X POST "http://localhost:8000/api/plugins/my-plugin/enable" \
  -H "Authorization: Bearer <your_token>"

# 禁用插件
curl -X POST "http://localhost:8000/api/plugins/my-plugin/disable" \
  -H "Authorization: Bearer <your_token>"
```

#### 获取插件配置 Schema

```bash
curl -X GET "http://localhost:8000/api/plugins/my-plugin/config" \
  -H "Authorization: Bearer <your_token>"
```

#### SSE 事件监听

```javascript
// 前端代码示例
const token = getAccessToken();
const url = `/api/plugins/events?token=${encodeURIComponent(token)}`;
const eventSource = new EventSource(url);

eventSource.addEventListener('plugin_loaded', (e) => {
  const data = JSON.parse(e.data);
  console.log('插件已加载:', data.name);
});

eventSource.addEventListener('plugin_error', (e) => {
  const data = JSON.parse(e.data);
  console.error('插件错误:', data.name, data.error);
});
```

### 11.4 权限说明

- 所有 API 端点都需要有效的 JWT Token
- Token 可通过 Header 或 Query 参数传递
- SSE 事件流使用 Query 参数传递 Token

## 12. 插件独立开发服务器

### 12.1 工具介绍

**文件路径**：`backend/plugins/plugin_dev.py`

插件独立开发服务器是一个轻量级的 FastAPI 应用，用于在开发阶段独立测试插件功能，无需启动完整的 QuantCell 后端服务。

### 12.2 启动命令

```bash
cd backend

# 基本启动
python plugins/plugin_dev.py run --plugin-dir ./plugins/my-plugin --port 9000

# 启用文件监控自动重载
python plugins/plugin_dev.py run --plugin-dir ./plugins/my-plugin --port 9000 --reload

# 指定监听地址
python plugins/plugin_dev.py run --plugin-dir ./plugins/my-plugin --port 9000 --host 0.0.0.0
```

### 12.3 命令参数

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--plugin-dir` | 字符串 | 必填 | 插件目录路径 |
| `--port` | 整数 | 9000 | 监听端口 |
| `--host` | 字符串 | localhost | 监听地址 |
| `--reload` | 布尔 | false | 是否启用文件监控自动重载 |

### 12.4 开发端点

开发服务器提供以下调试端点：

| 端点 | 方法 | 描述 |
|------|------|------|
| `/dev/health` | GET | 健康检查，返回插件状态信息 |
| `/dev/reload` | POST | 手动触发插件重载 |

#### 健康检查

```bash
curl http://localhost:9000/dev/health
```

响应示例：

```json
{
  "status": "running",
  "plugin_dir": "./plugins/my-plugin",
  "plugin": {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "示例插件"
  },
  "reload_enabled": true
}
```

#### 手动重载

```bash
curl -X POST http://localhost:9000/dev/reload
```

### 12.5 自动重载机制

当启用 `--reload` 参数时，开发服务器会：

1. 监控 `manifest.json` 文件的修改时间
2. 监控入口文件（如 `plugin.py`）的修改时间
3. 检测到变更后自动调用重载逻辑
4. 重载过程包括：停止当前插件 → 清理路由 → 重新加载插件

### 12.6 CORS 配置

开发服务器默认启用 CORS，允许所有来源访问：

```python
allow_origins=["*"]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

### 12.7 使用场景

1. **插件开发**：快速迭代测试插件功能
2. **接口调试**：独立测试插件 API 端点
3. **前端集成**：配合前端开发服务器调试插件 UI
4. **演示展示**：独立展示插件功能

## 13. 更新日志

- **v2.0.0**：
  - 插件打包格式从 tar.gz 更新为 ZIP
  - 新增 ZIP 文件上传安装方式
  - 新增 Git URL 安装方式
  - 新增前端插件管理 UI
  - 新增 REST API 管理端点
  - 新增 SSE 实时状态更新
  - 新增插件独立开发服务器
- **v1.0.0**：初始版本，支持基本的打包、安装和服务管理功能

## 14. 联系方式

如有问题或建议，请联系 QuantCell 开发团队。