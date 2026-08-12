# P1-Sprint 2: 实盘交易所 + 凭证管理 + 多账号 + 8 策略模板

**Date:** 2026-07-17
**Status:** Design — Pending user review
**Owner:** QuantCell Core Team
**Target Release:** v2.2.0
**Spec 依据:** §6.3 of `2026-07-16-axon-quant-integration-blueprint.md`

---

## 1. 背景与目标

### 1.1 背景

P1-Sprint 1 已完成：
- axon_quant 适配层（`backend/axon_bridge/`）全打通
- 业务代码 0 直连 axon_quant
- 12 子命令统一 CLI（`quantcell`）
- 向量化回测代码全部删除，回测仅走 axon_quant 事件驱动
- Binance 7 种历史归档数据采集完成（aggTrades/trades/bookDepth/bookTicker/3 种 K 线 × 3 市场）

但**实盘交易通道**仍是空白：
- 现有 `BinanceClient` / `OKXAdapter` 在 `backend/exchange/binance/live_adapter.py` 是"概念实现"，**未接入 TradingEngine**（`backend/engine/trading_engine.py`），只能在脚本中直接调用
- 凭证管理（API key/secret）**无安全存储**，仅硬编码在 `.env` 或代码里
- 多账号场景（主/副/对冲/做市）**无模型**
- 预设策略模板只有 3 个（dual_ma/sma_crossover/rl_ppo），**未覆盖 8 类典型策略**，模板不够

### 1.2 目标

在 P1-Sprint 1 基础上，**纵向打通实盘交易主线**：

1. **凭证管理**：SQLite 加密表 + API key/secret 安全存储（机器指纹密钥 AES-256）
2. **多账号模型**：账号名 + UUID 标识，1 个用户可挂 N 个交易所账户
3. **8 个策略模板**：覆盖趋势 / 区间 / 回归 / 动量 / 套利 / 多因子 / RL / 反转 8 类典型场景
4. **TradingEngine 实盘接入**：8 个模板能一键部署到 Binance/OKX 实盘
5. **8 个模板的基线回测报告**：BTCUSDT 2024-07 → 2025-07 一年数据，每模板 1 份
6. **不动现有 K 线 / 归档数据流**

### 1.3 非目标

- **不实现做市商分润**（非 P1 范围）
- **不实现组合优化**（P2-A 范围）
- **不接入 DEX**（仅 CEX）
- **不实现 Web 钱包 / 硬件钱包**
- **不动 P0-Sprint 已交付部分**（axon_bridge 适配层 / 12 子命令 CLI / 7 种归档数据）

### 1.4 验收标准（必须全部通过）

1. `quantcell account add --name main --exchange binance --api-key XXX --api-secret YYY` 成功创建账号（API secret 加密入库，列表不可见原文）
2. `quantcell account list` 显示账号名 + 交易所 + UUID，**不显示** api secret
3. `quantcell account remove --name main` 删除账号凭证（软删除 + 加密抹除）
4. 8 个策略模板在 `backend/strategies/` 下：dual_ma, grid, mean_reversion, momentum, trend_follow, funding_arbitrage, cross_sectional, mean_reversion_rl
5. 8 个模板的 `on_bar` / `on_fill` 签名一致（继承 `BaseStrategy`），通过 `quantcell strategy validate --name <template>` 静态校验
6. 8 个模板的基线回测报告在 `backend/data/source/backtest_baselines/<template>_BTCUSDT_2024-07_2025-07.{json,md}` 各 1 份
7. `quantcell strategy deploy --name dual_ma --account main --symbol BTCUSDT` 调用 TradingEngine 启动实盘
8. 现有 axon_bridge 47 测试 + archive 89 测试 + 12 子命令全部不破坏
9. `quantcell account export --name main` 导出加密备份文件（不解密），可 `quantcell account import <file>` 恢复
10. 现有 K 线 / 归档数据流完全不动

---

## 2. 整体架构

### 2.1 模块布局

