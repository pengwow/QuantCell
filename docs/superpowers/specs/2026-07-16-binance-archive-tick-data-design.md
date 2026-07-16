# Binance 历史归档（Tick + K 线）全种类数据采集

**Date:** 2026-07-16
**Status:** Design — Pending user review
**Owner:** QuantCell Core Team
**Target Release:** v2.1.0

---

## 1. 背景与目标

### 1.1 背景

QuantCell 当前数据管理模块（`backend/collector/` + 前端 `DataCollectionPage` / `DataManagementPage`）只覆盖**K 线**一种数据：
- 后端走 `BinanceDownloader` 下载 `data.binance.vision` 上的 K 线 `.zip` 归档，落地 Parquet + 入库 `crypto_spot_klines` / `crypto_future_klines`
- 增量/全量、定时调度、任务进度都围绕 K 线建立

但 Binance 官方历史归档（`https://data.binance.vision/`）**总共提供 9 种数据**：aggTrades、trades、bookDepth、bookTicker、klines、markPriceKlines、indexPriceKlines、premiumIndexKlines、metrics。其中：

- **Tick 级**（aggTrades、trades、bookDepth、bookTicker）：回测/撮合模拟/盘口研究必须
- **K 线级**（markPriceKlines、indexPriceKlines、premiumIndexKlines）：合约资金费/标记价/指数价/溢价指数研究必须
- **metrics**：做市商分润业务指标，**非行情数据**，本次不纳入

回测/研究场景对 tick 数据的需求与日俱增，但当前没有任何采集通道。

### 1.2 目标

复用现有 K 线下载器的基础设施，把数据采集能力**横向扩展到 Binance 历史归档的 7 种数据**（去掉 metrics，klines 已在跑）：

1. **7 种数据 × 3 个市场**（spot / futures/um / futures/cm）= **21 种组合**全支持
2. **全部只入 Parquet 分区**，不建新 SQL 表（避免量级爆炸）
3. **仅历史归档采集**，不碰 realtime 引擎
4. **不动现有 K 线**（表、下载、查询路径全部保留）
5. **前端最小改动**：在 `DataCollectionPage` 创建任务对话框加 kind 多选 + market 单选；`DataManagementPage` 新增归档数据浏览 tab
6. **复用现有 `task_manager` 异步任务 + `scheduled_tasks` 定时任务**，不重造调度
7. **复用现有 `BaseCollector` 并发/限速/重试基础设施**，子类只关心数据特异性

### 1.3 非目标

- **不实现 WebSocket 实时采集**（本次只做历史归档 zip 下载；实时由后续独立项目承担）
- **不拆 K 线表**（`crypto_spot_klines` / `crypto_future_klines` 现状保留；K 线表迁移到 Parquet-only 是未来独立项目）
- **不实现 metrics 数据采集**（业务侧分润指标，不是行情）
- **不引入时序库**（TimescaleDB / QuestDB 等本次不评估；Parquet + 文件元数据足够支撑当前规模）
- **不改动 realtime 引擎**（`realtime/factory.py` / `realtime/*.py` 完全不动）

### 1.4 验收标准（必须全部通过）

1. `quantcell data archive download --kind aggTrades --market spot --symbols BTCUSDT --start 2024-12-01 --end 2024-12-02` 退出码 0
2. `data/source/archive/spot/aggTrades/BTCUSDT/` 下出现 2 个 parquet 文件 + 1 个 `_meta.json`
3. `quantcell data archive meta --kind aggTrades --market spot --symbol BTCUSDT` 返回 `latest_date=2024-12-02, total_rows>1000`
4. 前端 `DataCollectionPage` 创建任务对话框显示 7 种 kind 多选 + 3 种 market 单选
5. 前端 `DataManagementPage` 新 Tab 能查到 BTCUSDT 2024-12-01 的 aggTrades 数据（≥100 行/页）
6. 现有所有 K 线相关测试不破坏（**回归测试 0 新增 failure**）
7. 删除 `archive/` 目录后 K 线系统完全不受影响

