import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  Tooltip,
  Modal,
  App,
  Select,
  Row,
  Col,
  Pagination,
} from 'antd';
import {
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { strategyApi } from '../../api';
import type { StrategyOverviewItem, StrategyParamRecord, StrategyVersionItem } from '../../api';
import { useTranslation } from 'react-i18next';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { setPageTitle } from '@/utils/pageTitle';
import PageContainer from '@/components/PageContainer';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import WorkerCreateModal from '@/components/worker/WorkerCreateModal';
import type { TablePaginationConfig, TableProps } from 'antd';
import dayjs from 'dayjs';
import { useGlobalPageSize } from '../../hooks/useGlobalPageSize';
import { useViewType } from '../../hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '../../constants/pagination';
import './StrategyManagement.css';

const { confirm } = Modal;

// 排序字段（现网增量：排序 Select 保留）
type SortField = 'name' | 'created_at' | 'updated_at';
type SortOrder = 'asc' | 'desc';

// 状态过滤：'' = 全部。其余取值 = /strategy/overview 的 state 契约值
type StateFilter = '' | 'live' | 'paper' | 'paused' | 'stopped' | 'error' | 'undeployed';

/**
 * 策略管理页面组件（demo #view-strategy 对齐）
 *
 * 数据源：GET /api/v1/strategy/overview（策略 × worker × 最近回测聚合）。
 * 状态/周期/标的/Worker/最近回测都是 worker 与任务表的聚合投影，本页不做本地拼凑；
 * 端点不可用时展示空态（不回退 /strategy/list 硬拼假字段）。
 * 「回测记录」页签已退役：回测统一在回测中心，?tab= 类返回链路进页即 replace 清空。
 */
const StrategyManagement = () => {
  const [items, setItems] = useState<StrategyOverviewItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [stateFilter, setStateFilter] = useState<StateFilter>('');
  const [sortField, setSortField] = useState<SortField>('updated_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  // 行选中（点击行 → 表下详情块；操作钮阻止冒泡）
  const [selectedRowKey, setSelectedRowKey] = useState<React.Key>('');
  // 创建 Worker：复用 worker 模块的现成创建弹窗（真实 POST /workers），不做死钮
  const [createWorkerOpen, setCreateWorkerOpen] = useState(false);
  // 详情块版本历史：懒加载（展开才请求），三态可分（loading / error / 空）
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versions, setVersions] = useState<StrategyVersionItem[] | null>(null);
  const [versionsState, setVersionsState] = useState<'idle' | 'loading' | 'error'>('idle');

  const navigate = useNavigate();
  const { t } = useTranslation();
  const { isGuest } = useGuestRestriction();
  const [searchParams, setSearchParams] = useSearchParams();
  const { message } = App.useApp();

  // 视图类型（跟随系统设置「默认展示类型」，页面不提供切换）
  const viewType = useViewType();

  // 全局分页大小（条数切换器即全站开关）
  const [pageSize, setPageSize] = useGlobalPageSize();

  const [pagination, setPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
  }));

  useEffect(() => {
    setPagination((prev) => ({ ...(prev || {}), pageSize }));
  }, [pageSize]);

  useEffect(() => {
    setPageTitle(t('strategy_management'));
  }, [t]);

  const loadOverview = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getStrategyOverview();
      // 拦截器已解包 data，直接得到 { strategies: [...] }
      setItems(response?.strategies ?? []);
    } catch (error) {
      console.error('Failed to load strategy overview:', error);
      setItems([]);
      message.error(t('load_strategy_list_failed_generic'));
    } finally {
      setLoading(false);
    }
  };

  // 首次挂载：?tab=backtests 等返回链路已随「回测记录」页签退役，
  // 任何带查询串的进入一律 replace 成裸路径（老书签/旧详情页返回不再复活退役页签）
  useEffect(() => {
    if (searchParams.toString()) {
      setSearchParams({}, { replace: true });
    }
    loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 路由参数一次性清理 + 首载
  }, []);

  // 创建策略
  const handleCreateStrategy = () => {
    navigate('/strategy-editor');
  };

  // 页头「发起回测」：回测配置统一在回测中心
  const handleLaunchBacktest = () => {
    navigate('/backtest/config');
  };

  // 行级「去回测」：带策略名预填（与策略编辑器同一 state 契约）
  const handleBacktestStrategy = (item: StrategyOverviewItem) => {
    navigate('/backtest/config', { state: { strategy: item, showConfig: true } });
  };

  // 编辑
  const handleEditStrategy = (item: StrategyOverviewItem) => {
    navigate(`/strategy-editor/${item.name}`);
  };

  // 删除策略（收敛为不显眼图标钮；访客早退 + 二次确认）
  const handleDeleteStrategy = (item: StrategyOverviewItem) => {
    if (isGuest) {
      message.warning(t('guest_delete_restricted'));
      return;
    }
    confirm({
      title: t('confirm_delete_strategy'),
      content: t('delete_strategy_confirm_msg', { name: item.name }),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          setLoading(true);
          await strategyApi.deleteStrategy(item.name);
          message.success(t('strategy_delete_success'));
          setSelectedRowKey((key) => (key === item.name ? '' : key));
          setPagination((prev) => ({ ...(prev || {}), current: 1 }));
          await loadOverview();
        } catch (error) {
          console.error('Failed to delete strategy:', error);
          message.error(t('strategy_delete_failed'));
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // —— 状态 → chip（demo 2985 SMAP 口径 + stopped/error 两个契约真实态）——
  const renderStateChip = (state: string | undefined) => {
    switch (state) {
      case 'live':
        return (
          <span className="qc-chip ok">
            <span className="qc-pdot" />
            {t('sm_state_live')}
          </span>
        );
      case 'paper':
        return <span className="qc-chip warn">{t('sm_state_paper')}</span>;
      case 'paused':
        return <span className="qc-chip quiet">{t('sm_state_paused')}</span>;
      case 'stopped':
        return <span className="qc-chip quiet">{t('sm_state_stopped')}</span>;
      case 'error':
        return <span className="qc-chip down">{t('sm_state_error')}</span>;
      case 'undeployed':
        return <span className="qc-chip info">{t('sm_state_undeployed')}</span>;
      default:
        // 契约外的缺席值：显示「—」弱文本，不猜测成某个聚合态
        return <span className="qc-mono qc-cell-none">—</span>;
    }
  };

  // 类型 chip：规则 info / RL 主色 / LLM warn（demo 1632/1642/1652）
  const renderKindChip = (kind: string | undefined) => {
    switch (kind) {
      case 'rl':
        return <span className="qc-chip pri">RL</span>;
      case 'llm':
        return <span className="qc-chip warn">LLM</span>;
      case 'rule':
        return <span className="qc-chip info">{t('sm_tag_rule')}</span>;
      default:
        return <span className="qc-mono qc-cell-none">—</span>;
    }
  };

  // 最近回测列：+x.xx% 涨绿/跌红、失败 down、运行中与未回测弱文本、0 不染色
  const renderLastBacktest = (item: StrategyOverviewItem) => {
    const lb = item.latest_backtest;
    if (!lb) return <span className="qc-mono qc-cell-none">{t('sm_bt_none')}</span>;
    const status = String(lb.status || '');
    if (status === 'running' || status === 'in_progress' || status === 'pending') {
      return <span className="qc-mono qc-cell-none">{t('sm_bt_running')}</span>;
    }
    if (status === 'failed') {
      return <span className="qc-mono qc-cell-down">{t('sm_bt_failed')}</span>;
    }
    if (typeof lb.total_return === 'number') {
      if (lb.total_return === 0) return <span className="qc-mono">0.00%</span>;
      const cls = lb.total_return > 0 ? 'qc-cell-up' : 'qc-cell-down';
      return (
        <span className={`qc-mono ${cls}`}>
          {lb.total_return > 0 ? '+' : ''}
          {lb.total_return.toFixed(2)}%
        </span>
      );
    }
    return <span className="qc-mono qc-cell-none">—</span>;
  };

  // 工具栏计数「显示 x-y / 共 z」
  const shownRange = (current: number, size: number, total: number) => {
    const start = total === 0 ? 0 : (current - 1) * size + 1;
    const end = Math.min(current * size, total);
    return t('shown_range', { start, end, total });
  };

  // 搜索 + 状态 chips + 排序 + 本地分页
  const filteredStrategies = useMemo(() => {
    let result = [...items];

    if (searchText) {
      const lower = searchText.toLowerCase();
      result = result.filter(
        (s) =>
          s.name?.toLowerCase().includes(lower) ||
          s.description?.toLowerCase().includes(lower) ||
          (s.symbols ?? []).some((sym) => sym?.toLowerCase().includes(lower))
      );
    }

    if (stateFilter) {
      result = result.filter((s) => s.state === stateFilter);
    }

    result.sort((a, b) => {
      let aVal = '';
      let bVal = '';
      switch (sortField) {
        case 'name':
          aVal = a.name || '';
          bVal = b.name || '';
          break;
        case 'created_at':
          aVal = a.created_at || '';
          bVal = b.created_at || '';
          break;
        case 'updated_at':
        default:
          aVal = a.updated_at || '';
          bVal = b.updated_at || '';
          break;
      }
      return sortOrder === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    });

    return result;
  }, [items, searchText, stateFilter, sortField, sortOrder]);

  // 状态计数（副标口径 + chips 显隐的单一事实源；缺 state 的行不进任何桶，如实）
  const counts = useMemo(() => {
    const c = { live: 0, paper: 0, paused: 0, stopped: 0, error: 0, undeployed: 0 };
    for (const s of items) {
      if (s.state && s.state in c) c[s.state as keyof typeof c] += 1;
    }
    return c;
  }, [items]);

  // 选中的策略（随筛选收窄，详情块始终对应可见行）
  const selectedItem = useMemo(
    () => filteredStrategies.find((s) => s.name === selectedRowKey) ?? null,
    [filteredStrategies, selectedRowKey]
  );

  // 换选中行 → 收起并清空版本历史缓存（条数来自 overview，重载后跟着变）
  useEffect(() => {
    setVersionsOpen(false);
    setVersions(null);
    setVersionsState('idle');
  }, [selectedItem?.name]);

  // 页头副标：demo 1601 六段口径 + hint；「草稿」无源不出现，已停止/错误有真数据才补段
  const pageSubtitle = useMemo(() => {
    const segs = [
      t('sm_sub_total', { n: items.length }),
      t('sm_sub_live', { n: counts.live }),
      t('sm_sub_paper', { n: counts.paper }),
      t('sm_sub_paused', { n: counts.paused }),
      ...(counts.stopped > 0 ? [t('sm_sub_stopped', { n: counts.stopped })] : []),
      ...(counts.error > 0 ? [t('sm_sub_error', { n: counts.error })] : []),
      t('sm_sub_undeployed', { n: counts.undeployed }),
      t('sm_sub_hint'),
    ];
    return segs.join(' · ');
  }, [t, items.length, counts]);

  // chips：全部 + 五个核心态恒显，stopped/error 只在真有数据时出现（不摆死钮），
  // 桶序与副标一致：运行中 / 模拟盘 / 已暂停 /（已停止、错误）/ 未部署
  const stateChips = useMemo(() => {
    const core: { value: StateFilter; count: number; key: string }[] = [
      { value: 'live', count: counts.live, key: 'sm_state_live' },
      { value: 'paper', count: counts.paper, key: 'sm_state_paper' },
      { value: 'paused', count: counts.paused, key: 'sm_state_paused' },
    ];
    const extra: { value: StateFilter; count: number; key: string }[] = [];
    if (counts.stopped > 0) extra.push({ value: 'stopped', count: counts.stopped, key: 'sm_state_stopped' });
    if (counts.error > 0) extra.push({ value: 'error', count: counts.error, key: 'sm_state_error' });
    return [...core, ...extra, { value: 'undeployed' as const, count: counts.undeployed, key: 'sm_state_undeployed' }];
  }, [counts]);

  // 表格列定义 — demo 1628 列序：策略/类型/周期/标的/状态/Worker/最近回测/操作
  const columns: TableProps<StrategyOverviewItem>['columns'] = [
    {
      title: t('sm_col_strategy'),
      dataIndex: 'name',
      key: 'name',
      width: 190,
      ellipsis: { showTitle: false },
      render: (text: string) => (
        <Tooltip title={text} placement="topLeft">
          <span className="qc-cell-strat" style={{ maxWidth: 150 }}>{text}</span>
        </Tooltip>
      ),
    },
    {
      title: t('sm_col_kind'),
      dataIndex: 'kind',
      key: 'kind',
      width: 76,
      render: (_: unknown, record: StrategyOverviewItem) => renderKindChip(record.kind),
    },
    {
      title: t('sm_col_interval'),
      dataIndex: 'interval',
      key: 'interval',
      width: 74,
      render: (text: string | null) =>
        text ? (
          <span className="qc-mono qc-cell-id">{text}</span>
        ) : (
          <span className="qc-mono qc-cell-none">—</span>
        ),
    },
    {
      title: t('sm_col_symbols'),
      dataIndex: 'symbols',
      key: 'symbols',
      width: 140,
      ellipsis: { showTitle: false },
      render: (symbols: string[] | null | undefined) => {
        if (!symbols?.length) return <span className="qc-mono qc-cell-none">—</span>;
        const joined = symbols.join(', ');
        return (
          <Tooltip title={joined} placement="topLeft">
            <span className="qc-mono" style={{ fontSize: 11.5 }}>{joined}</span>
          </Tooltip>
        );
      },
    },
    {
      title: t('sm_col_state'),
      dataIndex: 'state',
      key: 'state',
      width: 100,
      render: (state: string | undefined) => renderStateChip(state),
    },
    {
      title: t('sm_col_workers'),
      dataIndex: 'worker_count',
      key: 'worker_count',
      width: 82,
      align: 'right',
      render: (n: number | undefined) =>
        // 0 是真值：显示但走弱色，不染色
        n ? (
          <span className="qc-mono">{n}</span>
        ) : (
          <span className="qc-mono qc-cell-none">{n ?? 0}</span>
        ),
    },
    {
      title: t('sm_col_last_backtest'),
      key: 'latest_backtest',
      width: 118,
      align: 'right',
      render: (_: unknown, record: StrategyOverviewItem) => renderLastBacktest(record),
    },
    {
      title: t('action'),
      key: 'action',
      width: 190,
      fixed: 'right',
      render: (_: unknown, record: StrategyOverviewItem) => (
        <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className="qc-mini-btn"
            onClick={() => handleBacktestStrategy(record)}
          >
            {t('sm_action_backtest')}
          </button>
          <button type="button" className="qc-mini-btn" onClick={() => handleEditStrategy(record)}>
            {t('edit')}
          </button>
          <Tooltip title={isGuest ? t('guest_delete_restricted') : t('delete_strategy')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only danger"
              aria-label={isGuest ? t('guest_delete_restricted') : t('delete_strategy')}
              onClick={() => handleDeleteStrategy(record)}
              disabled={isGuest}
            >
              <DeleteOutlined />
            </button>
          </Tooltip>
        </div>
      ),
    },
  ];

  // 列表视图 — demo 1612-1714：搜索 + chips + 排序 Select（现网增量）+ 计数 + 表格
  const renderListView = () => {
    const paginationCfg = (pagination ?? {}) as TablePaginationConfig;
    const current = (paginationCfg.current as number) || 1;
    const currentSize = (paginationCfg.pageSize as number) || pageSize;
    return (
      <>
        <PageToolbar
          search={{
            value: searchText,
            onChange: (value) => {
              setSearchText(value);
              // §6.6 过滤联动：搜索变化页码归 1（历史雷区：搜索不重置页码）
              setPagination((prev) => ({ ...(prev || {}), current: 1 }));
            },
            placeholder: t('sm_search_placeholder'),
            ariaLabel: t('sm_search_placeholder'),
          }}
          filters={
            <>
              <div className="qc-row-chips" role="group" aria-label={t('sm_col_state')}>
                <button
                  type="button"
                  className={`qc-ichip${stateFilter === '' ? ' qc-ichip-on' : ''}`}
                  aria-pressed={stateFilter === ''}
                  onClick={() => {
                    setStateFilter('');
                    setPagination((prev) => ({ ...(prev || {}), current: 1 }));
                  }}
                >
                  {t('sm_filter_all')}
                </button>
                {stateChips.map((chip) => (
                  <button
                    key={chip.value}
                    type="button"
                    className={`qc-ichip${stateFilter === chip.value ? ' qc-ichip-on' : ''}`}
                    aria-pressed={stateFilter === chip.value}
                    onClick={() => {
                      setStateFilter(chip.value);
                      setPagination((prev) => ({ ...(prev || {}), current: 1 }));
                    }}
                  >
                    {t(chip.key)}
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
                }}
                style={{ width: 150 }}
                popupMatchSelectWidth={false}
                options={[
                  { value: 'updated_at-desc', label: t('sort_update_time_desc') },
                  { value: 'updated_at-asc', label: t('sort_update_time_asc') },
                  { value: 'created_at-desc', label: t('sort_create_time_backtest_desc') },
                  { value: 'created_at-asc', label: t('sort_create_time_backtest_asc') },
                  { value: 'name-asc', label: t('sort_name_asc') },
                  { value: 'name-desc', label: t('sort_name_desc') },
                ]}
              />
            </>
          }
          count={shownRange(current, currentSize, filteredStrategies.length)}
        />
        <DataTable<StrategyOverviewItem>
          columns={columns}
          dataSource={filteredStrategies}
          pagination={{
            ...pagination,
            onChange: (pg, size) => {
              if (size !== pageSize) setPageSize(size);
              setPagination({ ...(pagination || {}), current: pg, pageSize: size });
            },
          }}
          loading={loading}
          rowKey="name"
          rowClassName={(record) => (record.name === selectedRowKey ? 'qc-row-selected' : '')}
          onRow={(record) => ({
            onClick: () => setSelectedRowKey(record.name),
            style: { cursor: 'pointer' },
          })}
          onChange={(newPagination) => {
            if (newPagination.pageSize && newPagination.pageSize !== pageSize) {
              setPageSize(newPagination.pageSize);
            }
            setPagination(newPagination);
          }}
          emptyTitle={searchText || stateFilter ? t('no_data') : t('no_strategies')}
        />
      </>
    );
  };

  // —— demo .kvtab 参数键值：k = 参数名，v = 默认值 + [范围] + 弱色描述 ——
  const fmtParamValue = (p: StrategyParamRecord): string => {
    const d = p.default;
    if (d === null || d === undefined || d === '') return '—';
    if (Array.isArray(d)) return d.map((x) => String(x)).join(', ') || '—';
    if (typeof d === 'object') return JSON.stringify(d);
    return String(d);
  };

  // ponytail: 范围只合成 min/max（options 少见且宽度受限），补齐需真实参数元数据更全时再做
  const fmtParamRange = (p: StrategyParamRecord): string => {
    const parts: string[] = [];
    if (typeof p.min === 'number' && typeof p.max === 'number') parts.push(`${p.min} ~ ${p.max}`);
    else if (typeof p.min === 'number') parts.push(`≥ ${p.min}`);
    else if (typeof p.max === 'number') parts.push(`≤ ${p.max}`);
    return parts.length ? `[${parts[0]}]` : '';
  };

  const renderParamsKv = (params: StrategyParamRecord[] | undefined) => {
    if (!params?.length) {
      return <div className="sm-detail-empty">{t('sm_detail_no_params')}</div>;
    }
    return (
      <table className="sm-kvtab">
        <tbody>
          {params.map((p, i) => {
            const range = fmtParamRange(p);
            return (
              <tr key={p.name || `param-${i}`}>
                <td className="k">
                  <span className="qc-mono">{p.name || '—'}</span>
                </td>
                <td className="v">
                  <span className="qc-mono">{fmtParamValue(p)}</span>
                  {range && <span className="sm-kv-range qc-mono">{range}</span>}
                  {p.description && <span className="sm-kv-desc">{p.description}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  };

  // 版本历史折叠：首次展开才请求 /strategy/{name}/versions（只回元信息，不含 code）
  const toggleVersions = async () => {
    if (!selectedItem) return;
    if (versionsOpen) {
      setVersionsOpen(false);
      return;
    }
    setVersionsOpen(true);
    if (versions) return; // 已加载过，复用缓存
    setVersionsState('loading');
    try {
      const response = await strategyApi.getStrategyVersions(selectedItem.name);
      setVersions(response?.versions ?? []);
      setVersionsState('idle');
    } catch (error) {
      console.error('Failed to load strategy versions:', error);
      setVersionsState('error');
    }
  };

  // 版本历史列表：时间 + 版本号（无声明版本则 code_hash 前 8 位），最多 20 条
  const renderVersionList = () => {
    if (versionsState === 'loading') {
      return <div className="sm-ver-note">{t('sm_ver_loading')}</div>;
    }
    if (versionsState === 'error') {
      return <div className="sm-ver-note sm-ver-note-error">{t('sm_ver_failed')}</div>;
    }
    if (!versions || versions.length === 0) {
      return <div className="sm-ver-note">{t('sm_ver_empty')}</div>;
    }
    const shown = versions.slice(0, 20);
    return (
      <div className="sm-ver-list">
        {shown.map((v, i) => {
          const d = v.created_at ? dayjs(v.created_at) : null;
          const time = d?.isValid() ? d.format('MM-DD HH:mm') : '—';
          const label = v.version ? `v${v.version}` : (v.code_hash || '').slice(0, 8);
          return (
            <div className="sm-ver-row" key={`${v.code_hash}-${i}`}>
              <span className="qc-mono sm-ver-time">{time}</span>
              <span className="qc-mono sm-ver-label">{label || '—'}</span>
            </div>
          );
        })}
        {versions.length > shown.length && <div className="sm-ver-note">{t('sm_ver_more')}</div>}
      </div>
    );
  };

  // 表下详情块 — demo 1716-1729 同构：标题 + 名称 + 状态 chip + 版本；参数 KV + 去回测/创建 Worker + footer
  // 「版本历史 N 条」只读 /strategy/overview 的 version_count（真实快照数，0 时整段不渲染）
  const renderDetailBlock = () => {
    if (!selectedItem) return null;
    const verSegs: string[] = [];
    if (selectedItem.version) verSegs.push(`v${selectedItem.version}`);
    if (selectedItem.updated_at) {
      const d = dayjs(selectedItem.updated_at);
      if (d.isValid()) verSegs.push(t('sm_detail_updated', { d: d.format('MM-DD') }));
    }

    // footer 段落：「默认 runner：kernel」恒有（内核默认路径真值），
    // 累计回测次数取 /strategy/overview 的 backtest_count（真实任务总数）；字段缺席时隐藏该段
    const footSegs: string[] = [t('sm_detail_runner', { runner: 'kernel' })];
    if (typeof selectedItem.backtest_count === 'number') {
      footSegs.push(t('sm_detail_backtest_count', { n: selectedItem.backtest_count }));
    }
    const versionCount = selectedItem.version_count ?? 0;

    return (
      <div className="sm-detail" role="region" aria-label={t('sm_detail_title')}>
        <div className="sm-detail-head">
          <span className="sm-detail-title">{t('sm_detail_title')}</span>
          <span className="qc-mono sm-detail-name">{selectedItem.name}</span>
          {renderStateChip(selectedItem.state)}
          {verSegs.length > 0 && <span className="qc-mono sm-detail-ver">{verSegs.join(' · ')}</span>}
        </div>
        {renderParamsKv(selectedItem.params)}
        <div className="sm-detail-actions">
          <Button type="primary" onClick={() => handleBacktestStrategy(selectedItem)}>
            {t('sm_action_backtest')}
          </Button>
          <Button onClick={() => setCreateWorkerOpen(true)}>{t('create_worker')}</Button>
          <span className="sm-detail-foot">{footSegs.join(' · ')}</span>
          {versionCount > 0 && (
            <button
              type="button"
              className="sm-ver-toggle"
              aria-expanded={versionsOpen}
              onClick={toggleVersions}
            >
              <span>{t('sm_detail_version_count', { n: versionCount })}</span>
              <span className="sm-ver-caret" aria-hidden="true">
                {versionsOpen ? '▾' : '▸'}
              </span>
            </button>
          )}
        </div>
        {versionCount > 0 && versionsOpen && renderVersionList()}
      </div>
    );
  };

  // 卡片视图分页条：与 DataTable 同一 §6.7 原语
  const renderPgBar = (
    current: number,
    size: number,
    total: number,
    onPgChange: (page: number, size: number) => void
  ) =>
    total > 0 ? (
      <div className="qc-pg-bar">
        <div className="qc-pg-info">
          <span>{t('total_items', { total })}</span>
          <span className="qc-pg-sep">·</span>
          <span>{t('per_page')}</span>
          <Select
            size="small"
            className="qc-pg-size"
            value={size}
            popupMatchSelectWidth={false}
            aria-label={t('per_page')}
            onChange={(value) => onPgChange(1, value)}
            options={PAGE_SIZE_OPTIONS.map((n) => ({ value: Number(n), label: n }))}
          />
        </div>
        <Pagination
          size="small"
          className="qc-pagination"
          showLessItems
          showQuickJumper
          showSizeChanger={false}
          current={current}
          pageSize={size}
          total={total}
          onChange={onPgChange}
          itemRender={(pg, type, node) =>
            type === 'jump-prev' || type === 'jump-next' ? (
              <span className="qc-pg-ellipsis">…</span>
            ) : (
              node
            )
          }
        />
      </div>
    ) : null;

  // 卡片视图 — §6.3 卡片 chrome + §6.7 分页条；不因新列退化：补状态 chip 与 Worker 数
  const renderCardView = () => {
    const currentPage = (pagination?.current as number) || 1;
    const currentSize = (pagination?.pageSize as number) || pageSize;
    const startIndex = (currentPage - 1) * currentSize;
    const pageData = filteredStrategies.slice(startIndex, startIndex + currentSize);
    const pgChange = (page: number, size: number) => {
      if (size !== pageSize) setPageSize(size);
      setPagination({ ...(pagination || {}), current: page, pageSize: size });
    };

    const infoRow = (label: string, node: React.ReactNode) => (
      <div className="flex justify-between items-center" key={label}>
        <span>{label}</span>
        {node}
      </div>
    );

    return (
      <>
        {pageData.length > 0 ? (
          <Row gutter={[16, 16]}>
            {pageData.map((item) => (
              <Col xs={24} sm={12} md={8} lg={6} key={item.name}>
                <Card
                  size="small"
                  className={`qc-card${item.name === selectedRowKey ? ' qc-card-selected' : ''}`}
                  title={
                    <span
                      title={item.name}
                      className="qc-mono"
                      style={{
                        display: 'inline-block',
                        maxWidth: '100%',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        verticalAlign: 'bottom',
                      }}
                    >
                      {item.name}
                    </span>
                  }
                  extra={
                    <Space size={4}>
                      <Tooltip title={t('edit_strategy')}>
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditStrategy(item);
                          }}
                        />
                      </Tooltip>
                      <Tooltip title={isGuest ? t('guest_delete_restricted') : t('delete_strategy')}>
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          disabled={isGuest}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteStrategy(item);
                          }}
                        />
                      </Tooltip>
                    </Space>
                  }
                  hoverable
                  onClick={() => setSelectedRowKey(item.name)}
                  style={{ cursor: 'pointer', boxShadow: 'var(--qc-shadow-card)' }}
                >
                  <Space size={4} wrap style={{ marginBottom: 8 }}>
                    {renderKindChip(item.kind)}
                    {renderStateChip(item.state)}
                  </Space>
                  <div
                    className="space-y-1"
                    style={{ color: 'var(--qc-text-tertiary)', fontSize: 12 }}
                  >
                    {infoRow(
                      t('sm_col_interval'),
                      item.interval ? (
                        <span className="qc-mono" style={{ fontSize: 12 }}>{item.interval}</span>
                      ) : (
                        <span className="qc-mono qc-cell-none" style={{ fontSize: 12 }}>—</span>
                      )
                    )}
                    {infoRow(
                      t('sm_col_symbols'),
                      <span
                        className="qc-mono"
                        style={{ fontSize: 12, maxWidth: '60%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      >
                        {item.symbols?.length ? item.symbols.join(', ') : '—'}
                      </span>
                    )}
                    {infoRow(
                      t('sm_col_workers'),
                      item.worker_count ? (
                        <span className="qc-mono" style={{ fontSize: 12 }}>{item.worker_count}</span>
                      ) : (
                        <span className="qc-mono qc-cell-none" style={{ fontSize: 12 }}>0</span>
                      )
                    )}
                    {infoRow(t('sm_col_last_backtest'), renderLastBacktest(item))}
                    {infoRow(
                      t('update_time'),
                      <span className="qc-cell-time qc-mono">
                        {item.updated_at && dayjs(item.updated_at).isValid()
                          ? dayjs(item.updated_at).format('YYYY-MM-DD HH:mm')
                          : '—'}
                      </span>
                    )}
                  </div>

                  <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--qc-border)' }}>
                    <Row gutter={[8, 8]}>
                      <Col span={12}>
                        <Button
                          type="primary"
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleBacktestStrategy(item);
                          }}
                          style={{ width: '100%' }}
                        >
                          {t('sm_action_backtest')}
                        </Button>
                      </Col>
                      <Col span={12}>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditStrategy(item);
                          }}
                          style={{ width: '100%' }}
                        >
                          {t('edit')}
                        </Button>
                      </Col>
                    </Row>
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          <Card className="qc-card">
            <QcEmpty
              title={searchText || stateFilter ? t('no_data') : t('no_strategies')}
              action={
                !searchText && !stateFilter && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateStrategy}>
                    {t('create_first_strategy')}
                  </Button>
                )
              }
            />
          </Card>
        )}
        {renderPgBar(currentPage, currentSize, filteredStrategies.length, pgChange)}
      </>
    );
  };

  return (
    <PageContainer
      title={t('strategy_management')}
      subtitle={pageSubtitle}
      actions={
        <Space size={8}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateStrategy}
            style={{ height: 30, padding: '0 14px', fontSize: 12 }}
          >
            {t('new_strategy')}
          </Button>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={handleLaunchBacktest}
            style={{ height: 30, padding: '0 14px', fontSize: 12 }}
          >
            {t('launch_backtest')}
          </Button>
        </Space>
      }
    >
      {viewType === 'list' ? renderListView() : renderCardView()}
      {renderDetailBlock()}
      {/* 创建 Worker：复用 worker 模块创建弹窗（真实 POST /workers；成功后刷新聚合计数） */}
      <WorkerCreateModal
        visible={createWorkerOpen}
        onCancel={() => setCreateWorkerOpen(false)}
        onSuccess={() => {
          setCreateWorkerOpen(false);
          loadOverview();
        }}
      />
    </PageContainer>
  );
};

export default StrategyManagement;
