import { QUANT_COLORS } from '@/utils/colors';
/**
 * 回测回放页面组件
 * 功能：回放回测过程，展示K线图表和交易信号
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
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
  Spin,
  Alert,
  App,
  Divider,
  Tooltip,
  Segmented,
} from 'antd';
import TradeTable, { type Trade as TradeTableTrade } from '../../components/TradeTable';
import {
  CaretRightOutlined,
  PauseOutlined,
  FastForwardOutlined,
  StopOutlined,
  StepForwardOutlined,
  ClockCircleOutlined,
  StockOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { init, dispose, registerLocale, registerOverlay } from 'klinecharts';
import type { Chart, DataLoaderGetBarsParams, KLineData, PeriodType } from 'klinecharts';
import jsonAnnotation from '../../utils/klineAnnotations';
import { backtestApi } from '../../api';
import type { ReplayData, ReplayKline, SymbolInfo } from '../../types/backtest';
import PortfolioReplayView from './PortfolioReplayView';
// 显式带 .tsx 扩展名：同目录存在仅大小写不同的 factorSnapshot.ts，
// macOS 默认大小写不敏感文件系统下省略扩展名会误解析到该文件
import FactorSnapshot from './FactorSnapshot.tsx';
import './backtest.css';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';

const { Option } = Select;

// 与全局视角统一的速度枚举：覆盖 1x~128x
const SPEED_OPTIONS = [
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '4x', value: 4 },
  { label: '8x', value: 8 },
  { label: '16x', value: 16 },
  { label: '32x', value: 32 },
  { label: '64x', value: 64 },
  { label: '128x', value: 128 },
];

// Segmented 视角切换选项提到模块级常量，避免每次 render 新引用触发 antd 内部 rebuild
// （rebuild 时 onMouseMove 监听残留会造成 setViewMode 死循环）
const VIEW_MODE_OPTIONS = [
  { label: '品种视角', value: 'symbol', icon: <StockOutlined /> },
  { label: '全局视角', value: 'portfolio', icon: <GlobalOutlined /> },
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
 * 回放 K 线与 klinecharts 的 KLineData 字段存在差异（时间字段名、类型），统一转换为数值格式
 */
const toChartKlines = (klines: ReplayKline[]): KLineData[] =>
  klines.map((k) => ({
    timestamp: Number(k.timestamp ?? k.time) || 0,
    open: Number(k.open) || 0,
    high: Number(k.high) || 0,
    low: Number(k.low) || 0,
    close: Number(k.close) || 0,
    volume: Number(k.volume) || 0,
  }));

/**
 * 解析周期字符串为klinecharts需要的格式
 */
