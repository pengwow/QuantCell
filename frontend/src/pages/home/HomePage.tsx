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
import { backtestApi, systemApi } from '@/api';
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

const HomePage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [workers, setWorkers] = useState<Worker[]>([]);
  const [workersTotal, setWorkersTotal] = useState(0);
  const [backtests, setBacktests] = useState<BacktestTask[]>([]);
  const [backtestsTotal, setBacktestsTotal] = useState(0);
  const [research, setResearch] = useState<ResearchSession[]>([]);
  const [researchTotal, setResearchTotal] = useState(0);
  const [system, setSystem] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  // 四个接口互不依赖，用 allSettled 保证单个失败不影响其他区块
  const load = useCallback(async () => {
    const [workerRes, backtestRes, researchRes, systemRes] = await Promise.allSettled([
      workerApi.getWorkers({ page: 1, page_size: 50 }),
      backtestApi.getBacktestList({ page: 1, page_size: 96 }),
      researchApi.list({ limit: 50, offset: 0 }),
      systemApi.getSystemMetrics(),
    ]);

    if (workerRes.status === 'fulfilled') {
      setWorkers(workerRes.value.items ?? []);
      setWorkersTotal(workerRes.value.total ?? 0);
    }
    if (backtestRes.status === 'fulfilled') {
      setBacktests(backtestRes.value.backtests ?? []);
      setBacktestsTotal(backtestRes.value.total ?? 0);
    }
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

  const totalProfit = useMemo(
    () => workers.reduce((sum, worker) => sum + (worker.total_profit ?? 0), 0),
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
  const offline = system?.connectionStatus === 'disconnected' || system?.connectionStatus === 'error';
  // 首次加载尚未拿到任何数据时才展示骨架；轮询刷新不打断已有内容
  const firstLoading = loading && updatedAt === null;
  const pnlTone = firstLoading ? '' : totalProfit > 0 ? ' up' : totalProfit < 0 ? ' down' : '';

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
            onClick={() => navigate('/strategy-worker')}
          >
            {t('home_create_task')}
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
            <div className="qc-kpi-sub">{t('home_kpi_running_hint', { total: workersTotal })}</div>
          </div>
          <div className="qc-kpi">
            <div className="qc-kpi-top">
              <span className="qc-kpi-lb">{t('home_kpi_pnl')}</span>
              <span className="home-kpi-ico">
                <IconTrendingUp />
              </span>
            </div>
            <div className={`qc-kpi-num${pnlTone}`}>
              {firstLoading ? '—' : formatUSD(totalProfit, { showSign: true })}
            </div>
            <div className="qc-kpi-sub">{t('home_kpi_pnl_hint')}</div>
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
            <div className="qc-kpi-sub">{t('home_kpi_backtests_hint')}</div>
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

        {/* 系统状态（demo col4；§6.17：8px 点 + 名称 12 + 右值 mono 10.5） */}
        <Card
          className="home-col-4 qc-card"
          title={t('home_system_status')}
          extra={
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
          }
        >
          {firstLoading && !system ? (
            <HomeSkelRows />
          ) : (
            <>
              <div className="home-sys">
                <div className="home-sys-row">
                  <span className={`home-dot ${online ? 'ok' : offline ? 'down' : system ? 'warn' : 'off'}`} />
                  <span className="home-sys-name">{t('home_connection')}</span>
                  <span className="qc-mono home-sys-val">
                    {system ? (online ? t('home_system_online') : t('home_system_offline')) : '—'}
                  </span>
                </div>
                <div className="home-sys-row">
                  <span className={`home-dot ${system ? 'ok' : 'off'}`} />
                  <span className="home-sys-name">{t('home_cpu')}</span>
                  <span className="qc-mono home-sys-val">{system ? `${Math.round(system.cpuUsage)}%` : '—'}</span>
                </div>
                <div className="home-sys-row">
                  <span className={`home-dot ${system ? 'ok' : 'off'}`} />
                  <span className="home-sys-name">{t('home_memory')}</span>
                  <span className="qc-mono home-sys-val">
                    {system ? `${system.memoryUsed} / ${system.memoryTotal}` : '—'}
                  </span>
                </div>
                <div className="home-sys-row">
                  <span className={`home-dot ${system ? 'ok' : 'off'}`} />
                  <span className="home-sys-name">{t('home_disk')}</span>
                  <span className="qc-mono home-sys-val">
                    {system ? `${system.diskUsed} / ${system.diskTotal}` : '—'}
                  </span>
                </div>
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
                      {task.created_at ? dayjs(task.created_at).format('MM-DD HH:mm') : '—'}
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
