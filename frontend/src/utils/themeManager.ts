/**
 * 主题管理工具
 * 处理浅色/深色模式切换
 */

// 主题类型定义
export type ThemeType = 'light' | 'dark' | 'auto';

/**
 * 应用主题
 * @param theme 主题模式
 */
export const applyTheme = (theme: ThemeType) => {
  const root = document.documentElement;
  
  // 移除现有的 theme 属性，恢复默认（浅色）
  root.removeAttribute('data-theme');

  if (theme === 'dark') {
    root.setAttribute('data-theme', 'dark');
  } else if (theme === 'auto') {
    // 跟随系统
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    if (mediaQuery.matches) {
      root.setAttribute('data-theme', 'dark');
    }
    
    // 监听系统变化 (注意：这里每次调用都会添加监听器，可能需要清理，但作为简单实现先这样)
    // 更完善的做法是在 useEffect 中处理监听
  }
};

/**
 * 初始化主题
 * 尝试从 localStorage 或 window.APP_CONFIG 获取主题配置
 */
export const initTheme = () => {
  // 优先从 APP_CONFIG 获取（如果是 SSR 或已注入）
  let theme: ThemeType = 'light';
  
  if (window.APP_CONFIG && window.APP_CONFIG.theme) {
    theme = window.APP_CONFIG.theme as ThemeType;
  }
  
  // 应用主题
  applyTheme(theme);
  
  // 监听系统主题变化
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  mediaQuery.addEventListener('change', (e) => {
    // 只有当当前设置为 auto 时才响应
    const currentSettings = window.APP_CONFIG?.theme || 'light'; // 默认 light
    if (currentSettings === 'auto') {
      if (e.matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
    }
  });
};
