/**
 * 主题注册表 —— 合并层（内置主题 + packs/ 主题包）
 *
 * ▍管理员的两种改色路径（详见 docs/theme.md）：
 *   A. 改内置主题：编辑 builtin.ts 里 default 主题的亮/暗色值 —— 代码级、可评审。
 *   B. 导入主题包：`bun scripts/theme-import.mjs import <包>.json|.zip`
 *      → 包写入 packs/ 目录并自动并入本注册表；`use <id>` 一键启用。
 *
 *   两条路径都受 theme.test.ts 守护；点击生效需 `bun run build`（或开发态热更）。
 *
 * ▍字段分组命名约定 —— 见 builtin.ts / types.ts 注释。
 * ▍default 主题的值原样继承自 2026-11 重构前的既有字面量（保证零视觉回归）。
 */
import type { ThemeDefinition } from './types';
import { validateThemeData } from './fields';
import { BUILTIN_THEMES } from './builtin';

export const THEMES: Record<string, ThemeDefinition> = BUILTIN_THEMES;

/* ------------------------------------------------------------------ */
/*  主题包目录：packs/*.json 自动并入注册表                              */
/* ------------------------------------------------------------------ */
/* 维护者无需改 TS：把主题包 JSON（可由 scripts/theme-import.mjs 生成/校验）
   放进 src/theme/packs/ 即注册，文件名（去扩展名，kebab-case）即主题 ID。
   包结构 {label, light, dark}，字段契约见 fields.ts；坏包在加载期直接抛错。
   与内置主题同名的包会被拒绝（内置 default 是像素基准，不允许覆盖）。 */
const packModules = import.meta.glob<{ default?: unknown } | unknown>('./packs/*.json', { eager: true });
for (const [path, mod] of Object.entries(packModules)) {
  const id = path.replace(/^\.\/packs\//, '').replace(/\.json$/, '');
  const data = (mod as { default?: unknown }).default ?? mod;
  const errors = validateThemeData(data);
  if (errors.length > 0) {
    throw new Error(`[theme] 主题包 ${path} 非法:\n  - ${errors.join('\n  - ')}`);
  }
  if (THEMES[id]) {
    throw new Error(`[theme] 主题包 ${path} 与内置主题/其他包重名: "${id}"（重命名文件后重试）`);
  }
  THEMES[id] = data as ThemeDefinition;
}
