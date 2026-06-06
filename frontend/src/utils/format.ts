/**
 * 量化交易数据格式化工具
 *
 * 集中管理数字、百分比、持仓时长等格式化逻辑，
 * 确保 Worker 详情页所有 tab 展示风格统一。
 */

// 量化行业标准颜色
export const QUANT_COLORS = {
  positive: '#52c41a', // 盈利 / 多头 / 涨
  negative: '#ff4d4f', // 亏损 / 空头 / 跌
  neutral: '#666666', // 中性
  warning: '#faad14', // 警告
  info: '#1890ff', // 信息
} as const

/**
 * 格式化美元金额：千分位 + 2 位小数 + $ 前缀
 * @example formatUSD(1234.567) => "$1,234.57"
 */
export const formatUSD = (value: number | null | undefined, options?: { showSign?: boolean; precision?: number }): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '$-'
  const precision = options?.precision ?? 2
  const sign = options?.showSign && value > 0 ? '+' : ''
  const formatted = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  })
  return `${sign}${value < 0 ? '-' : ''}$${formatted}`
}

/**
 * 格式化百分比：2 位小数 + % 后缀
 * @example formatPercent(12.345) => "12.35%"
 */
export const formatPercent = (
  value: number | null | undefined,
  options?: { showSign?: boolean; precision?: number }
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-%'
  const precision = options?.precision ?? 2
  const sign = options?.showSign && value > 0 ? '+' : ''
  return `${sign}${value.toFixed(precision)}%`
}

/**
 * 格式化加密货币数量：保留 6 位小数（精度满足大多数币种）
 * @example formatQuantity(0.000123456789) => "0.000123"
 */
export const formatQuantity = (value: number | null | undefined, precision = 6): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toFixed(precision)
}

/**
 * 格式化倍率：1 位小数 + x 后缀
 * @example formatLeverage(10) => "10x"
 */
export const formatLeverage = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-x'
  return `${value}x`
}

/**
 * 格式化持仓时长：将毫秒数转为 "Xd Yh Zm" 格式
 * @example formatHoldingDuration(186000000) => "2d 3h 40m"
 */
export const formatHoldingDuration = (startTime: string | number | Date | null | undefined): string => {
  if (!startTime) return '-'
  const start = new Date(startTime).getTime()
  if (Number.isNaN(start)) return '-'
  const diffMs = Date.now() - start
  if (diffMs < 0) return '-'

  const totalMinutes = Math.floor(diffMs / (1000 * 60))
  const days = Math.floor(totalMinutes / (60 * 24))
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) return `${days}d ${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

/**
 * 计算 ROE（投资回报率 %）：unrealized_pnl / margin_used * 100
 */
export const calcROE = (unrealizedPnl: number, marginUsed: number): number => {
  if (!marginUsed || marginUsed === 0) return 0
  return (unrealizedPnl / marginUsed) * 100
}

/**
 * 格式化时间戳：本地时区 YYYY-MM-DD HH:mm:ss
 */
export const formatTimestamp = (value: string | number | Date | null | undefined): string => {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '-'
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/**
 * 截断长 ID 用于表格显示
 * @example truncateId('abc123def456', 8, 4) => "abc123de...f456"
 */
export const truncateId = (id: string | null | undefined, head = 8, tail = 4): string => {
  if (!id) return '-'
  if (id.length <= head + tail + 3) return id
  return `${id.slice(0, head)}...${id.slice(-tail)}`
}
