---
title: 5 分钟跑通
description: 从零到回测的完整流程演示
---

# 5 分钟跑通

本文用最小步骤演示 QuantCell 的核心闭环：**启动服务 → 下载行情 → 运行回测 → AI 生成策略**。

前置条件：已完成[安装](installation.md)（`uv sync` 生成 `quantcell` 命令、数据库已初始化）。

## 1. 启动服务

=== "一键启动"

    ```bash
    make dev-start     # 后端 uvicorn + 前端 vite 后台驻留
    make dev-status    # 确认服务已就绪
    ```

=== "手动启动"

    ```bash
    cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
    cd frontend && bun run dev
    ```

浏览器打开前端开发地址即可看到量化工作台界面。

## 2. 下载行情数据

```bash
quantcell data download -s BTCUSDT -i 1d
```

`-s` 指定交易对，`-i` 指定 K 线周期。首次下载会自动从交易所拉取历史并落成
Parquet 存储。

验证数据质量：

```bash
quantcell data quality check --start 20240101 --end 20241231
```

## 3. 运行内置策略回测

```bash
quantcell strategy list          # 查看可用策略（内置 13 种模板）
quantcell backtest run \
  -s dual_ma \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000 \
  --trading-mode spot
```

输出包含总收益、最大回撤、成交记录等指标，回测默认走 axon-quant Rust 统一内核。

## 4. AI 生成一个策略

```bash
quantcell strategy generate \
  --requirement "基于双均线的趋势跟踪策略，快线 10 天、慢线 30 天，金叉买入、死叉卖出" \
  --name dual_ma
```

系统自动完成：**理解需求 → 生成代码 → 安全校验 → 回测验证 → 输出报告**。
生成结果可在前端「策略」页面查看与编辑。

## 5. 训练一个 RL 模型（可选）

```bash
quantcell rl train -s BTCUSDT -a ppo -t 100000 -r sharpe
```

参数：`-a` 算法（ppo / sac / dqn），`-t` 训练步数，`-r` 奖励函数。

## 6. 连接交易所（可选）

```bash
quantcell account add            # 交互式录入 API Key（加密入库）
quantcell account list           # 查看已配置的凭证
```

凭证加密存储，永不以明文落盘或打印到日志。

## 下一步

- [统一主回路架构](../user-guide/architecture.md) —— 理解回测 / paper / live 一致性
- [CLI 完整参考](../modules/cli.md) —— 15 组命令速查
- [REST API](../reference/api.md) —— 前后端接口契约
