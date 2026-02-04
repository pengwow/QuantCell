# 策略回测模块详细设计文档

## 1. 系统架构概述

### 1.1 系统架构图

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                  前端层 (React + TypeScript)                      │
├─────────────────────────────┬─────────────────────────────┬─────────────────────────┤
│  回测任务配置页面           │  回测结果展示页面           │  回测回放页面           │
│  - 策略选择与上传           │  - 关键指标展示             │  - K线图表回放          │
│  - 参数配置                 │  - 绩效分析图表             │  - 交易信号标注         │
│  - 回测执行控制             │  - 交易详情表格             │  - 播放控制 (播放/暂停/倍速) │
│  - 任务状态监控             │  - 风险分析图表             │  - 进度调整             │
└─────────────┬───────────────┴───────────────┬─────────────┴─────────────────────┘
              │                               │
┌─────────────▼───────────────────────────────▼───────────────────────────────────┐
│                                  API层 (FastAPI)                                │
├─────────────────────────────┬─────────────────────────────┬─────────────────────────┤
│  回测任务管理API           │  策略管理API                │  回放数据API            │
│  - 创建/查询/删除任务       │  - 策略上传/列表/加载        │  - 获取回放数据         │
│  - 执行/停止任务           │  - 策略参数配置             │  - 回放控制             │
└─────────────┬───────────────┴───────────────┬─────────────┴─────────────────────┘
              │                               │
┌─────────────▼───────────────────────────────▼───────────────────────────────────┐
│                                  业务逻辑层 (Python)                            │
├─────────────────────────────┬─────────────────────────────┬─────────────────────────┤
│  回测服务 (BacktestService) │  策略管理服务               │  回放数据生成服务       │
│  - 回测执行                 │  - 策略动态加载             │  - 回放数据预处理       │
│  - 结果处理与翻译           │  - 策略参数验证             │  - 回放数据格式化       │
│  - 任务状态管理             │  - 策略文件管理             │  - 回放进度计算         │
└─────────────┬───────────────┴───────────────┬─────────────┴─────────────────────┘
              │                               │
┌─────────────▼───────────────────────────────▼───────────────────────────────────┐
│                                  数据层                                          │
├─────────────────────────────┬─────────────────────────────┬─────────────────────────┤
│  回测任务数据库             │  策略文件存储               │  回测结果存储           │
│  - 任务配置                 │  - 策略脚本文件             │  - 结果指标             │
│  - 任务状态                 │  - 策略元数据               │  - 交易记录             │
│  - 回测统计信息             │                           │  - 资金曲线数据         │
│                           │                           │  - K线数据             │
└─────────────────────────────┴─────────────────────────────┴─────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────────────────────┐
│                                  外部依赖层                                      │
├─────────────────────────────┬─────────────────────────────┬─────────────────────────┤
│  backtesting.py             │  数据服务                   │  klinecharts            │
│  - 核心回测引擎             │  - K线数据获取              │  - K线图表渲染          │
│  - 策略执行框架             │  - 历史数据存储              │  - 标记点/线绘制        │
└─────────────────────────────┴─────────────────────────────┴─────────────────────────┘
```

### 1.2 核心技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 前端 | React | 18+ | UI框架 |
| 前端 | TypeScript | 5+ | 类型安全 |
| 前端 | klinecharts | 10.0.0-beta1 | K线图表渲染 |
| 前端 | echarts | 5+ | 绩效分析图表 |
| 后端 | FastAPI | 0.100+ | API框架 |
| 后端 | Python | 3.10+ | 后端开发 |
| 后端 | backtesting.py | 0.3.3+ | 回测引擎 |
| 后端 | SQLAlchemy | 2.0+ | ORM框架 |
| 数据库 | SQLite | 3+ | 数据存储 |

## 2. 核心模块设计

### 2.1 回测任务管理模块

**功能描述**：负责回测任务的创建、配置、执行与监控。

**核心组件**：

| 组件 | 职责 | 实现类/函数 |
|------|------|-------------|
| 任务管理器 | 处理任务生命周期 | `BacktestService` |
| 策略加载器 | 动态加载策略脚本 | `BacktestService.load_strategy_from_file` |
| 回测执行器 | 执行回测逻辑 | `BacktestService.run_backtest` |
| 结果处理器 | 处理回测结果 | `BacktestService.translate_backtest_results` |
| 任务状态监控 | 监控回测执行状态 | 任务状态字段 + 定时刷新 |

**关键数据结构**：

```python
# 回测任务模型
class BacktestTask:
    id: str  # 任务唯一标识
    strategy_name: str  # 策略名称
    backtest_config: dict  # 回测配置
    status: str  # 任务状态: pending/running/completed/failed
    created_at: datetime  # 创建时间
    started_at: Optional[datetime]  # 开始执行时间
    completed_at: Optional[datetime]  # 完成时间
    result_id: Optional[str]  # 关联的回测结果ID

