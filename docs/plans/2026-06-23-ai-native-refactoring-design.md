# QuantCell AI原生重构方案

> 设计日期: 2026-06-23
> 状态: 设计阶段

## 1. 整体架构设计 — 5层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Layer 5: Frontend (Vue3 + Ant Design X)          │
│  传统UI面板  ←→  AI对话界面 (Ant Design X)                          │
│  策略/回测/Worker/数据/设置  ←→  Agent对话                           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST + WebSocket + SSE
┌────────────────────────────────▼────────────────────────────────────┐
│                Layer 4: API Gateway (FastAPI)                       │
│  /api/v2/strategies  /api/v2/backtest  /api/v2/agent/chat (SSE)    │
│  /api/v2/rl/train    /api/v2/models    /api/v2/workers             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│            Layer 3: Business Services (Python)                      │
│  StrategyService  BacktestService  WorkerService  DataService       │
│  RLService  ModelRegistryService  AgentOrchestrator                 │
└───────┬────────────┬──────────────┬────────────────┬────────────────┘
        │            │              │                │
┌───────▼────────────▼──────────────▼────────────────▼────────────────┐
│          Layer 2: AI Agent System (双层架构)                         │
│  ┌─────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Interaction Agent    │  │ Decision Agent (axon_quant 驱动)    │  │
│  │ (QuantCell 交互层)   │  │ (底层决策引擎)                       │  │
│  │ - NLU/意图解析       │  │ - ReAct 交易循环                    │  │
│  │ - 工具编排           │  │ - RL 推理                           │  │
│  │ - 记忆/上下文        │  │ - 风控管理                          │  │
│  │ - 技能管理           │  │ - 集成投票                          │  │
│  └─────────────────────┘  └──────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│         Layer 1: axon_quant Integration Layer (axon_quant_sdk/)     │
│  16个axon_quant子模块的统一封装                                      │
│  rl  tracker  registry  hpo  walk_forward  distributed  llm        │
│  trading  data  backtest  risk  oms  exchange  inference            │
│  explain  ensemble  compliance                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**各层职责:**

| 层级 | 职责 | 技术栈 |
|------|------|--------|
| L5 前端 | 用户交互、可视化、AI对话 | Vue3, Ant Design X, ECharts |
| L4 API网关 | HTTP/WS路由、认证、限流 | FastAPI, Pydantic v2 |
| L3 业务服务 | 领域逻辑、工作流编排 | Python async services |
| L2 Agent | AI决策、双层Agent | OpenAI兼容LLM + axon_quant LLM |
| L1 集成层 | axon_quant Python绑定封装 | axon-quant PyO3包 |

---

## 2. axon_quant集成层设计

新建包: `backend/axon_quant_sdk/` — 对axon_quant 16个子模块的薄封装。

```
backend/axon_quant_sdk/
├── __init__.py              # 版本检查、可用性标志
├── _compat.py               # Python版本检查、导入防护
├── backtest.py              # axon_quant.backtest 封装
├── rl.py                    # axon_quant.rl 封装
├── hpo.py                   # axon_quant.hpo 封装
├── walk_forward.py          # axon_quant.walk_forward 封装
├── distributed.py           # axon_quant.distributed 封装
├── registry.py              # axon_quant.registry 封装
├── tracker.py               # axon_quant.tracker 封装
├── llm.py                   # axon_quant.llm 封装
├── trading.py               # axon_quant.trading 封装
├── data.py                  # axon_quant.data 封装
├── risk.py                  # axon_quant.risk 封装
├── oms.py                   # axon_quant.oms 封装
├── exchange.py              # axon_quant.exchange 封装
├── inference.py             # axon_quant.inference 封装
├── explain.py               # axon_quant.explain 封装
├── ensemble.py              # axon_quant.ensemble 封装
├── compliance.py            # axon_quant.compliance 封装
└── types.py                 # 核心类型重导出 (Bar, Order, Position等)
```

**设计原则:**

1. **优雅降级** — 每个模块用 `try/except ImportError` 包裹，暴露 `AVAILABLE` 标志
2. **类型统一** — 重导出axon_quant类型，与现有 `axond/types.py` 并存
3. **配置桥接** — QuantCell的SQLAlchemy配置 → axon_quant的dict/struct配置
4. **错误转换** — axon_quant Rust异常 → Python领域异常

**封装模式示例:**

```python
# backend/axon_quant_sdk/backtest.py
"""axon_quant.backtest 封装，集成QuantCell数据格式。"""

try:
    from axon_quant.backtest import BacktestEngine, BacktestEngineConfig, RunResult
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

from .types import Bar, OrderSide

class BacktestService:
    """QuantCell友好的axon_quant BacktestEngine封装。"""

    def __init__(self, initial_cash: float = 100_000.0):
        if not AVAILABLE:
            raise RuntimeError("axon_quant.backtest not available")
        self._config = BacktestEngineConfig(initial_cash=initial_cash)
        self._engine = BacktestEngine(self._config)

    def run(self, bars: list[dict], strategy_fn) -> dict:
        """使用QuantCell格式的bar和策略回调执行回测。"""
        # 转换QuantCell bars → axon_quant events
        # 执行回测
        # 返回QuantCell格式的结果dict
        ...
```

