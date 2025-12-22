<template>
  <div class="chart-page-container">
    <h1>{{ $route.meta.title }}</h1>
    
    <!-- 筛选条件区域 -->
    <div class="filter-section">
      <div class="filter-row">
        <div class="filter-item">
          <label>货币模式</label>
          <select v-model="filterParams.symbol">
            <option value="BTCUSDT">BTCUSDT</option>
            <option value="ETHUSDT">ETHUSDT</option>
            <option value="BNBUSDT">BNBUSDT</option>
            <option value="SOLUSDT">SOLUSDT</option>
          </select>
        </div>
        
        <div class="filter-item">
          <label>开始时间</label>
          <input v-model="filterParams.startTime" type="date" />
        </div>
        
        <div class="filter-item">
          <label>结束时间</label>
          <input v-model="filterParams.endTime" type="date" />
        </div>
        
        <div class="filter-item">
          <label>时间周期</label>
          <select v-model="filterParams.period">
            <option value="1min">1分钟</option>
            <option value="5min">5分钟</option>
            <option value="15min">15分钟</option>
            <option value="30min">30分钟</option>
            <option value="1h">1小时</option>
            <option value="4h">4小时</option>
            <option value="1d">日线</option>
            <option value="1w">周线</option>
          </select>
        </div>
        
        <div class="filter-item">
          <label>数据周期数</label>
          <input v-model.number="filterParams.limit" type="number" min="100" max="2000" step="100" />
        </div>
        
        <div class="filter-actions">
          <button @click="fetchChartData" class="btn btn-primary">获取数据</button>
          <button @click="resetFilters" class="btn btn-secondary">重置</button>
        </div>
      </div>
      
      <!-- 指标选择区域 -->
      <div class="indicator-section">
        <div class="indicator-header">
          <h3>指标选择</h3>
          <div class="indicator-info">
            <span>已选指标: {{ selectedIndicators.length }}</span>
          </div>
        </div>
        
        <div class="indicator-list">
          <div 
            v-for="indicator in indicators" 
            :key="indicator.id"
            class="indicator-item"
            :class="{ active: selectedIndicators.includes(indicator.id) }"
            @click="toggleIndicator(indicator.id)"
          >
            <div class="indicator-name">{{ indicator.name }}</div>
            <div class="indicator-desc">{{ indicator.description }}</div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 图表区域 -->
    <div class="chart-section">
      <div class="chart-header">
        <div class="chart-title">{{ filterParams.symbol }} K线图</div>
        <div class="chart-stats">
          <span v-if="chartData.length > 0">
            最新价格: {{ chartData[chartData.length - 1].close.toFixed(2) }} 
            ({{ chartData[chartData.length - 1].changePercent.toFixed(2) }}%)
          </span>
        </div>
      </div>
      
      <div class="chart-container">
        <div id="kline-chart" ref="chartRef"></div>
      </div>
    </div>
    
    <!-- 指标配置区域 -->
    <div v-if="selectedIndicators.length > 0" class="indicator-config-section">
      <h3>指标配置</h3>
      <div class="indicator-config-list">
        <div 
          v-for="indicatorId in selectedIndicators" 
          :key="indicatorId"
          class="indicator-config-item"
        >
          <div class="config-header">
            <span>{{ indicators.find(ind => ind.id === indicatorId)?.name }}</span>
            <button @click="toggleIndicator(indicatorId)" class="btn-remove">×</button>
          </div>
          <div class="config-content">
            <!-- 这里可以根据指标类型动态生成配置项 -->
            <div class="config-row">
              <label>周期</label>
              <input 
                type="number" 
                :value="indicatorConfigs[indicatorId]?.period || 14" 
                min="1" 
                @input="updateIndicatorConfig(indicatorId, 'period', parseInt(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="config-row">
              <label>颜色</label>
              <input 
                type="color" 
                :value="indicatorConfigs[indicatorId]?.color || '#1890ff'" 
                @input="updateIndicatorConfig(indicatorId, 'color', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { init, dispose } from 'klinecharts';

// 图表容器引用
const chartRef = ref<HTMLElement | null>(null);
// 图表实例
let chart: any = null;

// 筛选参数
const filterParams = ref({
  symbol: 'BTCUSDT',
  startTime: '2024-01-01',
  endTime: new Date().toISOString().split('T')[0],
  period: '1d',
  limit: 500
});

// 图表数据
const chartData = ref<any[]>([]);

// 指标列表
const indicators = ref([
  { id: 'ma', name: 'MA', description: '移动平均线' },
  { id: 'ema', name: 'EMA', description: '指数移动平均线' },
  { id: 'macd', name: 'MACD', description: '平滑异同移动平均线' },
  { id: 'rsi', name: 'RSI', description: '相对强弱指标' },
  { id: 'kdj', name: 'KDJ', description: '随机指标' },
  { id: 'boll', name: 'BOLL', description: '布林带' }
]);

// 已选指标
const selectedIndicators = ref<string[]>(['ma', 'macd']);

