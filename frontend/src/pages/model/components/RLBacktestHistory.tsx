import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, App, Tooltip } from 'antd';
import type { TableProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { EyeOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { backtestApi } from '@/api';
import type { BacktestTask } from '@/types/backtest';
import DataTable from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';

// 状态筛选chips：'all' 不传后端；label 复用 BacktestList 同款 status_* 词条
type FilterStatus = 'all' | 'completed' | 'running' | 'failed' | 'pending';

const STATUS_CHIPS: Array<{ value: FilterStatus; i18nKey: string }> = [
  { value: 'all', i18nKey: 'all' },
  { value: 'completed', i18nKey: 'status_completed' },
  { value: 'running', i18nKey: 'status_running' },
  { value: 'failed', i18nKey: 'status_failed' },
  { value: 'pending', i18nKey: 'status_pending' },
];

// 状态 → §6.2 chip（与回测中心列表同款映射：运行中带 pulse 圆点）
const renderStatusChip = (status: string, t: (k: string) => string) => {
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

// RL 回测历史（模型中心只读 Tab）：服务端 source=rl 过滤 + 分页/搜索/排序，
// 点击行进回测详情页——与回测中心列表、临时 Drawer 汇合到同一详情
const RLBacktestHistory = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const [rows, setRows] = useState<BacktestTask[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<FilterStatus>('all');
  const [sort, setSort] = useState<{ by: string; order: 'asc' | 'desc' }>({
    by: 'created_at',
    order: 'desc',
  });
  const [page, setPage] = useState(1);
  // pageSize 走全站档位（12 的倍数），条数切换持久化到全局配置
  const [pageSize, setPageSize] = useGlobalPageSize();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await backtestApi.getBacktestList({
        page,
        page_size: pageSize,
        keyword: keyword || undefined,
        status: status === 'all' ? undefined : status,
        sort_by: sort.by,
        sort_order: sort.order,
        source: 'rl',
      });
      setRows(resp.backtests ?? []);
      setTotal(resp.total ?? 0);
    } catch (error) {
      console.error('Failed to load RL backtest history:', error);
      message.error(
        t('backtest_list_load_failed', {
          message: error instanceof Error ? error.message : String(error),
        }),
      );
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword, status, sort, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  // §6.6 过滤联动：搜索/状态/排序变化页码归 1
  useEffect(() => {
    setPage(1);
  }, [keyword, status, sort]);

  const columns: TableProps<BacktestTask>['columns'] = [
    {
      // 与回测列表同款来源 chip：RL 模型-主色 / RL 集成-蓝
      title: t('backtest_strategy_name'),
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      width: 220,
      ellipsis: { showTitle: false },
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
              <span className="qc-cell-strat" style={{ maxWidth: 190 }}>{name || '—'}</span>
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: t('symbols'),
      dataIndex: 'symbols',
      key: 'symbols',
      width: 130,
      ellipsis: { showTitle: false },
      render: (v?: string[]) => (
        <Tooltip title={(v ?? []).join(',')} placement="topLeft">
          <span className="qc-mono qc-cell-none">{(v ?? []).length ? v!.join(',') : '—'}</span>
        </Tooltip>
      ),
    },
    {
      title: t('interval'),
      dataIndex: 'intervals',
      key: 'intervals',
      width: 90,
      ellipsis: { showTitle: false },
      render: (v?: string[]) => (
        <Tooltip title={(v ?? []).join(',')} placement="topLeft">
          <span className="qc-mono qc-cell-none">{(v ?? []).length ? v!.join(',') : '—'}</span>
        </Tooltip>
      ),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      width: 96,
      render: (s: string) => renderStatusChip(s, t),
    },
    {
      title: t('return_rate'),
      dataIndex: 'total_return',
      key: 'total_return',
      width: 100,
      align: 'right',
      sorter: true,
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return <span className="qc-mono qc-cell-none">—</span>;
        return (
          <span className={`qc-mono ${value >= 0 ? 'qc-cell-up' : 'qc-cell-down'}`}>
            {value >= 0 ? '+' : ''}
            {value.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: t('max_drawdown'),
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 106,
      align: 'right',
      sorter: true,
      // 幅度值不按符号染色（与回测中心同口径），中性前景
      render: (value: number | undefined) => {
        if (value === undefined || value === null) return <span className="qc-mono qc-cell-none">—</span>;
        return <span className="qc-mono">{value.toFixed(2)}%</span>;
      },
    },
    {
      title: t('create_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 110,
      sorter: true,
      render: (value: string) => (
        <Tooltip title={value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : ''}>
          <span className="qc-cell-time qc-mono">{value ? dayjs(value).format('MM-DD HH:mm') : '—'}</span>
        </Tooltip>
      ),
    },
    {
      title: t('action'),
      key: 'action',
      width: 72,
      fixed: 'right',
      render: (_, record: BacktestTask) => (
        <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
          <Tooltip title={t('view')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('view')}
              onClick={() => navigate('/backtest/detail/' + record.id)}
            >
              <EyeOutlined />
            </button>
          </Tooltip>
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <Alert type="info" showIcon title={t('rl_history_hint')} />
      <PageToolbar
        search={{
          value: keyword,
          onChange: (v) => setKeyword(v),
          placeholder: t('search'),
          ariaLabel: t('search'),
        }}
        filters={
          <div role="group" aria-label={t('filter_status')} style={{ display: 'contents' }}>
            {STATUS_CHIPS.map((chip) => (
              <button
                key={chip.value}
                type="button"
                className={`qc-ichip${status === chip.value ? ' qc-ichip-on' : ''}`}
                onClick={() => setStatus(chip.value)}
              >
                {t(chip.i18nKey)}
              </button>
            ))}
          </div>
        }
      />
      <DataTable<BacktestTask>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        onRow={(record) => ({
          onClick: () => navigate('/backtest/detail/' + record.id),
          style: { cursor: 'pointer' },
        })}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: (p, ps) => {
            // 条数变化写回全局配置，全站生效
            if (ps !== pageSize) setPageSize(ps);
            setPage(p);
          },
        }}
        /* 服务端分页：rows 已按页裁好 */
        remote
        emptyTitle={t('rl_history_empty')}
        onChange={(_pagination, _filters, sorter) => {
          // 服务端排序：清空排序时回落创建时间倒序
          const s = Array.isArray(sorter) ? sorter[0] : sorter;
          if (s?.field && s?.order) {
            setSort({ by: String(s.field), order: s.order === 'ascend' ? 'asc' : 'desc' });
          } else {
            setSort({ by: 'created_at', order: 'desc' });
          }
        }}
      />
    </div>
  );
};

export default RLBacktestHistory;
