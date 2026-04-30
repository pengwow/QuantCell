/**
 * 回测回放页面组件
 * 功能：回放回测过程，展示K线图表和交易信号
 */
import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'ahooks';
import {
  Card,
  Button,
  Select,
  Slider,
  Space,
  Row,
  Col,
  Statistic,
  Spin,
  Alert,
  message,
  Divider,
  Tooltip,
} from 'antd';
import TradeTable from '../../components/TradeTable';
import {
  CaretRightOutlined,
  PauseOutlined,
  FastForwardOutlined,
  StopOutlined,
  StepForwardOutlined,
  ClockCircleOutlined,
  StockOutlined,
} from '@ant-design/icons';
import { init, dispose, registerLocale, registerOverlay } from 'klinecharts';
import jsonAnnotation from '../../utils/klineAnnotations';
import { backtestApi } from '../../api';
import type { ReplayData, MergeSummary, SymbolInfo } from '../../types/backtest';
import './backtest.css';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/router';

const { Option } = Select;

// 播放速度选项
const SPEED_OPTIONS = [
  { label: '0.5x', value: 0.5 },
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '4x', value: 4 },
  { label: '8x', value: 8 },
];

/**
 * 格式化时间戳为可读的日期时间字符串
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
    second: '2-digit',
  });
};

/**
 * 格式化时间为 mm:ss
 */
const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

/**
 * 解析周期字符串为klinecharts需要的格式
 */
