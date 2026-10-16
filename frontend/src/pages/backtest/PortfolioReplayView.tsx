/**
 * 全局视角（组合）回测回放
 * 时钟是覆盖全部品种的统一时间网格；账户数字为各独立资金池合并口径；
 * 持仓由跨品种成交流重建。主图保留单品种 K 线作为行情背景（可切换品种）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Divider,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CaretRightOutlined,
  PauseOutlined,
  StepForwardOutlined,
  StopOutlined,
  FastForwardOutlined,
  ClockCircleOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { init, dispose, registerOverlay } from 'klinecharts';
import type { Chart, DataLoaderGetBarsParams, KLineData, PeriodType } from 'klinecharts';
import EChart from '@/components/EChart';
import type { EChartsOption } from 'echarts';
import TradeTable, { type Trade as TradeTableTrade } from '@/components/TradeTable';
import { useQuantColors } from '@/utils/colors';
import jsonAnnotation from '../../utils/klineAnnotations';
import { backtestApi } from '../../api';
import type {
  PortfolioAccountPoint,
  PortfolioPositionEvent,
  PortfolioReplayData,
  ReplayKline,
  ReplayTrade,
} from '../../types/backtest';

// 与品种视角统一的速度枚举：覆盖 1x~128x，合并两套档位
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

const formatDateTime = (ms: number): string =>
  new Date(ms).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

/** 二分：返回 arr 中满足 pick(item) <= key 的元素个数 */
function bisectRight<T>(arr: T[], key: number, pick: (item: T) => number): number {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (pick(arr[mid]) <= key) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

const toChartKlines = (klines: ReplayKline[]): KLineData[] =>
  klines.map((k) => ({
    timestamp: Number(k.timestamp ?? k.time) || 0,
    open: Number(k.open) || 0,
    high: Number(k.high) || 0,
    low: Number(k.low) || 0,
    close: Number(k.close) || 0,
    volume: Number(k.volume) || 0,
  }));

const parseInterval = (interval: string): { span: number; type: PeriodType } => {
  const span = parseInt(interval.match(/\d+/)?.[0] ?? '15', 10);
  switch (interval.replace(/\d+/, '').toLowerCase()) {
    case 'h': return { span, type: 'hour' };
    case 'd': return { span, type: 'day' };
    default: return { span, type: 'minute' };
  }
};

// ---- 当前持仓表行 ----
interface HoldingRow {
  symbol: string;
  qty: number;
  avg_cost: number;
  price: number;
  market_value: number;
  unrealized_pnl: number;
}

// 行情背景卡片固定高度：K 线容器必须在挂载时就拿到确定高度，klinecharts 才不会把主图区算成 0
const CHART_HEIGHT = 480;

// ---- 单品种 K 线行情背景（时钟来自父组件，只按时间切片显示）----
// 父组件用 key={symbol} + 条件渲染保证：本组件挂载时 klines 已就绪且容器高度确定
interface KlineBackgroundProps {
  symbol: string;
  interval: string;
  klines: ReplayKline[];
  trades: ReplayTrade[];
  currentMs: number;
}

const KlineBackground = ({ symbol, interval, klines, trades, currentMs }: KlineBackgroundProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  // 已渲染到的 K 线索引，时钟推进但未跨 K 线时不重绘（32~128 格/秒下避免无意义刷新）
  const lastKlineIndexRef = useRef<number>(-2);
  // 全局时钟早于该品种首根 K 线时提示
  const [noDataYet, setNoDataYet] = useState(false);
  const colors = useQuantColors();

  // K 线时间戳序列在同品种内不变，只算一次
  const klineTimes = useMemo(() => klines.map((k) => Number(k.timestamp ?? k.time) || 0), [klines]);

  // 按当前时刻切片最近 100 根 K 线并叠加窗口内成交标记
  const renderFrame = useCallback(
    (chart: Chart, nowMs: number) => {
      const kIdx = bisectRight(klineTimes, nowMs, (v) => v) - 1;
      if (kIdx === lastKlineIndexRef.current) return;
      lastKlineIndexRef.current = kIdx;
      setNoDataYet(kIdx < 0);

      // 清掉上一窗口的成交标记后按新窗口重绘
      chart.getOverlays({ name: 'jsonAnnotation' })?.forEach((o) => {
        chart.removeOverlay({ id: o.id });
      });

      if (kIdx < 0) {
        // 时钟尚早：该品种此时还没有行情，画面留空
        chart.setDataLoader({ getBars: (params: DataLoaderGetBarsParams) => params.callback([]) });
        return;
      }

      const WINDOW = 100;
      const startIndex = Math.max(0, kIdx - WINDOW + 1);
      const windowKlines = klines.slice(startIndex, kIdx + 1);
      chart.setDataLoader({
        getBars: (params: DataLoaderGetBarsParams) => {
          params.callback(toChartKlines(windowKlines));
        },
      });

      const winStart = klineTimes[startIndex];
      const winEnd = klineTimes[kIdx];
      // round-trip 契约：每条记录展开为开仓/平仓两个标记（side 即开仓方向 buy）
      trades.forEach((tr) => {
        const marks: Array<{ ms: number; price: number; label: string }> = [
          { ms: tr.timestamp * 1000, price: tr.entry_price, label: '买入' },
        ];
        if (tr.exit_timestamp) {
          marks.push({ ms: tr.exit_timestamp * 1000, price: tr.exit_price, label: '卖出' });
        }
        marks.forEach((mk) => {
          if (mk.ms < winStart || mk.ms > winEnd) return;
          chart.createOverlay({
            name: 'jsonAnnotation',
            extendData: JSON.stringify({
              lines: [mk.label, `数量: ${tr.size.toFixed(4)}`],
              colors: [mk.label === '买入' ? colors.positive : colors.negative, '#ffffff'],
              fontSize: 12,
              align: 'left',
            }),
            points: [{ timestamp: mk.ms, value: mk.price }],
          });
        });
      });
    },
    // colors 每渲染派生新对象，由 lastKlineIndexRef 去重保证不会重绘，不入 deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [klineTimes, klines, trades],
  );

  // 挂载即初始化（klines 由父组件条件渲染保证就绪）
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    registerOverlay(jsonAnnotation);
    const chart = init(el, { locale: 'zh-CN' });
    if (!chart) return;
    chartRef.current = chart;
    const periodInfo = parseInterval(interval);
    chart.setPeriod({ span: periodInfo.span, type: periodInfo.type });
    chart.setSymbol({ ticker: symbol });
    chart.resize();
    // 首帧布局可能在 effect 后才完成，rAF 再 resize 一次兜底
    const raf = requestAnimationFrame(() => chart.resize());
    // 侧栏折叠/窗口缩放时容器尺寸会变，用 RO 保证主图区跟随
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(el);
    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      dispose(el);
      chartRef.current = null;
      lastKlineIndexRef.current = -2;
    };
  }, [symbol, interval]);

  // 时钟推进
  useEffect(() => {
    if (chartRef.current) renderFrame(chartRef.current, currentMs);
  }, [currentMs, renderFrame]);

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%' }}>
      {noDataYet && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: colors.neutral,
            pointerEvents: 'none',
            zIndex: 2,
          }}
        >
          全局时钟早于该品种行情起点，暂无 K 线
        </div>
      )}
    </div>
  );
};

