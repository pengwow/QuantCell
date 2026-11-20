/**
 * 主题全局配置 —— 维护者唯一需要触碰的开关
 *
 * 一键切换全局主题：把 ACTIVE_THEME_ID 改成 palettes.ts 里注册的主题名即可
 * （satisfies 保证写错主题名在编译期直接报错）。
 * 刻意不做终端用户 UI 开关（需求明确：仅面向项目维护者）；
 * 后续要开放时，把 ACTIVE_THEME_ID 提到 localStorage / 后端 appearance 配置，
 * 读取点（index.ts 的 activeTheme）改为运行时求值即可，消费端无需改动。
 */
import { THEMES } from './palettes';
import { BUILTIN_THEMES } from './builtin';
import type { ThemeDefinition } from './types';

/** 当前生效的主题 ID：内置主题写错名字编译期即报错；主题包 ID 在模块加载期/测试校验 */
export const ACTIVE_THEME_ID = 'default' satisfies keyof typeof BUILTIN_THEMES;

export function resolveTheme(): ThemeDefinition {
  const theme = THEMES[ACTIVE_THEME_ID];
  if (!theme) {
    // 主题包 ID 的运行时兜底（scripts/theme-import.mjs use 写入的 id 未注册时在此暴露）
    throw new Error(`[theme] ACTIVE_THEME_ID "${ACTIVE_THEME_ID}" 未注册（检查 packs/ 或 builtin.ts）`);
  }
  return theme;
}
