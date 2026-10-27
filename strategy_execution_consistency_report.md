# QuantCell 策略脚本执行体系三环境一致性深度分析报告

**日期**：2026-10-27
**范围**：backend 回测（backtest）/ 模拟盘（paper）/ 实盘（live, 含 testnet）三条策略执行链路
**方法**：3 路并行代码调研 + 主线逐条亲验（直接读源码 + 运行时实测）。每条结论标注证据状态：
✅ = 本会话直接亲验（源码/运行实测）；◇ = subagent 调研提供具体行号（未逐行复核）

---

## 0. 执行摘要

| 维度 | 结论 |
|------|------|
| 1. 三环境链路是否打通 | **结构上打通**（同一加载器、同一内核主回路、同一适配器），但存在 4 个运营级断点：成交不落库、无风控接线、重启不恢复、假停止 |
| 2. 语义一致性 | **核心语义一致**：加载器唯一、`ratio_to_target_qty` 换算唯一、`run_mode` 仅在 LLM replay 一处合法生效。不一致项：`on_fill` 死钩子、`on_stop` 仅回测调用、bar 键名分叉（python 回退路径） |
| 3. 环境特异性分支 | 显式分支仅 2 处（`run_mode`→LLM replay、`trading_mode`→装配分岔），主回路无 mode 分支。硬编码：testnet URL ×2、initial_cash 100_000、engine_status 假数据 |
| 4. 信号/执行/周期/数据对齐 | 信号与执行对齐；**时间周期严重不对齐（P0）**：live 硬编码 1m 订阅、timeframe 形参失效；**特征注入不对齐（P0）**：paper/live 的 bar state 恒 None |
| 5. 风险清单 | P0 ×2（R1 周期错位、R2 特征注入缺失）+ P0 ×2 运营断点（B2 成交不落库、B3 无风控）+ P1 ~P2 若干，详见 §5 |

---

## 1. 三环境执行链路实测（维度一）

### 1.1 三条链路

```
回测   POST /backtest → backtest/routes.py:246 → backtest/service.py
        → engine_service.execute_backtest
        → StrategyLoaderService.load_strategy(run_mode="backtest")   [backtest/strategy_loader_service.py:116-189]
        → runner 分流 (engine_service.py:392-393)
             kernel(默认)  → worker.Kernel.run_history  → BacktestSink
             legacy        → worker.BacktestRunner
             python        → backtest_loop.BacktestLoop（Python 回退）

paper  POST /workers/{id}/start (trading_mode=paper)
        → strategy_manager.start_strategy (worker/strategy_manager.py:285-455)
        → load_strategy(run_mode="paper")
        → _assemble_rule_paper_driver (L423-455)
        → PaperDriver (adapter=None) → Python REST 轮询 feed_bar (L962-1043)
        → KernelPump → Kernel/BarLifecycle → PaperSink

live   start (trading_mode=testnet/live)
        → start_crypto_live (L703-803) / start_rl_live (L591-701)
        → load_strategy(run_mode="live")   [testnet 也标 "live"，L364-371]
        → LiveDriver + BinanceAdapter(WebSocket) → KernelPump → 实盘 sink
```

三条链路最终汇聚于同一内核编排：`axon-kernel` 的 `BarLifecycle::on_bar_closed` 九步 per-bar 流程，策略侧统一经 `strategy/rust_adapter.py::RustStrategyAdapter.decide → on_bar`。**主回路本身没有任何 mode 分支**（配合 AGENTS.md 声明 && engine_service/strategy_manager 亲读确认）。

### 1.2 断点清单（链路"打通"但运营能力缺失）

