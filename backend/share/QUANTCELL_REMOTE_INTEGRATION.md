# QuantCell 分享系统 远端集成（quantcell.top）

> 本文面向 PC 端 QuantCell 开发者，介绍如何配置、调试和监控 PC 端向 quantcell.top 推送分享的能力。
>
> **本地分享模式已下线**：分享功能完全走远端 quantcell.top 分发，不再支持本机 `/share/<token>` 形式的链接，也不再支持「PC 本地生成凭据 + 降级」分支。

## 1. 架构速览

```
PC (QuantCell)
  ├── backend/share/config.py         集中读取 share_remote 配置
  ├── backend/share/credentials.py    远端凭据按需自动注册
  ├── backend/share/remote_client.py  HTTP 客户端（HMAC + 重试）
  └── backend/share/routes.py         create_share / revoke_share 内嵌远端推送
        │
        │  POST /api/share  +  DELETE /api/share/{remote_id}
        ▼
quantcell.top
  ├── POST /api/share                  写入 snapshot
  ├── DELETE /api/share/{remote_id}    撤销
  └── GET  /api/share/public/{token}   公开访问
share.quantcell.top
  └── 独立 React 静态站（客户端 fetch 公开 JSON 后渲染）
```

## 2. 工作模式

分享功能**只有一种模式：远端模式**。`ShareRemoteConfig.is_ready` 仅由 `api_key` 与 `hmac_secret` 是否同时存在决定：

| `api_key` | `hmac_secret` | 行为 |
|---|---|---|
| ✅ | ✅ | **远端就绪**：推送 quantcell.top，返回 `https://share.quantcell.top/<token>` |
| 缺 | 缺 | **远端未就绪**：create_share 立即抛 502（远端未就绪），列表中显示 `remote_status=PENDING` 或 `FAILED`，可在前端点击「重试」再次推送 |

> 历史曾存在的 `enabled` 标志与「PC 本地降级」分支已彻底移除。
> `remote_status` 取值固定为 `PENDING` / `UPLOADED` / `FAILED` / `REVOKED`，不再有 `LOCAL_ONLY`。

## 3. 凭据申请流程

凭据由 PC 端**首次 create_share 时按需自动注册**，无需前端 UI 引导：

1. 用户在 PC 端 `WorkerShareModal` 点击「生成链接」；
2. PC 后端 `ensure_remote_credentials()` 读取 `config.toml`：
   - 若 `api_key` + `hmac_secret` 同时存在 → 直接复用；
   - 若任一缺失：
     - 存在 `SHARE_REMOTE_ADMIN_TOKEN` → 调远端 `POST /api/admin/devices/auto-register` 获取由远端统一下发的 `api_key` + `hmac_secret`；
     - 无 admin token → 抛 503 `RemoteConfigError`，要求管理员先在远端用户中心为该设备分配凭据并写入 `config.toml`；
3. 凭据合并写入 `backend/config.toml` 的 `[share_remote]` 段（保留其他字段）；
4. 清空 `ShareRemoteConfig` 单例，触发下次懒加载重建 → `is_ready` 立即变 `True`；
5. 凭据就绪后再走常规远端推送流程（`build_snapshot` → `RemoteShareClient.upload_sync` → 落库 `short_url`）。

### 3.1 历史兼容

- 旧 token（`remote_status` 为旧字段 `LOCAL_ONLY`）的迁移已通过 Alembic `18_remove_share_views_table.py` 配套清理（删除 `share_views` 公开访问审计表）。`share_tokens.remote_status` 字段被收敛为远端四态，无需手动迁移。
- 历史曾提供的 `/api/share/credentials/status` 与 `/api/share/credentials/generate` 端点已下线，前端不再调用。

## 4. 调试步骤

```bash
# 1. 启动 mock 远端
cd mock_remote && uvicorn mock_remote:app --port 9999

# 2. 在 config.toml 中指向 mock
[share_remote]
base_url = "http://localhost:9999"
api_key = "test_device_key"
hmac_secret = "test_hmac_secret"

# 3. 启动 PC 端
cd backend && uvicorn main:app --port 8000

# 4. 调用创建分享 API
curl -X POST http://localhost:8000/api/workers/1/share \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"expires_in_seconds": 3600, "one_time": false, "max_views": null}'

# 期望响应含 short_url = "http://localhost:9999/s/<token>"
```

