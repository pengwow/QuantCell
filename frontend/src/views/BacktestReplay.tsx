/**
 * 回测回放页面组件
 * 功能：回放回测过程，展示K线图表和交易信号
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Slider, Select, Spin, Alert, message, Table } from 'antd';
import {
  CaretRightOutlined,
  PauseOutlined,
  FastForwardOutlined,
  StopOutlined,
  LeftOutlined
} from '@ant-design/icons';
import { init, dispose, registerLocale, registerOverlay } from 'klinecharts';
// 导入自定义遮盖物组件
import jsonAnnotation from '../extension/jsonAnnotation';
import { backtestApi } from '../api';
import { useTranslation } from 'react-i18next';
import '../styles/BacktestReplay.css';

// 导入AppConfig类型
import type { AppConfig } from '../utils/configLoader';

// 扩展Window接口，添加APP_CONFIG属性
declare global {
  interface Window {
    APP_CONFIG: AppConfig;
  }
}

// 注册语言包
registerLocale('zh-CN', {
  time: '时间：',
  open: '开：',
  high: '高：',
  low: '低：',
  close: '收：',
  volume: '成交量：',
  change: '涨跌：',
  turnover: '成交额：',
  second: '秒',
  minute: '分',
  hour: '时',
  day: '日',
  week: '周',
  month: '月',
  year: '年'
});

registerLocale('en-US', {
  time: 'Time:',
  open: 'Open:',
  high: 'High:',
  low: 'Low:',
  close: 'Close:',
  volume: 'Volume:',
  change: 'Change:',
  turnover: 'Turnover:',
  second: 's',
  minute: 'm',
  hour: 'h',
  day: 'd',
  week: 'w',
  month: 'M',
  year: 'y'
});

const { Option } = Select;

// 货币对信息类型
interface SymbolInfo {
  symbol: string;
  status: string;
  message: string;
}

// 回放数据类型
interface ReplayData {
  klines: any[];
  trades: any[];
  equity_curve: any[];
  strategy_name: string;
  backtest_config: any;
  symbol: string;
  interval: string;
}

// 回测货币对列表数据类型
interface BacktestSymbols {
  symbols: SymbolInfo[];
  total: number;
}

// 播放速度选项
const SPEED_OPTIONS = [
  { label: '0.5x', value: 0.5 },
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '5x', value: 5 },
  { label: '10x', value: 10 },
  { label: '20x', value: 20 }
];

// 交易详情表格列配置
const TRADE_TABLE_COLUMNS = [
  { title: '交易ID', dataIndex: 'trade_id', key: 'trade_id', width: 120 },
  { title: '入场时间', dataIndex: 'EntryTime', key: 'EntryTime' },
  { title: '方向', dataIndex: 'Direction', key: 'Direction', width: 80 },
  { title: '入场价格', dataIndex: 'EntryPrice', key: 'EntryPrice', width: 120 },
  { title: '出场时间', dataIndex: 'ExitTime', key: 'ExitTime' },
  { title: '出场价格', dataIndex: 'ExitPrice', key: 'ExitPrice', width: 120 },
  { title: '盈亏', dataIndex: 'PnL', key: 'PnL', width: 100 }
];

/**
 * 格式化时间戳为可读的日期时间字符串
 * @param timestamp 时间戳（毫秒）
 * @returns 格式化后的日期时间字符串
 */
