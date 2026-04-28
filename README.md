# QuantCell - 量化交易系统

demo地址:[https://demo.quantcell.top/](https://demo.quantcell.top/chart)

## 项目简介

QuantCell 是一个功能完整的量化交易系统，集成了策略开发、回测、实盘交易和 AI 辅助功能。系统采用前后端分离架构，后端基于 FastAPI 构建，前端使用 React + TypeScript 开发。

### 核心功能

- **策略开发与管理**：提供策略基类和多种执行引擎，支持事件驱动和向量式回测
- **高性能回测**：基于 nautilus\_trader 框架的事件驱动回测引擎
- **实时数据处理**：支持实时市场数据订阅和处理
- **交易所连接**：支持 Binance、OKX 等交易所的接口
- **AI 辅助功能**：集成 AI 模型，支持策略生成和优化
- **完整的前端界面**：提供策略管理、回测分析、实时监控等功能

## 技术栈

| 类别   | 技术/框架              | 用途     |
| ---- | ------------------ | ------ |
| 后端   | Python 3.10+       | 核心业务逻辑 |
| 后端框架 | FastAPI            | API 服务 |
| 数据库  | SQLite/PostgreSQL  | 数据存储   |
| 前端   | React 18+          | 用户界面   |
| 前端语言 | TypeScript         | 类型安全   |
| 前端框架 | Ant Design         | UI 组件库 |
| 包管理  | uv (后端) / bun (前端) | 依赖管理   |
| 回测引擎 | nautilus\_trader   | 高性能回测  |

## 系统要求

### 后端

- Python 3.10 或更高版本
- uv 包管理器
- 足够的存储空间用于数据存储

### 前端

- Node.js 16 或更高版本
- bun 包管理器

## 安装与部署

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/quantcell.git
cd quantcell
```

### 2. 后端安装

```bash
cd backend
# 安装依赖
uv sync
# 初始化数据库
python init_db.py
```

### 3. 前端安装

```bash
cd frontend
# 安装依赖
bun install
```

## 快速开始

### 启动后端服务

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 启动前端开发服务器

```bash
cd frontend
bun run dev
```

### 构建前端生产版本

```bash
cd frontend
bun run build
```

## 项目结构

```
QuantCell/
├── backend/              # 后端代码
│   ├── agent/            # 智能代理模块
│   ├── ai_model/         # AI 模型相关功能
│   ├── backtest/         # 回测系统
│   ├── collector/        # 数据采集模块
│   ├── common/           # 通用组件
│   ├── core/             # 核心功能
│   ├── exchange/         # 交易所接口
│   ├── factor/           # 因子分析
│   ├── indicators/       # 技术指标
│   ├── realtime/         # 实时数据处理
│   ├── strategy/         # 策略系统
│   ├── tests/            # 测试代码
│   ├── utils/            # 工具函数
│   ├── main.py           # 应用入口
│   └── pyproject.toml    # 项目配置
├── frontend/             # 前端代码
│   ├── public/           # 静态资源
│   ├── src/              # 源代码
│   │   ├── api/          # API 调用
│   │   ├── components/   # 组件
│   │   ├── pages/        # 页面
│   │   ├── router/       # 路由
│   │   ├── services/     # 服务
│   │   └── store/        # 状态管理
│   ├── package.json      # 前端依赖
│   └── vite.config.ts    # Vite 配置
├── CODE_WIKI.md          # 代码文档
└── README.md             # 项目说明
```

## 核心模块

### 策略系统

策略系统是 QuantCell 的核心功能，提供了策略开发、执行和管理的完整框架。策略基类 `StrategyBase` 定义了策略的基本接口和生命周期方法，所有策略都需要继承此类并实现相应的方法。

**主要文件**：[strategy/core/strategy.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/strategy/core/strategy.py)

### 回测系统

回测系统提供了高性能的策略回测功能，支持多种回测引擎和结果分析。基于 nautilus\_trader 的事件驱动回测引擎，支持多品种、多策略回测。

**主要文件**：[backtest/engines/engine.py](file:///Users/liupeng/workspace/quant/QuantCell/backend/backtest/engines/engine.py)

### 实时数据处理

实时数据处理模块负责从交易所获取实时市场数据，并分发给策略和前端。支持 WebSocket 连接管理、实时 K 线数据处理和数据分发。

### 交易所接口

交易所接口模块提供了与不同交易所的连接和交互功能，支持 Binance、OKX 等交易所的接口。

### AI 辅助功能

AI 辅助功能模块集成了 AI 模型，用于策略生成、优化和分析，提供智能的策略生成和技术分析能力。

## 前端界面

前端系统使用 React + TypeScript 构建，提供了直观的用户界面，用于策略管理、回测分析和系统监控。主要功能包括：

- 策略管理：创建、编辑、测试策略
- 回测分析：配置回测参数，查看回测结果
- 数据管理：管理市场数据和历史数据
- 实时监控：监控策略运行状态和市场数据
- 系统设置：配置系统参数和交易所连接

## API 文档

后端服务启动后，可以通过以下地址访问 API 文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 开发指南

### 策略开发

1. **创建策略类**：继承 `StrategyBase` 类
2. **实现核心方法**：`on_start()`, `on_bar()`, `on_stop()`
3. **配置策略参数**：定义 `StrategyConfig` 子类
4. **测试策略**：使用回测引擎测试策略性能

### 回测配置

```python
backtest_config = {
    "initial_capital": 100000.0,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "symbols": ["BTCUSDT"],
    "catalog_path": "/path/to/data",
    "strategy_config": {
        "strategy_path": "my_strategy:MyStrategy",
        "params": {
            "fast_period": 10,
            "slow_period": 20
        }
    }
}
```

### 前端开发

1. **页面开发**：在 `src/pages` 目录创建新页面
2. **组件开发**：在 `src/components` 目录创建可复用组件
3. **API 调用**：使用 `src/api` 中的 API 函数
4. **状态管理**：使用 store 管理全局状态

## 系统监控与维护

### 日志系统

系统使用统一的日志系统，所有日志通过 `utils/logger.py` 中的日志器记录。支持 DEBUG、INFO、WARNING、ERROR、CRITICAL 等日志级别。

### 系统健康检查

- `GET /health`：检查系统健康状态
- `GET /system/info`：获取系统信息
- `GET /system/logs`：查看系统日志

### 常见问题排查

1. **回测失败**：检查数据目录是否正确，策略代码是否有语法错误
2. **实时数据连接失败**：检查网络连接，验证交易所 API 密钥
3. **策略执行异常**：查看策略日志，检查策略逻辑
4. **前端加载缓慢**：检查网络连接，清除浏览器缓存

## 贡献指南

1. **Fork 项目**：在 GitHub 上 Fork 项目到自己的账号
2. **创建分支**：创建一个新的分支用于开发
3. **提交更改**：提交代码更改并添加详细的 commit 信息
4. **创建 Pull Request**：提交 Pull Request 到主分支
5. **代码审查**：等待代码审查和合并

## 许可证

本项目采用 Apache License 2.0 许可证。详见 [LICENSE](LICENSE) 文件。

## 联系方式

- 项目维护者：QuantCell Team
- 邮箱：<pengwow@hotmail.com>
- 网站：[https://quantcell.top](https://quantcell.io)

***

**QuantCell** - 让量化交易更简单、更智能！
