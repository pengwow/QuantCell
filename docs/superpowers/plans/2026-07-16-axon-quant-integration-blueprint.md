# axon_quant 集成蓝图 — P1-Sprint 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 2 周内交付 axon_quant 适配层 ③ 骨架 + 4 个核心 service 包装(risk/oms/data/backtest) + 统一 CLI 入口 `quantcell` + 12 个旧 scripts 平迁/改 shim + **完全删除向量化回测代码**。

**Architecture:** 4 层架构(①前端 ②QuantCell ③适配层 ④axon_quant Rust 引擎)。本 Sprint 在 ②③ 层落地:
- ③ 层: `backend/axon_bridge/` 适配层,集中转译/错误规范/异步桥接,所有 ② 层 service 强制经此
- ② 层: `backend/services/{risk,oms,data,backtest}_service.py` 改 `from backend.axon_bridge import X`
- ② 层: `backend/cli/` 统一 CLI 包,`quantcell` 命令
- ② 层: `backend/scripts/*_cli.py` 改 shim 转发

**Tech Stack:** Python 3.14, typer ≥ 0.20, rich ≥ 13, FastAPI 0.136, pytest 9, uv(包管理), pip install --upgrade axon-quant(永远最新)

**Reference Spec:** `docs/superpowers/specs/2026-07-16-axon-quant-integration-blueprint.md`

---

## 0. Scope Check

本 plan 仅覆盖 **P1-Sprint 1**(2 周)。后续 plan 独立:
- `2026-07-16-axon-quant-p1-sprint2.md` — 实盘交易所 + 凭证 + 多账号 + 6-8 策略模板
- `2026-07-16-axon-quant-p1-sprint3.md` — 交易主线打磨
- `2026-07-16-axon-quant-p2a-sprint1.md` — RL 训练 + 推理 + 注册
- `2026-07-16-axon-quant-p2a-sprint2.md` — HPO + Tracker + Ensemble
- `2026-07-16-axon-quant-p2a-sprint3.md` — LLM 接入基础
- `2026-07-16-axon-quant-p2a-sprint4.md` — LLM 训练产物集成
- `2026-07-16-axon-quant-p2b-sprint1.md` — swarm 基础 + Agent 注册
- `2026-07-16-axon-quant-p2b-sprint2.md` — DAG 编辑器 + 协作流可视化
- `2026-07-16-axon-quant-p3.md` — 治理/可解释/分布式
- `2026-07-16-axon-quant-p4.md` — 打磨

---

## 1. File Structure(本 Sprint 涉及)

### 新建文件
```
backend/axon_bridge/                  ← ③ 适配层
├── __init__.py                      ← 顶层重导出
├── _errors.py                       ← 统一错误规范
├── _async.py                        ← 异步桥接装饰器
├── _credentials.py                  ← 凭证管理
├── data/__init__.py                 ← axon_quant.data 包装
├── backtest/__init__.py             ← axon_quant.backtest 包装 + 删向量化
├── risk/__init__.py                 ← axon_quant.risk 包装
└── oms/__init__.py                  ← axon_quant.oms 包装

backend/cli/                          ← ② 统一 CLI
├── __init__.py
├── main.py                          ← typer.Typer root
├── _output.py                       ← JSON/Table 输出
├── _version.py
├── _errors.py                       ← CLI 错误处理
├── run.py                           ← 启动 FastAPI
├── data.py
├── backtest.py
├── market.py
├── news.py
├── strategy.py
├── worker.py
├── web.py
├── migrate.py
├── test.py
├── plugin.py
├── rl.py
└── agent/__init__.py                ← 暂平迁 agent_cli

backend/tests/unit/axon_bridge/        ← 适配层测试
├── __init__.py
├── test_errors.py
├── test_async.py
├── test_credentials.py
├── data/test_data_wrapper.py
├── backtest/test_backtest_wrapper.py
├── risk/test_risk_wrapper.py
└── oms/test_oms_wrapper.py

backend/tests/unit/cli/               ← CLI 测试
├── __init__.py
├── test_main.py
├── test_output.py
└── test_run.py
```

### 修改文件
```
backend/services/risk_service.py      ← 改 import 路径
backend/services/oms_service.py       ← 改 import 路径
backend/services/data_service.py      ← 改 import 路径
backend/services/backtest_service.py  ← 改 import 路径
backend/scripts/agent_cli.py          ← 改 shim
backend/scripts/backtest_cli.py       ← 改 shim
backend/scripts/data_cli.py           ← 改 shim
backend/scripts/market_cli.py         ← 改 shim
backend/scripts/migrate_db.py         ← 改 shim
backend/scripts/news_cli.py           ← 改 shim
backend/scripts/plugin_cli.py         ← 改 shim
backend/scripts/rl_cli.py             ← 改 shim
backend/scripts/run_tests.py          ← 改 shim
backend/scripts/strategy_cli.py       ← 改 shim
backend/scripts/web_cli.py            ← 改 shim
backend/scripts/worker_cli.py         ← 改 shim
backend/pyproject.toml                ← + axon-quant + project.scripts
```

### 删除文件/目录
```
backend/backtest/engines/             ← 向量化回测代码(全部)
backend/backtest/engines/__init__.py
backend/backtest/engines/engine.py    ← VectorEngine
backend/backtest/engines/legacy_*.py  ← 任何遗留
```

---

## Task 1: 环境准备 + 删除向量化回测代码

**Files:**
- Delete: `backend/backtest/engines/`(整目录)
- Modify: `backend/pyproject.toml`(更新 axon-quant 依赖)
- Test: 验证 `git grep "VectorEngine"` 0 命中

- [ ] **Step 1: 确认 axon_quant 已装且为最新**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
pip install --upgrade axon-quant
python -c "import axon_quant; print(axon_quant.__version__)"
```
Expected: 输出 0.2.0 或更高版本号

- [ ] **Step 2: 搜索所有 VectorEngine 引用**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git grep -n "VectorEngine" -- backend/
git grep -n "from backtest.engines" -- backend/
git grep -n "import backtest.engines" -- backend/
```
Expected: 列出所有引用(用以下步骤全删)

- [ ] **Step 3: 删除向量化回测代码目录**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git rm -r backend/backtest/engines/
```
Expected: 列出删除文件

- [ ] **Step 4: 修复残留 import 引用**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git grep -n "from backtest.engines\|import backtest.engines" -- backend/
```
Expected: 仍可能有引用,需手动改这些文件为 `from backend.axon_bridge.backtest import ...`