```python
# backend/axon_quant_sdk/rl.py
"""axon_quant.rl 封装，提供RL训练环境和算法。"""

try:
    from axon_quant.rl import TradingEnv, PPO, SAC, DQN
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

class RLEnvironmentFactory:
    """创建axon_quant RL训练环境。"""

    @staticmethod
    def create_env(
        data: pd.DataFrame,
        features: list[str],
        reward_type: str = "sharpe",
        **kwargs,
    ):
        if not AVAILABLE:
            raise RuntimeError("axon_quant.rl not available")
        # 转换QuantCell DataFrame → axon_quant env格式
        return TradingEnv(data=data, features=features, **kwargs)

class RLTrainer:
    """RL训练器，封装PPO/SAC/DQN。"""

    def __init__(self, algorithm: str = "ppo", **kwargs):
        if not AVAILABLE:
            raise RuntimeError("axon_quant.rl not available")
        algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
        self._algo = algo_map[algorithm](**kwargs)

    def train(self, env, total_timesteps: int, **kwargs):
        return self._algo.train(env, total_timesteps=total_timesteps, **kwargs)
```

```python
# backend/axon_quant_sdk/risk.py
"""axon_quant.risk 封装，提供实时风控。"""

try:
    from axon_quant.risk import RiskEngine, RiskConfig
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

class RiskManager:
    """QuantCell风控管理器。"""

    def __init__(self, config: dict | None = None):
        if not AVAILABLE:
            raise RuntimeError("axon_quant.risk not available")
        risk_config = RiskConfig(**config) if config else RiskConfig()
        self._engine = RiskEngine(risk_config)

    def check_order(self, order: dict, portfolio: dict) -> tuple[bool, str]:
        """检查订单是否通过风控。返回 (通过, 原因)。"""
        result = self._engine.check_order(order, portfolio)
        return result.passed, result.reason

    def get_limits(self) -> dict:
        """获取当前风控限制。"""
        return self._engine.get_config().__dict__
```

---

## 3. 业务层重构设计

### 3.1 策略管理 → StrategyService

```
backend/strategy/
├── service.py               # 重构: 增加AI生成管线
├── models.py                # 保留: SQLAlchemy模型
├── schemas.py               # 更新: 增加RL策略schema
├── routes.py                # 更新: 增加 /strategies/generate-ai
├── validation/              # 保留: 现有验证器
├── core/                    # 保留: StrategyCore, VectorEngine (引擎无关)
└── rl_strategy.py           # 新增: RL策略封装 (使用axon_quant.rl)
```

**关键变更:**
- 策略类型从 {手动, AI生成} 扩展为 {手动, AI生成, RL训练, 集成策略}
- `StrategyCore` 保持不变（引擎无关，无nautilus依赖）
- 新增 `RLStrategy` 类，将axon_quant RL策略封装为可调用策略
- AI策略生成使用axon_quant的LLM模块进行ReAct式代码生成

```python
# backend/strategy/rl_strategy.py
"""RL策略封装 — 将axon_quant RL策略包装为QuantCell策略。"""

class RLStrategy:
    """将训练好的RL模型包装为QuantCell可执行策略。"""

    def __init__(self, model_path: str, env_config: dict):
        from axon_quant_sdk.inference import InferenceEngine
        self._engine = InferenceEngine(model_path)
        self._env_config = env_config

    def on_bar(self, bar: dict, portfolio: dict) -> list[dict]:
        """处理bar事件，返回交易信号。"""
        # 构建observation
        obs = self._build_observation(bar, portfolio)
        # RL推理
        action = self._engine.predict(obs)
        # 转换为交易信号
        return self._action_to_orders(action, bar, portfolio)
```

### 3.2 回测系统 → BacktestService

```
backend/backtest/
├── service.py               # 重构: 委托给axon_quant BacktestEngine
├── engine_service.py        # 重构: 使用axon_quant_sdk.backtest
├── engines/
│   ├── axon_engine.py       # 新增: axon_quant BacktestEngine适配器
│   └── vector_engine.py     # 保留: 现有向量化引擎
├── walk_forward.py          # 新增: Walk-Forward验证 (axon_quant.walk_forward)
├── hpo_runner.py            # 新增: HPO (axon_quant.hpo, Optuna)
└── result_analyzer.py       # 新增: 增强分析 (axon_quant.explain)
```

**关键变更:**
- 事件驱动回测委托给 `axon_quant_sdk.backtest.BacktestService`
- 向量化回测保留（StrategyCore + VectorEngine，引擎无关）
- 新增Walk-Forward验证，使用 `axon_quant.walk_forward`
- 新增HPO runner，使用 `axon_quant.hpo`（Optuna）
- 结果分析增强，使用 `axon_quant.explain`（SHAP、反事实分析）

```python
# backend/backtest/walk_forward.py
"""Walk-Forward验证服务。"""

class WalkForwardService:
    """基于axon_quant.walk_forward的Walk-Forward验证。"""

    def __init__(self):
        from axon_quant_sdk.walk_forward import WalkForwardValidator
        self._validator = WalkForwardValidator()

    def validate(
        self,
        strategy_name: str,
        data: pd.DataFrame,
        n_splits: int = 5,
        train_ratio: float = 0.7,
        mode: str = "rolling",  # rolling | expanding
    ) -> dict:
        """执行Walk-Forward验证。"""
        results = self._validator.run(
            strategy_fn=self._load_strategy(strategy_name),
            data=data,
            n_splits=n_splits,
            train_ratio=train_ratio,
            mode=mode,
        )
        return self._format_results(results)

# backend/backtest/hpo_runner.py
"""超参数优化服务。"""

class HPORunner:
    """基于axon_quant.hpo的超参数优化。"""

    def __init__(self):
        from axon_quant_sdk.hpo import HPOEngine
        self._engine = HPOEngine()

    def optimize(
        self,
        strategy_name: str,
        param_space: dict,
        data: pd.DataFrame,
        n_trials: int = 100,
        objective: str = "sharpe",
    ) -> dict:
        """执行超参数优化。"""
        results = self._engine.optimize(
            objective_fn=self._build_objective(strategy_name, data, objective),
            param_space=param_space,
            n_trials=n_trials,
        )
        return {
            "best_params": results.best_params,
            "best_value": results.best_value,
            "all_trials": results.trials,
        }
```

