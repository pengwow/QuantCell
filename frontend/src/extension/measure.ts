/**
 * 涨跌测量 overlay：复刻 QuantDinger priceRangeMeasure。
 * 本文件第一部分是可测试的纯函数；overlay 模板在文件后半部分（Task 2 追加）。
 */
import type { OverlayTemplate } from 'klinecharts'

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

// 量线两端短横线的半长（px）与箭头翼尖尺寸（px）
const TICK = 5
const WING = 6

// 涨绿跌红，与 K 线主体配色惯例一致（现有 extension 均为硬编码色值，测量保持同一模式）
const COLOR_UP = '#26a69a'
const COLOR_DOWN = '#ef5350'

/**
 * 测量 overlay：起点/终点竖直量线（双箭头）+ 上下端横线 + 中部价差/涨跌幅标签。
 * totalStep 3 = 两次点击完成。
 */
const measure: OverlayTemplate = {
  name: 'measure',
  totalStep: 3,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ overlay, coordinates }) => {
    if (coordinates.length < 2) return []
    const start = overlay.points[0]
    const end = overlay.points[1]
    if (start.value == null || end.value == null) return []

    const { diff, pct } = calcMeasureLabel(start.value, end.value)
    const color = pct >= 0 ? COLOR_UP : COLOR_DOWN

    // 量线贴终点一侧；两端点上下顺序不定，箭头统一"向外"指
    const x = Math.max(coordinates[0].x, coordinates[1].x)
    const topY = Math.min(coordinates[0].y, coordinates[1].y)
    const bottomY = Math.max(coordinates[0].y, coordinates[1].y)
    const midY = (topY + bottomY) / 2
    const label = `${formatMeasureValue(diff)} (${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%)`

    return [
      // 上端横线
      { type: 'line', ignoreEvent: true, attrs: { coordinates: [{ x: x - TICK, y: topY }, { x: x + TICK, y: topY }] }, styles: { style: 'stroke', stroke: color, strokeWidth: 1 } },
      // 下端横线
      { type: 'line', ignoreEvent: true, attrs: { coordinates: [{ x: x - TICK, y: bottomY }, { x: x + TICK, y: bottomY }] }, styles: { style: 'stroke', stroke: color, strokeWidth: 1 } },
      // 竖直量线
      { type: 'line', attrs: { coordinates: [{ x, y: topY }, { x, y: bottomY }] }, styles: { style: 'stroke', stroke: color, strokeWidth: 1.5 } },
      // 上端箭头翼尖（朝上）
      { type: 'line', ignoreEvent: true, attrs: { coordinates: [{ x: x - WING / 2, y: topY + WING }, { x, y: topY }, { x: x + WING / 2, y: topY + WING }] }, styles: { style: 'stroke', stroke: color, strokeWidth: 1.5 } },
      // 下端箭头翼尖（朝下）
      { type: 'line', ignoreEvent: true, attrs: { coordinates: [{ x: x - WING / 2, y: bottomY - WING }, { x, y: bottomY }, { x: x + WING / 2, y: bottomY - WING }] }, styles: { style: 'stroke', stroke: color, strokeWidth: 1.5 } },
      // 价差/涨跌幅标签（ponytail: 无背景板，可读性不够时再加半透明 rect）
      { type: 'text', ignoreEvent: true, attrs: { x: x + 8, y: midY, text: label, align: 'left', baseline: 'middle' }, styles: { style: 'fill', color, size: 11, family: 'sans-serif' } }
    ]
  }
}

export default measure