```
backend/
├── exchange/
│   ├── binance/live_adapter.py        # 已存在：升级为注入 TradingEngine
│   └── okx/okx_adapter.py             # 升级为注入 TradingEngine
├── credentials/                       # 新建：凭证管理
│   ├── __init__.py
│   ├── crypto.py                      # AES-256 + 机器指纹密钥
│   ├── store.py                       # SQLite 加密表 CRUD
│   ├── account.py                     # 账号模型（账号名 + UUID + exchange）
│   └── exceptions.py                  # 凭证相关异常
├── strategy/
│   ├── base.py                        # BaseStrategy 抽象（on_bar/on_fill 签名）
│   └── loader.py                      # 策略模板加载器
├── strategies/                        # 8 个策略模板（独立模块）
│   ├── dual_ma.py                     # 趋势 1
│   ├── grid.py                        # 区间
│   ├── mean_reversion.py              # 回归
│   ├── momentum.py                    # 动量
│   ├── trend_follow.py                # 趋势 2
│   ├── funding_arbitrage.py           # 套利
│   ├── cross_sectional.py             # 截面多因子
│   └── mean_reversion_rl.py           # RL 仓位管理
├── engine/
│   ├── trading_engine.py              # 升级：实盘 deploy 流程
│   └── deployer.py                    # 新建：策略 → 账户 → engine 绑定
├── backtest/
│   └── baseline.py                    # 新建：基线回测报告生成器
├── cli/
│   ├── account.py                     # 新建：account 子命令
│   └── strategy.py                    # 升级：validate / deploy 子命令
├── data/source/
│   └── backtest_baselines/            # 8 个模板 × 1 份 = 8 个回测报告
└── tests/unit/
    ├── credentials/                   # 凭证管理测试
    ├── strategies/                    # 8 模板测试
    └── baseline/                      # 基线回测测试
```

### 2.2 关键设计点

- **凭证存储**：用 `cryptography` 库的 `Fernet`（AES-128-CBC + HMAC）+ 机器指纹（`/etc/machine-id` + `socket.gethostname()`）派生密钥；sqlite 表用 SQLCipher？**不**，用普通 SQLite + Fernet 加密字段，密钥不入库
- **多账号**：账号表 `accounts(id UUID, name UNIQUE, exchange, api_key_id FK, created_at)` + 凭证表 `credentials(id UUID, api_key_enc, api_secret_enc, fingerprint_hash)` 拆表（凭证可独立轮换）
- **策略模板**：所有模板继承 `BaseStrategy`，统一签名 `on_bar(bar, ctx) -> Action` / `on_fill(fill, ctx) -> None`，模板只关心策略逻辑，不感知账户/凭证
- **TradingEngine deploy**：`Deployer.deploy(strategy, account, symbol) -> WorkerHandle`，把 strategy 注册到 engine + 用 account 凭证创建 ExchangeAdapter + 启动 StrategyLoop
- **基线回测**：复用 `BacktestLoop`（已事件驱动），固定 1 年 BTCUSDT 1h K 线，输出 `{total_pnl, sharpe, max_drawdown, win_rate, total_trades, report_path}`
- **CLI 入口**：在 `quantcell` 下加 `account` 子命令（add/list/remove/export/import），升级 `strategy` 子命令（加 validate/deploy/baseline）

### 2.3 核心抽象

```python
# 凭证抽象
class Account:
    id: UUID
    name: str           # "main" / "sub1" / "btc_only"
    exchange: ExchangeId  # BINANCE / OKX
    created_at: datetime

class Credential:
    id: UUID
    api_key_enc: bytes
    api_secret_enc: bytes
    fingerprint_hash: str   # 验证密钥派生自当前机器

class CredentialsService:
    def add_account(name, exchange, api_key, api_secret) -> Account
    def list_accounts() -> list[Account]   # 不返回 secret
    def get_credential(account_id) -> tuple[api_key, api_secret]   # 解密
    def remove_account(name) -> None
    def export_account(name) -> bytes   # 加密备份
    def import_account(data: bytes) -> Account

# 策略抽象
class BaseStrategy:
    def on_start(self, ctx) -> None: ...
    def on_bar(self, bar, ctx) -> Action: ...    # 必须实现
    def on_fill(self, fill, ctx) -> None: ...
    def on_stop(self, ctx) -> None: ...

# Deployer 抽象
class StrategyDeployer:
    def deploy(self, strategy_name, account_name, symbol, interval=1.0) -> WorkerHandle
    def stop(self, handle) -> None
```

---

## 3. 8 个策略模板清单