// ============================== 主组件 ==============================
interface PortfolioReplayViewProps {
  backtestId: string;
  symbols: string[];
}

const PortfolioReplayView = ({ backtestId, symbols }: PortfolioReplayViewProps) => {
  const { message } = App.useApp();
  const colors = useQuantColors();

  const [data, setData] = useState<PortfolioReplayData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bgSymbol, setBgSymbol] = useState(symbols[0] ?? '');
  const [bgKlines, setBgKlines] = useState<ReplayKline[]>([]);
  const [bgTrades, setBgTrades] = useState<ReplayTrade[]>([]);
  // 首个品种挂载即加载，初始按加载中渲染占位
  const [bgLoading, setBgLoading] = useState(true);

  // 时钟
  const [gridIndex, setGridIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(32);
  const [lastFilledTs, setLastFilledTs] = useState<number | null>(null);
  const timerRef = useRef<number | null>(null);

  // 加载组合回放数据
  useEffect(() => {
    let cancelled = false;
    backtestApi
      .getPortfolioReplay(backtestId)
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((err) => {
        console.error('加载全局回放数据失败:', err);
        if (!cancelled) setError('加载全局回放数据失败');
      });
    return () => {
      cancelled = true;
    };
  }, [backtestId]);

  // 加载行情背景品种的 K 线（复用单品种 replay 接口，K 线不进组合接口）
  useEffect(() => {
    if (!bgSymbol) return;
    let cancelled = false;
    setBgLoading(true);
    backtestApi
      .getReplayData(backtestId, bgSymbol)
      .then((res) => {
        if (cancelled) return;
        setBgKlines(res.kline_data ?? []);
        setBgTrades(res.trades ?? []);
      })
      .catch((err) => {
        console.error('加载行情背景失败:', err);
        message.error('加载行情背景失败');
      })
      .finally(() => {
        if (!cancelled) setBgLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [backtestId, bgSymbol, message]);

  // 卸载清理定时器
  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

  const maxIndex = (data?.grid_count ?? 1) - 1;
  const currentMs = data ? data.start_ms + gridIndex * data.grid_step_ms : 0;

  const handlePause = useCallback(() => {
    setPlaying(false);
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const handlePlay = useCallback(() => {
    if (!data || gridIndex >= maxIndex) return;
    setPlaying(true);
    timerRef.current = window.setInterval(() => {
      setGridIndex((prev) => {
        if (prev >= maxIndex) {
          handlePause();
          return prev;
        }
        return prev + 1;
      });
    }, 1000 / speed);
  }, [data, gridIndex, maxIndex, speed, handlePause]);

  const handleStop = () => {
    handlePause();
    setGridIndex(0);
  };

  const handleSpeedChange = (value: number) => {
    setSpeed(value);
    if (playing) {
      handlePause();
      // 等待 state 提交后用新速度重启
      window.setTimeout(() => {
        setPlaying(true);
        timerRef.current = window.setInterval(() => {
          setGridIndex((prev) => {
            if (prev >= maxIndex) {
              setPlaying(false);
              return prev;
            }
            return prev + 1;
          });
        }, 1000 / value);
      }, 0);
    }
  };

  // 事件步进：跳到下一个有成交的网格点
  const nextEventIndex = useMemo(() => {
    if (!data) return null;
    const idx = bisectRight<PortfolioPositionEvent>(data.position_events, currentMs, (e) => e.t);
    const next = data.position_events[idx];
    if (!next) return null;
    return Math.round((next.t - data.start_ms) / data.grid_step_ms);
  }, [data, currentMs]);

  // ---- 当前账户（稀疏序列 ffill，起点前取初始权益）----
  const account = useMemo(() => {
    if (!data) return null;
    const idx = bisectRight<PortfolioAccountPoint>(data.account, currentMs, (p) => p[0]);
    if (idx === 0) {
      return { equity: data.init_cash, balance: data.init_cash, margin: 0, cum_pnl: 0, drawdown: 0, day_pnl: 0 };
    }
    const p = data.account[idx - 1];
    return { equity: p[1], balance: p[2], margin: p[3], cum_pnl: p[4], drawdown: p[5], day_pnl: p[6] };
  }, [data, currentMs]);

  // ---- 当前持仓：扫描截至当前的事件，取每品种最新状态 ----
  // ponytail: 每帧 O(事件数) 线性扫描，3453 事件 × 128 格/秒量级无压力；
  // 若未来事件上万且掉帧，升级为「网格索引 -> 事件指针」增量维护
  const holdings = useMemo<HoldingRow[]>(() => {
    if (!data) return [];
    const latest = new Map<string, PortfolioPositionEvent>();
    for (const ev of data.position_events) {
      if (ev.t > currentMs) break;
      latest.set(ev.symbol, ev);
    }
    const rows: HoldingRow[] = [];
    latest.forEach((ev, symbol) => {
      if (ev.qty === 0) return;
      const prices = data.holding_prices[symbol] ?? [];
      const priceIdx = bisectRight<[number, number]>(prices, currentMs, (p) => p[0]) - 1;
      const price = priceIdx >= 0 ? prices[priceIdx][1] : ev.avg_cost;
      rows.push({
        symbol,
        qty: ev.qty,
        avg_cost: ev.avg_cost,
        price,
        market_value: price * Math.abs(ev.qty),
        unrealized_pnl: (price - ev.avg_cost) * ev.qty,
      });
    });
    return rows;
  }, [data, currentMs]);

  // ---- 截至当前的跨品种成交流（round-trip 契约 timestamp 为秒级必填）----
  const tradeTimes = useMemo(() => (data?.trades ?? []).map((tr) => tr.timestamp), [data]);
  const filledCount = data ? bisectRight<number>(tradeTimes, currentMs / 1000, (v) => v) : 0;

  // 新契约记录直接透传（后端已带 trade_id/symbol）
  const allTableTrades = useMemo<TradeTableTrade[]>(() => data?.trades ?? [], [data]);

  // 新成交出现时记录最新一笔的时间戳（用于行高亮）
  const filledCountRef = useRef(0);
  useEffect(() => {
    if (filledCount > filledCountRef.current && filledCount > 0) {
      setLastFilledTs(tradeTimes[filledCount - 1]);
    }
    filledCountRef.current = filledCount;
  }, [filledCount, tradeTimes]);

  // ---- 组合权益曲线（生长 + 当前时刻游标）----
  const equityOption = useMemo<EChartsOption | null>(() => {
    if (!data) return null;
    const accIdx = bisectRight<PortfolioAccountPoint>(data.account, currentMs, (p) => p[0]);
    const visible = data.account.slice(0, accIdx);
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '3%', bottom: '12%', top: '12%', containLabel: true },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: colors.chartAxis } },
        axisLabel: { color: colors.neutral },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: colors.neutral },
        splitLine: { lineStyle: { color: colors.chartSplit } },
      },
      dataZoom: [{ type: 'inside' }],
      series: [
        {
          name: '组合权益',
          type: 'line',
          symbol: 'none',
          lineStyle: { width: 2, color: colors.chartLine },
          areaStyle: { opacity: 0.08 },
          data: visible.map((p) => [p[0], p[1]]),
          markLine: {
            symbol: 'none',
            silent: true,
            label: { show: false },
            lineStyle: { color: colors.info, type: 'dashed', width: 1 },
            data: [{ xAxis: currentMs }],
          },
        },
      ],
    };
  }, [data, currentMs, colors]);

  // ---- 持仓表列 ----
  const holdingColumns: ColumnsType<HoldingRow> = [
    { title: '品种', dataIndex: 'symbol', key: 'symbol' },
    {
      title: '方向',
      dataIndex: 'qty',
      key: 'side',
      width: 80,
      render: (qty: number) =>
        qty > 0 ? <Tag color="green">多</Tag> : <Tag color="red">空</Tag>,
    },
    {
      title: '数量',
      dataIndex: 'qty',
      key: 'qty',
      align: 'right',
      render: (qty: number) => Math.abs(qty).toFixed(6),
    },
    { title: '均价', dataIndex: 'avg_cost', key: 'avg_cost', align: 'right', render: (v: number) => v.toFixed(4) },
    { title: '现价', dataIndex: 'price', key: 'price', align: 'right', render: (v: number) => v.toFixed(4) },
    { title: '市值', dataIndex: 'market_value', key: 'market_value', align: 'right', render: (v: number) => v.toFixed(2) },
    {
      title: '浮动盈亏',
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      align: 'right',
      render: (v: number) => (
        <span style={{ color: v >= 0 ? colors.positive : colors.negative }}>{v.toFixed(2)}</span>
      ),
    },
  ];

  if (error) {
    return <Alert title="错误" description={error} type="error" showIcon />;
  }
  if (!data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '96px 0' }}>
        {/* 与品种视角切 symbol/视角时的加载动画保持一致：纯大 Spin 无文字 */}
        <Spin size="large" />
      </div>
    );
  }

  const pnlColor = (v: number) => (v >= 0 ? colors.positive : colors.negative);

  return (
    <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
      <Alert
        type="info"
        showIcon
        title="组合口径说明"
        description="本次回测各品种使用独立资金池，账户数字为各品种权益的汇总；持仓由跨品种成交流重建（现货双向口径），与单品种视角的持仓记录可能存在口径差异。"
      />

      {/* 时钟控制栏 */}
      <Card size="small">
        <Row align="middle" justify="space-between" gutter={[16, 16]}>
          <Col flex="none">
            <Space align="center">
              <GlobalOutlined style={{ fontSize: 18, color: colors.info }} />
              <span style={{ fontWeight: 500 }}>全局时钟</span>
              <Tag>{data.interval}</Tag>
            </Space>
          </Col>
          <Col flex="auto" style={{ textAlign: 'center' }}>
            <Space size="small" align="center">
              <Tooltip title="停止并回到起点">
                <Button
                  type="text"
                  shape="circle"
                  icon={<StopOutlined />}
                  onClick={handleStop}
                  disabled={gridIndex === 0}
                  style={{ color: gridIndex === 0 ? undefined : colors.negative, fontSize: 18 }}
                />
              </Tooltip>
              <Button
                type="primary"
                shape="circle"
                size="large"
                icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
                onClick={playing ? handlePause : handlePlay}
                disabled={gridIndex >= maxIndex}
                style={{ width: 48, height: 48, fontSize: 20, boxShadow: '0 2px 8px rgba(24, 144, 255, 0.35)' }}
              />
              <Tooltip title="前进一格">
                <Button
                  type="text"
                  shape="circle"
                  icon={<StepForwardOutlined />}
                  onClick={() => setGridIndex((v) => Math.min(v + 1, maxIndex))}
                  disabled={gridIndex >= maxIndex}
                  style={{ fontSize: 16 }}
                />
              </Tooltip>
              <Tooltip title="跳到下一成交">
                <Button
                  type="text"
                  shape="circle"
                  icon={<FastForwardOutlined />}
                  onClick={() => nextEventIndex !== null && setGridIndex(nextEventIndex)}
                  disabled={nextEventIndex === null || nextEventIndex <= gridIndex}
                  style={{ fontSize: 16 }}
                />
              </Tooltip>
              <Divider orientation="vertical" style={{ margin: '0 8px' }} />
              <Tooltip title="播放速度">
                <Space align="center">
                  <ClockCircleOutlined style={{ color: colors.neutral }} />
                  <Select
                    value={speed}
                    onChange={handleSpeedChange}
                    style={{ width: 76 }}
                    variant="borderless"
                    popupMatchSelectWidth={false}
                    options={SPEED_OPTIONS}
                  />
                </Space>
              </Tooltip>
            </Space>
          </Col>
          <Col flex="none">
            <Space align="center" style={{ border: '1px solid var(--ant-color-border)', borderRadius: 4, padding: '4px 12px' }}>
              <ClockCircleOutlined style={{ color: colors.neutral }} />
              <span style={{ fontFamily: 'monospace' }}>{formatDateTime(currentMs)}</span>
            </Space>
          </Col>
        </Row>
        <Row align="middle" gutter={[16, 0]} style={{ marginTop: 8 }}>
          <Col flex="none" style={{ fontSize: 12, color: colors.neutral, fontFamily: 'monospace' }}>
            {gridIndex + 1}
          </Col>
          <Col flex="auto" style={{ padding: '0 8px' }}>
            <Slider
              min={0}
              max={maxIndex}
              value={gridIndex}
              onChange={setGridIndex}
              tooltip={{ formatter: (v) => formatDateTime(data.start_ms + (v ?? 0) * data.grid_step_ms) }}
            />
          </Col>
          <Col flex="none" style={{ fontSize: 12, color: colors.neutral, fontFamily: 'monospace' }}>
            {data.grid_count}
          </Col>
        </Row>
      </Card>

      {/* 账户状态条 */}
      {account && (
        <Card size="small">
          <Row gutter={[16, 16]}>
            <Col xs={12} md={8} lg={4}>
              <Statistic title="总权益" value={account.equity} precision={2} />
            </Col>
            <Col xs={12} md={8} lg={4}>
              <Statistic title="可用余额" value={account.balance} precision={2} />
            </Col>
            <Col xs={12} md={8} lg={4}>
              <Statistic title="保证金" value={account.margin} precision={2} />
            </Col>
            <Col xs={12} md={8} lg={4}>
              <Statistic
                title="累计盈亏"
                value={account.cum_pnl}
                precision={2}
                styles={{ content: { color: pnlColor(account.cum_pnl) } }}
              />
            </Col>
            <Col xs={12} md={8} lg={4}>
              <Statistic
                title="当日盈亏"
                value={account.day_pnl}
                precision={2}
                styles={{ content: { color: pnlColor(account.day_pnl) } }}
              />
            </Col>
            <Col xs={12} md={8} lg={4}>
              <Statistic
                title="最大回撤(当期)"
                value={account.drawdown * 100}
                precision={2}
                suffix="%"
                styles={{ content: { color: account.drawdown < 0 ? colors.negative : undefined } }}
              />
            </Col>
          </Row>
        </Card>
      )}

      {/* 行情背景 K 线：条件渲染保证图表容器挂载时数据就绪、父级高度确定 */}
      <Card
        size="small"
        title="行情背景（单品种）"
        extra={
          <Select
            value={bgSymbol}
            onChange={setBgSymbol}
            style={{ width: 160 }}
            options={symbols.map((s) => ({ label: s, value: s }))}
          />
        }
        styles={{ body: { height: CHART_HEIGHT, padding: 0, overflow: 'hidden' } }}
      >
        {bgLoading ? (
          <div style={{ height: CHART_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin />
          </div>
        ) : bgKlines.length === 0 ? (
          <div style={{ height: CHART_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', color: colors.neutral }}>
            该品种无行情数据
          </div>
        ) : (
          <KlineBackground
            key={bgSymbol}
            symbol={bgSymbol}
            interval={data.interval}
            klines={bgKlines}
            trades={bgTrades}
            currentMs={currentMs}
          />
        )}
      </Card>

      {/* 组合权益曲线 */}
      <Card size="small" title="组合权益曲线">
        {equityOption ? (
          <EChart option={equityOption} style={{ height: 300, width: '100%' }} opts={{ renderer: 'canvas' }} />
        ) : (
          <div style={{ height: 300 }} />
        )}
      </Card>

      {/* 当前持仓 */}
      <Card size="small" title={`当前持仓（${holdings.length} 个品种）`}>
        <Table<HoldingRow>
          rowKey="symbol"
          size="small"
          columns={holdingColumns}
          dataSource={holdings}
          pagination={false}
          locale={{ emptyText: '当前无持仓' }}
        />
      </Card>

      {/* 跨品种成交流 */}
      <Card size="small" title="跨品种成交流">
        <div style={{ marginBottom: 12, color: colors.neutral }}>
          已成交 {filledCount} / {data.trades.length} 笔
        </div>
        <TradeTable
          data={allTableTrades.slice(0, filledCount)}
          pagination
          rowClassName={(record) => (record.timestamp === lastFilledTs ? 'portfolio-new-trade' : '')}
        />
      </Card>
    </Space>
  );
};

export default PortfolioReplayView;