# 回测配置模型
class BacktestConfig:
    symbol: str  # 交易对
    interval: str  # 时间周期
    start_time: str  # 开始时间
    end_time: str  # 结束时间
    initial_cash: float  # 初始资金
    commission: float  # 手续费率
    exclusive_orders: bool  # 是否排他订单
```

### 2.2 策略管理模块

**功能描述**：负责策略脚本的上传、管理和动态加载。

**核心组件**：

| 组件 | 职责 | 实现类/函数 |
|------|------|-------------|
| 策略文件管理器 | 处理策略文件的上传、存储和删除 | `BacktestService.upload_strategy_file` |
| 策略加载器 | 动态加载策略类 | `BacktestService.load_strategy_from_file` |
| 策略参数验证器 | 验证策略参数的有效性 | 待实现 |

**关键数据结构**：

```python
# 策略信息模型
class StrategyInfo:
    name: str  # 策略名称
    filename: str  # 策略文件名
    description: Optional[str]  # 策略描述
    parameters: List[Dict]  # 策略参数列表
    created_at: datetime  # 创建时间
    updated_at: datetime  # 更新时间
```

### 2.3 回测数据持久化模块

**功能描述**：负责回测结果数据的完整持久化存储。

**核心组件**：

| 组件 | 职责 | 实现类/函数 |
|------|------|-------------|
| 数据模型定义 | 定义回测相关的数据模型 | SQLAlchemy Models |
| 数据访问层 | 处理数据的CRUD操作 | 数据库会话管理 |
| 结果格式化器 | 格式化回测结果数据 | `BacktestService.translate_backtest_results` |

**数据库表设计**：

```sql
-- 回测任务表
CREATE TABLE backtest_tasks (
    id VARCHAR(50) PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    backtest_config TEXT NOT NULL,  -- JSON格式
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    result_id VARCHAR(50)
);

-- 回测结果表
CREATE TABLE backtest_results (
    id VARCHAR(50) PRIMARY KEY,
    task_id VARCHAR(50) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    metrics TEXT NOT NULL,  -- JSON格式，包含翻译后的指标
    trades TEXT NOT NULL,  -- JSON格式，交易记录
    equity_curve TEXT NOT NULL,  -- JSON格式，资金曲线
    strategy_data TEXT NOT NULL,  -- JSON格式，策略数据
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES backtest_tasks(id)
);

