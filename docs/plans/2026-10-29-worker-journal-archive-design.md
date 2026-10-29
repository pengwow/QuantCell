# Worker Journal 归档（重锚前置）设计

- 日期：2026-10-29
- 状态：已批准
- 背景：worker_3 实盘恢复守卫拒绝续跑（对账差异）后，归档 journal 走重锚 fresh start 的操作此前只能手动 `mv backend/data/live/worker_X.jsonl → archive/`。本设计将其产品化为页面 + CLI + API 的一等功能。

## 需求决策（ brainstorming 已确认）

| 决策点 | 结论 |
|--------|------|
| worker 运行中允许归档？ | 不允许，必须先停止（服务端校验） |
| 归档后动作 | 保持停止，由用户手动启动（fresh start 重锚） |
| 归档范围 | journal + 对账报告 `worker_X.reconcile.json` 一并移入 archive |
| 页面入口 | 仅 WorkerDetail 操作区（危险按钮 + 二次确认 Modal） |
| 方案形态 | 方案 A：service 层归档函数，HTTP API 与 CLI 共享同一逻辑 |

## 方案对比

- **A（采用）**：Backend service 归档函数 + `POST /workers/{id}/lifecycle/archive` + `qc worker archive` + 详情页按钮。三入口一条逻辑，停止状态校验在服务端绕不过。
- B（否决）：CLI 直接文件操作。worker 停止状态在 backend 进程内存中，CLI 本地无法可靠校验；live/rl_live 路径变体会导致逻辑漂移。
- C（否决）：归档语义并入 restart。restart 是日常低危操作，混入高危「丢弃账本」语义会把每次重启拖进同一个高危确认。

## 架构

```
WorkerDetail 按钮 ─┐
                   ├─► POST /api/v1/workers/{id}/lifecycle/archive ─┐
qc worker archive ─┘（CLI 走 _service 同一入口）                    ├─► worker/lifecycle.py
                                                                  │   archive_journal_files()
                                                                  └──── 校验停止态 → mv 落盘 → 返回归档清单
```

## 组件设计

### 1. service：`worker/lifecycle.py::archive_journal_files(worker_id) -> list[dict]`

1. 校验 worker 处于停止态，否则抛 `WorkerLifecycleError`（路由映射 409）。状态来源与 `lifecycle/start` 现有校验一致。
2. 收集候选文件（复用 `worker/strategy_manager.py` L1357-L1376 的现有路径规则，不新增第二处硬编码）：
   - journal（两类目录取存在者）：规则/LLM `backend/data/live/worker_{id}.jsonl`；RL `backend/data/rl_live/worker_{id}.jsonl`
   - 对账报告：`backend/data/live/worker_{id}.reconcile.json`（两类型 worker 的报告统一落在此；存在即收）
   - 两类目录下 journal 均不存在 → 抛「无可归档 journal」（路由映射 400）
3. 逐文件 `shutil.move` 到其来源目录下的 `archive/` 子目录，命名 `worker_{id}.{YYYYmmdd-HHMMSS}.jsonl`；对账报告用同一时间戳 `worker_{id}.{ts}.reconcile.json`（名字带来源标识则保持原名）。
4. 目标重名时追加 `_1` 递增后缀防覆盖（`mv` 覆盖即丢数据，值得防御；不做其余清理逻辑）。
5. 返回 `[{"from": ..., "to": ...}]`。

### 2. HTTP API：`worker/routes.py`

- `POST /{worker_id}/lifecycle/archive`，summary「归档 journal（重锚前置）」，沿用 `handle_worker_exceptions`。
- 路由只接参数、调 service、映射异常：409 未停止 / 400 无 journal。
- 成功响应：`{"archived": [{"from", "to"}], "hint": "下次启动将 fresh start，以交易所快照重锚"}`。

### 3. CLI：`backend/cli/worker.py`

- `qc worker archive <ID>`，与 `start/stop/restart` 同风格：`_service` 调归档函数，逐文件回显 `moved: from → to`；失败按现有 `错误: ...` + `Exit(1)` 模式。不加 flag。

### 4. 前端：`frontend/src/pages/worker/WorkerDetail.tsx` + `frontend/src/api/workerApi.ts`

- `archiveWorkerJournal(id)` API 封装；操作区加 danger 按钮「归档重锚」。
- 非 stopped 态 disabled，tooltip「先停止后再归档」。
- 点击弹 Modal 二次确认，列明影响：journal + 对账报告移入 archive；下次启动为 fresh start 以交易所快照重锚；归档后保持停止需手动启动；实盘 worker 请先人工核对交易所持仓与资金。
- 成功后 message + 刷新详情。antd 组件间距用 `<Space orientation>` / `<Flex gap>`（项目规则，禁 space-y-*）。

## 错误处理

| 场景 | 行为 |
|------|------|
| worker 未停止 | 409，提示先停止 |
| 无可归档 journal | 400，提示可能已归档或从未实盘启动 |
| 部分文件 mv 失败 | 成功的保留在 archive，失败的留在原地并在错误信息里列出清单（500），不回滚 |
| archive 目录缺失 | 自动创建 |

## 测试与验收

- `backend/tests/unit/worker/test_journal_archive.py`（tmp 路径注入）：停止态归档成功（mv + 时间戳改名 + 报告同名随迁）、运行中 409、无 journal 400、RL 分支路径、重名防覆盖。
- CLI 冒烟与 HTTP 冒烟各 1 条。
- 前端 `bun run build` 通过。
- 实施期间顺带清理 `backend/**/Volumes/` 脏目录（mv 到临时目录）。

## 非目标（YAGNI）

批量归档、定时归档、archive 内容列表页、归档文件下载/回读、归档即自动启动。
