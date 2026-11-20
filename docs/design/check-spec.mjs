#!/usr/bin/env node
/**
 * 规范 ↔ 基准 demo 一致性校验（无依赖，node docs/design/check-spec.mjs）
 *
 * 守护三件事：
 *  1. docs/design-spec.md §2.2 的 token 块与 demo 的 :root / [data-theme=dark] 逐值相等；
 *  2. demo 里每个 .view 的 id 都有 TITLES 路由（v4 曾因 view-btconfig 与路由名不一致整页黑屏）；
 *  3. demo 中 var(--x) 引用的变量都有定义（曾漏定义 --card 导致弹窗透明底）。
 * 另附关键几何值抽样断言。任一项失败退出码 1。
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
const demo = readFileSync(join(dir, 'qc-prototype-demo.html'), 'utf8');
const spec = readFileSync(join(dir, '..', 'design-spec.md'), 'utf8');

let fail = 0;
const ok = (cond, msg) => { console.log(`${cond ? 'PASS' : 'FAIL'}  ${msg}`); if (!cond) fail++; };

/* ---------- 1. token 块逐值比对 ---------- */
const tokensOf = (css) => {
  const m = new Map();
  for (const [, k, v] of css.matchAll(/^\s*(--[\w-]+):\s*([^;]+);/gm)) m.set(k, v.trim());
  return m;
};
const cssBlock = (src, re, label) => {
  const m = src.match(re);
  if (!m) throw new Error(`未找到 ${label} 的 token 块`);
  return tokensOf(m[0]);
};

const specCss = spec.match(/```css\n([\s\S]*?)```/)[1]; // §2.2 单一围栏内含亮暗两块
const pairs = [
  ['light', /:root, html\[data-theme='light'\] \{[\s\S]*?\n\s*\}/],
  ['dark', /html\[data-theme='dark'\] \{[\s\S]*?\n\s*\}/],
];
for (const [name, re] of pairs) {
  const d = cssBlock(demo, re, `demo ${name}`);
  const s = cssBlock(specCss, re, `spec ${name}`);
  for (const [k, v] of s) ok(d.get(k) === v, `${name} ${k}: spec=${v} demo=${d.get(k) ?? '<缺失>'}`);
  for (const k of d.keys()) ok(s.has(k), `${name} ${k}: demo 有而 spec 未收录（${d.get(k)}）`);
  ok(d.size === s.size, `${name} token 数量 spec=${s.size} demo=${d.size}`);
}

/* ---------- 2. 视图 id ↔ 路由表 ---------- */
const viewIds = [...demo.matchAll(/<section class="view[^"]*" id="view-([\w-]+)"/g)].map(m => m[1]);
const titles = [...demo.match(/var TITLES = \{[\s\S]*?\};/)[0].matchAll(/(?:'([\w-]+)'|(\w+)):\s*'/g)]
  .map(m => m[1] ?? m[2]);
ok(viewIds.length === titles.length, `视图数 ${viewIds.length} == 路由数 ${titles.length}`);
for (const v of viewIds) ok(titles.includes(v), `view-${v} 有对应路由`);
for (const t of titles) ok(viewIds.includes(t), `路由 ${t} 有对应视图`);

/* ---------- 3. var() 引用都有定义 ---------- */
const defined = new Set([...demo.matchAll(/^\s*(--[\w-]+):/gm)].map(m => m[1]));
const used = new Set([...demo.matchAll(/var\((--[\w-]+)/g)].map(m => m[1]));
for (const v of used) ok(defined.has(v), `var(${v}) 已定义`);

/* ---------- 4. 关键几何抽样 ---------- */
const geometry = [
  ['Header 52px', 'height:52px; flex:0 0 52px'],
  ['Sider 216px', 'flex:0 0 216px'],
  ['正文 13px', 'font-size:13px; color:var(--fg); overflow:hidden'],
  ['卡片 10px/12px 14px', '.card { background:var(--bgc); border:1px solid var(--bd); border-radius:10px; padding:12px 14px'],
  ['表头 10.5px/9px 12px', '.bt th { font-size:10.5px; font-weight:500; color:var(--fg-4); text-align:left; padding:9px 12px'],
  ['表格 td 12px/10px 12px', '.bt td { padding:10px 12px; font-size:12px'],
  ['弹窗 560px/14px', 'width:min(560px, 94vw); max-height:86vh; display:flex; flex-direction:column; border-radius:14px'],
  ['按钮 30px/8px', '.btn {'],
  ['页码钮 28px', 'height:28px'],
  ['导航项 13px', 'font:inherit; font-size:13px; cursor:pointer; text-align:left; white-space:nowrap'],
];
for (const [label, needle] of geometry) ok(demo.includes(needle), `几何 ${label}`);

console.log(fail ? `\n✗ ${fail} 项不一致` : '\n✓ 规范与 demo 完全一致');
process.exit(fail ? 1 : 0);