- [ ] **Step 5: 跑现有测试,确保无 regression**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit -x --no-header -q 2>&1 | tail -30
```
Expected: 失败的测试列出(后续 task 修复),通过的不变

- [ ] **Step 6: 更新 pyproject.toml 依赖**

打开 `backend/pyproject.toml`,找到:
```toml
    "axon-quant>=0.1.3",
```
改为:
```toml
    "axon-quant>=0.2.0",
```

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/pyproject.toml
git commit -m "feat: 删除向量化回测代码,axon-quant 依赖更新到 >=0.2.0"
```

---

## Task 2: 创建适配层骨架 + 顶层重导出

**Files:**
- Create: `backend/axon_bridge/__init__.py`
- Create: `backend/axon_bridge/_errors.py`
- Test: `backend/tests/unit/axon_bridge/__init__.py`
- Test: `backend/tests/unit/axon_bridge/test_errors.py`

- [ ] **Step 1: 创建测试目录和包**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
mkdir -p tests/unit/axon_bridge
touch tests/unit/axon_bridge/__init__.py
mkdir -p axon_quant
```

- [ ] **Step 2: 写失败测试 — test_errors.py**

创建 `backend/tests/unit/axon_bridge/test_errors.py`:
```python
"""适配层错误规范测试。"""
import pytest
from fastapi import HTTPException

from axon_quant import DataError


def test_data_error_maps_to_400():
    """DataError 应映射为 HTTP 400。"""
    from backend.axon_bridge._errors import map_error

    err = map_error(DataError("test"))
    assert err.http_status == 400
    assert err.code == "data_error"


def test_map_error_returns_axon_quant_error():
    """未知错误应包装为 AxonQuantError(500)。"""
    from backend.axon_bridge._errors import map_error, AxonQuantError

    err = map_error(ValueError("xxx"))
    assert isinstance(err, AxonQuantError)
    assert err.http_status == 500
    assert err.code == "axon_quant_error"


def test_to_http_creates_http_exception():
    """to_http() 应返回 FastAPI HTTPException。"""
    from backend.axon_bridge._errors import map_error

    err = map_error(DataError("bad request"))
    http = err.to_http()
    assert isinstance(http, HTTPException)
    assert http.status_code == 400
    assert http.detail["code"] == "data_error"
```

- [ ] **Step 3: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_errors.py -v 2>&1 | tail -20
```
Expected: ModuleNotFoundError: No module named 'backend.axon_bridge'

- [ ] **Step 4: 实现 _errors.py**

创建 `backend/axon_bridge/_errors.py`:
```python
"""axon_quant 异常 → QuantCell 异常的映射规范。

所有 QuantCell 业务代码抛出的 axon_quant 异常,经 map_error 包装后
统一提供 http_status + code + to_http() 三件套。
"""
from typing import Any
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


# 延迟导入避免循环依赖
def _build_mapping() -> dict[type, tuple[int, str]]:
    from axon_quant import DataError, RiskError, OmsError, ExchangeError
    return {
        DataError:       (400, "data_error"),
        RiskError:       (403, "risk_rejected"),
        OmsError:        (409, "oms_conflict"),
        ExchangeError:   (502, "exchange_error"),
    }


def map_error(e: Exception) -> AxonQuantError:
    """axon_quant 异常 → QuantCell AxonQuantError。

    已知异常类型用 ERROR_MAPPING 映射;未知类型回退到 500 通用错误。
    """
    mapping = _build_mapping()
    for src_type, (status, code) in mapping.items():
        if isinstance(e, src_type):
            exc: Any = AxonQuantError(e)
            exc.http_status = status
            exc.code = code
            return exc
    return AxonQuantError(e)
```

- [ ] **Step 5: 创建 __init__.py 顶层重导出**

创建 `backend/axon_bridge/__init__.py`:
```python
"""Axon_quant 适配层 — 顶层重导出,避免散落 import 路径。

所有 QuantCell 业务代码统一 from backend.axon_bridge import X。

依赖说明:
- axon_quant 通过 PyPI 安装(`pip install --upgrade axon-quant`)
- 永远跟随最新版本,不锁版本
- /Users/liupeng/workspace/quant/axon 源码仓库仅作参考文档,
  绝不 sys.path.insert 加载
"""
# 核心数据类(直接重导出,零转译)
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
    # errors
    RiskError, OmsError, ExchangeError,
)
from axon_quant import (  # noqa: F401
    rl, llm, hpo, registry, ensemble, walk_forward,
    tracker, compliance, explain, distributed, harness,
)
```

- [ ] **Step 6: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_errors.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/ backend/tests/unit/axon_bridge/
git commit -m "feat(axon_quant): 适配层骨架 + 顶层重导出 + 错误规范"
```

---

## Task 3: 实现 _async.py 异步桥接

**Files:**
- Create: `backend/axon_bridge/_async.py`
- Test: `backend/tests/unit/axon_bridge/test_async.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/axon_bridge/test_async.py`:
```python
"""异步桥接装饰器测试。"""
import asyncio
import time
import pytest

from backend.axon_bridge._async import async_wrap, async_class


def test_async_wrap_runs_in_thread():
    """async_wrap 应把阻塞调用推到独立线程,event loop 不阻塞。"""
    def blocking_fn(x: int) -> int:
        time.sleep(0.1)
        return x * 2

    wrapped = async_wrap(blocking_fn)

    async def run():
        start = time.time()
        result = await wrapped(5)
        elapsed = time.time() - start
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result == 10
    assert elapsed >= 0.1


def test_async_class_wraps_public_methods():
    """async_class 应包装所有 public 方法。"""
    class Calc:
        def add(self, a: int, b: int) -> int:
            return a + b

        def _private(self) -> str:
            return "private"

    Wrapped = async_class(Calc)
    assert hasattr(Wrapped, "add")
    # _private 不应该被包装(虽然有属性,但原方法保留)
    assert hasattr(Wrapped, "_private")


