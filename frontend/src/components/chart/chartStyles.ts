/**
 * 图表样式对象的路径读写辅助
 * klinecharts 的 styles 是深层嵌套对象（如 candle.priceMark.last.show），
 * 设置弹窗按路径取值/回写，避免引入 lodash.set 这类额外依赖。
 */
import type { ThemeMode } from '@/theme';

/** 按 'candle.priceMark.last.show' 读取嵌套值 */
export const getStyleValue = (styles: unknown, path: string): unknown =>
  path
    .split('.')
    .reduce<unknown>((obj, key) => (obj as Record<string, unknown> | undefined)?.[key], styles);

/**
 * 当前图表主题模式：canvas 绘制代码拿不到 CSS 变量与 React 上下文，
 * 绘制时读根元素的主题类即可拿到当前模式（palette 由调用方 getPalette(mode) 读取）。
 */
export const currentChartThemeMode = (): ThemeMode =>
  typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? 'dark' : 'light';

/** 按 'candle.priceMark.last.show' 写入嵌套值（中间层缺失时自动补空对象） */
export const setStyleValue = (
  target: Record<string, unknown>,
  path: string,
  value: unknown,
): void => {
  const keys = path.split('.');
  const last = keys.pop() as string;
  keys
    .reduce<Record<string, unknown>>((obj, key) => {
      obj[key] ??= {};
      return obj[key] as Record<string, unknown>;
    }, target)[last] = value;
};
