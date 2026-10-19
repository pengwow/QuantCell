/**
 * 首页 / 工作台
 *
 * 定位：登录后的第一屏，回答三个问题 —— 系统是否正常、策略在跑什么、下一步去哪。
 * 数据全部来自现有接口，任一接口失败只影响对应区块，不阻塞整页渲染。
 */
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Skeleton,
  Space,
  Tag,
  theme,
} from 'antd';
import {
  IconArrowRight,
  IconChartCandle,
  IconChartHistogram,
  IconCpu,
  IconDatabase,
  IconPlayerPlay,
  IconRefresh,
  IconRobot,
  IconShield,
  IconSparkles,
  IconTrendingUp,
} from '@tabler/icons-react';
import dayjs from 'dayjs';

import PageContainer from '@/components/PageContainer';
import { usePolling } from '@/hooks/usePolling';
import { backtestApi, systemApi } from '@/api';
import workerApi from '@/api/workerApi';
import type { BacktestTask } from '@/types/backtest';
import type { Worker } from '@/types/worker';
import type { SystemMetrics } from '@/pages/setting/types';
import { useQuantColors } from '@/utils/colors';
import { formatPercent, formatUSD } from '@/utils/format';
import './HomePage.css';

/** 回测状态 → antd Tag 颜色，与 BacktestList 保持一致 */
const BACKTEST_STATUS_COLOR: Record<string, string> = {
  completed: 'success',
  running: 'processing',
  in_progress: 'processing',
  failed: 'error',
  pending: 'default',
};