// 指标配置
const indicatorConfigs = ref<any>({
  ma: { period: 14, color: '#1890ff' },
  ema: { period: 20, color: '#52c41a' },
  macd: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
  rsi: { period: 14, color: '#faad14' },
  kdj: { kPeriod: 9, dPeriod: 3, jPeriod: 3 },
  boll: { period: 20, stdDev: 2 }
});

// 初始化图表
const initChart = () => {
  if (chartRef.value) {
    // 销毁现有图表
    if (chart) {
      dispose('kline-chart');
    }
    
    // 创建新图表
    chart = init('kline-chart');
    chart.setSymbol({ ticker: filterParams.value.symbol });
    chart.setPeriod({ span: 1, type: 'day' });
    
    // 设置数据加载器
    chart.setDataLoader({
      getBars: ({ callback }: { callback: (data: any[]) => void }) => {
        callback(chartData.value);
      }
    });
    
    // 应用初始指标
    applyIndicators();
  }
};

// 应用指标
const applyIndicators = () => {
  if (!chart) return;
  
  // 清除所有指标
  if (typeof chart.removeAllIndicators === 'function') {
    chart.removeAllIndicators();
  } else {
    console.warn('removeAllIndicators method not found, trying alternative...');
  }
  
  // 应用选中的指标
  selectedIndicators.value.forEach(indicatorId => {
    const config = indicatorConfigs.value[indicatorId] || {};
    
    try {
      switch (indicatorId) {
        case 'ma':
          chart.addIndicator({
            name: 'ma',
            calcParams: [config.period || 14],
            styles: {
              color: config.color || '#1890ff'
            }
          });
          break;
        case 'ema':
          chart.addIndicator({
            name: 'ema',
            calcParams: [config.period || 20],
            styles: {
              color: config.color || '#52c41a'
            }
          });
          break;
        case 'macd':
          chart.addIndicator({
            name: 'macd',
            calcParams: [config.fastPeriod || 12, config.slowPeriod || 26, config.signalPeriod || 9]
          });
          break;
        case 'rsi':
          chart.addIndicator({
            name: 'rsi',
            calcParams: [config.period || 14],
            styles: {
              color: config.color || '#faad14'
            }
          });
          break;
        case 'kdj':
          chart.addIndicator({
            name: 'kdj',
            calcParams: [config.kPeriod || 9, config.dPeriod || 3, config.jPeriod || 3]
          });
          break;
        case 'boll':
          chart.addIndicator({
            name: 'boll',
            calcParams: [config.period || 20, config.stdDev || 2]
          });
          break;
      }
    } catch (error) {
      console.error(`Failed to add indicator ${indicatorId}:`, error);
    }
  });
};

// 获取图表数据
const fetchChartData = async () => {
  try {
    // 这里使用模拟数据，实际应该调用后端接口
    // const response = await axios.post('http://localhost:8000/api/chart/data', {
    //   symbol: filterParams.value.symbol,
    //   startTime: filterParams.value.startTime,
    //   endTime: filterParams.value.endTime,
    //   period: filterParams.value.period,
    //   limit: filterParams.value.limit
    // });
    
    // 模拟后端API返回格式
    const mockResponse = {
      code: 0,
      message: 'success',
      data: generateDemoData(filterParams.value.symbol, filterParams.value.limit)
    };
    
    if (mockResponse.code === 0) {
      chartData.value = mockResponse.data;
    } else {
      alert('获取数据失败: ' + mockResponse.message);
      return;
    }
    
    // 更新图表
    if (chart) {
      chart.resetData();
      applyIndicators();
    }
  } catch (error) {
    console.error('获取图表数据失败:', error);
    alert('获取数据失败');
  }
};

// 生成模拟K线数据 - 模拟真实市场数据
const generateDemoData = (symbol: string, count: number) => {
  // 不同货币对的基础价格
  const basePrices: Record<string, number> = {
    BTCUSDT: 50000,
    ETHUSDT: 3000,
    BNBUSDT: 300,
    SOLUSDT: 100
  };
  
  // 不同时间周期的毫秒数
  const intervals: Record<string, number> = {
    '1min': 60000,
    '5min': 300000,
    '15min': 900000,
    '30min': 1800000,
    '1h': 3600000,
    '4h': 14400000,
    '1d': 86400000,
    '1w': 604800000
  };
  
  const basePrice = basePrices[symbol] || 50000;
  const interval = intervals[filterParams.value.period] || 86400000;
  
  const data: any[] = [];
  let currentPrice = basePrice;
  const now = Date.now();
  
  // 生成更真实的价格走势
  for (let i = count - 1; i >= 0; i--) {
    const timestamp = now - i * interval;
    
    // 添加一些趋势性
    const trendFactor = Math.sin(i / 20) * 0.1; // 周期性趋势
    const randomFactor = (Math.random() - 0.5) * 0.05; // 随机波动
    const volatility = Math.random() * 0.02; // 波动率
    
    const open = currentPrice;
    const close = open * (1 + trendFactor + randomFactor);
    const high = Math.max(open, close) * (1 + volatility);
    const low = Math.min(open, close) * (1 - volatility);
    const volume = Math.abs((close - open) / open) * 100000 * (0.5 + Math.random());
    
    const prevClose = data.length > 0 ? data[data.length - 1].close : open;
    const change = close - prevClose;
    const changePercent = (change / prevClose) * 100;
    
    data.push({
      timestamp,
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      volume: parseFloat(volume.toFixed(2)),
      change: parseFloat(change.toFixed(2)),
      changePercent: parseFloat(changePercent.toFixed(2))
    });
    
    currentPrice = close;
  }
  
  return data;
};

