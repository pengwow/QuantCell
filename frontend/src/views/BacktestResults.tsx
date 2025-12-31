/**
 * 回测结果页面组件
 * 功能：展示回测任务列表和详细的回测结果，包括概览、绩效分析、交易详情和风险分析
 */
import { useState, useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import '../styles/BacktestResults.css';

// 回测任务类型定义
interface BacktestTask {
  id: number;
  name: string;
  status: 'completed' | 'running' | 'failed';
  date: string;
  return: number;
}

// 交易记录类型定义
interface Trade {
  id: number;
  date: string;
  symbol: string;
  type: '买入' | '卖出';
  price: number;
  quantity: number;
  profit: number;
}

const BacktestResults = () => {
  // 回测任务数据
  const [backtestTasks] = useState<BacktestTask[]>([
    { id: 1, name: '策略A回测', status: 'completed', date: '2024-01-15', return: 12.56 },
    { id: 2, name: '策略B回测', status: 'completed', date: '2024-01-14', return: -3.21 },
    { id: 3, name: '策略C回测', status: 'running', date: '2024-01-15', return: 0 },
    { id: 4, name: '策略A回测', status: 'completed', date: '2024-01-13', return: 5.67 },
    { id: 5, name: '策略B回测', status: 'completed', date: '2024-01-12', return: 8.92 },
  ]);

  // 选中的回测任务ID
  const [selectedTaskId, setSelectedTaskId] = useState<number>(1);

  // 交易数据
  const [trades] = useState<Trade[]>([
    { id: 1, date: '2024-01-15', symbol: 'BTCUSDT', type: '买入', price: 42000, quantity: 0.01, profit: 2.5 },
    { id: 2, date: '2024-01-14', symbol: 'ETHUSDT', type: '卖出', price: 2300, quantity: 0.1, profit: -1.2 },
    { id: 3, date: '2024-01-13', symbol: 'BTCUSDT', type: '买入', price: 41500, quantity: 0.01, profit: 3.8 },
    { id: 4, date: '2024-01-12', symbol: 'ETHUSDT', type: '卖出', price: 2350, quantity: 0.1, profit: 2.1 },
    { id: 5, date: '2024-01-11', symbol: 'BTCUSDT', type: '买入', price: 41000, quantity: 0.01, profit: 1.5 },
  ]);

  // 图表引用
  const returnChartRef = useRef<HTMLDivElement>(null);
  const riskChartRef = useRef<HTMLDivElement>(null);
  const returnChart = useRef<echarts.ECharts | null>(null);
  const riskChart = useRef<echarts.ECharts | null>(null);

  /**
   * 选择回测任务
   * @param taskId 任务ID
   */
  const selectTask = (taskId: number) => {
    setSelectedTaskId(taskId);
    // 这里可以添加加载回测结果的逻辑
  };

  /**
   * 初始化收益率曲线图表
   */
  const initReturnChart = () => {
    if (!returnChartRef.current) return;
    
    returnChart.current = echarts.init(returnChartRef.current);
    
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
    };
    
    returnChart.current.setOption(option);
  };

  /**
   * 初始化风险分析图表
   */
  const initRiskChart = () => {
    if (!riskChartRef.current) return;
    
    riskChart.current = echarts.init(riskChartRef.current);
    
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
    };
    
    riskChart.current.setOption(option);
  };

  /**
   * 监听窗口大小变化，调整图表大小
   */
  const handleResize = () => {
    returnChart.current?.resize();
    riskChart.current?.resize();
  };

  // 组件挂载时初始化图表
  useEffect(() => {
    initReturnChart();
    initRiskChart();
    window.addEventListener('resize', handleResize);

    // 组件卸载时清理
    return () => {
      window.removeEventListener('resize', handleResize);
      returnChart.current?.dispose();
      riskChart.current?.dispose();
    };
  }, []);

  return (
    <div className="backtest-results-container">
      <h1>回测结果</h1>
      
      <div className="backtest-layout">
        {/* 左侧：回测任务列表 */}
        <div className="backtest-list">
          <div className="panel">
            <div className="panel-header">
              <h2>回测任务</h2>
              <button className="btn btn-primary btn-sm">新建回测</button>
            </div>
            <div className="panel-body">
              {backtestTasks.map(task => (
                <div 
                  key={task.id}
                  className={`backtest-task-item ${selectedTaskId === task.id ? 'active' : ''}`}
                  onClick={() => selectTask(task.id)}
                >
                  <div className="task-header">
                    <div className="task-name">{task.name}</div>
                    <div className={`task-status ${task.status}`}>{task.status}</div>
                  </div>
                  <div className="task-meta">
                    <div className="task-date">{task.date}</div>
                    <div className="task-return">{task.return}%</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        
        {/* 右侧：回测结果详情 */}
        <div className="backtest-detail">
          {/* 回测概览 */}
          <div className="panel">
            <div className="panel-header">
              <h2>回测概览</h2>
            </div>
            <div className="panel-body">
              <div className="overview-grid">
                <div className="metric-card">
                  <div className="metric-label">总收益率</div>
                  <div className="metric-value positive">12.56%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">年化收益率</div>
                  <div className="metric-value positive">8.32%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">最大回撤</div>
                  <div className="metric-value negative">-4.21%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">夏普比率</div>
                  <div className="metric-value">1.85</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">胜率</div>
                  <div className="metric-value">62.3%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">交易次数</div>
                  <div className="metric-value">156</div>
                </div>
              </div>
            </div>
          </div>
          
          {/* 绩效分析 */}
          <div className="panel">
            <div className="panel-header">
              <h2>绩效分析</h2>
            </div>
            <div className="panel-body">
              <div className="chart-container">
                <div ref={returnChartRef} className="chart"></div>
              </div>
            </div>
          </div>
          
          {/* 交易详情和风险分析 */}
          <div className="grid-layout">
            {/* 交易详情 */}
            <div className="panel">
              <div className="panel-header">
                <h2>交易详情</h2>
              </div>
              <div className="panel-body">
                <div className="table-container">
                  <table className="data-table">
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
                      {trades.map(trade => (
                        <tr key={trade.id}>
                          <td>{trade.date}</td>
                          <td>{trade.symbol}</td>
                          <td>{trade.type}</td>
                          <td>{trade.price}</td>
                          <td>{trade.quantity}</td>
                          <td className={trade.profit >= 0 ? 'positive' : 'negative'}>
                            {trade.profit >= 0 ? '+' : ''}{trade.profit}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            
            {/* 风险分析 */}
            <div className="panel">
              <div className="panel-header">
                <h2>风险分析</h2>
              </div>
              <div className="panel-body">
                <div className="risk-metrics">
                  <div className="risk-item">
                    <div className="risk-label">波动率</div>
                    <div className="risk-value">6.8%</div>
                  </div>
                  <div className="risk-item">
                    <div className="risk-label">索提诺比率</div>
                    <div className="risk-value">2.1</div>
                  </div>
                  <div className="risk-item">
                    <div className="risk-label">卡尔马比率</div>
                    <div className="risk-value">1.97</div>
                  </div>
                  <div className="risk-item">
                    <div className="risk-label">信息比率</div>
                    <div className="risk-value">0.75</div>
                  </div>
                </div>
                <div className="chart-container small">
                  <div ref={riskChartRef} className="chart"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BacktestResults;