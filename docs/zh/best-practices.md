---
title: 最佳实践
description: 策略研发、回测、数据、部署与安全的项目约定
---

# 最佳实践

## 策略研发

- **先回测，再 paper，后 live**：每一步都有通过标准再进入下一步
- 参数敏感的策略（动量、均值回归、RL）**必须做 Walk-Forward**
- HPO 结果再跑一次 Walk-Forward 独立验证，双重防过拟合
- 策略内部只做信号计算：不下单、不访问网络、不直接读交易所状态
- LLM 策略回测只走 ReplayProvider，未命中即报错，不静默降级

## 回测

- 明确 `runner` 选择：默认统一内核即可，特殊 data_type 自动回退 Python 路径
- 注意数据类型语义边界：`fundingRate` 是特征列不是结算通道；
  `bookDepth` / `bookTicker` 聚合出的是合成价不是可撮合盘口
- 币本位账务为近似（乘数未计入名义价值），重仓币本位场景谨慎解读盈亏
- 对比策略时固定资金、周期与品种集合，保证口径一致

## 数据

- 回测前先跑 `quantcell data quality check`，缺失区间会直接扭曲结果
- 时间戳统一纳秒精度 ISO 8601；品种统一 `BASE/QUOTE`
- 新数据源先小批量验证聚合形态，再放量采集

## 代码规范（后端）

- 路由层只接参数调 service，业务逻辑放 service
- 统一 `HTTPException` 抛错；参数校验交给 Pydantic
- 依赖注入（`Depends`）便于测试 mock
- 优先顶部 import；确需函数内 import 时注明原因
- 日志统一走 `backend/utils/logger.py`，**禁止 print**；结构化输出带 request_id，敏感信息不打日志
- 脚本用 `typer`，不用 argparse
- 时间戳字符串遵循 ISO 8601（RFC 3339），9 位（纳秒）精度为主

## 代码规范（前端）

- antd v6 组件间距用 `<Space orientation="vertical">` 或 `<Flex gap>`，
  **禁止** Tailwind `space-y-*` 拼接 antd 组件（CSS-in-JS 下会失效）
- 间距取值统一：`small`(8px) / `middle`(16px) / `large`(24px)，不写魔法 margin
- 页面写完自查相邻区块间距是否可见

## 引擎依赖（axon-quant）

修改 axon-quant Rust 源码后，同步到 backend 的标准命令：

```bash
cd backend && uv sync --frozen --reinstall-package axon-quant
```

- **必须带 `--reinstall-package`**：uv 对 maturin path 依赖不做源码新鲜度比对，
  缺了它会装回旧 .so
- 禁止用 `uv pip install <wheel>` 手装（下次 `uv sync` 会静默打回旧版）
- 引擎同步后先跑契约门禁再跑全量：`uv run pytest tests/conformance/ -q`

## Git 提交

- 提交信息用 `feat/ fix/ docs/ refactor/` 前缀
- 逻辑独立拆分 commit，不堆文件
- 提交前跑对应 lint / test（`make lint` / `make test`）

## 环境

- 配置按环境分层（`.env.dev / .env.test / .env.prod`），用 pydantic-settings 管理
- 敏感信息不硬编码；生产配置不入库
- API 前缀 `/api/v1`，预留不兼容升级空间

## 部署

- 生产前端：`make frontend-build` 后部署静态产物，或直接用桌面端 / 远程模式
- 后端生产启动：`uvicorn main:app --host 0.0.0.0 --port 8000`（建议配 systemd /
  容器编排与日志收集）
- 实盘服务器只开必要端口与权限；交易所密钥最小权限（关闭提币）
