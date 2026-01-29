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
{plugin-name}-{version}-{type}.tar.gz
```

**示例**：
- `example-plugin-1.0.0-backend.tar.gz`
- `demo-plugin-1.0.0-frontend.tar.gz`

## 3. 插件安装

### 3.1 安装脚本

**文件路径**：`/Users/liupeng/workspace/quantcell/plugin_installer.py`

**功能**：解压 tar.gz 文件并安装到对应插件目录

### 3.2 使用方法

```bash
# 基本语法
python plugin_installer.py <package_path>

# 示例：安装后端插件
python plugin_installer.py example-plugin-1.0.0-backend.tar.gz

# 示例：安装前端插件
python plugin_installer.py demo-plugin-1.0.0-frontend.tar.gz
```

### 3.3 安装流程

1. 验证包文件完整性
2. 检测插件类型
3. 创建临时目录
4. 解压 tar.gz 文件
5. 验证插件结构
6. 安装到对应插件目录
7. 清理临时文件
8. 输出安装结果和后续操作建议

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

## 10. 更新日志

- **v1.0.0**：初始版本，支持基本的打包、安装和服务管理功能

## 11. 联系方式

如有问题或建议，请联系 QuantCell 开发团队。