// 重置筛选条件
const resetFilters = () => {
  filterParams.value = {
    symbol: 'BTCUSDT',
    startTime: '2024-01-01',
    endTime: new Date().toISOString().split('T')[0],
    period: '1d',
    limit: 500
  };
};

// 切换指标选择
const toggleIndicator = (indicatorId: string) => {
  const index = selectedIndicators.value.indexOf(indicatorId);
  if (index > -1) {
    selectedIndicators.value.splice(index, 1);
  } else {
    selectedIndicators.value.push(indicatorId);
  }
  
  // 应用指标变化
  applyIndicators();
};

// 更新指标配置
const updateIndicatorConfig = (indicatorId: string, key: string, value: any) => {
  if (!indicatorConfigs.value[indicatorId]) {
    indicatorConfigs.value[indicatorId] = {};
  }
  
  indicatorConfigs.value[indicatorId][key] = value;
  
  // 应用指标配置变化
  applyIndicators();
};

// 监听筛选参数变化
watch(filterParams, (newParams, oldParams) => {
  // 如果symbol或period变化，重新获取数据
  if (newParams.symbol !== oldParams.symbol || newParams.period !== oldParams.period) {
    fetchChartData();
  }
}, { deep: true });

// 初始化
onMounted(() => {
  initChart();
  fetchChartData();
});

// 销毁
onUnmounted(() => {
  if (chart) {
    dispose('kline-chart');
    chart = null;
  }
});
</script>

<style scoped>
.chart-page-container {
  padding: 20px;
  background-color: #f9fafb;
  min-height: 100vh;
}

h1 {
  font-size: 24px;
  margin-bottom: 20px;
  color: #333;
}

/* 筛选区域样式 */
.filter-section {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
}

.filter-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: flex-end;
  margin-bottom: 20px;
}

.filter-item {
  flex: 1;
  min-width: 150px;
}

.filter-item label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
  color: #333;
  font-size: 14px;
}

.filter-item input,
.filter-item select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
}

.filter-actions {
  display: flex;
  gap: 10px;
}

/* 按钮样式 */
.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.btn-primary {
  background-color: #1890ff;
  color: white;
}

.btn-primary:hover {
  background-color: #40a9ff;
}

.btn-secondary {
  background-color: #f0f0f0;
  color: #333;
}

.btn-secondary:hover {
  background-color: #e0e0e0;
}

/* 指标选择区域 */
.indicator-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.indicator-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.indicator-header h3 {
  font-size: 16px;
  color: #333;
  margin: 0;
}

.indicator-info {
  font-size: 14px;
  color: #666;
}

.indicator-list {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.indicator-item {
  padding: 10px 15px;
  background-color: #f0f0f0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
  min-width: 150px;
  border: 1px solid transparent;
}

.indicator-item:hover {
  background-color: #e0e0e0;
}

.indicator-item.active {
  background-color: #e6f7ff;
  border-color: #1890ff;
  color: #1890ff;
}

.indicator-name {
  font-weight: 500;
  margin-bottom: 3px;
}

.indicator-desc {
  font-size: 12px;
  opacity: 0.8;
}

/* 图表区域 */
.chart-section {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.chart-title {
  font-size: 18px;
  font-weight: 500;
  color: #333;
}

.chart-stats {
  font-size: 14px;
  color: #666;
}

.chart-container {
  width: 100%;
  height: 600px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}

/* 指标配置区域 */
.indicator-config-section {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.indicator-config-section h3 {
  font-size: 16px;
  color: #333;
  margin-bottom: 15px;
}

.indicator-config-list {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.indicator-config-item {
  flex: 1;
  min-width: 250px;
  padding: 15px;
  background-color: #f9fafb;
  border-radius: 4px;
  border: 1px solid #f0f0f0;
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.config-header span {
  font-weight: 500;
  color: #333;
}

.btn-remove {
  background: none;
  border: none;
  font-size: 18px;
  color: #ff4d4f;
  cursor: pointer;
  padding: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-remove:hover {
  background-color: #fff1f0;
  border-radius: 50%;
}

.config-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.config-row label {
  font-size: 14px;
  color: #666;
}

.config-row input {
  width: 100px;
  padding: 5px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
}

.config-row input[type="color"] {
  width: 40px;
  height: 30px;
  padding: 0;
  border: none;
  cursor: pointer;
}
</style>