/**
 * 因子分析页面组件
 * 功能：提供因子管理、计算、有效性检验和可视化功能
 */
import { useState, useEffect, useRef } from 'react';
import axios from '../api';
import * as echarts from 'echarts';
import '../styles/FactorAnalysis.css';

// 标签页类型定义
interface Tab {
  id: string;
  name: string;
}

// 新因子类型定义
interface NewFactor {
  name: string;
  expression: string;
}

// 计算参数类型定义
interface CalculateParams {
  factorName: string[];
  instruments: string;
  startTime: string;
  endTime: string;
  freq: string;
}

// 因子计算结果项类型定义
interface FactorDataItem {
  date: string;
  instrument: string;
  value: number;
}

// 因子计算结果类型定义
interface FactorResult {
  factor_name: string;
  shape: [number, number];
  data: FactorDataItem[];
}

// 有效性检验参数类型定义
interface ValidationParams {
  factorName: string;
  startTime: string;
  endTime: string;
}

// 单调性检验结果类型定义
interface MonotonicityResult {
  monotonicity_score: number;
  monotonicity_corr: number;
}

// 有效性检验结果类型定义
interface ValidationResult {
  ic?: number[];
  ir?: number;
  groupAnalysis?: any;
  monotonicity?: MonotonicityResult;
  stability?: any;
}

// 可视化参数类型定义
interface VisualizationParams {
  factorName: string;
  instrument: string;
  startTime: string;
  endTime: string;
}