const parseInterval = (interval: string): { span: number; type: any } => {
  const match = interval.match(/\d+/);
  const span = match ? parseInt(match[0]) : 1;
  const unit = interval.replace(/\d+/, '');

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
  const { t } = useTranslation();

  // 获取主题
  const { theme } = useTheme({ localStorageKey: "quantcell-ui-theme" });
  const isDark = theme === 'dark';

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('backtest_replay') || '回测回放');
  }, [t]);

  // 回放数据
  const [replayData, setReplayData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 货币对相关状态
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [loadingSymbols, setLoadingSymbols] = useState<boolean>(false);

  // 合并结果相关状态
  const [mergeSummary, setMergeSummary] = useState<MergeSummary | null>(null);
  const [showMergeSummary, setShowMergeSummary] = useState<boolean>(true);

  // 播放控制状态
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playSpeed, setPlaySpeed] = useState<number>(1);
  const [elapsedTime, setElapsedTime] = useState<number>(0);

  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<any>(null);
  const playTimerRef = useRef<number | null>(null);
  const elapsedTimerRef = useRef<number | null>(null);

  // 注册语言包
  useEffect(() => {
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
      year: '年',
    });
  }, []);

  /**
   * 加载货币对列表
   * 后端返回数据结构: { symbols: ["ETH/USDT", "BTC/USDT"], total: 2 }
   * 注意：apiRequest 已经通过响应拦截器返回 data 字段，不需要再访问 .data
   */
  const loadSymbols = async () => {
    if (!backtestId) return;

    setLoadingSymbols(true);
    setError(null);

    try {
      const data = await backtestApi.getBacktestSymbols(backtestId);
      // 适配新的数据结构：后端返回字符串数组
      const symbolList: string[] = data?.symbols || [];
      
      // 将字符串数组转换为 SymbolInfo 数组用于下拉列表显示
      const formattedSymbols: SymbolInfo[] = symbolList.map((symbol: string) => ({
        symbol,
        status: 'success',
        message: '回测成功'
      }));
      
      setSymbols(formattedSymbols);

      if (formattedSymbols.length > 0) {
        setSelectedSymbol(formattedSymbols[0].symbol);
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
   * 后端新格式：data 中包含 kline_data, trades, equity_curve, metrics, backtest_config 等
   */
  const loadReplayData = async (symbol?: string) => {
    if (!backtestId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await backtestApi.getReplayData(backtestId, symbol);

      // 后端返回的新格式：response 直接是 data 内容
      // 包含：id, strategy_name, backtest_config, metrics, equity_curve, trades, kline_data, equity_data, status, created_at, metadata
      const data = response;

      // 调试日志
      console.log('[BacktestReplay] 获取回放数据:', {
        kline_data_length: data.kline_data?.length || 0,
        trades_length: data.trades?.length || 0,
        equity_curve_length: data.equity_curve?.length || 0,
        strategy_name: data.strategy_name,
        symbol: data.backtest_config?.symbol || symbol,
        interval: data.backtest_config?.interval,
      });

      // 调试第一条交易的原始字段
      if (data.trades && data.trades.length > 0) {
        console.log('[BacktestReplay] 第一条交易原始数据:', data.trades[0]);
        console.log('[BacktestReplay] 第一条交易所有字段:', Object.keys(data.trades[0]));
      }

      const mappedData = {
        klines: data.kline_data || [],
        trades: (data.trades || []).map((trade: any, index: number) => {
          // nautilus 引擎返回的字段名: trade_id, side, direction, quantity, price, timestamp, formatted_time
          // 需要映射到前端期望的字段名: EntryTime, ExitTime, EntryPrice, ExitPrice, PnL, Direction

          // 时间字段 - nautilus 使用 timestamp (秒级) 或 formatted_time
          // 交易ID
          const tradeId = trade.trade_id || `trade-${index}`;

          return {
            // TradeTable 组件需要的字段
            trade_id: tradeId,
            timestamp: trade.timestamp,
            formatted_time: trade.formatted_time,
            side: trade.side,
            direction: trade.direction,
            price: trade.price,
            quantity: trade.quantity,
            volume: trade.volume,
            commission: trade.commission,
            status: trade.status,
            instrument_id: trade.instrument_id,
            // 保留原始字段供后续处理
            _side: trade.side,
            _direction: trade.direction,
            _quantity: trade.quantity,
            _volume: trade.volume,
            _timestamp: trade.timestamp,
          };
        }),
        equity_curve: data.equity_curve || [],
        strategy_name: data.strategy_name || '',
        backtest_config: data.backtest_config || {},
        symbol: data.backtest_config?.symbol || symbol || 'BTCUSDT',
        interval: data.backtest_config?.interval || '15m',
      };

      console.log('[BacktestReplay] 映射后的数据:', {
        klines_length: mappedData.klines.length,
        trades_length: mappedData.trades.length,
      });

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
   * 加载合并结果摘要
   */
  const loadMergeSummary = async () => {
    if (!backtestId) return;

    try {
      const response = await fetch(`/backtest/${backtestId}/results`);
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success' && data.summary) {
          setMergeSummary(data.summary);
        }
      }
    } catch (err) {
      console.error('加载合并结果失败:', err);
    }
  };

  /**
   * 处理货币对切换
   */
  const handleSymbolChange = (value: string) => {
    setSelectedSymbol(value);
    handleStop();
    loadReplayData(value);
  };

  /**
   * 初始化图表
   */
  const initChart = () => {
    if (!chartRef.current || !replayData) return;

    if (chartRef.current) {
      chartRef.current.style.width = '100%';
      chartRef.current.style.height = '100%';
      chartRef.current.style.minHeight = '600px';
    }

    if (chartInstance.current) {
      dispose(chartRef.current);
      chartInstance.current = null;
    }

    try {
      // 注册自定义遮盖物组件
      if (typeof registerOverlay === 'function') {
        registerOverlay(jsonAnnotation);
      }

      const chart = init(chartRef.current, { locale: 'zh-CN' });
      chartInstance.current = chart as any;

      if (chart) {
        chart.setStyles({
          candle: {
            tooltip: {
              showRule: 'always',
              showType: 'standard',
            },
          },
        });

        const symbol = replayData.symbol || 'BTC/USDT';
        chart.setSymbol({ ticker: symbol.replace('USDT', '/USDT') });

        const interval = replayData.interval || '15m';
        const periodInfo = parseInterval(interval);
        chart.setPeriod({ span: periodInfo.span, type: periodInfo.type });

        chart.setDataLoader({
          getBars: (params: any) => {
            const currentKlines = replayData.klines.slice(0, currentIndex + 1);
            params.callback(currentKlines);
          },
        });

        if (replayData.klines && replayData.klines.length > 0) {
          const initialKlines = replayData.klines.slice(0, 1);
          chart.setDataLoader({
            getBars: (params: any) => {
              params.callback(initialKlines);
            },
          });
        }

        chart.resize();
      }
    } catch (error) {
      console.error('初始化图表失败:', error);
    }
  };

  /**
   * 更新图表数据
   */
  const updateChart = (index: number) => {
    if (!chartInstance.current || !replayData || !replayData.klines || replayData.klines.length === 0) return;

    try {
      const chart = chartInstance.current;
      const visibleKlineCount = 100;
      const startIndex = Math.max(0, index - visibleKlineCount + 1);
      const endIndex = index + 1;
      const currentKlines = replayData.klines.slice(startIndex, endIndex);

      chart.setDataLoader({
        getBars: (params: any) => {
          params.callback(currentKlines);
        },
      });

      chart.resize();

      const currentKline = replayData.klines[index];
      if (currentKline) {
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
   */
  const addTradeMarkers = (chart: any, formattedKline: any, visibleStartTime: number, visibleEndTime: number) => {
    if (!replayData) return;

    const currentTime = formattedKline.timestamp;
    if (!currentTime || !replayData.trades) return;

    console.log('[addTradeMarkers] 开始添加交易标记:', {
      currentTime,
      visibleStartTime,
      visibleEndTime,
      totalTrades: replayData.trades.length,
    });

    if (typeof chart.removeOverlay === 'function') {
      const tradeOverlays = chart.getOverlays({ name: 'jsonAnnotation' }) || [];
      tradeOverlays.forEach((overlay: any) => {
        chart.removeOverlay({ id: overlay.id });
      });
    }

    // 调试第一条交易和K线的时间格式
    if (replayData.trades.length > 0) {
      const firstTrade = replayData.trades[0];
      const firstKline = replayData.klines[0];
      console.log('[addTradeMarkers] 时间格式调试:', {
        firstTrade_timestamp: firstTrade.timestamp,
        firstTrade_timestamp_parsed: firstTrade.timestamp ? firstTrade.timestamp * 1000 : 0,
        firstKline_timestamp: firstKline?.timestamp,
        visibleStartTime,
        visibleEndTime,
      });
    }

    const visibleTrades = replayData.trades.filter((trade) => {
      // nautilus 数据使用秒级 timestamp，需要转换为毫秒
      const entryTime = trade.timestamp ? trade.timestamp * 1000 : 0;
      const isVisible = entryTime >= visibleStartTime && entryTime <= visibleEndTime;
      return isVisible;
    });

    console.log('[addTradeMarkers] 可见范围内的交易:', visibleTrades.length);

    visibleTrades.forEach((trade) => {
      // nautilus 数据使用秒级 timestamp，需要转换为毫秒
      const entryTime = trade.timestamp ? trade.timestamp * 1000 : 0;

      if (typeof chart.createOverlay === 'function') {
        try {
          if (entryTime >= visibleStartTime && entryTime <= visibleEndTime) {
            // 判断方向
            const isBuy = trade.side?.toUpperCase() === 'BUY' || trade.direction?.includes('买入');
            const directionText = isBuy ? '买入' : '卖出';
            const color = isBuy ? '#26a69a' : '#ef5350';

            // 格式化数量和金额
            const quantity = trade.quantity ? trade.quantity.toFixed(4) : '0';
            const volume = trade.volume ? trade.volume.toFixed(2) : '0';

            // 根据主题设置标签颜色
            const labelColor = isDark ? '#ffffff' : '#333333';

            chart.createOverlay({
              name: 'jsonAnnotation',
              extendData: JSON.stringify({
                lines: [`${directionText}`, `数量: ${quantity}`, `金额: ${volume}`],
                colors: [color, labelColor, labelColor],
                fontSize: 12,
                align: 'left',
              }),
              points: [{ timestamp: entryTime, value: trade.price }],
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
    
    // 播放进度定时器
    playTimerRef.current = window.setInterval(() => {
      setCurrentIndex((prev) => {
        const maxIndex = replayData.klines?.length || 0;
        if (prev >= maxIndex - 1) {
          handlePause();
          return prev;
        }
        return prev + 1;
      });
    }, 1000 / playSpeed);

    // 计时器
    elapsedTimerRef.current = window.setInterval(() => {
      setElapsedTime((prev) => prev + 1);
    }, 1000);
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
    if (elapsedTimerRef.current) {
      window.clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  };

  /**
   * 快进
   */
  const handleFastForward = () => {
    if (!replayData || !replayData.klines || replayData.klines.length === 0) return;

    setCurrentIndex((prev) => {
      const maxIndex = replayData.klines?.length || 0;
      return Math.min(prev + 10, maxIndex - 1);
    });
  };

  /**
   * 单步前进
   */
  const handleStepForward = () => {
    if (!replayData || !replayData.klines || replayData.klines.length === 0) return;
    
    setCurrentIndex((prev) => {
      const maxIndex = replayData.klines?.length || 0;
      return Math.min(prev + 1, maxIndex - 1);
    });
  };

  /**
   * 停止播放并重置
   */
  const handleStop = () => {
    handlePause();
    setCurrentIndex(0);
    setElapsedTime(0);
  };

  /**
   * 改变播放速度
   */
  const handleSpeedChange = (value: number) => {
    setPlaySpeed(value);
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

  // 组件挂载时加载货币对列表和合并结果
  useEffect(() => {
    loadSymbols();
    loadMergeSummary();

    return () => {
      if (playTimerRef.current) {
        window.clearInterval(playTimerRef.current);
      }
      if (elapsedTimerRef.current) {
        window.clearInterval(elapsedTimerRef.current);
      }
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
      <PageContainer title={t('backtest_replay') || '回测回放'}>
        <div className="flex justify-center items-center py-24">
          <Spin size="large" />
        </div>
      </PageContainer>
    );
  }

  // 渲染错误状态
  if (error) {
    return (
      <PageContainer title={t('backtest_replay') || '回测回放'}>
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
        />
      </PageContainer>
    );
  }

  const progressPercent = replayData?.klines?.length 
    ? Math.round((currentIndex / (replayData.klines.length - 1)) * 100) 
    : 0;

  return (
    <PageContainer title={t('backtest_replay') || '回测回放'}>
      <div className="space-y-6">
        {/* 控制栏 - 重新设计 */}
        <Card size="small" className="replay-control-card">
          {/* 第一行：货币对选择和播放控制 */}
          <Row align="middle" justify="space-between" gutter={[16, 16]}>
            {/* 左侧：货币对选择 */}
            <Col flex="none">
              <Space align="center">
                <StockOutlined style={{ fontSize: 18, color: '#1890ff' }} />
                <span style={{ fontWeight: 500 }}>货币对</span>
                <Select
                  value={selectedSymbol}
                  onChange={handleSymbolChange}
                  style={{ width: 140 }}
                  disabled={loadingSymbols || symbols.length === 0}
                  loading={loadingSymbols}
                  placeholder="选择货币对"
                  suffixIcon={<StockOutlined />}
                >
                  {symbols.map((symbol) => (
                    <Option key={symbol.symbol} value={symbol.symbol}>
                      {symbol.symbol}
                    </Option>
                  ))}
                </Select>
              </Space>
            </Col>

            {/* 中间：播放控制按钮组 */}
            <Col flex="auto" style={{ textAlign: 'center' }}>
              <Space size="small" align="center">
                {/* 停止按钮 */}
                <Tooltip title="停止并重置">
                  <Button
                    type="text"
                    shape="circle"
                    icon={<StopOutlined />}
                    onClick={handleStop}
                    disabled={currentIndex === 0 || !replayData}
                    style={{ 
                      color: currentIndex === 0 ? undefined : '#ff4d4f',
                      fontSize: 18 
                    }}
                  />
                </Tooltip>

                <Divider type="vertical" style={{ margin: '0 8px' }} />

                {/* 播放/暂停按钮 - 主按钮 */}
                <Button
                  type="primary"
                  shape="circle"
                  size="large"
                  icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
                  onClick={isPlaying ? handlePause : handlePlay}
                  disabled={!replayData}
                  style={{ 
                    width: 48, 
                    height: 48, 
                    fontSize: 20,
                    boxShadow: '0 2px 8px rgba(24, 144, 255, 0.35)'
                  }}
                />

                {/* 单步前进 */}
                <Tooltip title="单步前进">
                  <Button
                    type="text"
                    shape="circle"
                    icon={<StepForwardOutlined />}
                    onClick={handleStepForward}
                    disabled={!replayData || currentIndex >= (replayData?.klines?.length || 0) - 1}
                    style={{ fontSize: 16 }}
                  />
                </Tooltip>

                {/* 快进 */}
                <Tooltip title="快进10步">
                  <Button
                    type="text"
                    shape="circle"
                    icon={<FastForwardOutlined />}
                    onClick={handleFastForward}
                    disabled={!replayData || currentIndex >= (replayData?.klines?.length || 0) - 1}
                    style={{ fontSize: 16 }}
                  />
                </Tooltip>

                <Divider type="vertical" style={{ margin: '0 8px' }} />

                {/* 播放速度 */}
                <Tooltip title="播放速度">
                  <Space align="center" style={{ marginLeft: 8 }}>
                    <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                    <Select
                      value={playSpeed}
                      onChange={handleSpeedChange}
                      style={{ width: 70 }}
                      disabled={!replayData}
                      bordered={false}
                      dropdownMatchSelectWidth={false}
                    >
                      {SPEED_OPTIONS.map((option) => (
                        <Option key={option.value} value={option.value}>
                          {option.label}
                        </Option>
                      ))}
                    </Select>
                  </Space>
                </Tooltip>
              </Space>
            </Col>

            {/* 右侧：时间显示 */}
            <Col flex="none">
              <Space align="center" style={{ 
                background: 'transparent', 
                padding: '4px 12px', 
                borderRadius: 4,
                fontFamily: 'monospace',
                border: '1px solid var(--ant-color-border)'
              }}>
                <ClockCircleOutlined style={{ color: 'var(--ant-color-text-secondary)' }} />
                <span style={{ color: 'var(--ant-color-text)' }}>{formatTime(elapsedTime)}</span>
              </Space>
            </Col>
          </Row>

          <Divider style={{ margin: '12px 0' }} />

          {/* 第二行：进度条 */}
          <Row align="middle" gutter={[16, 0]}>
            <Col flex="none">
              <span style={{ 
                fontSize: 12, 
                color: '#8c8c8c',
                fontFamily: 'monospace'
              }}>
                {currentIndex + 1}
              </span>
            </Col>
            <Col flex="auto" style={{ padding: '0 8px' }}>
              <Slider
                min={0}
                max={(replayData?.klines?.length || 1) - 1}
                value={currentIndex}
                onChange={handleProgressChange}
                disabled={!replayData}
                tooltip={{
                  formatter: (value) => (
                    <div>
                      <div>第 {value! + 1} / {replayData?.klines?.length || 0} 根K线</div>
                      <div style={{ fontSize: 12, opacity: 0.8 }}>
                        {formatTimestamp(
                          replayData?.klines?.[value!]?.time || replayData?.klines?.[value!]?.timestamp || ''
                        )}
                      </div>
                    </div>
                  ),
                }}
              />
            </Col>
            <Col flex="none">
              <span style={{ 
                fontSize: 12, 
                color: '#8c8c8c',
                fontFamily: 'monospace'
              }}>
                {replayData?.klines?.length || 0}
              </span>
            </Col>
          </Row>

          {/* 第三行：时间戳和进度百分比 */}
          <Row justify="center" style={{ marginTop: 4 }}>
            <Col>
              <span style={{ 
                fontSize: 13, 
                color: '#595959',
                fontWeight: 500
              }}>
                {formatTimestamp(
                  replayData?.klines?.[currentIndex]?.time || replayData?.klines?.[currentIndex]?.timestamp || ''
                )}
                <span style={{ marginLeft: 12, color: '#1890ff' }}>
                  {progressPercent}%
                </span>
              </span>
            </Col>
          </Row>
        </Card>

        {/* 合并结果显示区域 */}
        {mergeSummary && showMergeSummary && (
          <Card
            size="small"
            title="合并结果摘要"
            extra={
              <Button type="text" onClick={() => setShowMergeSummary(false)}>
                收起
              </Button>
            }
          >
            <Row gutter={[16, 16]}>
              <Col span={6}>
                <Statistic title="总货币对数量" value={mergeSummary.total_currencies} />
              </Col>
              <Col span={6}>
                <Statistic
                  title="成功货币对"
                  value={mergeSummary.successful_currencies}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="失败货币对"
                  value={mergeSummary.failed_currencies}
                  valueStyle={{ color: '#f5222d' }}
                />
              </Col>
              <Col span={6}>
                <Statistic title="总交易次数" value={mergeSummary.total_trades} />
              </Col>
              <Col span={6}>
                <Statistic title="平均每货币对交易次数" value={mergeSummary.average_trades_per_currency} />
              </Col>
              <Col span={6}>
                <Statistic
                  title="总收益率"
                  value={`${mergeSummary.total_return}%`}
                  valueStyle={{ color: mergeSummary.total_return >= 0 ? '#52c41a' : '#f5222d' }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="平均收益率"
                  value={`${mergeSummary.average_return}%`}
                  valueStyle={{ color: mergeSummary.average_return >= 0 ? '#52c41a' : '#f5222d' }}
                />
              </Col>
              <Col span={6}>
                <Statistic title="平均最大回撤" value={`${mergeSummary.average_max_drawdown}%`} />
              </Col>
              <Col span={6}>
                <Statistic title="平均夏普比率" value={mergeSummary.average_sharpe_ratio} />
              </Col>
              <Col span={6}>
                <Statistic title="平均索提诺比率" value={mergeSummary.average_sortino_ratio} />
              </Col>
              <Col span={6}>
                <Statistic title="平均卡尔玛比率" value={mergeSummary.average_calmar_ratio} />
              </Col>
              <Col span={6}>
                <Statistic title="平均胜率" value={`${mergeSummary.average_win_rate}%`} />
              </Col>
            </Row>
          </Card>
        )}

        {mergeSummary && !showMergeSummary && (
          <div className="text-right">
            <Button type="link" onClick={() => setShowMergeSummary(true)}>
              显示合并结果摘要
            </Button>
          </div>
        )}

        {/* 图表区域 - 优化布局 */}
        <Card 
          style={{ marginTop: 24 }}
          styles={{ body: { padding: 0, height: '600px' } }}
          className="replay-chart-card"
        >
          <div
            ref={chartRef}
            className="replay-kline-chart"
          />
        </Card>

        {/* 交易详情表格 - 使用 TradeTable 组件，根据播放进度动态显示 */}
        {replayData && (
          <Card size="small" title="交易详情" style={{ marginTop: 24 }}>
            {(() => {
              // 根据当前播放进度过滤交易
              const currentKline = replayData.klines?.[currentIndex];
              const currentTime = currentKline?.timestamp || 0;
              
              const visibleTrades = replayData.trades?.filter((trade: any) => {
                // nautilus 数据使用 timestamp (秒级)，需要转换为毫秒
                const tradeTime = trade.timestamp ? trade.timestamp * 1000 : 0;
                return tradeTime <= currentTime;
              }) || [];
              
              return (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <span style={{ color: '#8c8c8c' }}>
                      共 {visibleTrades.length} 条记录 (总 {replayData.trades?.length || 0} 条)
                    </span>
                  </div>
                  <TradeTable
                    data={visibleTrades}
                    loading={loading}
                    pagination={true}
                  />
                </>
              );
            })()}
          </Card>
        )}
      </div>
    </PageContainer>
  );
};

export default BacktestReplay;