| # | 名称 | 类 | 核心思路 | 关键参数 | 适用 |
|---|---|---|---|---|---|
| 1 | `dual_ma` | DualMA | 趋势 1：快慢均线金叉死叉 | `fast=10, slow=30` | 强趋势 BTC |
| 2 | `trend_follow` | TrendFollow | 趋势 2：ATR 通道突破 + 跟踪止损 | `atr_period=14, multiplier=3.0` | 强趋势 BTC/ETH |
| 3 | `grid` | GridStrategy | 区间：等距挂单网格 | `lower=60000, upper=70000, levels=20` | 震荡 BTC/ETH |
| 4 | `mean_reversion` | MeanReversion | 回归：布林带 + RSI 反转 | `bb_period=20, rsi_period=14` | 震荡 ETH |
| 5 | `momentum` | MomentumStrategy | 动量：N 日收益率排序做多 Top K | `lookback=20, top_k=5` | 截面多品种 |
| 6 | `funding_arbitrage` | FundingArbitrage | 套利：现货做多 + 合约做空，吃资金费率 | `min_funding=0.0001` | 永续合约 |
| 7 | `cross_sectional` | CrossSectional | 截面多因子：动量 + 价值 + 波动率打分 | `factors=[mom, value, vol]` | 多品种轮动 |
| 8 | `mean_reversion_rl` | MeanReversionRL | RL 仓位管理：在 mean_reversion 信号上叠加 PPO | `signal=mean_reversion, rl_model=PPO` | BTC 主动管理 |

每个模板要求：
- 单一文件 `backend/strategies/<name>.py`，类名 PascalCase
- 继承 `BaseStrategy`
- 静态参数 dataclass，配置走环境变量或 CLI 传入
- 至少 1 个单元测试 `test_<name>.py`
- 1 份基线回测报告 `backend/data/source/backtest_baselines/<name>_BTCUSDT_2024-07_2025-07.{json,md}`

---

## 4. 数据模型

### 4.1 SQLite 表

```sql
-- 账号表
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,                -- UUID4
    name TEXT UNIQUE NOT NULL,
    exchange TEXT NOT NULL,             -- binance | okx
    credential_id TEXT NOT NULL,
    created_at TEXT NOT NULL,           -- ISO 8601 纳秒
    deleted_at TEXT,                    -- 软删除
    FOREIGN KEY (credential_id) REFERENCES credentials(id)
);

-- 凭证表（加密字段）
CREATE TABLE credentials (
    id TEXT PRIMARY KEY,                -- UUID4
    api_key_enc BLOB NOT NULL,          -- Fernet 加密
    api_secret_enc BLOB NOT NULL,
    fingerprint_hash TEXT NOT NULL,     -- 当前机器指纹哈希
    created_at TEXT NOT NULL,
    rotated_at TEXT
);

-- 索引
CREATE INDEX idx_accounts_name ON accounts(name) WHERE deleted_at IS NULL;
```

### 4.2 存储位置

- `backend/data/credentials.db`（SQLite 文件，git ignore）
- 机器指纹 = SHA256(`/etc/machine-id` + hostname + MAC)[:32]
- 加密使用 `cryptography.fernet.Fernet(machine_key)`

### 4.3 备份格式

```python
# export 输出
{
    "version": 1,
    "account": {"name": "main", "exchange": "binance", "id": "uuid"},
    "credential_enc": "base64(...Fernet...)",   # 用导出密码再加密一次
    "fingerprint_hash": "...",
    "exported_at": "2026-07-17T10:00:00.000000000+08:00"
}
```

---

## 5. 关键流程

### 5.1 凭证管理流程

```
add account:
  user → quantcell account add --name main --exchange binance --api-key XXX --api-secret YYY
       ↓
  CredentialsService.add_account(name, exchange, api_key, api_secret)
       ↓
  credential_id = uuid4()
  api_key_enc = Fernet.encrypt(api_key.encode())
  api_secret_enc = Fernet.encrypt(api_secret.encode())
  fingerprint_hash = sha256(machine_id + hostname + mac)
       ↓
  INSERT INTO credentials + INSERT INTO accounts
       ↓
  print("✓ Account 'main' created (UUID: xxx)")

list accounts:
  SELECT id, name, exchange, created_at FROM accounts WHERE deleted_at IS NULL
       ↓
  print table (no secret fields)
```

### 5.2 策略部署流程

```
quantcell strategy deploy --name dual_ma --account main --symbol BTCUSDT
       ↓
  Deployer.deploy("dual_ma", "main", "BTCUSDT")
       ↓
  1. credentials = CredentialsService.get_credential_by_name("main")
  2. exchange_adapter = ExchangeAdapterFactory.create(
         exchange=binance, api_key, api_secret
     )
  3. strategy = StrategyLoader.load("dual_ma")
  4. engine = TradingEngine()
  5. engine.register_strategy(strategy, symbols=["BTCUSDT"])
  6. loop = StrategyLoop(adapter=exchange_adapter, strategy=strategy, symbol="BTCUSDT")
  7. loop.start()
       ↓
  WorkerHandle {worker_id, status: "running"}
       ↓
  print("✓ Strategy 'dual_ma' deployed on account 'main' for BTCUSDT (worker_id: xxx)")
```

