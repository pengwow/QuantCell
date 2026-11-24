/* eslint-disable react-refresh/only-export-components -- pnlDeltaPp 是纯函数，直接导出给单测（不起 React 渲染） */
/**
 * 首页看板（/home）—— design-spec §5/§6.3/§6.4/§6.5/§6.13/§6.17 像素收口
 *
 * 定位：登录后的第一屏，回答三个问题 —— 系统是否正常、策略在跑什么、下一步去哪。
 * 数据全部来自现有接口（workers / backtests / research / system metrics），
 * 任一接口失败只影响对应区块，不阻塞整页渲染。
 * 视觉基准：docs/design/qc-prototype-demo.html#home；数字口径只写接口能算出的
 * 真实数据，demo 里的静态演示值（如「历史共 128」）一律不照抄。
 */
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Button, Card } from 'antd';
import {
  IconChartCandle,
  IconChartHistogram,
  IconDatabase,
  IconFlask,
  IconArrowRight,
  IconPlayerPlay,
  IconPlus,
  IconRefresh,
  IconRobot,
  IconTrendingUp,
} from '@tabler/icons-react';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

import PageContainer from '@/components/PageContainer';
import { QcEmpty } from '@/components/ui/DataTable';
import { usePolling } from '@/hooks/usePolling';
import { apiRequest, backtestApi, systemApi } from '@/api';
import workerApi from '@/api/workerApi';
import { researchApi } from '@/api/research';
import type { BacktestTask } from '@/types/backtest';
import type { Worker, WorkerStatus } from '@/types/worker';
import { WorkerStatusText } from '@/types/worker';
import type { ResearchSession, ResearchStatus } from '@/api/research';
import type { SystemMetrics } from '@/pages/setting/types';
import { formatPercent, formatUSD } from '@/utils/format';
import './HomePage.css';

// 「更新于 x 前」需要相对时间；extend 幂等，重复调用无副作用
dayjs.extend(relativeTime);

/** GET /workers/stats/pnl-overview（backend/worker/routes.py 只读聚合） */
interface PnlOverview {
  window_hours: number;
  /** 窗口内已实现盈亏合计（配对毛口径，手续费不挤入） */
  realized_pnl: number;
  trade_count: number;
  /** 配置资金合计（worker_capital 有行取 initial_capital，否则 workers.config） */
  capital: number;
  /** 分母为 0 时后端给 null（0/0 不等于 0%） */
  pnl_pct: number | null;
  /** 昨日**同期**窗口（now-2h ~ now-h）同口径已实现盈亏 */
  prev_realized_pnl: number;
  prev_trade_count: number;
  /** 同一分母下的昨日同期百分比；分母为 0 时为 null */
  prev_pnl_pct: number | null;
}

/**
 * 「较昨日同期」是**百分点差**（today_pct - prev_pct），不是百分比变化。
 * 任一值为 null 返回 null（该段不渲染，不写 0.00pp）；两位小数内为 0 时归零，
 * 避免 -0.00 这种带符号的假方向。
 */
export function pnlDeltaPp(today: number | null, prev: number | null): number | null {
  if (today === null || prev === null) return null;
  const delta = today - prev;
  return Math.abs(delta) < 0.005 ? 0 : delta;
}


/** 回测任务行「区间 · 周期」真值（来自 GET /backtest/{id}/summary 的 backtest_config） */
interface BacktestRange {
  start?: string;
  end?: string;
  interval?: string;
}

/** 周期取值校验：历史任务文件里有 "invalid" 这种脏值，不是真周期，不渲染 */
const showInterval = (interval?: string): string | undefined =>
  interval && /^\d+[mhdwM]$/.test(interval) ? interval : undefined;

/** 回测行「区间 · 周期」：区间仅在 summary 给到起止时间时渲染，缺失退回创建时间 */
function backtestRangeLabel(task: BacktestTask, range?: BacktestRange): string {
  const interval = range?.interval;
  const suffix = interval ? ` · ${interval}` : '';
  if (range?.start && range?.end) {
    return `${dayjs(range.start).format('YYYY-MM-DD')} → ${dayjs(range.end).format('YYYY-MM-DD')}${suffix}`;
  }
  if (task.created_at) return `${dayjs(task.created_at).format('MM-DD HH:mm')}${suffix}`;
  return '—';
}

