# QuantCell AI原生重构 — TDD实施计划

> 日期: 2026-06-23
> 方法: Test-Driven Development (Red→Green→Refactor 垂直切片)
> 前置文档: `docs/plans/2026-06-23-ai-native-refactoring-design.md`

---

## 核心原则

1. **垂直切片**: 每个行为先写测试再写实现，不批量写测试
2. **公共接口测试**: 测试通过公共API验证行为，不依赖内部实现
3. **可存活重构**: 测试在内部重构时不应失败
4. **最小代码**: 只写刚好通过当前测试的代码

---

## Phase 1: axon_quant SDK封装层 (Week 1-2)

### Slice 1.1: SDK可用性检测

**行为**: 当axon_quant已安装时，SDK模块报告AVAILABLE=True；未安装时报告AVAILABLE=False且不崩溃

```
RED:  test_sdk_available_when_installed → 失败（模块不存在）
GREEN: 创建 backend/axon_quant_sdk/__init__.py + _compat.py
```

**测试文件**: `tests/unit/test_axon_quant_sdk.py`

```python
def test_sdk_reports_available_when_axon_quant_installed():
    from axon_quant_sdk import AVAILABLE
    assert isinstance(AVAILABLE, bool)

def test_sdk_graceful_degradation_when_missing():
    import importlib
    import axon_quant_sdk._compat as compat
    assert hasattr(compat, 'check_availability')
```

**关键文件**: `backend/axon_quant_sdk/__init__.py`, `backend/axon_quant_sdk/_compat.py`
**验收**: `import axon_quant_sdk` 不抛异常，`axon_quant_sdk.AVAILABLE` 为bool

---

### Slice 1.2: backtest模块封装

**行为**: BacktestService接受QuantCell格式的bar数据和策略回调，返回回测结果字典

```
RED:  test_backtest_service_runs_simple_strategy → 失败
GREEN: 创建 backend/axon_quant_sdk/backtest.py
```

**测试文件**: `tests/unit/test_axon_quant_sdk_backtest.py`

```python
def test_backtest_service_creation():
    from axon_quant_sdk.backtest import BacktestService
    service = BacktestService(initial_cash=100_000.0)
    assert service is not None

def test_backtest_service_runs_and_returns_result():
    from axon_quant_sdk.backtest import BacktestService
    service = BacktestService(initial_cash=100_000.0)
    bars = [
        {"timestamp": 1000, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
        {"timestamp": 2000, "open": 102, "high": 108, "low": 100, "close": 106, "volume": 1200},
    ]
    def simple_strategy(bar, portfolio):
        return [{"side": "buy", "quantity": 1.0}] if bar["close"] > 100 else []
    result = service.run(bars, simple_strategy)
    assert "total_pnl" in result
    assert "fills" in result
```

**关键文件**: `backend/axon_quant_sdk/backtest.py`
**验收**: 可用QuantCell格式数据执行简单回测并获得结果

---

### Slice 1.3: risk模块封装

**行为**: RiskManager检查订单是否通过风控，返回(通过, 原因)元组

```
RED:  test_risk_manager_checks_order → 失败
GREEN: 创建 backend/axon_quant_sdk/risk.py
```

**测试文件**: `tests/unit/test_axon_quant_sdk_risk.py`

```python
def test_risk_manager_creation():
    from axon_quant_sdk.risk import RiskManager
    rm = RiskManager()
    assert rm is not None

def test_risk_manager_accepts_valid_order():
    from axon_quant_sdk.risk import RiskManager
    rm = RiskManager({"max_order_notional": 100_000.0})
    order = {"symbol": "BTCUSDT", "side": "buy", "quantity": 0.1, "price": 50_000.0}
    portfolio = {"cash": 200_000.0, "positions": {}}
    passed, reason = rm.check_order(order, portfolio)
    assert passed is True

def test_risk_manager_rejects_oversized_order():
    from axon_quant_sdk.risk import RiskManager
    rm = RiskManager({"max_order_notional": 10_000.0})
    order = {"symbol": "BTCUSDT", "side": "buy", "quantity": 1.0, "price": 50_000.0}
    portfolio = {"cash": 200_000.0, "positions": {}}
    passed, reason = rm.check_order(order, portfolio)
    assert passed is False
```