### 3.3 实盘交易 → WorkerService

```
backend/worker/
├── service.py               # 重构: 使用axon_quant exchange adapters
├── axon_worker_system.py    # 重构: 增强RL推理能力
├── rl_worker.py             # 新增: RL策略推理worker
├── risk_monitor.py          # 新增: 实时风控 (axon_quant.risk)
├── ensemble_worker.py       # 新增: 集成模型投票worker
├── models.py                # 保留
├── routes.py                # 更新
└── schemas.py               # 更新: 增加RL/集成worker类型
```

**关键变更:**
- `AxonTradingSystem` 增强RL推理管线
- 实时风控监控通过 `axon_quant.risk.RiskEngine`
- 集成投票通过 `axon_quant.ensemble.EnsembleManager`
- OMS集成通过 `axon_quant.oms.OrderManager`

```python
# backend/worker/risk_monitor.py
"""实时风控监控服务。"""

class RiskMonitor:
    """基于axon_quant.risk的实时风控。"""

    def __init__(self, config: dict):
        from axon_quant_sdk.risk import RiskManager
        self._risk = RiskManager(config)
        self._alerts: list[dict] = []

    def check_order(self, order: dict, portfolio: dict) -> bool:
        """预交易风控检查。"""
        passed, reason = self._risk.check_order(order, portfolio)
        if not passed:
            self._alerts.append({
                "type": "order_rejected",
                "order": order,
                "reason": reason,
                "timestamp": datetime.now(),
            })
        return passed

    def get_portfolio_risk(self, portfolio: dict) -> dict:
        """获取组合风险指标。"""
        return self._risk.get_portfolio_risk(portfolio)

# backend/worker/ensemble_worker.py
"""集成模型投票worker。"""

class EnsembleWorker:
    """基于axon_quant.ensemble的集成策略执行。"""

    def __init__(self, model_paths: list[str], strategy: str = "soft_vote"):
        from axon_quant_sdk.ensemble import EnsembleManager, SoftVoteStrategy
        strategy_map = {
            "hard_vote": HardVoteStrategy,
            "soft_vote": SoftVoteStrategy,
            "weighted": WeightedVoteStrategy,
        }
        self._manager = EnsembleManager(strategy_map[strategy]())
        for path in model_paths:
            self._manager.register_model(path)

    def predict(self, observation: dict) -> dict:
        """集成投票预测。"""
        return self._manager.predict(observation)
```

### 3.4 数据采集 → DataService

```
backend/collector/
├── services/
│   ├── collection_service.py  # 保留
│   ├── quality_service.py     # 保留
│   └── rl_data_service.py     # 新增: RL环境数据准备
├── rl_dataset.py              # 新增: Gymnasium数据集管理
└── routes.py                  # 更新: 增加 /data/rl-datasets
```

### 3.5 模型管理 → ModelRegistryService

```
backend/model/
├── service.py               # 重构: 集成axon_quant.registry
├── registry.py              # 新增: 封装axon_quant.registry.ModelRegistry
├── routes.py                # 更新: 增加 /models/register, /models/compare
└── saved_models/            # 保留: 本地模型存储
```

```python
# backend/model/registry.py
"""模型注册表服务。"""

class ModelRegistryService:
    """基于axon_quant.registry的模型管理。"""

    def __init__(self):
        from axon_quant_sdk.registry import ModelRegistry
        self._registry = ModelRegistry()

    async def register_model(
        self,
        name: str,
        model_path: str,
        metadata: dict,
        metrics: dict,
    ) -> str:
        """注册模型到注册表。"""
        model_id = await self._registry.register(
            name=name,
            path=model_path,
            metadata=metadata,
            metrics=metrics,
        )
        return model_id

    async def compare_models(self, model_ids: list[str]) -> dict:
        """比较多个模型的性能。"""
        models = [await self._registry.get(mid) for mid in model_ids]
        return self._build_comparison(models)
```

---

## 4. AI Agent分层架构

### 4.1 双层架构详解

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户消息                                       │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Interaction Agent (QuantCell 交互层)                │
│                                                                 │
│  职责:                                                          │
│  - NLU: 解析用户意图 (策略/回测/数据/RL/通用)                    │
│  - 上下文: 维护对话记忆、用户偏好                                │
│  - 工具编排: 调用QuantCell业务服务                               │
│  - 技能管理: 加载领域特定技能                                    │
│  - 响应格式化: 为前端渲染结果                                    │
│                                                                 │
│  工具集:                                                        │
│  - create_strategy / edit_strategy / list_strategies            │
│  - run_backtest / compare_backtests / analyze_results           │
│  - start_worker / stop_worker / monitor_worker                  │
│  - collect_data / check_data_quality                            │
│  - train_rl_model / run_hpo / validate_walk_forward             │
│  - register_model / compare_models / deploy_model               │
│  - query_risk / adjust_risk_limits                              │
└────────────────────────┬────────────────────────────────────────┘
                         │ 委托 (交易决策)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Decision Agent (axon_quant 引擎层)                  │
