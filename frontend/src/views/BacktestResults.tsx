/**
 * 回测结果页面组件
 * 功能：展示回测任务列表和详细的回测结果，包括概览、绩效分析、交易详情和风险分析
 */
import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
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
  Symbol: string;
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

import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';

// ... (existing imports)
// 回测指标类型定义
interface MetricItem {
  name: string;
  key?: string; // 添加key字段，用于标识
  value: any;
  description: string;
  type?: string; // 新增类型字段，用于区分显示格式
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
  
  // 路由导航
  const navigate = useNavigate();

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
  const [listLoading, setListLoading] = useState<boolean>(false);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);

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
    setListLoading(true);
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
      setListLoading(false);
    }
  };

  /**
   * 加载回测结果详情
   * @param taskId 任务ID
   */
  const loadBacktestDetail = async (taskId: string) => {
    setDetailLoading(true);
    try {
      const response = await backtestApi.getBacktestDetail(taskId);
      if (response && response.status === 'success') {
        setBacktestResult(response);
        setTrades(response.trades || []);
        setMetrics(response.metrics || []);
        // 图表更新现在由useEffect处理，不再这里直接调用
      }
    } catch (error) {
      console.error('加载回测结果详情失败:', error);
    } finally {
      // 添加一个小的延迟，避免闪烁太快
      setTimeout(() => {
        setDetailLoading(false);
      }, 300);
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
    
    // 1. 数据预处理：过滤无效数据并统一格式
    // 我们需要确保 X轴 (时间) 和 Y轴 (权益) 的数据点是一一对应的
    const validData = equityCurve.map(item => {
      let dateStr = '';
      
      // 尝试获取时间字段
      if (item.datetime) {
        dateStr = item.datetime;
      } else if (item.Open_time) {
        dateStr = item.Open_time;
      } else if (item.timestamp) {
        dateStr = item.timestamp;
      } else if (item.time) {
        dateStr = item.time;
      }

      // 处理时间戳 (如果是数字)
      if (typeof dateStr === 'number') {
        dateStr = dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss');
      }

      // 获取权益值
      const equityVal = item.Equity;

      return {
        date: dateStr,
        value: equityVal
      };
    }).filter(item => item.date && (typeof item.value === 'number')); // 过滤掉没有时间或权益值的数据

    // 2. 分离轴数据
    const dates = validData.map(item => item.date);
    const equity = validData.map(item => item.value);
    
    const option = {
      backgroundColor: '#ffffff',
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
        type: 'value',
        scale: true // 自动缩放Y轴，避免从0开始导致波动看不清
      },
      // 添加缩放功能，与导出报告保持一致
      dataZoom: [
        { type: 'inside' },
        { type: 'slider' }
      ],
      series: [{
        data: equity,
        type: 'line',
        smooth: true,
        showSymbol: false, // 数据量大时不显示点
        lineStyle: {
          color: '#4a6cf7',
          width: 2
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
    
    // 查找最大回撤指标，使用原始key匹配
    const maxDrawdownMetric = metrics.find(metric => metric.key === 'Max. Drawdown [%]');
    const maxDrawdown = maxDrawdownMetric ? maxDrawdownMetric.value : 0;
    
    const option = {
      backgroundColor: '#ffffff',
      title: {
        text: maxDrawdownMetric ? maxDrawdownMetric.name : '最大回撤',
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
        data: [maxDrawdownMetric ? maxDrawdownMetric.name : '最大回撤']
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


  // 表格列定义
  const columns: TableProps<Trade>['columns'] = [
    {
      title: t('symbol'),
      dataIndex: 'Symbol',
      key: 'Symbol',
      filters: [],
      onFilter: (value, record) => record.Symbol === value,
    },
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
        { text: '多单', value: '多单' },
        { text: '空单', value: '空单' },
      ],
      onFilter: (value, record) => record.Direction === value,
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

  // 组件挂载时加载回测列表
  useEffect(() => {
    loadBacktestList();
    window.addEventListener('resize', handleResize);

    // 组件卸载时清理
    return () => {
      window.removeEventListener('resize', handleResize);
      returnChart.current?.dispose();
      riskChart.current?.dispose();
    };
  }, []);

  // 监听数据变化，初始化和更新图表
  useEffect(() => {
    // 只有当有数据且加载完成时才处理图表
    if (backtestResult && !detailLoading) {
      // 确保DOM已经渲染
      setTimeout(() => {
        // 初始化收益率曲线图表
        if (returnChartRef.current) {
          if (!returnChart.current) {
            returnChart.current = echarts.init(returnChartRef.current);
          }
          // 只有在实例存在时才更新数据
          updateReturnChart(backtestResult.equity_curve);
        }

        // 初始化风险分析图表
        if (riskChartRef.current) {
          if (!riskChart.current) {
            riskChart.current = echarts.init(riskChartRef.current);
          }
          // 只有在实例存在时才更新数据
          updateRiskChart(backtestResult.metrics);
        }
      }, 0);
    }
  }, [backtestResult, detailLoading]);

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
   * 根据指标类型渲染不同的显示格式
   * @param metric 指标对象
   * @returns 格式化后的指标值
   */
  const renderMetricValue = (metric: MetricItem) => {
    const { value, type, key } = metric;
    
    // 如果没有类型信息，使用默认行为
    if (!type) {
      return typeof value === 'number' ? `${value.toFixed(2)}%` : value;
    }
    
    // 根据类型渲染不同格式
    switch (type) {
      case 'percentage':
        return typeof value === 'number' ? `${value.toFixed(2)}%` : value;
      case 'currency':
        return typeof value === 'number' ? `$${value.toFixed(2)}` : value;
      case 'number':
        if (key === '# Trades') {
          // 交易次数应该是整数
          return typeof value === 'number' ? Math.round(value) : value;
        }
        return typeof value === 'number' ? value.toFixed(2) : value;
      case 'datetime':
      case 'duration':
      case 'string':
      default:
        return value;
    }
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
   * 跳转到回放页面
   * @param taskId 任务ID
   */
  const handleReplay = (taskId: string) => {
    navigate(`/backtest/replay/${taskId}`);
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
              {listLoading ? (
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
                      <div className="task-date">
                        {(() => {
                          // 尝试解析日期格式 YYYYMMDD_HHmmss
                          if (task.created_at && task.created_at.includes('_')) {
                            const parts = task.created_at.split('_');
                            if (parts.length === 2) {
                              const datePart = parts[0];
                              const timePart = parts[1];
                              if (datePart.length === 8 && timePart.length >= 6) {
                                return `${datePart.substring(0, 4)}-${datePart.substring(4, 6)}-${datePart.substring(6, 8)} ${timePart.substring(0, 2)}:${timePart.substring(2, 4)}:${timePart.substring(4, 6)}`;
                              }
                            }
                          }
                          // 如果不是标准格式，直接显示
                          return task.created_at;
                        })()}
                      </div>
                      <div className="task-return">
                        {task.total_return !== undefined ? `${task.total_return}%` : 'N/A'}
                      </div>
                    </div>
                    <div className="task-actions">
                      <button 
                        className="btn btn-success btn-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleReplay(task.id);
                        }}
                        style={{ marginBottom: '4px' }}
                      >
                        {t('replay')}
                      </button>
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
                    {metrics.map((metric, index) => (
                      <div key={index} className="metric-card">
                        <div className="metric-label">
                          {metric.name}
                          {metric.description && (
                            <Tooltip title={metric.description}>
                              <InfoCircleOutlined style={{ marginLeft: 4, color: '#999', fontSize: 12 }} />
                            </Tooltip>
                          )}
                        </div>
                        <div className={`metric-value ${metric.key === 'Return [%]' && Number(metric.value) >= 0 ? 'positive' : ''} ${metric.key === 'Return [%]' && Number(metric.value) < 0 ? 'negative' : ''}`}>
                          {renderMetricValue(metric)}
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
              
              {/* 风险分析 */}
              <div className="panel">
                <div className="panel-header">
                  <h2>{t('risk_analysis')}</h2>
                </div>
                <div className="panel-body">
                  <div className="chart-container" style={{ width: '100%', height: '300px' }}>
                    <div ref={riskChartRef} className="chart" />
                  </div>
                </div>
              </div>
              
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
                      rowKey={(record) => record.ID || `${record.EntryTime}-${record.ExitTime}-${record.Direction}-${record.EntryPrice}`}
                      pagination={tableParams}
                      onChange={handleTableChange}
                      size="small"
                      className="data-table"
                    />
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-detail">
              {detailLoading ? (
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