# 打包产物功能验证体系（文档即测试）

> 执行者：AI agent + 浏览器自动化。被测对象：打包产物（与 .app 同二进制同 dist），零安装。
> 每份页面文档必须做到**全新会话、零历史上下文可执行**——这是文档能当测试用的底线。

## 一、环境准备（唯一的环境vera源）

```bash
bash desktop/scripts/preview-packaged.sh   # 打包 sidecar + 同款 dist + /api 反代，Ctrl-C 一并收尾
```

- 前端：http://localhost:4173 ；sidecar：http://127.0.0.1:19999 ；日志与数据目录见脚本横幅
- 免登录（后端 `QUANTCELL_DESKTOP_LOCAL=1` 全量豁免鉴权，浏览器只需过前端守卫），
  在页面控制台执行后回首页：

```js
localStorage.setItem('quantcell_jwt_token', JSON.stringify({access_token:'desktop-local',refresh_token:'desktop-local'}));
localStorage.setItem('access_token', 'desktop-local'); location.href = '/';
```

  双 key 缺一不可：`AuthGuard` 读 `access_token`，请求头用 `quantcell_jwt_token` 对象。

## 二、验证层级

| 层级 | 何时跑 | 范围 |
|---|---|---|
| L1 冒烟 | 每次打包必跑 | 每页 1 条主路径，仅只读/可撤销操作 |
| L2 功能 | 页面首次落地或该区域有改动 | 该文档全部验证项 |
| 按需 | 手动触发，默认跳过并记录原因 | 标注"外部依赖"的项（真实 LLM 配额、交易所实时探测） |

`docs/testing/check-coverage.mjs` 对账路由表与 MANIFEST——新路由未登记直接失败：

```bash
node docs/testing/check-coverage.mjs   # 打包验证前必须全绿
```

## 三、每步证据采集（标准化，失败可归因前后端）

每个验证项固定采三样：
1. **关键可见文本**（页面实际渲染的关键字，≤1 行）
2. **该页发起的关键 API + 状态码**（`performance.getEntriesByType('resource')` 过滤 `/api/`，或 network 面板）
3. **控制台错误**（若有）

失败时追加：sidecar 日志对应时间窗（`$DATA_DIR/sidecar.log`，用时间过滤）。

## 四、报告格式

写入 `reports/YYYY-MM-DD-L<级别>.md`（追加式，不覆盖历史）：

```markdown
# 打包验证 YYYY-MM-DD L1
环境：sidecar mtime=<...>｜dist=<...>｜数据目录=<...>
| 页面 | 验证项 | 结果 | 证据 | 备注 |
|---|---|---|---|---|
结论：X 过 / Y 跳过（原因）/ Z 失败（归因）
```

## 五、失败分类（定位抓手）

- **前端渲染类**：文本缺失/组件未挂载 → 查页面文档"历史雷区"，多半有先例
- **边界契约类**：错误文案渲染成 `[object Object]`、状态码误判 → 后端错误体形状与前端解析不匹配
- **环境类**：端口占用、onefile 时代遗留（现 sidecar 为 onedir，冷启动 1-2 分钟内属正常）、token 注入遗漏 key
- **打包缺文件类**：PyInstaller 只保证 import 不炸（字节码进 PYZ），运行时按 `spec.origin`/`__file__` 读包内源文件的逻辑会静默缺文件（案例：`strategy/templates/*.py` 漏打 → 策略编辑器模板列表 500）。现由 `desktop/scripts/verify-sidecar.sh` 在 build-backend.sh 末尾冷启动打包产物、真打这些端点兜底；**新写「读包内文件」的端点时必须在脚本 CHECKS 清单补一行**

## 六、执行技巧（前人踩坑实录）

- **一次只验一条请求**：重复触发发送会让请求互相 abort，abort 气泡被 UI 过滤造成"错误静默"假阴性（详见 pages/strategy-editor.md 雷区栏）；每项验证前刷新页面重置状态
- **图标按钮没有文本**：用 `aria-label` 属性定位（如 AI 助手入口），文本扫描会漏
- antd Modal / CodeMirror 的 a11y 快照经常残缺 → 兜底用 DOM 直查（`document.querySelector('.ant-modal')`、`textarea`、`body.innerText`）
- 等待用**条件轮询**（wait_for 文本 / 轮询 location.pathname），不要死等固定时长
- 打包 sidecar（onedir）冷启动首跑要 import 全量路由 + 三方库，1-2 分钟内属正常，脚本已内置健康等待，见到 `/health ✓` 再动
- 页面登录门只认 token 存在性；后端 local 模式不校验值，任何非空 token 均可
- Tauri 壳专属能力（更新器、崩溃遮罩、系统代理继承、真实窗口行为）不在浏览器链路，**发布前仍需一次 .app 冒烟**（`open` + `/health` 探测，纯后端无需点界面）

## 七、文档维护规则

- 新增/修改页面功能：**同一变更内**更新对应 `pages/<功能区>.md` 的验证项（验收标准直接写成步骤），并在 MANIFEST 登记
- 验证项只写**行为与可观测信号**，禁写 CSS 类名等实现细节（重构不应弄断文档）
- 每个功能区一个文件；发现新雷区当场记入该文件的"历史雷区"栏