const formatTimestamp = (timestamp: number | string): string => {
  if (!timestamp) return '';
  
  const ts = typeof timestamp === 'string' ? parseInt(timestamp) : timestamp;
  if (isNaN(ts)) return '';
  
  const date = new Date(ts);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

/**
 * 解析周期字符串为klinecharts需要的格式
 * @param interval 周期字符串，如 '15m', '1h', '1d'
 * @returns 包含span和type的对象
 */
const parseInterval = (interval: string): { span: number; type: any } => {
  // 提取数字部分
  const match = interval.match(/\d+/);
  const span = match ? parseInt(match[0]) : 1;
  
  // 提取时间单位
  const unit = interval.replace(/\d+/, '');
  
  // 映射到klinecharts的类型
  switch (unit.toLowerCase()) {
    case 'm':
      return { span, type: 'minute' as const };
    case 'h':
      return { span, type: 'hour' as const };
    case 'd':
      return { span, type: 'day' as const };
    case 'w':
      return { span, type: 'week' as const };
    case 'mo':
    case 'mth':
      return { span, type: 'month' as const };
    case 'y':
      return { span, type: 'year' as const };
    default:
      return { span: 15, type: 'minute' as const };
  }
};

const BacktestReplay = () => {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  // 回放数据
  const [replayData, setReplayData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 货币对相关状态
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [loadingSymbols, setLoadingSymbols] = useState<boolean>(false);

  // 播放控制状态
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playSpeed, setPlaySpeed] = useState<number>(1);

  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<any>(null);
  const playTimerRef = useRef<number | null>(null);

  /**
   * 加载货币对列表
   */
  const loadSymbols = async () => {
    if (!backtestId) return;
    
    setLoadingSymbols(true);
    setError(null);
    
    try {
      const data: BacktestSymbols = await backtestApi.getBacktestSymbols(backtestId);
      console.log('后端返回的货币对数据:', data);
      
      setSymbols(data.symbols || []);
      
      // 默认选择第一个货币对
      if (data.symbols && data.symbols.length > 0) {
        setSelectedSymbol(data.symbols[0].symbol);
      }
    } catch (err) {
      console.error('加载货币对列表失败:', err);
      message.error('加载货币对列表失败');
    } finally {
      setLoadingSymbols(false);
    }
  };

  /**
   * 加载回放数据
   */
  const loadReplayData = async (symbol?: string) => {
    if (!backtestId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await backtestApi.getReplayData(backtestId, symbol);
      console.log('后端返回的原始数据:', data);
      
      // 映射后端返回的字段名到前端期望的字段名
      const mappedData = {
        klines: data.kline_data || [],
        trades: (data.trade_signals || []).map((trade: any, index: number) => ({
          EntryTime: trade.time || '',
          ExitTime: '', // 后端未返回
          Direction: trade.type === 'buy' ? '多单' : '空单',
          EntryPrice: trade.price || 0,
          ExitPrice: 0, // 后端未返回
          PnL: 0, // 后端未返回
          // 确保trade_id唯一，当后端未返回时使用索引作为fallback
          trade_id: trade.trade_id || `trade-${index}`
        })),
        equity_curve: data.equity_data || [],
        strategy_name: data.metadata?.strategy_name || '',
        backtest_config: data.backtest_config || {},
        symbol: data.metadata?.symbol || 'BTCUSDT',
        interval: data.metadata?.interval || '15m'
      };
      
      console.log('映射后的数据:', mappedData);
      console.log('K线数据格式:', mappedData.klines.length > 0 ? mappedData.klines[0] : '无数据');
      console.log('K线数据数量:', mappedData.klines.length);
      
      setReplayData(mappedData);
    } catch (err) {
      console.error('加载回放数据失败:', err);
      setError('加载回放数据失败，请稍后重试');
      message.error('加载回放数据失败');
    } finally {
      setLoading(false);
    }
  };

  /**
   * 处理货币对切换
   */
  const handleSymbolChange = (value: string) => {
    setSelectedSymbol(value);
    // 重置播放状态
    handleStop();
    // 加载新货币对的回放数据
    loadReplayData(value);
  };

  /**
   * 初始化图表 - 参考ChartPage.tsx的实现
   */
  const initChart = () => {
    if (!chartRef.current || !replayData) return;

    console.log('开始初始化图表...');
    console.log('可用的K线数据:', replayData.klines.length);
    console.log('图表容器:', chartRef.current);

    // 确保容器有正确的尺寸
    if (chartRef.current) {
      chartRef.current.style.width = '100%';
      chartRef.current.style.height = '100%';
      chartRef.current.style.minHeight = '600px';
    }

    // 如果已有实例，先销毁
    if (chartInstance.current) {
      console.log('销毁现有图表实例...');
      dispose(chartRef.current);
      chartInstance.current = null;
    }

    // 初始化图表
    try {
      console.log('创建新图表实例...');
      // 获取系统配置的语言
      const language = window.APP_CONFIG?.language || 'zh-CN';
      console.log('使用语言:', language);
      
      // 注册自定义遮盖物组件
      if (typeof registerOverlay === 'function') {
        // 注册jsonAnnotation自定义遮盖物组件
        registerOverlay(jsonAnnotation);
      }
      
      const chart = init(chartRef.current, { 
        locale: language
      });
      chartInstance.current = chart as any;

      // 设置图表配置
      if (chart) {
        console.log('图表实例创建成功:', chart);
        
        // 设置基本样式
        chart.setStyles({
          candle: {
            tooltip: {
              showRule: 'always',
              showType: 'standard'
            }
          }
        });

        // 设置交易对信息
        const symbol = replayData.symbol || 'BTC/USDT';
        chart.setSymbol({ ticker: symbol.replace('USDT', '/USDT') });
        
        // 设置周期
        const interval = replayData.interval || '15m';
        const periodInfo = parseInterval(interval);
        chart.setPeriod({ span: periodInfo.span, type: periodInfo.type });

        // 参考ChartPage.tsx，使用setDataLoader方法
        console.log('设置数据加载器...');
        chart.setDataLoader({
          getBars: (params: any) => {
            console.log('数据加载器回调被调用，当前索引:', currentIndex);
            // 返回当前索引之前的所有K线数据
            const currentKlines = replayData.klines.slice(0, currentIndex + 1);
            console.log('返回的K线数据数量:', currentKlines.length);
            params.callback(currentKlines);
          }
        });

        // 初始加载数据
        console.log('初始加载数据...');
        if (replayData.klines && replayData.klines.length > 0) {
          const initialKlines = replayData.klines.slice(0, 1);
          console.log('初始K线数据:', initialKlines);
          
          // 触发数据加载
          chart.setDataLoader({
            getBars: (params: any) => {
              params.callback(initialKlines);
            }
          });
        }

        // 初始调整图表大小
        chart.resize();
      }
    } catch (error) {
      console.error('初始化图表失败:', error);
    }
  };



  /**
   * 更新图表数据 - 结合LoadMore.tsx和Update.tsx的逻辑
   */
  const updateChart = (index: number) => {
    if (!chartInstance.current || !replayData || !replayData.klines || replayData.klines.length === 0) return;

    console.log('更新图表数据，当前索引:', index);
    
    try {
      const chart = chartInstance.current;
      
      // 限制可见K线数量，只显示最近100条，确保图表能完整显示
      const visibleKlineCount = 100;
      const startIndex = Math.max(0, index - visibleKlineCount + 1);
      const endIndex = index + 1;
      
      // 获取当前可见范围内的K线数据
      const currentKlines = replayData.klines.slice(startIndex, endIndex);
      console.log('更新的K线数据数量:', currentKlines.length, '从索引', startIndex, '到', endIndex - 1);
      
      // 重新设置数据加载器并触发数据更新
      console.log('更新数据加载器...');
      chart.setDataLoader({
        getBars: (params: any) => {
          params.callback(currentKlines);
        }
      });

      // 强制触发图表重新渲染
      chart.resize();

      // 添加交易标记，传入可见范围信息
      const currentKline = replayData.klines[index];
      if (currentKline) {
        // 计算可见时间范围
        const visibleStartTime = replayData.klines[startIndex]?.timestamp || 0;
        const visibleEndTime = replayData.klines[endIndex - 1]?.timestamp || 0;
        
        addTradeMarkers(chart, currentKline, visibleStartTime, visibleEndTime);
      }
    } catch (error) {
      console.error('更新图表数据失败:', error);
    }
  };

  /**
   * 添加交易标记
   * @param chart 图表实例
   * @param formattedKline 当前格式化的K线数据
   * @param visibleStartTime 可见范围起始时间
   * @param visibleEndTime 可见范围结束时间
   */
  const addTradeMarkers = (chart: any, formattedKline: any, visibleStartTime: number, visibleEndTime: number) => {
    if (!replayData) return;
    
    const currentTime = formattedKline.timestamp;
    if (!currentTime || !replayData.trades) return;

    // 清除之前的交易标记
    if (typeof chart.removeOverlay === 'function') {
      // 只清除交易相关的标记，保留其他可能的overlay
      const tradeOverlays = chart.getOverlays({ name: 'jsonAnnotation' }) || [];
      tradeOverlays.forEach((overlay: any) => {
        chart.removeOverlay({ id: overlay.id });
      });
    }

    // 过滤出可见范围内的交易
    const visibleTrades = replayData.trades.filter(trade => {
      const entryTime = new Date(trade.EntryTime).getTime();
      // 只处理入场时间在可见范围内的交易标记
      return entryTime >= visibleStartTime && entryTime <= visibleEndTime;
    });

    // 添加交易标记（包括入场和出场）
    visibleTrades.forEach(trade => {
      const entryTime = new Date(trade.EntryTime).getTime();
      const exitTime = trade.ExitTime ? new Date(trade.ExitTime).getTime() : null;
      
      if (typeof chart.createOverlay === 'function') {
        try {
          // 创建入场标记 - 检查时间是否在可见范围内
          if (entryTime >= visibleStartTime && entryTime <= visibleEndTime) {
            chart.createOverlay({
              name: 'jsonAnnotation',
              // 使用JSON字符串格式的extendData，支持多行文本和颜色
              extendData: JSON.stringify({
                lines: [
                  `${trade.Direction}`,
                  // `入场`,
                  `ID: ${trade.trade_id}`,
                  // `价格: ${trade.EntryPrice}`
                ],
                colors: [
                  trade.Direction === '多单' ? '#26a69a' : '#ef5350',
                  '#000000ff',
                  // '#000000ff'
                ],
                fontSize: 12,
                align: 'left',
              }),
              points: [
                {
                  timestamp: entryTime,
                  value: trade.EntryPrice
                }
              ],
            });
          }
          
          // 如果有出场时间且在当前时间之前，创建出场标记 - 检查时间是否在可见范围内
          if (exitTime && exitTime <= currentTime && exitTime >= visibleStartTime && exitTime <= visibleEndTime) {
            chart.createOverlay({
              name: 'jsonAnnotation',
              // 使用JSON字符串格式的extendData，支持多行文本和颜色
              extendData: JSON.stringify({
                lines: [
                  `${trade.Direction}`,
                  // `出场`,
                  `ID: ${trade.trade_id}`,
                  // `价格: ${trade.ExitPrice}`,
                  `盈亏: ${trade.PnL.toFixed(2)}`
                ],
                colors: [
                  trade.PnL >= 0 ? '#4a6cf7' : '#ff9800',
                  '#ffffff',
                  '#ffffff',
                  '#ffffff',
                  trade.PnL >= 0 ? '#4a6cf7' : '#ff9800'
                ],
                fontSize: 12,
                align: 'left',
              }),
              points: [
                {
                  timestamp: exitTime,
                  value: trade.ExitPrice
                }
              ]
            });
            
            // 添加连接入场和出场的线
            chart.createOverlay({
              name: 'line',
              points: [
                {
                  timestamp: entryTime,
                  value: trade.EntryPrice
                },
                {
                  timestamp: exitTime,
                  value: trade.ExitPrice
                }
              ],
              styles: {
                line: {
                  color: trade.PnL >= 0 ? '#26a69a' : '#ef5350',
                  width: 2,
                  type: 'dashed'
                }
              }
            });
          }
        } catch (err) {
          console.warn('创建交易标记失败:', err);
        }
      }
    });
  };

  /**
   * 播放控制
   */
  const handlePlay = () => {
    if (!replayData || !replayData.klines || replayData.klines.length === 0) return;

    setIsPlaying(true);
    playTimerRef.current = window.setInterval(() => {
      setCurrentIndex(prev => {
        const maxIndex = replayData.klines?.length || 0;
        if (prev >= maxIndex - 1) {
          handlePause();
          return prev;
        }
        return prev + 1;
      });
    }, 1000 / playSpeed);
  };

  /**
   * 暂停播放
   */
  const handlePause = () => {
    setIsPlaying(false);
    if (playTimerRef.current) {
      window.clearInterval(playTimerRef.current);
      playTimerRef.current = null;
    }
  };

  /**
   * 快进
   */
  const handleFastForward = () => {
    if (!replayData || !replayData.klines || replayData.klines.length === 0) return;
    
    setCurrentIndex(prev => {
      const maxIndex = replayData.klines?.length || 0;
      const nextIndex = Math.min(prev + 10, maxIndex - 1);
      return nextIndex;
    });
  };

  /**
   * 停止播放并重置
   */
  const handleStop = () => {
    handlePause();
    setCurrentIndex(0);
  };

  /**
   * 改变播放速度
   */
  const handleSpeedChange = (value: number) => {
    setPlaySpeed(value);
    
    // 如果正在播放，重新开始以应用新速度
    if (isPlaying) {
      handlePause();
      setTimeout(() => {
        handlePlay();
      }, 0);
    }
  };

  /**
   * 进度条变化
   */
  const handleProgressChange = (value: number) => {
    setCurrentIndex(value);
  };

  /**
   * 返回上一页
   */
  const handleBack = () => {
    navigate('/backtest');
  };

  // 组件挂载时加载货币对列表
  useEffect(() => {
    loadSymbols();

    return () => {
      // 清理定时器
      if (playTimerRef.current) {
        window.clearInterval(playTimerRef.current);
      }
      // 清理图表
      if (chartRef.current) {
        dispose(chartRef.current);
      }
    };
  }, [backtestId]);

  // 货币对列表加载完成后，加载第一个货币对的回放数据
  useEffect(() => {
    if (selectedSymbol) {
      loadReplayData(selectedSymbol);
    }
  }, [selectedSymbol]);

  // 数据加载完成后初始化图表
  useEffect(() => {
    if (replayData && chartRef.current) {
      initChart();
    }
  }, [replayData]);

  // 当前索引变化时更新图表
  useEffect(() => {
    if (replayData && chartInstance.current) {
      updateChart(currentIndex);
    }
  }, [currentIndex, replayData]);

  // 渲染加载状态
  if (loading) {
    return (
      <div className="backtest-replay-container">
        <div className="loading-container">
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>{t('loading')}</div>
        </div>
      </div>
    );
  }

  // 渲染错误状态
  if (error) {
    return (
      <div className="backtest-replay-container">
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
          action={
            <Button size="small" onClick={handleBack}>
              {t('back')}
            </Button>
          }
        />
      </div>
    );
  }

  // 渲染回放页面
  return (
    <div className="backtest-replay-container">
      {/* 顶部标题栏 */}
      <div className="replay-header">
        <Button
          icon={<LeftOutlined />}
          onClick={handleBack}
          type="text"
          size="large"
        >
          {t('back')}
        </Button>
        <h1 className="replay-title">
          {t('backtest_replay')} - {replayData?.strategy_name}
        </h1>
      </div>

      {/* 控制栏 */}
      <div className="replay-controls">
        <div className="control-buttons">
          <div className="symbol-selector">
            <span className="symbol-label">{t('symbol')}:</span>
            <Select
              value={selectedSymbol}
              onChange={handleSymbolChange}
              style={{ width: 150 }}
              disabled={loadingSymbols || symbols.length === 0}
              loading={loadingSymbols}
            >
              {symbols.map(symbol => (
                <Option key={symbol.symbol} value={symbol.symbol}>
                  {symbol.symbol}
                </Option>
              ))}
            </Select>
          </div>
          <Button
            type="primary"
            icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={isPlaying ? handlePause : handlePlay}
            size="large"
            disabled={!replayData}
          >
            {isPlaying ? t('pause') : t('play')}
          </Button>
          <Button
            icon={<FastForwardOutlined />}
            onClick={handleFastForward}
            disabled={!replayData || currentIndex >= (replayData?.klines?.length || 0) - 1}
            size="large"
          >
            {t('fast_forward')}
          </Button>
          <Button
            icon={<StopOutlined />}
            onClick={handleStop}
            disabled={currentIndex === 0 || !replayData}
            size="large"
          >
            {t('stop')}
          </Button>
          <div className="speed-control">
            <span className="speed-label">{t('play_speed')}:</span>
            <Select
              value={playSpeed}
              onChange={handleSpeedChange}
              style={{ width: 100 }}
              disabled={!replayData}
            >
              {SPEED_OPTIONS.map(option => (
                <Option key={option.value} value={option.value}>
                  {option.label}
                </Option>
              ))}
            </Select>
          </div>
        </div>

        {/* 进度条 */}
        <div className="progress-bar">
          <span className="progress-label">
            {currentIndex + 1} / {replayData?.klines?.length || 0}
          </span>
          <Slider
            min={0}
            max={(replayData?.klines?.length || 1) - 1}
            value={currentIndex}
            onChange={handleProgressChange}
            style={{ flex: 1, marginLeft: 16, marginRight: 16 }}
            disabled={!replayData}
            tooltip={{
              formatter: (value) => `${value! + 1} / ${replayData?.klines?.length || 0}`
            }}
          />
          <span className="progress-time">
            {formatTimestamp(replayData?.klines?.[currentIndex]?.time || replayData?.klines?.[currentIndex]?.timestamp || '')}
          </span>
        </div>
      </div>

      {/* 图表区域 */}
      <div className="replay-chart-container">
        <div ref={chartRef} className="replay-chart" />
      </div>

      {/* 交易详情表格 */}
      {replayData && (
        <div className="replay-trade-table-container">
          <h3>交易详情</h3>
          <Table
            columns={TRADE_TABLE_COLUMNS}
            dataSource={replayData.trades?.filter(trade => {
              // 获取当前K线的时间戳
              const currentKline = replayData.klines?.[currentIndex];
              if (!currentKline) return false;
              
              const currentTime = currentKline.timestamp || currentKline.time;
              const entryTime = new Date(trade.EntryTime).getTime();
              
              // 只显示当前时间之前的交易
              return entryTime <= currentTime;
            }) || []}
            rowKey="trade_id"
            // 添加分页功能
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条交易`,
              pageSizeOptions: ['5', '10', '20', '50'],
              defaultPageSize: 10,
              size: 'small'
            }}
            // 添加滚动支持
            scroll={{
              x: 800, // 横向滚动条
              y: 300  // 纵向滚动条
            }}
            bordered
            size="middle"
          />
        </div>
      )}
    </div>
  );
};

export default BacktestReplay;
