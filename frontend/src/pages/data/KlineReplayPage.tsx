/**
 * K线数据回放页面
 * 功能：回放指定货币对的K线数据，支持播放控制、速度调节、时间范围选择
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
  DatePicker,
  Tooltip,
  Badge,
} from 'antd';
import {
  CaretRightOutlined,
  PauseOutlined,
  FastForwardOutlined,
  StopOutlined,
  StepForwardOutlined,
  StepBackwardOutlined,
  ArrowLeftOutlined,
  HistoryOutlined,
  ClockCircleOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import { init, dispose } from 'klinecharts';
import dayjs from 'dayjs';
import { dataApi } from '@/api/dataApi';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/router';
import { useTranslation } from 'react-i18next';

const { Option } = Select;
const { RangePicker } = DatePicker;

// 播放速度选项
const SPEED_OPTIONS = [
  { label: '0.5x', value: 0.5 },
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '5x', value: 5 },
  { label: '10x', value: 10 },
];

// 时间周期选项
const INTERVAL_OPTIONS = [
  { label: '1分钟', value: '1m' },
  { label: '5分钟', value: '5m' },
  { label: '15分钟', value: '15m' },
  { label: '1小时', value: '1h' },
  { label: '4小时', value: '4h' },
  { label: '1天', value: '1d' },
];

// 快进步长选项
const FAST_FORWARD_STEPS = [
  { label: '+10', value: 10 },
  { label: '+50', value: 50 },
  { label: '+100', value: 100 },
];

/**
 * 格式化时间戳
 */
const formatTimestamp = (timestamp: number | string): string => {
  if (!timestamp) return '-';
  const ts = typeof timestamp === 'string' ? parseInt(timestamp) : timestamp;
  if (isNaN(ts)) return '-';
  return dayjs(ts).format('YYYY-MM-DD HH:mm:ss');
};

/**
 * 格式化K线数据为klinecharts需要的格式
 */
const formatKlineData = (data: any[]) => {
  return data.map((item) => ({
    timestamp: item.timestamp || item[0],
    open: item.open || item[1],
    high: item.high || item[2],
    low: item.low || item[3],
    close: item.close || item[4],
    volume: item.volume || item[5] || 0,
  }));
};