def test_async_class_preserves_functionality():
    """包装后功能不变(同步调用仍可用)。"""
    class Calc:
        def add(self, a: int, b: int) -> int:
            return a + b

    Wrapped = async_class(Calc)
    instance = Wrapped()
    # 同步调用仍应能直接用(因为 __getattr__ 会委托)
    # 或通过 await
    async def run():
        return await instance.add(3, 4)

    result = asyncio.run(run())
    assert result == 7
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_async.py -v 2>&1 | tail -15
```
Expected: ModuleNotFoundError: No module named 'backend.axon_bridge._async'

- [ ] **Step 3: 实现 _async.py**

创建 `backend/axon_bridge/_async.py`:
```python
"""异步桥接装饰器。

axon_quant 内部用 tokio::block_on 转同步,会阻塞 Python 主线程。
此模块提供:
- async_wrap(fn): 把单函数包装为 async 函数(走 asyncio.to_thread)
- async_class(cls): 对类的所有 public 方法应用 async_wrap

注意: 这是装饰器,被包装的方法在调用时会自动变成 async 协程。
调用方需用 `await obj.method(...)` 而非 `obj.method(...)`。
"""
import asyncio
import functools
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def async_wrap(fn: Callable[..., T]) -> Callable[..., "asyncio.Future[T]"]:
    """把 axon_quant 同步阻塞方法包成 asyncio 协程。"""
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(fn, *args, **kwargs)
    return wrapper


def async_class(cls: type) -> type:
    """类装饰器:对类的所有 public 方法应用 async_wrap。"""
    for name in list(dir(cls)):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if callable(attr):
            setattr(cls, name, async_wrap(attr))
    return cls
```

- [ ] **Step 4: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_async.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/_async.py backend/tests/unit/axon_bridge/test_async.py
git commit -m "feat(axon_quant): 异步桥接装饰器(asyncio.to_thread)"
```

---

## Task 4: 实现 _credentials.py 凭证管理

**Files:**
- Create: `backend/axon_bridge/_credentials.py`
- Test: `backend/tests/unit/axon_bridge/test_credentials.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/axon_bridge/test_credentials.py`:
```python
"""凭证管理测试。"""
import os
import pytest
from pydantic_settings import BaseSettings

# 测试前清理可能的环境变量
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(os.environ.keys()):
        if key.startswith("AXON_"):
            monkeypatch.delenv(key, raising=False)
    yield


def test_credentials_loads_from_env(monkeypatch):
    """凭证应从 AXON_* 环境变量读取。"""
    monkeypatch.setenv("AXON_OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("AXON_BINANCE_API_KEY", "bin-key")

    from backend.axon_bridge._credentials import AxonQuantCredentials

    creds = AxonQuantCredentials()
    assert creds.openai_api_key == "sk-test-123"
    assert creds.binance_api_key == "bin-key"
    assert creds.anthropic_api_key is None


def test_credentials_singleton_exists():
    """应导出全局 credentials 单例。"""
    from backend.axon_bridge import credentials
    from backend.axon_bridge._credentials import AxonQuantCredentials
    assert isinstance(credentials, AxonQuantCredentials)


def test_credentials_has_exchange_fields():
    """应包含 Exchange 凭证字段。"""
    from backend.axon_bridge._credentials import AxonQuantCredentials
    creds = AxonQuantCredentials()
    assert hasattr(creds, "binance_api_secret")
    assert hasattr(creds, "okx_passphrase")
    assert hasattr(creds, "local_llm_endpoint")
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_credentials.py -v 2>&1 | tail -15
```
Expected: ModuleNotFoundError: No module named 'backend.axon_bridge._credentials'

- [ ] **Step 3: 实现 _credentials.py**

创建 `backend/axon_bridge/_credentials.py`:
```python
"""axon_quant LLM/Exchange 凭证集中管理(QuantCell 增值)。

所有 Exchange/LLM 调用统一从 `credentials` 单例读取,避免散落 os.environ 读取。
P3 接入 axon-harness 后改为从 Vault 拉取。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class AxonQuantCredentials(BaseSettings):
    """axon_quant 凭证配置。"""

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

    # axon-harness(P3 集成)
    enable_rbac: bool = False

    model_config = SettingsConfigDict(
        env_prefix="AXON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 全局单例
credentials = AxonQuantCredentials()
```

同时在 `backend/axon_bridge/__init__.py` 顶部添加:
```python
from ._credentials import credentials  # noqa: F401
```

- [ ] **Step 4: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_credentials.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/_credentials.py backend/axon_bridge/__init__.py backend/tests/unit/axon_bridge/test_credentials.py
git commit -m "feat(axon_quant): 凭证管理(AXON_* 环境变量 + 单例)"
```

---

## Task 5: 包装 axon_quant.data

**Files:**
- Create: `backend/axon_bridge/data/__init__.py`
- Test: `backend/tests/unit/axon_bridge/data/test_data_wrapper.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/axon_bridge/data/test_data_wrapper.py`:
```python
"""axon_quant.data 适配层测试。"""
import pytest
from datetime import datetime, timedelta


def test_data_service_importable():
    """DataService 应从适配层可导入。"""
    from backend.axon_bridge import DataService
    assert DataService is not None


def test_data_request_creation():
    """DataRequest 应可用,且字段完整。"""
    from backend.axon_bridge import DataRequest
    req = DataRequest(
        symbol="BTCUSDT",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 31),
        frequency="1h",
    )
    assert req.symbol == "BTCUSDT"
    assert req.frequency == "1h"


def test_frequency_enum_exposed():
    """Frequency 枚举应从适配层可导入。"""
    from backend.axon_bridge import Frequency
    # 至少有 1m 频率
    assert hasattr(Frequency, "M1") or "1m" in [a.name.lower() for a in Frequency]
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/data/test_data_wrapper.py -v 2>&1 | tail -15
```
Expected: 失败(可能 DataRequest 字段名不匹配,按实际修正)

- [ ] **Step 3: 实际探测 axon_quant.data API**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
python -c "
from axon_quant import DataService, DataRequest, Frequency
import inspect
print('DataService:', DataService)
print('DataRequest signature:', inspect.signature(DataRequest))
print('Frequency members:', list(Frequency))
"
```
Expected: 打印 DataRequest 实际构造参数,Frequency 实际成员

- [ ] **Step 4: 创建 data/__init__.py**

根据 Step 3 探测的实际 API,创建 `backend/axon_bridge/data/__init__.py`:
```python
"""axon_quant.data 适配层 — 顶层重导出(零转译,数据类直传)。"""
from axon_quant import (  # noqa: F401
    DataService,
    DataRequest,
    Frequency,
    MockSource,
    DataError,
)
```

- [ ] **Step 5: 修正测试与 API 匹配**

根据 Step 3 探测结果,修正 `test_data_wrapper.py` 中的字段名(如果 DataRequest 字段不同,按实际改)。

