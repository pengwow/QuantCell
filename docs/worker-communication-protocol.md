# Worker 通信协议（三轨现行版）

> P2-09 三轨收敛的协议基线。ZMQ 控制面**定性保留**（架构评审 D-09 驳回重写结论），
> 本文档把三条通信轨道的现行契约固化为单一出处，改动协议时先改本文档。

| 轨道 | 通道 | 用途 |
|------|------|------|
| 控制面 | ZMQ（命令/响应/事件） | 服务端 ↔ worker 进程：生命周期命令、状态回传、交易/心跳事件 |
| 日志面 | 本地文件（journal / 对账报告） | worker 决策留痕、账实对账报告落盘、归档与重新导入 |
| 数据面 | HTTP（paper 行情泵轮询） | paper 泵拉取 testnet 公共收市 K 线 |

## 1. 控制面：ZMQ 协议

实现：`backend/worker/protocol.py`（信封与校验）、`backend/worker/zmq_transport.py`（传输层）。

### 1.1 端口拓扑

| 端口 | 模式 | 方向 |
|------|------|------|
| 5559 | DEALER（worker，identity=`worker-{id}`）↔ ROUTER（orchestrator，bind） | orchestrator → worker 命令；worker → orchestrator 响应 |
| 5558 | PUSH（worker，connect）→ PULL（orchestrator，bind） | worker → orchestrator 事件流（单向，无响应） |

### 1.2 信封 schema（v1）

所有消息为 JSON dict，公共字段：

```json
{
    "schema_version": 1,        // 信封协议版本（P2-09 起）
    "type": "command|response|event",
    "worker_id": 11,
    "timestamp": 1724745600.0
}
```

按 `type` 追加的字段：

| type | 追加字段 | 说明 |
|------|----------|------|
| `command` | `cmd`、`params`、`request_id` | `cmd` ∈ ping / start / stop / restart / status / update_params |
| `response` | `request_id`、`status`（ok/error）、`data` | 响应对应的命令经 `request_id` 关联 |
| `event` | `event_type`、`payload` | `event_type` ∈ trade / heartbeat / log / order / position |

### 1.3 schema_version 语义

- 组装端（`make_command` / `make_response` / `make_event`）固定注入当前版本 `PROTOCOL_SCHEMA_VERSION = 1`。
- 校验端（`validate_message`）：
  - **缺失视为 v0**——存量旧版消息没有该字段，向后兼容读，不拒绝；
  - 非 int / 负数 / bool → 拒绝（`Invalid 'schema_version'`）；
  - **大于当前版本 → 拒绝**（`Unsupported schema_version`）：新版消费旧端会产生字段歧义，宁可显式失败。

升级协议时的流程：`PROTOCOL_SCHEMA_VERSION` +1 → 校验端按 v{N-1} 写降级兼容读 → 本文档同步。

## 2. 日志面：文件协议

### 2.1 journal（决策留痕）

| 文件 | 内容 |
|------|------|
| `backend/data/live/worker_{id}.jsonl` | 规则 / LLM 策略的 paper/live 决策与事件记录（JSONL，逐行一个 JSON 对象；行内容由 axon-quant Rust live_driver 写入，本仓库只消费与归档） |
| `backend/data/rl_live/worker_{id}.jsonl` | RL 策略同上 |

### 2.2 对账报告

命名与 journal 同目录（`report_path_for`，由 Rust `live_driver.rs` 落盘，两端共用手规则）：

| 文件 | 触发 |
|------|------|
| `worker_{id}.reconcile.json` | 对账**失败** |
| `worker_{id}.reconcile_last_ok.json` | 对账**通过** |

报告 schema：六类 break 字段（`reconciliation.py::_BREAK_FIELDS`，非空即账实不符）+
`frozen_instruments`（仅预警，不参与 clean 判定）：

```
position_breaks / missing_fills / extra_fills / ghost_orders /
orphan_local_orders / cash_break / frozen_instruments
```

clean 口径（与 Rust resume 守卫一致）：六类 break 全空即放行。

### 2.3 归档与重新导入

- **归档**（`StrategyManager.archive_journal`）：已停止 worker 的 journal 连同对账报告
  移入来源目录的 `archive/` 子目录，命名 `worker_{id}.{ts}.jsonl` /
  `worker_{id}.reconcile.{ts}.json`（`_unique_archive_path` 重名追加 `_1` 递增，永不覆盖）。
  归档即 fresh start：下次启动重新锚定基准权益，resume 守卫不再对旧 journal 对账。
- **重新导入**（`reconciliation.import_reconcile_reports`）：扫描现存对账报告，按文件内容
  md5 去重后写入 `worker_logs` 表（`RECONCILE_LOG_SOURCE = "reconciliation"`），
  同一报告重复导入不产生重复记录。

## 3. 数据面：HTTP 泵端点

实现：`backend/worker/pump_client.py`（typed client，P2-09 收敛；调用方 `strategy_manager.py`）。

### 3.1 端点与参数

```
GET https://testnet.binancefuture.com/fapi/v1/klines?symbol={api_symbol}&interval={timeframe}&limit={limit}
```

- 无签名、无凭证（testnet 公共行情）；`api_symbol` 形如 `BTCUSDT`（内部 `BTC/USDT` 去 `/`），
  `timeframe` 受 `_PAPER_INTERVAL_SECONDS` 白名单限制。
- 直连语义：client 使用显式清空代理的 urllib opener（`PAPER_NO_PROXY_OPENER`）——
  urllib 默认读系统代理，GUI 代理工具不在线会整条泵管线静默断流；同链路的
  requests / python-binance 只读环境变量，行为对齐为强制直连。

### 3.2 响应行 schema（PaperKline）

成功响应是原始行 list，每行 `["openTime", "open", "high", "low", "close", "volume", ...]`（数值为字符串），
由 `as_kline` 统一转换为 typed dict（`as_kline` 幂等，兼容 typed 输入）：

| 字段 | 类型 | 来源 |
|------|------|------|
| `open_time` | int | openTime，开市毫秒时间戳 |
| `open` / `high` / `low` | float | 四价 |
| `close` | float | 收盘价（决策只用收盘确认价） |
| `volume` | float | 成交量 |

错误形态：端点限频/参数错误时响应是 `{"code": ..., "msg": ...}` dict 而非 list，
`fetch_paper_klines` 显式抛 `ValueError`，由泵轮按常态异常路径降级告警（不重试堆积）。

### 3.3 泵轮消费规则（`_paper_pump_round`）

1. **收市判定**：`open_time + interval 毫秒 > now` 的行不喂（决策只用收盘确认价）；
2. **去重**：按 symbol 记录 `seen_open_ms`，只喂比上次新的行；
3. **时间戳换算**：`feed_bar` 吃开市时刻纳秒，事件时间戳由引擎按 interval 推成收市时刻。
