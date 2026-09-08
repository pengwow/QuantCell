/**
 * ECharts 包装组件
 * 用统一的按需 echarts 实例替代 echarts-for-react 默认的全量 echarts，
 * 业务侧用法与 <ReactECharts /> 完全一致，仅 import 来源不同。
 */
import ReactEChartsCore from 'echarts-for-react/lib/core'
import type { EChartsReactProps } from 'echarts-for-react/lib/types'
import echarts from '@/utils/echarts'

const EChart = (props: EChartsReactProps) => (
  <ReactEChartsCore echarts={echarts} {...props} />
)

export default EChart