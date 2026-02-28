/**
 * 回测回放页面组件
 * 功能：回放回测过程，展示K线图表和交易信号
 */
import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Button,
  Select,
  Slider,
  Space,
  Table,
  Tag,
  Row,
  Col,
  Statistic,
  Spin,
  Alert,
  message,
} from 'antd';
import {
  CaretRightOutlined,
  PauseOutlined,
  FastForwardOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { init, dispose, registerLocale, registerOverlay } from 'klinecharts';
import jsonAnnotation from '../../utils/klineAnnotations';
import { backtestApi } from '../../api';
import type { ReplayData, MergeSummary, SymbolInfo, BacktestSymbols } from '../../types/backtest';
import './backtest.css';
import PageContainer from '@/components/PageContainer';

const { Option } = Select;

// 播放速度选项
const SPEED_OPTIONS = [
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '4x', value: 4 },
  { label: '8x', value: 8 },
];

// 交易详情表格列配置
const TRADE_TABLE_COLUMNS = [
  { title: '交易ID', dataIndex: 'trade_id', key: 'trade_id', width: 120 },
  { title: '入场时间', dataIndex: 'EntryTime', key: 'EntryTime' },
  { title: '方向', dataIndex: 'Direction', key: 'Direction', width: 80, render: (text: string) => (
    <Tag color={text === '多单' ? 'green' : 'red'}>{text}</Tag>
  )},
  { title: '入场价格', dataIndex: 'EntryPrice', key: 'EntryPrice', width: 120 },
  { title: '出场时间', dataIndex: 'ExitTime', key: 'ExitTime' },
  { title: '出场价格', dataIndex: 'ExitPrice', key: 'ExitPrice', width: 120 },
  { title: '盈亏', dataIndex: 'PnL', key: 'PnL', width: 100, render: (value: number) => (
    <span style={{ color: value >= 0 ? '#52c41a' : '#f5222d' }}>
      {value >= 0 ? `+${value.toFixed(2)}` : value.toFixed(2)}
    </span>
  )},
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

  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<any>(null);
  const playTimerRef = useRef<number | null>(null);

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
   */
  const loadSymbols = async () => {
    if (!backtestId) return;

    setLoadingSymbols(true);
    setError(null);

    try {
      const data: BacktestSymbols = await backtestApi.getBacktestSymbols(backtestId);
      setSymbols(data.symbols || []);

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

      const mappedData = {
        klines: data.kline_data || [],
        trades: (data.trade_signals || []).map((trade: any, index: number) => ({
          EntryTime: trade.time || '',
          ExitTime: '',
          Direction: trade.type === 'buy' ? '多单' : '空单',
          EntryPrice: trade.price || 0,
          ExitPrice: 0,
          PnL: 0,
          trade_id: trade.trade_id || `trade-${index}`,
        })),
        equity_curve: data.equity_data || [],
        strategy_name: data.metadata?.strategy_name || '',
        backtest_config: data.backtest_config || {},
        symbol: data.metadata?.symbol || 'BTCUSDT',
        interval: data.metadata?.interval || '15m',
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

    if (typeof chart.removeOverlay === 'function') {
      const tradeOverlays = chart.getOverlays({ name: 'jsonAnnotation' }) || [];
      tradeOverlays.forEach((overlay: any) => {
        chart.removeOverlay({ id: overlay.id });
      });
    }

    const visibleTrades = replayData.trades.filter((trade) => {
      const entryTime = new Date(trade.EntryTime).getTime();
      return entryTime >= visibleStartTime && entryTime <= visibleEndTime;
    });

    visibleTrades.forEach((trade) => {
      const entryTime = new Date(trade.EntryTime).getTime();
      const exitTime = trade.ExitTime ? new Date(trade.ExitTime).getTime() : null;

      if (typeof chart.createOverlay === 'function') {
        try {
          if (entryTime >= visibleStartTime && entryTime <= visibleEndTime) {
            chart.createOverlay({
              name: 'jsonAnnotation',
              extendData: JSON.stringify({
                lines: [`${trade.Direction}`, `ID: ${trade.trade_id}`],
                colors: [trade.Direction === '多单' ? '#26a69a' : '#ef5350', '#000000ff'],
                fontSize: 12,
                align: 'left',
              }),
              points: [{ timestamp: entryTime, value: trade.EntryPrice }],
            });
          }

          if (exitTime && exitTime <= currentTime && exitTime >= visibleStartTime && exitTime <= visibleEndTime) {
            chart.createOverlay({
              name: 'jsonAnnotation',
              extendData: JSON.stringify({
                lines: [`${trade.Direction}`, `ID: ${trade.trade_id}`, `盈亏: ${trade.PnL.toFixed(2)}`],
                colors: [
                  trade.PnL >= 0 ? '#4a6cf7' : '#ff9800',
                  '#ffffff',
                  '#ffffff',
                  trade.PnL >= 0 ? '#4a6cf7' : '#ff9800',
                ],
                fontSize: 12,
                align: 'left',
              }),
              points: [{ timestamp: exitTime, value: trade.ExitPrice }],
            });

            chart.createOverlay({
              name: 'line',
              points: [
                { timestamp: entryTime, value: trade.EntryPrice },
                { timestamp: exitTime, value: trade.ExitPrice },
              ],
              styles: {
                line: {
                  color: trade.PnL >= 0 ? '#26a69a' : '#ef5350',
                  width: 2,
                  type: 'dashed',
                },
              },
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
      setCurrentIndex((prev) => {
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

    setCurrentIndex((prev) => {
      const maxIndex = replayData.klines?.length || 0;
      return Math.min(prev + 10, maxIndex - 1);
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
      <PageContainer title={t('backtest_replay')}>
        <div className="flex justify-center items-center py-24">
          <Spin size="large" />
        </div>
      </PageContainer>
    );
  }

  // 渲染错误状态
  if (error) {
    return (
      <PageContainer title={t('backtest_replay')}>
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer title={t('backtest_replay')}>
      <div className="space-y-6">
        {/* 控制栏 */}
        <Card size="small">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Row align="middle" gutter={16}>
            <Col>
              <Space>
                <span>货币对:</span>
                <Select
                  value={selectedSymbol}
                  onChange={handleSymbolChange}
                  style={{ width: 150 }}
                  disabled={loadingSymbols || symbols.length === 0}
                  loading={loadingSymbols}
                >
                  {symbols.map((symbol) => (
                    <Option key={symbol.symbol} value={symbol.symbol}>
                      {symbol.symbol}
                    </Option>
                  ))}
                </Select>
              </Space>
            </Col>
            <Col>
              <Button
                type="primary"
                icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
                onClick={isPlaying ? handlePause : handlePlay}
                disabled={!replayData}
              >
                {isPlaying ? '暂停' : '播放'}
              </Button>
            </Col>
            <Col>
              <Button
                icon={<FastForwardOutlined />}
                onClick={handleFastForward}
                disabled={!replayData || currentIndex >= (replayData?.klines?.length || 0) - 1}
              >
                快进
              </Button>
            </Col>
            <Col>
              <Button
                icon={<StopOutlined />}
                onClick={handleStop}
                disabled={currentIndex === 0 || !replayData}
              >
                停止
              </Button>
            </Col>
            <Col>
              <Space>
                <span>播放速度:</span>
                <Select
                  value={playSpeed}
                  onChange={handleSpeedChange}
                  style={{ width: 80 }}
                  disabled={!replayData}
                >
                  {SPEED_OPTIONS.map((option) => (
                    <Option key={option.value} value={option.value}>
                      {option.label}
                    </Option>
                  ))}
                </Select>
              </Space>
            </Col>
          </Row>

          {/* 进度条 */}
          <Row align="middle">
            <Col flex="none">
              <span className="text-sm text-gray-500 mr-4">
                {currentIndex + 1} / {replayData?.klines?.length || 0}
              </span>
            </Col>
            <Col flex="auto" style={{ padding: '0 16px' }}>
              <Slider
                min={0}
                max={(replayData?.klines?.length || 1) - 1}
                value={currentIndex}
                onChange={handleProgressChange}
                disabled={!replayData}
                tooltip={{
                  formatter: (value) => `${value! + 1} / ${replayData?.klines?.length || 0}`,
                }}
              />
            </Col>
            <Col flex="none">
              <span className="text-sm text-gray-500 ml-4">
                {formatTimestamp(
                  replayData?.klines?.[currentIndex]?.time || replayData?.klines?.[currentIndex]?.timestamp || ''
                )}
              </span>
            </Col>
          </Row>
        </Space>
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

      {/* 图表区域 */}
      <Card>
        <div
          ref={chartRef}
          style={{ width: '100%', height: '600px', minHeight: '400px' }}
        />
      </Card>

      {/* 交易详情表格 */}
      {replayData && (
        <Card size="small" title="交易详情">
          <Table
            columns={TRADE_TABLE_COLUMNS}
            dataSource={
              replayData.trades?.filter((trade) => {
                const currentKline = replayData.klines?.[currentIndex];
                if (!currentKline) return false;
                const currentTime = currentKline.timestamp || currentKline.time;
                const entryTime = new Date(trade.EntryTime).getTime();
                return entryTime <= currentTime;
              }) || []
            }
            rowKey="trade_id"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条交易`,
              pageSizeOptions: ['5', '10', '20', '50'],
              defaultPageSize: 10,
              size: 'small',
            }}
            scroll={{ x: 800, y: 300 }}
            bordered
            size="small"
          />
        </Card>
      )}
    </div>
    </PageContainer>
  );
};

export default BacktestReplay;