const FactorAnalysis = () => {
  // 标签页状态
  const [activeTab, setActiveTab] = useState<string>('list');
  
  // 因子列表
  const [factors, setFactors] = useState<string[]>([]);
  const [selectedFactor, setSelectedFactor] = useState<string>('');
  
  // 自定义因子
  const [newFactor, setNewFactor] = useState<NewFactor>({
    name: '',
    expression: ''
  });
  
  // 计算参数
  const [calculateParams, setCalculateParams] = useState<CalculateParams>({
    factorName: [],
    instruments: 'BTC,ETH,BNB',
    startTime: '2024-01-01',
    endTime: '2024-12-31',
    freq: 'day'
  });
  
  // 因子计算结果
  const [factorResult, setFactorResult] = useState<FactorResult | null>(null);
  
  // 有效性检验参数
  const [validationParams, setValidationParams] = useState<ValidationParams>({
    factorName: '',
    startTime: '2024-01-01',
    endTime: '2024-12-31'
  });
  
  // 有效性检验结果
  const [validationResult, setValidationResult] = useState<ValidationResult>({});
  
  // 可视化参数
  const [visualizationParams, setVisualizationParams] = useState<VisualizationParams>({
    factorName: '',
    instrument: 'BTC',
    startTime: '2024-01-01',
    endTime: '2024-12-31'
  });
  
  // 可视化结果
  const [visualizationResult, setVisualizationResult] = useState<FactorResult | null>(null);
  
  // 图表容器ref
  const icChartRef = useRef<HTMLDivElement>(null);
  const groupChartRef = useRef<HTMLDivElement>(null);
  const stabilityChartRef = useRef<HTMLDivElement>(null);
  const factorChartRef = useRef<HTMLDivElement>(null);
  
  // 图表实例
  const icChart = useRef<echarts.ECharts | null>(null);
  const groupChart = useRef<echarts.ECharts | null>(null);
  const stabilityChart = useRef<echarts.ECharts | null>(null);
  const factorChart = useRef<echarts.ECharts | null>(null);
  
  // 标签页数据
  const tabs: Tab[] = [
    { id: 'list', name: '因子列表' },
    { id: 'calculate', name: '因子计算' },
    { id: 'validation', name: '有效性检验' },
    { id: 'visualization', name: '因子可视化' }
  ];

  /**
   * 获取因子列表
   */
  const fetchFactors = async () => {
    try {
      const response = await axios.get('/api/factor/list');
      if (response.data.code === 0) {
        setFactors(response.data.data.factors);
      }
    } catch (error) {
      console.error('获取因子列表失败:', error);
    }
  };

  /**
   * 选择因子
   * @param factor 因子名称
   */
  const selectFactor = (factor: string) => {
    setSelectedFactor(factor);
  };

  /**
   * 添加因子
   */
  const addFactor = async () => {
    try {
      if (!newFactor.name || !newFactor.expression) {
        alert('请输入因子名称和表达式');
        return;
      }
      
      const response = await axios.post('/api/factor/add', {
        factor_name: newFactor.name,
        expression: newFactor.expression
      });
      
      if (response.data.code === 0) {
        alert('因子添加成功');
        fetchFactors();
        setNewFactor({ name: '', expression: '' });
      } else {
        alert('因子添加失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('添加因子失败:', error);
      alert('添加因子失败');
    }
  };

  /**
   * 验证因子表达式
   */
  const validateFactor = async () => {
    try {
      if (!newFactor.expression) {
        alert('请输入因子表达式');
        return;
      }
      
      const response = await axios.post('/api/factor/validate', {
        expression: newFactor.expression
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

  /**
   * 计算因子
   */
  const calculateFactor = async () => {
    try {
      if (calculateParams.factorName.length === 0) {
        alert('请选择至少一个因子');
        return;
      }
      
      const instruments = calculateParams.instruments.split(',').map(item => item.trim());
      
      const response = await axios.post('/api/factor/calculate', {
        factor_name: calculateParams.factorName[0],
        instruments: instruments,
        start_time: calculateParams.startTime,
        end_time: calculateParams.endTime,
        freq: calculateParams.freq
      });
      
      if (response.data.code === 0) {
        setFactorResult(response.data.data);
      } else {
        alert('因子计算失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('计算因子失败:', error);
      alert('计算因子失败');
    }
  };

  /**
   * 计算IC
   */
  const calculateIC = async () => {
    try {
      const response = await axios.post('/api/factor/ic', {
        factor_data: {}, // 实际应该传入因子数据
        return_data: {}, // 实际应该传入收益率数据
        method: 'spearman'
      });
      
      if (response.data.code === 0) {
        setValidationResult(prev => ({
          ...prev,
          ic: response.data.data.ic
        }));
        renderICChart();
      } else {
        alert('计算IC失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('计算IC失败:', error);
      alert('计算IC失败');
    }
  };

  /**
   * 计算IR
   */
  const calculateIR = async () => {
    try {
      const response = await axios.post('/api/factor/ir', {
        factor_data: {}, // 实际应该传入因子数据
        return_data: {}, // 实际应该传入收益率数据
        method: 'spearman'
      });
      
      if (response.data.code === 0) {
        setValidationResult(prev => ({
          ...prev,
          ir: response.data.data.ir
        }));
      } else {
        alert('计算IR失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('计算IR失败:', error);
      alert('计算IR失败');
    }
  };

  /**
   * 分组分析
   */
  const groupAnalysis = async () => {
    try {
      const response = await axios.post('/api/factor/group-analysis', {
        factor_data: {}, // 实际应该传入因子数据
        return_data: {}, // 实际应该传入收益率数据
        n_groups: 5
      });
      
      if (response.data.code === 0) {
        setValidationResult(prev => ({
          ...prev,
          groupAnalysis: response.data.data.group_analysis
        }));
        renderGroupChart();
      } else {
        alert('分组分析失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('分组分析失败:', error);
      alert('分组分析失败');
    }
  };

  /**
   * 单调性检验
   */
  const monotonicityTest = async () => {
    try {
      const response = await axios.post('/api/factor/monotonicity', {
        factor_data: {}, // 实际应该传入因子数据
        return_data: {}, // 实际应该传入收益率数据
        n_groups: 5
      });
      
      if (response.data.code === 0) {
        setValidationResult(prev => ({
          ...prev,
          monotonicity: response.data.data.monotonicity
        }));
      } else {
        alert('单调性检验失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('单调性检验失败:', error);
      alert('单调性检验失败');
    }
  };

  /**
   * 稳定性检验
   */
  const stabilityTest = async () => {
    try {
      const response = await axios.post('/api/factor/stability', {
        factor_data: {}, // 实际应该传入因子数据
        window: 20
      });
      
      if (response.data.code === 0) {
        setValidationResult(prev => ({
          ...prev,
          stability: response.data.data.stability
        }));
        renderStabilityChart();
      } else {
        alert('稳定性检验失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('稳定性检验失败:', error);
      alert('稳定性检验失败');
    }
  };

  /**
   * 因子可视化
   */
  const visualizeFactor = async () => {
    try {
      if (!visualizationParams.factorName || !visualizationParams.instrument) {
        alert('请选择因子和标的');
        return;
      }
      
      const response = await axios.post('/api/factor/calculate', {
        factor_name: visualizationParams.factorName,
        instruments: [visualizationParams.instrument],
        start_time: visualizationParams.startTime,
        end_time: visualizationParams.endTime,
        freq: 'day'
      });
      
      if (response.data.code === 0) {
        setVisualizationResult(response.data.data);
        renderFactorChart();
      } else {
        alert('因子可视化失败: ' + response.data.message);
      }
    } catch (error) {
      console.error('因子可视化失败:', error);
      alert('因子可视化失败');
    }
  };

  /**
   * 渲染IC图表
   */
  const renderICChart = () => {
    if (!icChart.current && icChartRef.current) {
      icChart.current = echarts.init(icChartRef.current);
    }
    
    // 模拟数据，实际应该使用validationResult.ic
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
    
    icChart.current?.setOption(option);
  };

  /**
   * 渲染分组图表
   */
  const renderGroupChart = () => {
    if (!groupChart.current && groupChartRef.current) {
      groupChart.current = echarts.init(groupChartRef.current);
    }
    
    // 模拟数据，实际应该使用validationResult.groupAnalysis
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
    
    groupChart.current?.setOption(option);
  };

  /**
   * 渲染稳定性图表
   */
  const renderStabilityChart = () => {
    if (!stabilityChart.current && stabilityChartRef.current) {
      stabilityChart.current = echarts.init(stabilityChartRef.current);
    }
    
    // 模拟数据，实际应该使用validationResult.stability
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
    
    stabilityChart.current?.setOption(option);
  };

  /**
   * 渲染因子趋势图
   */
  const renderFactorChart = () => {
    if (!factorChart.current && factorChartRef.current) {
      factorChart.current = echarts.init(factorChartRef.current);
    }
    
    if (visualizationResult) {
      const data = visualizationResult.data.map((item) => item.value);
      const dates = visualizationResult.data.map((item) => item.date);
      
      const option = {
        title: {
          text: `${visualizationParams.factorName} - ${visualizationParams.instrument} 因子值走势`
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
      
      factorChart.current?.setOption(option);
    }
  };

  // 组件挂载时获取因子列表
  useEffect(() => {
    fetchFactors();
  }, []);

  return (
    <div className="factor-analysis-container">
      <h1>因子分析</h1>
      
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
      
      {/* 因子列表 */}
      {activeTab === 'list' && (
        <div className="tab-content">
          <div className="section">
            <h2>因子列表</h2>
            <div className="factor-list">
              {factors.map(factor => (
                <div 
                  key={factor}
                  className={`factor-item ${selectedFactor === factor ? 'selected' : ''}`}
                  onClick={() => selectFactor(factor)}
                >
                  {factor}
                </div>
              ))}
            </div>
          </div>
          
          <div className="section">
            <h2>自定义因子</h2>
            <div className="custom-factor-form">
              <div className="form-item">
                <label>因子名称</label>
                <input 
                  value={newFactor.name} 
                  type="text" 
                  placeholder="输入因子名称"
                  onChange={(e) => setNewFactor(prev => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div className="form-item">
                <label>因子表达式</label>
                <input 
                  value={newFactor.expression} 
                  type="text" 
                  placeholder="输入因子表达式，如 $close / $Ref($close, 5) - 1"
                  onChange={(e) => setNewFactor(prev => ({ ...prev, expression: e.target.value }))}
                />
              </div>
              <div className="form-actions">
                <button onClick={addFactor} className="btn btn-primary">添加因子</button>
                <button onClick={validateFactor} className="btn btn-secondary">验证表达式</button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* 因子计算 */}
      {activeTab === 'calculate' && (
        <div className="tab-content">
          <div className="section">
            <h2>因子计算</h2>
            <div className="calculate-form">
              <div className="form-item">
                <label>选择因子</label>
                <select 
                  value={calculateParams.factorName} 
                  multiple
                  onChange={(e) => {
                    const selectedOptions = Array.from(e.target.selectedOptions, option => option.value);
                    setCalculateParams(prev => ({ ...prev, factorName: selectedOptions }));
                  }}
                >
                  {factors.map(factor => (
                    <option key={factor} value={factor}>{factor}</option>
                  ))}
                </select>
              </div>
              <div className="form-item">
                <label>标的列表</label>
                <textarea 
                  value={calculateParams.instruments} 
                  placeholder="输入标的列表，用逗号分隔" 
                  rows={3}
                  onChange={(e) => setCalculateParams(prev => ({ ...prev, instruments: e.target.value }))}
                ></textarea>
              </div>
              <div className="form-row">
                <div className="form-item">
                  <label>开始时间</label>
                  <input 
                    value={calculateParams.startTime} 
                    type="date"
                    onChange={(e) => setCalculateParams(prev => ({ ...prev, startTime: e.target.value }))}
                  />
                </div>
                <div className="form-item">
                  <label>结束时间</label>
                  <input 
                    value={calculateParams.endTime} 
                    type="date"
                    onChange={(e) => setCalculateParams(prev => ({ ...prev, endTime: e.target.value }))}
                  />
                </div>
                <div className="form-item">
                  <label>频率</label>
                  <select 
                    value={calculateParams.freq}
                    onChange={(e) => setCalculateParams(prev => ({ ...prev, freq: e.target.value }))}
                  >
                    <option value="day">日线</option>
                    <option value="1min">1分钟</option>
                    <option value="5min">5分钟</option>
                    <option value="15min">15分钟</option>
                    <option value="30min">30分钟</option>
                    <option value="60min">60分钟</option>
                  </select>
                </div>
              </div>
              <div className="form-actions">
                <button onClick={calculateFactor} className="btn btn-primary">计算因子</button>
              </div>
            </div>
          </div>
          
          {/* 计算结果 */}
          {factorResult && (
            <div className="section">
              <h2>计算结果</h2>
              <div className="result-info">
                <p>因子名称: {factorResult.factor_name}</p>
                <p>数据形状: {factorResult.shape[0]} 行, {factorResult.shape[1]} 列</p>
              </div>
              <div className="result-table">
                <table>
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>标的</th>
                      <th>因子值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factorResult.data.slice(0, 10).map(item => (
                      <tr key={`${item.date}-${item.instrument}`}>
                        <td>{item.date}</td>
                        <td>{item.instrument}</td>
                        <td>{item.value.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {factorResult.data.length > 10 && (
                  <div className="more-data">
                    显示前10条数据，共 {factorResult.data.length} 条
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* 因子有效性检验 */}
      {activeTab === 'validation' && (
        <div className="tab-content">
          <div className="section">
            <h2>因子有效性检验</h2>
            <div className="validation-form">
              <div className="form-item">
                <label>选择因子</label>
                <select 
                  value={validationParams.factorName}
                  onChange={(e) => setValidationParams(prev => ({ ...prev, factorName: e.target.value }))}
                >
                  {factors.map(factor => (
                    <option key={factor} value={factor}>{factor}</option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <div className="form-item">
                  <label>开始时间</label>
                  <input 
                    value={validationParams.startTime} 
                    type="date"
                    onChange={(e) => setValidationParams(prev => ({ ...prev, startTime: e.target.value }))}
                  />
                </div>
                <div className="form-item">
                  <label>结束时间</label>
                  <input 
                    value={validationParams.endTime} 
                    type="date"
                    onChange={(e) => setValidationParams(prev => ({ ...prev, endTime: e.target.value }))}
                  />
                </div>
              </div>
              <div className="form-actions">
                <button onClick={calculateIC} className="btn btn-primary">计算IC</button>
                <button onClick={calculateIR} className="btn btn-primary">计算IR</button>
                <button onClick={groupAnalysis} className="btn btn-primary">分组分析</button>
                <button onClick={monotonicityTest} className="btn btn-primary">单调性检验</button>
                <button onClick={stabilityTest} className="btn btn-primary">稳定性检验</button>
              </div>
            </div>
          </div>
          
          {/* 检验结果 */}
          {Object.keys(validationResult).length > 0 && (
            <div className="section">
              <h2>检验结果</h2>
              <div className="validation-result">
                {validationResult.ic && (
                  <div className="result-item">
                    <h3>信息系数(IC)</h3>
                    <div className="chart-container">
                      <div ref={icChartRef} className="chart"></div>
                    </div>
                  </div>
                )}
                
                {validationResult.ir !== undefined && (
                  <div className="result-item">
                    <h3>信息比率(IR)</h3>
                    <div className="ir-value">{validationResult.ir.toFixed(4)}</div>
                  </div>
                )}
                
                {validationResult.groupAnalysis && (
                  <div className="result-item">
                    <h3>分组分析</h3>
                    <div className="chart-container">
                      <div ref={groupChartRef} className="chart"></div>
                    </div>
                  </div>
                )}
                
                {validationResult.monotonicity && (
                  <div className="result-item">
                    <h3>单调性检验</h3>
                    <div className="monotonicity-info">
                      <p>单调性得分: {validationResult.monotonicity.monotonicity_score.toFixed(4)}</p>
                      <p>相关性: {validationResult.monotonicity.monotonicity_corr.toFixed(4)}</p>
                    </div>
                  </div>
                )}
                
                {validationResult.stability && (
                  <div className="result-item">
                    <h3>稳定性检验</h3>
                    <div className="chart-container">
                      <div ref={stabilityChartRef} className="chart"></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* 因子可视化 */}
      {activeTab === 'visualization' && (
        <div className="tab-content">
          <div className="section">
            <h2>因子可视化</h2>
            <div className="visualization-form">
              <div className="form-item">
                <label>选择因子</label>
                <select 
                  value={visualizationParams.factorName}
                  onChange={(e) => setVisualizationParams(prev => ({ ...prev, factorName: e.target.value }))}
                >
                  {factors.map(factor => (
                    <option key={factor} value={factor}>{factor}</option>
                  ))}
                </select>
              </div>
              <div className="form-item">
                <label>选择标的</label>
                <input 
                  value={visualizationParams.instrument} 
                  type="text" 
                  placeholder="输入标的代码"
                  onChange={(e) => setVisualizationParams(prev => ({ ...prev, instrument: e.target.value }))}
                />
              </div>
              <div className="form-row">
                <div className="form-item">
                  <label>开始时间</label>
                  <input 
                    value={visualizationParams.startTime} 
                    type="date"
                    onChange={(e) => setVisualizationParams(prev => ({ ...prev, startTime: e.target.value }))}
                  />
                </div>
                <div className="form-item">
                  <label>结束时间</label>
                  <input 
                    value={visualizationParams.endTime} 
                    type="date"
                    onChange={(e) => setVisualizationParams(prev => ({ ...prev, endTime: e.target.value }))}
                  />
                </div>
              </div>
              <div className="form-actions">
                <button onClick={visualizeFactor} className="btn btn-primary">可视化</button>
              </div>
            </div>
          </div>
          
          {/* 可视化结果 */}
          {visualizationResult && (
            <div className="section">
              <h2>因子趋势图</h2>
              <div className="chart-container">
                <div ref={factorChartRef} className="chart"></div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FactorAnalysis;