│                                                                 │
│  职责:                                                          │
│  - ReAct交易循环: 市场分析 → 信号 → 风控 → 执行                 │
│  - RL推理: 实时策略决策                                         │
│  - 风控管理: 预交易风控检查                                      │
│  - 集成投票: 多模型共识                                         │
│                                                                 │
│  底层能力:                                                      │
│  - axon_quant.llm (chat + tool calling)                        │
│  - axon_quant.trading (PlaceOrderTool, QueryPortfolio等)        │
│  - axon_quant.inference (ONNX/Candle模型推理)                   │
│  - axon_quant.risk (RiskEngine预交易检查)                       │
│  - axon_quant.ensemble (EnsembleManager投票)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 接口定义

```python
# backend/agent/core/interaction_agent.py
"""QuantCell交互层Agent。"""

class InteractionAgent:
    """用户交互Agent，负责NLU、工具编排、响应格式化。"""

    def __init__(self, llm_provider, services: "ServiceRegistry"):
        self.llm = llm_provider
        self.services = services
        self._decision_agent: DecisionAgent | None = None

    async def process(self, message: str, session: Session) -> AgentResponse:
        """处理用户消息。"""
        # 1. 意图解析
        intent = await self._parse_intent(message, session)

        # 2. 路由到相应处理器
        match intent.category:
            case "trading_decision":
                return await self._delegate_to_decision(intent, session)
            case "backtest":
                return await self._handle_backtest(intent, session)
            case "rl_training":
                return await self._handle_rl(intent, session)
            case "strategy_generation":
                return await self._handle_strategy_gen(intent, session)
            case _:
                return await self._handle_general(message, session)

    async def _delegate_to_decision(self, intent: Intent, session: Session) -> AgentResponse:
        """委托交易决策给Decision Agent。"""
        if self._decision_agent is None:
            self._decision_agent = DecisionAgent(self.services)
        return await self._decision_agent.execute(intent, session)

    async def _parse_intent(self, message: str, session: Session) -> Intent:
        """使用LLM解析用户意图。"""
        ...

    async def _handle_backtest(self, intent: Intent, session: Session) -> AgentResponse:
        """处理回测相关请求。"""
        ...

    async def _handle_rl(self, intent: Intent, session: Session) -> AgentResponse:
        """处理RL训练相关请求。"""
        ...

    async def _handle_strategy_gen(self, intent: Intent, session: Session) -> AgentResponse:
        """处理策略生成请求。"""
        ...

# backend/agent/core/decision_agent.py
"""axon_quant驱动的交易决策Agent。"""

class DecisionAgent:
    """底层交易决策引擎，基于axon_quant的ReAct循环。"""

    def __init__(self, services: "ServiceRegistry"):
        from axon_quant_sdk.llm import TradingLLMAgent
        from axon_quant_sdk.trading import PlaceOrderTool, QueryPortfolioTool, CancelOrderTool
        from axon_quant_sdk.risk import RiskManager

        self.services = services
        self.risk_manager = RiskManager()
        self.agent = TradingLLMAgent(
            tools=[
                PlaceOrderTool(),
                QueryPortfolioTool(),
                CancelOrderTool(),
            ],
            risk_engine=self.risk_manager._engine,
        )

    async def execute(self, intent: Intent, session: Session) -> AgentResponse:
        """执行ReAct交易循环。"""
        result = await self.agent.run(
            prompt=intent.resolved_prompt,
            context=session.market_context,
            max_iterations=10,
        )
        return AgentResponse.from_react_result(result)
```

### 4.3 会话管理与记忆

```python
# backend/agent/core/memory.py
"""Agent记忆系统 — 增强版。"""

class AgentMemory:
    """双层Agent共享记忆系统。"""

    def __init__(self, workspace: Path):
        self.short_term = ConversationMemory(window=100)  # 短期: 对话历史
        self.long_term = PersistentMemory(workspace)       # 长期: 持久化存储
        self.market = MarketContext()                       # 市场: 实时市场数据

    def build_context(self, session: Session) -> dict:
        """构建Agent上下文。"""
        return {
            "conversation": self.short_term.get(session.key),
            "knowledge": self.long_term.search(session.key),
            "market": self.market.current(),
            "user_prefs": self.long_term.get_user_prefs(session.user_id),
        }
```

### 4.4 技能系统

```
backend/agent/skills/
├── builtin/
│   ├── strategy_generation.py   # AI策略代码生成
│   ├── backtest_analysis.py     # 回测结果解读
│   ├── risk_assessment.py       # 风险分析与建议
│   ├── market_analysis.py       # 市场数据分析
│   ├── rl_training.py           # RL训练指导
│   └── portfolio_review.py      # 组合审查
├── loader.py                    # 动态技能加载
└── registry.py                  # 技能注册表
```

---

## 5. RL训练管线集成

### 5.1 完整管线流程

