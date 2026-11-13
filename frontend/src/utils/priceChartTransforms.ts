/**
 * 图表派生 bar 变换函数（平均K线 / HLC 面积 / 砖形 / 范围图）。
 *
 * klinecharts 只内置 6 种蜡烛形状，其余图表类型通过「把 OHLC 序列变换为
 * 派生 bar 序列」实现：图表仍用原生 candle_solid / area 渲染，数据由这里产出。
 * 变换均为纯函数，输入原始 bar 集合，输出同结构的派生 bar 集合。
 */
import type { KLineData } from 'klinecharts';

type BarOptions = { atrLength?: number; rangeSize?: number; boxSize?: number };

// 变换过程中的 K 线形态：volume 归一为必填（KLineData 中为可选）
type TransformBar = Required<Pick<KLineData, 'timestamp' | 'open' | 'high' | 'low' | 'close' | 'volume'>>;

// 非法数值容错：变换过程若混入 NaN 会污染整条序列，这里统一清洗后过滤
const finiteNumber = (value: unknown): number | null => {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const normalizeRows = (rows: KLineData[]): TransformBar[] =>
  (Array.isArray(rows) ? rows : [])
    .map((row) => ({
      ...row,
      timestamp: finiteNumber(row.timestamp) as number,
      open: finiteNumber(row.open),
      high: finiteNumber(row.high),
      low: finiteNumber(row.low),
      close: finiteNumber(row.close),
      volume: finiteNumber(row.volume) || 0,
    }))
    .filter(
      (row): row is TransformBar =>
        row.timestamp != null && row.open != null && row.high != null && row.low != null && row.close != null,
    )
    .sort((a, b) => a.timestamp - b.timestamp);

/** 平均K线图：open 取前一根 HA 开收均值，close 取四价均值，平滑涨跌方向 */
export function buildHeikinAshiRows (rows: KLineData[]): KLineData[] {
  const data = normalizeRows(rows)
  let previousOpen: number | null = null
  let previousClose: number | null = null

  return data.map((row, index) => {
    const close = (row.open + row.high + row.low + row.close) / 4
    const open = index === 0
      ? (row.open + row.close) / 2
      : ((previousOpen as number) + (previousClose as number)) / 2
    const transformed = {
      ...row,
      open,
      high: Math.max(row.high, open, close),
      low: Math.min(row.low, open, close),
      close
    }
    previousOpen = open
    previousClose = close
    return transformed
  })
}

/** HLC 面积图：close 压缩为高低收三元均值，配合 area 渲染得到「区域」观感 */
export function buildHlcAreaRows (rows: KLineData[]): KLineData[] {
  return normalizeRows(rows).map(row => ({
    ...row,
    close: (row.high + row.low + row.close) / 3
  }))
}

/**
 * 用近期真实波幅（简化 ATR，默认 14 周期）估算砖形/范围图的每格尺寸；
 * 无有效样本时退化为「末价 0.5%」，避免因数据过短而渲染空白。
 */
function calculateTrueRangeSize (rows: KLineData[], atrLength = 14): number {
  const data = normalizeRows(rows)
  if (data.length < 2) return 0

  const trueRanges = []
  for (let index = 1; index < data.length; index += 1) {
    const current = data[index]
    const previous = data[index - 1]
    trueRanges.push(Math.max(
      current.high - current.low,
      Math.abs(current.high - previous.close),
      Math.abs(current.low - previous.close)
    ))
  }

  const sample = trueRanges.slice(-Math.max(1, Number(atrLength) || 14)).filter(value => value > 0)
  const atr = sample.length ? sample.reduce((sum, value) => sum + value, 0) / sample.length : 0
  const lastClose = Math.abs(data[data.length - 1].close)
  const fallback = lastClose > 0 ? lastClose * 0.005 : 0.01
  return Math.max(atr || fallback, fallback * 0.1, Number.EPSILON)
}

/** 砖形图：价格每净变动一格画一块砖，反向需 2 格才翻转（过滤噪音波动） */
export function buildRenkoBricks (rows: KLineData[], options: BarOptions = {}): KLineData[] {
  const data = normalizeRows(rows)
  if (data.length < 2) return []

  const requestedBoxSize = finiteNumber(options.boxSize)
  const boxSize = requestedBoxSize && requestedBoxSize > 0
    ? requestedBoxSize
    : calculateTrueRangeSize(data, options.atrLength)
  if (!Number.isFinite(boxSize) || boxSize <= 0) return []

  const bricks = []
  let brickClose = data[0].close
  let direction = 0
  let lastTimestamp = data[0].timestamp - 1

  for (let index = 1; index < data.length; index += 1) {
    const row = data[index]
    const difference = row.close - brickClose
    const nextDirection = Math.sign(difference)
    if (!nextDirection) continue

    const reversing = Boolean(direction && nextDirection !== direction)
    // 反转阈值翻倍是砖形图的通用口径：先回到原方向起点才算有效翻转
    const reversalThreshold = reversing ? boxSize * 2 : boxSize
    if (Math.abs(difference) + Number.EPSILON < reversalThreshold) continue

    const distanceInBoxes = Math.floor((Math.abs(difference) + Number.EPSILON) / boxSize)
    const brickCount = reversing ? distanceInBoxes - 1 : distanceInBoxes
    if (!brickCount) continue
    const volumePerBrick = row.volume / brickCount

    for (let brickIndex = 0; brickIndex < brickCount; brickIndex += 1) {
      const open = reversing && brickIndex === 0
        ? brickClose + nextDirection * boxSize
        : brickClose
      const close = reversing && brickIndex === 0
        ? brickClose + nextDirection * boxSize * 2
        : brickClose + nextDirection * boxSize
      // 派生 bar 无真实时间轴：同源 row 顺延 +1 保证严格递增（klinecharts 要求时间轴单调）
      const timestamp = Math.max(row.timestamp + brickIndex, lastTimestamp + 1)
      bricks.push({
        timestamp,
        open,
        high: Math.max(open, close),
        low: Math.min(open, close),
        close,
        volume: volumePerBrick
      })
      brickClose = close
      lastTimestamp = timestamp
    }

    direction = nextDirection
  }

  return bricks as KLineData[]
}

/** 范围图：按固定价格区间切分走势，把每个区间收敛为一根「方向性」bar */
export function buildRangeBars (rows: KLineData[], options: BarOptions = {}): KLineData[] {
  const data = normalizeRows(rows)
  if (data.length < 2) return []

  const rangeSize = (() => {
    const requested = finiteNumber(options.rangeSize)
    return requested && requested > 0 ? requested : calculateTrueRangeSize(data, options.atrLength)
  })()
  if (!Number.isFinite(rangeSize) || rangeSize <= 0) return []

  const bars = []
  let barClose = data[0].close
  let lastTimestamp = data[0].timestamp - 1

  for (let index = 1; index < data.length; index += 1) {
    const row = data[index]
    let remaining = row.close - barClose
    const barCount = Math.floor((Math.abs(remaining) + Number.EPSILON) / rangeSize)
    if (!barCount) continue
    const volumePerBar = row.volume / barCount

    for (let barIndex = 0; barIndex < barCount; barIndex += 1) {
      const direction = Math.sign(remaining)
      const open = barClose
      const close = open + direction * rangeSize
      const timestamp = Math.max(row.timestamp + barIndex, lastTimestamp + 1)
      bars.push({
        timestamp,
        open,
        high: Math.max(open, close),
        low: Math.min(open, close),
        close,
        volume: volumePerBar
      })
      barClose = close
      remaining = row.close - barClose
      lastTimestamp = timestamp
    }
  }

  return bars as KLineData[]
}
