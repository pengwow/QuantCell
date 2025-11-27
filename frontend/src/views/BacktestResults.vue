<template>
  <div class="backtest-results-container">
    <h1>回测结果</h1>
    
    <div class="backtest-layout">
      <!-- 左侧：回测任务列表 -->
      <div class="backtest-list">
        <div class="panel">
          <div class="panel-header">
            <h2>回测任务</h2>
            <button class="btn btn-primary btn-sm">新建回测</button>
          </div>
          <div class="panel-body">
            <div 
              v-for="task in backtestTasks" 
              :key="task.id"
              :class="['backtest-task-item', { active: selectedTaskId === task.id }]"
              @click="selectTask(task.id)"
            >
              <div class="task-header">
                <div class="task-name">{{ task.name }}</div>
                <div :class="['task-status', task.status]">{{ task.status }}</div>
              </div>
              <div class="task-meta">
                <div class="task-date">{{ task.date }}</div>
                <div class="task-return">{{ task.return }}%</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 右侧：回测结果详情 -->
      <div class="backtest-detail">
        <!-- 回测概览 -->
        <div class="panel">
          <div class="panel-header">
            <h2>回测概览</h2>
          </div>
          <div class="panel-body">
            <div class="overview-grid">
              <div class="metric-card">
                <div class="metric-label">总收益率</div>
                <div class="metric-value positive">12.56%</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">年化收益率</div>
                <div class="metric-value positive">8.32%</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">最大回撤</div>
                <div class="metric-value negative">-4.21%</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">夏普比率</div>
                <div class="metric-value">1.85</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">胜率</div>
                <div class="metric-value">62.3%</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">交易次数</div>
                <div class="metric-value">156</div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 绩效分析 -->
        <div class="panel">
          <div class="panel-header">
            <h2>绩效分析</h2>
          </div>
          <div class="panel-body">
            <div class="chart-container">
              <div ref="returnChartRef" class="chart"></div>
            </div>
          </div>
        </div>
        
        <!-- 交易详情和风险分析 -->
        <div class="grid-layout">
          <!-- 交易详情 -->
          <div class="panel">
            <div class="panel-header">
              <h2>交易详情</h2>
            </div>
            <div class="panel-body">
              <div class="table-container">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>标的</th>
                      <th>类型</th>
                      <th>价格</th>
                      <th>数量</th>
                      <th>收益</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="trade in trades" :key="trade.id">
                      <td>{{ trade.date }}</td>
                      <td>{{ trade.symbol }}</td>
                      <td>{{ trade.type }}</td>
                      <td>{{ trade.price }}</td>
                      <td>{{ trade.quantity }}</td>
                      <td :class="trade.profit >= 0 ? 'positive' : 'negative'">
                        {{ trade.profit >= 0 ? '+' : '' }}{{ trade.profit }}%
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          
          <!-- 风险分析 -->
          <div class="panel">
            <div class="panel-header">
              <h2>风险分析</h2>
            </div>
            <div class="panel-body">
              <div class="risk-metrics">
                <div class="risk-item">
                  <div class="risk-label">波动率</div>
                  <div class="risk-value">6.8%</div>
                </div>
                <div class="risk-item">
                  <div class="risk-label">索提诺比率</div>
                  <div class="risk-value">2.1</div>
                </div>
                <div class="risk-item">
                  <div class="risk-label">卡尔马比率</div>
                  <div class="risk-value">1.97</div>
                </div>
                <div class="risk-item">
                  <div class="risk-label">信息比率</div>
                  <div class="risk-value">0.75</div>
                </div>
              </div>
              <div class="chart-container small">
                <div ref="riskChartRef" class="chart"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'

// 回测任务数据
const backtestTasks = ref([
  { id: 1, name: '策略A回测', status: 'completed', date: '2024-01-15', return: 12.56 },
  { id: 2, name: '策略B回测', status: 'completed', date: '2024-01-14', return: -3.21 },
  { id: 3, name: '策略C回测', status: 'running', date: '2024-01-15', return: 0 },
  { id: 4, name: '策略A回测', status: 'completed', date: '2024-01-13', return: 5.67 },
  { id: 5, name: '策略B回测', status: 'completed', date: '2024-01-12', return: 8.92 },
])

// 选中的回测任务ID
const selectedTaskId = ref(1)

// 交易数据
const trades = ref([
  { id: 1, date: '2024-01-15', symbol: 'BTCUSDT', type: '买入', price: 42000, quantity: 0.01, profit: 2.5 },
  { id: 2, date: '2024-01-14', symbol: 'ETHUSDT', type: '卖出', price: 2300, quantity: 0.1, profit: -1.2 },
  { id: 3, date: '2024-01-13', symbol: 'BTCUSDT', type: '买入', price: 41500, quantity: 0.01, profit: 3.8 },
  { id: 4, date: '2024-01-12', symbol: 'ETHUSDT', type: '卖出', price: 2350, quantity: 0.1, profit: 2.1 },
  { id: 5, date: '2024-01-11', symbol: 'BTCUSDT', type: '买入', price: 41000, quantity: 0.01, profit: 1.5 },
])

