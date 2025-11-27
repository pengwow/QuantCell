<template>
  <div class="model-management-container">
    <h1>模型管理</h1>
    
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
    
    <!-- 模型列表 -->
    <div v-if="activeTab === 'list'" class="tab-content">
      <div class="section">
        <h2>模型列表</h2>
        <div class="model-list">
          <div 
            v-for="model in savedModels" 
            :key="model"
            class="model-item"
            @click="selectModel(model)"
          >
            {{ model }}
            <div class="model-actions">
              <button @click.stop="evaluateModel(model)" class="btn btn-sm btn-primary">评估</button>
              <button @click.stop="deleteModel(model)" class="btn btn-sm btn-danger">删除</button>
            </div>
          </div>
        </div>
        <div v-if="savedModels.length === 0" class="empty-state">
          暂无保存的模型
        </div>
      </div>
    </div>
    
    <!-- 模型训练 -->
    <div v-else-if="activeTab === 'train'" class="tab-content">
      <div class="section">
        <h2>模型训练</h2>
        <div class="train-form">
          <div class="form-item">
            <label>模型名称</label>
            <input v-model="trainParams.modelName" type="text" placeholder="输入模型名称" />
          </div>
          <div class="form-item">
            <label>模型类型</label>
            <select v-model="trainParams.modelType">
              <option v-for="model in models" :key="model" :value="model">{{ model }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>模型参数</label>
            <textarea v-model="trainParams.modelParams" type="text" placeholder="输入模型参数，JSON格式" rows="5"></textarea>
          </div>
          <div class="form-item">
            <label>数据集配置</label>
            <textarea v-model="trainParams.datasetConfig" type="text" placeholder="输入数据集配置，JSON格式" rows="5"></textarea>
          </div>
          <div class="form-item">
            <label>训练器配置</label>
            <textarea v-model="trainParams.trainerConfig" type="text" placeholder="输入训练器配置，JSON格式" rows="5"></textarea>
          </div>
          <div class="form-actions">
            <button @click="trainModel" class="btn btn-primary">开始训练</button>
          </div>
        </div>
      </div>
      
      <!-- 训练状态 -->
      <div v-if="trainingStatus" class="section">
        <h2>训练状态</h2>
        <div class="training-status">
          <div class="status-item">
            <span class="label">状态:</span>
            <span :class="['value', trainingStatus.status]">{{ trainingStatus.status }}</span>
          </div>
          <div class="status-item">
            <span class="label">消息:</span>
            <span class="value">{{ trainingStatus.message }}</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 模型评估 -->
    <div v-else-if="activeTab === 'evaluate'" class="tab-content">
      <div class="section">
        <h2>模型评估</h2>
        <div class="evaluate-form">
          <div class="form-item">
            <label>选择模型</label>
            <select v-model="evaluateParams.modelName">
              <option v-for="model in savedModels" :key="model" :value="model">{{ model }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>数据集配置</label>
            <textarea v-model="evaluateParams.datasetConfig" type="text" placeholder="输入数据集配置，JSON格式" rows="5"></textarea>
          </div>
          <div class="form-actions">
            <button @click="evaluateModel()" class="btn btn-primary">开始评估</button>
          </div>
        </div>
      </div>
      
      <!-- 评估结果 -->
      <div v-if="evaluationResult" class="section">
        <h2>评估结果</h2>
        <div class="evaluation-result">
          <div class="metrics">
            <div class="metric-item">
              <span class="metric-name">MSE</span>
              <span class="metric-value">{{ evaluationResult.metrics.mse.toFixed(6) }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-name">MAE</span>
              <span class="metric-value">{{ evaluationResult.metrics.mae.toFixed(6) }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-name">R²</span>
              <span class="metric-value">{{ evaluationResult.metrics.r2.toFixed(4) }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-name">IC</span>
              <span class="metric-value">{{ evaluationResult.metrics.ic.toFixed(4) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 模型可视化 -->
    <div v-else-if="activeTab === 'visualization'" class="tab-content">
      <div class="section">
        <h2>模型可视化</h2>
        <div class="visualization-form">
          <div class="form-item">
            <label>选择模型</label>
            <select v-model="visualizationParams.modelName">
              <option v-for="model in savedModels" :key="model" :value="model">{{ model }}</option>
            </select>
          </div>
          <div class="form-actions">
            <button @click="visualizeModel()" class="btn btn-primary">可视化</button>
          </div>
        </div>
      </div>
      
      <!-- 可视化结果 -->
      <div v-if="visualizationResult" class="section">
        <h2>模型性能可视化</h2>
        <div class="chart-container">
          <div ref="modelChartRef" class="chart"></div>
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
  { id: 'list', name: '模型列表' },
  { id: 'train', name: '模型训练' },
  { id: 'evaluate', name: '模型评估' },
  { id: 'visualization', name: '模型可视化' }
];
const activeTab = ref('list');

// 模型列表
const models = ref<string[]>([]);
const savedModels = ref<string[]>([]);
const selectedModel = ref<string>('');

// 训练参数
const trainParams = ref({
  modelName: 'my_model',
  modelType: 'lightgbm',
  modelParams: JSON.stringify({
    task: 'train',
    objective: 'regression',
    boosting_type: 'gbdt',
    num_leaves: 31,
    learning_rate: 0.05,
    n_estimators: 100
  }, null, 2),
  datasetConfig: JSON.stringify({
    "class": "qlib.data.dataset.DatasetH",
    "kwargs": {
      "handler": {
        "class": "qlib.data.handler.DataHandlerLP",
        "kwargs": {
          "start_time": "2024-01-01",
          "end_time": "2024-12-31",
          "fit_start_time": "2024-01-01",
          "fit_end_time": "2024-06-30",
          "instruments": "all",
          "fields": [
            "$close",
            "$volume",
            "$open",
            "$high",
            "$low"
          ],
          "label": [
            "Ref($close, -2) / Ref($close, -1) - 1"
          ]
        }
      },
      "segments": {
        "train": ["2024-01-01", "2024-06-30"],
        "valid": ["2024-07-01", "2024-09-30"],
        "test": ["2024-10-01", "2024-12-31"]
      }
    }
  }, null, 2),
  trainerConfig: JSON.stringify({
    "class": "qlib.model.trainer.TrainerR",
    "kwargs": {
      "epochs": 10,
      "early_stopping_rounds": 20,
      "verbose": 1
    }
  }, null, 2)
});

// 训练状态
const trainingStatus = ref<any>(null);

// 评估参数
const evaluateParams = ref({
  modelName: '',
  datasetConfig: JSON.stringify({
    "class": "qlib.data.dataset.DatasetH",
    "kwargs": {
      "handler": {
        "class": "qlib.data.handler.DataHandlerLP",
        "kwargs": {
          "start_time": "2024-10-01",
          "end_time": "2024-12-31",
          "instruments": "all",
          "fields": [
            "$close",
            "$volume",
            "$open",
            "$high",
            "$low"
          ],
          "label": [
            "Ref($close, -2) / Ref($close, -1) - 1"
          ]
        }
      },
      "segments": {
        "test": ["2024-10-01", "2024-12-31"]
      }
    }
  }, null, 2)
});

// 评估结果
const evaluationResult = ref<any>(null);

// 可视化参数
const visualizationParams = ref({
  modelName: ''
});

// 可视化结果
const visualizationResult = ref<any>(null);

// 图表实例
let modelChart: echarts.ECharts | null = null;

// 图表容器ref
const modelChartRef = ref<HTMLElement | null>(null);

// 获取模型类型列表
const fetchModels = async () => {
  try {
    const response = await axios.get('http://localhost:8000/api/model/list');
    if (response.data.code === 0) {
      models.value = response.data.data.models;
    }
  } catch (error) {
    console.error('获取模型类型列表失败:', error);
  }
};

// 获取保存的模型列表
const fetchSavedModels = async () => {
  try {
    const response = await axios.get('http://localhost:8000/api/model/saved');
    if (response.data.code === 0) {
      savedModels.value = response.data.data.saved_models;
    }
  } catch (error) {
    console.error('获取保存的模型列表失败:', error);
  }
};

// 选择模型
const selectModel = (model: string) => {
  selectedModel.value = model;
};

// 训练模型
const trainModel = async () => {
  try {
    if (!trainParams.value.modelName) {
      alert('请输入模型名称');
      return;
    }
    
    let modelParams, datasetConfig, trainerConfig;
    try {
      modelParams = JSON.parse(trainParams.value.modelParams);
      datasetConfig = JSON.parse(trainParams.value.datasetConfig);
      trainerConfig = JSON.parse(trainParams.value.trainerConfig);
    } catch (e) {
      alert('参数格式错误，请检查JSON格式');
      return;
    }
    
    // 创建模型配置
    const modelConfigResponse = await axios.post('http://localhost:8000/api/model/config', {
      model_type: trainParams.value.modelType,
      params: modelParams
    });
    
    if (modelConfigResponse.data.code !== 0) {
      alert('模型配置创建失败: ' + modelConfigResponse.data.message);
      return;
    }
    
    const modelConfig = modelConfigResponse.data.data.model_config;
    modelConfig.model_name = trainParams.value.modelName;
    
    // 开始训练
    trainingStatus.value = { status: 'training', message: '模型训练中...' };
    
    const response = await axios.post('http://localhost:8000/api/model/train', {
      model_config: modelConfig,
      dataset_config: datasetConfig,
      trainer_config: trainerConfig
    });
    
    if (response.data.code === 0) {
      trainingStatus.value = { status: 'success', message: '模型训练成功' };
      fetchSavedModels();
    } else {
      trainingStatus.value = { status: 'failed', message: '模型训练失败: ' + response.data.message };
    }
  } catch (error) {
    console.error('模型训练失败:', error);
    trainingStatus.value = { status: 'failed', message: '模型训练失败: ' + (error as any).message };
  }
};

// 评估模型
const evaluateModel = async (modelName?: string) => {
  try {
    const name = modelName || selectedModel.value;
    if (!name) {
      alert('请选择模型');
      return;
    }
    
    let datasetConfig;
    try {
      datasetConfig = JSON.parse(evaluateParams.value.datasetConfig);
    } catch (e) {
      alert('数据集配置格式错误，请检查JSON格式');
      return;
    }
    
    const response = await axios.post('http://localhost:8000/api/model/evaluate', {
      model_name: name,
      dataset_config: datasetConfig
    });
    
    if (response.data.code === 0) {
      evaluationResult.value = response.data.data;
      activeTab.value = 'evaluate';
    } else {
      alert('模型评估失败: ' + response.data.message);
    }
  } catch (error) {
    console.error('模型评估失败:', error);
    alert('模型评估失败');
  }
};

// 删除模型
const deleteModel = async (modelName: string) => {
  try {
    if (confirm(`确定要删除模型 ${modelName} 吗？`)) {
      const response = await axios.delete(`http://localhost:8000/api/model/delete/${modelName}`);
      
      if (response.data.code === 0) {
        alert('模型删除成功');
        fetchSavedModels();
        if (selectedModel.value === modelName) {
          selectedModel.value = '';
        }
      } else {
        alert('模型删除失败: ' + response.data.message);
      }
    }
  } catch (error) {
    console.error('模型删除失败:', error);
    alert('模型删除失败');
  }
};

// 模型可视化
const visualizeModel = async () => {
  try {
    if (!visualizationParams.value.modelName) {
      alert('请选择模型');
      return;
    }
    
    // 这里使用模拟数据，实际应该调用模型预测API获取真实数据
    visualizationResult.value = {
      model_name: visualizationParams.value.modelName,
      predictions: [0.1, 0.2, 0.15, -0.1, 0.05, 0.3, 0.25, -0.05, 0.1, 0.15],
      labels: [0.08, 0.18, 0.12, -0.12, 0.03, 0.28, 0.22, -0.08, 0.08, 0.12]
    };
    
    renderModelChart();
  } catch (error) {
    console.error('模型可视化失败:', error);
    alert('模型可视化失败');
  }
};

// 渲染模型图表
const renderModelChart = () => {
  if (!modelChart && modelChartRef.value) {
    modelChart = echarts.init(modelChartRef.value);
  }
  
  if (visualizationResult.value) {
    const predictions = visualizationResult.value.predictions;
    const labels = visualizationResult.value.labels;
    const dates = ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06', '2024-07', '2024-08', '2024-09', '2024-10'];
    
    const option = {
      title: {
        text: `${visualizationParams.value.modelName} 模型预测结果`
      },
      tooltip: {
        trigger: 'axis'
      },
      legend: {
        data: ['预测值', '真实值']
      },
      xAxis: {
        type: 'category',
        data: dates
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name: '预测值',
          data: predictions,
          type: 'line'
        },
        {
          name: '真实值',
          data: labels,
          type: 'line'
        }
      ]
    };
    
    modelChart?.setOption(option);
  }
};

// 初始化
onMounted(() => {
  fetchModels();
  fetchSavedModels();
});
</script>

<style scoped>
.model-management-container {
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

/* 模型列表 */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.model-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background-color: #f0f0f0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
}

.model-item:hover {
  background-color: #e0e0e0;
}

.model-actions {
  display: flex;
  gap: 5px;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 12px;
}

.empty-state {
  text-align: center;
  padding: 20px;
  color: #666;
  background-color: #fafafa;
  border-radius: 4px;
}

/* 表单样式 */
.train-form,
.evaluate-form,
.visualization-form {
  background-color: #fafafa;
  padding: 20px;
  border-radius: 4px;
}

.form-item {
  margin-bottom: 15px;
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
  font-family: monospace;
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

.btn-danger {
  background-color: #ff4d4f;
  color: #fff;
}

.btn-danger:hover {
  background-color: #ff7875;
}

/* 训练状态 */
.training-status {
  background-color: #fafafa;
  padding: 20px;
  border-radius: 4px;
}

.status-item {
  display: flex;
  margin-bottom: 10px;
}

.status-item .label {
  width: 80px;
  font-weight: 500;
  color: #333;
}

.status-item .value {
  color: #666;
}

.status-item .value.training {
  color: #faad14;
}

.status-item .value.success {
  color: #52c41a;
}

.status-item .value.failed {
  color: #ff4d4f;
}

/* 评估结果 */
.evaluation-result {
  background-color: #fafafa;
  padding: 20px;
  border-radius: 4px;
}

.metrics {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.metric-item {
  background-color: #fff;
  padding: 20px;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  min-width: 150px;
  text-align: center;
}

.metric-name {
  display: block;
  font-size: 14px;
  color: #666;
  margin-bottom: 5px;
}

.metric-value {
  display: block;
  font-size: 24px;
  font-weight: bold;
  color: #1890ff;
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
