# QuantCell 分享系统 远端集成（quantcell.top）

> 本文面向 PC 端 QuantCell 开发者，介绍如何配置、调试和监控 PC 端向 quantcell.top 推送分享的能力。

## 1. 架构速览

```
PC (QuantCell)
  ├── backend/share/config.py         集中读取 share_remote 配置
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

## 2. 三种工作模式

| `enabled` | `api_key` | `hmac_secret` | 行为 |
|---|---|---|---|
| ❌ | * | * | **本地模式**：仅生成 token，不推送，链接形如 `/share/<token>`（仅本机可见） |
| ✅ | 缺 | 缺 | 启动日志告警，自动降级本地 |
| ✅ | ✅ | ✅ | **远端模式**：推送 quantcell.top，返回 `https://share.quantcell.top/<token>` |

## 3. 凭据申请流程

1. 用户登录 `https://quantcell.top`（生产）或本地 mock 服务（开发）
2. 用户中心 → 设备管理 → 新建设备
3. 系统生成 `qck_<32 hex>` 格式的 **API Key** 和对应的 **HMAC Secret**（两者必须配对）
4. 把两者写入 `backend/config.local.toml`（必须 gitignore）：

   ```toml
   [share_remote]
   enabled = true
   api_key = "qck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   hmac_secret = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
   ```

5. 重启 backend，访问 `GET /api/share/health`（即将提供）确认远端连通

## 4. 调试步骤

```bash
# 1. 启动 mock 远端
cd mock_remote && uvicorn mock_remote:app --port 9999

# 2. 在 config.local.toml 中指向 mock
[share_remote]
enabled = true
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
| 远端 4xx（业务错误） | 不重试，remote_status=FAILED | 弹 toast "分享链接生成失败：<err>" |
| 远端 5xx | 重试 3 次后 FAILED | 同上 |
| 网络不可达 | 重试 3 次后 FAILED | 同上 |
| HMAC 验签错误（远端拒绝） | 不重试，remote_status=FAILED | 弹 toast "签名错误" |
| 凭据缺失 | 启动时降级 LOCAL_ONLY | 列表中 status 显示 "本地模式" |

## 6. 安全约束

- `hmac_secret` 一旦泄露应立即在用户中心**轮换**（生成新 key，旧 share 自动失效）
- PC 端**永不暴露公网**；远端无法回连 PC
- snapshot 推送时带 `uploaded_at`，远端拒绝偏差 > 5min 的请求（防回放）
- 公开端点限频 60s/30 次/IP（远端侧实现）
- 设备 API Key 与 `created_by`（用户）双绑：吊销设备后该设备的所有 share 立即失效

## 7. 数据迁移

旧 token（`remote_status = NULL`）继续走本地分享，链接形如 `/share/<token>`，**仅本机可见**。
提示用户重新生成以获得跨设备分享能力（前端在列表展示横幅"建议重新生成以获得跨设备分享能力"）。

## 8. 监控指标

| 指标 | 含义 | 告警阈值 |
|---|---|---|
| `share.remote_status = UPLOADED` 比例 | 远端上传成功率 | < 99% |
| `share.remote_status = FAILED` 且 5xx | 远端故障 | > 1% 持续 5min |
| 平均 `upload_to_remote` 耗时 | 远端网络质量 | > 2s |