// 图表引用
const returnChartRef = ref<HTMLElement | null>(null)
const riskChartRef = ref<HTMLElement | null>(null)
let returnChart: echarts.ECharts | null = null
let riskChart: echarts.ECharts | null = null

// 选择回测任务
const selectTask = (taskId: number) => {
  selectedTaskId.value = taskId
  // 这里可以添加加载回测结果的逻辑
}

// 初始化收益率曲线图表
const initReturnChart = () => {
  if (!returnChartRef.value) return
  
  returnChart = echarts.init(returnChartRef.value)
  
  const option = {
    title: {
      text: '收益率曲线',
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 'normal'
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: '{b}: {c}%'
    },
    xAxis: {
      type: 'category',
      data: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-06', '2024-01-07', '2024-01-08', '2024-01-09', '2024-01-10', '2024-01-11', '2024-01-12', '2024-01-13', '2024-01-14', '2024-01-15']
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: '{value}%'
      }
    },
    series: [{
      data: [0, 1.2, 2.5, 1.8, 3.2, 4.5, 3.8, 5.2, 6.5, 5.8, 7.2, 8.5, 10.2, 9.8, 12.56],
      type: 'line',
      smooth: true,
      lineStyle: {
        color: '#4a6cf7'
      },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(74, 108, 247, 0.3)' },
          { offset: 1, color: 'rgba(74, 108, 247, 0.05)' }
        ])
      }
    }]
  }
  
  returnChart.setOption(option)
}

// 初始化风险分析图表
const initRiskChart = () => {
  if (!riskChartRef.value) return
  
  riskChart = echarts.init(riskChartRef.value)
  
  const option = {
    title: {
      text: '最大回撤',
      left: 'center',
      textStyle: {
        fontSize: 14,
        fontWeight: 'normal'
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: '{b}: {c}%'
    },
    xAxis: {
      type: 'category',
      data: ['2024-01-01', '2024-01-05', '2024-01-10', '2024-01-15']
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: '{value}%'
      }
    },
    series: [{
      data: [0, -2.1, -3.5, -4.21],
      type: 'bar',
      itemStyle: {
        color: '#f87272'
      }
    }]
  }
  
  riskChart.setOption(option)
}

// 监听窗口大小变化，调整图表大小
const handleResize = () => {
  returnChart?.resize()
  riskChart?.resize()
}

// 组件挂载时初始化图表
onMounted(() => {
  initReturnChart()
  initRiskChart()
  window.addEventListener('resize', handleResize)
})

// 组件卸载时销毁图表
onMounted(() => {
  return () => {
    window.removeEventListener('resize', handleResize)
    returnChart?.dispose()
    riskChart?.dispose()
  }
})
</script>

<style scoped>
.backtest-results-container {
  padding: 20px;
}

.backtest-layout {
  display: flex;
  gap: 20px;
  margin-top: 20px;
}

.backtest-list {
  width: 300px;
  flex-shrink: 0;
}

.backtest-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.panel {
  background-color: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  background-color: #f9fafb;
}

.panel-header h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #1f2937;
}

.panel-body {
  padding: 20px;
}

/* 回测任务列表 */
.backtest-task-item {
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.backtest-task-item:hover {
  border-color: #4a6cf7;
  box-shadow: 0 2px 8px rgba(74, 108, 247, 0.1);
}

.backtest-task-item.active {
  border-color: #4a6cf7;
  background-color: #f0f4ff;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.task-name {
  font-weight: 500;
  color: #1f2937;
}

.task-status {
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.task-status.completed {
  background-color: #d1fae5;
  color: #065f46;
}

.task-status.running {
  background-color: #dbeafe;
  color: #1e40af;
}

.task-status.failed {
  background-color: #fee2e2;
  color: #991b1b;
}

.task-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #6b7280;
}

.task-return {
  font-weight: 500;
  color: #10b981;
}

/* 概览网格 */
.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.metric-card {
  background-color: #f9fafb;
  padding: 16px;
  border-radius: 6px;
  text-align: center;
}

.metric-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
}

.metric-value.positive {
  color: #10b981;
}

.metric-value.negative {
  color: #ef4444;
}

/* 图表容器 */
.chart-container {
  height: 300px;
  margin-top: 20px;
}

.chart-container.small {
  height: 200px;
}

.chart {
  width: 100%;
  height: 100%;
}

/* 网格布局 */
.grid-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

/* 表格容器 */
.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th,
.data-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.data-table th {
  background-color: #f9fafb;
  font-weight: 600;
  color: #1f2937;
}

.data-table td {
  color: #6b7280;
}

.data-table tr:hover {
  background-color: #f9fafb;
}

.positive {
  color: #10b981;
}

.negative {
  color: #ef4444;
}

/* 风险指标 */
.risk-metrics {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.risk-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background-color: #f9fafb;
  border-radius: 6px;
}

.risk-label {
  font-size: 14px;
  color: #6b7280;
}

.risk-value {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

/* 按钮样式 */
.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-primary {
  background-color: #4a6cf7;
  color: white;
}

.btn-primary:hover {
  background-color: #3b5bdb;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .backtest-layout {
    flex-direction: column;
  }
  
  .backtest-list {
    width: 100%;
  }
  
  .grid-layout {
    grid-template-columns: 1fr;
  }
}
</style>