---

## 2. 整体架构

### 2.1 模块布局

```
backend/exchange/binance/
├── downloader.py              # 现有 BinanceDownloader（K线用，不动）
├── archive/                   # 新建：历史归档体系（7 种数据共享）
│   ├── __init__.py
│   ├── base.py                # BaseBinanceArchiveDownloader（90% 通用逻辑）
│   ├── factory.py             # BinanceArchiveFactory.create(kind, market)
│   ├── kinds.py               # ArchiveKind 枚举、MarketType 枚举、列名常量
│   ├── fetchers/              # 7 个轻量子类
│   │   ├── __init__.py
│   │   ├── agg_trades.py
│   │   ├── trades.py
│   │   ├── book_depth.py
│   │   ├── book_ticker.py
│   │   ├── mark_price_klines.py
│   │   ├── index_price_klines.py
│   │   └── premium_index_klines.py
│   └── archive_meta.py        # 轻量元数据 _meta.json 读写（每目录一份）

backend/collector/
├── services/
│   ├── archive_service.py     # 业务编排：调用 factory、任务进度、错误聚合
│   └── archive_meta_service.py # 元数据查询（前端用）
├── api/
│   └── archive.py             # 7 种数据的 REST 端点
└── ...

backend/cli/data.py            # 追加 subcommand：quantcell data archive ...
```

### 2.2 关键设计点

- 复用现有 `BaseCollector` 的并发/限速/重试基础设施（继承）
- 复用现有 `get_date_range` / `parquet_utils.append_to_parquet`（不要造新轮子）
- 复用现有 `task_manager` 异步任务调度（不重造）
- 复用现有 `scheduled_tasks` 表的 cron 调度（复用 `task_type` 新值 `archive_agg_trades` 等 7 个）
- 复用现有 `DataCollectionPage` 的"创建采集任务"入口，加 kind/market 多选下拉
- 复用现有 `DataManagementPage` 的"查看已有数据"入口，加新 kind 的浏览 tab

### 2.3 核心抽象

- `ArchiveKind` 枚举：`AGG_TRADES / TRADES / BOOK_DEPTH / BOOK_TICKER / MARK_KLINES / INDEX_KLINES / PREMIUM_KLINES`
- `MarketType` 枚举：`SPOT / FUTURES_UM / FUTURES_CM`
- `BaseBinanceArchiveDownloader`：提供 `download_range(symbol, start, end)` / `save_instrument(df, symbol)` / `collect_data(progress_cb)` / `get_instrument_list()`；子类只需重写 4 个钩子方法
- `BinanceArchiveFactory.create(kind, market)` 返回 7×3 装配好的下载器实例

---

## 3. 数据模型 & 存储

### 3.1 目录布局（与现有 K 线对称）

```
backend/data/source/archive/                  # 新根目录（独立于 klines/）
├── spot/
│   ├── aggTrades/{SYMBOL}/{SYMBOL}-aggTrades-YYYY-MM-DD.parquet
│   ├── trades/{SYMBOL}/{SYMBOL}-trades-YYYY-MM-DD.parquet
│   ├── bookDepth/{SYMBOL}/{SYMBOL}-bookDepth-YYYY-MM-DD.parquet
│   ├── bookTicker/{SYMBOL}/{SYMBOL}-bookTicker-YYYY-MM-DD.parquet
│   ├── markPriceKlines/{SYMBOL}/...parquet
│   ├── indexPriceKlines/{SYMBOL}/...parquet
│   └── premiumIndexKlines/{SYMBOL}/...parquet
├── um/                                       # futures/um
│   └── (同 7 个子目录)
└── cm/                                       # futures/cm
    └── (同 7 个子目录)
```

每个子目录下额外存一份**轻量元数据**（不建 SQL 表）：
- `data/source/archive/{market}/{kind}/{SYMBOL}/_meta.json`
- 字段：