```
┌──────────────────────────────────────────────────────────────────┐
│                    RL训练管线                                      │
│                                                                  │
│  Step 1: 数据准备                                                │
│  ┌─────────────────┐    ┌──────────────────┐                     │
│  │ DataService      │───▶│ RL Dataset Builder│                    │
│  │ (collector/)     │    │ (Gymnasium格式)   │                    │
│  └─────────────────┘    └────────┬─────────┘                     │
│                                  ▼                               │
│  Step 2: 环境创建                                                │
│  ┌─────────────────────────────────────────┐                     │
│  │ axon_quant.rl.TradingEnv               │                     │
│  │ - 特征: OHLCV + 技术指标               │                     │
│  │ - 动作: Buy/Hold/Sell (连续)            │                     │
│  │ - 奖励: 风险调整收益                    │                     │
│  └────────────────┬────────────────────────┘                     │
│                   ▼                                              │
│  Step 3: 训练 (3种模式)                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐         │
│  │ 单GPU训练     │ │ 分布式训练   │ │ Walk-Forward验证 │         │
│  │ axon_quant.rl │ │ axon_quant.  │ │ axon_quant.      │         │
│  │ .PPO/.SAC     │ │ distributed  │ │ walk_forward     │         │
│  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘         │
│         └────────────────┼──────────────────┘                    │
│                          ▼                                       │
│  Step 4: 超参数优化                                              │
│  ┌─────────────────────────────────────────┐                     │
│  │ axon_quant.hpo (Optuna)                │                     │
│  │ - 目标: Sharpe ratio / Calmar / 自定义  │                     │
│  │ - 搜索: 贝叶斯优化 + TPE               │                     │
│  └────────────────┬────────────────────────┘                     │
│                   ▼                                              │
│  Step 5: 模型注册                                                │
│  ┌─────────────────────────────────────────┐                     │
│  │ axon_quant.registry.ModelRegistry      │                     │
│  │ - 版本管理                              │                     │
│  │ - 指标记录                              │                     │
│  │ - 模型签名                              │                     │
│  └────────────────┬────────────────────────┘                     │
│                   ▼                                              │
│  Step 6: 部署                                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐         │
│  │ 推理部署      │ │ 集成部署     │ │ A/B测试           │         │
│  │ axon_quant.   │ │ axon_quant.  │ │ axon_quant.       │         │
│  │ inference     │ │ ensemble     │ │ compliance        │         │
│  └──────────────┘ └──────────────┘ └──────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 关键服务实现

```python
# backend/services/rl_service.py
"""RL训练管线服务 — 统一入口。"""

class RLService:
    """RL训练管线的统一服务层。"""

    def __init__(self):
        from axon_quant_sdk.rl import RLEnvironmentFactory, RLTrainer
        from axon_quant_sdk.hpo import HPORunner
        from axon_quant_sdk.walk_forward import WalkForwardService
        from axon_quant_sdk.registry import ModelRegistryService
        from axon_quant_sdk.distributed import DistributedTrainer
        from axon_quant_sdk.tracker import ExperimentTracker

        self.env_factory = RLEnvironmentFactory()
        self.trainer = RLTrainer()
        self.hpo = HPORunner()
        self.wf = WalkForwardService()
        self.registry = ModelRegistryService()
        self.distributed = DistributedTrainer()
        self.tracker = ExperimentTracker()

    async def train(
        self,
        config: RLTrainConfig,
    ) -> RLTrainResult:
        """执行完整RL训练管线。"""
        # 1. 创建环境
        env = self.env_factory.create_env(
            data=config.data,
            features=config.features,
            reward_type=config.reward_type,
        )

        # 2. 训练
        if config.distributed:
            model = await self.distributed.train(
                env=env,
                algorithm=config.algorithm,
                config=config.distributed_config,
            )
        else:
            model = await self.trainer.train(
                env=env,
                algorithm=config.algorithm,
                total_timesteps=config.total_timesteps,
            )

        # 3. Walk-Forward验证
        if config.walk_forward:
            wf_results = await self.wf.validate(
                strategy_fn=model.predict,
                data=config.data,
                n_splits=config.wf_splits,
            )
        else:
            wf_results = None

        # 4. 注册模型
        model_id = await self.registry.register_model(
            name=config.model_name,
            model_path=model.path,
            metadata={
                "algorithm": config.algorithm,
                "features": config.features,
                "train_timesteps": config.total_timesteps,
            },
            metrics=wf_results.metrics if wf_results else model.metrics,
        )

        return RLTrainResult(
            model_id=model_id,
            metrics=model.metrics,
            walk_forward=wf_results,
        )

    async def optimize_hyperparameters(
        self,
        config: HPOConfig,
    ) -> HPOResult:
        """执行超参数优化。"""
        return await self.hpo.optimize(
            strategy_name=config.strategy_name,
            param_space=config.param_space,
            data=config.data,
            n_trials=config.n_trials,
            objective=config.objective,
        )

    async def compare_models(self, model_ids: list[str]) -> dict:
        """比较多个模型。"""
        return await self.registry.compare_models(model_ids)
```

### 5.3 API端点

```python
# backend/api/v2/rl_routes.py
"""RL训练API端点。"""

router = APIRouter(prefix="/api/v2/rl", tags=["RL Training"])

@router.post("/train")
async def train_rl_model(config: RLTrainConfig, db: Session = Depends(get_db)):
    """启动RL训练任务。"""
    service = RLService()
    task_id = await service.train(config)
    return {"task_id": task_id, "status": "started"}

@router.post("/hpo")
async def run_hpo(config: HPOConfig, db: Session = Depends(get_db)):
    """执行超参数优化。"""
    service = RLService()
    result = await service.optimize_hyperparameters(config)
    return result

