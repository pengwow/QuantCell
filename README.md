# QuantCell - 智能量化交易系统

[Demo地址](https://demo.quantcell.top/chart) | [项目主页](https://quantcell.top)

## 项目简介

QuantCell 是一款 AI 驱动的智能量化交易系统，让量化交易变得简单、高效、智能。无需复杂的编程知识，只需用自然语言描述您的交易策略，系统就能自动生成可执行的策略代码并进行回测验证。

## 核心优势

### 🤖 AI 智能驱动
- **自然语言生成策略**: 用中文描述交易想法，AI 自动生成完整策略代码
- **智能代码优化**: 自动优化策略代码，提升执行效率
- **技术分析助手**: 内置技术分析技能，支持实时市场分析

### ⚡ 高性能回测
- **多引擎支持**: 事件驱动、向量化等多种回测引擎
- **极速计算**: 集成 Numba 加速，回测效率提升 10 倍以上
- **准确可靠**: 严格的数据完整性验证，确保回测结果可信

### 📊 完整数据生态
- **多交易所支持**: Binance、OKX 等主流交易所
- **实时数据采集**: 自动采集和管理市场数据
- **历史数据回补**: 智能数据缺失检测和回补

### 🔄 稳定工作流
- **完整生命周期管理**: 策略从开发到实盘的全流程支持
- **优雅关闭机制**: 确保交易状态安全保存
- **实时状态监控**: 随时掌握系统运行状态

### 🌐 友好的开发体验
- **清晰的 API 文档**: 自动生成的交互式 API 文档
- **模块化设计**: 易于扩展和定制
- **完善的测试覆盖**: 确保代码质量可靠

## 快速开始

### 环境要求
- Python 3.12+
- uv 包管理器

### 安装运行

```bash
# 克隆项目
git clone https://github.com/pengwow/quantcell.git
cd quantcell

# 进入后端目录
cd backend

# 安装依赖
uv sync

# 初始化数据库
python init_db.py

# 启动服务
python main.py
```

服务启动后，访问 `http://localhost:8000/docs` 查看 API 文档。

## 使用示例

### AI 生成策略

只需简单描述您的交易想法：

```
帮我生成一个基于 SMA 金叉死叉的交易策略，快线周期 10 天，慢线周期 20 天，当快线向上穿越慢线时买入，向下穿越时卖出。
```

系统会自动完成：
1. 理解您的需求
2. 生成策略代码
3. 验证代码正确性
4. 进行回测验证

### 回测策略

通过简单的 API 调用即可启动回测：

```python
from backtest.engine_service import BacktestEngine

# 创建回测引擎
engine = BacktestEngine()

# 配置回测参数
result = engine.run_backtest(
    strategy_name="sma_cross",
    initial_capital=100000,
    start_date="2024-01-01",
    end_date="2024-12-31",
    symbols=["BTCUSDT"]
)

# 查看回测结果
print(f"收益率: {result.total_return:.2f}%")
print(f"最大回撤: {result.max_drawdown:.2f}%")
```

## 为什么选择 QuantCell

| 特性 | QuantCell | 传统量化平台 |
|------|-----------|-------------|
| AI 策略生成 | ✅ 支持 | ❌ 不支持 |
| 自然语言交互 | ✅ 支持 | ❌ 不支持 |
| 多引擎回测 | ✅ 事件驱动+向量化 | ⚠️ 单一引擎 |
| 实时数据 | ✅ 自动采集 | ⚠️ 需手动配置 |
| 性能优化 | ✅ Numba 加速 | ❌ 通用计算 |
| 代码质量 | ✅ 自动验证 | ❌ 手动检查 |

## 技术亮点

- **智能 Agent 系统**: 具备记忆能力的 AI Agent，能够理解上下文并持续改进
- **思维链生成**: 多步骤策略生成，确保逻辑正确且可解释
- **模块化架构**: 清晰的模块划分，易于理解和扩展
- **优雅的错误处理**: 友好的错误提示和完善的日志系统

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支
3. 提交代码更改
4. 运行测试确保通过
5. 创建 Pull Request

## 许可证

本项目采用 Apache License 2.0 许可证。详见 [LICENSE](LICENSE) 文件。

## 联系方式

- 项目维护者: QuantCell Team
- 邮箱: <pengwow@hotmail.com>
- 网站: [https://quantcell.top](https://quantcell.top)

---

**QuantCell** - 让量化交易更简单、更智能！
