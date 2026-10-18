# 非 K 线数据类型放行 Rust BacktestRunner —— 方案

日期：2026-10-18
状态：已实施（批 1）+ 已实施（批 2 特征通道）+ 已实施（结算口径有界版）；批 3 与「乘数入账」未做
相关代码：[engine_service.py](../backtest/engine_service.py)、[data_adapters/](../backtest/data_adapters/)、[rust_adapter.py](../../strategy/rust_adapter.py)

## 1. 目标与范围

**目标**：让 `engine_service` 的 Rust 原生编排路径（`BacktestRunner`）接受**非 K 线**数据类型，
消除「只有 `data_type == "kline"` 才走 Rust、其余全走 Python `BacktestLoop`」的分叉。

**不在本方案内**：原生 tick / 逐档 book 驱动的撮合（即「一根 bar 一个决策」之外的步进模型）。
那需要 Rust 侧非 bar 编排内核（复用 `axon-backtest` 的 L2/L3 撮合 + 事件驱动步进），属独立立项。

## 2. 现状核查（已实测）

### 2.1 回测数据的两条入口

[engine_service.py:123-164](../backtest/engine_service.py#L123-L164)：

- `data_type == "kline"` → `provider.load_multiple(...)`，直接拿 OHLCV DataFrame；
- 其他类型 → `provider.load_multiple_data(...)` → `DataAdapterFactory` 选适配器，
  返回 `{data, features, feature_dataframe}`；`feature_dataframe` 取 `AdapterResult.features`，
  `features` 取 `metadata["features_dict"]`。

放行 gate 在 [engine_service.py:236](../backtest/engine_service.py#L236)：
`use_rust_runner = runner_mode == "rust" and data_type == "kline"`。

### 2.2 适配器输出契约

四类适配器（[factory.py:14-22](../backtest/data_adapters/factory.py#L14-L22)）**都已把数据聚合成 bar 形状**：

| 适配器 | 覆盖 data_type | `data` 形状 |
|--------|---------------|-------------|
| `KlineAdapter` | `kline` / `markPriceKlines` / `indexPriceKlines` / `premiumIndexKlines` | 大写 OHLCV + `timestamp`（ns） |
| `TickAdapter` | `aggTrades` / `trades` | 聚合的 OHLCV（大写）+ `timestamp` |
| `OrderBookAdapter` | `bookDepth` / `bookTicker` | mid-price 聚合的 OHLCV + `feature_mid_price` / `feature_spread` |
| `DerivAdapter` | `fundingRate` / `openInterest` | `markPriceKlines` 的 OHLCV + `feature_funding_rate` / `feature_open_interest*` |

共同点：`AdapterResult.data` 是 **大写 `Open/High/Low/Close/Volume` + int64 纳秒 `timestamp` 列**、
索引已 `reset_index`（[orderbook_adapter.py:65-79](../backtest/data_adapters/orderbook_adapter.py#L65-L79)、
[deriv_adapter.py:52-55](../backtest/data_adapters/deriv_adapter.py#L52-L55)）。

### 2.3 Rust 路径能否直接吃这些帧（实测）

用 `KlineAdapter` 风格帧（大写 OHLCV + int64 ns `timestamp` + `feature_*` 列 + RangeIndex）实跑：

```text
clean_ohlcv_df(df)          → DatetimeIndex，列归一为 open/high/low/close/volume
_df_to_rust_bars(clean)     → timestamp = 1700000000000000000（与输入完全一致）
```

结论：`_run_rust_single` 的入口链路（[engine_service.py:620-622](../backtest/engine_service.py#L620-L622)）
**无需改动**即可消费适配器输出。`clean_ohlcv_df` 的小写化 + 纳秒→Timestamp 转换对 int64 ns 正确，
`_df_to_rust_bars` 的 `to_datetime().dt.as_unit("ns").astype("int64")` 也能精确还原。

### 2.4 既有断点：适配器的 `feature_*` 列根本没有进特征通道

`clean_ohlcv_df` 只保留 `timestamp + OHLCV`，`feature_mid_price` / `feature_spread` /
`feature_funding_rate` 等列**被丢弃**；而 `AdapterResult.features`（是否提供这些特征帧）
在四个适配器里都是 `None`，`metadata` 也只给 `has_*_feature: True` 这类标记。
两条路径都不例外（Python 路径同样拿 `feature_dataframe=None`，见
[engine_service.py:259-266](../backtest/engine_service.py#L259-L266)）。

**即：非 K 线回测目前是「纯价格」回测——非 K 线数据唯一带出来的特征（mid price / spread /
funding rate / open interest）全丢。** 这是既有断点，与放行与否无关。

### 2.5 已经对齐、不需要重新设计的部分

- **品种**：Python 路径 futures 用 `swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)`
  （[backtest_loop.py:134-139](../backtest/backtest_loop.py#L134-L139)），与 Rust `futures=True`
  的 USD 保证金 / 乘数 1.0 一致（已有期货 parity 测试覆盖）。
- **资金费结算**：Rust 侧 `funding_by_symbol` 与 Python 路径的 funding 查找表同口径（已有 parity 测试）。
- **多品种**：按「每品种独立跑一个 runner」执行，跨品种聚合留在 Python 侧（与 kline 现状一致）。

## 3. 方案：分批放行

### 批 1（本方案落地内容）

把 gate 从「等于 `"kline"`」放宽为「属于适配器已聚合为 bar 的 10 个 data_type」：

```text
kline / markPriceKlines / indexPriceKlines / premiumIndexKlines   （KlineAdapter）
aggTrades / trades                                                （TickAdapter）
bookDepth / bookTicker                                            （OrderBookAdapter）
fundingRate / openInterest                                        （DerivAdapter）
```

注意两个语义边界，必须在代码注释与文档里写死：

1. **`fundingRate` 作为 data_type ≠ 资金费结算通道**：前者是 `DerivAdapter` 产出的
   `feature_funding_rate` 特征列（本轮还不进特征通道，见 2.4）；后者是 `_build_rust_funding`
   的结算查找表，仅在 `trading_mode == "futures"` + `provider.load_funding_rate()` 有值时生效。
   两者不得混用，否则会双重计费。
2. **`bookDepth` / `bookTicker` 聚合出的 OHLCV 是 mid-price 合成价**，不是可撮合盘口深度。
   这与 Python 路径现状一致（parity 可保证两条路径一致，但不代表策略在这类数据上有意义）。

### 后续批次（不在本方案）

- 批 2：把适配器 `feature_*` 列接进特征通道（`state["features"]`）。**必须两条路径同改**，
  否则 parity 被破坏；建议单独提案。
- 批 3：原生 tick / 逐档 book 驱动撮合（Rust L2/L3 + 非 bar 步进），独立立项。

## 4. 改动点清单（批 1）

| 文件 | 改动 |
|------|------|
| [engine_service.py](../backtest/engine_service.py) | 新增模块级常量 `RUST_RUNNER_DATA_TYPES`（上述 10 个）；gate 改为 `data_type in RUST_RUNNER_DATA_TYPES`；模块 docstring 与 gate 处注释同步反映新放行集合与两条语义边界 |
| [AGENTS.md](../../AGENTS.md) | 「BacktestRunner 放行条件」从「kline 数据类型」改为「上述 10 个已聚合为 bar 的 data_type」 |
| [test_rust_runner_parity.py](../tests/unit/backtest/test_rust_runner_parity.py) | `_StubProvider` 增 `load_multiple_data`（返回 `AdapterResult` 风格对象）；新增适配器帧契约测试 + 参数化的非 K 线 parity 测试 |

`_run_rust_single` / `RustStrategyAdapter` / Rust 侧**均不需要改**（2.3 已实测）。

## 5. 测试与验收口径

1. **适配器帧契约测试**（不依赖真实 parquet）：对四类适配器各造一个代表性帧
   （大写 OHLCV + int64 ns `timestamp` + 各自的 `feature_*` 列），断言
   `clean_ohlcv_df` → `_df_to_rust_bars` 后时间戳与输入逐位相等、列归一正确。
2. **非 K 线 parity 测试**：沿用现有 `_assert_parity` / `_assert_deep_parity`
   （[test_rust_runner_parity.py](../tests/unit/backtest/test_rust_runner_parity.py)），
   参数化 10 个 data_type × {spot, futures}，确认 Rust 路径与 `runner='python'` 回退路径
   在 fills / orders / pnl / final_nav / max_dd / fees / win_rate / final_positions /
   equity_curve 上一致。
3. **默认路径断言**：`test_default_runner_uses_rust` 扩展到非 K 线 data_type
   （避免 gate 被改回 `== "kline"`）。
4. 回归：`pytest tests/unit/backtest` + `tests/integration` 全绿。

## 6. 风险与未决项

- **R1（低）**：`TickAdapter` / `OrderBookAdapter` 的聚合 interval 与"策略期望的 bar 周期"可能不一致
  （`aggTrades` 默认 5m、`bookTicker`/`bookDepth` 取 `interval or "1m"`）。放行后这类"隐式降采样"
  会从 Python 路径原样带到 Rust 路径——两条路径一致，因此不破坏 parity，但值得在 UI/CLI 上提示。
  现状不改。
- **R2（已修，批 2）**：2.4 的特征断点已在本轮修掉：`adapter_feature_frame()` 把
  `feature_*` 列抽成特征帧（去前缀、纳秒对齐），喂进两条路径共用的 `feature_dataframe`，
  并有「策略真读到 mid_price、两侧 fills > 0」的 parity 用例兜底。
- **R3（已部分修，有界版）**：`market="cm"` 的结算方式已如实标注为 `coin_margin`
  （`market → settle` 推导，两条路径同改），但 `contract_size` 仍只是品种元数据、
  默认 1.0，且引擎未把乘数计入名义价值/盈亏 —— 账面口径仍是近似，属上文的待立项。

## 8. 实施记录（2026-10-18）

| 项 | 落地内容 | 提交 |
|----|---------|------|
| P1 放行 | `RUST_RUNNER_DATA_TYPES`（10 类白名单）替换 `== "kline"` gate；注释写死两个语义边界 | QuantCell `bdb07c1` |
| 批 2 特征通道 | 新增 `adapter_feature_frame()`：`feature_*` 列 → 去前缀特征帧（纳秒对齐）；Python 与 Rust 两条路径共用同一 `feature_dataframe` 入口 | QuantCell `bdb07c1` |
| P2 契约测试 | 适配器帧 → `clean_ohlcv_df` → `_df_to_rust_bars` 的纳秒逐位保留断言；feature 帧派生的三个分支 | QuantCell `bdb07c1` |
| P3 parity 测试 | 9 类非 K 线 `_assert_deep_parity`、非 K 线默认走 Rust、未放行类型回退 Python、策略读到 `mid_price` 的两路径 fills>0 | QuantCell `bdb07c1` |
| 结算口径 | `market` → `settle` 推导（cm → coin_margin）两条路径同改；`axon_quant.worker.BacktestRunner` 新增 `settle` / `contract_size` | QuantCell `4adfe83`、axon_quant `387061f` |
| P4 文档 | AGENTS.md 放行条件与边界；本文件状态收敛 | 同上 |

**实施中发现、需另立项的**：

1. `contract_size` 只是品种元数据（`axon-backtest` engine.rs 挂着 0.8.0 待办），
   币本位账务仍是近似 —— 要做对需「离线面值表 + 引擎侧乘数入账 + `ratio → 合约张数`换算」。
2. 本地 `maturin build --release` 产出的 wheel 解压进 venv 后 `import` 会被 SIGKILL
   （macOS 校验/签名问题），`maturin develop` 则正常 —— 本地装扩展请用 `make python-develop`
   （axon_quant 仓库的 `make python-develop` / `python-test`）。axon_quant 新增的 CI
   `python-test` job 用的正是 `maturin develop`。

## 7. 分步任务

- **P1**：`engine_service.py` 加放行集合 + gate 改写 + 注释/docstring 对齐（含两条语义边界）。✅
- **P2**：`_StubProvider` 支持 `load_multiple_data`，补适配器帧契约测试。✅
- **P3**：补 10 个 data_type 的无关 parity 参数化测试 + 默认路径断言扩展。✅
- **P4**：`AGENTS.md` 放行条件更新；`pytest tests/unit/backtest tests/integration` 回归。✅
- **批 2**：适配器 `feature_*` 列接入特征通道（两条路径同改）。✅
- **结算口径**：`market → settle` 推导 + `contract_size` 显式配置。✅（有界版，见上）
- **待立项**：批 3 原生 tick / 逐档 book 撮合；合约面值表 + 引擎侧乘数入账。
