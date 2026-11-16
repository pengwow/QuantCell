---
title: 常见问题排查
description: 安装、运行、回测与实盘的常见问题与解决方法
---

# 常见问题排查

## 安装相关

### `uv sync` 失败或依赖冲突

- 确认 Python 3.14（项目目标版本）：`python3 --version`
- 删缓存重装：`uv cache clean && uv sync`
- axon-quant 是 maturin 完整 path 依赖，首次 sync 需要 Rust 编译环境可耗时较长，
  属正常现象

### `quantcell` 命令不存在

`quantcell` 由 `uv sync` 生成在 `backend/.venv/bin/`：

```bash
export PATH="$PATH:$(pwd)/backend/.venv/bin"   # 或使用完整路径
backend/.venv/bin/quantcell --help
```

### 前端启动报错

- 确认用 bun 而不是 npm：`bun install && bun run dev`
- 依赖缓存异常时删除 `frontend/node_modules` 重装

## 运行相关

### 后端启动成功但页面打不开

- 前端开发模式与后端端口分离：后端 `8000`，前端 `5173`（vite 默认）
- 确认访问的是 vite dev 地址而非 8000（8000 只有 API 与 Swagger）

### `/metrics` 404

Prometheus 指标端点受**能力开关**控制：查询 `/api/v1/extensions` 并启用对应能力。

### 端口冲突

`make dev-start` 前先 `make dev-status` / `make dev-stop` 清理残留进程。

## 数据相关

### 回测报「数据缺失」

```bash
quantcell data download -s BTCUSDT -i 1h
quantcell data quality check --start <start> --end <end>
```

缺失区间自动回补后重试。

### 时间戳不对

系统统一纳秒精度；手写数据源请先转换（毫秒 × 1_000_000）。

## 回测相关

### 回测结果与 Python 路径不一致

- 确认未混用 `fundingRate` 数据类型与 `funding_by_symbol` 结算通道（会双计费）
- `bookDepth` / `bookTicker` 是 mid-price 合成价，不产生真实成交撮合
- 多品种是「每品种独立资金池」口径，不要按整体资金池解读

### 引擎行为与预期不符

Rust 引擎 .so 可能过期（改过 axon-quant 源码后未重装）：

```bash
cd backend && uv sync --frozen --reinstall-package axon-quant
uv run pytest tests/conformance/ -q     # 契约门禁最先报警
```

## 实盘相关

### API Key 校验失败

- `quantcell account add` 重新录入；`quantcell account list` 确认交易所与 key 相符
- 检查交易所侧 IP 白名单与权限（交易开、提币关）

### paper 与 live 行为差异

- paper 撮合无真实滑点与排队，live 成交更差属正常
- 确认 risk engine 配置在两种模式一致

### LLM 策略回测报 ReplayMissError

回测只回放录制记录，**不真实请求 LLM**：

- 先在 paper / live 跑一段时间积累录制（`backend/data/llm_replay`）
- 或指定策略参数 `llm_replay_path` 指向已有录制目录

## 桌面端

### macOS 「无法验证开发者」

系统设置 → 隐私与安全性 → 仍要打开；或右键 → 打开。

### sidecar 后端未启动

- 查看 Tauri 日志确认 `quantcell-backend` 二进制存在且可执行
- 首次运行可能被 Gatekeeper 拦截，放行后重试