@router.post("/walk-forward")
async def run_walk_forward(config: WalkForwardConfig):
    """执行Walk-Forward验证。"""
    service = RLService()
    result = await service.wf.validate(**config.dict())
    return result

@router.get("/models")
async def list_rl_models():
    """列出所有RL模型。"""
    service = RLService()
    return await service.registry.list_models()

@router.post("/models/compare")
async def compare_models(model_ids: list[str]):
    """比较模型性能。"""
    service = RLService()
    return await service.compare_models(model_ids)

@router.post("/deploy/{model_id}")
async def deploy_model(model_id: str, config: DeployConfig):
    """部署模型到实盘。"""
    service = RLService()
    return await service.deploy(model_id, config)
```

---

## 6. 前端交互设计

### 6.1 混合模式分工

```
┌─────────────────────────────────────────────────────────────────┐
│                    前端交互模式                                   │
│                                                                 │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐  │
│  │ 传统UI (70%)         │  │ AI对话 (30%)                     │  │
│  │                     │  │                                  │  │
│  │ - 策略列表/编辑      │  │ - "帮我写一个MACD策略"            │  │
│  │ - 回测配置/结果      │  │ - "分析这个回测结果的风险"        │  │
│  │ - Worker监控面板     │  │ - "用PPO训练一个BTC交易策略"      │  │
│  │ - 数据管理/质量      │  │ - "比较这3个模型的表现"           │  │
│  │ - 设置/配置         │  │ - "调整风控参数到更保守"           │  │
│  │ - 图表/K线          │  │ - "今天的市场情况怎么样"           │  │
│  │ - 因子分析          │  │ - "帮我排查Worker为什么停了"       │  │
│  └─────────────────────┘  └──────────────────────────────────┘  │
│                                                                 │
│  触发AI对话的场景:                                               │
│  1. 用户在任何页面点击AI助手按钮                                 │
│  2. 用户在Agent页面直接对话                                      │
│  3. 复杂操作的确认和解释                                         │
│  4. 错误诊断和建议                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 页面结构

```
frontend/src/pages/
├── agent/                    # AI对话页面 (保留，增强)
│   ├── Agent.tsx             # 主对话界面
│   ├── AgentPanel.tsx        # 侧边栏AI面板 (可在任何页面打开)
│   └── store/
│       └── agentStore.ts     # Agent状态管理
├── backtest/                 # 回测模块 (增强)
│   ├── BacktestConfig.tsx    # 回测配置 (传统UI)
│   ├── BacktestDetail.tsx    # 回测详情 (传统UI + AI分析按钮)
│   ├── WalkForwardPage.tsx   # Walk-Forward验证页面 (新增)
│   └── HPOPage.tsx           # 超参数优化页面 (新增)
├── strategy/                 # 策略管理 (增强)
│   ├── StrategyManagement.tsx # 策略列表 (传统UI)
│   ├── StrategyEditor.tsx    # 策略编辑器 (传统UI + AI辅助)
│   └── RLStrategyPage.tsx    # RL策略管理 (新增)
├── model/                    # 模型管理 (增强)
│   ├── ModelManagement.tsx   # 模型列表 (传统UI)
│   ├── ModelCompare.tsx      # 模型比较 (新增)
│   └── ModelDeploy.tsx       # 模型部署 (新增)
├── rl/                       # RL训练模块 (新增)
│   ├── RLTrainingPage.tsx    # RL训练配置和监控
│   ├── RLMonitor.tsx         # 训练进度监控
│   └── RLResults.tsx         # 训练结果展示
├── worker/                   # Worker管理 (增强)
│   ├── Worker.tsx            # Worker列表 (传统UI)
│   └── WorkerDetail.tsx      # Worker详情 (传统UI + AI诊断)
├── data/                     # 数据管理 (保留)
├── chart/                    # 图表 (保留)
├── factor/                   # 因子分析 (保留)
├── setting/                  # 设置 (保留)
└── login/                    # 登录 (保留)
```

### 6.3 AI对话界面增强

```typescript
// frontend/src/components/AgentPanel.tsx
// 全局AI面板 — 可在任何页面侧边打开

interface AgentPanelProps {
  visible: boolean;
  onClose: () => void;
  context?: {
    page: string;        // 当前页面
    selectedItem?: any;  // 选中的项目
    error?: string;      // 当前错误
  };
}

// 使用方式:
// 1. 在任何页面按 Cmd+K 打开AI面板
// 2. AI自动获取当前页面上下文
// 3. 用户可以直接用自然语言操作当前页面的功能
```

### 6.4 新增RL训练页面

```typescript
// frontend/src/pages/rl/RLTrainingPage.tsx
// RL训练配置和监控页面

interface RLTrainConfig {
  algorithm: "ppo" | "sac" | "dqn";
  data_source: string;
  features: string[];
  reward_type: "sharpe" | "calmar" | "sortino" | "custom";
  total_timesteps: number;
  distributed: boolean;
  walk_forward: boolean;
  hpo: boolean;
  hpo_trials?: number;
}

// 页面结构:
// 1. 训练配置表单 (传统UI)
// 2. 训练进度监控 (实时图表)
// 3. 训练结果展示 (指标、图表)
// 4. AI辅助 (自然语言调参、结果解读)
```

---

## 7. 数据流设计