/** 回测状态 → §6.2 chip 语义（与 BacktestList 的 renderStatusChip 口径一致） */
function backtestChip(status: string): { cls: string; label: string; pulse: boolean } {
  switch (status) {
    case 'completed':
      return { cls: 'ok', label: 'status_completed', pulse: false };
    case 'running':
    case 'in_progress':
      return { cls: 'info', label: 'status_running', pulse: true };
    case 'failed':
      return { cls: 'down', label: 'status_failed', pulse: false };
    case 'pending':
      return { cls: 'quiet', label: 'status_pending', pulse: false };
    default:
      return { cls: 'quiet', label: status, pulse: false };
  }
}

/** 研究状态 → chip 语义（与 ResearchList 的 STATUS_META 一致） */
const RESEARCH_CHIP: Record<ResearchStatus, { cls: string; i18nKey: string; pulse: boolean }> = {
  pending: { cls: 'info', i18nKey: 'research_status_pending', pulse: false },
  running: { cls: 'info', i18nKey: 'research_status_running', pulse: true },
  paused: { cls: 'warn', i18nKey: 'research_status_paused', pulse: false },
  completed: { cls: 'ok', i18nKey: 'research_status_completed', pulse: false },
  failed: { cls: 'down', i18nKey: 'research_status_failed', pulse: false },
  cancelled: { cls: 'quiet', i18nKey: 'research_status_cancelled', pulse: false },
};

/** 运行中任务状态 → chip 语义（12 态收拢到 4 档语义色） */
function workerChip(status: WorkerStatus): { cls: string; pulse: boolean } {
  switch (status) {
    case 'running':
      return { cls: 'info', pulse: true };
    case 'error':
    case 'interrupted':
      return { cls: 'down', pulse: false };
    case 'paused':
      return { cls: 'warn', pulse: false };
    case 'starting':
    case 'stopping':
    case 'recovering':
    case 'reloading':
    case 'restarting':
    case 'initializing':
      return { cls: 'info', pulse: false };
    default:
      return { cls: 'quiet', pulse: false };
  }
}

/** 交易模式 → .home-mode 变体（§6.2 mode-tag：实盘主色 tint、模拟/info tint） */
function modeClass(tradingMode: string | undefined): string {
  if (tradingMode === 'live') return 'live';
  if (tradingMode === 'paper' || tradingMode === 'testnet') return 'paper';
  return '';
}

/** 运行中的 worker 从 started_at 起算的真实运行时长（demo「14h 22m」） */
function runningDuration(worker: Worker): string | null {
  if (worker.status !== 'running' || !worker.started_at) return null;
  const ms = Date.now() - dayjs(worker.started_at).valueOf();
  if (!Number.isFinite(ms) || ms <= 0) return null;
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `${h}h ${String(m).padStart(2, '0')}m`;
}

type SysTone = 'ok' | 'warn' | 'down' | 'off';

/** 「系统状态」卡的一行：点状态 + 名称(+mono id) + 副说明 + 右侧 mono 值 */
interface SysRow {
  key: string;
  tone: SysTone;
  name: string;
  id?: string;
  sub: string;
  val: string;
}

