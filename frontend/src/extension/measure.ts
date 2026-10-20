/**
 * 涨跌测量 overlay：复刻 QuantDinger priceRangeMeasure。
 * 本文件第一部分是可测试的纯函数；overlay 模板在文件后半部分（Task 2 追加）。
 */

/**
 * 计算测量标签数据：价差与涨跌幅（百分比数值）。
 * 精度口径与 utils.ts 的斐波那契计算一致（toFixed(8)，ponytail: 8 位小数上限）。
 */
export function calcMeasureLabel(start: number, end: number): { diff: number; pct: number } {
  const diff = Number((end - start).toFixed(8))
  const pct = Number(((end - start) / start * 100).toFixed(2))
  return { diff, pct }
}

/**
 * 格式化数值：6 位有效数字，Number 转回去掉尾零。
 */
export function formatMeasureValue(value: number): string {
  return String(Number(value.toPrecision(6)))
}
