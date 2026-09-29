/**
 * ECharts 包装组件
 * 用统一的按需 echarts 实例替代 echarts-for-react 默认的全量 echarts，
 * 业务侧用法与 <ReactECharts /> 完全一致，仅 import 来源不同。
 */
import ReactEChartsCoreImport from 'echarts-for-react/lib/core'
import type { EChartsReactProps } from 'echarts-for-react/lib/types'
import type { ComponentType } from 'react'
import echarts from '@/utils/echarts'

// Vite dev 下深层 CJS 入口（echarts-for-react/lib/core，末尾仅 exports.default）
// 若未被预构建做 __esModule interop，default import 会拿到 { default: 组件 } 模块对象，
// 直接渲染会抛 "Element type is invalid ... got: object" 导致整页白屏（懒加载 chunk 必现）。
// 这里兼容两种形态：对象取 .default，生产 rollup 已正确 interop（.default 为 undefined）则回退自身。
const ReactEChartsCore = (
  (ReactEChartsCoreImport as unknown as { default?: ComponentType<EChartsReactProps> }).default ??
  ReactEChartsCoreImport
) as ComponentType<EChartsReactProps>

const EChart = (props: EChartsReactProps) => (
  <ReactEChartsCore echarts={echarts} {...props} />
)

export default EChart