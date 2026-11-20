# 登录注册（/login）

## 前置
- 环境见 `../README.md` 第一节。**本页是守卫外的唯一页面**：不要先注入 token（注入了也能直达，但那样验的不是登录页）
- 组件：`frontend/src/pages/login/LoginPage.tsx`；接口：`POST /api/v1/auth/login`、`POST /api/v1/auth/register`
- 打包验证默认走免登录注入（`../README.md` 第一节），本页 L1 只验「未登录时表单可渲染」；真实登录为 L2
- L2 项（A3/A4/A5）需要账号：`preview-packaged.sh` 默认数据目录 `$TMPDIR/quantcell-preview-data`，若沿用旧数据目录则 qa 账号仍在；全新数据目录（脚本默认每次重建）需先注册（见 A3）或直接跳过并记录原因

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| A1 | 未注入任何 token，直接打开 `/login` | 页面渲染登录卡片：品牌名 `QuantCell`、副标题`量化交易平台`、两个页签`登录`/`注册`、字段标签`用户名`/`密码`、主按钮`登录`；URL 保持 `/login` | L1 |
| A2 | 在登录页点击`注册`页签 | 表单切换为注册态：按钮文案变为`立即注册`，底部提示变为`创建账号后即可使用完整功能`；无网络请求（纯前端切换） | L1 |
| A3 | 在`注册`页签填写新用户名 + 密码（≥6 位），点`立即注册` | `POST /api/v1/auth/register` 返回 HTTP 200 且响应体 `code=0`；页面提示`注册成功，请使用新账号登录`，自动切回`登录`页签并回填用户名、密码清空（**不自动登录**） | L2（写操作，测试账号用 `zz_doc_<时间戳>`） |
| A4 | 在`登录`页签用已有账号（qa 账号或 A3 新建账号）填写正确的用户名/密码，点`登录` | `POST /api/v1/auth/login` 返回 HTTP 200 且响应体 `code=0`；提示`登录成功`并跳转 `/home`；浏览器 localStorage 同时写入 `access_token` 与 `quantcell_jwt_token`（两个 key 都在） | L2 |
| A5 | 用错误密码登录 | `POST /api/v1/auth/login` 仍是 **HTTP 200**，响应体 `code=401`、`message=用户名或密码错误`；页面弹出可读中文错误提示，停留 `/login`，不出现 `[object Object]` | L2（回归哨：状态码 ≠ 业务码） |
| A6 | 空表单直接点`登录` | 前端校验拦截：用户名/密码处出现`请输入用户名`/`请输入密码`；不发 `/auth/login` 请求 | L2 |

## 历史雷区
- **两个 token key 缺一不可**：`AuthGuard` 只读 `access_token`，请求头取 `quantcell_jwt_token` 对象。只注入其一会表现为"页面进得去、接口全 401"；免登录注入必须按 `../README.md` 第一节整段执行
- **登录/注册失败也是 HTTP 200**：后端把业务失败放在响应体 `code`（400/401/409），前端按 `data.code` 判定。拿状态码断言会把登录失败误判为成功
- **注册成功 ≠ 已登录**：注册接口不返回 token，页面切回登录页签并清空密码；断言"注册后直接进首页"必然失败
- **`redirect_after_login` 残留**：`AuthGuard` 会把被拦截的路径写进 sessionStorage，登录成功优先回跳该路径。自动化脚本若先访问过受保护页，A4 的落地页可能不是 `/home`，断言前清 sessionStorage 或先开 `/login`
- **local 模式不校验 token 值**：打包 sidecar 以 `QUANTCELL_DESKTOP_LOCAL=1` 运行，任何非空 token 都能过后端；A4 的"能进首页"不能证明账号密码校验链路正常，必须同时断言 `/auth/login` 的 `code=0`
