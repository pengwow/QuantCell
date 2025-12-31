/**
 * 模型管理页面组件
 * 功能：提供模型管理、训练、评估和可视化功能
 */
import { useState, useEffect, useRef } from 'react';
import axios from '../api';
import * as echarts from 'echarts';
import '../styles/ModelManagement.css';

// 标签页类型定义
interface Tab {
  id: string;
  name: string;
}

// 训练参数类型定义
interface TrainParams {
  modelName: string;
  modelType: string;
  modelParams: string;
  datasetConfig: string;
  trainerConfig: string;
}

// 训练状态类型定义
interface TrainingStatus {
  status: 'training' | 'success' | 'failed';
  message: string;
}

// 评估参数类型定义
interface EvaluateParams {
  modelName: string;
  datasetConfig: string;
}

// 评估指标类型定义
interface Metrics {
  mse: number;
  mae: number;
  r2: number;
  ic: number;
}

// 评估结果类型定义
interface EvaluationResult {
  metrics: Metrics;
}

// 可视化参数类型定义
interface VisualizationParams {
  modelName: string;
}

// 可视化结果类型定义
interface VisualizationResult {
  model_name: string;
  predictions: number[];
  labels: number[];
}

const ModelManagement = () => {
  // 标签页状态
  const [activeTab, setActiveTab] = useState<string>('list');
  
  // 模型列表
  const [models, setModels] = useState<string[]>([]);
  const [savedModels, setSavedModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  
  // 训练参数
  const [trainParams, setTrainParams] = useState<TrainParams>({
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
  const [trainingStatus, setTrainingStatus] = useState<TrainingStatus | null>(null);
  
  // 评估参数
  const [evaluateParams, setEvaluateParams] = useState<EvaluateParams>({
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
  const [evaluationResult, setEvaluationResult] = useState<EvaluationResult | null>(null);
  
  // 可视化参数
  const [visualizationParams, setVisualizationParams] = useState<VisualizationParams>({
    modelName: ''
  });
  
  // 可视化结果
  const [visualizationResult, setVisualizationResult] = useState<VisualizationResult | null>(null);
  
  // 图表容器ref
  const modelChartRef = useRef<HTMLDivElement>(null);
  
  // 图表实例
  const modelChart = useRef<echarts.ECharts | null>(null);
  
  // 标签页数据
  const tabs: Tab[] = [
    { id: 'list', name: '模型列表' },
    { id: 'train', name: '模型训练' },
    { id: 'evaluate', name: '模型评估' },
    { id: 'visualization', name: '模型可视化' }
  ];

  /**
   * 获取模型类型列表
   */
  const fetchModels = async () => {
    try {
      const response = await axios.get('/api/model/list');
      if (response.data.code === 0) {
        setModels(response.data.data.models);
      }
    } catch (error) {
      console.error('获取模型类型列表失败:', error);
    }
  };

  /**
   * 获取保存的模型列表
   */
  const fetchSavedModels = async () => {
    try {
      const response = await axios.get('/api/model/saved');
      if (response.data.code === 0) {
        setSavedModels(response.data.data.saved_models);
      }
    } catch (error) {
      console.error('获取保存的模型列表失败:', error);
    }
  };

  /**
   * 选择模型
   * @param model 模型名称
   */
  const selectModel = (model: string) => {
    setSelectedModel(model);
  };

  /**
   * 训练模型
   */
  const trainModel = async () => {
    try {
      if (!trainParams.modelName) {
        alert('请输入模型名称');
        return;
      }
      
      let modelParams, datasetConfig, trainerConfig;
      try {
        modelParams = JSON.parse(trainParams.modelParams);
        datasetConfig = JSON.parse(trainParams.datasetConfig);
        trainerConfig = JSON.parse(trainParams.trainerConfig);
      } catch (e) {
        alert('参数格式错误，请检查JSON格式');
        return;
      }
      
      // 创建模型配置
      const modelConfigResponse = await axios.post('/api/model/config', {
        model_type: trainParams.modelType,
        params: modelParams
      });
      
      if (modelConfigResponse.data.code !== 0) {
        alert('模型配置创建失败: ' + modelConfigResponse.data.message);
        return;
      }
      
      const modelConfig = modelConfigResponse.data.data.model_config;
      modelConfig.model_name = trainParams.modelName;
      
      // 开始训练
      setTrainingStatus({ status: 'training', message: '模型训练中...' });
      
      const response = await axios.post('/api/model/train', {
        model_config: modelConfig,
        dataset_config: datasetConfig,
        trainer_config: trainerConfig
      });
      
      if (response.data.code === 0) {
        setTrainingStatus({ status: 'success', message: '模型训练成功' });
        fetchSavedModels();
      } else {
        setTrainingStatus({ status: 'failed', message: '模型训练失败: ' + response.data.message });
      }
    } catch (error) {
      console.error('模型训练失败:', error);
      setTrainingStatus({ status: 'failed', message: '模型训练失败: ' + (error as any).message });
    }
  };

  /**
   * 评估模型
   * @param modelName 模型名称（可选，默认使用选中的模型）
   */
  const evaluateModel = async (modelName?: string) => {
    try {
      const name = modelName || selectedModel;
      if (!name) {
        alert('请选择模型');
        return;
      }
      
      let parsedDatasetConfig;
      try {
        parsedDatasetConfig = JSON.parse(evaluateParams.datasetConfig);
      } catch (e) {
        alert('数据集配置格式错误，请检查JSON格式');
        return;
      }
      
      const response = await axios.post('/api/model/evaluate', {
        model_name: name,
        dataset_config: parsedDatasetConfig
      });
      
      if (response.data.code === 0) {
        setEvaluationResult(response.data.data);
        setActiveTab('evaluate');
      } else {
        alert('模型评估失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('模型评估失败:', error);
      alert('模型评估失败');
    }
  };

  /**
   * 删除模型
   * @param modelName 模型名称
   */
  const deleteModel = async (modelName: string) => {
    try {
      if (confirm(`确定要删除模型 ${modelName} 吗？`)) {
        const response = await axios.delete(`/api/model/delete/${modelName}`);
        
        if (response.data.code === 0) {
          alert('模型删除成功');
          fetchSavedModels();
          if (selectedModel === modelName) {
            setSelectedModel('');
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

  /**
   * 模型可视化
   */
  const visualizeModel = async () => {
    try {
      if (!visualizationParams.modelName) {
        alert('请选择模型');
        return;
      }
      
      // 这里使用模拟数据，实际应该调用模型预测API获取真实数据
      setVisualizationResult({
        model_name: visualizationParams.modelName,
        predictions: [0.1, 0.2, 0.15, -0.1, 0.05, 0.3, 0.25, -0.05, 0.1, 0.15],
        labels: [0.08, 0.18, 0.12, -0.12, 0.03, 0.28, 0.22, -0.08, 0.08, 0.12]
      });
      
      renderModelChart();
    } catch (error) {
      console.error('模型可视化失败:', error);
      alert('模型可视化失败');
    }
  };

  /**
   * 渲染模型图表
   */
  const renderModelChart = () => {
    if (!modelChart.current && modelChartRef.current) {
      modelChart.current = echarts.init(modelChartRef.current);
    }
    
    if (visualizationResult) {
      const predictions = visualizationResult.predictions;
      const labels = visualizationResult.labels;
      const dates = ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06', '2024-07', '2024-08', '2024-09', '2024-10'];
      
      const option = {
        title: {
          text: `${visualizationParams.modelName} 模型预测结果`
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
      
      modelChart.current?.setOption(option);
    }
  };

  // 组件挂载时获取数据
  useEffect(() => {
    fetchModels();
    fetchSavedModels();
  }, []);

  return (
    <div className="model-management-container">
      <h1>模型管理</h1>
      
      {/* 标签页 */}
      <div className="tabs">
        {tabs.map(tab => (
          <div 
            key={tab.id}
            className={`tab-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.name}
          </div>
        ))}
      </div>
      
      {/* 模型列表 */}
      {activeTab === 'list' && (
        <div className="tab-content">
          <div className="section">
            <h2>模型列表</h2>
            <div className="model-list">
              {savedModels.map(model => (
                <div 
                  key={model}
                  className={`model-item ${selectedModel === model ? 'selected' : ''}`}
                  onClick={() => selectModel(model)}
                >
                  {model}
                  <div className="model-actions">
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        evaluateModel(model);
                      }} 
                      className="btn btn-sm btn-primary"
                    >
                      评估
                    </button>
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteModel(model);
                      }} 
                      className="btn btn-sm btn-danger"
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {savedModels.length === 0 && (
              <div className="empty-state">
                暂无保存的模型
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* 模型训练 */}
      {activeTab === 'train' && (
        <div className="tab-content">
          <div className="section">
            <h2>模型训练</h2>
            <div className="train-form">
              <div className="form-item">
                <label>模型名称</label>
                <input 
                  value={trainParams.modelName} 
 
                  placeholder="输入模型名称"
                  onChange={(e) => setTrainParams(prev => ({ ...prev, modelName: e.target.value }))}
                />
              </div>
              <div className="form-item">
                <label>模型类型</label>
                <select 
                  value={trainParams.modelType}
                  onChange={(e) => setTrainParams(prev => ({ ...prev, modelType: e.target.value }))}
                >
                  {models.map(model => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </div>
              <div className="form-item">
                <label>模型参数</label>
                <textarea 
                  value={trainParams.modelParams} 
                  placeholder="输入模型参数，JSON格式" 
                  rows={5}
                  onChange={(e) => setTrainParams(prev => ({ ...prev, modelParams: e.target.value }))}
                ></textarea>
              </div>
              <div className="form-item">
                <label>数据集配置</label>
                <textarea 
                  value={trainParams.datasetConfig} 
                  placeholder="输入数据集配置，JSON格式" 
                  rows={5}
                  onChange={(e) => setTrainParams(prev => ({ ...prev, datasetConfig: e.target.value }))}
                ></textarea>
              </div>
              <div className="form-item">
                <label>训练器配置</label>
                <textarea 
                  value={trainParams.trainerConfig} 
                  placeholder="输入训练器配置，JSON格式" 
                  rows={5}
                  onChange={(e) => setTrainParams(prev => ({ ...prev, trainerConfig: e.target.value }))}
                ></textarea>
              </div>
              <div className="form-actions">
                <button onClick={trainModel} className="btn btn-primary">开始训练</button>
              </div>
            </div>
          </div>
          
          {/* 训练状态 */}
          {trainingStatus && (
            <div className="section">
              <h2>训练状态</h2>
              <div className="training-status">
                <div className="status-item">
                  <span className="label">状态:</span>
                  <span className={`value ${trainingStatus.status}`}>{trainingStatus.status}</span>
                </div>
                <div className="status-item">
                  <span className="label">消息:</span>
                  <span className="value">{trainingStatus.message}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* 模型评估 */}
      {activeTab === 'evaluate' && (
        <div className="tab-content">
          <div className="section">
            <h2>模型评估</h2>
            <div className="evaluate-form">
              <div className="form-item">
                <label>选择模型</label>
                <select 
                  value={evaluateParams.modelName}
                  onChange={(e) => setEvaluateParams(prev => ({ ...prev, modelName: e.target.value }))}
                >
                  {savedModels.map(model => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </div>
              <div className="form-item">
                <label>数据集配置</label>
                <textarea 
                  value={evaluateParams.datasetConfig} 
                  placeholder="输入数据集配置，JSON格式" 
                  rows={5}
                  onChange={(e) => setEvaluateParams(prev => ({ ...prev, datasetConfig: e.target.value }))}
                ></textarea>
              </div>
              <div className="form-actions">
                <button onClick={() => evaluateModel()} className="btn btn-primary">开始评估</button>
              </div>
            </div>
          </div>
          
          {/* 评估结果 */}
          {evaluationResult && (
            <div className="section">
              <h2>评估结果</h2>
              <div className="evaluation-result">
                <div className="metrics">
                  <div className="metric-item">
                    <span className="metric-name">MSE</span>
                    <span className="metric-value">{evaluationResult.metrics.mse.toFixed(6)}</span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-name">MAE</span>
                    <span className="metric-value">{evaluationResult.metrics.mae.toFixed(6)}</span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-name">R²</span>
                    <span className="metric-value">{evaluationResult.metrics.r2.toFixed(4)}</span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-name">IC</span>
                    <span className="metric-value">{evaluationResult.metrics.ic.toFixed(4)}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* 模型可视化 */}
      {activeTab === 'visualization' && (
        <div className="tab-content">
          <div className="section">
            <h2>模型可视化</h2>
            <div className="visualization-form">
              <div className="form-item">
                <label>选择模型</label>
                <select 
                  value={visualizationParams.modelName}
                  onChange={(e) => setVisualizationParams(prev => ({ ...prev, modelName: e.target.value }))}
                >
                  {savedModels.map(model => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </div>
              <div className="form-actions">
                <button onClick={visualizeModel} className="btn btn-primary">可视化</button>
              </div>
            </div>
          </div>
          
          {/* 可视化结果 */}
          {visualizationResult && (
            <div className="section">
              <h2>模型性能可视化</h2>
              <div className="chart-container">
                <div ref={modelChartRef} className="chart"></div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ModelManagement;