```json
{
  "symbol": "BTCUSDT",
  "kind": "aggTrades",
  "market": "spot",
  "earliest_date": "2017-08-17",
  "latest_date": "2026-07-15",
  "total_rows": 52345678,
  "file_count": 3207,
  "corrupt_dates": [],
  "updated_at": "2026-07-15T08:00:00.000000000+08:00"
}
```

时间戳字符串遵循 ISO 8601（RFC 3339）格式，**具有 9 位（纳秒）小数精度**，始终保留所有数字，包括尾随零。

### 3.2 各 kind 的 Parquet schema

| kind | 关键列 | 行/天 (BTCUSDT) | 备注 |
|---|---|---|---|
| `aggTrades` | `agg_trade_id` (i64), `price` (f64), `quantity` (f64), `first_trade_id` (i64), `last_trade_id` (i64), `transact_time` (i64 毫秒), `is_buyer_maker` (bool) | ~200 万 | 主键：`agg_trade_id` |
| `trades` | `id` (i64), `price` (f64), `qty` (f64), `quote_qty` (f64), `time` (i64 毫秒), `is_buyer_maker` (bool) | ~500 万 | 主键：`id` |
| `bookDepth` | `timestamp` (i64 毫秒), `symbol` (str), `side` ('bid'/'ask'), `level` (i32), `price` (f64), `quantity` (f64) | ~几十万 × 20 层 | **嵌套 bids/asks 展开为长表** |
| `bookTicker` | `update_id` (i64), `timestamp` (i64 毫秒), `symbol` (str), `best_bid_price` (f64), `best_bid_qty` (f64), `best_ask_price` (f64), `best_ask_qty` (f64) | ~8.6 万 | 主键：`update_id` |
| `markPriceKlines` | `open_time` (i64 毫秒), `open`/`high`/`low`/`close` (f64), `volume` (f64), `quote_volume` (f64), `count` (i32) | 按 interval，1m 时 1440 | **复用 K 线的列名规范** |
| `indexPriceKlines` | 同上 + `index_price` (f64) | 同上 | |
| `premiumIndexKlines` | 同上 + `premium_index` (f64) | 同上 | |

### 3.3 关键约定

- 所有时间戳用**整数毫秒**（i64）存储；展示端需要纳秒时由前端按字符串解析（与现有 klines 同样的策略）
- Parquet 用 `snappy` 压缩，分区粒度 = `1 day / 1 symbol / 1 kind / 1 market`（小文件，但天然分片）
- `bookDepth` 嵌套展平后单日文件可能 50–200MB；保留 zip 原始 CSV 不入库（避免二次膨胀）

### 3.4 不入库 SQL 表的物证

- 7 种数据里**没有一张 SQL 元数据表**（用户确认全部只入 Parquet）
- 元数据靠 `_meta.json` 文件，跟数据共目录
- 唯一例外是 `scheduled_tasks` 表加 7 个新枚举值 `task_type='archive_agg_trades'` / `archive_trades` / `archive_book_depth` / `archive_book_ticker` / `archive_mark_klines` / `archive_index_klines` / `archive_premium_klines`（复用，不动表结构）

---

## 4. 采集器设计

### 4.1 基类 `BaseBinanceArchiveDownloader`

继承自 `BaseCollector`（复用并发/限速/重试），子类只需重写 4 个钩子方法：

```python
class BaseBinanceArchiveDownloader(BaseCollector):
    """所有 7 种数据归档下载器的共享基类。"""

    # —— 子类必须重写 ——
    archive_kind: ArchiveKind        # AGG_TRADES / TRADES / ...
    url_subpath: str                 # 'aggTrades' / 'trades' / ...
    column_mapping: dict[str, str]   # 原始列名 → 内部标准列名
    parquet_schema: pa.Schema        # pyarrow schema

    # —— 子类可选重写 ——
    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame: ...
    def needs_unzip(self) -> bool: return True

    # —— 基类提供 ——
    def get_zip_url(self, symbol, date) -> str
    def get_zip_name(self, symbol, date) -> str
    async def get_daily_archive(self, symbol, date) -> pd.DataFrame
    def download_range(self, symbol, start, end, progress_cb) -> pd.DataFrame
    def save_instrument(self, symbol, df) -> None
    def _calculate_missing_ranges(self, existing_files) -> list[tuple]
    def collect_data(self, progress_cb) -> None
    def _update_meta(self, symbol, new_files_added)
```

