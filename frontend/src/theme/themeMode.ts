/**
 * 主题模式（用户选择）与生效主题（light|dark）的取值与落盘约定。
 *
 * 两个 key 分工，别合并：
 * - THEME_STORAGE_KEY 存**生效**主题（light|dark）：index.html 首帧脚本、登录页、设置页都按这个口径读，
 *   所以它必须永远是 light/dark，不能写 'system'（否则首帧会判成浅色闪屏）。
 * - THEME_MODE_STORAGE_KEY 存**用户选择**（light|dark|system）：只有顶栏胶囊/设置页写它，
 *   用来恢复「我选过浅色」这件事，而不是恢复「当时的系统刚好是浅色」。
 */
export type StoredThemeMode = 'light' | 'dark' | 'system';

export const THEME_STORAGE_KEY = 'quantcell-ui-theme';
export const THEME_MODE_STORAGE_KEY = 'quantcell-ui-theme-mode';
export const THEME_MODE_EVENT = 'quantcell-theme-mode-change';

export const systemTheme = (): 'light' | 'dark' =>
  window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

const isMode = (v: unknown): v is StoredThemeMode => v === 'light' || v === 'dark' || v === 'system';

/**
 * 读取用户选择。没有 mode 键时兼容旧数据：存量生效主题若与当前系统偏好不同，
 * 说明当初是显式选的；相同则无法区分，按「跟随系统」处理。
 */
export const readThemeMode = (): StoredThemeMode => {
  const saved = localStorage.getItem(THEME_MODE_STORAGE_KEY);
  if (isMode(saved)) return saved;
  const effective = localStorage.getItem(THEME_STORAGE_KEY);
  if ((effective === 'light' || effective === 'dark') && effective !== systemTheme()) return effective;
  return 'system';
};

/** 写入生效主题：html.dark / data-theme / 首帧脚本读的 key 三处同步。 */
export const applyEffectiveTheme = (theme: 'light' | 'dark') => {
  const html = document.documentElement;
  html.classList.toggle('dark', theme === 'dark');
  html.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_STORAGE_KEY, theme);
};

/** 写入用户选择并广播，让顶栏胶囊与设置页共享同一份模式。 */
export const writeThemeMode = (mode: StoredThemeMode) => {
  localStorage.setItem(THEME_MODE_STORAGE_KEY, mode);
  window.dispatchEvent(new CustomEvent<StoredThemeMode>(THEME_MODE_EVENT, { detail: mode }));
};