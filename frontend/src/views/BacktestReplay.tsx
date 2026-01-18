/**
 * 回测回放页面组件
 * 功能：回放回测过程，展示K线图表和交易信号
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Slider, Select, Spin, Alert, message } from 'antd';
import {
  CaretRightOutlined,
  PauseOutlined,
  FastForwardOutlined,
  StopOutlined,
  LeftOutlined
} from '@ant-design/icons';
import { init, dispose, registerLocale } from 'klinecharts';
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

// 播放速度选项
const SPEED_OPTIONS = [
  { label: '0.5x', value: 0.5 },
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '5x', value: 5 },
  { label: '10x', value: 10 },
  { label: '20x', value: 20 }
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

  // 播放控制状态
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playSpeed, setPlaySpeed] = useState<number>(1);

  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<any>(null);
  const playTimerRef = useRef<number | null>(null);

  /**
   * 加载回放数据
   */
  const loadReplayData = async () => {
    if (!backtestId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await backtestApi.getReplayData(backtestId);
      console.log('后端返回的原始数据:', data);
      
      // 映射后端返回的字段名到前端期望的字段名
      const mappedData = {
        klines: data.kline_data || [],
        trades: (data.trade_signals || []).map((trade: any) => ({
          EntryTime: trade.time || '',
          ExitTime: '', // 后端未返回
          Direction: trade.type === 'buy' ? '多单' : '空单',
          EntryPrice: trade.price || 0,
          ExitPrice: 0, // 后端未返回
          PnL: 0, // 后端未返回
          trade_id: trade.trade_id || ''
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
   * 初始化图表 - 参考ChartPage.tsx的实现
   */
  const initChart = () => {
    if (!chartRef.current || !replayData) return;

    console.log('开始初始化图表...');
    console.log('可用的K线数据:', replayData.klines.length);
    console.log('图表容器:', chartRef.current);

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
      
      // 获取当前索引之前的所有K线数据
      const currentKlines = replayData.klines.slice(0, index + 1);
      console.log('更新的K线数据数量:', currentKlines.length);
      
      // 重新设置数据加载器并触发数据更新
      console.log('更新数据加载器...');
      chart.setDataLoader({
        getBars: (params: any) => {
          params.callback(currentKlines);
        }
      });

      // 强制触发图表重新渲染
      chart.resize();

      // 添加交易标记
      const currentKline = replayData.klines[index];
      if (currentKline) {
        addTradeMarkers(chart, currentKline);
      }
    } catch (error) {
      console.error('更新图表数据失败:', error);
    }
  };

  /**
   * 添加交易标记
   */
  const addTradeMarkers = (chart: any, formattedKline: any) => {
    if (!replayData) return;
    
    const currentTime = formattedKline.timestamp;
    if (!currentTime || !replayData.trades) return;

    // 查找当前时刻的交易
    const currentTrades = replayData.trades.filter(trade => {
      const entryTime = new Date(trade.EntryTime).getTime();
      return entryTime <= currentTime;
    });

    // 清除之前的标记
    if (typeof chart.removeOverlay === 'function') {
      chart.removeOverlay();
    }

    // 添加买入/卖出标记
    currentTrades.forEach(trade => {
      const entryTime = new Date(trade.EntryTime).getTime();
      const exitTime = trade.ExitTime ? new Date(trade.ExitTime).getTime() : null;
      
      if (entryTime <= currentTime && (!exitTime || exitTime > currentTime)) {
        // 当前持仓，显示入场标记
        if (typeof chart.createOverlay === 'function') {
          try {
            chart.createOverlay({
              name: 'simpleAnnotation',
              points: [
                {
                  timestamp: entryTime,
                  value: trade.EntryPrice
                }
              ],
              styles: {
                symbol: {
                  type: trade.Direction === '多单' ? 'triangle' : 'invertedTriangle',
                  size: 10,
                  color: trade.Direction === '多单' ? '#26a69a' : '#ef5350'
                }
              }
            });
          } catch (err) {
            console.warn('创建交易标记失败:', err);
          }
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

  // 组件挂载时加载数据
  useEffect(() => {
    loadReplayData();

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
    </div>
  );
};

export default BacktestReplay;
