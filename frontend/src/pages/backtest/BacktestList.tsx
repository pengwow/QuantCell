import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Col, Popconfirm, Row, Select, Skeleton, Tooltip, App, Pagination } from 'antd';
import type { TableProps } from 'antd';
import { DeleteOutlined, EyeOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { backtestApi } from '../../api';
import { useTranslation } from 'react-i18next';
import { setPageTitle } from '@/utils/pageTitle';
import type { BacktestTask, BacktestSummaryData } from '../../types/backtest';
import PageContainer from '@/components/PageContainer';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import { useGuestRestriction } from '@/hooks/useGuestRestriction';
import dayjs from 'dayjs';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType } from '@/hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import { METRIC_CARDS, formatMetricValue } from './metricCards';
import { formatCashGrouped, formatElapsedCompact, formatFeePercent } from './bcFormat';
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
  }) => {
    setLoading(true);
    try {
      const nextPage = overrides?.page ?? page;
      const nextPageSize = overrides?.pageSize ?? pageSize;
      const nextStatus = overrides?.status ?? statusFilter;
      const nextKeyword = overrides?.keyword ?? searchText;
      const nextSortBy = overrides?.sortBy ?? sortField;
      const nextSortOrder = overrides?.sortOrder ?? sortOrder;
      const response = await backtestApi.getBacktestList({
        page: nextPage,
        page_size: nextPageSize,
        // 'all' 表示不筛选状态，不传给后端
        status: nextStatus === 'all' ? undefined : nextStatus,
        keyword: nextKeyword || undefined,
        sort_by: nextSortBy,
        sort_order: nextSortOrder,
      });
      const rows = Array.isArray(response.backtests) ? response.backtests : [];
      const nextTotal = typeof response.total === 'number' ? response.total : rows.length;
      setTasks(rows);
      setTotal(nextTotal);
      // 页码越界钳制（切档位/筛掉数据后 current 可能超出最大页）
      setPage(Math.min(Math.max(1, nextPage), Math.max(1, Math.ceil(nextTotal / nextPageSize))));
      // 无筛选请求才刷新「任务表 N 条」口径，副标不随筛选抖动
      if (nextStatus === 'all' && !nextKeyword) {
        setOverallTotal(nextTotal);
      }
    } catch (error) {
      console.error('Failed to load backtest list:', error);
      message.error(t('backtest_list_load_failed', { message: error instanceof Error ? error.message : String(error) }));
    } finally {
      setLoading(false);
    }
  }, [message, t, page, pageSize, statusFilter, searchText, sortField, sortOrder]);

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
          {renderStatusChip(selectedTask.status)}
          {subSegs.length > 0 && !summaryLoading && (
            <span className="qc-mono bt-summary-sub">{subSegs.join(' · ')}</span>
          )}
        </div>
        {summaryLoading && (
          <div className="bt-summary-body"><Skeleton active title={false} paragraph={{ rows: 2 }} /></div>
        )}
        {!summaryLoading && summaryError && (
          <div className="bt-summary-body bt-summary-empty">{t('bt_summary_load_failed')}</div>
        )}
        {!summaryLoading && !summaryError && summary && (
          <>
            {renderSummaryStats(summary.metrics)}
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
      width: 200,
      ellipsis: { showTitle: false },
      render: (name: string) => (
        <Tooltip title={name} placement="topLeft">
          <span className="qc-cell-strat-wrap">
            <span className="qc-cell-strat" style={{ maxWidth: 160 }}>{name || '—'}</span>
          </span>
        </Tooltip>
      ),
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

  // 重置筛选（chips/排序/搜索归位后按默认参数重拉第一页）
  const handleResetFilters = () => {
    setSearchText('');
    setStatusFilter('all');
    setSortField('created_at');
    setSortOrder('desc');
    loadBacktestList({
      page: 1,
      status: 'all',
      keyword: '',
      sortBy: 'created_at',
      sortOrder: 'desc',
    });
  };

  // 工具栏计数「显示 x-y / 共 z」：按当前页与页大小折算，空数据归 0
  const shownRange = (current: number, size: number, totalCount: number) => {
    const start = totalCount === 0 ? 0 : (current - 1) * size + 1;
    const end = Math.min(current * size, totalCount);
    return t('shown_range', { start, end, total: totalCount });
  };

  const hasFilters = searchText !== '' || statusFilter !== 'all';

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
          hasFilters ? undefined : (
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
      subtitle={t('bt_subtitle', { total: overallTotal })}
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