**复用清单**：
- `BaseCollector.collect_data`：并发调度 symbols
- `utils.decorators.async_deco_retry`：异步重试（K 线已用）
- `utils.time_parser.get_date_range`：日期范围
- `utils.parquet_utils.append_to_parquet`：增量合并到每日 Parquet
- `utils.timestamp_utils.normalize_to_nanoseconds`：仅在跨系统时转换

### 4.2 7 个 fetcher 的差异点

| fetcher | url_subpath | 主要差异 |
|---|---|---|
| `AggTradesFetcher` | `aggTrades` | 列名映射：`['agg_trade_id','price','quantity','first_trade_id','last_trade_id','transact_time','is_buyer_maker']` |
| `TradesFetcher` | `trades` | 列名：`['id','price','qty','quote_qty','time','is_buyer_maker']`；zip 不带 header |
| `BookDepthFetcher` | `bookDepth` | **唯一展开嵌套 bids/asks**：`transform_df` 把每条 `[price, qty]` 展成 1 行 → 单日行数 × 20-1000 层；转长表 |
| `BookTickerFetcher` | `bookTicker` | 列名：`['update_id','symbol','best_bid_price','best_bid_qty','best_ask_price','best_ask_qty']`；zip 内是单条/日，需带时间戳 |
| `MarkPriceKlinesFetcher` | `markPriceKlines` | 复用 K 线列名规范；`interval` 参数化（1m/5m/1h/1d） |
| `IndexPriceKlinesFetcher` | `indexPriceKlines` | 同上 + `index_price` 列 |
| `PremiumIndexKlinesFetcher` | `premiumIndexKlines` | 同上 + `premium_index` 列 |

### 4.3 工厂 `BinanceArchiveFactory`

```python
class BinanceArchiveFactory:
    _REGISTRY: dict[tuple[ArchiveKind, MarketType], type[BaseBinanceArchiveDownloader]] = {
        (ArchiveKind.AGG_TRADES, MarketType.SPOT): AggTradesFetcher,
        (ArchiveKind.AGG_TRADES, MarketType.FUTURES_UM): AggTradesFetcher,  # 同类，market 由 save_dir 区分
        ...
    }

    @classmethod
    def create(cls, kind: ArchiveKind, market: MarketType, **kwargs) -> BaseBinanceArchiveDownloader:
        fetcher_cls = cls._REGISTRY[(kind, market)]
        return fetcher_cls(market=market, **kwargs)
```

**简化策略**：每个 fetcher 实际上**不区分 market**（market 只影响 save_dir 和 URL 前缀），所以注册表 7×3=21 项但实际只有 **7 个类**。

### 4.4 增量/全量逻辑（与 K 线对齐）

- **inc 模式**（默认）：扫描 `{market}/{kind}/{SYMBOL}/` 下所有 `.parquet` 文件名 → 解析日期 → 与目标区间对比 → 只下载缺失日期
- **full 模式**：删除已有 parquet 后重下（K 线已有 `_calculate_missing_ranges`，参数化复用）
- 断点续传：每个 daily zip 是独立的，下载失败只丢一天，下次重跑自动补齐

---

## 5. API & 前端设计

### 5.1 后端 REST 端点（全部挂在 `/api/data/archive/*`）

