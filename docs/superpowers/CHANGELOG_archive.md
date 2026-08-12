# Binance 历史归档数据采集 — Changelog

> 范围: 7 种归档数据 × 3 个市场 (spot / um / cm) = 21 种组合采集、查询、UI 全链路
> 设计: [docs/superpowers/specs/2026-07-16-binance-archive-tick-data-design.md](specs/2026-07-16-binance-archive-tick-data-design.md)
> 实施 plan: [docs/superpowers/plans/2026-07-16-binance-archive-tick-data.md](plans/2026-07-16-binance-archive-tick-data.md)

## 一、Commit 列表 (按 Task 1-18 顺序)

### 后端 — Task 1-14 (基础架构 + 业务编排 + API + CLI)

| Task | Commit  | 描述 |
|------|---------|------|
| 1    | `d3940b5` | kinds enum + URL builder for 7 archive types × 3 markets |
| 2    | `02d3fae` | BaseBinanceArchiveDownloader + archive_meta stub |
| 3    | `804a855` | BinanceArchiveFactory with 7×3 registry |
| 4    | `8200a36` | full _meta.json read/write with parquet scan |
| 5    | `f4d0dd1` | AggTradesFetcher complete implementation |
| 6    | `e152bb4` | TradesFetcher complete implementation |
| 7    | `518a724` | BookTickerFetcher complete implementation |
| 8    | `62868e9` | BookDepthFetcher with nested bids/asks flatten |
| 9    | `56f266b` | MarkPriceKlinesFetcher complete implementation |
| 10   | `b70cca9` | IndexPriceKlinesFetcher complete implementation |
| 11   | `2ad7296` | PremiumIndexKlinesFetcher complete implementation |
| 12   | `f5bab4d` | ArchiveService business orchestration |
| 13   | `ad18b30` | 6 REST endpoints for archive management |
| 14   | `2f0cdf8` | CLI subcommands (download / list / meta) |

### 前端 — Task 15-17

| Task | Commit  | 描述 |
|------|---------|------|
| 15   | `8f00e47` | frontend API client + types |
| 16   | `879b67d` | DataCollectionPage multi-kind selector |
| 17   | `b809834` | DataManagementPage archive browser tab |

### 自检 — Task 18

| Task | Commit  | 描述 |
|------|---------|------|
| 18   | `21569e5` | self-check script for end-to-end verification |

---

## 二、关键功能

### 1. 数据种类与市场组合 (21 种)

**7 种数据**:
- aggTrades — 聚合成交 (Tick)
- trades — 逐笔成交 (Tick)
- bookDepth — 部分深度快照 (Tick)
- bookTicker — 最优挂单 (Tick)
- markPriceKlines — 标记价 K 线 (K 线)
- indexPriceKlines — 指数价 K 线 (K 线)
- premiumIndexKlines — 溢价指数 K 线 (K 线)

**3 个市场**: spot (现货) / um (USDⓈ-M 永续) / cm (COIN-M 永续)

### 2. 统一 Parquet 分区存储

- 目录格式: `data/source/archive/{market}/{kind}/{SYMBOL}/`
- 文件命名: `{SYMBOL}-{kind}[-{interval}]-{YYYY-MM-DD}.parquet`
- 元数据: 每个 (market, kind, symbol) 目录一份 `_meta.json`, 含 `earliest_date` / `latest_date` / `total_rows` / `file_count` / `corrupt_dates` / `updated_at` (纳秒 ISO 8601)
- K 线类 8 个 interval: 1m / 3m / 5m / 15m / 30m / 1h / 2h / 1d

### 3. 6 个 REST API 端点

- `POST   /api/data/archive/download`         — 创建下载任务 (返回 task_id)
- `GET    /api/data/archive/tasks/{task_id}`  — 查询任务进度
- `GET    /api/data/archive/symbols`          — 列出已采集 symbols
- `GET    /api/data/archive/data`             — 分页查询 (limit/offset)
- `GET    /api/data/archive/meta/{kind}/{market}/{symbol}` — 读 `_meta.json`
- `DELETE /api/data/archive/data`             — 删除某 symbol 全部数据

### 4. CLI 子命令