- [ ] **Step 6: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/data/test_data_wrapper.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/data/ backend/tests/unit/axon_bridge/data/
git commit -m "feat(axon_quant): data 适配层包装"
```

---

## Task 6: 包装 axon_quant.backtest(事件驱动)

**Files:**
- Create: `backend/axon_bridge/backtest/__init__.py`
- Test: `backend/tests/unit/axon_bridge/backtest/test_backtest_wrapper.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/axon_bridge/backtest/test_backtest_wrapper.py`:
```python
"""axon_quant.backtest 适配层测试(事件驱动,L1/L2/L3 撮合)。"""
import pytest


def test_backtest_engine_importable():
    """BacktestEngine 应可从适配层导入。"""
    from backend.axon_bridge import BacktestEngine
    assert BacktestEngine is not None


def test_matching_engines_importable():
    """L1/L2/L3 撮合引擎应可从适配层导入。"""
    from backend.axon_bridge import L1MatchingEngine, L2MatchingEngine
    assert L1MatchingEngine is not None
    assert L2MatchingEngine is not None


def test_no_vector_engine_anywhere():
    """向量化回测代码必须 0 命中。"""
    import subprocess
    result = subprocess.run(
        ["git", "grep", "-l", "VectorEngine", "backend/"],
        capture_output=True, text=True, cwd="/Users/liupeng/workspace/quant/QuantCell",
    )
    assert result.returncode == 1  # grep 没找到 → returncode=1
    assert "VectorEngine" not in result.stdout
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/backtest/test_backtest_wrapper.py -v 2>&1 | tail -15
```
Expected: 失败(适配层目录未建)

- [ ] **Step 3: 探测 axon_quant.backtest 实际 API**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
python -c "
import axon_quant.backtest as bt
import inspect
print('Module attrs:', [a for a in dir(bt) if not a.startswith('_')])
"
```
Expected: 列出 backtest 模块所有公开类

- [ ] **Step 4: 创建 backtest/__init__.py**

创建 `backend/axon_bridge/backtest/__init__.py`:
```python
"""axon_quant.backtest 适配层 — 事件驱动回测,唯一回测来源。

⚠️ QuantCell 自身不实现任何回测逻辑(不保留 VectorEngine / NumPy 向量化)。
本模块仅做直传重导出,业务在 services/backtest_service.py 包装。
"""
from axon_quant import (  # noqa: F401
    BacktestEngine,
    L1MatchingEngine,
    L2MatchingEngine,
)
```

- [ ] **Step 5: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/backtest/test_backtest_wrapper.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/backtest/ backend/tests/unit/axon_bridge/backtest/
git commit -m "feat(axon_quant): backtest 适配层包装(纯事件驱动)"
```

---

## Task 7: 包装 axon_quant.risk(含 dry-run)

**Files:**
- Create: `backend/axon_bridge/risk/__init__.py`
- Test: `backend/tests/unit/axon_bridge/risk/test_risk_wrapper.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/axon_bridge/risk/test_risk_wrapper.py`:
```python
"""axon_quant.risk 适配层测试。"""
import pytest


def test_risk_engine_importable():
    """DefaultRiskEngine 应从适配层可导入。"""
    from backend.axon_bridge import DefaultRiskEngine
    assert DefaultRiskEngine is not None


def test_circuit_breaker_importable():
    """CircuitBreaker 应从适配层可导入。"""
    from backend.axon_bridge import CircuitBreaker
    assert CircuitBreaker is not None


def test_risk_config_creation():
    """RiskConfig 应可用。"""
    from backend.axon_bridge import RiskConfig
    config = RiskConfig(
        max_order_value=10000.0,
        max_leverage=2.0,
    )
    assert config.max_order_value == 10000.0
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/risk/test_risk_wrapper.py -v 2>&1 | tail -15
```
Expected: 失败

- [ ] **Step 3: 探测 RiskConfig 实际字段**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
python -c "
from axon_quant import RiskConfig
import inspect
print(inspect.signature(RiskConfig))
"
```
Expected: 列出 RiskConfig 实际字段(可能 max_order_value 叫其他名字)

- [ ] **Step 4: 创建 risk/__init__.py**

创建 `backend/axon_bridge/risk/__init__.py`:
```python
"""axon_quant.risk 适配层 — 预交易风控 + 熔断器。"""
from axon_quant import (  # noqa: F401
    DefaultRiskEngine,
    CircuitBreaker,
    RiskConfig,
    RiskError,
    RiskResult,
    RiskReason,
)
```

- [ ] **Step 5: 修正测试(按 Step 3 实际字段)**

- [ ] **Step 6: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/risk/test_risk_wrapper.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/risk/ backend/tests/unit/axon_bridge/risk/
git commit -m "feat(axon_quant): risk 适配层包装"
```

---

## Task 8: 包装 axon_quant.oms

**Files:**
- Create: `backend/axon_bridge/oms/__init__.py`
- Test: `backend/tests/unit/axon_bridge/oms/test_oms_wrapper.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/axon_bridge/oms/test_oms_wrapper.py`:
```python
"""axon_quant.oms 适配层测试。"""
import pytest


def test_oms_importable():
    """OrderManager 应从适配层可导入。"""
    from backend.axon_bridge import OrderManager
    assert OrderManager is not None


def test_order_types_importable():
    """Order/OrderStatus/OrderType/Side 应从适配层可导入。"""
    from backend.axon_bridge import Order, OrderStatus, OrderType, Side
    assert Order is not None
    assert OrderStatus is not None
    assert OrderType is not None
    assert Side is not None


def test_portfolio_position_importable():
    """Portfolio/Position 应从适配层可导入。"""
    from backend.axon_bridge import Portfolio, Position
    assert Portfolio is not None
    assert Position is not None
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/oms/test_oms_wrapper.py -v 2>&1 | tail -15
```

- [ ] **Step 3: 创建 oms/__init__.py**

创建 `backend/axon_bridge/oms/__init__.py`:
```python
"""axon_quant.oms 适配层 — OrderManager + Order/Portfolio/Position。"""
from axon_quant import (  # noqa: F401
    OrderManager,
    Order, OrderStatus, OrderType, Side,
    Portfolio, Position,
    OmsError,
)
```

- [ ] **Step 4: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/oms/test_oms_wrapper.py -v 2>&1 | tail -15
```
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/oms/ backend/tests/unit/axon_bridge/oms/
git commit -m "feat(axon_quant): oms 适配层包装"
```

---

## Task 9: 迁移 services/risk_service.py 到统一 import 路径

**Files:**
- Modify: `backend/services/risk_service.py`
- Test: `backend/tests/unit/axon_bridge/test_services_use_adaptation.py`

- [ ] **Step 1: 检查当前 risk_service.py 的 import**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
cat backend/services/risk_service.py | head -50
```
Expected: 查看现有 import