const HomePage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const quant = useQuantColors();

  const [workers, setWorkers] = useState<Worker[]>([]);
  const [backtests, setBacktests] = useState<BacktestTask[]>([]);
  const [system, setSystem] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  // 三个接口互不依赖，用 allSettled 保证单个失败不影响其他区块
  const load = useCallback(async () => {
    const [workerRes, backtestRes, systemRes] = await Promise.allSettled([
      workerApi.getWorkers({ page: 1, page_size: 50 }),
      backtestApi.getBacktestList(),
      systemApi.getSystemMetrics(),
    ]);

    if (workerRes.status === 'fulfilled') setWorkers(workerRes.value.items ?? []);
    if (backtestRes.status === 'fulfilled') setBacktests(backtestRes.value.backtests ?? []);
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

  const online = system?.connectionStatus === 'connected';
  const cpu = Math.round(system?.cpuUsage ?? 0);
  const username = localStorage.getItem('nickname') || localStorage.getItem('username') || '';

  const quickActions = [
    {
      path: '/chart',
      icon: <IconChartCandle size="1.15em" />,
      label: t('chart'),
      desc: t('home_quick_chart_desc'),
    },
    {
      path: '/agent',
      icon: <IconRobot size="1.15em" />,
      label: t('strategy_agent'),
      desc: t('home_quick_agent_desc'),
    },
    {
      path: '/backtest',
      icon: <IconTrendingUp size="1.15em" />,
      label: t('backtest'),
      desc: t('home_quick_backtest_desc'),
    },
    {
      path: '/factor-analysis',
      icon: <IconChartHistogram size="1.15em" />,
      label: t('factor_analysis'),
      desc: t('home_quick_factor_desc'),
    },
    {
      path: '/data-management',
      icon: <IconDatabase size="1.15em" />,
      label: t('data_management'),
      desc: t('home_quick_data_desc'),
    },
    {
      path: '/risk-monitor',
      icon: <IconShield size="1.15em" />,
      label: t('risk_monitor'),
      desc: t('home_quick_risk_desc'),
    },
  ];

  // 主题色通过 CSS 变量下传，避免在样式文件里硬编码亮/暗两套颜色
  const themeVars = {
    '--home-accent': token.colorPrimary,
    '--home-accent-soft': `${token.colorPrimary}14`,
    '--home-grid-color': `${token.colorPrimary}14`,
    '--home-border': token.colorBorderSecondary,
    '--home-hover': token.colorFillQuaternary,
    '--home-positive': quant.positive,
    '--home-negative': quant.negative,
    '--home-warning': quant.warning,
    '--home-muted': token.colorTextQuaternary,
    '--home-text-secondary': token.colorTextSecondary,
  } as React.CSSProperties;

  return (
    <PageContainer className="home-page" >
      <div style={themeVars}>
        <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
          {/* 顶部品牌区：身份 + 主操作 + 系统状态 */}
          <Card className="home-hero" styles={{ body: { padding: 0 } }}>
            <div className="home-hero__inner">
              <div className="home-hero__grid" aria-hidden />
              <div className="home-hero__glow" aria-hidden />

              <div className="relative z-10 flex flex-col gap-6 p-6 md:p-8">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <img src="/logo.svg" alt="QuantCell" className="size-12 shrink-0" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl font-semibold tracking-tight">QuantCell</span>
                        <Tag className="m-0" color="processing">
                          v{__APP_VERSION__}
                        </Tag>
                      </div>
                      <div className="mt-1 text-sm home-muted">
                        {t('home_tagline')}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="primary"
                      icon={<IconPlayerPlay size="1.1em" />}
                      onClick={() => navigate('/strategy-worker')}
                    >
                      {t('home_create_task')}
                    </Button>
                    <Button
                      icon={<IconTrendingUp size="1.1em" />}
                      onClick={() => navigate('/backtest/config')}
                    >
                      {t('home_start_backtest')}
                    </Button>
                    <Button
                      icon={<IconSparkles size="1.1em" />}
                      onClick={() => navigate('/agent')}
                    >
                      {t('strategy_agent')}
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs home-muted">
                  <span className={`home-status ${online ? 'is-online' : 'is-offline'}`}>
                    <span className="home-status__dot" />
                    {online ? t('home_system_online') : t('home_system_offline')}
                  </span>
                  <span>
                    {username
                      ? t('home_welcome_back', { name: username })
                      : t('home_welcome_back_guest')}
                  </span>
                  <span className="hidden sm:inline">{t('home_hero_desc')}</span>
                </div>
              </div>
            </div>
          </Card>

          {/* KPI 指标条 */}
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} xl={6}>
              <KpiCard
                icon={<IconPlayerPlay size="1.15em" />}
                label={t('home_kpi_running')}
                value={String(runningWorkers.length)}
                hint={t('home_kpi_running_hint', { total: workers.length })}
              />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <KpiCard
                icon={<IconTrendingUp size="1.15em" />}
                label={t('home_kpi_pnl')}
                value={formatUSD(totalProfit, { showSign: true })}
                hint={t('home_kpi_pnl_hint')}
                tone={totalProfit > 0 ? quant.positive : totalProfit < 0 ? quant.negative : undefined}
              />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <KpiCard
                icon={<IconChartHistogram size="1.15em" />}
                label={t('home_kpi_backtests')}
                value={String(backtests.length)}
                hint={t('home_kpi_backtests_hint')}
              />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <KpiCard
                icon={<IconCpu size="1.15em" />}
                label={t('home_kpi_cpu')}
                value={system ? `${cpu}%` : '-'}
                hint={t('home_kpi_cpu_hint')}
              />
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                {/* 策略任务 */}
                <Card
                  title={t('home_running_tasks')}
                  extra={
                    <Button type="link" size="small" onClick={() => navigate('/strategy-worker')}>
                      {t('home_view_all')}
                      <IconArrowRight size="1em" />
                    </Button>
                  }
                >
                  {loading && taskPreview.length === 0 ? (
                    <Skeleton active paragraph={{ rows: 4 }} title={false} />
                  ) : taskPreview.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('home_no_tasks')}
                    >
                      <Button type="primary" size="small" onClick={() => navigate('/strategy-worker')}>
                        {t('home_create_task')}
                      </Button>
                    </Empty>
                  ) : (
                    <div className="home-list">
                      {taskPreview.map((worker) => {
                        const profit = worker.total_profit ?? 0;
                        const symbols = worker.trading_config?.symbols_config?.symbols ?? [];
                        const strategyName =
                          worker.strategy_info?.name || worker.strategy_type || '-';

                        return (
                          <button
                            key={worker.id}
                            type="button"
                            className="home-row"
                            onClick={() => navigate(`/strategy-worker/${worker.id}`)}
                          >
                            <span className="home-dot" data-status={worker.status} />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium">
                                {worker.name}
                              </span>
                              <span className="block truncate text-xs home-muted">
                                {strategyName}
                                {symbols.length > 0 && ` · ${symbols.slice(0, 2).join(' / ')}`}
                                {symbols.length > 2 && ` +${symbols.length - 2}`}
                              </span>
                            </span>
                            <span className="shrink-0 text-right">
                              <span
                                className="home-num block text-sm font-medium"
                                style={{
                                  color:
                                    profit > 0
                                      ? quant.positive
                                      : profit < 0
                                        ? quant.negative
                                        : undefined,
                                }}
                              >
                                {formatUSD(profit, { showSign: true })}
                              </span>
                              <span className="block text-xs home-muted">
                                {t(worker.status)}
                              </span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </Card>

                {/* 最近回测 */}
                <Card
                  title={t('home_recent_backtests')}
                  extra={
                    <Button type="link" size="small" onClick={() => navigate('/backtest')}>
                      {t('home_view_all')}
                      <IconArrowRight size="1em" />
                    </Button>
                  }
                >
                  {loading && recentBacktests.length === 0 ? (
                    <Skeleton active paragraph={{ rows: 4 }} title={false} />
                  ) : recentBacktests.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('home_no_backtests')}
                    >
                      <Button type="primary" size="small" onClick={() => navigate('/backtest/config')}>
                        {t('home_start_backtest')}
                      </Button>
                    </Empty>
                  ) : (
                    <div className="home-list">
                      {recentBacktests.map((task) => (
                        <button
                          key={task.id}
                          type="button"
                          className="home-row"
                          onClick={() => navigate(`/backtest/detail/${task.id}`)}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium">
                              {task.strategy_name}
                            </span>
                            <span className="block truncate text-xs home-muted">
                              {task.created_at
                                ? dayjs(task.created_at).format('YYYY-MM-DD HH:mm')
                                : '-'}
                            </span>
                          </span>
                          <span className="shrink-0 text-right">
                            <span
                              className="home-num block text-sm font-medium"
                              style={{
                                color:
                                  (task.total_return ?? 0) > 0
                                    ? quant.positive
                                    : (task.total_return ?? 0) < 0
                                      ? quant.negative
                                      : undefined,
                              }}
                            >
                              {formatPercent(task.total_return, { showSign: true })}
                            </span>
                            <span className="block text-xs home-muted">
                              {t('home_max_drawdown')} {formatPercent(task.max_drawdown)}
                            </span>
                          </span>
                          <Tag
                            className="m-0 shrink-0"
                            color={BACKTEST_STATUS_COLOR[task.status] ?? 'default'}
                          >
                            {t(task.status)}
                          </Tag>
                        </button>
                      ))}
                    </div>
                  )}
                </Card>
              </Space>
            </Col>

            <Col xs={24} xl={8}>
              <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                {/* 系统状态 */}
                <Card
                  title={t('home_system_status')}
                  extra={
                    <Button
                      type="text"
                      size="small"
                      icon={<IconRefresh size="1em" />}
                      loading={loading}
                      onClick={() => {
                        setLoading(true);
                        void load();
                      }}
                    />
                  }
                >
                  <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="home-muted">{t('home_connection')}</span>
                      <Badge
                        status={online ? 'success' : 'error'}
                        text={online ? t('home_system_online') : t('home_system_offline')}
                      />
                    </div>

                    <div>
                      <div className="mb-1 flex items-center justify-between text-sm">
                        <span className="home-muted">{t('home_cpu')}</span>
                        <span className="home-num">{system ? `${cpu}%` : '-'}</span>
                      </div>
                      <Progress
                        percent={cpu}
                        showInfo={false}
                        size="small"
                        strokeColor={token.colorPrimary}
                      />
                    </div>

                    <div className="flex items-center justify-between text-sm">
                      <span className="home-muted">{t('home_memory')}</span>
                      <span className="home-num">
                        {system ? `${system.memoryUsed} / ${system.memoryTotal}` : '-'}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-sm">
                      <span className="home-muted">{t('home_disk')}</span>
                      <span className="home-num">
                        {system ? `${system.diskUsed} / ${system.diskTotal}` : '-'}
                      </span>
                    </div>

                    <div className="text-xs home-muted">
                      {t('home_last_updated')}{' '}
                      {updatedAt ? dayjs(updatedAt).format('HH:mm:ss') : '-'}
                    </div>
                  </Space>
                </Card>

                {/* 快捷入口 */}
                <Card title={t('home_quick_actions')}>
                  <div className="home-quick-grid">
                    {quickActions.map((action) => (
                      <button
                        key={action.path}
                        type="button"
                        className="home-quick"
                        onClick={() => navigate(action.path)}
                      >
                        <span className="home-quick__icon">{action.icon}</span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">
                            {action.label}
                          </span>
                          <span className="block truncate text-xs home-muted">
                            {action.desc}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                </Card>
              </Space>
            </Col>
          </Row>
        </Space>
      </div>
    </PageContainer>
  );
};

/** KPI 卡片：数值用等宽数字，避免轮询刷新时宽度跳动 */
function KpiCard({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
  tone?: string;
}) {
  return (
    <Card className="home-kpi" styles={{ body: { padding: '18px 20px' } }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs home-muted">{label}</div>
          <div className="home-kpi__value mt-1" style={{ color: tone }}>
            {value}
          </div>
          <div className="mt-1 truncate text-xs home-muted">{hint}</div>
        </div>
        <span className="home-kpi__icon">{icon}</span>
      </div>
    </Card>
  );
}

export default HomePage;