| # | 断点 | 严重度 | 证据 | 状态 |
|---|------|--------|------|------|
| B2 | **paper/live 成交、订单、持仓不落数据库**。`LiveTradeRecorder` / `crud.create_order_if_not_exists` / `create_trade_if_not_exists`（worker/event_handler.py:588, worker/crud.py:461/472）在全 backend 仅被 event_handler 自身与单测引用，主启动链路（strategy_manager）无任何实例化/subscribe 调用。docstring 写明应在 `_run_node_sync` 中 `recorder.subscribe(node.trader)`，但该调用从未发生 | P0 | 全库 grep 亲验（仅 event_handler.py + tests 命中） | ✅ |
| B3 | **三环境均无 pre-trade 风控接线**。Rust `risk.engine` 存在，RiskService / RiskMonitor 均为死代码；paper/live 装配处不注入风控，下单直通 | P1 | subagent 调研 + engine_status 中 `risk_available` 硬编码 True（旁证） | ✅◇ |
| B4 | **worker 路由重复注册**：`/{worker_id}/lifecycle/start` 与 `/stop` 在 worker/routes.py L313/L364 与 L1024/L1072 双重注册；FastAPI 先注册优先，后者为不可达死路由；且 L1072 的 stop 仅回 success 不停止任何线程（假停止） | P1 | grep 亲验 4 处注册 + L1072-1080 亲读 | ✅ |
| B5 | 后端重启后 running 状态 worker **不恢复**（core/lifespan.py 无恢复逻辑），live 策略静默停摆但 DB 状态仍 running | P1 | subagent 调研 | ✅◇ |
| B6 | **回测假停止**：`backtest/service.py` `stop_backtest`（L949-972）仅翻转任务状态文件，不中断引擎线程，内存照跑、结果照写 | P2 | 亲读 | ✅ |
| B1 | ~~`except ValueError, AttributeError:` 语法错误~~ → **裁决：非错误**。backend 运行于 Python 3.14（pyproject.toml `requires-python = ">=3.14"`），PEP 758 使无 `as` 的裸多类型捕获合法。实测 `py_compile.compile` 与 `import backtest.service` 均 exit=0。现存 5 处（backtest/service.py:945,961、utils/kline_file_manager.py:275,285、utils/file_log_manager.py:526）——合法但易误读为 Python 2 残留，且任何人将 requires-python 降到 <3.14 会立即全面炸裂 | 影响可读性，**解除 P0 告警** | py_compile 实测 + repr 字节检查 + requires-python 亲读 | ✅ |

### 1.3 无缝切换能力

- **回测 → paper/live**：同一 `load_strategy` 静态加载器（目录优先级 `strategy/templates` → `strategies`，`del sys.modules` 保证读磁盘最新版），同一个 `RustStrategyAdapter`，同一套 Action 语义。切换在结构上是「换装配、不换策略」，✅ 成立。
- **paper ↔ live**：两者都是 `KernelPump` + `BarLifecycle`，差异仅在数据泵（REST 轮询 vs WebSocket）与 sink（PaperSink vs 实盘 sink）。理论切换成本低，✅。
- **阻塞切换一致性的硬伤**是 §4 的 R1/R2：同一策略在回测/paper 用 N 分钟 bar，在 live 却每 1m 触发一次——这不是"切换断点"，而是"切换后行为改变"。

---

## 2. 语义一致性矩阵（维度二）

| 环节 | 回测 | paper | live | 一致性 | 状态 |
|------|------|-------|------|--------|------|
| 策略加载 | load_strategy("backtest") | load_strategy("paper") | load_strategy("live") | 同一加载器、同一候选目录、同等 params 透传（_instantiate_strategy L269-333） | ✅ |
| `run_mode` 影响 | 仅 `strategy/llm_replay.py:185-229 wrap_llm_provider`：规则策略完全无影响 | 同左（RecordingProvider） | 同左（RecordingProvider） | **唯一 run_mode 生效点是 LLM replay**，规则策略三环境语义逐字节一致 | ✅ |
| 指令解析 | Action→on_bar→ActionType | 同 | 同 | rust_adapter.decide L74-107 单一入口 | ✅ |
| 仓位换算 | `target_position_ratio × equity / price`（strategy/target.py:10-25 `ratio_to_target_qty`，含杠杆） | 同（经 StrategyHost） | 同 | **全系统唯一换算实现**，回测/paper/live 共用；hold 保持上次目标（rust_adapter L94-101） | ✅ |
| on_start | BacktestLoop L187 调用 | rust_adapter.__init__ L62 调用 | 同 | ✅ |
| on_bar | BacktestLoop L241 / rust_adapter L74 | 同 | 同 | ✅ |
| on_fill | **零调用（死钩子）** | 零调用 | 零调用 | 三环境一致地"不调"——钩子承诺未兑现，写了对 on_fill 有副作用的策略会静默失效 | ✅◇ |
| on_stop | 仅 BacktestLoop L271 调用；kernel 路径回测不调 | stop_strategy（strategy_manager L1129-1136）不调 | 同 | **不一致**：`on_stop` 实质是"仅 python 回退回测专用钩子" | ✅ |
| 参数来源 | 请求体 strategy_params（backtest/routes.py:246） | DB worker.params（json.loads 失败**静默 {}**，L318-328） | 同 | 回测参数走请求体、paper/live 走 DB——参数名空间一致但校验强度不同；DB 静默兜底 {} 会掩盖损坏配置 | ✅ |
| 输出格式 | BacktestResult + equity_curve 落盘 JSON（_convert_backtest_result L844-876） | kernel.snapshot 推送 {worker_id, equity, positions}（L1047-1065） | 同 | 输出格式差异属**合理环境差异**（批量结果 vs 实时快照），且 snapshot 契约 paper/live 相同 | ✅ |
| 交易记录落库 | 无（回测本来不落交易表） | **不落（B2）** | **不落（B2）** | paper 与 live 一致地缺失，前后端"成交明细"页面在两种模式下都无数据来源 | ✅ |