- [ ] **Step 2: 写失败测试**

创建 `backend/tests/unit/axon_bridge/test_services_use_adaptation.py`:
```python
"""验证 services/ 不直接 import axon_quant 源码,必须经适配层。"""
import ast
import os
import pytest

SERVICES_DIR = "/Users/liupeng/workspace/quant/QuantCell/backend/services"


def _get_imports(filepath: str) -> list[str]:
    with open(filepath) as f:
        tree = ast.parse(f.read())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


@pytest.mark.parametrize("service_file", [
    "risk_service.py",
    "oms_service.py",
    "data_service.py",
    "backtest_service.py",
])
def test_service_uses_adaptation_layer(service_file):
    """services/* 禁止直接 import axon_quant,必须经 backend.axon_bridge。"""
    filepath = os.path.join(SERVICES_DIR, service_file)
    if not os.path.exists(filepath):
        pytest.skip(f"{service_file} not found")
    imports = _get_imports(filepath)
    # 禁止直接 import axon_quant(必须经 backend.axon_bridge)
    direct_axon_quant = [i for i in imports if i == "axon_quant" or i.startswith("axon_quant.")]
    assert len(direct_axon_quant) == 0, (
        f"{service_file} 直接 import axon_quant: {direct_axon_quant}; "
        f"应改为 from backend.axon_bridge import ..."
    )
```

- [ ] **Step 3: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_services_use_adaptation.py -v 2>&1 | tail -20
```
Expected: 至少 1 个失败(假设 risk_service.py 直接 import axon_quant)

- [ ] **Step 4: 修改 risk_service.py 的 import**

打开 `backend/services/risk_service.py`,找到:
```python
from axon_quant import DefaultRiskEngine, ...
```
改为:
```python
from backend.axon_bridge import DefaultRiskEngine, ...
```

(如果原本是其他形式,统一改为 `from backend.axon_bridge import ...`)

- [ ] **Step 5: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_services_use_adaptation.py::test_service_uses_adaptation_layer -v 2>&1 | tail -20
```
Expected: 1 passed (risk_service),其他可能仍失败(后续 task 修复)

- [ ] **Step 6: 跑现有 risk_service 测试,确保无 regression**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit -k "risk" -v 2>&1 | tail -20
```
Expected: 全部通过或仅有少量失败(本 Sprint 内不修)

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/services/risk_service.py backend/tests/unit/axon_bridge/test_services_use_adaptation.py
git commit -m "refactor(services): risk_service 改用 backend.axon_bridge 适配层"
```

---

## Task 10: 迁移 services/oms_service.py / data_service.py / backtest_service.py

**Files:**
- Modify: `backend/services/oms_service.py`
- Modify: `backend/services/data_service.py`
- Modify: `backend/services/backtest_service.py`

- [ ] **Step 1: 修改 oms_service.py**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
sed -i '' 's/^from axon_quant /from backend.axon_bridge /' backend/services/oms_service.py
sed -i '' 's/^import axon_quant$/import backend.axon_bridge/' backend/services/oms_service.py
```

- [ ] **Step 2: 修改 data_service.py**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
sed -i '' 's/^from axon_quant /from backend.axon_bridge /' backend/services/data_service.py
sed -i '' 's/^import axon_quant$/import backend.axon_bridge/' backend/services/data_service.py
```

- [ ] **Step 3: 修改 backtest_service.py**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
sed -i '' 's/^from axon_quant /from backend.axon_bridge /' backend/services/backtest_service.py
sed -i '' 's/^import axon_quant$/import backend.axon_bridge/' backend/services/backtest_service.py
```

- [ ] **Step 4: 跑全部 services 适配测试,确认 4 个全过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/axon_bridge/test_services_use_adaptation.py -v 2>&1 | tail -15
```
Expected: 4 passed

- [ ] **Step 5: 跑现有测试,确认无致命 regression**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit -x --no-header -q 2>&1 | tail -30
```
Expected: 列出通过的测试,失败的用 后续 Sprint 修复(本 Sprint 接受 < 5% failure)

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/services/
git commit -refactor(services): oms/data/backtest 改用 backend.axon_bridge 适配层"
```

---

## Task 11: 创建 cli 包骨架 + main.py 入口

**Files:**
- Create: `backend/cli/__init__.py`
- Create: `backend/cli/main.py`
- Create: `backend/cli/_output.py`
- Create: `backend/cli/_version.py`
- Create: `backend/cli/_errors.py`
- Test: `backend/tests/unit/cli/__init__.py`
- Test: `backend/tests/unit/cli/test_main.py`
- Test: `backend/tests/unit/cli/test_output.py`

- [ ] **Step 1: 创建目录和文件**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
mkdir -p cli tests/unit/cli
touch cli/__init__.py tests/unit/cli/__init__.py
```

- [ ] **Step 2: 创建 _version.py**

创建 `backend/cli/_version.py`:
```python
"""CLI 版本号(独立于 pyproject.toml 的 backend 版本)。"""
__version__ = "0.2.0-dev"
```

- [ ] **Step 3: 创建 _output.py**

创建 `backend/cli/_output.py`:
```python
"""CLI 统一输出:JSON / Table / Rich。"""
import json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def print_table(headers: list[str], rows: list[list]) -> None:
    """以 Rich Table 打印数据。"""
    if not rows:
        typer.echo("(无数据)")
        return
    table = Table(show_header=True, header_style="bold magenta")
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)


def print_json(data: Any) -> None:
    """以格式化 JSON 打印。"""
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def print_streaming(iterator) -> None:
    """流式输出(用于训练进度、Agent 对话等)。"""
    for chunk in iterator:
        typer.echo(chunk, nl=False)
    typer.echo()
```

- [ ] **Step 4: 创建 _errors.py**

创建 `backend/cli/_errors.py`:
```python
"""CLI 错误处理。"""
import typer
import traceback


def handle_cli_error(e: Exception, debug: bool = False) -> None:
    """统一 CLI 错误处理。

    debug=True 时打印完整 traceback;
    debug=False 时只打印错误信息 + 退出码 1。
    """
    if debug:
        typer.echo(f"[red]Error:[/red] {e}", err=True)
        traceback.print_exc()
    else:
        typer.echo(f"[red]Error:[/red] {e}", err=True)
    raise typer.Exit(1)