| 方法 | 路径 | 用途 | 入参 |
|---|---|---|---|
| `POST` | `/archive/download` | 启动采集任务（异步） | `{symbols: [...], kind: 'aggTrades', market: 'spot', start_date, end_date, mode: 'inc'/'full'}` |
| `GET` | `/archive/tasks/{task_id}` | 查任务进度 | — |
| `GET` | `/archive/symbols` | 列出某 kind+market 下已采集的 symbols | `{kind, market}` |
| `GET` | `/archive/data` | **分页查 Parquet 数据**（核心查询接口） | `{kind, market, symbol, start_time, end_time, limit=1000, offset=0}` |
| `GET` | `/archive/meta/{kind}/{market}/{symbol}` | 读 `_meta.json` 元数据 | — |
| `DELETE` | `/archive/data` | 删除某 symbol 的所有数据（带保护） | `{kind, market, symbol}` |

**关键设计**：
- `GET /archive/data` 用 `pyarrow.parquet.ParquetDataset` 按日期目录做 partition filter，**只读匹配的 Parquet 文件**，不扫整个目录
- 时间范围过大时强制截断（默认单次最多 1M 行；超限返回截断标记）
- 返回格式与现有 K 线 API 对齐：`{success, message, total, rows: [...]}`

### 5.2 业务编排层

`backend/collector/services/archive_service.py`：薄编排层，不做实际下载逻辑
- `create_download_task()` → 复用 `task_manager.create_task(task_type='archive_agg_trades', ...)`
- `query_data()` → 委托给 fetcher 的 `read_range()` 方法
- `get_meta()` → 读 `_meta.json`

### 5.3 前端集成（最小改动原则）

| 文件 | 改动 |
|---|---|
| `frontend/src/api/dataApi.ts` | 新增 `archiveApi` 子对象；6 个方法 |
| `frontend/src/types/data.ts` | 新增 `ArchiveKind` / `MarketType` 枚举类型；`ArchiveTaskRequest` / `ArchiveRow` 接口 |
| `frontend/src/pages/data/DataCollectionPage.tsx` | 现有"创建任务"对话框加：① **kind 多选 checkbox**（7 种）② **market 三选一 radio**（spot/um/cm）③**interval 选择**（仅 K 线类 3 种显示） |
| `frontend/src/pages/data/DataManagementPage.tsx` | 新增 **"归档数据浏览" Tab**：左侧 kind+market 树形导航，中间日期日历范围选，右侧虚拟滚动表（10 万行不卡） |
| `frontend/src/pages/setting/types.ts` 等 | 无需改 |

**前端 UX 决策点**（默认建议）：
- 创建任务时**多选 kind**（一次下多个 → 后端拆成 7 个并发子任务，避免单任务 IO 集中）
- 默认显示**已采集符号数 + 最新日期**（来自 `_meta.json`）
- 数据浏览页面对 **bookDepth** 自动提示"展平后行数大，请缩小时间范围"

### 5.4 CLI（复用 `quantcell` 入口）

```bash
quantcell data archive download \
  --kind aggTrades,bookTicker \
  --market spot \
  --symbols BTCUSDT,ETHUSDT \
  --start 2024-01-01 --end 2024-01-31 \
  --mode inc

quantcell data archive list --kind aggTrades --market spot
quantcell data archive meta --kind aggTrades --market spot --symbol BTCUSDT
```

---

## 6. 错误处理、测试、回退

### 6.1 错误处理与重试

| 错误类型 | 处理策略 |
|---|---|
| 单日 zip 下载失败（404 / 500 / 超时） | `async_deco_retry(max_retry=3, delay=1.0)` + 指数退避（与 K 线同） |
| 单日 zip 数据为空 | 跳过写入，不报错；记日志 `INFO: {symbol} {date} empty` |
| zip 内 CSV 解析失败 | 捕获异常，标记当日为"corrupt"，不阻塞后续日期；记录到 `_meta.json.corrupt_dates` |
| Parquet 写入失败（磁盘满/权限） | 整批失败，`task_manager.fail_task` 标记 |
| 增量合并时类型不匹配 | 强制 schema 校验；不匹配则**重新下载该日**（写一条 warn 日志） |
| 单个 symbol 全部失败 | 不影响其他 symbols；汇总到 `task.last_result.errors[]` |
| 网络全局不可达 | 同 K 线，提示配置代理；走 `_get_proxy_config("binance")` |