/**
 * 解析周期字符串
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
    default:
      return { span: 15, type: 'minute' as const };
  }
};

interface KlineReplayPageProps {
  symbol?: string;
}

const KlineReplayPage: React.FC<KlineReplayPageProps> = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('kline_replay') || 'K线回放');
  }, [t]);

  // 从查询参数中获取货币对
  const queryParams = new URLSearchParams(location.search);
  const symbol = queryParams.get('symbol') || '';

  // 从路由状态中获取返回信息
  const returnState = location.state as {
    returnPath?: string;
    returnSearch?: string;
    pageState?: Record<string, any>;
  } | null;

  // K线数据
  const [klines, setKlines] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 回放控制状态
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playSpeed, setPlaySpeed] = useState<number>(1);
  const [fastForwardStep, setFastForwardStep] = useState<number>(10);

  // 时间范围设置
  const [interval, setInterval] = useState<string>('1h');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);

  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<any>(null);
  const playTimerRef = useRef<number | null>(null);

  // 统计数据
  const [stats, setStats] = useState({
    totalKlines: 0,
    startTime: '',
    endTime: '',
    highestPrice: 0,
    lowestPrice: 0,
    totalVolume: 0,
  });

  /**
   * 加载K线数据
   */
  const loadKlines = useCallback(async () => {
    if (!symbol) return;

    setLoading(true);
    setError(null);

    try {
      const params: any = {
        symbol,
        interval,
        limit: 1000,
      };

      if (dateRange && dateRange[0] && dateRange[1]) {
        params.start_time = dateRange[0].valueOf();
        params.end_time = dateRange[1].valueOf();
      }

      const response = await dataApi.getKlines(params);
      const data = formatKlineData(response.data || response);

      if (data.length === 0) {
        setError('未找到K线数据');
        setKlines([]);
        return;
      }

      setKlines(data);
      setCurrentIndex(0);

      // 计算统计数据
      const prices = data.flatMap((k) => [k.high, k.low]);
      const volumes = data.map((k) => k.volume || 0);

      setStats({
        totalKlines: data.length,
        startTime: formatTimestamp(data[0]?.timestamp),
        endTime: formatTimestamp(data[data.length - 1]?.timestamp),
        highestPrice: Math.max(...prices),
        lowestPrice: Math.min(...prices),
        totalVolume: volumes.reduce((a, b) => a + b, 0),
      });
    } catch (err) {
      console.error('加载K线数据失败:', err);
      setError('加载K线数据失败，请稍后重试');
      message.error('加载K线数据失败');
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, dateRange]);

  /**
   * 初始化图表
   */
  const initChart = useCallback(() => {
    if (!chartRef.current || klines.length === 0) return;

    // 清理旧图表
    if (chartInstance.current) {
      dispose(chartRef.current);
      chartInstance.current = null;
    }

    try {
      const chart = init(chartRef.current, {
        locale: 'zh-CN',
        styles: {
          candle: {
            tooltip: {
              showRule: 'always',
              showType: 'standard',
            },
          },
        },
      });

      chartInstance.current = chart;

      if (chart) {
        // 设置货币对
        chart.setSymbol({
          ticker: symbol,
          name: symbol,
        });

        // 设置周期
        const periodInfo = parseInterval(interval);
        chart.setPeriod(periodInfo);

        // 设置初始数据
        updateChartDisplay(0);

        // 调整大小
        chart.resize();
      }
    } catch (error) {
      console.error('初始化图表失败:', error);
    }
  }, [klines, symbol, interval]);

  /**
   * 更新图表显示
   */
  const updateChartDisplay = useCallback(
    (index: number) => {
      if (!chartInstance.current || klines.length === 0) return;

      try {
        const chart = chartInstance.current;

        // 显示从开头到当前索引的数据
        const visibleKlines = klines.slice(0, index + 1);

        chart.setDataLoader({
          getBars: (params: any) => {
            params.callback(visibleKlines);
          },
        });

        chart.resize();
      } catch (error) {
        console.error('更新图表显示失败:', error);
      }
    },
    [klines]
  );

  /**
   * 播放控制
   */
  const handlePlay = useCallback(() => {
    if (klines.length === 0) return;

    setIsPlaying(true);
    playTimerRef.current = window.setInterval(() => {
      setCurrentIndex((prev) => {
        if (prev >= klines.length - 1) {
          handlePause();
          return prev;
        }
        return prev + 1;
      });
    }, 500 / playSpeed);
  }, [klines.length, playSpeed]);

  /**
   * 暂停播放
   */
  const handlePause = useCallback(() => {
    setIsPlaying(false);
    if (playTimerRef.current) {
      window.clearInterval(playTimerRef.current);
      playTimerRef.current = null;
    }
  }, []);

  /**
   * 停止并重置
   */
  const handleStop = useCallback(() => {
    handlePause();
    setCurrentIndex(0);
  }, [handlePause]);

  /**
   * 单步前进
   */
  const handleStepForward = useCallback(() => {
    setCurrentIndex((prev) => Math.min(prev + 1, klines.length - 1));
  }, [klines.length]);

  /**
   * 单步后退
   */
  const handleStepBackward = useCallback(() => {
    setCurrentIndex((prev) => Math.max(prev - 1, 0));
  }, []);

  /**
   * 快进
   */
  const handleFastForward = useCallback(() => {
    setCurrentIndex((prev) => Math.min(prev + fastForwardStep, klines.length - 1));
  }, [fastForwardStep, klines.length]);

  /**
   * 快退
   */
  const handleFastBackward = useCallback(() => {
    setCurrentIndex((prev) => Math.max(prev - fastForwardStep, 0));
  }, [fastForwardStep]);

  /**
   * 改变播放速度
   */
  const handleSpeedChange = useCallback(
    (value: number) => {
      setPlaySpeed(value);
      if (isPlaying) {
        handlePause();
        setTimeout(() => {
          handlePlay();
        }, 0);
      }
    },
    [isPlaying, handlePause, handlePlay]
  );

  /**
   * 进度条变化
   */
  const handleProgressChange = useCallback((value: number) => {
    setCurrentIndex(value);
  }, []);

  /**
   * 返回数据管理页面
   */
  const handleBack = useCallback(() => {
    if (returnState?.returnPath) {
      // 使用保存的状态返回
      navigate(returnState.returnPath + (returnState.returnSearch || ''), {
        state: { pageState: returnState.pageState },
      });
    } else {
      navigate('/data-management');
    }
  }, [navigate, returnState]);

  /**
   * 处理时间范围变化
   */
  const handleDateRangeChange = useCallback((dates: any) => {
    setDateRange(dates);
  }, []);

  /**
   * 处理周期变化
   */
  const handleIntervalChange = useCallback((value: string) => {
    setInterval(value);
  }, []);

  // 组件挂载时加载数据
  useEffect(() => {
    loadKlines();
  }, [loadKlines]);

  // 数据加载完成后初始化图表
  useEffect(() => {
    if (klines.length > 0 && chartRef.current) {
      initChart();
    }
  }, [klines, initChart]);

  // 当前索引变化时更新图表
  useEffect(() => {
    if (klines.length > 0) {
      updateChartDisplay(currentIndex);
    }
  }, [currentIndex, klines.length, updateChartDisplay]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (playTimerRef.current) {
        window.clearInterval(playTimerRef.current);
      }
      if (chartRef.current) {
        dispose(chartRef.current);
      }
    };
  }, []);

  // 渲染加载状态
  if (loading) {
    return (
      <PageContainer title="K线回放">
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '100px 0' }}>
          <Spin size="large" tip="加载K线数据中..." />
        </div>
      </PageContainer>
    );
  }

  // 渲染错误状态
  if (error) {
    return (
      <PageContainer title="K线回放">
        <Card>
          <Alert
            message="加载失败"
            description={error}
            type="error"
            showIcon
            action={
              <Button type="primary" onClick={loadKlines}>
                重试
              </Button>
            }
          />
          <div style={{ marginTop: 16 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={handleBack}>
              返回数据管理
            </Button>
          </div>
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer title={`K线回放 - ${symbol} (${interval})`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* 控制栏 */}
        <Card size="small" title="回放控制">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {/* 第一行：时间范围和周期选择 */}
            <Row align="middle" gutter={[16, 16]}>
              <Col xs={24} lg={12} xl={10}>
                <Space wrap>
                  <CalendarOutlined />
                  <span>时间范围:</span>
                  <RangePicker
                    showTime
                    value={dateRange}
                    onChange={handleDateRangeChange}
                    style={{ width: '100%', maxWidth: 320 }}
                    disabled={isPlaying}
                  />
                </Space>
              </Col>
              <Col xs={12} sm={8} lg={6} xl={5}>
                <Space>
                  <ClockCircleOutlined />
                  <span>周期:</span>
                  <Select
                    value={interval}
                    onChange={handleIntervalChange}
                    style={{ width: 100 }}
                    disabled={isPlaying}
                  >
                    {INTERVAL_OPTIONS.map((opt) => (
                      <Option key={opt.value} value={opt.value}>
                        {opt.label}
                      </Option>
                    ))}
                  </Select>
                </Space>
              </Col>
              <Col xs={12} sm={16} lg={6} xl={9}>
                <Space wrap>
                  <Button type="primary" onClick={loadKlines} disabled={isPlaying}>
                    加载数据
                  </Button>
                  <Button onClick={handleBack} icon={<ArrowLeftOutlined />}>
                    返回
                  </Button>
                </Space>
              </Col>
            </Row>

            {/* 第二行：播放控制按钮 */}
            <Row align="middle" gutter={[16, 16]} wrap>
              <Col xs={24} sm={12} lg="auto">
                <Space wrap>
                  <Tooltip title="单步后退">
                    <Button
                      icon={<StepBackwardOutlined />}
                      onClick={handleStepBackward}
                      disabled={currentIndex === 0 || isPlaying}
                    />
                  </Tooltip>
                  <Tooltip title={isPlaying ? '暂停' : '播放'}>
                    <Button
                      type="primary"
                      icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
                      onClick={isPlaying ? handlePause : handlePlay}
                      disabled={klines.length === 0}
                    >
                      {isPlaying ? '暂停' : '播放'}
                    </Button>
                  </Tooltip>
                  <Tooltip title="停止并重置">
                    <Button
                      icon={<StopOutlined />}
                      onClick={handleStop}
                      disabled={currentIndex === 0 || klines.length === 0}
                    >
                      终止
                    </Button>
                  </Tooltip>
                  <Tooltip title="单步前进">
                    <Button
                      icon={<StepForwardOutlined />}
                      onClick={handleStepForward}
                      disabled={currentIndex >= klines.length - 1 || isPlaying}
                    />
                  </Tooltip>
                </Space>
              </Col>
              <Col xs={24} sm={12} lg="auto">
                <Space wrap>
                  <Tooltip title="快退">
                    <Button
                      icon={<FastForwardOutlined style={{ transform: 'rotate(180deg)' }} />}
                      onClick={handleFastBackward}
                      disabled={currentIndex === 0 || klines.length === 0}
                    >
                      快退
                    </Button>
                  </Tooltip>
                  <Select
                    value={fastForwardStep}
                    onChange={setFastForwardStep}
                    style={{ width: 80 }}
                    disabled={isPlaying}
                  >
                    {FAST_FORWARD_STEPS.map((opt) => (
                      <Option key={opt.value} value={opt.value}>
                        {opt.label}
                      </Option>
                    ))}
                  </Select>
                  <Tooltip title="快进">
                    <Button
                      icon={<FastForwardOutlined />}
                      onClick={handleFastForward}
                      disabled={currentIndex >= klines.length - 1 || klines.length === 0}
                    >
                      快进
                    </Button>
                  </Tooltip>
                </Space>
              </Col>
              <Col>
                <Space>
                  <span>播放速度:</span>
                  <Select
                    value={playSpeed}
                    onChange={handleSpeedChange}
                    style={{ width: 90 }}
                  >
                    {SPEED_OPTIONS.map((opt) => (
                      <Option key={opt.value} value={opt.value}>
                        {opt.label}
                      </Option>
                    ))}
                  </Select>
                </Space>
              </Col>
            </Row>

            {/* 第三行：进度条 */}
            <Row align="middle">
              <Col flex="none">
                <Badge
                  count={`${currentIndex + 1} / ${klines.length}`}
                  style={{ backgroundColor: '#1890ff' }}
                />
              </Col>
              <Col flex="auto" style={{ padding: '0 16px' }}>
                <Slider
                  min={0}
                  max={Math.max(klines.length - 1, 0)}
                  value={currentIndex}
                  onChange={handleProgressChange}
                  disabled={klines.length === 0}
                  tooltip={{
                    formatter: (value) => formatTimestamp(klines[value || 0]?.timestamp),
                  }}
                />
              </Col>
              <Col flex="none">
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {formatTimestamp(klines[currentIndex]?.timestamp)}
                </Text>
              </Col>
            </Row>
          </Space>
        </Card>

        {/* 统计信息 */}
        {klines.length > 0 && (
          <Card size="small">
            <Row gutter={[16, 16]}>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title="总K线数"
                  value={stats.totalKlines}
                  prefix={<HistoryOutlined />}
                />
              </Col>
              <Col xs={12} sm={6} md={5}>
                <Statistic title="开始时间" value={stats.startTime} />
              </Col>
              <Col xs={12} sm={6} md={5}>
                <Statistic title="结束时间" value={stats.endTime} />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title="最高价"
                  value={stats.highestPrice}
                  precision={2}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Statistic
                  title="最低价"
                  value={stats.lowestPrice}
                  precision={2}
                  valueStyle={{ color: '#f5222d' }}
                />
              </Col>
              <Col xs={12} sm={6} md={2}>
                <Statistic title="总成交量" value={stats.totalVolume.toFixed(0)} />
              </Col>
            </Row>
          </Card>
        )}

        {/* 图表区域 */}
        <Card styles={{ body: { padding: 0 } }}>
          <div
            ref={chartRef}
            style={{
              width: '100%',
              height: '500px',
              minHeight: '400px',
            }}
          />
        </Card>
      </div>
    </PageContainer>
  );
};

// 导入Typography.Text
import { Typography } from 'antd';
const { Text } = Typography;

export default KlineReplayPage;