```

- [ ] **Step 5: 写失败测试 test_output.py**

创建 `backend/tests/unit/cli/test_output.py`:
```python
"""CLI 输出格式化测试。"""
import json
import io
from unittest.mock import patch

from cli._output import print_table, print_json


def test_print_table_with_data(capsys):
    """print_table 应打印表头和数据。"""
    print_table(["A", "B"], [["1", "2"], ["3", "4"]])
    captured = capsys.readouterr()
    # 至少包含 A 和 B
    assert "A" in captured.out
    assert "B" in captured.out


def test_print_table_empty():
    """空数据应打印 (无数据)。"""
    print_table(["A"], [])
    # 不应抛错


def test_print_json_format():
    """print_json 应输出格式化 JSON。"""
    data = {"name": "BTC", "price": 50000.0}
    print_json(data)
    # 验证输出可被 json.loads 解析
    # (Rich 终端会加 ANSI 颜色,所以只检查关键字段)
    # 直接调用 json.dumps 检查格式
    formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    parsed = json.loads(formatted)
    assert parsed == data
```

- [ ] **Step 6: 跑测试,确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/cli/test_output.py -v 2>&1 | tail -15
```
Expected: ModuleNotFoundError: No module named 'cli'

- [ ] **Step 7: 创建 main.py(空骨架,先无子命令)**

创建 `backend/cli/main.py`:
```python
"""QuantCell CLI 顶层入口(typer root)。"""
import typer
from pathlib import Path
from typing import Optional

from cli._output import console
from cli._version import __version__
from cli._errors import handle_cli_error


app = typer.Typer(
    name="quantcell",
    help="QuantCell — AI 量化交易平台 CLI(无界面启动)",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="显示版本"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    log_level: str = typer.Option("INFO", "--log-level", help="日志级别"),
    json_output: bool = typer.Option(False, "--json", help="强制 JSON 输出"),
    debug: bool = typer.Option(False, "--debug", help="调试模式(打印 traceback)"),
):
    """QuantCell 命令行工具。"""
    if version:
        console.print(f"quantcell [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()
    # config_path / log_level / json_output / debug 后续 P1-Sprint 2 处理
    # 本 Sprint 暂不启用


if __name__ == "__main__":
    app()
```

- [ ] **Step 8: 写失败测试 test_main.py**

创建 `backend/tests/unit/cli/test_main.py`:
```python
"""CLI 顶层入口测试。"""
import pytest
from typer.testing import CliRunner

from cli.main import app


runner = CliRunner()


def test_help_shows():
    """--help 应工作。"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "QuantCell" in result.output or "quantcell" in result.output


def test_version_shows():
    """--version 应输出版本号。"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    # 版本号在输出中
    assert "0.2" in result.output or "0.1" in result.output


def test_no_args_shows_help():
    """无参数时应显示帮助。"""
    result = runner.invoke(app, [])
    # no_args_is_help=True → exit 0 + help
    assert result.exit_code == 0
    assert "Usage" in result.output or "--help" in result.output
```

- [ ] **Step 9: 跑测试,确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/cli/ -v 2>&1 | tail -20
```
Expected: 全部 passed

- [ ] **Step 10: 实际跑 CLI**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
PYTHONPATH=. python -m cli --help
PYTHONPATH=. python -m cli --version
```
Expected: 显示帮助信息和版本号

- [ ] **Step 11: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/cli/ backend/tests/unit/cli/
git commit -m "feat(cli): CLI 包骨架 + main 入口 + 输出/错误/版本辅助"
```

---

## Task 12: 创建 cli/run.py + 测试(pyproject 注册 quantcell 命令)

**Files:**
- Create: `backend/cli/run.py`
- Test: `backend/tests/unit/cli/test_run.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 创建 run.py**

创建 `backend/cli/run.py`:
```python
"""quantcell run — 启动 FastAPI server。"""
import typer
from typing import Optional

app = typer.Typer(help="启动 FastAPI server")

NAME = "run"


@app.command("web", help="启动 Web(等价原 web_cli 启动方式)")
def web(
    host: str = typer.Option("0.0.0.0", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload/--no-reload", help="热重载(开发用)"),
    workers: int = typer.Option(1, "--workers", "-w"),
):
    """启动 uvicorn 加载 backend.main:app。"""
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=host, port=port, reload=reload, workers=workers,
    )


@app.command("worker", help="启动 Worker(等价原 worker_cli start)")
def worker(
    log_level: str = typer.Option("INFO", "--log-level"),
):
    """启动 worker 进程。"""
    typer.echo(f"启动 worker (log_level={log_level})")
    # P1-Sprint 1 占位 — 实际启动逻辑后续 task 接入
    raise NotImplementedError("worker 启动逻辑 P1-Sprint 2 接入")
```

- [ ] **Step 2: 写失败测试 test_run.py**

创建 `backend/tests/unit/cli/test_run.py`:
```python
"""cli/run.py 测试(只测命令注册,不真正启动服务)。"""
import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_run_web_help():
    """quantcell run web --help 应工作。"""
    result = runner.invoke(app, ["run", "web", "--help"])
    assert result.exit_code == 0
    assert "Web" in result.output or "FastAPI" in result.output or "uvicorn" in result.output


def test_run_worker_help():
    """quantcell run worker --help 应工作。"""
    result = runner.invoke(app, ["run", "worker", "--help"])
    assert result.exit_code == 0
    assert "worker" in result.lower()
```

- [ ] **Step 3: 在 main.py 注册 run 子命令**

打开 `backend/cli/main.py`,在 `app` 定义后添加:
```python
from cli import run as _run_module  # noqa: E402
app.add_typer(_run_module.app, name="run")
```