**关键文件**: `backend/axon_quant_sdk/risk.py`
**验收**: RiskManager可创建、可检查订单、正确拒绝超限订单

---

### Slice 1.4: rl模块封装

**行为**: RLEnvironmentFactory创建TradingEnv，RLTrainer执行训练

```
RED:  test_rl_env_factory_creates_env → 失败
GREEN: 创建 backend/axon_quant_sdk/rl.py
```

**测试文件**: `tests/unit/test_axon_quant_sdk_rl.py`

```python
def test_rl_env_factory_creates_env():
    import pandas as pd
    from axon_quant_sdk.rl import RLEnvironmentFactory
    data = pd.DataFrame({
        "open": [100,101,102,103,104], "high": [105,106,107,108,109],
        "low": [95,96,97,98,99], "close": [102,103,104,105,106],
        "volume": [1000,1100,1200,1300,1400],
    })
    env = RLEnvironmentFactory.create_env(data, features=["close"], reward_type="sharpe")
    assert env is not None
    obs, info = env.reset()
    assert obs is not None

def test_rl_trainer_creates_with_algorithm():
    from axon_quant_sdk.rl import RLTrainer
    trainer = RLTrainer(algorithm="ppo")
    assert trainer is not None
```

**关键文件**: `backend/axon_quant_sdk/rl.py`
**验收**: 可创建RL环境并执行reset/step

---

### Slice 1.5: llm模块封装

**行为**: TradingLLMAgent创建时接受工具列表

```
RED:  test_llm_agent_creation → 失败
GREEN: 创建 backend/axon_quant_sdk/llm.py + trading.py
```

**测试文件**: `tests/unit/test_axon_quant_sdk_llm.py`

```python
def test_llm_agent_creation():
    from axon_quant_sdk.llm import TradingLLMAgent
    from axon_quant_sdk.trading import PlaceOrderTool, QueryPortfolioTool
    agent = TradingLLMAgent(tools=[PlaceOrderTool(), QueryPortfolioTool()])
    assert agent is not None
```

**关键文件**: `backend/axon_quant_sdk/llm.py`, `backend/axon_quant_sdk/trading.py`
**验收**: Agent可创建并持有工具列表

---

### Slice 1.6: 类型统一

**行为**: axon_quant_sdk.types导出核心类型

```
RED:  test_types_export_bar_order_position → 失败
GREEN: 创建 backend/axon_quant_sdk/types.py
```

**测试文件**: `tests/unit/test_axon_quant_sdk_types.py`

```python
def test_types_export_core_types():
    from axon_quant_sdk.types import Bar, Order, OrderSide
    assert Bar is not None
    assert Order is not None

def test_bar_creation_from_dict():
    from axon_quant_sdk.types import Bar
    bar = Bar.from_dict({"timestamp": 1000, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000})
    assert bar.close == 102
```

**关键文件**: `backend/axon_quant_sdk/types.py`
**验收**: 核心类型可导入，支持QuantCell格式转换

---

## Phase 2: 回测系统增强 (Week 3-4)

### Slice 2.1: axon回测引擎适配器

**行为**: AxonEngine作为回测引擎选项

```
RED:  test_axon_engine_creation → 失败
GREEN: 创建 backend/backtest/engines/axon_engine.py
```

**测试文件**: `tests/unit/test_axon_backtest_engine.py`

```python
def test_axon_engine_creation():
    from backtest.engines.axon_engine import AxonEngine
    engine = AxonEngine(initial_cash=100_000.0)
    assert engine is not None

def test_axon_engine_runs_backtest():
    from backtest.engines.axon_engine import AxonEngine
    engine = AxonEngine(initial_cash=100_000.0)
    config = {"symbol": "BTCUSDT", "timeframe": "1h"}
    result = engine.run(config, strategy_fn=lambda bar, portfolio: [])
    assert "metrics" in result
    assert "trades" in result
```

**关键文件**: `backend/backtest/engines/axon_engine.py`, `backend/backtest/engine_service.py`
**验收**: engine_service可通过配置选择axon引擎

---

### Slice 2.2: Walk-Forward验证

**行为**: WalkForwardService执行滚动/扩展窗口验证