### 7.1 完整数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                    数据流全景                                        │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 外部数据  │───▶│ 数据采集  │───▶│ 数据存储  │───▶│ 数据质量  │      │
│  │ 交易所API │    │ collector │    │ DuckDB   │    │ quality   │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│                                                     │               │
│                                                     ▼               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    数据消费层                                  │   │
│  │                                                              │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │   │
│  │  │ 回测引擎  │  │ RL训练   │  │ 实盘Worker│  │ 因子分析  │    │   │
│  │  │ backtest  │  │ rl       │  │ worker   │  │ factor   │    │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┘    │   │
│  │       │              │              │                         │   │
│  │       ▼              ▼              ▼                         │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │   │
│  │  │ 回测结果  │  │ RL模型   │  │ 交易信号  │                   │   │
│  │  │ (RunResult)│ │ (Policy) │  │ (Orders) │                   │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │   │
│  │       │              │              │                         │   │
│  │       ▼              ▼              ▼                         │   │
│  │  ┌──────────────────────────────────────────────────────┐    │   │
│  │  │              结果分析层                                │    │   │
│  │  │  SHAP解释  反事实分析  风险指标  性能归因              │    │   │
│  │  └──────────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    AI Agent层                                 │   │
│  │  用户: "帮我分析BTC最近的走势"                                │   │
│  │  → Interaction Agent → DataService → 市场分析 → 响应         │   │
│  │                                                              │   │
│  │  用户: "用PPO训练一个ETH策略"                                 │   │
│  │  → Interaction Agent → RLService → 训练监控 → 结果           │   │
│  │                                                              │   │
│  │  用户: "现在买入1个BTC"                                       │   │
│  │  → Interaction Agent → Decision Agent → ReAct循环 → 执行     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 关键数据流详解

**数据采集 → RL训练:**
```
交易所API → collector → DuckDB(原始K线)
    → rl_data_service.py (特征工程)
    → axon_quant.rl.TradingEnv (Gymnasium环境)
    → axon_quant.rl.PPO/SAC (训练)
    → axon_quant.registry (模型注册)
```

**RL模型 → 实盘推理:**
```
ModelRegistry → InferenceEngine (ONNX加载)
    → TradingEnv.reset() (获取observation)
    → model.predict(observation) (RL推理)
    → RiskEngine.check_order() (风控检查)
    → OrderManager.submit() (OMS提交)
    → ExchangeAdapter.place_order() (交易所下单)
```

**AI Agent → 交易执行:**
```
用户消息 → Interaction Agent (NLU解析)
    → 意图: "trading_decision"
    → Decision Agent (axon_quant LLM)
    → ReAct循环:
        🧠 REASON: 分析市场数据
        ⚡ ACTION: QueryPortfolioTool
        👁️ OBSERVATION: 当前持仓
        🧠 REASON: 决定买入
        ⚡ ACTION: PlaceOrderTool(Buy BTC 0.1)
        👁️ OBSERVATION: 订单已提交
    → 返回交易结果
```

---

## 8. 重构路线图

### Phase 1: 基础层 (Week 1-2)
**目标: axon_quant SDK封装 + 类型统一**

| 任务 | 产出 | 依赖 |
|------|------|------|
| 创建 `axon_quant_sdk/` 包 | 16个模块封装 | axon-quant>=0.1.3 |
| 统一类型系统 | types.py + axond整合 | Phase 1 |
| 配置桥接层 | QuantCell config → axon_quant config | Phase 1 |
| 测试基础 | axon_quant_sdk单元测试 | Phase 1 |

**验收标准:** `from axon_quant_sdk.backtest import BacktestService` 可用

### Phase 2: 回测增强 (Week 3-4)
**目标: 回测系统集成axon_quant能力**

| 任务 | 产出 | 依赖 |
|------|------|------|
| axon_quant BacktestEngine适配 | axon_engine.py | Phase 1 |
| Walk-Forward验证集成 | walk_forward.py | Phase 1 |
| HPO超参数优化集成 | hpo_runner.py | Phase 1 |
| 结果分析增强 (SHAP) | result_analyzer.py | Phase 1 |
| 前端Walk-Forward/HPO页面 | WalkForwardPage.tsx, HPOPage.tsx | Phase 2 |

**验收标准:** 可通过Web界面配置并运行Walk-Forward验证

### Phase 3: RL训练管线 (Week 5-7)
**目标: 完整RL训练能力**

| 任务 | 产出 | 依赖 |
|------|------|------|
| RL环境工厂 | rl.py: RLEnvironmentFactory | Phase 1 |
| RL训练器 (PPO/SAC/DQN) | rl.py: RLTrainer | Phase 1 |
| 分布式训练集成 | distributed.py | Phase 1 |
| 实验追踪集成 | tracker.py | Phase 1 |
| 模型注册表集成 | registry.py | Phase 1 |
| RL Service层 | services/rl_service.py | Phase 3 |
| RL API端点 | api/v2/rl_routes.py | Phase 3 |
| 前端RL训练页面 | pages/rl/RLTrainingPage.tsx | Phase 3 |

**验收标准:** 可通过Web界面启动RL训练、查看进度、比较模型

### Phase 4: Agent双层架构 (Week 8-10)
**目标: AI Agent分层架构**

