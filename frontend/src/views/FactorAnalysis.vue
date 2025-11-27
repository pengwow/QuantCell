<template>
  <div class="factor-analysis-container">
    <h1>因子分析</h1>
    
    <!-- 标签页 -->
    <div class="tabs">
      <div 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="['tab-item', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
      >
        {{ tab.name }}
      </div>
    </div>
    
    <!-- 因子列表 -->
    <div v-if="activeTab === 'list'" class="tab-content">
      <div class="section">
        <h2>因子列表</h2>
        <div class="factor-list">
          <div 
            v-for="factor in factors" 
            :key="factor"
            class="factor-item"
            @click="selectFactor(factor)"
          >
            {{ factor }}
          </div>
        </div>
      </div>
      
      <div class="section">
        <h2>自定义因子</h2>
        <div class="custom-factor-form">
          <div class="form-item">
            <label>因子名称</label>
            <input v-model="newFactor.name" type="text" placeholder="输入因子名称" />
          </div>
          <div class="form-item">
            <label>因子表达式</label>
            <input v-model="newFactor.expression" type="text" placeholder="输入因子表达式，如 $close / $Ref($close, 5) - 1" />
          </div>
          <div class="form-actions">
            <button @click="addFactor" class="btn btn-primary">添加因子</button>
            <button @click="validateFactor" class="btn btn-secondary">验证表达式</button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 因子计算 -->
    <div v-else-if="activeTab === 'calculate'" class="tab-content">
      <div class="section">
        <h2>因子计算</h2>
        <div class="calculate-form">
          <div class="form-item">
            <label>选择因子</label>
            <select v-model="calculateParams.factorName" multiple>
              <option v-for="factor in factors" :key="factor" :value="factor">{{ factor }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>标的列表</label>
            <textarea v-model="calculateParams.instruments" placeholder="输入标的列表，用逗号分隔" rows="3"></textarea>
          </div>
          <div class="form-row">
            <div class="form-item">
              <label>开始时间</label>
              <input v-model="calculateParams.startTime" type="date" />
            </div>
            <div class="form-item">
              <label>结束时间</label>
              <input v-model="calculateParams.endTime" type="date" />
            </div>
            <div class="form-item">
              <label>频率</label>
              <select v-model="calculateParams.freq">
                <option value="day">日线</option>
                <option value="1min">1分钟</option>
                <option value="5min">5分钟</option>
                <option value="15min">15分钟</option>
                <option value="30min">30分钟</option>
                <option value="60min">60分钟</option>
              </select>
            </div>
          </div>
          <div class="form-actions">
            <button @click="calculateFactor" class="btn btn-primary">计算因子</button>
          </div>
        </div>
      </div>
      
      <!-- 计算结果 -->
      <div v-if="factorResult" class="section">
        <h2>计算结果</h2>
        <div class="result-info">
          <p>因子名称: {{ factorResult.factor_name }}</p>
          <p>数据形状: {{ factorResult.shape[0] }} 行, {{ factorResult.shape[1] }} 列</p>
        </div>
        <div class="result-table">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>标的</th>
                <th>因子值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in factorResult.data.slice(0, 10)" :key="`${item.date}-${item.instrument}`">
                <td>{{ item.date }}</td>
                <td>{{ item.instrument }}</td>
                <td>{{ item.value.toFixed(4) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="factorResult.data.length > 10" class="more-data">
            显示前10条数据，共 {{ factorResult.data.length }} 条
          </div>
        </div>
      </div>
    </div>
    
    <!-- 因子有效性检验 -->
    <div v-else-if="activeTab === 'validation'" class="tab-content">
      <div class="section">
        <h2>因子有效性检验</h2>
        <div class="validation-form">
          <div class="form-item">
            <label>选择因子</label>
            <select v-model="validationParams.factorName">
              <option v-for="factor in factors" :key="factor" :value="factor">{{ factor }}</option>
            </select>
          </div>
          <div class="form-row">
            <div class="form-item">
              <label>开始时间</label>
              <input v-model="validationParams.startTime" type="date" />
            </div>
            <div class="form-item">
              <label>结束时间</label>
              <input v-model="validationParams.endTime" type="date" />
            </div>
          </div>
          <div class="form-actions">
            <button @click="calculateIC" class="btn btn-primary">计算IC</button>
            <button @click="calculateIR" class="btn btn-primary">计算IR</button>
            <button @click="groupAnalysis" class="btn btn-primary">分组分析</button>
            <button @click="monotonicityTest" class="btn btn-primary">单调性检验</button>
            <button @click="stabilityTest" class="btn btn-primary">稳定性检验</button>
          </div>
        </div>
      </div>
      
      <!-- 检验结果 -->
      <div v-if="validationResult" class="section">
        <h2>检验结果</h2>
        <div class="validation-result">
          <div v-if="validationResult.ic" class="result-item">
            <h3>信息系数(IC)</h3>
            <div class="chart-container">
              <div ref="icChartRef" class="chart"></div>
            </div>
          </div>
          
          <div v-if="validationResult.ir" class="result-item">
            <h3>信息比率(IR)</h3>
            <div class="ir-value">{{ validationResult.ir.toFixed(4) }}</div>
          </div>
          
          <div v-if="validationResult.groupAnalysis" class="result-item">
            <h3>分组分析</h3>
            <div class="chart-container">
              <div ref="groupChartRef" class="chart"></div>
            </div>
          </div>
          
          <div v-if="validationResult.monotonicity" class="result-item">
            <h3>单调性检验</h3>
            <div class="monotonicity-info">
              <p>单调性得分: {{ validationResult.monotonicity.monotonicity_score.toFixed(4) }}</p>
              <p>相关性: {{ validationResult.monotonicity.monotonicity_corr.toFixed(4) }}</p>
            </div>
          </div>
          
          <div v-if="validationResult.stability" class="result-item">
            <h3>稳定性检验</h3>
            <div class="chart-container">
              <div ref="stabilityChartRef" class="chart"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 因子可视化 -->
    <div v-else-if="activeTab === 'visualization'" class="tab-content">
      <div class="section">
        <h2>因子可视化</h2>
        <div class="visualization-form">
          <div class="form-item">
            <label>选择因子</label>
            <select v-model="visualizationParams.factorName">
              <option v-for="factor in factors" :key="factor" :value="factor">{{ factor }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>选择标的</label>
            <input v-model="visualizationParams.instrument" type="text" placeholder="输入标的代码" />
          </div>
          <div class="form-row">
            <div class="form-item">
              <label>开始时间</label>
              <input v-model="visualizationParams.startTime" type="date" />
            </div>
            <div class="form-item">
              <label>结束时间</label>
              <input v-model="visualizationParams.endTime" type="date" />
            </div>
          </div>
          <div class="form-actions">
            <button @click="visualizeFactor" class="btn btn-primary">可视化</button>
          </div>
        </div>
      </div>
      
      <!-- 可视化结果 -->
      <div v-if="visualizationResult" class="section">
        <h2>因子趋势图</h2>
        <div class="chart-container">
          <div ref="factorChart" class="chart"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import axios from 'axios';
import * as echarts from 'echarts';

// 标签页
const tabs = [
  { id: 'list', name: '因子列表' },
  { id: 'calculate', name: '因子计算' },
  { id: 'validation', name: '有效性检验' },
  { id: 'visualization', name: '因子可视化' }
];
const activeTab = ref('list');

// 因子列表
const factors = ref<string[]>([]);
const selectedFactor = ref<string>('');

// 自定义因子
const newFactor = ref({
  name: '',
  expression: ''
});

// 计算参数
const calculateParams = ref({
  factorName: [] as string[],
  instruments: 'BTC,ETH,BNB',
  startTime: '2024-01-01',
  endTime: '2024-12-31',
  freq: 'day'
});

// 因子计算结果
const factorResult = ref<any>(null);

// 有效性检验参数
const validationParams = ref({
  factorName: '',
  startTime: '2024-01-01',
  endTime: '2024-12-31'
});

// 有效性检验结果
const validationResult = ref<any>({});

// 可视化参数
const visualizationParams = ref({
  factorName: '',
  instrument: 'BTC',
  startTime: '2024-01-01',
  endTime: '2024-12-31'
});

// 可视化结果
const visualizationResult = ref<any>(null);

// 图表实例
let icChart: echarts.ECharts | null = null;
let groupChart: echarts.ECharts | null = null;
let stabilityChart: echarts.ECharts | null = null;
let factorChart: echarts.ECharts | null = null;

// 图表容器ref
const icChartRef = ref<HTMLElement | null>(null);
const groupChartRef = ref<HTMLElement | null>(null);
const stabilityChartRef = ref<HTMLElement | null>(null);
const factorChartRef = ref<HTMLElement | null>(null);

// 获取因子列表
const fetchFactors = async () => {
  try {
    const response = await axios.get('http://localhost:8000/api/factor/list');
    if (response.data.code === 0) {
      factors.value = response.data.data.factors;
    }
  } catch (error) {
    console.error('获取因子列表失败:', error);
  }
};

// 选择因子
const selectFactor = (factor: string) => {
  selectedFactor.value = factor;
};

// 添加因子
const addFactor = async () => {
  try {
    if (!newFactor.value.name || !newFactor.value.expression) {
      alert('请输入因子名称和表达式');
      return;
    }
    
    const response = await axios.post('http://localhost:8000/api/factor/add', {
      factor_name: newFactor.value.name,
      expression: newFactor.value.expression
    });
    
    if (response.data.code === 0) {
      alert('因子添加成功');
      fetchFactors();
      newFactor.value = { name: '', expression: '' };
    } else {
      alert('因子添加失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('添加因子失败:', error);
    alert('添加因子失败');
  }
};

// 验证因子表达式
const validateFactor = async () => {
  try {
    if (!newFactor.value.expression) {
      alert('请输入因子表达式');
      return;
    }
    
    const response = await axios.post('http://localhost:8000/api/factor/validate', {
      expression: newFactor.value.expression
    });
    
    if (response.data.code === 0) {
      alert('因子表达式验证通过');
    } else {
      alert('因子表达式验证失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('验证因子表达式失败:', error);
    alert('验证因子表达式失败');
  }
};

// 计算因子
const calculateFactor = async () => {
  try {
    if (calculateParams.value.factorName.length === 0) {
      alert('请选择至少一个因子');
      return;
    }
    
    const instruments = calculateParams.value.instruments.split(',').map(item => item.trim());
    
    const response = await axios.post('http://localhost:8000/api/factor/calculate', {
      factor_name: calculateParams.value.factorName[0],
      instruments: instruments,
      start_time: calculateParams.value.startTime,
      end_time: calculateParams.value.endTime,
      freq: calculateParams.value.freq
    });
    
    if (response.data.code === 0) {
      factorResult.value = response.data.data;
    } else {
      alert('因子计算失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('计算因子失败:', error);
    alert('计算因子失败');
  }
};

// 计算IC
const calculateIC = async () => {
  try {
    const response = await axios.post('http://localhost:8000/api/factor/ic', {
      factor_data: {}, // 这里需要传入实际的因子数据
      return_data: {}, // 这里需要传入实际的收益率数据
      method: 'spearman'
    });
    
    if (response.data.code === 0) {
      validationResult.value.ic = response.data.data.ic;
      renderICChart();
    } else {
      alert('计算IC失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('计算IC失败:', error);
    alert('计算IC失败');
  }
};

// 计算IR
const calculateIR = async () => {
  try {
    const response = await axios.post('http://localhost:8000/api/factor/ir', {
      factor_data: {}, // 这里需要传入实际的因子数据
      return_data: {}, // 这里需要传入实际的收益率数据
      method: 'spearman'
    });
    
    if (response.data.code === 0) {
      validationResult.value.ir = response.data.data.ir;
    } else {
      alert('计算IR失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('计算IR失败:', error);
    alert('计算IR失败');
  }
};

// 分组分析
const groupAnalysis = async () => {
  try {
    const response = await axios.post('http://localhost:8000/api/factor/group-analysis', {
      factor_data: {}, // 这里需要传入实际的因子数据
      return_data: {}, // 这里需要传入实际的收益率数据
      n_groups: 5
    });
    
    if (response.data.code === 0) {
      validationResult.value.groupAnalysis = response.data.data.group_analysis;
      renderGroupChart();
    } else {
      alert('分组分析失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('分组分析失败:', error);
    alert('分组分析失败');
  }
};

// 单调性检验
const monotonicityTest = async () => {
  try {
    const response = await axios.post('http://localhost:8000/api/factor/monotonicity', {
      factor_data: {}, // 这里需要传入实际的因子数据
      return_data: {}, // 这里需要传入实际的收益率数据
      n_groups: 5
    });
    
    if (response.data.code === 0) {
      validationResult.value.monotonicity = response.data.data.monotonicity;
    } else {
      alert('单调性检验失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('单调性检验失败:', error);
    alert('单调性检验失败');
  }
};

// 稳定性检验
const stabilityTest = async () => {
  try {
    const response = await axios.post('http://localhost:8000/api/factor/stability', {
      factor_data: {}, // 这里需要传入实际的因子数据
      window: 20
    });
    
    if (response.data.code === 0) {
      validationResult.value.stability = response.data.data.stability;
      renderStabilityChart();
    } else {
      alert('稳定性检验失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('稳定性检验失败:', error);
    alert('稳定性检验失败');
  }
};

// 因子可视化
const visualizeFactor = async () => {
  try {
    if (!visualizationParams.value.factorName || !visualizationParams.value.instrument) {
      alert('请选择因子和标的');
      return;
    }
    
    const response = await axios.post('http://localhost:8000/api/factor/calculate', {
      factor_name: visualizationParams.value.factorName,
      instruments: [visualizationParams.value.instrument],
      start_time: visualizationParams.value.startTime,
      end_time: visualizationParams.value.endTime,
      freq: 'day'
    });
    
    if (response.data.code === 0) {
      visualizationResult.value = response.data.data;
      renderFactorChart();
    } else {
      alert('因子可视化失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('因子可视化失败:', error);
    alert('因子可视化失败');
  }
};

// 渲染IC图表
const renderICChart = () => {
  if (!icChart && icChartRef.value) {
    icChart = echarts.init(icChartRef.value);
  }
  
  // 这里使用模拟数据，实际应该使用validationResult.value.ic
  const data = [0.1, 0.2, 0.15, -0.1, 0.05, 0.3, 0.25, -0.05, 0.1, 0.15];
  const dates = ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06', '2024-07', '2024-08', '2024-09', '2024-10'];
  
  const option = {
    title: {
      text: '因子IC值走势'
    },
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: {
      type: 'value'
    },
    series: [{
      data: data,
      type: 'line'
    }]
  };
  
  icChart?.setOption(option);
};

// 渲染分组图表
const renderGroupChart = () => {
  if (!groupChart && groupChartRef.value) {
    groupChart = echarts.init(groupChartRef.value);
  }
  
  // 这里使用模拟数据，实际应该使用validationResult.value.groupAnalysis
  const data = [0.01, 0.02, 0.03, 0.04, 0.05];
  const groups = ['Group 1', 'Group 2', 'Group 3', 'Group 4', 'Group 5'];
  
  const option = {
    title: {
      text: '因子分组收益率'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    xAxis: {
      type: 'category',
      data: groups
    },
    yAxis: {
      type: 'value'
    },
    series: [{
      data: data,
      type: 'bar'
    }]
  };
  
  groupChart?.setOption(option);
};

// 渲染稳定性图表
const renderStabilityChart = () => {
  if (!stabilityChart && stabilityChartRef.value) {
    stabilityChart = echarts.init(stabilityChartRef.value);
  }
  
  // 这里使用模拟数据，实际应该使用validationResult.value.stability
  const data = [0.8, 0.85, 0.75, 0.9, 0.88, 0.92, 0.85, 0.8, 0.78, 0.82];
  const dates = ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06', '2024-07', '2024-08', '2024-09', '2024-10'];
  
  const option = {
    title: {
      text: '因子稳定性（滚动自相关性）'
    },
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: {
      type: 'value'
    },
    series: [{
      data: data,
      type: 'line'
    }]
  };
  
  stabilityChart?.setOption(option);
};

// 渲染因子趋势图
const renderFactorChart = () => {
  if (!factorChart && factorChartRef.value) {
    factorChart = echarts.init(factorChartRef.value);
  }
  
  if (visualizationResult.value) {
    const data = visualizationResult.value.data.map((item: any) => item.value);
    const dates = visualizationResult.value.data.map((item: any) => item.date);
    
    const option = {
      title: {
        text: `${visualizationParams.value.factorName} - ${visualizationParams.value.instrument} 因子值走势`
      },
      tooltip: {
        trigger: 'axis'
      },
      xAxis: {
        type: 'category',
        data: dates
      },
      yAxis: {
        type: 'value'
      },
      series: [{
        data: data,
        type: 'line'
      }]
    };
    
    factorChart?.setOption(option);
  }
};

// 初始化
onMounted(() => {
  fetchFactors();
});
</script>

<style scoped>
.factor-analysis-container {
  padding: 20px;
}

h1 {
  font-size: 24px;
  margin-bottom: 20px;
  color: #333;
}

.tabs {
  display: flex;
  margin-bottom: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.tab-item {
  padding: 10px 20px;
  cursor: pointer;
  color: #666;
  font-size: 16px;
  border-bottom: 2px solid transparent;
  transition: all 0.3s;
}

.tab-item:hover {
  color: #1890ff;
}

.tab-item.active {
  color: #1890ff;
  border-bottom-color: #1890ff;
}

.tab-content {
  background-color: #fff;
  padding: 20px;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.section {
  margin-bottom: 30px;
}

h2 {
  font-size: 18px;
  margin-bottom: 15px;
  color: #333;
}

/* 因子列表 */
.factor-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.factor-item {
  padding: 8px 16px;
  background-color: #f0f0f0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
}

.factor-item:hover {
  background-color: #1890ff;
  color: #fff;
}

/* 表单样式 */
.custom-factor-form,
.calculate-form,
.validation-form,
.visualization-form {
  background-color: #fafafa;
  padding: 20px;
  border-radius: 4px;
}

.form-item {
  margin-bottom: 15px;
}

.form-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.form-row .form-item {
  flex: 1;
  margin-bottom: 0;
}

.form-item label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
  color: #333;
}

.form-item input,
.form-item select,
.form-item textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
}

.form-item textarea {
  resize: vertical;
}

.form-actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
}

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
  color: #fff;
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

/* 结果样式 */
.result-info {
  background-color: #f0f0f0;
  padding: 15px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.result-info p {
  margin: 5px 0;
}

.result-table {
  overflow-x: auto;
}

.result-table table {
  width: 100%;
  border-collapse: collapse;
}

.result-table th,
.result-table td {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  text-align: left;
}

.result-table th {
  background-color: #f0f0f0;
  font-weight: 500;
}

.more-data {
  margin-top: 10px;
  text-align: center;
  color: #666;
  font-size: 14px;
}

/* 验证结果样式 */
.validation-result {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.result-item {
  background-color: #fafafa;
  padding: 20px;
  border-radius: 4px;
}

.result-item h3 {
  font-size: 16px;
  margin-bottom: 15px;
  color: #333;
}

.ir-value {
  font-size: 24px;
  font-weight: bold;
  color: #1890ff;
  text-align: center;
}

.monotonicity-info {
  background-color: #f0f0f0;
  padding: 15px;
  border-radius: 4px;
}

.monotonicity-info p {
  margin: 5px 0;
}

/* 图表样式 */
.chart-container {
  width: 100%;
  height: 400px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