### 6.2 资源控制（绝不能爆）

- **并发下载**：`max_workers=1`（K 线已强制，因 Windows pickle 限制），单 task 顺序下载
- **批下载进度**：`task_manager.update_progress` 推送（与 K 线同）
- **磁盘预警**：每次写入前 `shutil.disk_usage(save_dir).free > 5GB`，否则 `fail_task` 提前终止
- **内存保护**：单个 daily zip 解压到 `BytesIO` 后立即 `pd.read_csv` + `append_to_parquet`；不长期驻留内存

### 6.3 测试策略

```
backend/tests/unit/exchange/binance/archive/
├── test_base_archive.py           # 基类：URL 拼装、缺失区间计算、并发调度
├── test_factory.py                # 工厂：7×3 装配正确性
├── test_fetchers/
│   ├── test_agg_trades.py         # 真实 BTCUSDT 单日 zip 解析（fixture）
│   ├── test_book_depth.py         # 嵌套 bids/asks 展平
│   ├── test_book_ticker.py
│   ├── test_mark_klines.py
│   ├── test_index_klines.py
│   ├── test_premium_klines.py
│   └── test_trades.py
├── test_meta.py                   # _meta.json 读写
└── test_parquet_io.py             # 增量合并、schema 校验

backend/tests/integration/
└── test_archive_api.py            # 6 个端点的 happy path + 错误路径
```

- **不连真实网络**：除 `test_agg_trades` 等 7 个 fetcher 集成测试用录制的 zip fixture 外，全部 mock `aiohttp.ClientSession`
- **1 个 demo/self-check**（Ponytail 要求）：`scripts/check_archive.py`，跑一遍 BTCUSDT aggTrades 某日下载 + Parquet 写入 + 读回校验

### 6.4 回退方案

- **软回退**：本功能**完全独立**于 K 线数据流。删除 `archive/` 目录和相关 service/api/cli 注册项即可彻底移除，不影响 K 线。
- **数据可清**：所有数据在 `data/source/archive/` 下，删目录即清空（**提示用户**前端会显示"无数据"）
- **migration**：**无 alembic 变更**（不建 SQL 表）✅

---

## 7. 实施顺序（拆分建议）

后续 `writing-plans` 阶段会展开为详细任务清单，本节给出顶层拆分：

1. **后端基类 + 工厂 + 1 个 fetcher（aggTrades）端到端跑通** — 验证基础设施无缺陷
2. **补齐其余 6 个 fetcher**（trades / bookDepth / bookTicker / mark / index / premium Klines）
3. **后端 REST API + 业务编排层**（`archive_service.py` + `api/archive.py`）
4. **CLI 子命令**（`quantcell data archive ...`）
5. **前端最小改动**（dataApi + DataCollectionPage 多选 + DataManagementPage 新 tab）
6. **测试 + self-check**（单元 + 集成 + 1 个 e2e）
7. **回归 K 线测试**，确保 0 新增 failure

---

## 8. 风险 & 缓解

| 风险 | 缓解 |
|---|---|
| BTCUSDT aggTrades 单日 zip 可能 100MB+，下载/解压慢 | 限速 + 重试 + 磁盘预警 + 进度推送 |
| bookDepth 展平后单日行数爆炸 | UI 端强制时间范围；后端查询接口硬上限 1M 行 |
| 不同市场的 symbol 命名差异（cm 用 BTCUSD 无 USDT） | `MarketType` 枚举里附带 `symbol_suffix_map`，fetcher 调用时统一处理 |
| Binance 归档偶尔有缺失日期 | `corrupt_dates` 字段 + 缺失跳过 + 日志 `WARN` |
| 现有 K 线下载逻辑被误改 | 本次 PR 不动 `BinanceDownloader`；新代码全部在 `archive/` 子包；回归测试把关 |