| 任务 | 产出 | 依赖 |
|------|------|------|
| Interaction Agent重构 | agent/core/interaction_agent.py | Phase 1 |
| Decision Agent实现 | agent/core/decision_agent.py | Phase 1 |
| 风控集成 | risk.py: RiskManager | Phase 1 |
| 交易工具集成 | trading.py: PlaceOrderTool等 | Phase 1 |
| 技能系统增强 | skills/builtin/*.py | Phase 4 |
| Agent记忆增强 | memory.py | Phase 4 |
| 前端Agent面板增强 | AgentPanel.tsx | Phase 4 |

**验收标准:** 用户可通过AI对话完成策略生成→回测→部署的完整流程

### Phase 5: 实盘增强 (Week 11-12)
**目标: 实盘Worker集成RL/集成/风控**

| 任务 | 产出 | 依赖 |
|------|------|------|
| RL推理Worker | rl_worker.py | Phase 3 |
| 集成投票Worker | ensemble_worker.py | Phase 1 |
| 实时风控监控 | risk_monitor.py | Phase 1 |
| OMS集成 | oms.py | Phase 1 |
| 模型部署服务 | model/deploy.py | Phase 3 |
| 前端模型管理增强 | ModelCompare.tsx, ModelDeploy.tsx | Phase 5 |

**验收标准:** 可部署RL模型到实盘，实时风控生效

### Phase 6: 前端AI化 (Week 13-14)
**目标: 前端混合交互模式完善**

| 任务 | 产出 | 依赖 |
|------|------|------|
| 全局AI面板 (Cmd+K) | AgentPanel.tsx | Phase 4 |
| 页面上下文注入 | context injection | Phase 6 |
| AI辅助回测分析 | BacktestDetail.tsx增强 | Phase 6 |
| AI辅助策略编辑 | StrategyEditor.tsx增强 | Phase 6 |
| AI辅助Worker诊断 | WorkerDetail.tsx增强 | Phase 6 |
| 端到端测试 | E2E tests | Phase 6 |

**验收标准:** 用户可在任何页面通过AI面板完成操作

---

## 9. 文件结构总览

```
QuantCell/
├── backend/
│   ├── axon_quant_sdk/           # 新增: axon_quant集成层 (16个模块)
│   ├── agent/                    # 重构: 双层Agent架构
│   │   ├── core/
│   │   │   ├── interaction_agent.py  # 重构
│   │   │   ├── decision_agent.py     # 新增
│   │   │   ├── loop.py               # 保留
│   │   │   ├── memory.py             # 增强
│   │   │   └── factory.py            # 重构
│   │   ├── tools/
│   │   │   ├── trading/              # 重构: 集成axon_quant.trading
│   │   │   ├── rl_tools.py           # 新增: RL相关工具
│   │   │   └── risk_tools.py         # 新增: 风控相关工具
│   │   └── skills/
│   │       └── builtin/              # 增强: 新增RL/风控技能
│   ├── strategy/
│   │   ├── rl_strategy.py            # 新增
│   │   └── core/                     # 保留
│   ├── backtest/
│   │   ├── engines/
│   │   │   ├── axon_engine.py        # 新增
│   │   │   └── vector_engine.py      # 保留
│   │   ├── walk_forward.py           # 新增
│   │   ├── hpo_runner.py             # 新增
│   │   └── result_analyzer.py        # 新增
│   ├── worker/
│   │   ├── rl_worker.py              # 新增
│   │   ├── risk_monitor.py           # 新增
│   │   └── ensemble_worker.py        # 新增
│   ├── model/
│   │   ├── registry.py               # 新增
│   │   └── deploy.py                 # 新增
│   ├── services/
│   │   └── rl_service.py             # 新增
│   ├── api/
│   │   └── v2/
│   │       └── rl_routes.py          # 新增
│   └── collector/
│       └── rl_dataset.py             # 新增
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── agent/
│       │   │   └── AgentPanel.tsx     # 新增: 全局AI面板
│       │   ├── backtest/
│       │   │   ├── WalkForwardPage.tsx # 新增
│       │   │   └── HPOPage.tsx        # 新增
│       │   ├── rl/                    # 新增: RL训练模块
│       │   │   ├── RLTrainingPage.tsx
│       │   │   ├── RLMonitor.tsx
│       │   │   └── RLResults.tsx
│       │   ├── model/
│       │   │   ├── ModelCompare.tsx   # 新增
│       │   │   └── ModelDeploy.tsx    # 新增
│       │   └── strategy/
│       │       └── RLStrategyPage.tsx # 新增
│       ├── api/
│       │   ├── rlApi.ts              # 新增
│       │   └── modelApi.ts           # 新增
│       └── components/
│           └── AgentPanel.tsx        # 新增: 可复用AI面板组件
│
└── docs/
    └── plans/
        └── 2026-06-23-ai-native-refactoring-design.md  # 本文档
```

---

## 10. 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| RL训练算法 | PPO/SAC/DQN (axon_quant内置) | 覆盖离散/连续动作空间 |
| HPO框架 | Optuna (axon_quant.hpo封装) | 成熟、Python友好 |
| 模型格式 | ONNX (axon_quant.inference) | 跨平台、高性能 |
| 集成策略 | Hard/Soft/Weighted Vote | axon_quant.ensemble原生支持 |
| Agent LLM | OpenAI兼容 (可配置) | 灵活切换模型提供商 |
| 前端AI组件 | Ant Design X | 项目已使用Ant Design生态 |
| 实时通信 | SSE (Agent) + WebSocket (Worker) | SSE适合流式AI响应 |
| 风控引擎 | axon_quant.risk (同步热路径) | 12ns延迟，无tokio依赖 |
