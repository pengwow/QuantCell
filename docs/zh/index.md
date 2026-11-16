---
title: 首页
description: QuantCell — AI 原生量化交易系统官方文档
---

# QuantCell

**QuantCell** 是一款 AI 原生的量化交易系统，以 [axon-quant](https://github.com/pengwow/axon_quant)（Rust 核心）为交易引擎，以 FastAPI 为服务框架、React + TypeScript 为前端，提供从策略开发、回测验证到实盘部署的全流程能力。

核心设计理念：**让量化交易变得简单、高效、智能** —— 自然语言即可描述策略，AI 自动生成代码并完成回测验证。

[立即开始](getting-started/installation.md){ .md-button .md-button--primary }
[在线 Demo](https://demo.quantcell.top/chart){ .md-button }

---

## 功能特性

### 🤖 AI 智能

- **自然语言策略生成**：中文描述交易想法，AI 自动生成可执行策略代码
- **思维链推理**：多步骤策略与指标生成，逻辑可解释、可追溯
- **代码质量自检**：自动校验语法与运行时安全，拒绝不安全代码
- **智能 Agent**：具备记忆与工具调用能力，支持多轮对话与任务编排
- **LLM 决策录制回放**：LLM 策略回测时从录制记录回放决策，不真实请求 LLM

### ⚡ Axon-Quant 高性能引擎

- **Rust 核心驱动**：底层采用 `axon-quant 0.25.0`，统一内核架构
- **统一主回路**：回测 / paper / live 共用同一条 per-bar 编排，语义一致
- **多数据类型回测**：K 线、衍生数据（资金费率等）、订单簿、逐笔成交等数据适配器
- **Walk-Forward 验证**：滚动窗口回测，防止过拟合
- **HPO 超参优化**：内置 Optuna 超参数优化

### 🎯 强化学习

- **Gymnasium 量化环境**：内置交易 Gym 环境
- **Stable-Baselines3**：支持 PPO / SAC / DQN 等主流算法
- **完整生命周期**：训练 → 回测 → 评估 → 重训练，支持 Walk-Forward 验证

### 🛡️ 风控与合规

- **凭证加密存储**：交易所 API 密钥加密入库，`quantcell account` 统一管理
- **风险引擎**：交易风险指标监控、止损与持仓风控
- **多语言界面**：内置 i18n 国际化

### 📊 完整数据生态

- **多交易所**：Binance（实盘 / 纸面 / 归档）、OKX 适配器
- **实时行情**：WebSocket 实时订阅、分发与持久化
- **Parquet 存储**：列式存储，高效读写
- **数据质量检测**：缺失值检测、自动回补与归档修复

### 🔌 插件系统

- **插件安装与管理**：通过 `quantcell plugin` 命令安装、打包、管理插件
- **事件总线**：插件间通过统一事件总线通信
- **安全沙箱**：插件在受限沙箱中运行，保障主进程安全

### 🎨 现代化前端

- **React 19 + TypeScript + Vite 8**：类型安全的组件化开发
- **Ant Design 6**：企业级 UI 组件库
- **KLineCharts / ECharts**：专业级 K 线与指标图表
- **Monaco 编辑器**：内置代码编辑器
- **Tauri 2 桌面端**：macOS / Windows / Linux 全平台桌面应用

---

## 文档导航

| 章节 | 内容 |
|------|------|
| [快速开始](getting-started/installation.md) | 环境要求、安装、启动服务 |
| [架构总览](user-guide/architecture.md) | 系统分层、统一内核主回路、技术栈 |
| [策略开发全流程](user-guide/strategy-development.md) | AI 生成、模板、回测验证 |
| [回测详解](user-guide/backtesting.md) | 统一内核、执行路径、Walk-Forward、HPO |
| [模拟盘与实盘](user-guide/live-trading.md) | worker 系统、执行层、凭证管理 |
| [强化学习](user-guide/rl-training.md) | 交易环境、训练、生命周期管理 |
| [数据生态](user-guide/data.md) | 采集、质检、行情与存储 |
| [CLI 命令行](modules/cli.md) | 15 组命令完整参考 |
| [REST API](reference/api.md) | `/api/v1` 路由组参考 |
| [WebSocket](reference/websocket.md) | 实时通道协议 |
| [最佳实践](best-practices.md) | 策略、回测、部署、安全 |
| [常见问题排查](troubleshooting.md) | 安装、运行、交易故障排查 |