-- 策略表
CREATE TABLE strategies (
    name VARCHAR(100) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    description TEXT,
    parameters TEXT,  -- JSON格式，策略参数定义
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 2.4 高级可视化与回放模块

**功能描述**：基于klinecharts实现专业级回测结果可视化和历史回放功能。

**核心组件**：

| 组件 | 职责 | 实现类/函数 |
|------|------|-------------|
| K线图表管理器 | 初始化和管理K线图表 | `BacktestReplay.initChart` |
| 数据更新器 | 更新图表数据 | `BacktestReplay.updateChartData` |
| 交易信号渲染器 | 渲染交易信号标记 | `BacktestReplay.renderTradeSignals` |
| 回放控制器 | 控制回放逻辑 | `BacktestReplay.animate` |
| 播放速度管理器 | 处理播放速度调整 | `BacktestReplay.adjustSpeed` |

**关键数据结构**：

```typescript
// 回放数据结构
interface ReplayData {
    kline_data: KlineItem[];  // K线数据
    trade_signals: TradeSignal[];  // 交易信号
    equity_data: EquityPoint[];  // 资金曲线数据
}

// 回放控制状态
interface ReplayControlState {
    isPlaying: boolean;  // 播放状态
    currentIndex: number;  // 当前索引
    speed: number;  // 播放速度
    progress: number;  // 播放进度 (0-100)
}
```

## 3. 数据流程设计

### 3.1 回测执行数据流程

```
1. 前端用户在回测任务配置页面选择策略、设置参数
2. 前端发送创建回测任务请求到API
3. API层验证请求数据，创建回测任务记录
4. 调用BacktestService执行回测：
   a. 加载策略类
   b. 获取K线数据
   c. 执行回测 (使用backtesting.py)
   d. 处理回测结果
   e. 翻译结果为多语言格式
   f. 保存回测结果到数据库
5. 更新回测任务状态
6. 前端通过轮询或WebSocket获取任务状态更新
7. 回测完成后，前端展示回测结果
```

### 3.2 回测回放数据流程

```
1. 前端用户在回测结果页面点击"回放"按钮
2. 前端导航到回放页面，携带回测ID
3. 前端请求回放数据API
4. API层调用BacktestService获取回放数据：
   a. 加载回测结果
   b. 准备K线数据
   c. 提取交易信号
   d. 提取资金曲线数据
5. 前端接收回放数据，初始化K线图表
6. 用户操作播放控制：
   a. 点击播放按钮，启动动画循环
   b. 调整播放速度，更新帧间隔
   c. 拖动进度条，直接跳转到指定位置
   d. 点击暂停按钮，停止动画循环
7. 动画循环中：
   a. 根据当前索引更新K线数据
   b. 渲染对应时间点的交易信号
   c. 更新进度条
   d. 检查是否到达数据末尾
```

## 4. 关键API定义

### 4.1 回测任务管理API

| API路径 | 方法 | 功能描述 | 请求体 | 响应体 |
|---------|------|----------|--------|--------|
| `/api/backtest/tasks` | POST | 创建回测任务 | `BacktestRunRequest` | `{"task_id": "string"}` |
| `/api/backtest/tasks` | GET | 获取回测任务列表 | N/A | `{"tasks": [BacktestTask]}` |
| `/api/backtest/tasks/{task_id}` | GET | 获取回测任务详情 | N/A | `BacktestTask` |
| `/api/backtest/tasks/{task_id}/run` | POST | 执行回测任务 | N/A | `{"status": "running"}` |
| `/api/backtest/tasks/{task_id}/stop` | POST | 停止回测任务 | N/A | `{"status": "stopped"}` |
| `/api/backtest/tasks/{task_id}` | DELETE | 删除回测任务 | N/A | `{"success": true}` |

### 4.2 策略管理API

| API路径 | 方法 | 功能描述 | 请求体 | 响应体 |
|---------|------|----------|--------|--------|
| `/api/backtest/strategies` | GET | 获取策略列表 | N/A | `{"strategies": [StrategyInfo]}` |
| `/api/backtest/strategies` | POST | 上传策略 | `StrategyUploadRequest` | `{"success": true}` |
| `/api/backtest/strategies/{strategy_name}` | GET | 获取策略详情 | N/A | `StrategyInfo` |
| `/api/backtest/strategies/{strategy_name}` | DELETE | 删除策略 | N/A | `{"success": true}` |

### 4.3 回测结果API

| API路径 | 方法 | 功能描述 | 请求体 | 响应体 |
|---------|------|----------|--------|--------|
| `/api/backtest/results` | GET | 获取回测结果列表 | N/A | `{"results": [BacktestResult]}` |
| `/api/backtest/results/{result_id}` | GET | 获取回测结果详情 | N/A | `BacktestResult` |
| `/api/backtest/results/{result_id}` | DELETE | 删除回测结果 | N/A | `{"success": true}` |

### 4.4 回测回放API

| API路径 | 方法 | 功能描述 | 请求体 | 响应体 |
|---------|------|----------|--------|--------|
| `/api/backtest/replay/{backtest_id}` | GET | 获取回放数据 | N/A | `ReplayData` |
| `/api/backtest/replay/{backtest_id}/control` | POST | 控制回放 | `ReplayControlRequest` | `ReplayControlResponse` |

## 5. 实现难点与解决方案

### 5.1 动态策略加载与执行

**问题描述**：如何安全地加载和执行用户上传的策略脚本。

**解决方案**：
- 使用Python的`importlib`模块动态加载策略类
- 严格验证策略类是否继承自`backtesting.Strategy`
- 限制策略执行的资源使用（时间、内存）
- 使用沙箱环境执行用户策略（可选）

**代码示例**：
```python
def load_strategy_from_file(self, strategy_name):
    # 动态导入策略模块
    spec = importlib.util.spec_from_file_location(strategy_name, strategy_file)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[strategy_name] = module
        spec.loader.exec_module(module)
        
        # 查找Strategy子类
        for name, cls in module.__dict__.items():
            if isinstance(cls, type) and issubclass(cls, Strategy) and cls != Strategy:
                return cls
```

### 5.2 回测结果多语言支持

**问题描述**：backtesting.py默认输出英文结果，需要支持多语言展示。

**解决方案**：
- 建立指标翻译映射表，包含中英文名称和描述
- 重写结果处理逻辑，将英文指标转换为多语言格式
- 支持动态切换语言

**代码示例**：
```python
def translate_backtest_results(self, stats):
    translated_metrics = []
    for key, value in stats.items():
        if key in ['_strategy', '_equity_curve', '_trade_list', '_trades']:
            continue
    
        # 翻译指标
        translation = self.translations.get(key, {'cn': key, 'en': key, 'desc': ''})
        
        # 处理特殊类型的值
        if isinstance(value, pd.Timestamp):
            value = value.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(value, pd.Timedelta):
            value = str(value)
    
        translated_metrics.append({
            'name': key,
            'cn_name': translation['cn'],
            'en_name': translation['en'],
            'value': value,
            'description': translation['desc']
        })
    
    return translated_metrics
```

### 5.3 高性能K线图表渲染

**问题描述**：处理大量K线数据时的图表渲染性能问题。

**解决方案**：
- 使用klinecharts的增量更新机制，只更新变化的数据
- 实现数据分页加载，避免一次性加载全部数据
- 使用requestAnimationFrame优化动画性能
- 合理设置图表配置，减少渲染压力

**代码示例**：
```typescript
const animate = (timestamp: number) => {
    if (!replayData || !isPlaying) return;
    
    if (!lastUpdateTimeRef.current) {
        lastUpdateTimeRef.current = timestamp;
    }
    
    // 计算时间差
    const elapsedTime = timestamp - lastUpdateTimeRef.current;
    const frameInterval = 1000 / speed; // 根据速度调整帧间隔
    
    if (elapsedTime >= frameInterval) {
        // 更新索引
        setCurrentIndex(prevIndex => {
            const newIndex = prevIndex + 1;
            if (newIndex >= replayData.kline_data.length - 1) {
                // 回放结束
                setIsPlaying(false);
                return replayData.kline_data.length - 1;
            }
            return newIndex;
        });
        
        lastUpdateTimeRef.current = timestamp;
    }
    
    animationFrameRef.current = requestAnimationFrame(animate);
};
```

### 5.4 精确的交易信号标注

**问题描述**：在K线图表中精确标注交易信号。

**解决方案**：
- 将交易信号与K线时间戳精确匹配
- 使用klinecharts的markPoint功能绘制交易标记
- 区分买入和卖出信号的样式
- 支持悬停查看信号详情

**代码示例**：
```typescript
// 添加交易信号标记
currentSignals.forEach(signal => {
    const signalTime = new Date(signal.time).getTime();
    const markPointType = signal.type === 'buy' ? 'arrowUp' : 'arrowDown';
    const markPointColor = signal.type === 'buy' ? '#26a69a' : '#ef5350';
    
    // 添加标记点
    chartRef.current?.addMarkPoint({
        id: `signal_${signal.trade_id}`,
        data: [{
            timestamp: signalTime,
            price: signal.price,
            type: markPointType,
            color: markPointColor,
            text: signal.type === 'buy' ? '买' : '卖',
            textColor: '#fff',
            size: 20
        }]
    });
});
```

## 6. 前端界面设计

### 6.1 回测任务配置页面

**页面结构**：
- 策略选择区：下拉选择已上传策略或上传新策略
- 参数配置区：动态生成策略参数表单
- 回测配置区：时间范围、初始资金、手续费等
- 任务控制区：创建任务、执行/停止任务按钮
- 任务列表区：显示历史任务状态

### 6.2 回测结果展示页面

**页面结构**：
- 回测任务列表：左侧边栏，显示所有回测任务
- 关键指标概览：顶部卡片，显示总收益率、年化收益率、最大回撤等
- 绩效分析图表：收益率曲线、资金曲线
- 交易详情表格：展示所有交易记录
- 风险分析图表：最大回撤、夏普比率等风险指标

### 6.3 回测回放页面

**页面结构**：
- K线图表区：占页面主要部分，显示K线和交易信号
- 回放控制面板：
  - 播放控制按钮：停止、播放/暂停
  - 进度条：可拖动调整进度
  - 速度控制：1x、2x、5x、10x等
- 回放信息区：当前进度、K线数量、交易信号数量等

## 7. 部署与集成方案

### 7.1 前端部署

```bash
# 构建前端项目
bun run build

# 部署到静态文件服务器
# 例如：使用Nginx部署
```

### 7.2 后端部署

```bash
# 安装依赖
cd backend
uv install

# 启动后端服务
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 7.3 数据库初始化

```bash
# 执行数据库迁移
cd backend
python -m alembic upgrade head
```

## 8. 测试策略

### 8.1 单元测试

```bash
# 运行后端单元测试
cd backend
python -m pytest tests/

# 运行前端单元测试
cd frontend
bun test
```

### 8.2 集成测试

- 测试完整的回测流程：创建任务 -> 执行回测 -> 查看结果 -> 回放回测
- 测试不同策略的回测效果
- 测试各种参数配置的回测结果

### 8.3 性能测试

- 测试大数据量下的回测执行时间
- 测试回放功能的流畅度
- 测试多任务并发执行情况

## 9. 后续扩展规划

1. **策略优化建议**：基于回测结果提供智能优化建议
2. **参数寻优**：支持网格搜索、遗传算法等参数优化方法
3. **多策略回测**：支持同时回测多个策略并比较结果
4. **实盘模拟**：支持模拟实盘交易
5. **WebSocket实时更新**：使用WebSocket实现回测任务状态的实时更新
6. **分布式回测**：支持多节点分布式回测，提高大规模回测效率
7. **更多数据源支持**：支持从不同交易所获取历史数据
8. **自定义指标**：支持用户自定义回测指标

## 10. 技术参考与改进

### 10.1 参考项目分析

**ZBot项目优点**：
- 完整的回测记录数据库模型
- 策略加载机制设计合理
- 结果翻译功能实现较好

**ZBot项目改进点**：
- 回测播放功能未完成，需要完善
- 前端界面较为简单，需要优化
- 缺乏任务管理系统
- 回测结果展示不够丰富

### 10.2 本设计的改进与创新

1. **完整的回测任务管理系统**：支持任务的创建、执行、监控和管理
2. **高级可视化功能**：基于klinecharts实现专业级K线图表
3. **完善的回测回放功能**：支持播放、暂停、进度调整和倍速控制
4. **更好的用户体验**：现代化的前端界面设计
5. **更灵活的策略管理**：支持策略上传、参数配置和动态加载
6. **完整的数据持久化**：所有回测相关数据都持久化存储
7. **多语言支持**：支持中英文切换

## 11. 结论

本设计文档提供了基于backtesting.py的完整策略回测模块设计，包括系统架构、核心模块、数据流程、API定义和实现难点解决方案。该设计借鉴了ZBot项目的经验，同时解决了其已知缺陷并扩展了新功能，为用户提供了一个功能完善、易用、高性能的策略回测系统。

该模块的实现将大大提升策略开发和回测的效率，帮助用户更好地评估和优化交易策略，为实盘交易提供有力支持。