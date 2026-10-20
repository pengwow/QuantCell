import type React from 'react'

// 统一风格：24 viewBox / 18px / stroke 继承文字色（明暗主题免适配）
const svgProps = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round'
} as const

/** 小实心端点（线端圆点） */
const dot = (cx: number, cy: number) => (
  <circle cx={cx} cy={cy} r="1.6" fill="currentColor" stroke="none" />
)

/**
 * 绘图工具图标表：key 与 overlay name 一致（createOverlay 直接使用），
 * 另含 clear（清除全部按钮）。
 */
export const DRAWING_TOOL_ICONS: Record<string, React.ReactNode> = {
  // 线段：斜线 + 两端点
  segment: (
    <svg {...svgProps}><path d="M6 18 L18 6" />{dot(6, 18)}{dot(18, 6)}</svg>
  ),
  // 水平线：横线 + 左端点
  horizontalStraightLine: (
    <svg {...svgProps}><path d="M3 12 H21" />{dot(3, 12)}</svg>
  ),
  // 水平射线：左端点 + 向右射线
  horizontalRayLine: (
    <svg {...svgProps}>{dot(5, 12)}<path d="M5 12 H21" /></svg>
  ),
  // 水平线段：两端点横线
  horizontalSegment: (
    <svg {...svgProps}><path d="M5 12 H19" />{dot(5, 12)}{dot(19, 12)}</svg>
  ),
  // 垂直线
  verticalStraightLine: (
    <svg {...svgProps}><path d="M12 3 V21" />{dot(12, 3)}</svg>
  ),
  // 射线：左下端点 + 斜射线
  rayLine: (
    <svg {...svgProps}>{dot(5, 19)}<path d="M5 19 L20 4" /></svg>
  ),
  // 箭头：箭身 + 翼尖
  arrow: (
    <svg {...svgProps}><path d="M6 18 L18 6" /><path d="M10 6 H18 V14" /></svg>
  ),
  // 直线：双向延伸斜线（无端点，区别于线段）
  straightLine: (
    <svg {...svgProps}><path d="M3 21 L21 3" /></svg>
  ),
  // 涨跌测量：竖直双箭头 + 上下横线
  measure: (
    <svg {...svgProps}>
      <path d="M12 5 V19" />
      <path d="M9 8 L12 5 L15 8" />
      <path d="M9 16 L12 19 L15 16" />
      <path d="M6 5 H18" />
      <path d="M6 19 H18" />
    </svg>
  ),
  // 平行线：两条平行斜线
  parallelStraightLine: (
    <svg {...svgProps}><path d="M4 16 L16 4" /><path d="M8 20 L20 8" /></svg>
  ),
  // 矩形
  rect: (
    <svg {...svgProps}><rect x="4" y="6" width="16" height="12" rx="1" /></svg>
  ),
  // 价格线：横线 + 价格标签
  priceLine: (
    <svg {...svgProps}><path d="M3 12 H14" />{dot(14, 12)}<rect x="15" y="8" width="6" height="8" rx="1" /></svg>
  ),
  // 价格通道线：上下轨道线 + 中间虚线
  priceChannelLine: (
    <svg {...svgProps}>
      <path d="M4 6 H20" />
      <path d="M4 18 H20" />
      <path d="M4 12 H20" strokeDasharray="3 2.5" />
    </svg>
  ),
  // 斐波那契线：5 条左侧对齐、宽度递减的阶梯横线
  fibonacciLine: (
    <svg {...svgProps}>
      <path d="M6 5 H20" />
      <path d="M6 9 H18" />
      <path d="M6 13 H16" />
      <path d="M6 17 H14" />
      <path d="M6 21 H12" />
    </svg>
  ),
  // 清除全部：垃圾桶
  clear: (
    <svg {...svgProps}>
      <path d="M4 7 H20" />
      <path d="M9 7 V4 H15 V7" />
      <path d="M7 7 L8 21 H16 L17 7" />
    </svg>
  )
}
