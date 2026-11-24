# 全站通用 chrome（toast / notification / 字体栈 · 行内展开面板）

## 前置
- 本验证项挂在任意已登录页（不必单独路由），建议在首页或设置页做触发
- 规范：`docs/design-spec.md` §6.12；实现：`frontend/src/global.css` §6.12 段
- 词条：`message`（antd）= toast（右下角）；`notification` = 通知中心条目（右上角，另一原语）

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| C1 | 任一页触发一条 message 提示（如设置页保存、操作成功反馈） | 提示条出现在**视口右下角**（距右/距下各约 18px），不是 antd 默认的顶部居中；浏览器窗口缩放时位置跟随视口右下 | L1 |
| C2 | 观察 toast 条目形制 | 卡片底（亮色白/暗色深灰，跟主题 token）+ 1px 边框 + **左缘 3px 状态色竖条** + 9px 圆角 + 等宽字体小字（11.5px 级）+ 阴影；最长约 340px，过长文本换行不撑破 | L1 |
| C3 | 快速连续触发 3 条 message（如重复保存） | 3 条**纵向堆叠、间距约 8px、不重叠**，后发的在最下；入场自下升入（约 0.2s），消失时淡出下坠，剩余条目平滑上收 | L1 |
| C4 | 对照 4 种类型（success/error/warning/info，遇场景就地取证） | 左缘竖条与图标颜色分别对应成功/失败/警告/提示语义色；**不得残留 antd 默认绿/红**；亮暗两轮均跟随主题 token | L1 |
| C5 | 触发 notification（产品入口：更新提示、后台任务推送等） | 条目仍出现在**右上角**；面板为卡片底+1px 边+10px 圆角+卡片阴影，标题语义色图标在左；与 toast 右缘对齐（18px 网格）；无现成入口时如实记录「未触发」 | L1（条件式） |
| C6 | 亮/暗主题切换走查 | toast 底色/文字/边框、notification 面板全部随 token 切换，暗色下**不得白底黑底错乱**；切换无布局跳动 | L1 |
| C7 | 任一列表页点行展开（回测中心/策略管理/因子分析/策略智能体/模型中心/数据管理任务行） | 面板四周留白与 demo 同口径：展开行 td `9px 12px` + 面板 `margin:8px 10px 10px` + `padding:12px 14px`（视觉上 17 / 下 20 / 侧 22）；面板底 = 卡片面 token（`--qc-surface`），与 td 淡底（`2.5% text`）**不同层不双卡**；面板内指标卡 `10px 12px` / 8px 圆角 / 无投影 | L2 |
| C8 | 对照 demo 检查全局字体 | `html/body` 与 Portal（Modal/Drawer/下拉）字体族 = demo 同款系统栈（`-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei", sans-serif`）；侧栏菜单 13px、分组标题 10.5px/.16em、品牌 14px/700、面包屑 13px 与 demo 一致；**不得出现未加载的 webfont 首选（如 Inter）** | L2 |

## 历史雷区
- （§6.12 初版）antd message 的 top/left/transform 来自 rc-notification **内联样式**，任何仅靠提高类特异性的覆盖都压不过——历史教训：看到 toast 仍在顶部居中先查 `!important` 是否在位
- antd 原生 move-up 入场关键帧带 padding 动画（间距动画），与「wrapper 无 padding + 容器 gap」的间距方案冲突，曾会被误判为「间距 16px」——实现已整体替换动画，回归时注意 C3 的 8px 间距
- 主题色不在 CSS 里写死：success/error 图标若出现 antd 默认绿/红，说明 token 钉链被绕过（先查 global.css §6.12 段是否被改动）
- **行内展开面板「四周比 demo 宽」的两个真凶**（2026-11-23 修复，C7）：① antd 给展开行套 `.ant-table-expanded-row-fixed`（内联 `padding:16/margin:-8`，净 +8px），必须清零；② global.css 里展开行 `padding:0` 的规则特异性低于 tbody 密度规则（`tr > td` 的 `10px 12px` 会赢），实际从未生效——现按 demo **实测渲染值**对齐为 td `9px 12px`（demo 源码同样存在这条特异性事故，写 `padding:0` 却渲染 9/12）。别再改回 `padding:0`
- **字体栈不要写未加载的 webfont**（2026-11-23，C8）：`index.css` 的 `:root` 曾首选 `Inter` 但项目从未加载该字体，只在 `html/body` 与 Portal 上暴露回退差异（antd 树内被 ConfigProvider 兜住，看起来「没问题」）。字体族唯一真相 = demo body 规则
