import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Col, DatePicker, Popconfirm, Row, Select, Skeleton, Tooltip, App, Pagination } from 'antd';
import type { Dayjs } from 'dayjs';
import type { TableProps } from 'antd';
import { DeleteOutlined, EyeOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { backtestApi } from '../../api';
import { getBacktestProgress } from '../../api/backtest';
import { useTranslation } from 'react-i18next';
import { setPageTitle } from '@/utils/pageTitle';
import type { BacktestTask, BacktestSummaryData, BacktestProgressData } from '../../types/backtest';
import PageContainer from '@/components/PageContainer';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import { useGuestRestriction } from '@/hooks/useGuestRestriction';
import dayjs from 'dayjs';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType } from '@/hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import { METRIC_CARDS, formatMetricValue } from './metricCards';
import { buildEquityGeometry, formatCashGrouped, formatElapsedCompact, formatFeePercent } from './bcFormat';
import './backtest.css';

// 状态筛选（chips）：'all' 不传后端
type FilterStatus = 'all' | 'completed' | 'running' | 'failed';

// 排序字段（与后端 sort_by 取值对齐）
type SortField = 'created_at' | 'total_return' | 'max_drawdown' | 'strategy_name';
type SortOrder = 'asc' | 'desc';

const STATUS_CHIPS: Array<{ value: FilterStatus; i18nKey: string }> = [
  { value: 'all', i18nKey: 'all' },
  { value: 'completed', i18nKey: 'status_completed' },
  { value: 'running', i18nKey: 'status_running' },
  { value: 'failed', i18nKey: 'status_failed' },
];

// 行内摘要 KPI（demo bt-detail mstats 对位）：全部取自组合级真实指标，缺哪个少哪张
const SUMMARY_METRIC_KEYS = ['total_return', 'sharpe_ratio', 'max_drawdown', 'total_trades', 'win_rate'] as const;

