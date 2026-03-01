import { useEffect } from 'react';
import { useTheme } from "ahooks";

const LOCAL_STORAGE_KEY = "quantcell-ui-theme";
if (!localStorage.getItem(LOCAL_STORAGE_KEY)) {
  localStorage.setItem(LOCAL_STORAGE_KEY, "dark");
}

export type UseBrowserThemeReturns = ReturnType<typeof useTheme>;

/**
 * 获取并设置当前浏览器系统主题。
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

  return themeState;
};

export default useBrowserTheme;
