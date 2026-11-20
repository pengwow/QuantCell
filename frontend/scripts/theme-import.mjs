#!/usr/bin/env bun
/**
 * 主题包管理脚本（面向主题管理员）
 *
 * 用法（在 frontend/ 目录下）：
 *   bun scripts/theme-import.mjs import <主题包.json | 主题包.zip>
 *       校验并导入主题包 → 写入 src/theme/packs/<id>.json（id=文件名 stem，kebab-case）
 *   bun scripts/theme-import.mjs export [--all] [--out <dir>]
 *       导出已注册主题为 JSON（默认仅内置；--all 连同 packs 目录里的一起导出）
 *   bun scripts/theme-import.mjs use <themeId>
 *       一键启用：改写 src/theme/config.ts 的 ACTIVE_THEME_ID
 *   bun scripts/theme-import.mjs list
 *       列出全部已注册主题
 *
 * 导入后生效链：packs/*.json 在 Vite 构建时并入注册表（src/theme/palettes.ts），
 * 运行 `bun run test -- src/theme/theme.test.ts` 守卫 → `bun run build` 后全站生效。
 */
import { execSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename, join, resolve } from 'node:path';
import process from 'node:process';
import { validateThemeData } from '../src/theme/fields';

const FRONTEND_ROOT = resolve(import.meta.dir, '..');
const PACKS_DIR = join(FRONTEND_ROOT, 'src/theme/packs');
const CONFIG_FILE = join(FRONTEND_ROOT, 'src/theme/config.ts');

const ID_RE = /^[a-z][a-z0-9-]*$/;

/** 从 .json / .zip 读出主题包数据并校验；返回主题 id */
function readPack(inputPath) {
  const abs = resolve(inputPath);
  let data;
  let stem;
  if (abs.endsWith('.zip')) {
    // 压缩包：解到临时目录，取其中唯一（或第一个）.json
    const tmp = mkdtempSync('/tmp/qc-theme-');
    try {
      execSync(`unzip -o -q ${JSON.stringify(abs)} -d ${JSON.stringify(tmp)}`);
      const jsons = [];
      const walk = (dir) => {
        for (const name of readdirSync(dir, { withFileTypes: true })) {
          const p = join(dir, name.name);
          if (name.isDirectory()) walk(p);
          else if (name.name.endsWith('.json')) jsons.push(p);
        }
      };
      walk(tmp);
      if (jsons.length === 0) throw new Error('压缩包里没有 .json 主题包文件');
      if (jsons.length > 1) console.warn(`⚠ 压缩包里有 ${jsons.length} 个 .json，取第一个: ${basename(jsons[0])}`);
      data = JSON.parse(readFileSync(jsons[0], 'utf8'));
      stem = basename(jsons[0]).replace(/\.json$/, '');
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  } else {
    data = JSON.parse(readFileSync(abs, 'utf8'));
    stem = basename(abs).replace(/\.json$/, '');
  }
  const errors = validateThemeData(data);
  if (errors.length > 0) {
    console.error(`✗ 主题包校验失败（${errors.length} 项）：`);
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }
  let id = stem;
  if (!ID_RE.test(id)) {
    id = String(data.label ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'theme';
    console.warn(`⚠ 文件名 "${stem}" 不是合法主题 ID（kebab-case），改用 label 推导: "${id}"`);
  }
  return { id, data };
}

function cmdImport(inputPath) {
  const { id, data } = readPack(inputPath);
  mkdirSync(PACKS_DIR, { recursive: true });
  const out = join(PACKS_DIR, `${id}.json`);
  writeFileSync(out, `${JSON.stringify(data, null, 2)}\n`);
  console.log(`✓ 已导入主题 "${id}" → ${out}`);
  console.log(`  下一步：bun scripts/theme-import.mjs use ${id}   # 一键启用`);
  console.log(`  然后：bun run test -- src/theme/theme.test.ts && bun run build`);
}

async function loadRegistry() {
  // bun 不支持 Vite 的 import.meta.glob，不走 palettes.ts；
  // 注册表 = 内置主题（builtin.ts）+ packs/*.json（fs 直读），与 Vite 合并结果一致
  const { BUILTIN_THEMES } = await import('../src/theme/builtin');
  const themes = { ...BUILTIN_THEMES };
  let packs = [];
  try {
    packs = readdirSync(PACKS_DIR, { withFileTypes: true })
      .filter((d) => d.isFile() && d.name.endsWith('.json'))
      .map((d) => d.name.replace(/\.json$/, ''));
  } catch { /* 目录不存在 = 无主题包 */ }
  for (const id of packs) {
    const data = JSON.parse(readFileSync(join(PACKS_DIR, `${id}.json`), 'utf8'));
    if (validateThemeData(data).length > 0) throw new Error(`主题包 ${id} 非法（先跑 import 修复）`);
    if (themes[id]) throw new Error(`主题包 "${id}" 与内置主题重名`);
    themes[id] = data;
  }
  return themes;
}

async function cmdExport(args) {
  const all = args.includes('--all');
  const outIdx = args.indexOf('--out');
  const outDir = outIdx >= 0 ? resolve(args[outIdx + 1]) : join(FRONTEND_ROOT, 'theme-exports');
  const THEMES = await loadRegistry();
  mkdirSync(outDir, { recursive: true });
  let count = 0;
  for (const [id, theme] of Object.entries(THEMES)) {
    if (!all && id !== 'default') continue;
    const file = join(outDir, `${id}.json`);
    writeFileSync(file, `${JSON.stringify({ label: theme.label, ...theme }, null, 2)}\n`);
    console.log(`✓ 导出 ${id} → ${file}`);
    count++;
  }
  console.log(`提示：改完 JSON 后用 \`bun scripts/theme-import.mjs import ${outDir}/<id>.json\` 重新导入`);
  return count;
}

function cmdUse(id) {
  const config = readFileSync(CONFIG_FILE, 'utf8');
  const next = config.replace(
    /export const ACTIVE_THEME_ID = '[^']+' satisfies/,
    `export const ACTIVE_THEME_ID = '${id}' satisfies`,
  );
  if (next === config) {
    console.error('✗ 未找到/未修改 ACTIVE_THEME_ID —— config.ts 结构可能被手改，请手动编辑');
    process.exit(1);
  }
  writeFileSync(CONFIG_FILE, next);
  console.log(`✓ ACTIVE_THEME_ID → "${id}"；运行测试与构建后全站生效`);
}

function cmdList() {
  // list 走文件系统，不依赖 import.meta.glob（避免 bun 环境差异）
  const packs = readdirSync(PACKS_DIR, { withFileTypes: true })
    .filter((d) => d.isFile() && d.name.endsWith('.json'))
    .map((d) => d.name.replace(/\.json$/, ''));
  console.log('内置主题: default');
  console.log(`主题包(packs): ${packs.length ? packs.join(', ') : '（无）'}`);
}

const [, , cmd, ...rest] = process.argv;
if (cmd === 'import' && rest[0]) cmdImport(rest[0]);
else if (cmd === 'export') await cmdExport(rest);
else if (cmd === 'use' && rest[0]) cmdUse(rest[0]);
else if (cmd === 'list') cmdList();
else {
  console.log('QuantCell 主题包管理\n  bun scripts/theme-import.mjs import <file.json|.zip>\n  bun scripts/theme-import.mjs export [--all] [--out <dir>]\n  bun scripts/theme-import.mjs use <themeId>\n  bun scripts/theme-import.mjs list');
}
