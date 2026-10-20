/**
 * 图表样式对象的路径读写辅助
 * klinecharts 的 styles 是深层嵌套对象（如 candle.priceMark.last.show），
 * 设置弹窗按路径取值/回写，避免引入 lodash.set 这类额外依赖。
 */

/** 按 'candle.priceMark.last.show' 读取嵌套值 */
export const getStyleValue = (styles: unknown, path: string): unknown =>
  path
    .split('.')
    .reduce<unknown>((obj, key) => (obj as Record<string, unknown> | undefined)?.[key], styles);

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