```
RED:  test_walk_forward_service_validates → 失败
GREEN: 创建 backend/backtest/walk_forward.py
```

**测试文件**: `tests/unit/test_walk_forward.py`

```python
def test_walk_forward_service_creation():
    from backtest.walk_forward import WalkForwardService
    wf = WalkForwardService()
    assert wf is not None

def test_walk_forward_rolling_mode():
    import pandas as pd
    from backtest.walk_forward import WalkForwardService
    wf = WalkForwardService()
    data = pd.DataFrame({"close": range(100, 200), "volume": [1000]*100})
    result = wf.validate(strategy_name="test", data=data, n_splits=3, mode="rolling")
    assert "splits" in result
    assert len(result["splits"]) == 3
```

**关键文件**: `backend/backtest/walk_forward.py`
**验收**: 可执行Walk-Forward验证并返回各窗口指标

---

### Slice 2.3: HPO超参数优化

**行为**: HPORunner执行超参数搜索

```
RED:  test_hpo_runner_optimizes → 失败
GREEN: 创建 backend/backtest/hpo_runner.py
```

**测试文件**: `tests/unit/test_hpo_runner.py`

```python
def test_hpo_runner_creation():
    from backtest.hpo_runner import HPORunner
    hpo = HPORunner()
    assert hpo is not None

def test_hpo_runner_finds_best_params():
    from backtest.hpo_runner import HPORunner
    hpo = HPORunner()
    param_space = {"fast": {"type":"int","low":5,"high":20}, "slow": {"type":"int","low":20,"high":50}}
    result = hpo.optimize(objective_fn=lambda p: p["slow"]-p["fast"], param_space=param_space, n_trials=10)
    assert "best_params" in result
    assert result["best_value"] > 0
```

**关键文件**: `backend/backtest/hpo_runner.py`
**验收**: 可执行HPO并返回最优参数

---

## Phase 3: RL训练管线 (Week 5-7)

### Slice 3.1: RL Service基础

**行为**: RLService创建训练环境

```
RED:  test_rl_service_creates_env → 失败
GREEN: 创建 backend/services/rl_service.py
```

**测试文件**: `tests/unit/test_rl_service.py`

```python
def test_rl_service_creation():
    from services.rl_service import RLService
    svc = RLService()
    assert svc is not None

def test_rl_service_creates_environment():
    import pandas as pd
    from services.rl_service import RLService
    svc = RLService()
    data = pd.DataFrame({"open":range(100,200),"high":range(105,205),"low":range(95,195),"close":range(101,201),"volume":[1000]*100})
    env = svc.create_env(data, features=["close"], reward_type="sharpe")
    assert env is not None
```

**关键文件**: `backend/services/rl_service.py`
**验收**: RLService可创建环境

---

### Slice 3.2: RL训练执行

**行为**: RLService执行训练并返回模型

```
RED:  test_rl_service_trains_model → 失败
GREEN: 实现 RLService.train()
```

**测试文件**: `tests/unit/test_rl_service.py` (追加)

```python
def test_rl_service_trains_ppo():
    import pandas as pd
    from services.rl_service import RLService, RLTrainConfig
    svc = RLService()
    data = pd.DataFrame({"open":range(100,200),"high":range(105,205),"low":range(95,195),"close":range(101,201),"volume":[1000]*100})
    config = RLTrainConfig(algorithm="ppo", data=data, features=["close"], reward_type="sharpe", total_timesteps=1000)
    result = svc.train(config)
    assert result.model_id is not None
```

**验收**: 可训练PPO模型并返回模型ID

---

### Slice 3.3: 模型注册

**行为**: ModelRegistryService注册、列出、比较模型

```
RED:  test_model_registry_registers → 失败
GREEN: 创建 backend/model/registry.py
```

**测试文件**: `tests/unit/test_model_registry.py`

```python
def test_model_registry_registers_and_lists():
    from model.registry import ModelRegistryService
    registry = ModelRegistryService()
    registry.register_model(name="test", model_path="/tmp/test.onnx", metadata={"algo":"ppo"}, metrics={"sharpe":1.5})
    models = registry.list_models()
    assert any(m["name"] == "test" for m in models)
```

**关键文件**: `backend/model/registry.py`
**验收**: 可注册模型并列出

