#!/usr/bin/env node
// 路由覆盖率闸门：frontend/src/router/DynamicRouter.tsx 里的每个路由都必须在
// docs/testing/MANIFEST.md 登记（含"文档待补"状态亦可），新页面漏登记直接失败。
// 这是"新增功能必须带验证文档"的机械保证——不靠自觉。
//
// 归一化约定（依赖 DynamicRouter.tsx 的书写惯例：父路由先于子路由出现）：
//   - 相对路径（不以 / 开头）拼接到最近的绝对路径之后（如 'account' → /setting/account）
//   - 参数段原样保留（:workerId 等），MANIFEST 用相同写法
//   - element 为 <Navigate> 的重定向路由、根路径 '/'、插件动态路由（pr.path）不在对账范围
// 用法: node docs/testing/check-coverage.mjs
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const routerSrc = readFileSync(join(root, 'frontend/src/router/DynamicRouter.tsx'), 'utf8');
const manifest = readFileSync(join(root, 'docs/testing/MANIFEST.md'), 'utf8');

const routes = [];
let lastAbsolute = '';
for (const line of routerSrc.split('\n')) {
  const m = line.match(/path: '([^']+)'/);
  if (!m) continue;
  const raw = m[1];
  if (line.includes('<Navigate')) continue; // 重定向：目标页面所在行已对账
  if (raw === '/') continue; // 根布局，由子路由覆盖
  const full = raw.startsWith('/') ? raw : `${lastAbsolute}/${raw}`;
  if (raw.startsWith('/')) lastAbsolute = raw;
  if (full.startsWith('/setting/')) {
    // /setting 为布局父级，其子页属设置功能区；折叠到 /setting/*（见 MANIFEST）
    continue;
  }
  routes.push(full);
}

const missing = [];
for (const r of [...new Set(routes)].sort()) {
  if (!manifest.includes(r)) missing.push(r);
}

// 待补清单：MANIFEST 行内含 ⏳ 的路由（不失败，仅提醒 L2 未覆盖）
const pendingRows = manifest
  .split('\n')
  .filter((l) => l.includes('|') && l.includes('⏳'))
  .map((l) => l.split('|')[1]?.trim())
  .filter(Boolean);

if (missing.length) {
  console.error('>> 以下路由未在 docs/testing/MANIFEST.md 登记：');
  for (const r of missing) console.error('   ' + r);
  console.error('>> 新页面必须同步登记（状态允许"文档待补"，但不允许不登记）。');
  process.exit(1);
}

console.log(`>> 路由覆盖率闸门通过：${[...new Set(routes)].length} 个路由全部登记。`);
if (pendingRows.length) {
  console.log(`>> 其中 ${pendingRows.length} 项文档待补（L2 覆盖前不得宣称该区域已验证）：`);
  for (const r of pendingRows) console.log('   ' + r);
}
