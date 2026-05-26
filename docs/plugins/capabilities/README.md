# 插件能力文档

## 1. 概述

本文档提供了 QuantCell 项目插件系统的详细能力规范，旨在帮助 AI 系统理解和开发兼容的前端和后端插件。插件系统允许开发者扩展 QuantCell 的功能，而无需修改核心代码。

## 2. 插件系统架构

### 2.1 后端插件架构
- **基于 Python 和 FastAPI**
- **插件基类**：`PluginBase` 提供核心生命周期方法（`on_enable`/`on_disable`/`get_frontend_assets`/`get_config_schema`/`get_metadata`）
- **插件管理器**：`PluginManager` 负责扫描、加载和管理插件，支持热加载（HotPluginLoader）和重启加载（RestartPluginLoader）
- **事件总线**：`EventBus` 提供线程安全的发布/订阅事件系统，支持 `subscribe`/`unsubscribe`/`publish`/`publish_async`，使用 `threading.Lock` 确保线程安全
- **插件存储**：`PluginStore` 基于 SQLAlchemy ORM 的持久化存储，支持 `save_plugin`/`get_plugin`/`get_all_plugins`/`update_status`/`delete_plugin`
- **安全机制**：`PluginSecurity` 提供权限枚举（`PluginPermission`）、权限校验（`validate_permissions`）、路由冲突检测（`check_system_route_conflict`）和沙箱执行（`PluginSandbox`）
- **安装器**：`PluginInstaller` 支持从 ZIP 文件（`install_from_zip`）、字节数据（`install_from_zip_bytes`）和 Git 仓库（`install_from_git`）安装插件
- **插件 API**：`PluginAPI` 提供插件间通信和服务访问

### 2.2 前端插件架构
- **基于 React 和 TypeScript**
- **全局状态管理**：`PluginContext` 提供 `PluginProvider` 组件和 `usePlugins()` Hook，管理插件列表和状态
- **单例注册中心**：`PluginRegistry` 负责插件、菜单和路由的注册与管理
- **动态资源加载**：`PluginLoader` 支持动态加载插件的 CSS 和 JavaScript 资源
- **API 客户端**：`pluginApi` 封装所有插件相关 API 调用（`getPlugins`/`getPlugin`/`installFromZip`/`installFromGit`/`uninstallPlugin`/`enablePlugin`/`disablePlugin`/`getPluginConfig`）
- **SSE 事件监听**：`listenPluginEvents` 实时监听插件状态变化事件
- **插件管理 UI**：提供完整的插件管理界面（安装、卸载、启用、禁用、查看详情）

## 3. 文档结构

- **README.md**：插件能力总览
- **backend-capabilities.md**：后端插件能力详细规范
- **frontend-capabilities.md**：前端插件能力详细规范
- **plugin-examples.md**：插件实现模式示例
- **plugin-testing.md**：插件测试方法和兼容性验证指南

## 4. 插件开发流程

1. **创建插件目录结构**
2. **编写插件清单文件**（manifest.json）
3. **实现插件核心逻辑**
4. **注册插件服务和路由**
5. **测试插件功能**
6. **部署和集成**

## 5. 兼容性要求

- **后端插件**：
  - 必须继承 `PluginBase` 类
  - 必须提供 `register_plugin` 函数作为插件入口
  - 必须包含 `manifest.json` 清单文件
  - 必须设置 `load_type` 属性为 `LoadType.HOT`（热加载）或 `LoadType.RESTART`（重启加载）
  - 必须实现 `on_enable` 和 `on_disable` 生命周期方法
  - 必须声明所需权限（`permissions`）
  - 路由前缀不得与系统核心路由冲突

- **前端插件**：
  - 必须提供 `manifest.json` 清单文件
  - 必须包含 `frontend_entry` 指向前端入口文件
  - 前端资源必须包含 `index.js` 和可选的 `index.css`
  - 通过 `PluginRegistry` 注册菜单和路由
  - 使用 `usePlugins()` Hook 获取插件状态

- **清单文件**：
  - 必须包含 `name`（插件名称，唯一标识符）
  - 必须包含 `version`（遵循语义化版本 X.Y.Z）
  - 必须包含 `description`（插件描述）
  - 可选包含 `author`、`load_type`、`permissions`、`config_schema`、`frontend_entry`

- **API 兼容性**：必须遵循文档中定义的 API 规范

## 6. 安全注意事项

- **权限控制**：插件必须声明所需权限（`PluginPermission` 枚举，包括 `database:read/write`、`api:internal`、`filesystem:read/write`、`network:outbound`），系统会通过 `validate_permissions` 进行权限校验
- **路由冲突检测**：插件路由前缀不得与系统核心路由（`/api/config`、`/api/system`、`/api/auth` 等）冲突，系统通过 `check_system_route_conflict` 进行检测
- **沙箱执行**：插件代码在 `PluginSandbox` 中执行，异常不会影响系统稳定性
- **输入验证**：所有用户输入必须经过验证
- **错误处理**：不应向用户暴露敏感错误信息
- **依赖管理**：应明确声明插件依赖

## 7. 性能优化

- **热加载机制**：`LoadType.HOT` 类型插件支持运行时加载/卸载，无需重启系统
- **延迟加载**：插件应在需要时才加载资源
- **缓存策略**：合理使用缓存减少重复计算
- **资源管理**：及时释放不再使用的资源
- **事件总线优化**：`EventBus` 使用 `threading.Lock` 确保线程安全，支持异步事件发布（`publish_async`）

## 8. 支持和反馈

如有任何问题或建议，请通过项目的 GitHub Issues 或其他指定渠道提供反馈。