const parseInterval = (interval: string): { span: number; type: PeriodType } => {
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
  // 详情页跳转可携带 ?symbol= 指定初始品种
  const [searchParams] = useSearchParams();
  const initialSymbol = searchParams.get('symbol') || '';
  const { t } = useTranslation();
  const { message } = App.useApp();

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

  // 播放控制状态
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playSpeed, setPlaySpeed] = useState<number>(1);
  const [elapsedTime, setElapsedTime] = useState<number>(0);

  // 视角：多品种回测默认进入全局（组合）视角，单品种只有品种视角
  const [viewMode, setViewMode] = useState<'symbol' | 'portfolio'>('symbol');

  // 视角切换过渡：统一为整页 Spin 动画，避免 portfolio 数据快到时瞬间替换
  // ponytail: 首次挂载跳过，否则已缓存数据的首屏也会白转 300ms
  const [viewChanging, setViewChanging] = useState(false);
  const firstViewChangeRef = useRef(true);
  useEffect(() => {
    if (firstViewChangeRef.current) {
      firstViewChangeRef.current = false;
      return;
    }
    setViewChanging(true);
    const t = setTimeout(() => setViewChanging(false), 300);
    return () => clearTimeout(t);
  }, [viewMode]);

  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<Chart | null>(null);
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

      // 多品种默认全局视角；单品种固定品种视角
      setViewMode(symbolList.length > 1 ? 'portfolio' : 'symbol');

      if (formattedSymbols.length > 0) {
        // 优先使用详情页携带的品种（需在结果品种列表中），否则取第一个
        const preferred = initialSymbol && symbolList.includes(initialSymbol)
          ? initialSymbol
          : formattedSymbols[0].symbol;
        setSelectedSymbol(preferred);
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

      // round-trip 契约后端已带 trade_id/symbol entry/exit 全字段，直接透传
      const mappedData = {
        klines: data.kline_data || [],
        trades: data.trades || [],
        equity_curve: data.equity_curve || [],
        strategy_name: data.strategy_name || '',
        backtest_config: data.backtest_config || {},
        factors: data.factors ?? null,
        symbol: data.backtest_config?.symbol || symbol || 'BTCUSDT',
        interval: data.backtest_config?.interval || '15m',
      };

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

      if (chart) {
        chartInstance.current = chart;

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
          getBars: (params: DataLoaderGetBarsParams) => {
            const currentKlines = replayData.klines.slice(0, currentIndex + 1);
            params.callback(toChartKlines(currentKlines));
          },
        });

        if (replayData.klines && replayData.klines.length > 0) {
          const initialKlines = replayData.klines.slice(0, 1);
          chart.setDataLoader({
            getBars: (params: DataLoaderGetBarsParams) => {
              params.callback(toChartKlines(initialKlines));
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
    const chart = chartInstance.current;
    if (!chart || !replayData || !replayData.klines || replayData.klines.length === 0) return;

    try {
      const visibleKlineCount = 100;
      const startIndex = Math.max(0, index - visibleKlineCount + 1);
      const endIndex = index + 1;
      const currentKlines = replayData.klines.slice(startIndex, endIndex);

      chart.setDataLoader({
        getBars: (params: DataLoaderGetBarsParams) => {
          params.callback(toChartKlines(currentKlines));
        },
      });

      chart.resize();

      const currentKline = replayData.klines[index];
      if (currentKline) {
        // 回放数据的时间戳可能来自后端字符串或秒级数字，统一转成 number
        const visibleStartTime = Number(replayData.klines[startIndex]?.timestamp) || 0;
        const visibleEndTime = Number(replayData.klines[endIndex - 1]?.timestamp) || 0;
        addTradeMarkers(chart, currentKline, visibleStartTime, visibleEndTime);
      }
    } catch (error) {
      console.error('更新图表数据失败:', error);
    }
  };

  /**
   * 添加交易标记
   */
  const addTradeMarkers = (chart: Chart, formattedKline: ReplayKline, visibleStartTime: number, visibleEndTime: number) => {
    if (!replayData) return;

    const currentTime = formattedKline.timestamp;
    if (!currentTime || !replayData.trades) return;

    if (typeof chart.removeOverlay === 'function') {
      const tradeOverlays = chart.getOverlays({ name: 'jsonAnnotation' }) || [];
      tradeOverlays.forEach((overlay) => {
        chart.removeOverlay({ id: overlay.id });
      });
    }

    // round-trip 契约：秒级 timestamp，标记画在开仓价位置，side 为开仓方向
    const visibleTrades = replayData.trades.filter((trade) => {
      const entryTime = trade.timestamp * 1000;
      return entryTime >= visibleStartTime && entryTime <= visibleEndTime;
    });

    visibleTrades.forEach((trade) => {
      const entryTime = trade.timestamp * 1000;

      if (typeof chart.createOverlay === 'function') {
        try {
          if (entryTime >= visibleStartTime && entryTime <= visibleEndTime) {
            const isBuy = trade.side === 'buy';
            const directionText = isBuy ? '买入' : '卖出';
            const color = isBuy ? '#26a69a' : '#ef5350';
            // 根据主题设置标签颜色
            const labelColor = isDark ? '#ffffff' : '#333333';

            chart.createOverlay({
              name: 'jsonAnnotation',
              extendData: JSON.stringify({
                lines: [directionText, `数量: ${trade.size.toFixed(4)}`, `金额: ${(trade.entry_price * trade.size).toFixed(2)}`],
                colors: [color, labelColor, labelColor],
                fontSize: 12,
                align: 'left',
              }),
              points: [{ timestamp: entryTime, value: trade.entry_price }],
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

  // 组件挂载时加载货币对列表
  useEffect(() => {
    loadSymbols();

    return () => {
      if (playTimerRef.current) {
        window.clearInterval(playTimerRef.current);
      }
      if (elapsedTimerRef.current) {
        window.clearInterval(elapsedTimerRef.current);
      }
      // chart 实例在 init 后写入 ref，卸载时必须读取最新引用才能释放
      if (chartRef.current) {
        // eslint-disable-next-line react-hooks/exhaustive-deps -- 卸载时读取最新 ref 是有意为之
        dispose(chartRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, [backtestId]);

  // 货币对列表加载完成后（且处于品种视角）加载回放数据；
  // 从全局视角切回时重新加载，以便重新初始化图表
  useEffect(() => {
    if (viewMode === 'symbol' && selectedSymbol) {
      loadReplayData(selectedSymbol);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [viewMode, selectedSymbol]);

  // 数据加载完成后初始化图表
  // viewChanging 必须进依赖：切视角时数据可能在 300ms 过渡 Spin（图表容器被卸载）期间
  // 就返回，那次渲染 chartRef 为空会跳过 init；等容器随 viewChanging=false 重新挂载时，
  // replayData 引用已不会再变——不监听 viewChanging 就永远漏掉这次初始化（图表空白，
  // 直到切换货币对产生新 replayData 才恢复）
  useEffect(() => {
    if (replayData && chartRef.current && !viewChanging) {
      initChart();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [replayData, viewChanging]);

  // 当前索引变化时更新图表
  useEffect(() => {
    if (replayData && chartInstance.current) {
      updateChart(currentIndex);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [currentIndex, replayData]);

  // 切到全局视角：暂停品种时钟并释放 K 线图实例（其容器将卸载）
  useEffect(() => {
    if (viewMode !== 'portfolio') return;
    handlePause();
    if (chartRef.current) {
      dispose(chartRef.current);
    }
    chartInstance.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在视角切换时处理
  }, [viewMode]);

  // 渲染加载状态：品种列表加载、品种视角下回放数据加载、视角切换过渡统一走整页 Spin
  if (loadingSymbols || (loading && viewMode === 'symbol') || viewChanging) {
    return (
      <PageContainer title={t('backtest_replay') || '回测回放'}>
        <div className="flex justify-center items-center py-24">
          <Spin size="large" />
        </div>
      </PageContainer>
    );
  }

  // 渲染错误状态
  if (error && viewMode === 'symbol') {
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

  // 播放当前 K 线时刻（毫秒），交易过滤与因子快照对齐共用
  const currentMs = Number(replayData?.klines?.[currentIndex]?.timestamp) || 0;

  const progressPercent = replayData?.klines?.length 
    ? Math.round((currentIndex / (replayData.klines.length - 1)) * 100) 
    : 0;

  return (
    <PageContainer title={t('backtest_replay') || '回测回放'}>
      {symbols.length > 1 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
          <Segmented
            value={viewMode}
            onChange={(value) => setViewMode(value as 'symbol' | 'portfolio')}
            options={VIEW_MODE_OPTIONS}
          />
        </div>
      )}

      {viewMode === 'portfolio' && backtestId ? (
        <PortfolioReplayView backtestId={backtestId} symbols={symbols.map((s) => s.symbol)} />
      ) : (
      <div className="space-y-6">
        {/* 控制栏 - 重新设计 */}
        <Card size="small" className="replay-control-card">
          {/* 第一行：货币对选择和播放控制 */}
          <Row align="middle" justify="space-between" gutter={[16, 16]}>
            {/* 左侧：货币对选择 */}
            <Col flex="none">
              <Space align="center">
                <StockOutlined style={{ fontSize: 18, color: QUANT_COLORS.info }} />
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
                      color: currentIndex === 0 ? undefined : QUANT_COLORS.negative,
                      fontSize: 18 
                    }}
                  />
                </Tooltip>

                <Divider orientation="vertical" style={{ margin: '0 8px' }} />

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

                <Divider orientation="vertical" style={{ margin: '0 8px' }} />

                {/* 播放速度 */}
                <Tooltip title="播放速度">
                  <Space align="center" style={{ marginLeft: 8 }}>
                    <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                    <Select
                      value={playSpeed}
                      onChange={handleSpeedChange}
                      style={{ width: 70 }}
                      disabled={!replayData}
                      variant="borderless"
                      popupMatchSelectWidth={false}
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
                <span style={{ marginLeft: 12, color: QUANT_COLORS.info }}>
                  {progressPercent}%
                </span>
              </span>
            </Col>
          </Row>
        </Card>

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

        {/* 因子快照：随播放时刻对齐显示当前因子值与信号（无因子数据的回测不渲染） */}
        <FactorSnapshot factors={replayData?.factors} currentMs={currentMs} />

        {/* 交易详情表格 - 使用 TradeTable 组件，根据播放进度动态显示 */}
        {replayData && (
          <Card size="small" title="交易详情" style={{ marginTop: 24 }}>
            {(() => {
              // 根据当前播放进度过滤交易
              const currentKline = replayData.klines?.[currentIndex];
              // 回放K线时间与交易时间统一使用毫秒比较
              const currentTime = Number(currentKline?.timestamp) || 0;

              const visibleTrades = (replayData.trades?.filter((trade) => {
                // 回测数据使用 timestamp (秒级)，需要转换为毫秒
                const tradeTime = trade.timestamp ? trade.timestamp * 1000 : 0;
                return tradeTime <= currentTime;
              }) || []) as TradeTableTrade[];
              
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
      )}
    </PageContainer>
  );
};

export default BacktestReplay;
