/**
 * 回测结果页面组件
 * 功能：展示回测任务列表和详细的回测结果，包括概览、绩效分析、交易详情和风险分析
 */
import { useState, useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { backtestApi } from '../api';
import '../styles/BacktestResults.css';
import { useTranslation } from 'react-i18next';


// 回测任务类型定义
interface BacktestTask {
  id: string;
  strategy_name: string;
  created_at: string;
  status: string;
  total_return?: number;
  max_drawdown?: number;
}

// 交易记录类型定义
interface Trade {
  EntryTime: string;
  ExitTime: string;
  Duration: string;
  Direction: string;
  EntryPrice: number;
  ExitPrice: number;
  Size: number;
  PnL: number;
  ReturnPct: number;
  Tag?: string;
  ID?: string;
}

// 回测指标类型定义
interface MetricItem {
  name: string;
  value: any;
  cn_name: string;
  en_name: string;
  description: string;
}

// 回测结果类型定义
interface BacktestResult {
  task_id: string;
  status: string;
  message: string;
  strategy_name: string;
  backtest_config: any;
  metrics: MetricItem[];
  trades: Trade[];
  equity_curve: any[];
  strategy_data: any[];
}

const BacktestResults = () => {
  // 回测任务数据
  const [backtestTasks, setBacktestTasks] = useState<BacktestTask[]>([]);

  // 选中的回测任务ID
  const [selectedTaskId, setSelectedTaskId] = useState<string>('');

  // 回测结果详情
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);

  // 国际化支持
  const { t } = useTranslation();

  // 交易数据
  const [trades, setTrades] = useState<Trade[]>([]);

  // 回测指标
  const [metrics, setMetrics] = useState<MetricItem[]>([]);

  // 加载状态
  const [loading, setLoading] = useState<boolean>(false);

  // 图表引用
  const returnChartRef = useRef<HTMLDivElement>(null);
  const riskChartRef = useRef<HTMLDivElement>(null);
  const returnChart = useRef<echarts.ECharts | null>(null);
  const riskChart = useRef<echarts.ECharts | null>(null);

  /**
   * 加载回测任务列表
   */
  const loadBacktestList = async () => {
    setLoading(true);
    try {
      const response = await backtestApi.getBacktestList();
      if (response.backtests && Array.isArray(response.backtests)) {
        setBacktestTasks(response.backtests);
        // 如果有回测任务，默认选中第一个
        if (response.backtests.length > 0 && !selectedTaskId) {
          selectTask(response.backtests[0].id);
        }
      }
    } catch (error) {
      console.error('加载回测任务列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 加载回测结果详情
   * @param taskId 任务ID
   */
  const loadBacktestDetail = async (taskId: string) => {
    setLoading(true);
    try {
      const response = await backtestApi.getBacktestDetail(taskId);
      if (response && response.status === 'success') {
        setBacktestResult(response);
        setTrades(response.trades || []);
        setMetrics(response.metrics || []);
        // 更新收益率曲线和风险分析图表
        updateReturnChart(response.equity_curve);
        updateRiskChart(response.metrics);
      }
    } catch (error) {
      console.error('加载回测结果详情失败:', error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 选择回测任务
   * @param taskId 任务ID
   */
  const selectTask = (taskId: string) => {
    setSelectedTaskId(taskId);
    loadBacktestDetail(taskId);
  };

  /**
   * 更新收益率曲线图表
   */
  const updateReturnChart = (equityCurve: any[]) => {
    if (!returnChart.current || !equityCurve || equityCurve.length === 0) return;
    
    // 准备图表数据
    const dates = equityCurve.map(item => {
      if (typeof item.datetime === 'string') {
        return item.datetime;
      } else if (typeof item.Open_time === 'string') {
        return item.Open_time;
      }
      return '';
    }).filter(date => date !== '');
    
    const equity = equityCurve.map(item => item.Equity || 0);
    
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
        formatter: '{b}: {c}'
      },
      xAxis: {
        type: 'category',
        data: dates
      },
      yAxis: {
        type: 'value'
      },
      series: [{
        data: equity,
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
   * 更新风险分析图表
   */
  const updateRiskChart = (metrics: MetricItem[]) => {
    if (!riskChartRef.current || !metrics || metrics.length === 0) return;
    
    // 查找最大回撤指标
    const maxDrawdownMetric = metrics.find(metric => metric.cn_name === '最大回撤');
    const maxDrawdown = maxDrawdownMetric ? maxDrawdownMetric.value : 0;
    
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
        data: ['最大回撤']
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: '{value}%'
        }
      },
      series: [{
        data: [maxDrawdown],
        type: 'bar',
        itemStyle: {
          color: '#f87272'
        }
      }]
    };
    
    riskChart.current?.setOption(option);
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
        data: []
      },
      yAxis: {
        type: 'value'
      },
      series: [{
        data: [],
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
        data: ['最大回撤']
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: '{value}%'
        }
      },
      series: [{
        data: [0],
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

  // 组件挂载时初始化图表和加载数据
  useEffect(() => {
    initReturnChart();
    initRiskChart();
    loadBacktestList();
    window.addEventListener('resize', handleResize);

    // 组件卸载时清理
    return () => {
      window.removeEventListener('resize', handleResize);
      returnChart.current?.dispose();
      riskChart.current?.dispose();
    };
  }, []);

  // 选中任务变化时加载详情
  useEffect(() => {
    if (selectedTaskId) {
      loadBacktestDetail(selectedTaskId);
    }
  }, [selectedTaskId]);

  /**
   * 获取关键指标
   * @returns 关键指标列表
   */
  const getKeyMetrics = () => {
    if (!metrics || metrics.length === 0) {
      return [];
    }
    
    // 提取关键指标
    const keyMetricNames = [
      '总收益率', '年化收益率', '最大回撤', '夏普比率', '胜率', '交易次数'
    ];
    
    return metrics.filter(metric => keyMetricNames.includes(metric.cn_name));
  };

  /**
   * 删除回测结果
   * @param taskId 任务ID
   */
  const deleteBacktest = async (taskId: string) => {
    try {
      await backtestApi.deleteBacktest(taskId);
      // 重新加载回测任务列表
      loadBacktestList();
      // 如果删除的是当前选中的任务，清空选中状态
      if (selectedTaskId === taskId) {
        setSelectedTaskId('');
        setBacktestResult(null);
        setTrades([]);
        setMetrics([]);
      }
    } catch (error) {
      console.error('删除回测结果失败:', error);
    }
  };

  return (
    <div className="backtest-results-container">
      <h1>{t('strategy_backtest')}</h1>
      
      <div className="backtest-layout">
        {/* 左侧：回测任务列表 */}
        <div className="backtest-list">
          <div className="panel">
            <div className="panel-header">
              <h2>回测任务</h2>
              <button className="btn btn-primary btn-sm">新建回测</button>
            </div>
            <div className="panel-body">
              {loading ? (
                <div className="loading">加载中...</div>
              ) : backtestTasks.length === 0 ? (
                <div className="empty">暂无回测任务</div>
              ) : (
                backtestTasks.map(task => (
                  <div 
                    key={task.id}
                    className={`backtest-task-item ${selectedTaskId === task.id ? 'active' : ''}`}
                    onClick={() => selectTask(task.id)}
                  >
                    <div className="task-header">
                      <div className="task-name">{task.strategy_name}</div>
                      <div className={`task-status ${task.status}`}>{task.status}</div>
                    </div>
                    <div className="task-meta">
                      <div className="task-date">{task.created_at}</div>
                      <div className="task-return">
                        {task.total_return !== undefined ? `${task.total_return}%` : 'N/A'}
                      </div>
                    </div>
                    <div className="task-actions">
                      <button 
                        className="btn btn-danger btn-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteBacktest(task.id);
                        }}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
        
        {/* 右侧：回测结果详情 */}
        <div className="backtest-detail">
          {selectedTaskId && backtestResult ? (
            <>
              {/* 回测概览 */}
              <div className="panel">
                <div className="panel-header">
                  <h2>回测概览</h2>
                </div>
                <div className="panel-body">
                  <div className="overview-grid">
                    {getKeyMetrics().map((metric, index) => (
                      <div key={index} className="metric-card">
                        <div className="metric-label">{metric.cn_name}</div>
                        <div className={`metric-value ${metric.name === 'Return [%]' && Number(metric.value) >= 0 ? 'positive' : ''} ${metric.name === 'Return [%]' && Number(metric.value) < 0 ? 'negative' : ''}`}>
                          {typeof metric.value === 'number' ? `${metric.value}%` : metric.value}
                        </div>
                      </div>
                    ))}
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
                            <th>入场时间</th>
                            <th>出场时间</th>
                            <th>方向</th>
                            <th>入场价格</th>
                            <th>出场价格</th>
                            <th>仓位大小</th>
                            <th>收益</th>
                            <th>收益率</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trades.length === 0 ? (
                            <tr>
                              <td colSpan={8} className="empty">暂无交易记录</td>
                            </tr>
                          ) : (
                            trades.map((trade, index) => (
                              <tr key={index}>
                                <td>{trade.EntryTime}</td>
                                <td>{trade.ExitTime}</td>
                                <td>{trade.Direction}</td>
                                <td>{trade.EntryPrice}</td>
                                <td>{trade.ExitPrice}</td>
                                <td>{trade.Size}</td>
                                <td className={trade.PnL >= 0 ? 'positive' : 'negative'}>
                                  {trade.PnL >= 0 ? '+' : ''}{trade.PnL}
                                </td>
                                <td className={trade.ReturnPct >= 0 ? 'positive' : 'negative'}>
                                  {trade.ReturnPct >= 0 ? '+' : ''}{trade.ReturnPct}%
                                </td>
                              </tr>
                            ))
                          )}
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
                      {metrics.filter(metric => ['波动率', '索提诺比率', '卡尔马比率', '信息比率'].includes(metric.cn_name)).map((metric, index) => (
                        <div key={index} className="risk-item">
                          <div className="risk-label">{metric.cn_name}</div>
                          <div className="risk-value">{metric.value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="chart-container small">
                      <div ref={riskChartRef} className="chart"></div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-detail">
              {loading ? (
                <div className="loading">加载中...</div>
              ) : (
                <div className="empty">请选择一个回测任务查看详情</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BacktestResults;