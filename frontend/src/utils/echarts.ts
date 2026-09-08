/**
 * echarts 按需注册入口
 * 全量 echarts 体积约 1MB，而项目实际只用 line/bar/radar 三类图表，
 * 通过 echarts/core 按需注册，将 chart-vendor 体积降低一个量级。
 * 新增图表类型时，在此注册对应 Chart 与 Component 即可。
 */
import * as echarts from 'echarts/core'
import { BarChart, LineChart, RadarChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer, SVGRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  RadarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  MarkLineComponent,
  DataZoomComponent,
  CanvasRenderer,
  SVGRenderer,
])

export default echarts