---

## Phase 4: Agent双层架构 (Week 8-10)

### Slice 4.1: InteractionAgent意图路由

**行为**: InteractionAgent解析用户消息并路由到正确处理器

```
RED:  test_interaction_agent_routes_intent → 失败
GREEN: 创建 backend/agent/core/interaction_agent.py
```

**测试文件**: `tests/unit/test_interaction_agent.py`

```python
def test_interaction_agent_parses_backtest_intent():
    from agent.core.interaction_agent import InteractionAgent
    agent = InteractionAgent(llm_provider=None, services={})
    intent = agent._parse_intent_static("帮我回测MACD策略")
    assert intent.category == "backtest"

def test_interaction_agent_parses_rl_intent():
    from agent.core.interaction_agent import InteractionAgent
    agent = InteractionAgent(llm_provider=None, services={})
    intent = agent._parse_intent_static("用PPO训练一个BTC策略")
    assert intent.category == "rl_training"
```

**关键文件**: `backend/agent/core/interaction_agent.py`
**验收**: 可解析backtest/rl/trading三类意图

---

### Slice 4.2: DecisionAgent ReAct循环

**行为**: DecisionAgent持有axon_quant工具

```
RED:  test_decision_agent_has_tools → 失败
GREEN: 创建 backend/agent/core/decision_agent.py
```

**测试文件**: `tests/unit/test_decision_agent.py`

```python
def test_decision_agent_creation():
    from agent.core.decision_agent import DecisionAgent
    agent = DecisionAgent(services={})
    assert agent is not None

def test_decision_agent_has_tools():
    from agent.core.decision_agent import DecisionAgent
    agent = DecisionAgent(services={})
    tool_names = agent.get_tool_names()
    assert "place_order" in tool_names
    assert "query_portfolio" in tool_names
```

**关键文件**: `backend/agent/core/decision_agent.py`
**验收**: DecisionAgent可创建并持有axon_quant工具

---

### Slice 4.3: 双层Agent委托

**行为**: InteractionAgent将交易决策委托给DecisionAgent

```
RED:  test_interaction_delegates_to_decision → 失败
GREEN: 实现委托机制
```

**测试文件**: `tests/unit/test_interaction_agent.py` (追加)

```python
def test_interaction_delegates_trading_to_decision():
    from agent.core.interaction_agent import InteractionAgent
    from agent.core.decision_agent import DecisionAgent
    decision = DecisionAgent(services={})
    interaction = InteractionAgent(llm_provider=None, services={}, decision_agent=decision)
    assert interaction._decision_agent is decision
```

**验收**: 交互Agent可委托交易决策给决策Agent

---

## Phase 5: 实盘增强 (Week 11-12)

### Slice 5.1: RL推理Worker

**行为**: RLWorker加载RL模型并预测交易动作

```
RED:  test_rl_worker_predicts → 失败
GREEN: 创建 backend/worker/rl_worker.py
```

**测试文件**: `tests/unit/test_rl_worker.py`

```python
def test_rl_worker_creation():
    from worker.rl_worker import RLWorker
    worker = RLWorker(model_path="/tmp/test.onnx")
    assert worker is not None

def test_rl_worker_predicts_action():
    from worker.rl_worker import RLWorker
    worker = RLWorker(model_path="/tmp/test.onnx")
    action = worker.predict({"close": 50000.0, "volume": 1000.0, "position": 0.0})
    assert "side" in action
```

**关键文件**: `backend/worker/rl_worker.py`
**验收**: 可加载模型并预测

---

### Slice 5.2: 实时风控监控

**行为**: RiskMonitor检查订单并记录告警

```
RED:  test_risk_monitor_checks_order → 失败
GREEN: 创建 backend/worker/risk_monitor.py
```

**测试文件**: `tests/unit/test_risk_monitor.py`