const BacktestList = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { isGuest } = useGuestRestriction();

  // 回测任务数据（服务端分页：tasks 即当前页数据）
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  // 视图类型：跟随系统设置「默认展示类型」，页面不提供切换
  const viewType = useViewType();

  // 筛选状态（搜索词回车/清除才提交服务端；chips 即点即查）
  const [searchText, setSearchText] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<FilterStatus>('all');
  // 创建日期范围筛选（工具栏 RangePicker；服务端按 created_at 日粒度含端点过滤）
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  // 分页：pageSize 来自全局配置（条数切换器即全站开关）；total 为过滤后总数
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [page, setPage] = useState<number>(1);
  const [total, setTotal] = useState<number>(0);
  // 无筛选总数（页头副标「任务表 N 条」口径，不随筛选抖动）
  const [overallTotal, setOverallTotal] = useState<number>(0);

  // 选中的行（点击行打选中 tint + 列表下方显示部分详情；键盘 ↑↓ 也可移动，Enter=眼睛进完整详情）
  const [selectedRowKey, setSelectedRowKey] = useState<React.Key>('');

  // 行内部分详情（demo #view-backtest .bt-detail）：轻摘要按行懒加载，命中过的行复用缓存
  const [summary, setSummary] = useState<BacktestSummaryData | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(false);
  const summaryCache = useRef(new Map<string, BacktestSummaryData>());

  // 运行中/失败任务的进度快照（demo bt-run 进度条 / bt-fail 错误块）：
  // 只在选中任务处于这两种状态时按任务 id 拉一次；progress 是内存态，
  // 服务重启后的旧失败任务拿不到 error（接口返回空）→ 如实不渲染，不编原因
  const [progress, setProgress] = useState<BacktestProgressData | null>(null);

  // 选中行必须仍在当前页才显示面板（翻页/筛选后行不可见 → 面板自然隐藏，回来又恢复）
  const selectedTask = tasks.find((task) => task.id === selectedRowKey) || null;

  useEffect(() => {
    if (!selectedRowKey || !selectedTask) {
      setSummary(null);
      setSummaryError(false);
      return;
    }
    const cached = summaryCache.current.get(String(selectedRowKey));
    if (cached) {
      setSummary(cached);
      setSummaryLoading(false);
      setSummaryError(false);
      return;
    }
    let cancelled = false;
    setSummary(null);
    setSummaryError(false);
    setSummaryLoading(true);
    backtestApi
      .getBacktestSummary(String(selectedRowKey))
      .then((data) => {
        if (cancelled) return;
        if (data && typeof data === 'object' && Array.isArray((data as unknown as { metrics?: unknown }).metrics)) {
          // 后端契约是 key→value 字典；数组形态说明命中了旧详情接口，按失败处理不渲染
          setSummaryError(true);
          return;
        }
        summaryCache.current.set(String(selectedRowKey), data);
        setSummary(data);
      })
      .catch(() => {
        if (!cancelled) setSummaryError(true);
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRowKey, selectedTask]);

  // 进度快照：仅 running/in_progress/failed 需要（进度条 / 失败原因）
  const progressTaskId = selectedTask?.status && ['running', 'in_progress', 'failed'].includes(selectedTask.status)
    ? String(selectedTask.id)
    : '';
  useEffect(() => {
    if (!progressTaskId) {
      setProgress(null);
      return;
    }
    let cancelled = false;
    setProgress(null);
    getBacktestProgress(progressTaskId).then((data) => {
      if (!cancelled) setProgress(data);
    });
    return () => {
      cancelled = true;
    };
  }, [progressTaskId]);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('backtest_center'));
  }, [t]);

  // 加载回测任务列表（服务端分页/筛选/排序）
  // overrides：setState 异步生效前需要用新值发起请求时的显式传值入口
  const loadBacktestList = useCallback(async (overrides?: {
    page?: number;
    pageSize?: number;
    status?: FilterStatus;
    keyword?: string;
    sortBy?: SortField;
    sortOrder?: SortOrder;
    startTime?: string;
    endTime?: string;
  }) => {
    setLoading(true);
    try {
      const nextPage = overrides?.page ?? page;
      const nextPageSize = overrides?.pageSize ?? pageSize;
      const nextStatus = overrides?.status ?? statusFilter;
      const nextKeyword = overrides?.keyword ?? searchText;
      const nextSortBy = overrides?.sortBy ?? sortField;
      const nextSortOrder = overrides?.sortOrder ?? sortOrder;
      const nextStartTime = overrides?.startTime ?? dateRange?.[0]?.format('YYYY-MM-DD');
      const nextEndTime = overrides?.endTime ?? dateRange?.[1]?.format('YYYY-MM-DD');
      const response = await backtestApi.getBacktestList({
        page: nextPage,
        page_size: nextPageSize,
        // 'all' 表示不筛选状态，不传给后端
        status: nextStatus === 'all' ? undefined : nextStatus,
        keyword: nextKeyword || undefined,
        sort_by: nextSortBy,
        sort_order: nextSortOrder,
        start_time: nextStartTime || undefined,
        end_time: nextEndTime || undefined,
      });
      const rows = Array.isArray(response.backtests) ? response.backtests : [];
      const nextTotal = typeof response.total === 'number' ? response.total : rows.length;
      setTasks(rows);
      setTotal(nextTotal);
      // 页码越界钳制（切档位/筛掉数据后 current 可能超出最大页）
      setPage(Math.min(Math.max(1, nextPage), Math.max(1, Math.ceil(nextTotal / nextPageSize))));
      // 无筛选请求才刷新「任务表 N 条」口径，副标不随筛选抖动
      if (nextStatus === 'all' && !nextKeyword && !nextStartTime && !nextEndTime) {
        setOverallTotal(nextTotal);
      }
    } catch (error) {
      console.error('Failed to load backtest list:', error);
      message.error(t('backtest_list_load_failed', { message: error instanceof Error ? error.message : String(error) }));
    } finally {
      setLoading(false);
    }
  }, [message, t, page, pageSize, statusFilter, searchText, sortField, sortOrder, dateRange]);

  // 组件挂载时加载数据
  useEffect(() => {
    loadBacktestList();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 首载一次性执行
  }, []);

  // 状态 → §6.2 chip（运行中带 pulse 圆点；pending/stopped 等中性）
  const renderStatusChip = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="qc-chip ok">{t('status_completed')}</span>;
      case 'running':
      case 'in_progress':
        return <span className="qc-chip info"><span className="qc-pdot" />{t('status_running')}</span>;
      case 'failed':
        return <span className="qc-chip down">{t('status_failed')}</span>;
      case 'pending':
        return <span className="qc-chip quiet">{t('status_pending')}</span>;
      default:
        return <span className="qc-chip quiet">{status}</span>;
    }
  };

  // 策略类型 chip：rule/rl/llm 三类与策略管理页同形制（info/pri/warn），
  // 取不到（策略已删）显示占位 —— 不按策略名猜类型
  const renderKindChip = (kind: BacktestTask['strategy_kind']) => {
    switch (kind) {
      case 'rl':
        return <span className="qc-chip pri">{t('bt_kind_rl')}</span>;
      case 'llm':
        return <span className="qc-chip warn">{t('bt_kind_llm')}</span>;
      case 'rule':
        return <span className="qc-chip info">{t('bt_kind_rule')}</span>;
      default:
        return <span className="qc-mono qc-cell-none">—</span>;
    }
  };

  // 删除回测任务（Popconfirm 确认；入口按钮由访客禁用兜底）
  const handleDelete = async (taskId: string) => {
    try {
      await backtestApi.deleteBacktest(taskId);
      message.success(t('delete_success'));
      // 重新加载列表（页内删空时钳到上一页）
      const remaining = total - 1;
      const maxPage = Math.max(1, Math.ceil(remaining / pageSize));
      loadBacktestList({ page: Math.min(page, maxPage) });
    } catch (error) {
      console.error('Failed to delete backtest task:', error);
      message.error(t('delete_failed'));
    }
  };

  // 查看回测详情
  const handleViewDetail = (backtestId: string) => {
    navigate('/backtest/detail/' + backtestId);
  };

  // 跳转到回测配置页面
  const handleStartBacktest = () => {
    navigate('/backtest/config');
  };

  // 数值列：正绿负红；null →「—」弱文本（demo .c-num / .c-muted 口径）；0 中性不染色
  const renderReturn = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return <span className="qc-mono qc-cell-none">—</span>;
    }
    const cls = value > 0 ? 'qc-cell-up' : value < 0 ? 'qc-cell-down' : '';
    return (
      <span className={`qc-mono${cls ? ` ${cls}` : ''}`}>
        {value >= 0 ? '+' : ''}{value.toFixed(2)}%
      </span>
    );
  };

  // 最大回撤是幅度而非盈亏符号：接口给的是正数幅度（0.06%），按符号染红会把 0.00% 也显示成亏损。
  // ponytail: 一律中性前景色；若后端改为带符号的回撤值，再按符号上色
  const renderDrawdown = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return <span className="qc-mono qc-cell-none">—</span>;
    }
    return <span className="qc-mono">{value.toFixed(2)}%</span>;
  };

  // 空/缺字段统一「—」弱文本（老记录可能没有 symbols / intervals）
  const renderJoinField = (values: string[] | undefined | null) => {
    if (!values || values.length === 0) {
      return <span className="qc-mono qc-cell-none">—</span>;
    }
    return <span className="qc-mono">{values.join(',')}</span>;
  };

  // 「区间」列（demo .c-range）：`2025-09-01 → 2026-11-18`，mono 紧凑；
  // 任务行无 config 起止时整格「—」，不拿创建时间冒充回测区间
  const renderRange = (start?: string, end?: string) => {
    const day = (value?: string) => (/^\d{4}-\d{2}-\d{2}/.test(value || '') ? String(value).slice(0, 10) : null);
    const from = day(start);
    if (!from) {
      // 老任务/异常配置里出现过 "invalid-date" 之类非日期串：不渲染成残缺日期
      return <span className="qc-mono qc-cell-none">—</span>;
    }
    return (
      <span className="qc-cell-time qc-mono">
        {from} → {day(end) || '—'}
      </span>
    );
  };

  // 「订单」列（demo .c-num）：total_trades 原值右对齐，缺值「—」，不写 0
  const renderTradeCount = (value: number | undefined) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return <span className="qc-mono qc-cell-none">—</span>;
    }
    return <span className="qc-mono">{value}</span>;
  };

  // 行内摘要 KPI（demo .mstats）：与详情页同 spec 着色/格式；盈亏为 0 中性不染色
  const renderSummaryStats = (metrics: Record<string, number | string>) => {
    const cards = SUMMARY_METRIC_KEYS
      .map((key) => {
        const spec = METRIC_CARDS.find((m) => m.key === key);
        const value = Number(metrics[key]);
        return spec && Number.isFinite(value) ? { spec, value } : null;
      })
      .filter((c): c is { spec: (typeof METRIC_CARDS)[number]; value: number } => c !== null);
    if (cards.length === 0) return null;
    return (
      <div className="qc-kpi-grid bt-summary-stats">
        {cards.map(({ spec, value }) => {
          const color = spec.color(value, (k) => Number(metrics[k]));
          const tone = value === 0 ? '' : color === 'positive' ? 'up' : color === 'negative' ? 'down' : '';
          return (
            <div className="qc-kpi" key={spec.key}>
              <div className="qc-kpi-lb">{spec.label}</div>
              <div className={`qc-kpi-num${tone ? ` ${tone}` : ''}`}>{formatMetricValue(spec, value)}</div>
            </div>
          );
        })}
      </div>
    );
  };

  // 权益曲线块（demo .curve-wrap）：服务端采样点 ≤200，只画趋势；
  // 染色按走势（末>首 up / 末<首 down / 平线中性不画面积），期末 NAV 取组合真实 final_equity
  const renderEquityCurve = (summary: BacktestSummaryData) => {
    const points = summary.equity;
    if (!points || points.length < 2) return null;
    const values = points.map((p) => Number(p[1]));
    if (values.some((v) => !Number.isFinite(v))) return null;
    const geo = buildEquityGeometry(values);
    const tone = geo.flat ? '' : values[values.length - 1] > values[0] ? 'up' : 'down';
    const gradId = `bt-eq-${tone || 'flat'}`;
    const stroke = geo.flat ? 'var(--qc-text-quaternary)' : tone === 'up' ? 'var(--qc-success)' : 'var(--qc-error)';
    const finalNav = Number(summary.metrics.final_equity);
    const navValue = Number.isFinite(finalNav) ? finalNav : values[values.length - 1];

    // x 轴时间刻度（demo 8 档）：时间轴线性取等分点真实时间戳；标签按跨度自适应
    // ——≥90 天用 YY-MM，短区间用 MM-DD（8 个等分点落在同一月会得到 8 个相同
    // 月份标签，那比没有刻度更误导）；连续重复标签折叠，零宽区间不渲染刻度行
    const t0 = Number(points[0][0]);
    const t1 = Number(points[points.length - 1][0]);
    const daySpan = (t1 - t0) / 86_400_000;
    const labelFmt = daySpan >= 90 ? 'YY-MM' : 'MM-DD';
    const ticks = t1 > t0
      ? Array.from({ length: 8 }, (_, i) => t0 + ((t1 - t0) * i) / 7).reduce<string[]>((acc, ts) => {
          const label = dayjs(ts).format(labelFmt);
          if (acc[acc.length - 1] !== label) acc.push(label);
          return acc;
        }, [])
      : [];

    return (
      <div className="bt-curve">
        <div className="bt-curve-val">
          <div className="bt-curve-lb">{t('bt_final_nav')}</div>
          <div className={`qc-mono bt-curve-num${tone ? ` qc-cell-${tone}` : ''}`}>{formatCashGrouped(navValue)}</div>
        </div>
        <svg className="bt-curve-svg" viewBox="0 0 640 180" preserveAspectRatio="none" aria-label={t('backtest_equity_curve')}>
          {geo.area && (
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0"
                  style={{ stopColor: stroke, stopOpacity: 0.26 }}
                />
                <stop offset="1" style={{ stopColor: stroke, stopOpacity: 0 }} />
              </linearGradient>
            </defs>
          )}
          {[46, 92, 138].map((y) => (
            <line key={y} x1="0" y1={y} x2="640" y2={y} style={{ stroke: 'var(--qc-border)' }} strokeDasharray="3 5" />
          ))}
          {geo.area && <path d={geo.area} fill={`url(#${gradId})`} />}
          <path
            d={geo.line}
            fill="none"
            style={{ stroke }}
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <circle cx={geo.lastX} cy={geo.lastY} r="3" style={{ fill: stroke }} />
        </svg>
        {ticks.length > 0 && (
          <div className="qc-mono bt-curve-x">
            {ticks.map((label, i) => (
              <span key={i}>{label}</span>
            ))}
          </div>
        )}
      </div>
    );
  };

  // 行内摘要卡（demo .bt-detail）：head（标题/策略/chip/sub）+ KPI + 配置脚注；
  // 全部走轻摘要接口的真实数据，缺段自动省略，不造数
  const renderInlineSummary = () => {
    if (!selectedTask) return null;
    const cfg = summary?.backtest_config;
    const subSegs: string[] = [];
    if (cfg?.start_time) {
      subSegs.push(`${cfg.start_time.slice(0, 10)} → ${cfg.end_time ? cfg.end_time.slice(0, 10) : '—'}`);
    }
    const interval = cfg?.interval || summary?.intervals?.join(',');
    if (interval) subSegs.push(String(interval));
    // 耗时：≥48h（陈旧任务）不显示，见 formatElapsedCompact 注释
    const elapsed = typeof summary?.elapsed_seconds === 'number' ? formatElapsedCompact(summary.elapsed_seconds) : null;
    if (elapsed) subSegs.push(t('bt_summary_elapsed', { elapsed }));
    // 运行中：已运行时长 = created_at 到现在的真实差值（demo head-right「已运行 01h 07m」）
    const running = selectedTask.status === 'running' || selectedTask.status === 'in_progress';
    if (running && selectedTask.created_at) {
      const runningFor = formatElapsedCompact((Date.now() - dayjs(selectedTask.created_at).valueOf()) / 1000);
      if (runningFor) subSegs.push(t('bt_running_for', { elapsed: runningFor }));
    }
    // 进度接口的 overall_progress 是 0–100 的真实百分比；无快照（服务重启后的旧任务）就不画条
    const rawPercent = progress ? Number(progress.overall_progress) : NaN;
    const percent = Number.isFinite(rawPercent) ? Math.max(0, Math.min(100, Math.round(rawPercent))) : null;
    const failMessage = selectedTask.status === 'failed' ? progress?.error?.message : undefined;

    const footSegs: string[] = [];
    if (typeof cfg?.initial_cash === 'number') {
      footSegs.push(`${t('backtest_initial_cash')} ${formatCashGrouped(cfg.initial_cash)}`);
    }
    if (typeof cfg?.commission === 'number') {
      footSegs.push(`${t('backtest_commission')} ${formatFeePercent(cfg.commission)} ${t('bt_summary_fee_side')}`);
    }

    return (
      <div className="qc-card bt-summary" role="region" aria-label={t('backtest_detail')}>
        <div className="bt-summary-head">
          <span className="bt-summary-title">{t('backtest_detail')}</span>
          <span className="qc-mono bt-summary-strat">{selectedTask.strategy_name}</span>
          {renderKindChip(selectedTask.strategy_kind)}
          {renderStatusChip(selectedTask.status)}
          {subSegs.length > 0 && !summaryLoading && (
            <span className="qc-mono bt-summary-sub">{subSegs.join(' · ')}</span>
          )}
        </div>
        {summaryLoading && (
          <div className="bt-summary-body"><Skeleton active title={false} paragraph={{ rows: 2 }} /></div>
        )}
        {/* 运行中：真实总体进度（progress 接口）；「预计剩余」无源不做 */}
        {running && percent !== null && (
          <div className="bt-summary-body">
            <div className="qc-mono" style={{ fontSize: 11, color: 'var(--qc-text-tertiary)' }}>
              {t('bt_progress_label')}{' '}
              <span style={{ color: 'var(--qc-primary)' }}>{percent}%</span>
            </div>
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              style={{ height: 6, marginTop: 4, borderRadius: 3, background: 'var(--qc-border)', overflow: 'hidden' }}
            >
              <i style={{ display: 'block', height: '100%', width: `${percent}%`, background: 'var(--qc-primary)' }} />
            </div>
          </div>
        )}
        {/* 失败原因：progress 接口的 error.message（内存态，旧任务取不到就不渲染，不编结论句） */}
        {failMessage && (
          <div className="bt-summary-body">
            <div style={{ fontSize: 11.5, fontWeight: 550, color: 'var(--qc-error)' }}>
              {t('bt_fail_reason')}
              {progress?.error?.stage ? ` · ${progress.error.stage}` : ''}
            </div>
            <div
              className="qc-mono"
              style={{
                marginTop: 4,
                fontSize: 11,
                color: 'var(--qc-text-tertiary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {failMessage}
            </div>
          </div>
        )}
        {!summaryLoading && summaryError && (
          <div className="bt-summary-body bt-summary-empty">{t('bt_summary_load_failed')}</div>
        )}
        {!summaryLoading && !summaryError && summary && (
          <>
            {renderSummaryStats(summary.metrics)}
            {renderEquityCurve(summary)}
            {footSegs.length > 0 && (
              <div className="bt-summary-foot">
                <span className="qc-mono bt-summary-config">{footSegs.join(' · ')}</span>
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  // 表格列定义 — §6.5：时间 mono 11px fg-3、策略 mono 截断、状态 chip、数值右对齐
  const columns: TableProps<BacktestTask>['columns'] = [
    {
      title: t('bt_col_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 100,
      render: (value: string) => (
        <span className="qc-cell-time qc-mono">{value ? dayjs(value).format('MM-DD HH:mm') : '—'}</span>
      ),
    },
    {
      title: t('strategy'),
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      width: 220,
      ellipsis: { showTitle: false },
      // RL 任务 strategy_name 带 rl_model:/rl_ensemble: 前缀，拆成来源 chip + 模型名
      // （沿用原模型中心「RL 回测历史」页签的展示口径，合并后回测中心为唯一入口）
      render: (name: string) => {
        if (name?.startsWith('rl_model:') || name?.startsWith('rl_ensemble:')) {
          const [prefix, ...rest] = name.split(':');
          return (
            <Tooltip title={name} placement="topLeft">
              <span className="qc-cell-strat-wrap">
                <span className={`qc-chip ${prefix === 'rl_model' ? 'pri' : 'info'} qc-mono`}>
                  {t(prefix === 'rl_model' ? 'backtest_source_rl_model' : 'backtest_source_rl_ensemble')}
                </span>
                <span className="qc-cell-strat" style={{ maxWidth: 120 }}>{rest.join(':')}</span>
              </span>
            </Tooltip>
          );
        }
        return (
          <Tooltip title={name} placement="topLeft">
            <span className="qc-cell-strat-wrap">
              <span className="qc-cell-strat" style={{ maxWidth: 160 }}>{name || '—'}</span>
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: t('bt_col_kind'),
      dataIndex: 'strategy_kind',
      key: 'strategy_kind',
      width: 76,
      // 回测任务混合 rule / rl / llm 三类策略，靠这一列区分；
      // 值由后端按策略文件 AST 判定（rl_model:/rl_ensemble: 前缀归 rl），不是名字前缀猜测
      render: (kind: BacktestTask['strategy_kind']) => renderKindChip(kind),
    },
    {
      title: t('symbol'),
      dataIndex: 'symbols',
      key: 'symbols',
      width: 130,
      ellipsis: { showTitle: false },
      render: (values: string[] | undefined) => (
        <Tooltip title={values?.length ? values.join(',') : ''} placement="topLeft">
          {renderJoinField(values)}
        </Tooltip>
      ),
    },
    {
      // demo 列序：时间 / 策略 / 区间 / 周期 …；标的列是现网刻意增量，夹在策略与区间之间
      title: t('bt_col_range'),
      key: 'range',
      width: 190,
      render: (_, record: BacktestTask) => renderRange(record.start_time, record.end_time),
    },
    {
      title: t('bt_col_interval'),
      dataIndex: 'intervals',
      key: 'intervals',
      width: 84,
      render: (values: string[] | undefined) => (
        <span className="qc-mono qc-cell-none">{values?.length ? values.join(',') : '—'}</span>
      ),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      width: 92,
      render: (status: string) => renderStatusChip(status),
    },
    {
      title: t('return_rate'),
      dataIndex: 'total_return',
      key: 'total_return',
      width: 96,
      align: 'right',
      render: (value: number | undefined) => renderReturn(value),
    },
    {
      title: t('max_drawdown'),
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 104,
      align: 'right',
      render: (value: number | undefined) => renderDrawdown(value),
    },
    {
      // demo 列序：收益 → 订单（回撤列是现网刻意增量，按 demo 语义排在订单前）
      title: t('bt_col_orders'),
      dataIndex: 'total_trades',
      key: 'total_trades',
      width: 80,
      align: 'right',
      render: (value: number | undefined) => renderTradeCount(value),
    },
    {
      title: t('action'),
      key: 'action',
      width: 92,
      fixed: 'right',
      render: (_, record: BacktestTask) => (
        <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
          <Tooltip title={t('view_details')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('view_details')}
              onClick={() => handleViewDetail(record.id)}
            >
              <EyeOutlined />
            </button>
          </Tooltip>
          <Popconfirm
            title={t('confirm_delete_backtest')}
            description={t('delete_backtest_confirm')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('delete')}
            cancelText={t('cancel')}
            okButtonProps={{ danger: true }}
          >
            <Tooltip title={isGuest ? t('guest_delete_restricted') : t('delete')}>
              <button
                type="button"
                className="qc-mini-btn qc-icon-only danger"
                aria-label={isGuest ? t('guest_delete_restricted') : t('delete')}
                disabled={isGuest}
              >
                <DeleteOutlined />
              </button>
            </Tooltip>
          </Popconfirm>
        </div>
      ),
    },
  ];

  // 重置筛选（chips/排序/搜索/日期归位后按默认参数重拉第一页）
  const handleResetFilters = () => {
    setSearchText('');
    setStatusFilter('all');
    setSortField('created_at');
    setSortOrder('desc');
    setDateRange(null);
    loadBacktestList({
      page: 1,
      status: 'all',
      keyword: '',
      sortBy: 'created_at',
      sortOrder: 'desc',
      startTime: undefined,
      endTime: undefined,
    });
  };

  // 工具栏计数「显示 x-y / 共 z」：按当前页与页大小折算，空数据归 0
  const shownRange = (current: number, size: number, totalCount: number) => {
    const start = totalCount === 0 ? 0 : (current - 1) * size + 1;
    const end = Math.min(current * size, totalCount);
    return t('shown_range', { start, end, total: totalCount });
  };

  const hasFilters = searchText !== '' || statusFilter !== 'all' || dateRange !== null;

  // 渲染列表视图 — §6.5/§6.6/§6.7：chips 状态筛选 + DataTable + 行内摘要 + 脚注
  const renderListView = () => (
    <>
      <PageToolbar
        search={{
          value: searchText,
          onChange: (value) => {
            setSearchText(value);
            // 点 clear 清空时同步重发服务端过滤，避免「界面已清、结果仍是旧过滤」；§6.6 过滤联动页码归 1
            if (value === '') {
              loadBacktestList({ keyword: '', page: 1 });
            }
          },
          onPressEnter: (value) => loadBacktestList({ keyword: value, page: 1 }),
          placeholder: t('search_backtest'),
          ariaLabel: t('search_backtest'),
        }}
        filters={
          <>
            <div role="group" aria-label={t('filter_status')} style={{ display: 'contents' }}>
              {STATUS_CHIPS.map((chip) => (
                <button
                  key={chip.value}
                  type="button"
                  className={`qc-ichip${statusFilter === chip.value ? ' qc-ichip-on' : ''}`}
                  onClick={() => {
                    setStatusFilter(chip.value);
                    loadBacktestList({ status: chip.value, page: 1 });
                  }}
                >
                  {t(chip.i18nKey)}
                </button>
              ))}
            </div>
            {/* 创建日期范围（demo 工具栏无此控件，属显式需求扩展）：服务端含端点过滤 */}
            <DatePicker.RangePicker
              aria-label={t('date_range')}
              value={dateRange}
              allowClear
              onChange={(dates) => {
                setDateRange(dates);
                loadBacktestList({
                  page: 1,
                  startTime: dates?.[0]?.format('YYYY-MM-DD'),
                  endTime: dates?.[1]?.format('YYYY-MM-DD'),
                });
              }}
            />
            <Select
              aria-label={t('sort_by')}
              value={`${sortField}-${sortOrder}`}
              onChange={(value) => {
                const [field, order] = value.split('-');
                setSortField(field as SortField);
                setSortOrder(order as SortOrder);
                loadBacktestList({ sortBy: field as SortField, sortOrder: order as SortOrder, page: 1 });
              }}
              style={{ width: 150 }}
              options={[
                { value: 'created_at-desc', label: t('sort_create_time_desc') },
                { value: 'created_at-asc', label: t('sort_create_time_asc') },
                { value: 'total_return-desc', label: t('sort_return_desc') },
                { value: 'total_return-asc', label: t('sort_return_asc') },
                { value: 'max_drawdown-desc', label: t('sort_drawdown_desc') },
                { value: 'max_drawdown-asc', label: t('sort_drawdown_asc') },
                { value: 'strategy_name-asc', label: t('backtest_sort_strategy_az') },
                { value: 'strategy_name-desc', label: t('sort_name_desc') },
              ]}
            />
          </>
        }
        count={shownRange(page, pageSize, total)}
        actions={
          <Button onClick={handleResetFilters}>{t('reset_filter')}</Button>
        }
      />
      <DataTable<BacktestTask>
        columns={columns}
        dataSource={tasks}
        loading={loading}
        rowKey="id"
        rowClassName={(record) => (record.id === selectedRowKey ? 'qc-row-selected' : '')}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: (pg, size) => {
            // 条数变化写回全局配置，全站生效
            if (size !== pageSize) setPageSize(size);
            loadBacktestList({ page: pg, pageSize: size });
          },
        }}
        remote
        emptyTitle={hasFilters ? t('bt_no_match_title') : t('no_backtest_tasks')}
        emptyDescription={hasFilters ? t('bt_no_match_desc') : t('bt_empty_desc')}
        emptyAction={
          hasFilters ? (
            // demo 1215-1222：空态里直接给「清除筛选」动作（工具栏重置钮仍在）
            <button type="button" className="qc-mini-btn" onClick={handleResetFilters}>
              {t('bt_clear_filters')}
            </button>
          ) : (
            <button type="button" className="qc-mini-btn pri" onClick={handleStartBacktest}>
              {t('launch_backtest')}
            </button>
          )
        }
        onRow={(record) => ({
          onClick: () => {
            // demo #view-backtest 交互：点击行只做选中 + 列表下方显示部分详情；
            // 进完整详情走操作列的眼睛（或键盘 Enter），不再直接路由跳转
            setSelectedRowKey(record.id);
          },
          style: { cursor: 'pointer' },
        })}
      />
      {renderInlineSummary()}
      <div className="qc-footnote">
        <span>{t('bt_footnote')}</span>
      </div>
    </>
  );

  // 卡片视图 — 保留原结构，样式 token 化（触发服务端同页数据）
  const renderCardView = () => (
    <>
      {tasks.length === 0 && !loading && (
        <Card size="small">
          <QcEmpty
            title={hasFilters ? t('bt_no_match_title') : t('no_backtest_tasks')}
            description={hasFilters ? t('bt_no_match_desc') : t('bt_empty_desc')}
          />
        </Card>
      )}
      <Row gutter={[16, 16]}>
        {tasks.map((task) => (
          <Col xs={24} sm={12} md={8} lg={6} key={task.id}>
            <Card
              size="small"
              title={
                <div className="flex items-center justify-between">
                  <span className="qc-mono font-medium truncate" style={{ maxWidth: '70%' }}>
                    {task.strategy_name}
                  </span>
                  {renderStatusChip(task.status)}
                </div>
              }
              extra={
                // 删除统一放卡片右上角（与策略卡片一致）；卡片可点击需阻止冒泡
                <Popconfirm
                  title={t('confirm_delete_backtest')}
                  description={t('delete_backtest_confirm')}
                  onConfirm={(e) => {
                    e?.stopPropagation();
                    handleDelete(task.id);
                  }}
                  okText={t('delete')}
                  cancelText={t('cancel')}
                  okButtonProps={{ danger: true }}
                  disabled={isGuest}
                >
                  <Tooltip title={isGuest ? t('guest_delete_restricted') : t('delete')}>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      disabled={isGuest}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Tooltip>
                </Popconfirm>
              }
              className={selectedRowKey === task.id ? 'qc-card-selected' : ''}
              onClick={() => setSelectedRowKey(task.id)}
              onDoubleClick={() => handleViewDetail(task.id)}
              style={{ cursor: 'pointer', boxShadow: 'var(--qc-shadow-card)' }}
            >
              <div className="space-y-3" style={{ color: 'var(--qc-text-secondary)' }}>
                <div className="flex justify-between items-center">
                  <span style={{ color: 'var(--qc-text-tertiary)' }}>{t('return_rate')}</span>
                  {renderReturn(task.total_return)}
                </div>
                <div className="flex justify-between items-center">
                  <span style={{ color: 'var(--qc-text-tertiary)' }}>{t('max_drawdown')}</span>
                  {renderDrawdown(task.max_drawdown)}
                </div>
                <div className="flex justify-between items-center">
                  <span style={{ color: 'var(--qc-text-tertiary)' }}>{t('bt_col_time')}</span>
                  <span className="qc-cell-time qc-mono">{task.created_at ? dayjs(task.created_at).format('MM-DD HH:mm') : '—'}</span>
                </div>
                <div className="flex justify-end gap-2 pt-2" style={{ borderTop: '1px solid var(--qc-border)' }}>
                  <Button
                    type="link"
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleViewDetail(task.id);
                    }}
                  >
                    {t('view')}
                  </Button>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>
      <Row justify="center" style={{ marginTop: 16 }}>
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          showTotal={(totalCount) => t('total_items', { total: totalCount })}
          onChange={(pg, size) => {
            // 分页事件下沉服务端重新拉取；条数变化写回全局配置
            if (size !== pageSize) setPageSize(size);
            loadBacktestList({ page: pg, pageSize: size });
          }}
        />
      </Row>
    </>
  );

  // 键盘导航（↑↓ 移动选中行、Enter 打开详情；删除必须走 Popconfirm，见历史雷区）
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 输入控件内按键交给控件（搜索框里 Enter 是提交关键词，不能抢跑成「打开选中行详情」）
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) {
        return;
      }
      if (tasks.length === 0) return;

      const currentIndex = tasks.findIndex((item) => item.id === selectedRowKey);

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault();
          if (currentIndex > 0) {
            setSelectedRowKey(tasks[currentIndex - 1].id);
          } else if (currentIndex === -1) {
            setSelectedRowKey(tasks[0].id);
          }
          break;
        case 'ArrowDown':
          e.preventDefault();
          if (currentIndex === -1) {
            setSelectedRowKey(tasks[0].id);
          } else if (currentIndex < tasks.length - 1) {
            setSelectedRowKey(tasks[currentIndex + 1].id);
          }
          break;
        case 'Enter':
          e.preventDefault();
          if (currentIndex !== -1) {
            handleViewDetail(tasks[currentIndex].id);
          }
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [selectedRowKey, tasks]);

  return (
    <PageContainer
      title={t('backtest_center')}
      subtitle={t('bt_subtitle', { total: tasks.length, history: overallTotal })}
      actions={
        <>
          <Button
            type="primary"
            onClick={handleStartBacktest}
            style={{ height: 30, padding: '0 12px', fontSize: 12, fontWeight: 550 }}
          >
            {t('launch_backtest')}
          </Button>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/home')}
            style={{ height: 30, padding: '0 12px', fontSize: 12 }}
          >
            {t('back_to_home')}
          </Button>
        </>
      }
    >
      {viewType === 'list' ? renderListView() : renderCardView()}
    </PageContainer>
  );
};

export default BacktestList;
