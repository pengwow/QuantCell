/**
 * 成交/交易表的数字格式化。
 *
 * 存在的理由：后端历史记录存在缺字段的行（回测 cascade 旧数据 trades 缺
 * `quantity`、fills 缺 `price`），展示层直接 `undefined.toFixed()` 会抛
 * TypeError 并把整页打白（BacktestDetail 决策详情实录）。这里是展示边界，
 * 缺值/非有限值一律渲染 `—`，不让异常冒泡到 React 树。
 */
export const fmtNum = (value: number | null | undefined, digits: number): string =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
