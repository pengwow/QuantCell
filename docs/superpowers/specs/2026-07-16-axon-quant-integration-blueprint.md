# axon_quant 集成蓝图(QuantCell v2.0)

**Date:** 2026-07-16
**Status:** Design — Pending user review
**Owner:** QuantCell Core Team
**Target Release:** v2.0.0

---

## 1. 背景与目标

### 1.1 背景

QuantCell 当前作为 Python + FastAPI 的量化交易平台,核心问题:

1. **回测方向错误** — 现有 `backtest/engines/engine.py:VectorEngine` 是纯 Python 向量化回测,设计方向错误,无法真实模拟撮合、滑点、撮合优先级等微观结构,应**完全摒弃向量化回测**;QuantCell 应**只走事件驱动回测(axon_quant.backtest)**,axon_quant 自身就提供 L1/L2/L3 三档撮合引擎
2. **axon_quant 集成方式错误** — 当前把 [`/Users/liupeng/workspace/quant/axon`](file:///Users/liupeng/workspace/quant/axon) 仓库源码作为依赖(本地 maturin build),**应改为 PyPI 安装**:`pip install axon-quant==0.2.0`;源码只作参考,绝不直接 import 源码路径
3. **缺乏 AI 原生能力** — 现有 `rl_service.py` 仅 1 个简单的 GymnasiumWrapper,无 RL/HPO/LLM/可解释性/集成的完整链路
4. **多 Agent 协作缺失** — 现有 `agent_cli.py` 走 `ProcessDirect` 模式,无多 Agent 拓扑、无 vote、无 trace
5. **无统一 CLI 入口** — 12 个分散 `scripts/*_cli.py` 难记忆,无 bash/zsh 自动补全
6. **风控/合规/可解释/治理能力薄弱** — 缺乏 RBAC、SHAP 解释、合规报告

### 1.2 目标

将 [axon_quant](file:///Users/liupeng/workspace/quant/axon_quant) 作为**底层量化交易引擎**,QuantCell 作为**上层应用**,具体目标:

1. **axon_quant 全能力集成** — 23 个 crate 全部映射,清晰归属
2. **AI 原生能力完整闭环** — RL 训练 → Registry → Walk-Forward → Inference → Ensemble → Explain
3. **多 Agent 协作** — 6 个预制 Agent(Data/Strategy/Risk/Execution/Report/Audit)模板 + DAG 编排
4. **统一 CLI 入口** — `quantcell` 命令覆盖全部功能(回测/训练/部署/Agent/Web),支持无界面启动
5. **架构隔离清晰** — 4 层架构,axon_quant 通过 PyPI 包消费(零源码依赖)
6. **回测纯事件驱动** — QuantCell 自身**不实现任何回测逻辑**,完全委托 axon_quant.backtest(事件驱动 + L1/L2/L3 撮合),**所有向量化回测代码全量删除**

### 1.3 非目标

- **不集成 axon-defi**(DeFi/Uniswap/桥/MEV) — 量化对冲基金场景以 CEX 为主,v3+ 评估
- **不重写 axon_cli** — 库内 CLI 是给运维/Axon 团队用,QuantCell 用户走 Web + 自家 CLI
- **不重写 axon-core** — 纯 Rust 内部基础库,通过其他 crate 间接使用
- **不实现向量化回测** — QuantCell 自身不写任何回测逻辑(不保留任何 VectorEngine / NumPy 向量化回测代码),回测 100% 走 axon_quant 事件驱动
- **不加载 axon_quant 源码** — 全部依赖 `pip install axon-quant==X.Y.Z` 安装的 PyPI 包,**不** `import sys.path.insert(0, "/path/to/axon/python")` 加载本地源码;`/Users/liupeng/workspace/quant/axon` 仓库仅作参考文档,绝不在 QuantCell 运行时使用

---

## 2. 整体架构

### 2.1 4 层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│ ① 前端呈现层 (Bun + React)                                           │
│   非程序员: 预设策略模板(6-8 个) + 表单配置                          │
│   研究员:   Python 策略上传 / Web IDE / Jupyter 接入                │
│   公共:     实时仪表盘 / 风险监控 / 回测报告 / 可解释报告             │
│   AI 专属:  Agent 对话面板 / RL 训练可视化 / SHAP 解释视图           │
│   Agent:    协作流可视化(谁调谁 / 消息时序 / 投票过程)               │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP / WebSocket / SSE
┌─────────────────────────▼───────────────────────────────────────────┐
│ ② QuantCell 应用层 (FastAPI + Python + CLI)                          │
│                                                                       │
│  ②a Agent 协作编排 (核心差异化能力)                                   │
│      - workflow_designer:  Agent DAG 设计与存储                       │
│      - agent_registry:     Agent 版本/凭证/路由表                     │
│      - chat_runtime:       LLM ↔ 工具 ↔ 用户 的实时会话              │
│      - trace_collector:    Agent 消息时序/工具调用/票数落库           │
│                                                                       │
│  ②b 编排引擎:     工作流串联(回测→训练→部署→监控)                   │
│  ②c 服务包装:     services/* — DB 持久化 + 鉴权 + 协议转换            │
│  ②d 稳定 API:     api/v2/ — 前端契约                                  │
│  ②e 资产层:       模板/用户/权限/审计(QuantCell 独占)                │
│  ②f AI 编排:      train_orchestrator / explain_service / tracker_     │
│                   adapter (接 axon-rl/registry/walk-forward/inference)│
│ ②g CLI 入口:     quantcell 命令,无界面启动全功能                    │
│ ②h ★ 反向回测:   **完全不实现回测逻辑**,回测 100% 委托 axon_quant   │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ Python import (无 gRPC / IPC)
┌─────────────────────────▼───────────────────────────────────────────┐
│ ③ axon_quant 适配层 (Python 薄包装)                                   │
│   - 类型转译: Bar/Order/Position 统一为 axon_quant native             │
│   - 异步桥接: tokio::block_on → asyncio.to_thread                    │
│   - 错误规范: axon_quant.*Error → QuantCell HTTPException            │
│   - 顶层重导出: from backend.axon_quant import X 避免深路径           │
│   - Agent 适配: axon_quant.llm.swarm.* 的薄包装,接 ②a 层            │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ PyO3 (CPython ABI)
┌─────────────────────────▼───────────────────────────────────────────┐
│ ④ axon_quant 核心引擎 (Rust) — 23 crate                              │
│                                                                       │
│  交易主线: data / backtest(事件驱动,L1/L2/L3 撮合) / risk / oms / exchange                    │
│  AI 主线:   rl / inference / llm / llm.trading / hpo / registry /    │
│             distributed / ensemble / explain / walk_forward / tracker │
│  治理主线: compliance / monitor / harness / defi / core / python /   │
│           cli                                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 多 Agent 协作拓扑

axon_quant 的 [axon-llm/src/swarm/](file:///Users/liupeng/workspace/quant/QuantCell/backend/.venv/lib/python3.14/site-packages/axon_quant/llm.py) 已有 `agents/{market, risk, audit}_agent.rs` + `orchestrator.rs` + `message.rs` + `vote.rs`,QuantCell 在 ②a 层叠加配置/可观测性:

```
                     ┌────────────────────────┐
                     │  Orchestrator Agent    │
                     │  (axon-llm.swarm.      │
                     │   orchestrator + vote) │
                     │  QuantCell 调度 + UI   │
                     └──────────┬─────────────┘
                                │ message bus
                                │ (axon-llm.message + QuantCell trace)
        ┌────────────┬──────────┼──────────┬─────────────┬────────────┐
        ▼            ▼          ▼          ▼             ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │  Data   │ │Strategy │ │  Risk   │ │Execution│ │ Report  │ │  Audit  │
   │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │
   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │           │           │           │
   ┌────▼────┐ ┌───▼─────┐ ┌───▼─────┐ ┌───▼──────┐ ┌───▼────┐ ┌───▼─────┐
   │axon-data│ │axon-rl  │ │axon-risk│ │axon-oms/ │ │axon-   │ │axon-    │
   │         │ │/inference│ │         │ │exchange  │ │explain │ │complianc│
   │         │ │         │ │         │ │          │ │        │ │    e    │
   └─────────┘ └─────────┘ └─────────┘ └──────────┘ └────────┘ └─────────┘
```

### 2.3 两条 AI 闭环

```
┌────────────── 对内:模型生产闭环 ─────────────────────────────────┐
│                                                                     │
│  训练数据  ──►  RL/HPO 训练  ──►  Registry  ──►  Walk-Forward 验证 │
│  (axon-data)   (axon-rl)        (axon-registry) (axon-walk-forward)│
│                     │                              │               │
│                     └─────── Tracker 记录 ◄────────┘               │
│                     (axon-tracker)                                  │
│                                  │                                  │
│                                  ▼                                  │
│                       Inference 引擎 (axon-inference)               │
│                                  │                                  │
│                                  ▼                                  │
│                       Ensemble(axon-ensemble) ──► Explain ──┐      │
│                                  │                  (SHAP/CF)│      │
└─────────────────────────────────────────────────────────────┼──────┘
                                                             │
┌────────────── 对外:用户交互闭环 ─────────────────────────────┴────┐
│                                                                     │
│  LLM Agent(axon-llm)  ◄── 自然语言 / 工具调用                       │
│       │                                                              │
│       ├──► trading tools(下/撤单/查持仓) — axon-llm.trading          │
│       ├──► explain tools(为什么这只股?) — axon-explain              │
│       ├──► risk tools(能开多大仓?)    — axon-risk via tools          │
│       └──► audit tools(本次操作合规吗?)  — axon-compliance          │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.4 三类 AI 消费场景

| 用户 | AI 能力 | 入口 |
|---|---|---|
| 非程序员 | 6-8 个预训练模板(QuantCell 团队用 axon-rl 训练,axon-registry 管理) | 表单选择"双均线 + RL 仓位管理"即可部署 |
| 量化研究员 | 直接用 RL/HPO/Tracker 训练自定义模型 | Jupyter / Web IDE / `quantcell train` |
| 所有人 | LLM Agent 自然语言驱动 | Chat 面板 / `quantcell agent chat` |

---

## 3. axon_quant 23 crate 映射表

### 3.1 交易主线(5 crate)

| Crate | Rust 现状 | QuantCell 现状 | 归属层 | v2.0 阶段 | Python/Rust 建议 |
|---|---|---|---|---|---|
| **axon-data** | ✅ 已暴露 | ⚠️ `data_service.py`(部分) | ③④ | **P1** | Rust 写,Python 薄包装 |
| **axon-backtest** | ✅ BacktestEngine(事件驱动)+ L1/L2/L3 撮合 | ❌ 现有 `backtest/engines/engine.py:VectorEngine` 是向量化(应**全量删除**),`backtest_service.py` 包装中 | ③④ | **P1** | **事件驱动回测(Rust 写,axon_quant 唯一来源)**;**完全删除所有向量化回测代码**(`backtest/engines/`、`VectorEngine`、任何 NumPy/pandas 向量化回测) |
| **axon-risk** | ✅ `DefaultRiskEngine` | ✅ `risk_service.py` | ③④ | **P1** | Rust 写,QuantCell 补可视化表单/dry-run/审计 |
| **axon-oms** | ✅ OrderManager | ✅ `oms_service.py` | ③④ | **P1** | Rust 写,QuantCell 补 UI 状态机/订单历史落库 |
| **axon-exchange** | ✅ Binance/OKX | ✅ `exchange_service.py` | ③④ | **P1** | Rust 写,QuantCell 补多账号/凭证 vault/健康度 |

### 3.2 AI 主线(11 crate — QuantCell 差异化核心)

| Crate | Rust 现状 | QuantCell 现状 | 归属层 | v2.0 阶段 | Python/Rust 建议 |
|---|---|---|---|---|---|
| **axon-rl** | ✅ TradingEnv + VecEnv | ✅ `rl_service.py` | ③④ | **P2** | Rust 写,QuantCell 补训练队列/SSE 进度/checkpoint 注册 |
| **axon-inference** | ✅ 批推理 + 热更新 | ✅ `inference_service.py` | ③④ | **P2** | Rust 写,QuantCell 补推理路由/延迟监控 |
| **axon-llm** | ✅ LLMBackend + swarm | ⚠️ `llm_service.py`(无 swarm) | ③④ | **P2(★)** | Rust 写,QuantCell 补 swarm 包装/Agent 注册/凭证 vault |
| **axon-llm.trading** | ✅ TradingTools | ❌ 未集成 | ③④ | **P2** | Rust 写,QuantCell:注册到 Agent 白名单,需 Risk 二次确认 |
| **axon-hpo** | ✅ Optuna | ✅ `hpo_service.py` | ③④ | **P2** | Rust 写,QuantCell 补试验队列/最佳 trial 自动注册 |
| **axon-registry** | ✅ ModelRegistry | ✅ `model_registry_service.py` | ③④ | **P2** | Rust 写,QuantCell 补模型血缘/分享/权限 |
| **axon-distributed** | ✅ DistributedRunner | ❌ 未集成 | ③④ | **P3** | Rust 写,仅 K8s 部署时启用 |
| **axon-ensemble** | ✅ 4 种策略 | ✅ `ensemble_service.py` | ③④ | **P2** | Rust 写,QuantCell 补多模型对比回测 UI |
| **axon-explain** | ✅ SHAP + Counterfactual | ✅ `explain_service.py` | ③④ | **P3** | Rust 写,QuantCell 补 SHAP 解释/反事实/PDF 报告 |
| **axon-walk-forward** | ✅ purged CV | ❌ 未集成 | ③④ | **P2** | **强烈建议集成**(防过拟合标准动作) |
| **axon-tracker** | ✅ Local/Memory Tracker | ❌ 未集成 | ③④ | **P2** | Rust 写,QuantCell 补 TrackerAdapter → axond_*.db |

### 3.3 治理主线(5 crate)

| Crate | Rust 现状 | QuantCell 现状 | 归属层 | v2.0 阶段 | Python/Rust 建议 |
|---|---|---|---|---|---|
| **axon-compliance** | ✅ ComplianceModule | ✅ `compliance_service.py` | ③④ | **P3** | Rust 写,QuantCell 补规则配置/审计 UI/监管报告 |
| **axon-monitor** | ✅ Alert/Health/Metrics | ❌ 未集成 | ③④ | **P3** | Rust 写,QuantCell 补 Prometheus 导出/告警/健康仪表盘 |
| **axon-harness** | ✅ Audit + RBAC + 熔断 | ❌ 未集成 | ③④ | **P3** | Rust 写,QuantCell 补 RBAC/操作审计/资金熔断 |
| **axon-defi** | ✅ Uniswap/桥/MEV | ❌ 不集成 | — | **P5 (永不做)** | **跳过** |
| **axon-cli** | ✅ CLI | ❌ 不集成 | — | **P5 (永不做)** | **跳过**(QuantCell 用户走 Web + 自家 CLI) |
| **axon-core** | ✅ 基础类型 | 透传 | ④ | — | **零修改**(底座) |
| **axon-python** | ✅ PyO3 绑定 | — | ④ | — | **零修改**(Axon 团队维护) |

### 3.4 QuantCell 独占能力(axon_quant 没有,QuantCell 必须自己实现)

| 能力 | 实现层 | 说明 |
|---|---|---|
| **6-8 个预设策略模板** | ② Python | DualMA / Grid / MeanReversion / TrendFollow / 套利 / 截面多因子 / RL 仓位管理 / 动量反转 |
| **多 Agent DAG 编辑器** | ② + ① 前端 | 拖拽式 Agent 编排,生成 JSON DAG 配置 |
| **LLM 凭证 vault** | ② Python | 集中存 OpenAI/Anthropic API key,所有 Agent 共享 |
| **消息时序 trace** | ② + ③ 包装 | 每次多 Agent 协作的 message/vote/tool_call 落 `axond_agent_trace` 表 |
| **模型血缘/版本管理** | ② + ③ 包装 | 训练任务 → 模型 → 回测 → 部署 全链追溯 |
| **工作流编排引擎** | ② Python | 回测→训练→部署→监控 的可视化流程 |
| **用户/权限/RBAC** | ② + ③ axon-harness | QuantCell 写应用层,axon-harness 提供底层审计 |
| **审计与日志(应用层)** | ② Python | `axond_audit_log` 表,记录所有用户操作 |
| **报告导出** | ② + ③ 包装 | 回测/SHAP/合规 → PDF/Excel |
| **统一 CLI 入口 `quantcell`** | ② Python | 无界面启动全功能 |

---

## 4. 适配层(③)设计

### 4.1 目录结构

```
backend/
├── axon_quant/                  ← ③ 适配层
│   ├── __init__.py              ← 顶层重导出
│   ├── _errors.py               ← 统一错误规范
│   ├── _async.py                ← 异步桥接装饰器
│   ├── _credentials.py          ← 凭证管理
│   ├── data/                    ← 包装 axon_quant.data
│   ├── backtest/                ← 包装 axon_quant.backtest
│   ├── risk/                    ← 包装 axon_quant.risk
│   ├── oms/                     ← 包装 axon_quant.oms
│   ├── exchange/                ← 包装 axon_quant.exchange
│   ├── rl/                      ← 包装 axon_quant.rl
│   ├── inference/               ← 包装 axon_quant.inference
│   ├── llm/                     ← 包装 axon_quant.llm + swarm
│   │   ├── __init__.py
│   │   ├── agent.py             ← Agent 包装(强类型 schema)
│   │   ├── swarm.py             ← Orchestrator 包装
│   │   ├── message.py           ← Message/Trace 落库
│   │   └── tools.py             ← LLM Tool 注册
│   ├── registry/                ← 包装 axon_quant.registry
│   ├── hpo/                     ← 包装 axon_quant.hpo
│   ├── ensemble/                ← 包装 axon_quant.ensemble
│   ├── walk_forward/            ← 包装 axon_quant.walk_forward
│   ├── tracker/                 ← 包装 axon_quant.tracker
│   ├── explain/                 ← 包装 axon_quant.explain
│   ├── compliance/              ← 包装 axon_quant.compliance
│   └── monitor/                 ← 包装 axon_quant.monitor
│
└── tests/unit/axon_quant/       ← 适配层测试
```

**关键约束**:
- ② 层 `services/` **只能** `from backend.axon_quant import X`,**不能**直接 `from axon_quant import X`
- ③ 层每个文件 ≤ 200 行,只做转译/包装,不加业务逻辑
- 业务逻辑一律放 ② 层

### 4.2 顶层重导出样板

```python
# backend/axon_quant/__init__.py
"""Axon_quant 适配层 — 顶层重导出,避免散落 import 路径。
所有 QuantCell 业务代码统一 from backend.axon_quant import X。
"""
from axon_quant import (  # noqa: F401
    # data
    DataService, MockSource, Frequency, DataRequest, DataError,
    # backtest
    BacktestEngine, L1MatchingEngine, L2MatchingEngine,
    # risk
    DefaultRiskEngine, CircuitBreaker, RiskConfig,
    # oms
    OrderManager, Order, OrderStatus, OrderType, Side, Portfolio, Position,
    # exchange
    BinanceAdapter, OKXAdapter, ExchangeConfig, ExchangeId,
    # inference
    InferenceEngine, BatchInferencePipeline, ModelFormat,
    # explain
    KernelSHAP, CounterfactualExplanation, ReportGenerator,
    # monitor
    HealthCheck, AlertRule, MetricsRegistry,
)
from axon_quant import (  # noqa: F401
    rl, llm, hpo, registry, ensemble, walk_forward,
    tracker, compliance, explain, distributed, harness,
)
```

### 4.3 异步桥接样板

```python
# backend/axon_quant/_async.py
import asyncio
import functools
from typing import Any, Callable, TypeVar

T = TypeVar("T")

def async_wrap(fn: Callable[..., T]) -> Callable[..., "asyncio.Future[T]"]:
    """把 axon_quant 同步阻塞方法包成 asyncio 协程。
    
    axon_quant 内部用 tokio::block_on 转同步,会阻塞 Python 主线程。
    此装饰器把调用推到独立线程,避免阻塞 event loop。
    """
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(fn, *args, **kwargs)
    return wrapper

def async_class(cls: type) -> type:
    """类装饰器:对类的所有 public 方法应用 async_wrap。"""
    for name in dir(cls):
        attr = getattr(cls, name, None)
        if callable(attr) and not name.startswith("_"):
            setattr(cls, name, async_wrap(attr))
    return cls
```

### 4.4 错误规范样板

```python
# backend/axon_quant/_errors.py
from axon_quant import DataError, RiskError, OmsError, ExchangeError
from fastapi import HTTPException

class AxonQuantError(Exception):
    """axon_quant 异常的 QuantCell 包装基类。"""
    http_status: int = 500
    code: str = "axon_quant_error"

    def __init__(self, original: Exception):
        self.original = original
        self.message = str(original)
        super().__init__(self.message)

    def to_http(self) -> HTTPException:
        return HTTPException(
            status_code=self.http_status,
            detail={"code": self.code, "message": self.message},
        )

ERROR_MAPPING: dict[type, tuple[int, str]] = {
    DataError:       (400, "data_error"),
    RiskError:       (403, "risk_rejected"),
    OmsError:        (409, "oms_conflict"),
    ExchangeError:   (502, "exchange_error"),
}

def map_error(e: Exception) -> Exception:
    """axon_quant 异常 → QuantCell 异常。"""
    for src_type, (status, code) in ERROR_MAPPING.items():
        if isinstance(e, src_type):
            exc = AxonQuantError(e)
            exc.http_status = status
            exc.code = code
            return exc
    return AxonQuantError(e)
```

### 4.5 多 Agent 适配样板

```python
# backend/axon_quant/llm/agent.py
from dataclasses import dataclass, field
from axon_quant import llm as _llm_native

@dataclass
class AgentConfig:
    """QuantCell 层 Agent 配置,引用 axon-llm.swarm.agents.Agent。"""
    name: str                                  # e.g. "data_agent.btc_1h"
    role: str                                  # e.g. "data"
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    llm_backend: str = "openai"
    llm_model: str = "gpt-4o"
    version: int = 1
    parent: str | None = None

class QuantCellAgent:
    """Agent 包装,负责把 QuantCell 配置转译为 axon-llm Agent。"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self._native = _llm_native.Agent(
            name=config.name,
            system_prompt=config.system_prompt,
            tools=config.tools,
            llm_backend=config.llm_backend,
            llm_model=config.llm_model,
        )
    
    async def invoke(self, message: str, context: dict) -> "AgentResult":
        from backend.axon_quant.llm.message import trace_agent_call
        trace_id = trace_agent_call(agent=self.config.name, input=message, context=context)
        result = await asyncio.to_thread(self._native.invoke, message, context)
        trace_agent_call(trace_id, result=result)
        return result
```

```python
# backend/axon_quant/llm/swarm.py
from axon_quant import llm as _llm_native
from .agent import AgentConfig, QuantCellAgent

class QuantCellSwarm:
    """多 Agent 协作编排,基于 axon-llm.swarm.orchestrator。"""
    
    def __init__(self, agents: list[QuantCellAgent], topology: str = "orchestrator"):
        self.agents = {a.config.name: a for a in agents}
        self._native = _llm_native.SwarmOrchestrator(
            agents=[a._native for a in agents],
            topology=topology,
        )
    
    async def run(self, task: str) -> "SwarmResult":
        from backend.axon_quant.llm.message import trace_swarm_run
        trace_id = trace_swarm_run(
            topology=self._native.topology,
            agents=list(self.agents.keys()),
            task=task,
        )
        result = await asyncio.to_thread(self._native.run, task)
        trace_swarm_run(trace_id, result=result, messages=self._native.messages)
        return result
```

### 4.6 凭证管理样板

```python
# backend/axon_quant/_credentials.py
from pydantic_settings import BaseSettings

class AxonQuantCredentials(BaseSettings):
    """axon_quant LLM/Exchange 凭证集中管理。"""
    # LLM
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    local_llm_endpoint: str | None = None
    # Exchange
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_passphrase: str | None = None
    # axon-harness(待 P3 集成)
    enable_rbac: bool = False
    
    class Config:
        env_file = ".env"
        env_prefix = "AXON_"

credentials = AxonQuantCredentials()
```

---

## 5. CLI 入口设计

### 5.1 设计原则

1. **统一入口 `quantcell` 命令** — 一次安装,全功能访问
2. **CLI 是 ② 层的第二种入口**,不绕过 services/(Web 是第一种,API 客户端是第三种)
3. **平迁现有 12 个 `scripts/*_cli.py`** — typer app 全部平迁到 `cli/` 包,**业务逻辑不动**
4. **兼容期 6 个月** — 旧脚本保留为 shim,转发到新 `quantcell <cmd>`
5. **可发现性** — 顶层 `quantcell --help` 列出所有子命令组

### 5.2 目录结构

```
backend/
├── cli/                              ← 新增 CLI 入口包
│   ├── __init__.py
│   ├── main.py                       ← typer.Typer root (entry point)
│   ├── _errors.py
│   ├── _output.py                    ← JSON/Table/Streaming 输出
│   ├── _version.py
│   ├── run.py                        ← 启动 Web
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── chat.py                   ← session/tool/chat/workspace
│   │   ├── swarm.py                  ← 多 Agent 协作(新)
│   │   ├── trace.py                  ← 协作流回放(新)
│   │   ├── registry.py               ← Agent 注册(新)
│   │   └── template.py               ← Agent 模板(新)
│   ├── backtest.py
│   ├── data.py
│   ├── market.py
│   ├── news.py
│   ├── strategy.py
│   ├── train.py                      ← RL/HPO/walk-forward
│   ├── deploy.py
│   ├── worker.py
│   ├── plugin.py
│   ├── web.py
│   ├── migrate.py
│   ├── test.py
│   └── config.py                     ← 凭证/配置(新)
│
├── scripts/                          ← 兼容期保留 6 个月
│   └── *_cli.py → shim,转发到 quantcell <cmd>
│
└── pyproject.toml
    └── [project.scripts]
        quantcell = "cli.main:app"
```

### 5.3 顶层命令树

```
quantcell
├── run                # 启动 FastAPI server
│   └── --port / --host / --reload / --workers
├── worker             # Worker 进程管理
│   └── start / stop / restart / status / logs
├── migrate            # DB 迁移
│   └── up / down / status / create
├── test               # 跑测试
│   └── run / cov / lint
├── config             # 凭证/配置
│   └── show / set / get / import / export
├── shell              # 交互式 IPython(预加载 services)
│
├── data               # 数据子命令组
│   └── fetch / list / clean / cache
├── market             # 行情
│   └── ticker / kline / orderbook
├── news               # 新闻
│   └── list / fetch
├── strategy           # 策略
│   └── create / list / show / delete / deploy
├── backtest           # 回测
│   └── run / list / show / compare / report
├── train              # 训练
│   └── rl / hpo / walk-forward / list / status
├── deploy             # 部署
│   └── strategy / live / stop / status
│
├── agent              # 单/多 Agent
│   ├── chat send/interactive/history
│   ├── session list/create/delete/clear
│   ├── tool list/info/run
│   ├── workspace list/cat/clean
│   ├── params tools/show/set/import/export
│   │
│   ├── swarm          # ★ 多 Agent 协作
│   │   └── run / list / show / trace / replay
│   ├── registry       # ★ Agent 注册
│   │   └── list / show / create / delete / version
│   └── template       # ★ Agent 模板
│       └── list / show / apply
│
├── web                # 网页工具
│   └── search / fetch
└── plugin             # 插件
    └── list / install / enable / disable
```

### 5.4 关键样板代码

```python
# backend/cli/main.py
import typer
from pathlib import Path
from cli import (
    run, worker, migrate, test, config, shell,
    data, market, news, strategy, backtest, train, deploy,
    agent, web, plugin,
)

app = typer.Typer(
    name="quantcell",
    help="QuantCell — AI 量化交易平台 CLI(无界面启动)",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

for mod in [run, worker, migrate, test, config, shell,
            data, market, news, strategy, backtest, train, deploy,
            agent, web, plugin]:
    app.add_typer(mod.app, name=mod.NAME)

@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V"),
    config_path: Path | None = typer.Option(None, "--config", "-c"),
    log_level: str = typer.Option("INFO", "--log-level"),
    json_output: bool = typer.Option(False, "--json"),
):
    if version:
        from cli._version import __version__
        typer.echo(f"quantcell {__version__}")
        raise typer.Exit()
    if config_path:
        load_config(config_path)
    setup_logging(log_level)
```

```python
# backend/cli/_output.py
import json
import typer
from rich.console import Console
from rich.table import Table

console = Console()

def print_table(headers: list[str], rows: list[list]) -> None:
    table = Table(show_header=True, header_style="bold magenta")
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)

def print_json(data) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))

def print_streaming(iterator) -> None:
    for chunk in iterator:
        typer.echo(chunk, nl=False)
    typer.echo()
```

```python
# backend/cli/agent/swarm.py  (★ 新增:多 Agent 协作 CLI)
import asyncio
import json
from pathlib import Path
import typer
from typing_extensions import Annotated
from cli._output import print_table, print_json, print_streaming
from backend.axon_quant.llm import QuantCellSwarm, AgentConfig
from backend.services.agent_service import AgentService

app = typer.Typer(help="多 Agent 协作")

@app.command("run", help="执行 Agent 协作任务")
def swarm_run(
    dag: Annotated[Path, typer.Option("--dag", "-d", help="Agent DAG JSON")],
    task: Annotated[str, typer.Option("--task", "-t", help="自然语言任务")],
    stream: bool = typer.Option(True, "--stream/--no-stream"),
    save_trace: bool = typer.Option(True, "--trace/--no-trace"),
):
    """例:quantcell agent swarm run --dag templates/swarm/dualma_risk.json -t 'BTC 1h 回测'"""
    config = json.loads(dag.read_text())
    agents = [AgentConfig(**a) for a in config["agents"]]
    swarm = QuantCellSwarm(agents, topology=config.get("topology", "orchestrator"))
    
    if stream:
        for event in swarm.run_stream(task):
            typer.echo(event, nl=False)
    else:
        result = asyncio.run(swarm.run(task))
        print_json(result.to_dict())

@app.command("trace", help="查看 Agent 协作流")
def swarm_trace(
    run_id: str = typer.Argument(help="协作运行 ID"),
    format: str = typer.Option("table", "--format", "-f", help="table/json/timeline"),
):
    service = AgentService()
    trace = service.get_trace(run_id)
    if format == "json":
        print_json(trace)
    else:
        print_table(
            headers=["时间", "Agent", "动作", "结果"],
            rows=[[m["ts"], m["agent"], m["action"], m["result"]] for m in trace["messages"]]
        )

@app.command("replay", help="重演一次 Agent 协作")
def swarm_replay(
    run_id: str = typer.Argument(help="协作运行 ID"),
    speed: float = typer.Option(1.0, "--speed", help="重演倍速"),
):
    service = AgentService()
    for event in service.replay(run_id, speed=speed):
        typer.echo(event, nl=False)
```

### 5.5 安装与自动补全

```toml
# backend/pyproject.toml
[project.scripts]
quantcell = "cli.main:app"
```

安装后:
- `quantcell --help` 查看所有子命令
- `quantcell run` 启动 Web
- `quantcell agent chat interactive` 进入交互式 Agent
- `quantcell agent swarm run --dag templates/dualma.json -t "BTC 回测"` 多 Agent 协作
- `quantcell install-completion bash` 安装 bash 自动补全
- `uv tool install .` 全局安装

### 5.6 兼容期 shim

```python
# backend/scripts/agent_cli.py (改写为 shim,6 个月内)
#!/usr/bin/env python3
"""DEPRECATED: Use `quantcell agent <subcommand>` instead."""
import sys
import warnings
import subprocess

def main():
    warnings.warn(
        "scripts/agent_cli.py is deprecated. Use `quantcell agent <subcommand>` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    args = ["quantcell", "agent"] + sys.argv[1:]
    sys.exit(subprocess.call(args))
```

---

## 6. 实施阶段(16-21 周)

### 6.1 阶段总览

| 阶段 | 范围 | 时间 |
|---|---|---|
| **P1** | 交易主线(data/backtest/risk/oms/exchange)+ 6-8 策略模板 + 统一 CLI 入口 | 4-6 周 |
| **P2-A** | AI 主线核心(rl/inference/llm/hpo/registry/ensemble/walk_forward/tracker) | 6-8 周(与 P1 后段并行) |
| **P2-B** | 多 Agent 协作层(swarm 包装 + Agent 注册 + DAG 编辑器 + trace + 凭证 vault) | 4 周(与 P2-A 并行) |
| **P3** | 治理/可解释/分布式(compliance/monitor/harness/explain/distributed) | 4 周 |
| **P4** | 打磨(性能/E2E/文档/部署) | 2-3 周 |
| **P5** | 跳过:axon-defi / axon-cli | 0 |

### 6.2 P1-Sprint 1(2 周)— 数据/回测/风控/OMS 统一包装 + CLI 入口

| # | Task | 验收 |
|---|---|---|
| T1.1 | 创建 `backend/axon_quant/` 适配层目录骨架 | 目录结构 + `__init__.py` 顶层重导出 |
| T1.2 | 迁移 services → 统一 import 路径 | 4 个 service 改 `from backend.axon_quant import X` |
| T1.3 | 实现 `_errors.py` + `_async.py` + `_credentials.py` | 单测覆盖 8 个错误类型 + async_wrap |
| T1.4 | `axon_quant.data` 全量包装(多源 + 缓存 + Parquet) | 6 个 wrapper, ≤200 行/文件 |
| T1.5 | `axon_quant.backtest` 包装 + **完全删除所有向量化回测代码**(`backtest/engines/VectorEngine` 等) | `git grep "VectorEngine"` 0 命中;`git grep "from backtest.engines"` 0 命中;`ls backtest/engines/` 不存在 |
| T1.6 | `axon_quant.risk` 包装 + dry-run 模式 | dry-run API 输入 Order 返回 RiskResult 不下单 |
| T1.7 | `axon_quant.oms` 包装 + 订单状态机 UI 视图 | 订单历史落 `axond_orders` 表 |
| T1.8 | 回归测试:`tests/unit/worker/` + `tests/unit/axond/` 全过 | 192+ passed,0 失败 |
| **T1.19** | 创建 `backend/cli/` 包骨架 + `quantcell` 顶层入口 | `quantcell --help` 工作 |
| **T1.20** | 迁移 12 个 `scripts/*_cli.py` → `cli/*.py`(平迁) | 12 个子命令组 `quantcell <cmd> --help` 通过 |
| **T1.21** | `pyproject.toml` 配置 `[project.scripts] quantcell = "cli.main:app"` | `uv tool install .` 成功 |
| **T1.22** | scripts/*_cli.py 改写为 shim,DeprecationWarning | 旧命令仍可用 |
| **T1.26** | `quantcell install-completion` bash/zsh 自动补全 | 补全脚本生成 |

### 6.3 P1-Sprint 2(2 周)— 实盘交易所 + 凭证 + 多账号 + 策略模板

| # | Task | 验收 |
|---|---|---|
| T1.9 | `axon_quant.exchange` 包装(Binance/OKX) | `services/exchange_service.py` ≤ 200 行 |
| T1.10 | `_credentials.py` 凭证管理 | `.env` 模板 + 文档 |
| T1.11 | 多账号管理表 `axond_exchange_accounts` | CRUD API + 关联用户/策略 |
| T1.12 | Exchange 连接健康度仪表盘 | 指标:WS 心跳/REST 延迟/错误率 |
| T1.13 | `axon_quant.oms` 接入 exchange(下/撤单走 native) | E2E:纸面下单 → 真实 Binance testnet 撤单 |
| T1.14 | 6-8 个预设策略模板(DualMA/Grid/MeanReversion 等) | `axond_strategies/` 目录 + 模板注册表 |
| T1.15 | 模板表单配置 UI(非程序员入口) | 前端 `pages/strategies/templates/` |
| **T1.24** | `quantcell config` 凭证管理子命令 | `_credentials.py` 接入 |

### 6.4 P1-Sprint 3(2 周,可选)— 交易主线打磨

| # | Task | 验收 |
|---|---|---|
| T1.16 | 端到端回归测试(模板 → 回测 → 纸面实盘) | 1 条全链路用例 5 分钟内跑通 |
| T1.17 | 性能基线:BacktestEngine 1 年 1m 数据 < 30s | benchmark 报告 |
| T1.18 | 用户文档:从 0 到第一个回测 30 分钟教程 | `docs/quickstart_p1.md` |

### 6.5 P2-A Sprint 1(2 周)— RL 训练 + 推理 + 注册

| # | Task | 验收 |
|---|---|---|
| T2A.1 | `axon_quant.rl` 包装(TradingEnv/SyncVecEnv/AsyncVecEnv) | `services/rl_service.py` 升级 |
| T2A.2 | RL 训练任务队列(SQLite/Postgres 排队) | 多用户同时提交不互相阻塞 |
| T2A.3 | 训练进度 SSE 流 | 前端实时显示 PPO loss/entropy |
| T2A.4 | `axon_quant.inference` 包装 + 批推理 + 模型热更新 | 切换模型版本不中断推理 |
| T2A.5 | `axon_quant.registry` 包装 + 模型血缘 | 表 `axond_models` + `axond_model_lineage` |
| T2A.6 | `axon_quant.walk_forward` 包装(★ 防过拟合) | 回测结果附 walk-forward 拆分 |

### 6.6 P2-A Sprint 2(2 周)— HPO + Tracker + Ensemble

| # | Task | 验收 |
|---|---|---|
| T2A.7 | `axon_quant.hpo` 包装 + 试验队列 | 提交 HPO → 多 trial 并行 → 最佳 trial 自动注册 |
| T2A.8 | `axon_quant.tracker` 包装(MLflow/WandB 适配) | 训练/HPO 试验自动落 tracker |
| T2A.9 | `axon_quant.ensemble` 包装 + 多模型对比回测 | UI 选 3 个模型 → 集成回测报告 |
| T2A.10 | 模型对比仪表盘(SHAP/性能/收益) | 集成模型 vs 单模型对比报告 PDF |

### 6.7 P2-A Sprint 3(2 周)— LLM 接入基础

| # | Task | 验收 |
|---|---|---|
| T2A.11 | `axon_quant.llm` 包装(LLMBackend/Message/Config) | OpenAI/Anthropic/Local 三个 backend |
| T2A.12 | `axon_quant.llm.trading` 工具注册(下/撤/查) | 工具 schema 自动生成 |
| T2A.13 | LLM 凭证 vault 扩展(集中管理) | `_credentials.py` 扩展 |
| T2A.14 | 单 Agent 聊天面板(最小可用) | 前端 `pages/agent/chat/{id}` |

### 6.8 P2-A Sprint 4(2 周)— LLM 训练产物集成

| # | Task | 验收 |
|---|---|---|
| T2A.15 | RL 训练 → Registry → Inference → Ensemble 全链路 | E2E:从训练到集成推理 1 条用例 |
| T2A.16 | 模型血缘完整追溯 | UI 可视化模型谱系 |

### 6.9 P2-B Sprint 1(2 周)— swarm 基础 + Agent 注册

| # | Task | 验收 |
|---|---|---|
| T2B.1 | `axon_quant.llm.swarm` 包装(orchestrator + vote) | `backend/axon_quant/llm/swarm.py` |
| T2B.2 | `QuantCellAgent` + `AgentConfig`(含版本) | 6 个预制 Agent(data/strategy/risk/execution/report/audit) |
| T2B.3 | Agent 注册表 `axond_agents` | CRUD API + 版本管理 |
| T2B.4 | 6-8 个预设 Agent 模板("双均线+风控"等) | `axond_agent_templates/` |

### 6.10 P2-B Sprint 2(2 周)— DAG 编辑器 + 协作流可视化

| # | Task | 验收 |
|---|---|---|
| T2B.5 | Agent DAG 设计 UI(拖拽式) | 前端 `pages/agents/dag/editor` |
| T2B.6 | DAG JSON 配置存储 | 一次配置可被多次 invoke |
| T2B.7 | 消息时序 trace(`axond_agent_trace` 表) | 每次协作 message/vote/tool_call 落库 |
| T2B.8 | 协作流可视化(谁调谁 / 消息时序 / 投票过程) | 前端 `pages/agents/trace/{run_id}` |
| T2B.9 | 工具调用安全边界(trading.* 需 Risk Agent 二次确认) | 配置层强制 + 单测覆盖 |
| T2B.10 | 协作流回放(从头重演 message 序列) | UI 按钮"重演这次决策" |
| **T1.23** | `quantcell agent swarm` 4 个子命令 | run/list/trace/replay |

### 6.11 P3(4 周)— 治理/可解释/分布式

| # | Task | 验收 |
|---|---|---|
| T3.1 | `axon_quant.compliance` 包装 + 审计事件查询 UI | 日/月/年报告 |
| T3.2 | `axon_quant.monitor` 包装 + Prometheus 指标导出 | `/metrics` endpoint |
| T3.3 | `axon_quant.harness` 包装 + RBAC(用户/角色/权限) | `axond_rbac` 表 + 中间件 |
| T3.4 | `axon_quant.explain` 包装 + SHAP/Counterfactual 报告 | PDF 导出 |
| T3.5 | `axon_quant.distributed` 包装(仅 K8s 部署时启用) | Ray 集群对接 |

### 6.12 P4(2-3 周)— 打磨

| # | Task | 验收 |
|---|---|---|
| T4.1 | 全链路 E2E 测试覆盖(从模板到实盘) | 8 条用例 |
| T4.2 | 性能基线 + 压测报告 | 回测 1 年 1m < 30s,推理延迟 < 50ms |
| T4.3 | 文档:架构图 + 快速上手 + 多 Agent 教程 | 3 篇 docs |
| T4.4 | 部署:K8s manifests + Docker Compose | 2 套部署方案 |
| **T1.25** | `quantcell shell` 交互式 IPython(预加载 services) | 运维/调试用 |

### 6.13 立即可开工 Backlog(本周启动)

```
Day 1-2  :T1.1 适配层骨架 + T1.3 _errors / _async 基础
Day 3-4  :T1.4 data 包装(全量) + T1.5 backtest 包装 + **删除向量化回测代码**
Day 5-7  :T1.6 risk 包装(含 dry-run) + T1.7 oms 包装
Day 8-10 :T1.2 services 迁移到统一 import 路径
Day 11-14:T1.8 回归测试 + 修复
Day 1-2 (CLI 并行):T1.19 cli 包骨架 + T1.26 自动补全
Day 3-10 (CLI 并行):T1.20 平迁 12 个 scripts + T1.21 pyproject 注册
Day 11-14 (CLI 并行):T1.22 旧脚本 shim 化
Day 0 (环境):`pip install axon-quant==0.2.0`(锁定 PyPI 版本,绝不加载本地源码)
```

---

## 7. 风险与开放问题

### 7.1 技术风险(R1-R15)

| # | 风险 | 影响面 | 缓解措施 |
|---|---|---|---|
| **R1** | axon_quant Rust API 变更 — 库仍在快速迭代 | P1/P2 所有服务包装可能重写 | ① 适配层 ③ 集中 import,变更只改 1 个文件;② 锁定 axon-quant==0.2.0,~minor 升版本需全量回归 |
| **R2** | PyO3 native 类型 dump 到 JSON 行为不稳定 | ② 层序列化可能爆 | 统一用 `pydantic.TypeAdapter` + 自定义 `AxonQuantEncoder`;P1-Sprint 1 优先建样板 |
| **R3** | `tokio::block_on` 在主线程阻塞 FastAPI event loop | 实时接口(WebSocket/SSE)卡顿 | `_async.py` + `asyncio.to_thread` 强制隔离;P3 引入独立 Rust HTTP server(axon-quant 自带)直接暴露给前端 |
| **R4** | 多 Agent 工具调用可能绕过风控 | 资金安全 | trading.* 工具白名单 + Risk Agent 强制二次确认 + 审计 trace 落库 |
| **R5** | LLM 输出不稳定(JSON 格式 / 幻觉) | Agent 决策可靠 | ① 工具调用 schema 强校验;② Agent 输出 Pydantic 验证;失败时 retry 1 次后降级为人工 |
| **R6** | axon-llm.trading 与 axon-oms 重复(都能下单) | 决策路径不唯一 | 强制:**所有下单走 axon-oms**,axon-llm.trading 只发"下单意图"信号,由 axon-oms 执行 |
| **R7** | 模板策略在真实市场失效 | 非程序员用户亏损 | ① 模板标注"仅供学习";② 实盘前强制 walk-forward + dry-run;③ 单一模板最大资金上限 |
| **R8** | PyO3 GIL 限制 — CPU 密集阻塞其他 Python 线程 | 高并发场景下推理/回测排队 | 单用户独占回测/RL 训练 worker;多用户走 Celery/RQ 队列(P3 引入) |
| **R9** | axon-quant PyPI 安装与版本管理 — 必须锁定 PyPI 版本,不可加载本地源码 | 安装/升级混乱 | ① `pyproject.toml` 锁 `axon-quant==0.2.0`;② 升级做全量回归(单元 + 集成 + E2E);③ 源码仓库 `/Users/liupeng/workspace/quant/axon` **仅作参考文档**,绝不 `sys.path.insert` 加载 |
| **R10** | 6-8 个预设策略模板的"训练+回测"基线数据缺失 | 无法判定模板好坏 | P1-Sprint 2 末交付每个模板 1 份"基线回测报告"(BTC/ETH 过去 1 年) |
| **R11** | CLI shim 兼容期 6 个月期间,新旧命令行为漂移 | 用户体验 | shim 阶段用 `subprocess.call` 转发,确保只有一份真业务代码 |
| **R12** | CLI 启动慢(冷启动需加载 typer + 12 个 typer subapp) | 开发体验 | ① `cli/main.py` 顶层用 `lazy load`;② 提供 `quantcell --profile` 诊断冷启动 |
| **R13** | LLM CLI 工具暴露太多 API key / 凭证给终端 | 安全 | ① `quantcell config show` 默认脱敏;② 凭证统一从 `_credentials.py` 读,不从 CLI 参数 |
| **R14** | CLI 在 cron / CI 环境下与交互式环境混用 | 自动化 | ① `--no-input` 全局开关;② CI 默认 `--json` 输出;③ `QUANTCELL_NONINTERACTIVE=1` 环境变量 |
| **R15** | `quantcell run` 与 `quantcell worker start` 端口冲突 | 部署 | run 用 8000,worker 用 9000(已有);CLI 启动前 `port_check` 报错清晰 |

### 7.2 开放问题(Q1-Q12)

| # | 开放问题 | 何时决定 |
|---|---|---|
| **Q1** | axon-quant 升级节奏(0.2.0 → 0.3.0 预计何时)及 breaking change 范围 | 每次升级前看 CHANGELOG |
| **Q2** | 6-8 个预设策略具体清单 | P1-Sprint 2 末前确认;建议 DualMA / Grid / MeanReversion / TrendFollow / 套利 / 截面多因子 / RL 仓位管理 / 动量反转 |
| **Q3** | axon-harness RBAC 与 QuantCell 现有用户系统的关系 | P3 启动前 1 周 |
| **Q4** | 多 Agent 协作的 LLM 费用上限(每用户/每任务) | P2-B 末上线前 |
| **Q5** | 是否提供 Docker 镜像 / K8s manifests | P4 决定 |
| **Q6** | axon-monitor 的指标后端(Prometheus / OpenTelemetry / StatsD) | P3 启动前 |
| **Q7** | "策略市场"是否允许用户上传/分享策略(法律风险) | P2 末决策 |
| **Q8** | 实盘交易牌照/合规(中国/海外) | P3 末决策 |
| **Q9** | CLI 是否要支持插件机制(用户写 CLI 子命令) | P3 决定;若需要,用 `entry_points` 注册 |
| **Q10** | CLI 是否提供 TUI(交互式 dashboard 替代 Web) | P4 决定;若需要,用 `textual` 框架 |
| **Q11** | CLI 是否打包为独立二进制(用 `pyoxidizer` / `nuitka`) | P4 决定 |
| **Q12** | 现有 `scripts/run_tests.py` 是否纳入 `quantcell test run` | P1-Sprint 1 内决定;建议纳入 |

---

## 8. 决策记录

### 8.1 已决策(本次 spec)

1. ✅ 4 层架构 + 多 Agent 协作模式
2. ✅ ② 层 services/ 必须经 ③ 层 axon_quant/,禁止直接 import
3. ✅ axon_quant 通过 PyPI 安装,零源码依赖(`/Users/liupeng/workspace/quant/axon` 仅作参考文档)
4. ✅ **回测完全走事件驱动(axon_quant.backtest)**,**完全删除所有向量化回测代码**
5. ✅ CLI 是 ② 层第二种入口,统一为 `quantcell` 命令
6. ✅ axon-defi / axon_cli 永久跳过
7. ✅ 适配层样板 6 个(目录/类型/异步/错误/Agent/凭证)
8. ✅ 风险 15 条 + 开放问题 12 条

### 8.2 待决策(见 §7.2)

Q1-Q12 在对应阶段启动前 1 周内决定。

---

## 9. 验收标准

**v2.0.0 验收**(2026-07-16 → 2026-Q4 末):
- P1 全部完成:交易主线 + 6-8 策略模板 + 统一 CLI
- P2-A 全部完成:AI 主线核心(RL/HPO/LLM/Tracker 等)
- P2-B 全部完成:多 Agent 协作层
- P3 ≥ 60% 完成:合规/监控/RBAC
- 单元测试覆盖率 ≥ 90%
- 8 条 E2E 全链路用例通过
- 性能基线:回测 1 年 1m < 30s,推理延迟 < 50ms
- `quantcell --version` 工作,`quantcell agent swarm run` 工作
- **回测纯事件驱动**:`git grep "VectorEngine"` 0 命中,`backtest/engines/` 目录已删除
- **axon_quant 零源码依赖**:`pyproject.toml` 锁 `axon-quant==0.2.0`,`/Users/liupeng/workspace/quant/axon` 仓库未被任何 `sys.path` 引用

---

**Status:** Pending user review
**Next:** writing-plans skill 创建实施计划