---

## 3. 环境特异性分支与硬编码盘点（维度三）

### 3.1 显式分支（仅 2 处，均有明确边界）

1. `run_mode` → `wrap_llm_provider`（llm_replay.py L185-229）：backtest→ReplayProvider（JSONL 查表、未命中抛 `ReplayMissError`，绝不真实请求 LLM）；paper/live→RecordingProvider（追加写）。**这是有意设计且方向正确**——回测禁止真实 LLM 调用、实盘录制供回放。HTTP 回测请求体是 JSON 无法携带 provider callable，`inner is None` 时直接放行（L202-205），即 HTTP 回测的 LLM provider 由服务内部组装，仍受 replay 门禁约束 ✅◇。
2. `trading_mode` → 装配分岔（strategy_manager L382-410）：`paper` → `_assemble_rule_paper_driver`；`testnet`/`live` → `start_crypto_live`；`rl` → `_load_rl_spec → build_rl_kernel → add_rl_strategy`（L330-351，**RL 策略不走源码加载器**，是第三条装配支线）。

### 3.2 硬编码与静默兜底

| 位置 | 内容 | 影响 | 状态 |
|------|------|------|------|
| strategy_manager L355-358 | 主网 live 有闸门硬拒；testnet 走 **live 链路**（真实连接币安合约测试网），`run_mode="live"` | testnet 本质是真实下单环境，schema 只描述 "paper/live"（worker/schemas.py:34 失实），用户可能把 testnet 误当"安全沙盒" | ✅◇ |
| start_crypto_live L768-770 / start_rl_live L650-656 | 硬编码 `https://testnet.binancefuture.com` | live 闸门解锁后无法真正连主网（URL 不随配置切换） | ✅◇ |
| _assemble_rule_paper_driver L448 / start_crypto_live L773 | initial_cash=100_000 | 与回测默认 10_000（engine_service.py L209 亲读确认）不一致 → **B7**：同一策略三环境本金口径不同，回测收益数字与 paper/live 不可直接对比 | ✅ |
| strategy_manager L312 | paper/live 的 timeframe 取 `trading_config["timeframe"]` | 形参传给 KernelConfig，但 live 下被引擎忽略（见 R1）——居民以为在控制周期，实际仅 paper/回测语义生效 | ✅ |
| strategy_manager L285 | `trading_mode` 缺省兜底 "testnet" | 与 schema 默认 "paper" 漂移；漏传字段会落到最危险档（真实连接测试网） | ✅◇ |
| engine_status L1242-1248 | `exchange:"binance" / mode:"paper" / exchange_connected:True / risk_available:True` 全部硬编码 | 状态页显示假数据，掩盖真实连接/风控状态 | ✅（亲读） |
| paper 泵 L962-1043 | limit=2 拉取、收市判定、REST URL 硬编码 | paper 数据泵与 live 泵（Rust WebSocket）代码完全不同源，R1 类错位风险在 paper 侧独立存在 | ✅◇ |

### 3.3 并存的双路径（历史残留）

- 新主链路（worker/strategy_manager.ts + Kernel）之外，`strategy/event_loop.py::EventDrivenLoop`（ticker 快照伪 bar）仍可独立运行，语义与新链路不同（非 kernel、无 BarLifecycle 九步）。
- `strategy/loop.py::StrategyLoop` 在 AGENTS.md 中被描述为实盘循环，**该文件实际不存在**（文档失实）。
- `realtime/` 模块与策略链路无接线（只服务 API 行情推送与落盘）。
- multi-symbol：paper 装配 ponytail 注释只挂首品种（L448 附近"多品种 ponytail 只挂首品种"）◇。

---

## 4. 信号生成 / 订单执行 / 时间周期 / 数据源对齐（维度四）

### 4.1 信号生成与订单执行 —— 对齐 ✅

- 信号：统一 `on_bar(bar: dict) -> Action`，三环境经同一 `RustStrategyAdapter`。
- 执行：统一 `BarLifecycle` 九步编排 + 各环境 `ExecutionSink`（BacktestSink / PaperSink / 实盘 sink）。回测 kernel ↔ legacy 由 `tests/unit/backtest/test_rust_runner_parity.py` 守护，kernel ↔ live 由 axon-quant kernel 单测 + M3 shadow oracle 守护 ✅。
- 注意：Python 回退路径（runner='python'）与 kernel 路径的 parity 测试覆盖 legacy 而非 kernel；kernel 与 BacktestLoop 之间无直接逐 bar parity 测试（依赖 shadow oracle）◇。

