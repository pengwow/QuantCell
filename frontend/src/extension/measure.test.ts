import { describe, it, expect } from 'vitest'
import { calcMeasureLabel, formatMeasureValue } from './measure'

describe('calcMeasureLabel', () => {
  it('上涨方向：价差与百分比均为正', () => {
    expect(calcMeasureLabel(100, 110)).toEqual({ diff: 10, pct: 10 })
  })

  it('下跌方向：价差与百分比均为负', () => {
    expect(calcMeasureLabel(100, 90)).toEqual({ diff: -10, pct: -10 })
  })
})

describe('formatMeasureValue', () => {
  it('常规价格保留 6 位有效数字', () => {
    expect(formatMeasureValue(123.456789)).toBe('123.457')
  })

  it('微小价格不丢失有效位（SHIB 级别）', () => {
    expect(formatMeasureValue(0.0000123456)).toBe('0.0000123456')
  })

  it('整数去尾零', () => {
    expect(formatMeasureValue(2)).toBe('2')
  })
})
