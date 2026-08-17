# QuantCell v2.0 P1-Sprint 1 快速上手

> 30 分钟跑通第一个事件驱动回测

## 前置

- Python 3.14
- axon-quant 永远最新版本：`pip install --upgrade axon-quant`
- `/Users/liupeng/workspace/quant/axon` 源码仓库**仅作参考**，绝不 `sys.path.insert` 加载

## 安装

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
pip install -e .
quantcell --help   # 应输出 12 个子命令
```

## 跑回测

```bash
# 事件驱动回测(axon_quant 唯一路径)
quantcell backtest run --strategy dualma --symbol BTCUSDT --timeframe 1h
```

切换到 L2 撮合：

```python
from backend.axon_bridge import L2MatchingEngine, BacktestEngine

engine = BacktestEngine(matching=L2MatchingEngine(...))
```

## 统一 CLI 入口

`quantcell` 命令聚合 12 个子命令：

| 子命令 | 用途 |
|---|---|
| `agent` | AI agent 管理 |
| `backtest` | 事件驱动回测（axon_quant 唯一） |
| `data` | 数据采集 / 行情 / 存储 |
| `market` | 行情订阅 / 实时数据 |
| `migrate` | 数据库迁移 |
| `news` | 新闻 / 情绪数据 |
| `plugin` | 插件管理 |
| `rl` | 强化学习训练 / 推理 |
| `strategy` | 策略 CRUD / 生成 / 分析 / 优化 / 部署 |
| `tests` | 跑测试套件 |
| `web` | 启动 / 停止 Web 服务 |
| `worker` | Worker 工作进程管理 |

旧 `scripts/*_cli.py` 仍可调用（6 个月兼容期，转发到 `cli.*` 模块）。

## 架构边界

```
① 前端 (React)
   ↓
② QuantCell 业务层 (services/strategy/backtest/...)
   ↓
③ 适配层 (backend/axon_bridge/)  ← 所有 axon_quant 必经此
   ↓
④ axon_quant Rust 引擎（PyPI 安装，绝不源码加载）
```

**硬约束**：
- ② 层 services / strategy / backtest **只能** `from axon_bridge import X`
- ③ 层 `backend/axon_bridge/` 只做转译/包装/错误规范/异步桥接，**不加业务逻辑**
- ④ 层 axon_quant Rust 引擎**零修改**
- 回测**只走事件驱动**（axon_quant 唯一路径），**完全摒弃向量化回测**

## 适配层使用

```python
# ✅ 正确：走适配层
from axon_bridge import Action, ActionType, BacktestEngine, DefaultRiskEngine
from axon_bridge import rl, llm, hpo, registry, ensemble, walk_forward

# ❌ 错误：直连 axon_quant
from axon_quant import Action
import axon_quant
```

错误规范：所有 axon_quant 异常经 `axon_bridge._errors.map_error` 统一为 `AxonQuantError`，提供 `http_status + code + to_http()`。

## 验证 Sprint 1 收尾

```bash
cd /Users/liupeng/workspace/quant/QuantCell

# Step 1: 向量化回测代码 0 命中
git grep "VectorEngine" -- backend/    # 业务代码 0 命中
git grep "from backtest.engines" -- backend/  # 业务代码 0 命中

# Step 2: axon_quant 零源码依赖
git grep "sys.path.insert.*axon" -- backend/    # 0 命中
git grep "sys.path.insert.*axon_quant" -- backend/  # 0 命中

# Step 3: 业务代码不直连 axon_quant
git grep "import axon_quant" -- backend/ | grep -v "axon_bridge/" | grep -v "tests/"  # 0 命中
git grep "^from axon_quant import" -- backend/ | grep -v "axon_bridge/" | grep -v "tests/"  # 0 命中

# Step 4: 12 个子命令 --help
cd backend
for cmd in agent backtest data market migrate news plugin rl strategy tests web worker; do
    .venv/bin/quantcell $cmd --help > /dev/null 2>&1 && echo "✓ $cmd" || echo "✗ $cmd"
done
```

## 跑测试

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/python -m pytest tests/unit/axon_bridge -v        # 适配层 47/47
.venv/bin/python -m pytest tests/unit/test_rl_service.py -v # rl_service 18/18
.venv/bin/python -m pytest tests/unit/services -v           # services 7/7
```

## 后续 Sprint

- **P1-Sprint 2**：实盘交易所（Binance/OKX）+ 凭证管理 + 多账号 + 6-8 策略模板
- **P2-A Sprint 1**：RL 训练 + 推理 + 模型注册
- **P2-A Sprint 2**：HPO + Tracker + Ensemble
- **P2-B Sprint 1**：swarm 基础 + Agent 注册

详见 `docs/superpowers/specs/2026-07-16-axon-quant-integration-blueprint.md` §6。
