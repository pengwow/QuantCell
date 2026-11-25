import { useCallback, useEffect, useState } from 'react';
import {
  THEME_MODE_EVENT,
  applyEffectiveTheme,
  readThemeMode,
  systemTheme,
  writeThemeMode,
  type StoredThemeMode,
} from '@/theme/themeMode';

export type UseBrowserThemeReturns = {
  /** 生效主题（light|dark）：class/data-theme/图表配色都读它 */
  theme: 'light' | 'dark';
  /** 用户选择（light|dark|system）：顶栏胶囊的图标与文案读它 */
  themeMode: StoredThemeMode;
  setThemeMode: (mode: StoredThemeMode) => void;
};

/**
 * 浏览器主题：用户选择（mode）是唯一状态源，生效主题由 mode + 系统偏好派生。
 *
 * 之前这里把 ahooks.useTheme 的 themeMode 当状态，却越过它的 setter 直接写 localStorage，
 * 于是 React 里的 themeMode 永远停在初始值（通常 'system'）——顶栏胶囊点「浅色」后标签仍是「自动」，
 * 且系统偏好变化时会按 system 重新算主题，把用户显式选的浅色覆盖掉。
 */
const useBrowserTheme = (): UseBrowserThemeReturns => {
  const [themeMode, setMode] = useState<StoredThemeMode>(readThemeMode);
  const [system, setSystem] = useState<'light' | 'dark'>(systemTheme);

  // 跟随系统偏好（仅在 mode === 'system' 时用于派生）
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setSystem(mq.matches ? 'dark' : 'light');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // 设置页/其他 hook 实例改模式时同步（同文档 storage 事件不触发，走自定义事件）
  useEffect(() => {
    const onMode = (e: Event) => {
      const mode = (e as CustomEvent<StoredThemeMode>).detail;
      if (mode) setMode(mode);
    };
    window.addEventListener(THEME_MODE_EVENT, onMode);
    return () => window.removeEventListener(THEME_MODE_EVENT, onMode);
  }, []);

  const theme: 'light' | 'dark' = themeMode === 'system' ? system : themeMode;

  // 生效主题落到 html + 首帧 key
  useEffect(() => {
    applyEffectiveTheme(theme);
  }, [theme]);

  const setThemeMode = useCallback((mode: StoredThemeMode) => {
    setMode(mode);
    writeThemeMode(mode);
  }, []);

  return { theme, themeMode, setThemeMode };
};

export default useBrowserTheme;