## 5. 失败兜底矩阵

| 失败点 | 行为 | 前端感知 |
|---|---|---|
| `api_key` / `hmac_secret` 缺失 | 抛 502，token 不落库 | 弹 toast 提示管理员配置凭据 |
| 远端 4xx（业务错误） | 不重试，`remote_status=FAILED` | 列表显示「推送失败」Tag + 「重试」按钮 |
| 远端 5xx | 重试 3 次后 `FAILED` | 同上 |
| 网络不可达 | 重试 3 次后 `FAILED` | 同上 |
| HMAC 验签错误（远端拒绝） | 不重试，`remote_status=FAILED` | 弹 toast "签名错误" |
| `auto-register` 失败（无 admin token） | 抛 503 `RemoteConfigError` | 弹 toast 提示管理员配置 `SHARE_REMOTE_ADMIN_TOKEN` |

> 注意：远端推送失败时 `create_share` 仍会返回 502 并落库 token（`remote_status=FAILED`），方便用户事后点「重试」再次推送。

## 6. 安全约束

- `hmac_secret` 一旦泄露应立即在用户中心**轮换**（生成新 key，旧 share 自动失效）
- PC 端**永不暴露公网**；远端无法回连 PC
- snapshot 推送时带 `uploaded_at`，远端拒绝偏差 > 5min 的请求（防回放）
- 公开端点限频 60s/30 次/IP（远端侧实现）
- 设备 API Key 与 `created_by`（用户）双绑：吊销设备后该设备的所有 share 立即失效
- `api_key` + `hmac_secret` 按 **per-device** 模型生效：每个设备拥有独立的 `hmac_secret`，远端在 `device_keys` 表中按 `api_key` 索引，验签时取该行的 `hmac_secret` 而非全局共享密钥。轮换时只需重新生成一对，旧 share 立即失效。

## 7. 数据迁移

- 历史 `share_views` 表（公开访问审计）已通过 Alembic `18_remove_share_views_table.py` 删除；`downgrade()` 中保留重建脚本用于历史回退。
- 旧 `remote_status = LOCAL_ONLY` 的 token 在生产环境应被 `revoke`，新生成的 token 全部为远端四态。

## 8. 监控指标

| 指标 | 含义 | 告警阈值 |
|---|---|---|
| `share.remote_status = UPLOADED` 比例 | 远端上传成功率 | < 99% |
| `share.remote_status = FAILED` 且 5xx | 远端故障 | > 1% 持续 5min |
| 平均 `upload_to_remote` 耗时 | 远端网络质量 | > 2s |

## 9. 关键变更记录

| 变更 | 说明 |
|---|---|
| 删除 `ShareRemoteConfig.enabled` 字段 | 远端 / 本地不再二选一，凭据就绪即远端 |
| 删除 `ensure_remote_credentials` 的 `local` / `local_fallback` 路径 | 凭据缺失时直接抛 503 提示配置，不再生成 PC 本地凭据 |
| 移除 `share.remote_status = LOCAL_ONLY` 状态 | 远端四态收敛为 `PENDING` / `UPLOADED` / `FAILED` / `REVOKED` |
| 删除 `ShareView` 模型与 `share_views` 表 | 本地公开访问链路已下线 |
| 删除前端 `WorkerShareModal` 凭据生成 UI | 自动按需注册，前端无需引导 |
| 删除 `SharePage` 公开访问页 | 远端链接由 `share.quantcell.top` 静态站承接 |
| 删除 `/api/share/credentials/status` 与 `/api/share/credentials/generate` 端点 | 前端无调用方 |
| 删除 i18n 中 `share.local_only_hint` / `share.remote_unconfigured_*` / `share.credentials_*` / `share.generate_credentials` / `share.remote_mode_enabled` 等 key | 不再使用 |
