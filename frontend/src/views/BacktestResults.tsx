/**
 * 回测结果页面组件
 * 功能：展示回测任务列表和详细的回测结果，包括概览、绩效分析、交易详情和风险分析
 */
import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Table } from 'antd';
import type { TableProps } from 'antd';
import * as echarts from 'echarts';
import { backtestApi } from '../api';
import { generateBacktestReportHtml } from '../utils/exportBacktest';
import '../styles/BacktestResults.css';
import { useTranslation } from 'react-i18next';
import BacktestConfig from './BacktestConfig';
import ErrorBoundary from '../components/ErrorBoundary';
import dayjs from 'dayjs';


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
  strategy_config?: any; // Add strategy_config
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
  
  // 交易表格分页和排序状态
  const [tableParams, setTableParams] = useState<TableProps<Trade>['pagination']>({
    current: 1,
    pageSize: 10,
    showSizeChanger: true,
    pageSizeOptions: ['10', '20', '50', '100'],
  });

  // 回测指标
  const [metrics, setMetrics] = useState<MetricItem[]>([]);

  // 加载状态
  const [loading, setLoading] = useState<boolean>(false);

  // 是否显示回测配置页面
  const [showConfig, setShowConfig] = useState<boolean>(false);
  
  // 从路由状态获取策略信息
  const location = useLocation();
  const [initialStrategy, setInitialStrategy] = useState<any>(null);

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

  // 表格列定义
  const columns: TableProps<Trade>['columns'] = [
    {
      title: t('entry_time'),
      dataIndex: 'EntryTime',
      key: 'EntryTime',
      sorter: (a, b) => new Date(a.EntryTime).getTime() - new Date(b.EntryTime).getTime(),
    },
    {
      title: t('exit_time'),
      dataIndex: 'ExitTime',
      key: 'ExitTime',
      sorter: (a, b) => new Date(a.ExitTime).getTime() - new Date(b.ExitTime).getTime(),
    },
    {
      title: t('direction'),
      dataIndex: 'Direction',
      key: 'Direction',
      filters: [
        { text: 'LONG', value: 'LONG' },
        { text: 'SHORT', value: 'SHORT' },
      ],
      onFilter: (value, record) => record.Direction.indexOf(value as string) === 0,
    },
    {
      title: t('entry_price'),
      dataIndex: 'EntryPrice',
      key: 'EntryPrice',
      sorter: (a, b) => a.EntryPrice - b.EntryPrice,
      render: (value) => typeof value === 'number' ? value.toFixed(2) : value,
    },
    {
      title: t('exit_price'),
      dataIndex: 'ExitPrice',
      key: 'ExitPrice',
      sorter: (a, b) => a.ExitPrice - b.ExitPrice,
      render: (value) => typeof value === 'number' ? value.toFixed(2) : value,
    },
    {
      title: t('position_size'),
      dataIndex: 'Size',
      key: 'Size',
      sorter: (a, b) => a.Size - b.Size,
    },
    {
      title: t('pnl'),
      dataIndex: 'PnL',
      key: 'PnL',
      sorter: (a, b) => a.PnL - b.PnL,
      render: (value) => (
        <span className={value >= 0 ? 'positive' : 'negative'}>
          {value >= 0 ? '+' : ''}{typeof value === 'number' ? value.toFixed(2) : value}
        </span>
      ),
    },
    {
      title: t('return_pct'),
      dataIndex: 'ReturnPct',
      key: 'ReturnPct',
      sorter: (a, b) => a.ReturnPct - b.ReturnPct,
      render: (value) => (
        <span className={value >= 0 ? 'positive' : 'negative'}>
          {value >= 0 ? '+' : ''}{typeof value === 'number' ? value.toFixed(2) : value}%
        </span>
      ),
    },
  ];

  // 处理表格变更
  const handleTableChange: TableProps<Trade>['onChange'] = (pagination) => {
    setTableParams({
      ...pagination,
    });
  };

  // 监听窗口大小变化，调整图表大小
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

  // 监听路由状态，检查是否需要显示配置页面并传入策略信息
  useEffect(() => {
    if (location.state) {
      const { strategy, showConfig: showConfigFromState } = location.state;
      if (showConfigFromState) {
        setShowConfig(true);
        setInitialStrategy(strategy);
      }
      // 清除路由状态，避免刷新页面后重复显示
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

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

  // 切换到回测配置页面
  const handleNewBacktest = () => {
    setShowConfig(true);
  };

  // 从回测配置页面返回
  const handleBack = () => {
    setShowConfig(false);
  };

  // 执行回测后返回列表页面并刷新数据
  const handleRunBacktest = () => {
    setShowConfig(false);
    loadBacktestList();
  };

  /**
   * 导出回测报告
   */
  const handleExportReport = async (taskId?: string) => {
    let dataToExport = backtestResult;

    // 如果指定了 taskId 且不是当前选中的任务，或者当前没有 backtestResult，则尝试加载
    if (taskId && taskId !== selectedTaskId) {
       // 提示用户正在准备导出
       const loadingMsg = document.createElement('div');
       loadingMsg.id = 'export-loading-msg';
       loadingMsg.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,0.7);color:#fff;padding:12px 24px;border-radius:4px;z-index:9999;';
       loadingMsg.innerText = '正在准备导出数据...';
       document.body.appendChild(loadingMsg);

       try {
         const response = await backtestApi.getBacktestDetail(taskId);
         if (response && response.status === 'success') {
           dataToExport = response;
         }
       } catch (error) {
         console.error('加载导出数据失败:', error);
       } finally {
         const msg = document.getElementById('export-loading-msg');
         if (msg) document.body.removeChild(msg);
       }
    }

    if (!dataToExport) return;
    
    try {
      const htmlContent = generateBacktestReportHtml(dataToExport);
      const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `backtest_report_${dataToExport.strategy_name}_${dayjs().format('YYYYMMDDHHmmss')}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('导出报告失败:', error);
    }
  };

  // 如果显示回测配置页面，使用错误边界包裹渲染
  if (showConfig) {
    return (
      <ErrorBoundary>
        <BacktestConfig 
          onBack={handleBack} 
          onRunBacktest={handleRunBacktest} 
          strategy={initialStrategy} // 传递策略信息
        />
      </ErrorBoundary>
    );
  }

  // 否则渲染回测列表和详情
  return (
    <div className="backtest-results-container">
      <h1>{t('strategy_backtest')}</h1>
      
      <div className="backtest-layout">
        {/* 左侧：回测任务列表 */}
        <div className="backtest-list">
          <div className="panel">
            <div className="panel-header">
              <h2>{t('backtest_tasks')}</h2>
              <button className="btn btn-primary btn-sm" onClick={handleNewBacktest}>
                {t('new_backtest')}
              </button>
            </div>
            <div className="panel-body">
              {loading ? (
                <div className="loading">加载中...</div>
              ) : backtestTasks.length === 0 ? (
                <div className="empty">{t('no_backtest_tasks')}</div>
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
                        className="btn btn-primary btn-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleExportReport(task.id);
                        }}
                        style={{ marginBottom: '4px' }}
                      >
                        {t('export')}
                      </button>
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
              {/* 配置信息 */}
              <div className="panel">
                <div className="panel-header">
                  <h2>{t('config_info')}</h2>
                </div>
                <div className="panel-body">
                  <div className="config-grid">
                    <div className="config-item">
                      <span className="label">{t('strategy_name')}:</span>
                      <span className="value">{backtestResult.strategy_name}</span>
                    </div>
                    {backtestResult.backtest_config?.symbols && (
                      <div className="config-item">
                        <span className="label">{t('trading_symbols')}:</span>
                        <span className="value">
                          {Array.isArray(backtestResult.backtest_config.symbols) 
                            ? backtestResult.backtest_config.symbols.join(', ') 
                            : backtestResult.backtest_config.symbols}
                        </span>
                      </div>
                    )}
                    <div className="config-item">
                      <span className="label">{t('time_range')}:</span>
                      <span className="value">
                        {backtestResult.backtest_config?.start_time} ~ {backtestResult.backtest_config?.end_time}
                      </span>
                    </div>
                    <div className="config-item">
                      <span className="label">{t('interval')}:</span>
                      <span className="value">{backtestResult.backtest_config?.interval}</span>
                    </div>
                    <div className="config-item">
                      <span className="label">{t('initial_cash')}:</span>
                      <span className="value">{backtestResult.backtest_config?.initial_cash}</span>
                    </div>
                    <div className="config-item">
                      <span className="label">{t('commission_rate')}:</span>
                      <span className="value">{backtestResult.backtest_config?.commission}</span>
                    </div>
                    {backtestResult.strategy_config?.params && (
                      <div className="config-item full-width">
                        <span className="label">{t('strategy_params')}:</span>
                        <pre className="value params-json">
                          {JSON.stringify(backtestResult.strategy_config.params, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* 回测概览 */}
              <div className="panel">
                <div className="panel-header">
                  <h2>{t('backtest_overview')}</h2>
                </div>
                <div className="panel-body">
                  <div className="overview-grid">
                    {getKeyMetrics().map((metric, index) => (
                      <div key={index} className="metric-card">
                        <div className="metric-label">{metric.cn_name}</div>
                        <div className={`metric-value ${metric.name === 'Return [%]' && Number(metric.value) >= 0 ? 'positive' : ''} ${metric.name === 'Return [%]' && Number(metric.value) < 0 ? 'negative' : ''}`}>
                          {typeof metric.value === 'number' ? `${metric.value.toFixed(2)}%` : metric.value}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              
              {/* 绩效分析 */}
              <div className="panel">
                <div className="panel-header">
                  <h2>{t('performance_analysis')}</h2>
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
                    <h2>{t('trade_details')}</h2>
                  </div>
                  <div className="panel-body">
                    <div className="table-container">
                      <Table
                        columns={columns}
                        dataSource={trades}
                        rowKey={(_, index) => index?.toString() || ''}
                        pagination={tableParams}
                        onChange={handleTableChange}
                        size="small"
                        className="data-table"
                      />
                    </div>
                  </div>
                </div>
                
                {/* 风险分析 */}
                <div className="panel">
                  <div className="panel-header">
                    <h2>{t('risk_analysis')}</h2>
                  </div>
                  <div className="panel-body">
                    <div className="risk-metrics">
                      {metrics.filter(metric => ['波动率', '索提诺比率', '卡尔马比率', '信息比率'].includes(metric.cn_name)).map((metric, index) => (
                        <div key={index} className="risk-item">
                          <div className="risk-label">{metric.cn_name}</div>
                          <div className="risk-value">{typeof metric.value === 'number' ? metric.value.toFixed(2) : metric.value}</div>
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
                <div className="loading">{t('loading')}</div>
              ) : (
                <div className="empty">{t('select_backtest_task')}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BacktestResults;