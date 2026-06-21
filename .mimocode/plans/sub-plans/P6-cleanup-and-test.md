# P6: 清理、测试、验证

## 目标

删除所有 nautilus 残留代码，更新示例策略，运行完整测试套件，进行性能验证。

## 依赖

- P2, P3, P4, P5 全部完成

## TDD 行为清单

### 1. nautilus 残留删除验证

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 1.1 | `grep -r "nautilus_trader" backend/` 返回 0 结果 | `tests/integration/test_no_nautilus.py` |
| 1.2 | `import nautilus_trader` 抛出 ImportError | `tests/integration/test_no_nautilus.py` |
| 1.3 | pyproject.toml 中不包含 nautilus_trader 依赖 | `tests/integration/test_no_nautilus.py` |

### 2. 示例策略迁移

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 2.1 | `strategies/simple_dual_ma.py` 继承 AxonStrategy | `tests/unit/backtest/test_example_strategies.py` |
| 2.2 | `strategies/simple_dual_ma.py` 可被 StrategyLoaderService 加载 | `tests/unit/backtest/test_example_strategies.py` |
| 2.3 | `strategies/new_strategy.py` 继承 AxonStrategy | `tests/unit/backtest/test_example_strategies.py` |
| 2.4 | `strategies/test0001.py` 继承 AxonStrategy | `tests/unit/backtest/test_example_strategies.py` |
| 2.5 | 所有示例策略不包含 nautilus 导入 | `tests/unit/backtest/test_example_strategies.py` |

### 3. 端到端集成测试

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 3.1 | 完整回测流程：加载数据 → 创建策略 → 执行回测 → 获取结果 | `tests/integration/test_e2e_backtest.py` |
| 3.2 | 完整回测流程使用 AxonStrategy 策略 | `tests/integration/test_e2e_backtest.py` |
| 3.3 | 完整回测流程使用 StrategyBase 策略（向量化路径） | `tests/integration/test_e2e_backtest.py` |
| 3.4 | AI 生成策略的完整流程：生成代码 → 验证 → 加载 → 回测 | `tests/integration/test_e2e_ai_strategy.py` |

### 4. 性能验证

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 4.1 | 单品种回测 100K bars 耗时 < 5 秒 | `tests/benchmark/test_backtest_perf.py` |
| 4.2 | 多品种回测（10 品种 × 10K bars）耗时 < 30 秒 | `tests/benchmark/test_backtest_perf.py` |
| 4.3 | axon 回测吞吐量 > 100K events/sec | `tests/benchmark/test_backtest_perf.py` |

### 5. 依赖清理

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 5.1 | `uv sync` 成功（无依赖冲突） | 手动验证 |
| 5.2 | 所有现有测试通过 | `python -m pytest tests/ -v` |
| 5.3 | ruff lint 无错误 | `ruff check backend/` |
| 5.4 | mypy 类型检查通过 | `mypy backend/` |

## 实现步骤

### Cycle 1: nautilus 残留删除

```
1. 删除 nautilus 相关文件:
   - backtest/engines/nautilus_engine.py
   - backtest/strategies/strategy_adapter.py (nautilus 版本)
   - backtest/strategies/core.py (重复副本)
2. 删除 exchange/binance/live_adapter.py 中的 nautilus 引用
3. 写 test_no_nautilus.py 验证 → 通过
```

### Cycle 2: 示例策略迁移

```
1. 重写 strategies/simple_dual_ma.py → 继承 AxonStrategy
2. 重写 strategies/new_strategy.py → 继承 AxonStrategy
3. 重写 strategies/test0001.py → 继承 AxonStrategy
4. 写 test_example_strategies.py → 通过
```

### Cycle 3: 端到端测试

```
1. 写 test_e2e_backtest.py 3.1-3.3 → 失败
2. 修复集成问题 → 通过
3. 写 test_e2e_ai_strategy.py 3.4 → 失败
4. 修复 AI 生成流程 → 通过
```

### Cycle 4: 性能验证

```
1. 写 test_backtest_perf.py 4.1-4.3 → 失败
2. 优化热点路径 → 通过
```

### Cycle 5: 依赖清理

```
1. 更新 pyproject.toml（删除 nautilus，升级依赖）
2. 重新生成 uv.lock
3. 运行 ruff + mypy → 修复问题
4. 运行完整测试套件 → 全部通过
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `backend/backtest/engines/nautilus_engine.py` | 删除 |
| `backend/backtest/strategies/strategy_adapter.py` | 删除（nautilus 版本） |
| `backend/backtest/strategies/core.py` | 删除（重复副本） |
| `backend/strategies/simple_dual_ma.py` | 重写 |
| `backend/strategies/new_strategy.py` | 重写 |
| `backend/strategies/test0001.py` | 重写 |
| `backend/pyproject.toml` | 更新：删除 nautilus，升级依赖 |
| `backend/tests/integration/test_no_nautilus.py` | 新建 |
| `backend/tests/unit/backtest/test_example_strategies.py` | 新建 |
| `backend/tests/integration/test_e2e_backtest.py` | 新建 |
| `backend/tests/integration/test_e2e_ai_strategy.py` | 新建 |
| `backend/tests/benchmark/test_backtest_perf.py` | 新建 |

## 验证

```bash
cd backend

# 1. nautilus 残留检查
grep -r "nautilus_trader" backend/ || echo "✅ No nautilus references"

# 2. 完整测试套件
python -m pytest tests/ -v --timeout=300

# 3. 代码质量
ruff check backend/
mypy backend/

# 4. 性能基准
python -m pytest tests/benchmark/ -v -s
```

全部通过后，迁移完成。
