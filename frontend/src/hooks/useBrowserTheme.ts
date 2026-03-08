import { useEffect, useCallback } from 'react';
import { useTheme } from "ahooks";

const LOCAL_STORAGE_KEY = "quantcell-ui-theme";

export type UseBrowserThemeReturns = ReturnType<typeof useTheme> & {
  setThemeMode: (mode: 'light' | 'dark' | 'system') => void;
};

/**
 * 获取并设置当前浏览器系统主题。
 * 注意：此 hook 现在与后端配置同步，不再在初始化时设置默认值。
 * 主题值应该从后端配置加载，并同步到 localStorage。
 * @returns {UseBrowserThemeReturns}
 */
const useBrowserTheme = (): UseBrowserThemeReturns => {
  const themeState = useTheme({ localStorageKey: LOCAL_STORAGE_KEY });

  // 同步主题到 html 元素的 class
  useEffect(() => {
    const html = document.documentElement;
    const { theme } = themeState;

    // theme 是实际计算后的主题（light 或 dark）
    if (theme === 'dark') {
      html.classList.add('dark');
    } else {
      html.classList.remove('dark');
    }
  }, [themeState.theme, themeState.themeMode]);

  // 包装 setThemeMode，确保同时更新 localStorage 和 HTML class
  const setThemeMode = useCallback((mode: 'light' | 'dark' | 'system') => {
    const html = document.documentElement;
    let effectiveTheme: 'light' | 'dark';

    if (mode === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      effectiveTheme = prefersDark ? 'dark' : 'light';
    } else {
      effectiveTheme = mode;
    }

    // 设置 localStorage
    localStorage.setItem(LOCAL_STORAGE_KEY, effectiveTheme);

    // 设置 HTML class
    if (effectiveTheme === 'dark') {
      html.classList.add('dark');
    } else {
      html.classList.remove('dark');
    }

    // 设置 data-theme 属性
    html.setAttribute('data-theme', effectiveTheme);

    // 触发 storage 事件，让 useTheme 感知变化
    window.dispatchEvent(new StorageEvent('storage', {
      key: LOCAL_STORAGE_KEY,
      newValue: effectiveTheme,
    }));
  }, []);

  return {
    ...themeState,
    setThemeMode,
  };
};

export default useBrowserTheme;
