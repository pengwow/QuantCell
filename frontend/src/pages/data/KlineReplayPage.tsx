import { QUANT_COLORS } from '@/utils/colors';
/**
 * 行情回放页：基于历史K线的「时间机器」——只喂给图表已播放的 bar，
 * 指标在截断数组上计算，避免未来函数偷看。
 * 数据按块游标加载（chunk=2000），前进预取 / 回退补块，支持超大历史窗口回放。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Flex,
  Form,
  Input,
  Row,
  Select,
  Slider,
  Space,
  Tooltip,
} from 'antd';
import {
  CaretRightOutlined,
  PauseOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import type { KLineData } from 'klinecharts';
import { dataApi } from '@/api/dataApi';
import ChartShell, { type ChartShellHandle } from '@/components/chart/ChartShell';
import { PERIOD_BAR_ITEMS } from '@/components/chart/chartConstants';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { useTranslation } from 'react-i18next';

// 回放配置：分块大小、预取比例、播放节奏与速度边界（播放间隔一律由此推算）
const REPLAY_CONFIG = {
  chunkSize: 2000, // 每块加载的 bar 数
  prefetchRatio: 0.2, // 播到块尾前该比例处预取下一块；退到块头该比例处向前补块
  baseIntervalMs: 500, // 1x 速度下每根 bar 的间隔
  minSpeed: 0.25,
  maxSpeed: 64,
  stepMs: 1000, // 「跳到时间」输入为秒级精度（DatePicker showTime）
};

// 速度档位（2 的幂，min/max 之外不提供）
const SPEED_STEPS = [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64];

// 回放偏好（品种 / 周期 / 起始时间），下次进入自动回填
const LAST_KEY = 'qc:market-replay:last';

const formatTs = (ts?: number) => (ts ? dayjs(ts).format('YYYY-MM-DD HH:mm:ss') : '-');

// 周期字符串 → 毫秒（分块请求按相邻块时间衔接需要）
const intervalToMs = (interval: string): number => {
  const m = interval.match(/^(\d+)([mhdwMy])$/);
  if (!m) return 60 * 60 * 1000;
  const n = parseInt(m[1], 10);
  switch (m[2]) {
    case 'm':
      return n * 60_000;
    case 'h':
      return n * 3_600_000;
    case 'd':
      return n * 86_400_000;
    case 'w':
      return n * 7 * 86_400_000;
    case 'M':
      return n * 30 * 86_400_000;
    case 'y':
      return n * 365 * 86_400_000;
    default:
      return 60 * 60 * 1000;
  }
};

// 二分查找第一个 timestamp >= ts 的下标（「跳到时间」用）
const lowerBound = (bars: KLineData[], ts: number): number => {
  let lo = 0;
  let hi = bars.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].timestamp < ts) lo = mid + 1;
    else hi = mid;
  }
  return lo;
};

interface ReplayParams {
  symbol?: string;
  startDate?: Dayjs | null;
}

const KlineReplayPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const location = useLocation();
  // 行情回放从数据管理页进入，属于详情级页面，返回入口与其他详情页统一
  const navigate = useNavigate();
  const handleBack = useCallback(() => navigate('/data-management'), [navigate]);

  useEffect(() => {
    setPageTitle(t('market_replay') || '行情回放');
  }, [t]);

  const shellRef = useRef<ChartShellHandle>(null);

  // ===== 启动表单 =====
  const [form] = Form.useForm();

  // ===== 会话状态 =====
  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [period, setPeriod] = useState('1h');
  const [loadError, setLoadError] = useState<string | null>(null);

  // ===== 播放状态 =====
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [barsCount, setBarsCount] = useState(0);
  const [atStart, setAtStart] = useState(false); // 左侧已无更早数据
  const [atEnd, setAtEnd] = useState(false); // 右侧已无更多数据

  // ===== 游标引用（播放引擎读 ref，避免闭包过期）=====
  const barsRef = useRef<KLineData[]>([]);
  const indexRef = useRef(0);
  const periodSwitchingRef = useRef(false); // 周期切换防连点：请求在途时忽略周期栏点击
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const rafRef = useRef(0);
  const lastFrameRef = useRef(0);
  const accumRef = useRef(0); // 距上一整根 bar 的播放进度余数
  const chunkLoadingRef = useRef(false);
  const pastExhaustedRef = useRef(false); // 前面（更早）没有数据
  const futureExhaustedRef = useRef(false); // 后面没有更多数据
  const sessionParamsRef = useRef<ReplayParams | null>(null); // 当前会话启动参数，重置用
  const symbolRef = useRef(symbol);
  const periodRef = useRef(period);
  const intervalMsRef = useRef(60 * 60 * 1000);

  symbolRef.current = symbol;
  periodRef.current = period;
  intervalMsRef.current = intervalToMs(period);

  // 统一喂数：图表读 barsRef 截断到当前索引；本地指标在截断数组上重算。
  // 回补/预取会整块前插或追加数据（游标索引随之前后平移），klinecharts 重载数据
  // 后的可见区不一定锚定在游标上（实测回补后视口会停在历史段），因此喂数后
  // 显式滚动到当前 bar，保证图表可见区与回放游标一致。
  const feed = useCallback(() => {
    shellRef.current?.refreshData();
    shellRef.current?.recalculateIndicators();
    // 需后端执行的自定义指标重算（内部 1s 节流 + 在途门闩，播放中不会每根一个请求）
    shellRef.current?.recalcBackendIndicators();
    shellRef.current?.getChart()?.scrollToDataIndex(indexRef.current);
  }, []);

  // 拉一块数据：order=asc 从 start 向后取，order=desc 从 end 向前取；后端返回恒为升序
  const fetchChunk = useCallback(
    async (sym: string, per: string, opts: { startMs?: number; endMs?: number }) => {
      const resp = await dataApi.getKlines({
        symbol: sym,
        interval: per,
        limit: REPLAY_CONFIG.chunkSize,
        ...(opts.startMs !== undefined
          ? { start_time: opts.startMs, order: 'asc' }
          : { end_time: opts.endMs, order: 'desc' }),
      });
      const raw = Array.isArray(resp) ? resp : resp.data ?? resp.klines ?? [];
      return raw as KLineData[];
    },
    []
  );

  // 设置当前索引（含进度状态推导），不喂数——由调用方决定是否 feed
  const applyIndex = useCallback((idx: number) => {
    const bars = barsRef.current;
    const clamped = Math.max(0, Math.min(idx, bars.length - 1));
    indexRef.current = clamped;
    setCurrentIndex(clamped);
    setAtStart(clamped === 0 && pastExhaustedRef.current);
  }, []);

  // 向前预取：播到块尾前 prefetchRatio 时加载下一块
  const maybePrefetchNext = useCallback(async () => {
    const bars = barsRef.current;
    if (futureExhaustedRef.current || chunkLoadingRef.current || bars.length === 0) return;
    if (indexRef.current < bars.length - Math.ceil(REPLAY_CONFIG.chunkSize * REPLAY_CONFIG.prefetchRatio))
      return;
    chunkLoadingRef.current = true;
    try {
      const next = await fetchChunk(symbolRef.current, periodRef.current, {
        startMs: bars[bars.length - 1].timestamp + intervalMsRef.current,
      });
      if (next.length === 0) {
        futureExhaustedRef.current = true;
        setAtEnd(true);
        return;
      }
      barsRef.current = [...bars, ...next];
      setBarsCount(barsRef.current.length);
      if (next.length < REPLAY_CONFIG.chunkSize) {
        futureExhaustedRef.current = true;
        setAtEnd(true);
      }
    } catch (err) {
      // 分块拉取失败不中断播放，只提示；下个预取窗口会重试
      console.error('预取下一块失败:', err);
    } finally {
      chunkLoadingRef.current = false;
    }
  }, [fetchChunk]);

  // 向前补块：退到块头 prefetchRatio 内且更早还有数据时，往前补一块并平移索引。
  // 返回是否真的发生了补块（调用方据此决定喂数时机，避免中途用残缺数据刷图闪烁）
  const maybeFillPast = useCallback(async (): Promise<boolean> => {
    const bars = barsRef.current;
    if (pastExhaustedRef.current || chunkLoadingRef.current || bars.length === 0) return false;
    if (indexRef.current >= Math.ceil(REPLAY_CONFIG.chunkSize * REPLAY_CONFIG.prefetchRatio)) return false;
    chunkLoadingRef.current = true;
    try {
      const prev = await fetchChunk(symbolRef.current, periodRef.current, {
        endMs: bars[0].timestamp - 1,
      });
      if (prev.length === 0) {
        pastExhaustedRef.current = true;
        setAtStart(true);
        return false;
      }
      barsRef.current = [...prev, ...bars];
      indexRef.current += prev.length;
      setCurrentIndex(indexRef.current);
      setBarsCount(barsRef.current.length);
      if (prev.length < REPLAY_CONFIG.chunkSize) {
        pastExhaustedRef.current = true;
        setAtStart(true);
      }
      feed(); // 前插完成：窗口起点变了，必须重新喂数刷新图表
      return true;
    } catch (err) {
      console.error('补历史块失败:', err);
      return false;
    } finally {
      chunkLoadingRef.current = false;
    }
  }, [fetchChunk, feed]);

  const pause = useCallback(() => {
    playingRef.current = false;
    accumRef.current = 0;
    setIsPlaying(false);
  }, []);

  // 前进 n 根：clamp、到尽头自动暂停、触发预取
  const advanceBy = useCallback(
    (n: number) => {
      const bars = barsRef.current;
      if (bars.length === 0) return;
      const target = indexRef.current + n;
      if (n > 0 && target >= bars.length - 1) {
        applyIndex(bars.length - 1);
        if (futureExhaustedRef.current) {
          pause();
        } else {
          void maybePrefetchNext();
        }
        return;
      }
      applyIndex(target);
      if (n > 0) {
        void maybePrefetchNext();
      } else {
        void maybeFillPast(); // 后退到块头附近时向前补块
      }
      feed();
    },
    [applyIndex, feed, maybeFillPast, maybePrefetchNext, pause]
  );

  // 播放引擎：rAF 时间积累器，速度变化只影响推进速率、不重置位置
  const tick = useCallback(
    (now: number) => {
      if (playingRef.current) {
        const dt = lastFrameRef.current > 0 ? now - lastFrameRef.current : 0;
        if (dt > 0) {
          accumRef.current += (dt * speedRef.current) / REPLAY_CONFIG.baseIntervalMs;
          const whole = Math.floor(accumRef.current);
          if (whole > 0) {
            accumRef.current -= whole;
            advanceBy(whole);
          }
        }
      }
      lastFrameRef.current = now;
      rafRef.current = requestAnimationFrame(tick);
    },
    [advanceBy]
  );

  useEffect(() => {
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [tick]);

  const handlePlay = useCallback(() => {
    if (barsRef.current.length === 0) return;
    playingRef.current = true;
    lastFrameRef.current = 0;
    accumRef.current = 0;
    setIsPlaying(true);
  }, []);

  const handleStep = useCallback(
    (delta: number) => {
      pause();
      advanceBy(delta);
    },
    [advanceBy, pause]
  );

  const handleSeekIndex = useCallback(
    (idx: number) => {
      pause();
      applyIndex(idx);
      // 补块路径由补块完成后的 feed 统一刷新：若此刻立即 feed，补块请求在途时
      // 图表会先用极少数据重建（闪现只剩几根 bar），等补块返回才能恢复
      void maybeFillPast().then((filled) => {
        if (!filled) feed();
      });
    },
    [applyIndex, feed, maybeFillPast, pause]
  );

  // 跳到时间：仅在已加载窗口内定位（窗口数据随播放/预取扩展）
  const handleSeekTime = useCallback(
    (value: Dayjs | null) => {
      if (!value) return;
      const bars = barsRef.current;
      if (bars.length === 0) return;
      const ts = value.valueOf();
      if (ts < bars[0].timestamp || ts > bars[bars.length - 1].timestamp) {
        message.info(
          t('backtest_seek_range_hint', {
            start: formatTs(bars[0].timestamp),
            end: formatTs(bars[bars.length - 1].timestamp),
          })
        );
        return;
      }
      handleSeekIndex(lowerBound(bars, ts));
    },
    [handleSeekIndex, message, t]
  );

  const handleChangeSpeed = useCallback((v: number) => {
    speedRef.current = v;
    setSpeed(v);
  }, []);

  // 启动回放：从起始时间起拉第一块；周期取上次偏好/URL 值（进图后顶部可随时切，不再预选）
  const startReplay = useCallback(
    async (p: ReplayParams) => {
      const sym = (p.symbol ?? '').trim();
      const per = periodRef.current;
      const startDate = p.startDate ?? null;
      if (!sym) {
        message.warning(t('backtest_input_symbol'));
        return;
      }
      if (!startDate) {
        message.warning(t('backtest_select_start_time'));
        return;
      }
      pause();
      setLoading(true);
      setLoadError(null);
      try {
        const startMs = startDate.valueOf();
        const chunk = await fetchChunk(sym, per, { startMs });
        if (chunk.length === 0) {
          setLoadError(t('backtest_no_data_after_start', { start: formatTs(startMs), symbol: sym }));
          return;
        }
        barsRef.current = chunk;
        pastExhaustedRef.current = false;
        futureExhaustedRef.current = chunk.length < REPLAY_CONFIG.chunkSize;
        indexRef.current = 0;
        setCurrentIndex(0);
        setBarsCount(chunk.length);
        setAtStart(false);
        setAtEnd(futureExhaustedRef.current);
        setSymbol(sym);
        setPeriod(per);
        setStarted(true);
        sessionParamsRef.current = { symbol: sym, startDate: dayjs(startMs) };
        feed(); // 重置时图表已挂载，重新喂数回到首块状态；首次启动时 shell 未挂载，feed 为 no-op
        // 记住偏好，下次进入自动回填
        try {
          localStorage.setItem(LAST_KEY, JSON.stringify({ symbol: sym, period: per, startMs }));
        } catch {
          // 隐私模式等写入失败可忽略
        }
      } catch (err) {
        console.error('启动回放失败:', err);
        setLoadError(t('backtest_load_data_failed_retry'));
      } finally {
        setLoading(false);
      }
    },
    [fetchChunk, feed, message, pause, t]
  );

  // 重置回放：用当前会话的启动参数重跑 startReplay——游标回起点、补块/预取扩大的窗口
  // 也一并清空回到干净的首块状态。不禁用：即使停在起点，重置仍有「清窗口」的价值
  const handleResetReplay = useCallback(() => {
    if (sessionParamsRef.current) void startReplay(sessionParamsRef.current);
  }, [startReplay]);

  // 回放中切换周期（无缝衔接）：以「当前播放时刻」为新周期窗口的尾部向后拉一块，
  // 索引移到窗口最后一根——旧 bar 在新数据就位前一直显示，图表无空白，
  // 切换后与原时刻对齐继续播放（同 TradingView 切周期语义），前进/后退均可用
  const handleChangePeriod = useCallback(
    async (next: string) => {
      if (!started) {
        setPeriod(next);
        return;
      }
      if (next === periodRef.current || periodSwitchingRef.current) return;
      const wasPlaying = playingRef.current;
      pause();
      const bars = barsRef.current;
      if (bars.length === 0) {
        setPeriod(next);
        return;
      }
      periodSwitchingRef.current = true;
      try {
        const chunk = await fetchChunk(symbolRef.current, next, {
          endMs: bars[indexRef.current].timestamp,
        });
        if (chunk.length === 0) {
          message.warning(t('backtest_no_data_before_time', { symbol: symbolRef.current, period: next }));
          return;
        }
        barsRef.current = chunk;
        pastExhaustedRef.current = chunk.length < REPLAY_CONFIG.chunkSize;
        // 新窗口尾部是「当前时刻」，其后是否还有数据由预取判定
        futureExhaustedRef.current = false;
        indexRef.current = chunk.length - 1;
        setCurrentIndex(chunk.length - 1);
        setBarsCount(chunk.length);
        setAtStart(pastExhaustedRef.current);
        setAtEnd(false);
        setPeriod(next);
        feed();
        if (wasPlaying) handlePlay(); // 播放中切换 → 数据就位后无缝继续
      } catch (err) {
        console.error('切换周期失败:', err);
        message.error(t('backtest_change_period_failed'));
      } finally {
        periodSwitchingRef.current = false;
      }
    },
    [fetchChunk, feed, handlePlay, message, pause, started, t]
  );

  // 表单初始值：URL 参数 > 本地偏好 > 默认
  useEffect(() => {
    const qs = new URLSearchParams(location.search);
    let last: { symbol?: string; period?: string; startMs?: number } | null = null;
    try {
      last = JSON.parse(localStorage.getItem(LAST_KEY) || 'null');
    } catch {
      last = null;
    }
    const initSymbol = qs.get('symbol') || last?.symbol || 'BTCUSDT';
    const initPeriod = qs.get('interval') || last?.period || '1h';
    form.setFieldsValue({
      symbol: initSymbol,
      startDate: last?.startMs ? dayjs(last.startMs) : undefined,
    });
    setSymbol(initSymbol);
    setPeriod(initPeriod);
    // 仅在挂载时初始化一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 播放进度显示
  const progressTooltip = useMemo(
    () => (v?: number) => formatTs(barsRef.current[v ?? 0]?.timestamp),
    []
  );

  return (
    <PageContainer title={t('market_replay') || '行情回放'} onBack={handleBack}>
      {!started ? (
        <Card title={t('backtest_launch_replay')} style={{ maxWidth: 720 }}>
          <Alert
            type="info"
            showIcon
            title={t('backtest_replay_intro')}
            style={{ marginBottom: 16 }}
          />
          {loadError && (
            <Alert type="error" showIcon title={loadError} style={{ marginBottom: 16 }} />
          )}
          <Form
            form={form}
            layout="vertical"
            onFinish={(v) => startReplay({ symbol: v.symbol, startDate: v.startDate })}
          >
            <Form.Item
              name="symbol"
              label={t('backtest_symbol_label')}
              rules={[{ required: true, message: t('backtest_input_symbol_example') }]}
            >
              <Input placeholder="BTCUSDT" allowClear />
            </Form.Item>
            <Form.Item
              name="startDate"
              label={t('backtest_start_time')}
              rules={[{ required: true, message: t('backtest_select_replay_start_time') }]}
            >
              <DatePicker showTime style={{ width: '100%' }} placeholder={t('backtest_start_from_time')} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              {t('backtest_start_replay')}
            </Button>
          </Form>
        </Card>
      ) : (
        <Flex
          vertical
          gap={16}
          style={{ display: 'flex', width: '100%', height: 'calc(100vh - 88px)' }}
        >
          {/* 高度 88px = PageContainer 上下内边距 py-4(32) + 标题 h1(32) + mb-6(24)，
              整页恰好占满视口无滚动；图表区 flex:1 自动吃掉剩余高度，底部不留白 */}
          <Card size="small">
            <Space orientation="vertical" size="small" style={{ display: 'flex', width: '100%' }}>
              <Row align="middle" gutter={[12, 12]}>
                <Col>
                  <Space>
                    <Tooltip title={t('backtest_step_backward')}>
                      <Button icon={<StepBackwardOutlined />} onClick={() => handleStep(-1)} disabled={atStart && currentIndex === 0} />
                    </Tooltip>
                    {/* 与相邻单步/回退按钮一致：icon-only，悬浮 Tooltip 显示文字 */}
                    <Tooltip title={isPlaying ? t('pause') : t('play')}>
                      <Button
                        type="primary"
                        icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
                        onClick={() => (isPlaying ? pause() : handlePlay())}
                      />
                    </Tooltip>
                    <Tooltip title={t('backtest_step_forward')}>
                      <Button icon={<StepForwardOutlined />} onClick={() => handleStep(1)} disabled={atEnd && currentIndex >= barsCount - 1} />
                    </Tooltip>
                    <Tooltip title={t('backtest_reset_replay')}>
                      <Button icon={<ReloadOutlined />} onClick={handleResetReplay} />
                    </Tooltip>
                  </Space>
                </Col>
                <Col>
                  <Space>
                    <span>{t('backtest_speed_label')}</span>
                    <Select
                      value={speed}
                      onChange={handleChangeSpeed}
                      style={{ width: 90 }}
                      options={SPEED_STEPS.filter(
                        (s) => s >= REPLAY_CONFIG.minSpeed && s <= REPLAY_CONFIG.maxSpeed
                      ).map((s) => ({ label: `${s}x`, value: s }))}
                    />
                  </Space>
                </Col>
                <Col>
                  <Space>
                    <span>{t('backtest_jump_to_time')}</span>
                    <DatePicker showTime onChange={handleSeekTime} placeholder={t('backtest_second_precision')} />
                  </Space>
                </Col>
              </Row>
              <Row align="middle" gutter={[12, 12]}>
                <Col flex="none">
                  <Badge
                    count={`${currentIndex + 1} / ${barsCount}`}
                    style={{ backgroundColor: QUANT_COLORS.info }}
                  />
                </Col>
                <Col flex="auto" style={{ padding: '0 12px' }}>
                  <Slider
                    min={0}
                    max={Math.max(barsCount - 1, 0)}
                    value={currentIndex}
                    onChange={handleSeekIndex}
                    tooltip={{ formatter: progressTooltip }}
                  />
                </Col>
                <Col flex="none">
                  <span style={{ fontSize: 12, color: 'var(--ant-color-text-secondary)' }}>
                    {formatTs(barsRef.current[currentIndex]?.timestamp)}
                  </span>
                </Col>
              </Row>
            </Space>
          </Card>
          {/* flex:1 替代固定 calc(100vh - 320px)：控制卡高度变化时图表自动吃掉剩余视口，底部无空白带；
              replay-chart-shell 供 ChartPage.css 把图表主体拉到侧边栏边缘而周期栏保持缩进 */}
          <div className="replay-chart-shell" style={{ flex: 1, minHeight: 480 }}>
            <ChartShell
              ref={shellRef}
              chartId="market-replay-k-line"
              symbol={{ code: symbol }}
              periods={PERIOD_BAR_ITEMS}
              currentPeriod={period}
              onChangePeriod={handleChangePeriod}
              getBars={() => barsRef.current.slice(0, indexRef.current + 1)}
              drawingBarLocked
              indicatorScope="all"
              loading={false}
              error={loadError}
            />
          </div>
        </Flex>
      )}
    </PageContainer>
  );
};

export default KlineReplayPage;