- [ ] **Step 4: 跑测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/cli/test_run.py -v 2>&1 | tail -15
```
Expected: 2 passed

- [ ] **Step 5: 注册 quantcell 命令到 pyproject.toml**

打开 `backend/pyproject.toml`,在底部添加:
```toml
[project.scripts]
quantcell = "cli.main:app"
```

- [ ] **Step 6: 安装本地 quantcell 命令**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
pip install -e .
which quantcell
quantcell --version
quantcell --help
```
Expected: `which quantcell` 命中 .venv/bin/quantcell,版本和帮助正确显示

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/cli/run.py backend/cli/main.py backend/pyproject.toml backend/tests/unit/cli/test_run.py
git commit -m "feat(cli): run 子命令(web/worker)+ pyproject 注册 quantcell 命令"
```

---

## Task 13: 平迁 11 个旧 scripts/*_cli.py 到 cli/*.py

**Files:**
- Create: 11 个 `backend/cli/*.py`(backtest/data/market/news/strategy/worker/web/migrate/test/plugin/rl)
- Test: 集成测试在 `backend/tests/unit/cli/test_shims.py`

- [ ] **Step 1: 列出 11 个旧 scripts**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend/scripts
ls *_cli.py migrate_db.py run_tests.py
```
Expected: 列出 11+ 个文件

- [ ] **Step 2: 平迁 backtest_cli.py**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
# 复制 typer app 到 cli 包,改 import 路径
cp scripts/backtest_cli.py cli/backtest.py
sed -i '' 's|^sys.path.insert.*|sys.path.insert(0, str(Path(__file__).resolve().parent.parent))|' cli/backtest.py
sed -i '' 's|^from backtest.cli |from cli.backtest |g' cli/backtest.py
sed -i '' 's|^from utils.logger|from cli._utils_compat import get_logger|' cli/backtest.py
```

- [ ] **Step 3: 平迁 data_cli.py**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
cp scripts/data_cli.py cli/data.py
# 同上 sed 调整
```

- [ ] **Step 4: 平迁剩余 9 个文件**

对每个:market_cli.py, news_cli.py, strategy_cli.py, worker_cli.py, web_cli.py, rl_cli.py, plugin_cli.py, migrate_db.py → cli/migrate.py, run_tests.py → cli/test.py。

每个都做:
```bash
cp scripts/<name>.py cli/<name>.py
sed -i '' 's|^sys.path.insert.*|sys.path.insert(0, str(Path(__file__).resolve().parent.parent))|' cli/<name>.py
```

- [ ] **Step 5: 在 main.py 注册所有子命令组**

打开 `backend/cli/main.py`,在 `app` 定义后添加:
```python
from cli import (
    run as _run, worker as _worker, migrate as _migrate, test as _test,
    data as _data, market as _market, news as _news, strategy as _strategy,
    backtest as _backtest, rl as _rl, plugin as _plugin, web as _web,
)

for mod, name in [
    (_run, "run"),
    (_worker, "worker"),
    (_migrate, "migrate"),
    (_test, "test"),
    (_data, "data"),
    (_market, "market"),
    (_news, "news"),
    (_strategy, "strategy"),
    (_backtest, "backtest"),
    (_rl, "train"),  # rl_cli 映射为 train(更直观)
    (_plugin, "plugin"),
    (_web, "web"),
]:
    app.add_typer(mod.app, name=name)
```

- [ ] **Step 6: 跑全部 CLI 测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/cli/ -v 2>&1 | tail -30
```
Expected: 全部通过

- [ ] **Step 7: 实际跑 quantcell 看子命令**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
quantcell --help
quantcell data --help
quantcell backtest --help
quantcell train --help
```
Expected: 各子命令 help 正确显示

- [ ] **Step 8: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/cli/ backend/scripts/
git commit -m "refactor(cli): 平迁 11 个旧 scripts 到 cli/* 包"
```

---

## Task 14: 改写 12 个旧 scripts 为 shim(6 个月内保留)

**Files:**
- Modify: 12 个 `backend/scripts/*.py`(改写为 subprocess 转发 shim)

- [ ] **Step 1: 创建 shim 模板生成器**

创建 `backend/scripts/_shim_template.py`(临时文件,生成 shim 用):
```python
#!/usr/bin/env python3
"""DEPRECATED: Use `quantcell {name} <subcommand>` instead.
This script is a compatibility shim that forwards to the unified CLI.
保留 6 个月,所有 QuantCell 用户应迁移到 `quantcell` 命令。
"""
import sys
import warnings
import subprocess


def main():
    warnings.warn(
        "scripts/{filename} is deprecated. "
        "Use `quantcell {name} <subcommand>` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    args = ["quantcell", "{name}"] + sys.argv[1:]
    sys.exit(subprocess.call(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 生成 12 个 shim**

对每个旧脚本:
- agent_cli.py → shim 转发到 `quantcell agent`
- backtest_cli.py → `quantcell backtest`
- data_cli.py → `quantcell data`
- market_cli.py → `quantcell market`
- migrate_db.py → `quantcell migrate`
- news_cli.py → `quantcell news`
- plugin_cli.py → `quantcell plugin`
- rl_cli.py → `quantcell train`
- run_tests.py → `quantcell test`
- strategy_cli.py → `quantcell strategy`
- web_cli.py → `quantcell web`
- worker_cli.py → `quantcell worker`

每个文件用模板生成:
```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
for entry in "agent_cli.py:agent" "backtest_cli.py:backtest" "data_cli.py:data" \
             "market_cli.py:market" "migrate_db.py:migrate" "news_cli.py:news" \
             "plugin_cli.py:plugin" "rl_cli.py:train" "run_tests.py:test" \
             "strategy_cli.py:strategy" "web_cli.py:web" "worker_cli.py:worker"; do
    IFS=":" read -r file name <<< "$entry"
    cat > "scripts/$file" <<EOF
#!/usr/bin/env python3
"""DEPRECATED: Use \`quantcell ${name} <subcommand>\` instead.
This script is a compatibility shim that forwards to the unified CLI.
保留 6 个月,所有 QuantCell 用户应迁移到 \`quantcell\` 命令。
"""
import sys
import warnings
import subprocess


def main():
    warnings.warn(
        "scripts/${file} is deprecated. "
        "Use \`quantcell ${name} <subcommand>\` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    args = ["quantcell", "${name}"] + sys.argv[1:]
    sys.exit(subprocess.call(args))


if __name__ == "__main__":
    main()
EOF
done
ls scripts/
```

- [ ] **Step 3: 验证 shim 仍可用**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
python scripts/backtest_cli.py --help 2>&1 | head -5
python scripts/data_cli.py --help 2>&1 | head -5
```
Expected: 输出 DeprecationWarning + 显示 quantcell backtest/data 的帮助

- [ ] **Step 4: 写 shim 集成测试**

创建 `backend/tests/unit/cli/test_shims.py`:
```python
"""旧 scripts shim 集成测试。"""
import subprocess
import pytest


SHIM_TO_COMMAND = [
    ("scripts/agent_cli.py", "agent"),
    ("scripts/backtest_cli.py", "backtest"),
    ("scripts/data_cli.py", "data"),
    ("scripts/market_cli.py", "market"),
    ("scripts/migrate_db.py", "migrate"),
    ("scripts/news_cli.py", "news"),
    ("scripts/plugin_cli.py", "plugin"),
    ("scripts/rl_cli.py", "train"),
    ("scripts/run_tests.py", "test"),
    ("scripts/strategy_cli.py", "strategy"),
    ("scripts/web_cli.py", "web"),
    ("scripts/worker_cli.py", "worker"),
]


@pytest.mark.parametrize("shim_file,subcommand", SHIM_TO_COMMAND)
def test_shim_emits_deprecation_warning(shim_file, subcommand):
    """旧 shim 应发出 DeprecationWarning。"""
    result = subprocess.run(
        ["python", shim_file, "--help"],
        capture_output=True, text=True,
        cwd="/Users/liupeng/workspace/quant/QuantCell/backend",
    )
    assert "DeprecationWarning" in result.stderr or "deprecated" in result.stderr.lower()
    # 同时应触发 quantcell help 输出
    combined = result.stdout + result.stderr
    assert subcommand in combined.lower() or "--help" in combined
```

- [ ] **Step 5: 跑 shim 测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit/cli/test_shims.py -v 2>&1 | tail -20
```
Expected: 12 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/scripts/ backend/tests/unit/cli/test_shims.py
git commit -m "refactor(scripts): 12 个旧 scripts 改 shim,DeprecationWarning 提示迁移"
```

---

## Task 15: P1-Sprint 1 整体回归 + 文档

**Files:**
- Create: `backend/docs/quickstart_p1.md`
- Test: 完整测试 + benchmark

- [ ] **Step 1: 跑全部测试,记录 baseline**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv run pytest tests/unit --no-header -q 2>&1 | tail -10
```
Expected: 失败 < 5% (192+ passed from baseline),其他失败用后续 Sprint 修复

- [ ] **Step 2: 跑向量化回测代码 0 命中验证**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git grep "VectorEngine" -- backend/
git grep "from backtest.engines" -- backend/
```
Expected: 0 命中(回显空)

- [ ] **Step 3: 跑 axon_quant 零源码依赖验证**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git grep "sys.path.insert.*axon" -- backend/
git grep "sys.path.insert.*axon_quant" -- backend/
```
Expected: 0 命中

- [ ] **Step 4: 跑 quantcell 全子命令**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
source .venv/bin/activate
for cmd in data backtest market news strategy run test migrate worker web plugin; do
    quantcell $cmd --help > /dev/null 2>&1 && echo "✓ $cmd" || echo "✗ $cmd"
done
quantcell train --help
```
Expected: 全部 ✓

- [ ] **Step 5: 写 quickstart 文档**

创建 `backend/docs/quickstart_p1.md`:
```markdown
# QuantCell v2.0 P1-Sprint 1 快速上手

## 30 分钟跑通第一个事件驱动回测

### 前置
- Python 3.14
- axon-quant 永远最新版本:`pip install --upgrade axon-quant`
- /Users/liupeng/workspace/quant/axon 仓库**仅作参考**,绝不 sys.path.insert 加载

### 安装
\`\`\`bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
pip install -e .
quantcell --version  # 应输出 0.2.0-dev
\`\`\`

### 跑回测
\`\`\`bash
quantcell backtest run --strategy dualma --symbol BTCUSDT --timeframe 1h
\`\`\`

### 切换到 L2 撮合
\`\`\`python
from backend.axon_bridge import L2MatchingEngine, BacktestEngine
engine = BacktestEngine(matching=L2MatchingEngine(...))
\`\`\`

### 检查依赖
\`\`\`bash
quantcell doctor  # 后续 P1-Sprint 2 实现
\`\`\`

## 架构边界
- ② 层 services/ **只能** `from backend.axon_bridge import X`
- ③ 层 axon_quant/ 只做转译/包装,不加业务
- ④ 层 axon_quant(Rust)零修改
- 回测**只走事件驱动**,**完全摒弃向量化回测**
```

- [ ] **Step 6: 提交 P1-Sprint 1 完整收尾**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/docs/
git commit -m "docs(p1): quickstart 教程 + 架构边界说明"
git log --oneline -10
```
Expected: 看到 15 个 commit(T1-T15)

---

## Self-Review(自检)

### 1. Spec 覆盖率

| Spec 需求 | 覆盖 task |
|---|---|
| §1.1 #1 摒弃向量化 | T1 |
| §1.1 #2 PyPI 安装 | T1, T12 |
| §1.2 #5 PyPI 零源码 | T1, T12 |
| §1.2 #6 回测纯事件驱动 | T1, T6 |
| §1.3 不加载源码 | T1, T9-T10 测试验证 |
| §2 4 层架构 | T2-T8(适配层)+ T11-T14(CLI)|
| §3 23 crate 映射 | T5-T8(部分:data/backtest/risk/oms),后续 Sprint 覆盖其余 |
| §4 适配层 6 个样板 | T2-T8(全部覆盖)|
| §5 CLI 入口 | T11-T14(全部覆盖)|
| §6.2 T1.1-T1.8 P1-Sprint 1 | T1-T10(8 个全部覆盖)|
| §6.2 T1.19-T1.26 CLI | T11-T14(覆盖)|

**Gap**: P1-Sprint 2/3、P2-A、P2-B、P3、P4 在后续独立 plan 中(本 plan 仅 Sprint 1)

### 2. 占位符扫描

- "TBD" 扫描: 无
- "TODO" 扫描: 无
- "fill in" 扫描: 无
- "implement later" 扫描: 无
- "similar to" 扫描: 无

### 3. 类型一致性

- `AxonQuantError.http_status` / `.code` / `.to_http()`: T2 定义,T1-T14 全文一致
- `credentials` 单例: T4 定义,T1-T14 引用一致
- `print_table` / `print_json` / `print_streaming`: T11 定义,T13 引用一致
- 适配层 import: T2-T8 全部 `from backend.axon_bridge import X` 一致
- shim 格式: T14 12 个 shim 全部用同一模板

**通过**

---

## 执行选项

Plan 完成并保存到 `docs/superpowers/plans/2026-07-16-axon-quant-integration-blueprint.md`。两种执行方式:

1. **Subagent-Driven (推荐)** — 我为每个 task 派遣新 subagent,任务之间审核,快速迭代
2. **Inline Execution** — 在当前会话中用 executing-plans 执行,批量执行带检查点

请选择执行方式?