```python
def test_risk_monitor_accepts_valid_order():
    from worker.risk_monitor import RiskMonitor
    monitor = RiskMonitor(config={"max_order_notional": 100_000.0})
    passed = monitor.check_order({"symbol":"BTCUSDT","side":"buy","quantity":0.1,"price":50000}, {"cash":200000,"positions":{}})
    assert passed is True

def test_risk_monitor_rejects_and_alerts():
    from worker.risk_monitor import RiskMonitor
    monitor = RiskMonitor(config={"max_order_notional": 10_000.0})
    passed = monitor.check_order({"symbol":"BTCUSDT","side":"buy","quantity":1.0,"price":50000}, {"cash":200000,"positions":{}})
    assert passed is False
    assert len(monitor.alerts) == 1
```

**关键文件**: `backend/worker/risk_monitor.py`
**验收**: 可检查订单、拒绝超限、记录告警

---

### Slice 5.3: 集成投票Worker

**行为**: EnsembleWorker加载多模型并投票预测

```
RED:  test_ensemble_worker_votes → 失败
GREEN: 创建 backend/worker/ensemble_worker.py
```

**测试文件**: `tests/unit/test_ensemble_worker.py`

```python
def test_ensemble_worker_creation():
    from worker.ensemble_worker import EnsembleWorker
    worker = EnsembleWorker(model_paths=["/tmp/m1.onnx","/tmp/m2.onnx"], strategy="soft_vote")
    assert worker is not None

def test_ensemble_worker_predicts():
    from worker.ensemble_worker import EnsembleWorker
    worker = EnsembleWorker(model_paths=["/tmp/m1.onnx","/tmp/m2.onnx"], strategy="soft_vote")
    result = worker.predict({"close": 50000.0})
    assert "action" in result
    assert "confidence" in result
```

**关键文件**: `backend/worker/ensemble_worker.py`
**验收**: 可加载多模型并投票预测

---

## Phase 6: 前端AI化 (Week 13-14)

### Slice 6.1: 全局AI面板组件

**行为**: AgentPanel可在任何页面打开，传递上下文

```
RED:  test_agent_panel_renders → 失败
GREEN: 创建 frontend/src/components/AgentPanel.tsx
```

**测试文件**: `frontend/src/components/__tests__/AgentPanel.test.tsx`

```typescript
describe('AgentPanel', () => {
  it('renders when visible', () => {
    render(<AgentPanel visible={true} onClose={() => {}} />);
    expect(screen.getByTestId('agent-panel')).toBeInTheDocument();
  });
  it('passes context to backend', async () => {
    const mockFetch = jest.fn();
    global.fetch = mockFetch;
    render(<AgentPanel visible={true} onClose={() => {}} context={{ page: 'backtest' }} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '分析回测' } });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));
    expect(mockFetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      body: expect.stringContaining('"page":"backtest"'),
    }));
  });
});
```

**关键文件**: `frontend/src/components/AgentPanel.tsx`
**验收**: 组件可渲染、可传递上下文

---

### Slice 6.2: RL训练页面

**行为**: RLTrainingPage展示训练配置表单

```
RED:  test_rl_training_page_renders → 失败
GREEN: 创建 frontend/src/pages/rl/RLTrainingPage.tsx
```

**测试文件**: `frontend/src/pages/rl/__tests__/RLTrainingPage.test.tsx`

```typescript
describe('RLTrainingPage', () => {
  it('renders training config form', () => {
    render(<RLTrainingPage />);
    expect(screen.getByLabelText(/algorithm/i)).toBeInTheDocument();
  });
});
```

**关键文件**: `frontend/src/pages/rl/RLTrainingPage.tsx`
**验收**: 页面可渲染表单

---

## 依赖图

```
Phase 1 (SDK)
├── 1.1 可用性 → 1.2 backtest → 1.3 risk
│             → 1.4 rl → 1.5 llm
│             → 1.6 types
Phase 2 (回测) ← Phase 1
├── 2.1 axon引擎 → 2.2 Walk-Forward → 2.3 HPO
Phase 3 (RL) ← Phase 1
├── 3.1 Service → 3.2 训练 → 3.3 注册
Phase 4 (Agent) ← Phase 1
├── 4.1 InteractionAgent → 4.2 DecisionAgent → 4.3 委托
Phase 5 (实盘) ← Phase 1, 3
├── 5.1 RL Worker → 5.2 风控 → 5.3 集成
Phase 6 (前端) ← Phase 4
├── 6.1 AI面板 → 6.2 RL页面
```

每个Slice严格遵循: **RED → GREEN → REFACTOR**