const HomePage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [workers, setWorkers] = useState<Worker[]>([]);
  const [workersTotal, setWorkersTotal] = useState(0);
  const [backtests, setBacktests] = useState<BacktestTask[]>([]);
  const [backtestsTotal, setBacktestsTotal] = useState(0);
  const [backtestCounts, setBacktestCounts] = useState<{
    completed: number;
    running: number;
    failed: number;
  } | null>(null);
  const [backtestRanges, setBacktestRanges] = useState<Record<string, BacktestRange>>({});
  const [pnlOverview, setPnlOverview] = useState<PnlOverview | null>(null);
  const [research, setResearch] = useState<ResearchSession[]>([]);
  const [researchTotal, setResearchTotal] = useState(0);
  const [system, setSystem] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  // 四个接口互不依赖，用 allSettled 保证单个失败不影响其他区块
  const load = useCallback(async () => {
    const [workerRes, backtestRes, researchRes, systemRes, pnlRes, doneRes, runRes, failRes] =
      await Promise.allSettled([
        workerApi.getWorkers({ page: 1, page_size: 50 }),
        backtestApi.getBacktestList({ page: 1, page_size: 96 }),
        researchApi.list({ limit: 50, offset: 0 }),
        systemApi.getSystemMetrics(),
        // KPI2 今日盈亏：近 24h 已实现盈亏 ÷ 配置资金，后端只读聚合
        apiRequest.get<PnlOverview>('/workers/stats/pnl-overview'),
        // KPI3 副标分布：取服务端 total（page_size=1 只要计数），不是本页样本计数
        // ponytail: 三次请求各扫一遍 task JSON（本地 ~150ms）；升级路径是回测侧提供 status 聚合字段
        backtestApi.getBacktestList({ page: 1, page_size: 1, status: 'completed' }),
        backtestApi.getBacktestList({ page: 1, page_size: 1, status: 'running' }),
        backtestApi.getBacktestList({ page: 1, page_size: 1, status: 'failed' }),
      ]);

    if (workerRes.status === 'fulfilled') {
      setWorkers(workerRes.value.items ?? []);
      setWorkersTotal(workerRes.value.total ?? 0);
    }
    if (backtestRes.status === 'fulfilled') {
      const items = backtestRes.value.backtests ?? [];
      setBacktests(items);
      setBacktestsTotal(backtestRes.value.total ?? 0);

      // 「区间 · 周期」：列表行不带起止时间，只有 /backtest/{id}/summary 的
      // backtest_config 有真值（DB 行缺配置的旧任务给空对象 → 不给区间）
      // ponytail: summary 对 completed 任务首次会读结果 JSON 并回写任务文件（一次性，
      // 之后毫秒级）；固定 5 条不随分页放大，升级路径是列表接口直接回传起止区间
      const recent = [...items]
        .sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
        .slice(0, 5);
      const summaries = await Promise.allSettled(
        recent.map((task) => backtestApi.getBacktestSummary(String(task.id)))
      );
      const nextRanges: Record<string, BacktestRange> = {};
      recent.forEach((task, index) => {
        const summary = summaries[index];
        if (summary.status !== 'fulfilled') return;
        const config = summary.value.backtest_config ?? {};
        nextRanges[String(task.id)] = {
          start: config.start_time,
          end: config.end_time,
          interval: showInterval(config.interval ?? task.intervals?.[0]),
        };
      });
      setBacktestRanges(nextRanges);
    }
    if (
      doneRes.status === 'fulfilled' &&
      runRes.status === 'fulfilled' &&
      failRes.status === 'fulfilled'
    ) {
      setBacktestCounts({
        completed: doneRes.value.total ?? 0,
        running: runRes.value.total ?? 0,
        failed: failRes.value.total ?? 0,
      });
    }
    if (pnlRes.status === 'fulfilled') setPnlOverview(pnlRes.value);
    if (researchRes.status === 'fulfilled') {
      setResearch(researchRes.value.sessions ?? []);
      setResearchTotal(researchRes.value.total ?? 0);
    }
    if (systemRes.status === 'fulfilled') setSystem(systemRes.value);

    setUpdatedAt(new Date());
    setLoading(false);
  }, []);

  // 60s 轮询，页面隐藏时自动暂停
  usePolling(load, { interval: 60_000 });

  const runningWorkers = useMemo(
    () => workers.filter((worker) => worker.status === 'running'),
    [workers]
  );

  const pausedWorkers = useMemo(
    () => workers.filter((worker) => worker.status === 'paused'),
    [workers]
  );

  // 运行中的任务优先展示，其余按原顺序补位
  const taskPreview = useMemo(
    () =>
      [...workers]
        .sort((a, b) => Number(b.status === 'running') - Number(a.status === 'running'))
        .slice(0, 5),
    [workers]
  );

  const recentBacktests = useMemo(
    () =>
      [...backtests]
        .sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
        .slice(0, 5),
    [backtests]
  );

  // 最近研究会话（后端已按更新时间倒序的话直接可用，稳一点本地再排一次）
  const recentResearch = useMemo(
    () =>
      [...research]
        .sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
        .slice(0, 5),
    [research]
  );

  // ponytail: running/完成/失败数均取自首页样本（limit 50 / page_size 96），非全量精确值；
  // upgrade path：后端提供 status 聚合字段后改为直接读聚合
  const runningResearch = useMemo(
    () =>
      research.filter(
        (s) => s.status === 'running' || s.status === 'pending' || s.status === 'paused'
      ).length,
    [research]
  );

  const online = system?.connectionStatus === 'connected';
  // 首次加载尚未拿到任何数据时才展示骨架；轮询刷新不打断已有内容
  const firstLoading = loading && updatedAt === null;
  const pnlPct = pnlOverview?.pnl_pct ?? null;
  // 0 变动中性不染色：只有严格正/负才上色
  const pnlTone = firstLoading || pnlPct === null ? '' : pnlPct > 0 ? ' up' : pnlPct < 0 ? ' down' : '';
  // 「较昨日同期」百分点差：今日/昨日任一侧算不出（分母为 0）就整段不渲染
  const ppDelta = firstLoading
    ? null
    : pnlDeltaPp(pnlOverview?.pnl_pct ?? null, pnlOverview?.prev_pnl_pct ?? null);
  const ppTone = ppDelta === null || ppDelta === 0 ? '' : ppDelta > 0 ? ' qc-cell-up' : ' qc-cell-down';

  // 页头副标（§5 mono 口径行）：日期/星期取本地时间，时区取系统偏移，
  // 「系统运行中 / 数据同步时间」只在接口真的给出现状时才写，拿不到就省略
  const subtitle = useMemo(() => {
    const offsetMin = -new Date().getTimezoneOffset();
    const sign = offsetMin >= 0 ? '+' : '-';
    const oh = Math.floor(Math.abs(offsetMin) / 60);
    const om = Math.abs(offsetMin) % 60;
    const parts = [
      `${dayjs().format('YYYY-MM-DD dddd')} · UTC${sign}${oh}${om ? `:${om}` : ''}`,
    ];
    if (system) parts.push(online ? t('home_system_online') : t('home_system_offline'));
    if (updatedAt) parts.push(`${t('home_last_updated')} ${dayjs(updatedAt).format('HH:mm:ss')}`);
    return parts.join(' · ');
  }, [system, online, updatedAt, t]);

  // 「系统状态」四行：全部取 /system/metrics 的真实业务读数，缺失即「—」，
  // 不用 0 冒充；口径见 backend/observability/runtime_health.py 与 SystemService
  const sysRows = useMemo<SysRow[]>(() => {
    if (!system) return [];
    const ms = (v: number | null | undefined) =>
      v == null ? '—' : v >= 10 ? `${Math.round(v)}ms` : `${v.toFixed(1)}ms`;

    const eng = system.engine;
    const exs = system.exchanges?.exchanges ?? [];
    const okExs = exs.filter((e) => e.ok);
    const ds = system.dataSource;
    const llm = system.llm;
    const provider = llm?.provider;

    return [
      {
        key: 'engine',
        tone: eng && eng.samples > 0 ? 'ok' : 'off',
        name: t('home_sys_engine'),
        id: 'axon-kernel',
        sub:
          eng && eng.samples > 0
            ? t('home_sys_engine_sub', { samples: eng.samples })
            : t('home_sys_engine_sub_empty'),
        val: eng?.avg_ms != null ? t('home_sys_engine_val', { ms: ms(eng.avg_ms) }) : '—',
      },
      {
        key: 'exchange',
        tone:
          exs.length === 0 ? 'off' : okExs.length === exs.length ? 'ok' : okExs.length > 0 ? 'warn' : 'down',
        name: t('home_sys_exchange'),
        id: exs.map((e) => e.exchange).join(' / ') || undefined,
        sub:
          exs.length === 0
            ? t('home_sys_exchange_fail')
            : exs.length === 1
              ? t('home_sys_exchange_sub', {
                  mode: exs[0].trading_mode,
                  state: exs[0].ok ? t('home_sys_exchange_ok') : t('home_sys_exchange_fail'),
                })
              : t('home_sys_exchange_sub_multi', {
                  mode: exs[0].trading_mode,
                  ok: okExs.length,
                  total: exs.length,
                }),
        val:
          okExs.length === 0
            ? '—'
            : t('home_sys_exchange_val', {
                ms: ms(Math.min(...okExs.map((e) => e.latency_ms ?? 0))),
              }),
      },
      {
        key: 'data',
        tone: ds && (ds.bar_count ?? 0) > 0 ? 'ok' : 'off',
        name: t('home_sys_data'),
        id: 'kline',
        sub:
          ds && (ds.bar_count ?? 0) > 0
            ? t('home_sys_data_sub', {
                symbols: ds.symbols ?? 0,
                time: ds.latest_at ? dayjs(ds.latest_at).format('MM-DD HH:mm') : '—',
              })
            : t('home_sys_data_sub_empty'),
        val: ds?.bar_count != null ? t('home_sys_data_val', { n: ds.bar_count.toLocaleString('en-US') }) : '—',
      },
      {
        key: 'llm',
        tone: !provider ? 'off' : (llm?.rate_limit ?? 0) > 0 ? 'warn' : (llm?.calls ?? 0) > 0 ? 'ok' : 'off',
        name: t('home_sys_llm'),
        id: provider?.name || t('home_sys_unconfigured'),
        sub: provider
          ? t('home_sys_llm_sub', { model: provider.model || '—', calls: llm?.calls ?? 0 }) +
            ((llm?.rate_limit ?? 0) > 0 ? t('home_sys_llm_429', { n: llm?.rate_limit ?? 0 }) : '')
          : t('home_sys_unconfigured'),
        val: llm?.p95_ms != null ? t('home_sys_llm_val', { ms: ms(llm.p95_ms) }) : '—',
      },
    ];
  }, [system, t]);

  const quickActions = [
    { path: '/chart', icon: <IconChartCandle />, label: t('chart') },
    { path: '/agent', icon: <IconRobot />, label: t('agent_workspace') },
    { path: '/backtest', icon: <IconTrendingUp />, label: t('backtest') },
    { path: '/factor-analysis', icon: <IconChartHistogram />, label: t('factor_analysis') },
    { path: '/research', icon: <IconFlask />, label: t('ai_research') },
    { path: '/data-management', icon: <IconDatabase />, label: t('data_management') },
  ];

  const actionStyle = { height: 30, padding: '0 12px', fontSize: 12 } as const;

  return (
    <PageContainer
      title={t('home_dashboard')}
      subtitle={subtitle}
      actions={
        <>
          <Button
            type="primary"
            icon={<IconPlus size={14} stroke={1.8} />}
            style={{ ...actionStyle, fontWeight: 550 }}
            onClick={() => navigate('/strategy-editor')}
          >
            {t('new_strategy')}
          </Button>
          <Button
            icon={<IconPlayerPlay size={14} stroke={1.8} />}
            style={actionStyle}
            onClick={() => navigate('/backtest/config')}
          >
            {t('home_start_backtest')}
          </Button>
          <Button
            icon={<IconRobot size={14} stroke={1.8} />}
            style={actionStyle}
            onClick={() => navigate('/strategy-worker')}
          >
            {t('home_open_strategy_agent')}
          </Button>
        </>
      }
    >
      <div className="home-grid">
        {/* KPI ×4（§6.4：12px 14px 卡、label 11、数值 mono 22/650、sub 10.5） */}
        <div className="home-col-12 qc-kpi-grid">
          <div className="qc-kpi">
            <div className="qc-kpi-top">
              <span className="qc-kpi-lb">{t('home_kpi_running')}</span>
              <span className="home-kpi-ico">
                <IconRobot />
              </span>
            </div>
            {/* ponytail: 运行中数从 page_size=50 样本统计，样本不足时偏小；upgrade path 同上 */}
            <div className="qc-kpi-num">{firstLoading ? '—' : runningWorkers.length}</div>
            <div className="qc-kpi-sub">
              {t('home_kpi_running_breakdown', {
                total: workersTotal,
                running: runningWorkers.length,
                paused: pausedWorkers.length,
              })}
            </div>
          </div>
          <div className="qc-kpi">
            <div className="qc-kpi-top">
              <span className="qc-kpi-lb">{t('home_kpi_pnl_today')}</span>
              <span className="home-kpi-ico">
                <IconTrendingUp />
              </span>
            </div>
            <div className={`qc-kpi-num${pnlTone}`}>
              {firstLoading || pnlPct === null ? '—' : formatPercent(pnlPct, { showSign: true })}
            </div>
            <div className="qc-kpi-sub">
              {t('home_kpi_pnl_today_hint', { hours: pnlOverview?.window_hours ?? 24 })}
              {ppDelta !== null && (
                <>
                  {' · '}
                  {/* 滚动 24h 窗口对比，措辞固定「较昨日同期」，不得简写成「较昨日」 */}
                  <span className={`qc-mono${ppTone}`}>
                    {t('home_kpi_pnl_vs_prev', {
                      delta: `${ppDelta > 0 ? '+' : ''}${ppDelta.toFixed(2)}pp`,
                    })}
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="qc-kpi">
            <div className="qc-kpi-top">
              <span className="qc-kpi-lb">{t('home_kpi_backtests')}</span>
              <span className="home-kpi-ico">
                <IconChartHistogram />
              </span>
            </div>
            {/* 服务端 total：真实回测总数（非页面样本长度） */}
            <div className="qc-kpi-num">{firstLoading ? '—' : backtestsTotal}</div>
            <div className="qc-kpi-sub">
              {backtestCounts
                ? t('home_kpi_backtests_breakdown', backtestCounts)
                : t('home_kpi_backtests_hint')}
            </div>
          </div>
          <div className="qc-kpi">
            <div className="qc-kpi-top">
              <span className="qc-kpi-lb">{t('home_kpi_research')}</span>
              <span className="home-kpi-ico">
                <IconFlask />
              </span>
            </div>
            <div className="qc-kpi-num">{firstLoading ? '—' : researchTotal}</div>
            <div className="qc-kpi-sub">{t('home_kpi_research_hint', { running: runningResearch })}</div>
          </div>
        </div>

        {/* 运行中任务（demo col8） */}
        <Card
          className="home-col-8 qc-card"
          title={t('home_running_tasks')}
          extra={
            <span className="home-head-right">
              <span className="qc-count-chip">{`${runningWorkers.length} · ${t('status_running')}`}</span>
              <button type="button" className="home-cardlink" onClick={() => navigate('/strategy-worker')}>
                {t('home_view_all')}
                <IconArrowRight />
              </button>
            </span>
          }
        >
          {firstLoading ? (
            <HomeSkelRows />
          ) : taskPreview.length === 0 ? (
            <QcEmpty
              icon={<IconRobot />}
              title={t('home_no_tasks')}
              action={
                <button type="button" className="qc-mini-btn pri" onClick={() => navigate('/strategy-worker')}>
                  {t('home_create_task')}
                </button>
              }
            />
          ) : (
            <div>
              {taskPreview.map((worker) => {
                const profit = worker.total_profit ?? 0;
                const symbols = worker.trading_config?.symbols_config?.symbols ?? [];
                const interval = worker.trading_config?.interval;
                const typeLabel = worker.strategy_type === 'rl' ? 'RL' : t('worker_rule_tag');
                const chip = workerChip(worker.status);
                const dur = runningDuration(worker);

                return (
                  <div
                    key={worker.id}
                    role="button"
                    tabIndex={0}
                    className="home-row home-task"
                    title={t('worker_detail')}
                    onClick={() => navigate(`/strategy-worker/${worker.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(`/strategy-worker/${worker.id}`);
                      }
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="home-t-main">
                        <span className="qc-mono home-t-name">{worker.name}</span>
                        <span className="qc-mono home-t-id">#{worker.id}</span>
                        {worker.trading_config?.trading_mode && (
                          <span className={`home-mode ${modeClass(worker.trading_config.trading_mode)}`}>
                            {(() => {
                              const m = worker.trading_config?.trading_mode;
                              const key =
                                m === 'live'
                                  ? 'worker_trading_mode_live'
                                  : m === 'testnet'
                                    ? 'worker_trading_mode_testnet'
                                    : 'worker_trading_mode_paper';
                              return t(key);
                            })()}
                          </span>
                        )}
                      </div>
                      <div className="home-t-sub">
                        {[
                          typeLabel,
                          worker.strategy_info?.name || worker.strategy_type || '-',
                          symbols.length > 0
                            ? `${symbols.slice(0, 2).join(' / ')}${symbols.length > 2 ? ` +${symbols.length - 2}` : ''}`
                            : '',
                          interval,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                    </div>
                    <div className="home-t-right">
                      <span
                        className={`qc-mono home-t-pnl ${
                          profit > 0 ? 'up' : profit < 0 ? 'down' : 'flat'
                        }`}
                      >
                        {formatUSD(profit, { showSign: true })}
                      </span>
                      {dur && <span className="qc-mono home-t-dur">{dur}</span>}
                      <span className={`qc-chip ${chip.cls}`}>
                        {chip.pulse && <span className="qc-pdot" />}
                        {t(WorkerStatusText[worker.status])}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* 系统状态（demo col4：点 + 名称 + mono id + 副说明 + 右值；§6.17） */}
        <Card
          className="home-col-4 qc-card"
          title={t('home_system_status')}
          extra={
            <span className="home-head-right">
              <span className="qc-count-chip">{t('home_sys_count', { total: sysRows.length || 4 })}</span>
              <button
                type="button"
                className="qc-mini-btn qc-icon-only"
                aria-label={t('refresh')}
                title={t('refresh')}
                onClick={() => {
                  setLoading(true);
                  void load();
                }}
              >
                <IconRefresh />
              </button>
            </span>
          }
        >
          {firstLoading && !system ? (
            <HomeSkelRows />
          ) : (
            <>
              <div className="home-sys">
                {sysRows.map((row) => (
                  <div className="home-sys-row" key={row.key}>
                    <span className={`home-dot ${row.tone}`} />
                    <div className="home-sys-main">
                      <div className="home-sys-name">
                        {row.name}
                        {row.id && <span className="qc-mono home-sys-id">{row.id}</span>}
                      </div>
                      <div className="home-sys-sub">{row.sub}</div>
                    </div>
                    <span className="qc-mono home-sys-val">{row.val}</span>
                  </div>
                ))}
              </div>
              {/* §6.3 card-foot：真实刷新时间，不编造 */}
              <div className="home-foot">
                <span className="qc-mono">
                  {t('home_last_updated')} {updatedAt ? dayjs(updatedAt).format('HH:mm:ss') : '—'}
                </span>
              </div>
            </>
          )}
        </Card>

        {/* 最近回测（demo col6） */}
        <Card
          className="home-col-6 qc-card"
          title={t('home_recent_backtests')}
          extra={
            <span className="home-head-right">
              <span className="qc-count-chip">{t('total_items', { total: backtestsTotal })}</span>
              <button type="button" className="home-cardlink" onClick={() => navigate('/backtest')}>
                {t('home_view_all')}
                <IconArrowRight />
              </button>
            </span>
          }
        >
          {firstLoading ? (
            <HomeSkelRows />
          ) : recentBacktests.length === 0 ? (
            <QcEmpty
              icon={<IconChartHistogram />}
              title={t('home_no_backtests')}
              action={
                <button type="button" className="qc-mini-btn pri" onClick={() => navigate('/backtest/config')}>
                  {t('home_start_backtest')}
                </button>
              }
            />
          ) : (
            <div>
              {recentBacktests.map((task) => {
                const chip = backtestChip(task.status);
                const ret = task.total_return;
                return (
                  <div
                    key={task.id}
                    role="button"
                    tabIndex={0}
                    className="home-row home-row-mini"
                    title={t('backtest_detail')}
                    onClick={() => navigate(`/backtest/detail/${task.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(`/backtest/detail/${task.id}`);
                      }
                    }}
                  >
                    <span className="qc-mono home-mini-id">{task.strategy_name}</span>
                    <span className="qc-mono home-mini-x">
                      {backtestRangeLabel(task, backtestRanges[String(task.id)])}
                    </span>
                    <span className="home-mini-right">
                      <span className={`qc-chip ${chip.cls}`}>
                        {chip.pulse && <span className="qc-pdot" />}
                        {t(chip.label)}
                      </span>
                      <span
                        className={`qc-mono home-mini-pnl ${
                          task.status === 'failed' ? 'flat' : ret != null ? (ret > 0 ? 'up' : ret < 0 ? 'down' : 'flat') : 'flat'
                        }`}
                      >
                        {task.status === 'failed' || ret == null ? '—' : formatPercent(ret, { showSign: true })}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          {/* 卡脚说明（demo 921 对位）：只写真实机制——LLM 回测缺 replay 记录直接报错，不降级 Hold */}
          {!firstLoading && recentBacktests.length > 0 && (
            <div
              className="home-foot"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}
            >
              <span>{t('home_backtest_foot')}</span>
              <button type="button" className="home-cardlink" onClick={() => navigate('/backtest')}>
                {t('backtest_center')}
                <IconArrowRight />
              </button>
            </div>
          )}
        </Card>

        {/* 最近研究（demo col6） */}
        <Card
          className="home-col-6 qc-card"
          title={t('home_recent_research')}
          extra={
            <span className="home-head-right">
              <span className="qc-count-chip">{t('research_total_sessions', { total: researchTotal })}</span>
              <button type="button" className="home-cardlink" onClick={() => navigate('/research')}>
                {t('home_view_all')}
                <IconArrowRight />
              </button>
            </span>
          }
        >
          {firstLoading ? (
            <HomeSkelRows />
          ) : recentResearch.length === 0 ? (
            <QcEmpty
              icon={<IconFlask />}
              title={t('home_no_research')}
              action={
                <button type="button" className="qc-mini-btn pri" onClick={() => navigate('/research')}>
                  {t('home_create_research')}
                </button>
              }
            />
          ) : (
            <div>
              {recentResearch.map((row) => {
                const chip = RESEARCH_CHIP[row.status];
                return (
                  <div
                    key={row.id}
                    role="button"
                    tabIndex={0}
                    className="home-row home-row-mini"
                    title={t('ai_research')}
                    onClick={() => navigate(`/research/${row.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(`/research/${row.id}`);
                      }
                    }}
                  >
                    <span className="home-mini-name">
                      {row.name || t('research_session_fallback', { id: row.id })}
                    </span>
                    <span className="qc-chip info">{t(`research_scenario_${row.scenario ?? 'factor'}`)}</span>
                    <span className="home-mini-right">
                      <span className={`qc-chip ${chip.cls}`}>
                        {chip.pulse && <span className="qc-pdot" />}
                        {t(chip.i18nKey)}
                      </span>
                      <span className="qc-mono home-mini-x">
                        {row.updated_at ? dayjs(row.updated_at).fromNow() : '—'}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          {/* 卡脚说明（demo 943 对位）：只写真实机制——产物靠详情页逐个 trial 采纳，不做会话级一键转回测 */}
          {!firstLoading && recentResearch.length > 0 && (
            <div
              className="home-foot"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}
            >
              <span>{t('home_research_foot')}</span>
              <button type="button" className="home-cardlink" onClick={() => navigate('/research')}>
                {t('research')}
                <IconArrowRight />
              </button>
            </div>
          )}
        </Card>

        {/* 快速操作（全宽收尾卡；qc-mini-btn 24px + 14px 图标） */}
        <Card className="home-col-12 qc-card" title={t('home_quick_actions')}>
          <div className="home-quick-grid">
            {quickActions.map((action) => (
              <button key={action.path} type="button" className="qc-mini-btn home-quick" onClick={() => navigate(action.path)}>
                {action.icon}
                {action.label}
              </button>
            ))}
          </div>
        </Card>
      </div>
    </PageContainer>
  );
};

/** §6.13 骨架：bge 底 / 6px 圆角 / 无 shimmer，颜色只走 --qc-* */
const HomeSkelRows = () => (
  <div className="home-skel-rows" aria-hidden>
    {[64, 52, 76, 58].map((w) => (
      <span key={w} className="home-skel-line" style={{ width: `${w}%`, height: 12 }} />
    ))}
  </div>
);

export default HomePage;