### 4.2 时间周期 —— **不对齐（本次最大发现，P0）**

**R1：live 环境 timeframe 失效，固定按 1m 触发 on_bar**

证据链三环全部亲验：

1. [binance.rs:494](file:///Users/liupeng/workspace/quant/axon_quant/crates/axon-exchange/src/adapters/binance.rs#L494)：订阅频道硬编码 `format!("{lower}@kline_1m")`，单测 L2477-2493 断言 `btcusdt@kline_1m`；`KernelConfig.interval` 不参与订阅。
2. [live_driver.rs](file:///Users/liupeng/workspace/quant/axon_quant/crates/axon-worker/src/live_driver.rs)：主循环 `pump.drain()`（L297）直接消费泵产出，**全文件无任何 1m→N m 升采样/重采样逻辑**。
3. [pump.rs:272-307](file:///Users/liupeng/workspace/quant/axon_quant/crates/axon-worker/src/pump.rs#L272-307)：`on_kline` 聚合与缺口检测均以 `kline.interval`（= 推送源固定 1m）为准。

后果：配置 timeframe="1h" 的策略在回测/paper 下每小时收到一个 1h bar 并触发一次 on_bar；在 live 下**每分钟**收到一个 1m bar 触发一次 on_bar。三重伤害：
- 指标语义错乱（DualMA 的 slow=30 从"30 小时"变成"30 分钟"），信号频率放大约 60 倍，在真实账户会产生截然不同且更频繁的交易；
- `lifecycle.rs:90-98` 将 1m 帧错误标注为 `config.interval`，导致下游事件/日志把 1m bar 标成 1h（元数据造假）；
- 该错位此前被"三环境同一主回路"的架构叙事掩盖——主回路确实同一，但入场数据的时间粒度不同。

**R3：三环境均无 interval 声明一致性校验**。paper 走 REST 直接灌 N m bar（与回测同粒度），live 被 R1 强制 1m——没有任何断言/警告提示用户 live 行为与配置不符。

### 4.3 数据输入源 —— 形状对齐、来源分叉、特征不对齐

| 环节 | 结论 | 状态 |
|------|------|------|
| bar dict 形状 | kernel 路径（回测 kernel/paper/live）统一 `timestamp` 键 + `symbol` + `state`；仅 python 回退 `BacktestLoop`（backtest_loop.py L216-224 亲读）用 `timestamp_ns` 键。同一策略类若直接读 bar["timestamp"]，在 runner='python' 下 KeyError/App 参数不同。落到策略代码约定不一致 | ✅（R5，P1） |
| 数据源 | 回测=历史数据适配器（KlineAdapter 等 10 类 data_type，factory.py L14-45）；paper=Python REST 轮询（limit=2）；live=Binance WebSocket。**来源天然不同**：撮合价、bar 边界、缺口行为无法逐 tick 对齐，靠"同引擎+同适配"收敛 | ✅ |
| 特征注入（R2，P0） | 回测走 FactorInjector→frame.states→`bar["state"]`；paper/live enqueue 时 state 恒 **None**（paper_driver.rs L222）◇。**因子/特征类策略三环境根本不等价**：回测里的特征信号在实盘会退化成无特征决策 | ✅◇ |
| fundingRate 语义边界 | `fundingRate` 作为 data_type 是特征列而非结算通道，混用会双重计费（engine_service 顶部注释 + 亲读确认已声明边界） | ✅ |
| bookDepth/bookTicker | 聚合的是 mid-price 合成价，非可撮合盘口（边界已声明） | ✅◇ |

---

## 5. 不一致点与风险分级总表

| 编号 | 问题 | 级别 | 影响 | 状态 |
|------|------|------|------|------|
| R1 | live 硬编码 1m 订阅、timeframe 失效、无升采样、元数据错标 | **P0** | 信号频率/指标周期三环境不等价，live 交易行为与回测/paper 预期脱节 | ✅ |
| R2 | paper/live 特征注入缺失（state 恒 None） | **P0** | 特征类策略三环境不等价，实盘退化 | ✅◇ |
| B2 | paper/live 成交/订单/持仓不落库 | **P0**（运营） | 交易明细、对账、复盘链条断裂 | ✅ |
| B3 | 无 pre-trade 风控接线（RiskService 死代码） | P1 | live 直接暴露无风控下单 | ✅◇ |
| B5 | 重启不恢复 running worker | P1 | live 静默停摆 | ✅◇ |
| R5 | bar 键名分叉（timestamp vs timestamp_ns，python 回退） | P1 | 跨 runner 策略兼容性陷阱 | ✅ |
| R4 | 旧 EventDrivenLoop 并存且语义不同 + AGENTS.md 描述 loop.py 不存在 | P1 | 双路径漂移、文档误导 | ✅◇ |
| B4 | lifecycle 路由双重注册（L1024/1072 死路由）+ stop 假停止 | P1 | API 契约不可达 | ✅ |
| B7 | initial_cash 口径：回测默认 10_000 vs paper/live 100_000 | P2 | 收益指标跨环境不可比 | ✅ |
| L285 | trading_mode 缺省兜底 testnet（与 schema 默认 paper 漂移） | P2 | 漏传字段落到真实连接档 | ✅◇ |
| B8 | engine_status 硬编码假数据（mode/risk/exchange_connected） | P2 | 状态面板失真 | ✅ |
| B6 | 回测假停止（仅改状态文件不杀线程） | P2 | 资源浪费、结果文件 与状态不符 | ✅ |
| on_fill | 死钩子（三环境零调用） | P2 | 策略侧 on_fill 副作用永不触发 | ✅◇ |
| on_stop | 仅 python 回退回测调用 | P2 | 清理逻辑在 paper/live 不执行 | ✅ |
| L318-328 | DB params 解析失败静默 {} | P2 | 配置损坏被掩盖 | ✅◇ |
| B1 解除 | PEP 758 裸多类型 except ×5（requires-python>=3.14 下合法） | 可读性 | 降级为风格问题；若放宽 python 下限会变 P0 | ✅ |

（◇ = 行号来自 subagent 调研，主线抽查关键处一致，未逐行复核）

---

## 6. 优化建议

**P0（先做，直接影响"三环境等价"承诺）**
1. **R1**：binance.rs 订阅频道按 `KernelConfig.interval` 参数化（或显式只支持 1m并在文档/启动日志强提示）；live_driver 增加基于 `BarAggregator` 的 N×1m→interval 聚合；lifecycle 的 bar 标注改用真实 kline.interval。验收标准：timeframe=1h 的 live 会话每 60 个 1m bar 才触发一次 on_bar，且 bar.timestamp 对齐整点。
2. **R2**：paper/live 的 enqueue 路径接入与回测相同的 FactorInjector（至少对带 `factor` 配置的策略告警拒绝启动，避免静默退化）。
3. **B2**：在 paper/live 启动装配处实例化 `LiveTradeRecorder(worker_id)` 并 `subscribe(node.trader)`（代码已备好，只差接线一处）。

**P1**
4. **B3**：接线 Rust risk.engine 或明确移除 UI 状态里的 risk 字段，不要显示 `risk_available:True`。
5. **B5**：core/lifespan 启动时扫描 DB running worker → 标记 interrupted（或恢复），二者选一必须做。
6. **B4**：删除 worker/routes.py L1024-1080 死路由；lifecycle stop 补真实停止语义。
7. **R5**：统一 bar dict 键名为 `timestamp`；BacktestLoop 内部转换时一次性 rename。
8. **R4**：冻结或迁移 EventDrivenLoop 调用方；修正 AGENTS.md 中 loop.py 失实描述。

**P2**
9. **B7**：统一默认 initial_cash（建议读同一 settings 默认 100_000），回测请求未显式给资金时与 paper/live 同口径。
10. on_stop 接入 stop_strategy 路径；on_fill 要么接线要么从 BaseStrategy 文档中移除承诺。
11. L318-328：DB params 解析失败改为 log warning + 拒绝启动（live 档）。
12. 5 处 PEP 758 裸 except 加括号 `except (ValueError, AttributeError):`（纯可读性，避免被 linter/人误判为 bug；同时使未来放宽 requires-python 时不炸）。
13. worker/schemas.py:34 `trading_mode` 描述改为 "paper/testnet/live" 并说明 testnet 为真实连接环境；L285 缺省兜底从 "testnet" 收紧为显式必填。

**架构层结论**：`"三种模式跑同一条主回路，差异只在装配"` 的架构叙事在**策略语义层**成立（加载器/适配器/换算/内核统一），但在**数据层**（订阅粒度 R1、特征注入 R2）与**运营层**（落库 B2、风控 B3、生命周期 B4/B5）尚未兑现。当前三环境等价性 = 回测≈paper（bar 粒度一致、特征一致），live 与前两者在 R1/R2 两个维度不等价。修复 P0 三项后，"无缝切换"才在行为意义上成立。