### 5.3 基线回测流程

```
quantcell strategy baseline --name dual_ma --symbol BTCUSDT --start 2024-07-01 --end 2025-07-01
       ↓
  1. data = KLineLoader.load("BTCUSDT", "1h", start, end)  # 复用现有
  2. strategy = StrategyLoader.load("dual_ma")
  3. loop = BacktestLoop(initial_cash=100_000)
  4. result = loop.run(strategy, data, "BTCUSDT")
  5. report = {
       "template": "dual_ma",
       "symbol": "BTCUSDT",
       "period": "2024-07-01~2025-07-01",
       "total_pnl": result.total_pnl,
       "sharpe_ratio": result.sharpe_ratio,
       "max_drawdown": result.max_drawdown,
       "win_rate": result.win_rate,
       "total_trades": result.total_orders,
       "report_path": "data/source/backtest_baselines/dual_ma_BTCUSDT_2024-07_2025-07.md"
     }
  6. write json + md report
       ↓
  print("✓ Baseline report: <path>")
```

---

## 6. 范围与限制

### 6.1 安全约束

- API secret 在 DB 中永远加密；list 时**绝不返回** secret
- 仅授权进程（`/api/v1/...` + 异步 worker）可调用 `get_credential` 解密
- 软删除：账号 `deleted_at` 不为 NULL，凭证 30 天后硬删
- 机器指纹验证：换机器导入备份时报错

### 6.2 兼容性

- 现有 `BinanceDownloader` / 归档数据流 / 12 子命令 / axon_bridge 适配层**完全不动**
- 8 个新策略模板走 `BaseStrategy` 抽象，与 P1-Sprint 1 业务代码兼容
- K 线表 `crypto_spot_klines` / `crypto_future_klines` 保留，不迁移

### 6.3 风险

- **R1**：8 个策略模板可能部分策略不收敛（特别是 funding_arbitrage 在熊市有效 / 牛失效）→ 每个模板独立 fail-fast 基线回测，PnL < 0 仍交付（用户自评）
- **R2**：凭证 DB 损坏 → 备份文件 + 机器指纹校验可恢复
- **R3**：TradingEngine 实盘接口与现有 risk/oms 适配层不匹配 → Deployer 加 `dry_run` 模式，先验证信号流不下单
- **R4**：OKX 适配器未充分测试 → Sprint 2 末做 1 次小资金实盘验证（< $100）

### 6.4 不在范围内

- 实盘监控 dashboard（前端 P2-B 范围）
- 仓位管理 UI（前端 P2-B 范围）
- 多交易所聚合（仅 Binance + OKX 单点）
- 模拟盘（paper trading）独立入口（用 `risk_test_mode` 即可）
- 凭证多设备同步（仅本机）

---

## 7. 与 P1-Sprint 1 / P2-A 关系

| 内容 | Sprint | 状态 |
|---|---|---|
| axon_bridge 适配层 | P1-Sprint 1 | ✅ |
| 12 子命令 CLI | P1-Sprint 1 | ✅ |
| 7 种历史归档数据 | P1-Sprint 1 | ✅ |
| **凭证管理 + 多账号** | **P1-Sprint 2** | ⏳ |
| **TradingEngine 实盘 deploy** | **P1-Sprint 2** | ⏳ |
| **8 个策略模板 + 基线报告** | **P1-Sprint 2** | ⏳ |
| RL 训练 + 推理 + 注册 | P2-A Sprint 1 | 未启动 |
| HPO + Tracker + Ensemble | P2-A Sprint 2 | 未启动 |
| LLM 接入 | P2-A Sprint 3 | 未启动 |
| swarm + Agent 注册 | P2-B Sprint 1 | 未启动 |

---

## 8. 待确认事项

- [ ] 8 策略中 `mean_reversion_rl` 需要 stable-baselines3；如不希望引入 ML 依赖，改为 `mean_reversion_v2`（信号融合而非 RL）
- [ ] 凭证 DB 位置 `backend/data/credentials.db` 是否符合项目 .gitignore 规范
- [ ] 基线回测时长（默认 1 年）是否合理
- [ ] 8 个模板中是否要加 LLM 决策类（如 `llm_sentiment`），P1-Sprint 2 末会过 LLM spec