```bash
quantcell data archive download -k aggTrades -m spot -s BTCUSDT --start 2024-12-01 --end 2024-12-02
quantcell data archive list -k aggTrades -m spot
quantcell data archive meta -k aggTrades -m spot -s BTCUSDT
```

### 5. 前端 UI

- **DataCollectionPage**: 创建任务对话框加 kind 多选 + market 单选 (替换原 K 线单选)
- **DataManagementPage**: 新增 "归档数据" Tab, 支持按 (kind, market) 浏览已采集 symbols, 读 _meta 摘要, 跳到分页查询

### 6. 端到端自检 (Ponytail 风格)

`scripts/check_archive.py` 跑 5 项真实可运行检查:
1. `BinanceArchiveFactory.create(AGG_TRADES, SPOT, ...)` 装配
2. 真实下载 BTCUSDT aggTrades 2024-12-01 → 解析 → 落 Parquet
3. 读 Parquet 验证行数 > 1000 + price dtype == float64
4. 调 `read_range` 验证可查出数据
5. 验证 `_meta.json` 存在 + `latest_date == 2024-12-01`

---

## 三、使用方式

### 1. CLI 一行启动 (最常用)

```bash
# 现货聚合成交, 单日 1.5M 行, ~70 MB
quantcell data archive download \
  --kind aggTrades --market spot --symbols BTCUSDT \
  --start 2024-12-01 --end 2024-12-02

# 合约 markPriceKlines (1h K 线)
quantcell data archive download \
  --kind markPriceKlines --market um --symbols BTCUSDT --interval 1h \
  --start 2024-12-01 --end 2024-12-02

# 全量重下 (跳过已有 parquet)
quantcell data archive download \
  --kind trades --market spot --symbols BTCUSDT,ETHUSDT \
  --start 2024-12-01 --end 2024-12-02 --mode full
```

### 2. Python API (在已有代码内调用)

```python
from collector.services.archive_service import ArchiveService
from exchange.binance.archive.kinds import ArchiveKind, MarketType

svc = ArchiveService(base_dir="data/source/archive")
task_id = svc.create_download_task(
    symbols=["BTCUSDT"],
    kind=ArchiveKind.AGG_TRADES,
    market=MarketType.SPOT,
    start_date="2024-12-01",
    end_date="2024-12-02",
    mode="inc",          # 增量 / full 全量
)
print(task_id)  # 后续用 svc.get_meta / svc.query_data / svc.list_symbols 查询
```

### 3. REST API (前端 / 第三方调用)

```bash
# 创建任务
curl -X POST http://localhost:8000/api/data/archive/download \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["BTCUSDT"],"kind":"aggTrades","market":"spot","start_date":"2024-12-01","end_date":"2024-12-02"}'

# 查询进度
curl http://localhost:8000/api/data/archive/tasks/{task_id}

# 读数据 (分页)
curl 'http://localhost:8000/api/data/archive/data?kind=aggTrades&market=spot&symbol=BTCUSDT&start_time=1733011200000&end_time=1733097600000&limit=10'
```

### 4. 端到端自检

```bash
cd backend && .venv/bin/python ../scripts/check_archive.py
# 退出码: 0 = 全部通过, 1 = 代码/数据问题, 2 = 网络不可达
```

---

## 四、回归测试结果

详见 [PR_archive.md](PR_archive.md) § 测试结果。

---

## 五、关键设计决策

1. **零侵入**: 现有 K 线 (data_service + crypto_spot_klines / crypto_future_klines 表) 完全不动, archive 数据只入 Parquet。
2. **复用基础设施**: 走现有 `task_manager` 异步任务 + `BaseCollector` (注: archive fetcher 独立于 `BaseCollector`, 见 plan 修正 `75c5d66`)。
3. **轻 schema**: 7 种数据各 6-9 列, 强类型 (i64 / f64 / bool / string), 显式 pyarrow schema。
4. **fetch 走 aiohttp, 落盘走 pyarrow**: 异步下载 + 同步 Parquet 写入 (`_run_async` 桥接)。
5. **不读 realtime**: archive 与 realtime 引擎完全解耦。
6. **K 线类必须传 interval**: 8 个允许值, service 层校验, API 400 / CLI 错误退出。
