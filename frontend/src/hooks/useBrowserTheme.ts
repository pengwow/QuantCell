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
  return useTheme({ localStorageKey: LOCAL_STORAGE_KEY });
};

export default useBrowserTheme;
