# P2 批次 1：walk-forward 默认开启 + OOS 晋升门槛

日期：2026-11-18

## 行为变更（注意）

- `POST /api/v1/rl/train`（及 `/train/async`）的 `TrainRequest.walk_forward` 默认值
  由 `false` 翻为 `true`。**ModelHub 不显式传参时现在会跑 walk-forward**，训练耗时
  约为原来的 2 倍（WF 占进度前 50%）。显式传 `"walk_forward": false` 仍可关闭。
- 默认值只在 API 请求模型层翻转；`RLTrainConfig.walk_forward`（内部 dataclass）
  保持 `False`，直接调用 `RLService.train()` 的代码行为不变。

## 新增

### 1. 训练窗/验证窗统计量对齐检查

`rl/walk_forward_rl.py` 每折训练前比对 train/valid 的 bar 数、收盘收益率波动率比、
均值差（以波动率为单位）。任一项超阈值 → 该折标记失败并写入 `stats_check`，
不中断其余折；失败折不进入 aggregate。阈值见 `STATS_ALIGNMENT_DEFAULTS`，
可通过 `validate(stats_thresholds={...})` 单项覆盖。

### 2. 每轮 WF 产出 `oos` 报告

`RLWalkForwardService.validate()` 返回值新增 `oos`：折均 sharpe / 收益率 / 是否达标 /
指标来源。它随 `walk_forward` 一起写进模型旁车 `.meta.json`，即
`walk_forward.oos`；不新增独立落盘文件。旧产物没有该 key 时，门槛回退
`walk_forward.aggregate.mean`，再回退顶层 `oos`。

### 3. promote OOS 门槛（默认开启）

`ModelRegistryService.promote_to_production()` 在真正晋升前读取同族模型旁车：
最近 2 轮可评估的 walk-forward OOS **连续**不达标（默认 sharpe < 0 或收益 < 0）
→ 抛 `OosGateError`，`POST /api/v1/models/{model_id}/promote` 返回 **409**，
detail 含每轮模型名 / sharpe / return% 证据。

- 少于 2 轮可评估、或最近 2 轮有一轮达标 → 放行（不封冷启动/旧数据）。
- 同族归约见 `services/oos_gate.model_family()`：剥时间戳 / 算法 / `_vN` /
  `_retrain` 后缀，让多轮重训练的 OOS 串成连续轮次。
- **bypass 结论**：API 不暴露 bypass；仅 `seed_demo_models()` 内部以
  `enforce_oos_gate=False` 晋升首个示例，避免历史坏指标卡死启动自愈。

### 4. 周期审计

`core.scheduler` 新增每日 03:30 的只读审计 job，复用既有 APScheduler；
`rl.lifecycle.run_loop` 每轮迭代也顺带审计一次。审计只记日志，不触发训练；
训练侧仍由 `RLLifecycle` 负责。
