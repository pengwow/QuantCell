import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App as AntdApp,
  Button,
  Card,
  Pagination,
  Popconfirm,
  Row,
  Select,
  Space,
  Tooltip,
} from 'antd';
import type { TableProps } from 'antd';
import {
  BarChartOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  ReloadOutlined,
  RocketOutlined,
  RollbackOutlined,
  TagOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { modelApi, type UnifiedModelRow } from '@/api/modelApi';
import { rlApi } from '@/api/rlApi';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType } from '@/hooks/useViewType';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import { ExpandableCardGrid } from '@/components/ui/ExpandableCardGrid';
import PageToolbar from '@/components/ui/PageToolbar';
import ModelDetailDrawer from './ModelDetailDrawer';
import RLBacktestModal from './RLBacktestModal';
import RegisterModelModal from './RegisterModelModal';

// 页头副标口径（design-spec §5 page-sub：只写接口能算出的数字，机制描述不编造）
export interface ModelHubStats {
  total: number;
  production: number;
  staging: number;
  shadow: number;
  archived: number;
  unregistered: number;
  missing: number;
}

function computeStats(rows: UnifiedModelRow[]): ModelHubStats {
  const s: ModelHubStats = { total: rows.length, production: 0, staging: 0, shadow: 0, archived: 0, unregistered: 0, missing: 0 };
  for (const r of rows) {
    const st = statusOf(r);
    if (st === 'production' || st === 'staging' || st === 'shadow' || st === 'archived' || st === 'unregistered' || st === 'missing') {
      s[st]++;
    } else {
      // 未知 stage 兜底计入 staging（与 statusOf 默认口径一致）
      s.staging++;
    }
  }
  return s;
}

// 状态五态:未注册(灰)/staging(琥珀)/production(绿)/archived(灰)/shadow(蓝)/文件缺失(琥珀)
type RowStatus = 'unregistered' | 'missing' | 'staging' | 'production' | 'archived' | 'shadow' | string;

function statusOf(row: UnifiedModelRow): RowStatus {
  if (row.registered && row.size_mb == null) return 'missing';
  if (!row.registered) return 'unregistered';
  return row.stage || 'staging';
}

// §6.2 chip 替代 antd Tag：production→ok / staging→warn / shadow→info / 其余中性；文件缺失 warn
function StatusChip({ row }: { row: UnifiedModelRow }) {
  const { t } = useTranslation();
  const s = statusOf(row);
  if (s === 'production') return <span className="qc-chip ok">production</span>;
  if (s === 'shadow') return <span className="qc-chip info">shadow</span>;
  if (s === 'missing') return <span className="qc-chip warn">{t('umt_status_missing')}</span>;
  if (s === 'staging') return <span className="qc-chip warn">staging</span>;
  if (s === 'archived') return <span className="qc-chip quiet">archived</span>;
  return <span className="qc-chip quiet">{t('umt_status_unregistered')}</span>;
}

// 算法标签文本:'-' / 空视为无(表格列与卡片视图共用)
function algoLabel(row: UnifiedModelRow): string | null {
  return row.algorithm && row.algorithm !== '-' ? row.algorithm.toUpperCase() : null;
}

// Sharpe 展示:兼容 sharpe_ratio 与 sharpe 两种键名(表格列与卡片视图共用)
function sharpeText(row: UnifiedModelRow): string {
  const v = row.metrics?.sharpe_ratio ?? row.metrics?.sharpe;
  return v == null ? '-' : Number(v).toFixed(2);
}

// Sharpe 染色:正 up / 负 down / 0 与空值中性(表格列与卡片视图共用同一套阈值)
function sharpeToneClass(row: UnifiedModelRow): string {
  const v = row.metrics?.sharpe_ratio ?? row.metrics?.sharpe;
  if (v == null) return '';
  const n = Number(v);
  return n > 0 ? ' qc-cell-up' : n < 0 ? ' qc-cell-down' : '';
}

// OOS Sharpe:优先 walk-forward OOS 口径,缺键回落到 registry metrics(缺值 = 无指标,不兜底成 0)
function oosSharpe(row: UnifiedModelRow): { text: string; tone: string } {
  const v = row.oos?.sharpe_ratio ?? row.metrics?.sharpe_ratio ?? row.metrics?.sharpe;
  if (v == null) return { text: '—', tone: '' };
  const n = Number(v);
  return { text: n.toFixed(2), tone: n > 0 ? ' qc-cell-up' : n < 0 ? ' qc-cell-down' : '' };
}

// 行内展开摘要的单格:label 11px 三级色 + value mono(缺字段的格子由调用侧整格省略)
function ExpCell({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span style={{ fontSize: 11, color: 'var(--qc-text-tertiary)' }}>{label}</span>
      <span className="qc-mono truncate" style={{ fontSize: 12, color: 'var(--qc-text)' }} title={typeof value === 'string' ? value : undefined}>
        {value}
      </span>
    </div>
  );
}

// 卡片视图元信息行:label 左 value 右（label 不换行，value 可截断）
function MetaRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="shrink-0 whitespace-nowrap" style={{ color: 'var(--qc-text-tertiary)' }}>{label}</span>
      <span className="min-w-0 truncate text-right">{value}</span>
    </div>
  );
}

export default function UnifiedModelTable({
  refreshKey,
  onStats,
}: {
  refreshKey: number;
  onStats?: (s: ModelHubStats) => void;
}) {
  const { t } = useTranslation();
  const { message, modal } = AntdApp.useApp();
  const [rows, setRows] = useState<UnifiedModelRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [algoFilter, setAlgoFilter] = useState<string>();
  // 状态筛选 chips（§6.6 ichip 原语）；'' = 全部
  const [stageFilter, setStageFilter] = useState<string>('');
  // 单选行;存 file_name 作为 rowKey/选中键
  const [selectedKey, setSelectedKey] = useState('');
  // 行内展开:单键(一次只展开一行),初始不展开
  const [expandedKey, setExpandedKey] = useState('');
  const [registerRow, setRegisterRow] = useState<UnifiedModelRow | null>(null);
  const [detailRow, setDetailRow] = useState<UnifiedModelRow | null>(null);
  const [backtestRow, setBacktestRow] = useState<UnifiedModelRow | null>(null);
  // 视图类型:跟随系统设置「默认展示类型」(复用 useViewType),页面不提供切换
  const view = useViewType();
  // pageSize 全站开关,返回值是元组(同 RLModelList 既有用法)
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [current, setCurrent] = useState(1);

  const loadRows = async () => {
    setLoading(true);
    try {
      const data = await modelApi.unifiedModels();
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      message.error(t('umt_msg_load_failed', { err: err instanceof Error ? err.message : String(err) }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refreshKey 驱动重拉(训练成功后强制刷新)
  }, [refreshKey]);

  // 页头副标统计上报：rows 变化即按全量口径重算（不含筛选）
  useEffect(() => {
    onStats?.(computeStats(rows));
  }, [rows, onStats]);

  const kw = keyword.trim().toLowerCase();
  const hasFilters = kw !== '' || !!algoFilter || !!stageFilter;
  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        if (kw && !(r.file_name.toLowerCase().includes(kw) || (r.model_id ?? '').toLowerCase().includes(kw))) {
          return false;
        }
        if (algoFilter && (r.algorithm || '-') !== algoFilter) return false;
        if (stageFilter && statusOf(r) !== stageFilter) return false;
        return true;
      }),
    [rows, kw, algoFilter, stageFilter],
  );

  const algoOptions = useMemo(
    () =>
      Array.from(new Set(rows.map((r) => r.algorithm || '-')))
        .filter((a) => a !== '-')
        .map((a) => ({ value: a, label: a.toUpperCase() })),
    [rows],
  );

  // 状态筛选 chips（§6.6 ichip 原语）
  const stageChips: Array<{ value: string; label: string }> = [
    { value: '', label: t('all') },
    { value: 'production', label: 'production' },
    { value: 'staging', label: 'staging' },
    { value: 'shadow', label: 'shadow' },
    { value: 'archived', label: 'archived' },
    { value: 'unregistered', label: t('umt_status_unregistered') },
    { value: 'missing', label: t('umt_status_missing') },
  ];

  // §6.6 过滤联动:筛选变化页码归 1,并收起行内展开(筛选后旧行不保证还在当前页)
  useEffect(() => {
    setCurrent(1);
    setExpandedKey('');
  }, [keyword, algoFilter, stageFilter]);

  // 翻页/改档位同样收起展开,避免翻页后残留上一页的空展开行
  useEffect(() => {
    setExpandedKey('');
  }, [current, pageSize]);

  // Esc 收起当前展开行(键盘可达:行内 Enter/Space 切换,见 onRow)
  useEffect(() => {
    if (!expandedKey) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) setExpandedKey('');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expandedKey]);

  // refreshKey 变化后数据可能变短,防止 pageNum 越界空页
  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (current > totalPages) setCurrent(totalPages);
  }, [filtered, pageSize, current]);

  const handlePromote = async (modelId: string) => {
    try {
      await modelApi.promoteModel(modelId);
      message.success(t('umt_msg_promote_ok'));
      loadRows();
    } catch (err) {
      message.error(t('umt_msg_promote_failed', { err: err instanceof Error ? err.message : String(err) }));
    }
  };

  const handleUnpromote = async (modelId: string) => {
    try {
      await modelApi.unpromoteModel(modelId);
      message.success(t('umt_msg_unpromote_ok'));
      loadRows();
    } catch (err) {
      message.error(t('umt_msg_unpromote_failed', { err: err instanceof Error ? err.message : String(err) }));
    }
  };

  const doDelete = async (row: UnifiedModelRow) => {
    const stem = row.file_name.replace(/\.zip$/, '');
    try {
      await rlApi.deleteModel(stem);
      message.success(t('umt_msg_deleted'));
      setSelectedKey((prev) => (prev === row.file_name ? '' : prev));
      loadRows();
    } catch (err) {
      message.error(t('umt_msg_delete_failed', { err: err instanceof Error ? err.message : String(err) }));
    }
  };

  // 动作集合:表格操作列(图标钮)与卡片底部(文字钮)共用;删除在调用侧包 Popconfirm
  const actionsFor = (record: UnifiedModelRow) => {
    const acts: { key: string; icon: ReactNode; label: string; danger?: boolean; onClick: () => void }[] = [
      { key: 'view', icon: <EyeOutlined />, label: t('umt_action_detail'), onClick: () => setDetailRow(record) },
    ];
    // 文件缺失条目仅可看详情(注册表条目的 delete/生命周期操作不可用)
    if (statusOf(record) === 'missing') return acts;
    if (!record.registered) {
      acts.push({ key: 'register', icon: <TagOutlined />, label: t('umt_action_register'), onClick: () => setRegisterRow(record) });
    }
    if (record.registered && record.stage !== 'production') {
      acts.push({
        key: 'promote',
        icon: <RocketOutlined />,
        label: t('umt_action_promote'),
        onClick: () => record.model_id && handlePromote(record.model_id),
      });
    }
    if (record.registered && record.stage === 'production') {
      acts.push({
        key: 'download',
        icon: <DownloadOutlined />,
        label: t('umt_action_download'),
        // 下载不经 axios:后端该端点刻意不带 Authorization(见 model_routes.download),location 跳转直接触发下载
        onClick: () => {
          window.location.href = `/api/v1/models/${encodeURIComponent(record.model_id ?? '')}/download`;
        },
      });
      acts.push({
        key: 'unpromote',
        icon: <RollbackOutlined />,
        label: t('umt_action_unpromote'),
        onClick: () => {
          if (!record.model_id) return;
          modal.confirm({
            title: t('umt_action_unpromote'),
            content: t('umt_unpromote_confirm'),
            okText: t('umt_action_ok'),
            cancelText: t('umt_action_cancel'),
            onOk: () => handleUnpromote(record.model_id!),
          });
        },
      });
    }
    acts.push({
      key: 'delete',
      icon: <DeleteOutlined />,
      label: t('umt_action_delete'),
      danger: true,
      onClick: () => doDelete(record),
    });
    return acts;
  };

  // 操作列：24px 图标钮 + Tooltip；删除 Popconfirm（历史雷区：删除不可逆必须确认）
  const renderIconActions = (record: UnifiedModelRow) => {
    const acts = actionsFor(record);
    return (
      <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
        {acts.map((a) =>
          a.key === 'delete' ? (
            <Popconfirm
              key={a.key}
              title={t('umt_delete_title')}
              description={t('umt_delete_confirm', { name: record.file_name })}
              okText={t('umt_action_delete')}
              cancelText={t('umt_action_cancel')}
              okButtonProps={{ danger: true }}
              onConfirm={() => doDelete(record)}
            >
              <Tooltip title={a.label}>
                <button type="button" className="qc-mini-btn qc-icon-only danger" aria-label={a.label}>
                  {a.icon}
                </button>
              </Tooltip>
            </Popconfirm>
          ) : (
            <Tooltip key={a.key} title={a.label}>
              <button type="button" className="qc-mini-btn qc-icon-only" aria-label={a.label} onClick={a.onClick}>
                {a.icon}
              </button>
            </Tooltip>
          ),
        )}
      </div>
    );
  };

  // 卡片底部文字钮组（删除走卡片右上角，不重复展示）
  const renderCardActions = (record: UnifiedModelRow) => (
    <Space size={4} onClick={(e) => e.stopPropagation()} wrap>
      {actionsFor(record)
        .filter((a) => a.key !== 'delete')
        .map((a) => (
          <Button key={a.key} size="small" onClick={a.onClick}>
            {a.label}
          </Button>
        ))}
    </Space>
  );

  // 行内展开面板:轻摘要(只读 UnifiedModelRow 真字段,缺字段整格省略);完整详情仍走 Drawer
  const renderExpanded = (record: UnifiedModelRow) => {
    const algo = algoLabel(record);
    const sharpe = oosSharpe(record);
    return (
      <div className="qc-exp-panel">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px 18px' }}>
          {record.model_id ? <ExpCell label={t('umt_exp_model_id')} value={record.model_id} /> : null}
          <ExpCell label={t('mdd_label_file_name')} value={record.file_name} />
          {algo ? <ExpCell label={t('mdd_label_algo')} value={algo} /> : null}
          {record.version ? <ExpCell label={t('mdd_field_version')} value={record.version} /> : null}
          <ExpCell label={t('umt_col_status')} value={<StatusChip row={record} />} />
          {sharpe.text === '—' ? (
            <ExpCell label={t('umt_exp_oos_sharpe')} value={<span className="qc-cell-none">—</span>} />
          ) : (
            <ExpCell label={t('umt_exp_oos_sharpe')} value={<span className={sharpe.tone.trim()}>{sharpe.text}</span>} />
          )}
          {record.created ? (
            <ExpCell label={t('mdd_label_created')} value={dayjs(record.created * 1000).format('YYYY-MM-DD HH:mm')} />
          ) : null}
          {record.size_mb != null ? <ExpCell label={t('mdd_label_size')} value={`${record.size_mb} MB`} /> : null}
          {record.path ? <ExpCell label={t('mdd_label_path')} value={record.path} /> : null}
        </div>
        {/* demo 动作行 margin-top:11px */}
        <div style={{ marginTop: 11, display: 'flex', justifyContent: 'flex-end' }}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailRow(record)}>
            {t('umt_exp_open_detail')}
          </Button>
        </div>
      </div>
    );
  };

  // 数值/时间为 §3 排印：右对齐 mono、空值弱化、时间 MM-DD HH:mm
  const columns: TableProps<UnifiedModelRow>['columns'] = [
    {
      title: t('umt_col_model'),
      dataIndex: 'file_name',
      key: 'file_name',
      ellipsis: { showTitle: false },
      width: 300,
      render: (text: string, record: UnifiedModelRow) => {
        const algo = algoLabel(record);
        const tip = record.model_id ? `${text}（${record.model_id}）` : text;
        const open = expandedKey === record.file_name;
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', maxWidth: '100%', overflow: 'hidden' }}>
            {/* 三角自绘在模型列(showExpandColumn:false);行点击展开,此图标随选中/展开态旋转 */}
            <span className={`qc-cell-caret${open ? ' is-open' : ''}`} aria-hidden>
              <svg viewBox="0 0 12 12" width="12" height="12" fill="none">
                <path d="M4.5 2.5 8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <Tooltip title={tip} placement="topLeft">
              <span className="qc-cell-strat-wrap">
                {algo && <span className="qc-chip quiet qc-mono">{algo}</span>}
                <span className="qc-cell-strat" style={{ maxWidth: 200 }}>
                  {record.model_id ?? text}
                </span>
              </span>
            </Tooltip>
          </span>
        );
      },
    },
    { title: t('umt_col_status'), key: 'status', width: 104, render: (_, record) => <StatusChip row={record} /> },
    {
      title: 'Sharpe',
      key: 'sharpe',
      width: 84,
      align: 'right',
      render: (_, record) => {
        const v = record.metrics?.sharpe_ratio ?? record.metrics?.sharpe;
        if (v == null) return <span className="qc-mono qc-cell-none">—</span>;
        return <span className={`qc-mono${sharpeToneClass(record)}`}>{Number(v).toFixed(2)}</span>;
      },
    },
    {
      title: t('umt_col_created'),
      dataIndex: 'created',
      key: 'created',
      width: 120,
      render: (ts: number | null) => {
        if (!ts) return <span className="qc-cell-time qc-mono">—</span>;
        const full = dayjs(ts * 1000).format('YYYY-MM-DD HH:mm:ss');
        return (
          <Tooltip title={full}>
            <span className="qc-cell-time qc-mono">{dayjs(ts * 1000).format('MM-DD HH:mm')}</span>
          </Tooltip>
        );
      },
    },
    {
      title: t('umt_col_size'),
      dataIndex: 'size_mb',
      key: 'size_mb',
      width: 90,
      align: 'right',
      render: (v: number | null) => (v == null ? <span className="qc-mono qc-cell-none">—</span> : <span className="qc-mono">{v} MB</span>),
    },
    // 固定列:容器横向滚动时操作始终可见
    { title: t('umt_col_actions'), key: 'actions', width: 130, fixed: 'right', render: (_, record) => renderIconActions(record) },
  ];

  // 工具栏计数「显示 x-y / 共 z」：按当前页与页大小折算，空数据归 0
  const shownRange = () => {
    const start = filtered.length === 0 ? 0 : (current - 1) * pageSize + 1;
    const end = Math.min(current * pageSize, filtered.length);
    return t('shown_range', { start, end, total: filtered.length });
  };

  const selectedRow = rows.find((r) => r.file_name === selectedKey && r.size_mb != null);

  // 列表视图当前页由 DataTable 本地切片
  const paginationProps = {
    current,
    pageSize,
    onChange: (page: number, size: number) => {
      // 条数变化写回全局配置(与列表页既有口径一致)
      if (size !== pageSize) setPageSize(size);
      setCurrent(page);
    },
  };

  return (
    <>
      <PageToolbar
        search={{
          value: keyword,
          onChange: (v) => setKeyword(v),
          placeholder: t('umt_search_ph'),
          ariaLabel: t('umt_search_ph'),
        }}
        filters={
          <>
            <div role="group" aria-label={t('umt_filter_status')} style={{ display: 'contents' }}>
              {stageChips.map((chip) => (
                <button
                  key={chip.value}
                  type="button"
                  className={`qc-ichip${stageFilter === chip.value ? ' qc-ichip-on' : ''}`}
                  onClick={() => setStageFilter(chip.value)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
            <Select
              allowClear
              aria-label={t('umt_filter_algo')}
              placeholder={t('umt_filter_algo')}
              value={algoFilter}
              onChange={(v) => setAlgoFilter(v)}
              options={algoOptions}
              style={{ width: 130 }}
            />
          </>
        }
        count={shownRange()}
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={loadRows} aria-label={t('umt_action_refresh')} title={t('umt_action_refresh')} />
            {selectedRow && (
              <Button
                type="primary"
                icon={<BarChartOutlined />}
                onClick={() => setBacktestRow(selectedRow)}
              >
                {t('umt_btn_backtest_selected')}
              </Button>
            )}
          </>
        }
      />

      {view === 'card' ? (
        <>
          {filtered.length === 0 && !loading && (
            <Card size="small" className="qc-card">
              <QcEmpty
                title={hasFilters ? t('no_data') : t('no_models')}
                description={hasFilters ? t('bt_no_match_desc') : undefined}
              />
            </Card>
          )}
          {/* 卡片与列表是同一份数据的两种排版,点开必须是同一块面板 */}
          {/* 沿用 ExpandableCardGrid(面板插在被点卡片所在视觉行之后、跨全宽),内容走与列表 expandedRowRender 相同的 renderExpanded */}
          <ExpandableCardGrid
            items={filtered.slice((current - 1) * pageSize, current * pageSize)}
            getKey={(record) => record.file_name}
            expandedKey={expandedKey || null}
            gutter={[12, 12]}
            renderExpanded={renderExpanded}
            renderCard={(record) => {
              const algo = algoLabel(record);
              const isSelected = selectedKey === record.file_name;
              const nameTooltip = record.model_id ? `${record.file_name}（${record.model_id}）` : record.file_name;
              return (
                  <Card
                    size="small"
                    hoverable
                    className={`qc-card${isSelected ? ' qc-card-selected' : ''}`}
                    style={{ cursor: 'pointer', height: '100%' }}
                    onClick={() => {
                      // 对齐表格禁选口径:文件缺失(无文件)不可选中
                      if (record.size_mb == null) return;
                      // 选中 + 就地展开/收起,与列表行「点行 = 选中 + 展开」同语义
                      setSelectedKey((prev) => (prev === record.file_name ? '' : record.file_name));
                      setExpandedKey((prev) => (prev === record.file_name ? '' : record.file_name));
                    }}
                    title={
                      <span className="qc-mono font-medium truncate" style={{ maxWidth: '70%' }} title={nameTooltip}>
                        {record.model_id ?? record.file_name}
                      </span>
                    }
                    extra={
                      statusOf(record) !== 'missing' && (
                        <Popconfirm
                          title={t('umt_delete_title')}
                          description={t('umt_delete_confirm', { name: record.file_name })}
                          okText={t('umt_action_delete')}
                          cancelText={t('umt_action_cancel')}
                          okButtonProps={{ danger: true }}
                          onConfirm={() => doDelete(record)}
                        >
                          <Tooltip title={t('umt_action_delete')}>
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              // 删除统一放卡片右上角;点击不可穿透到卡片选中
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Tooltip>
                        </Popconfirm>
                      )
                    }
                  >
                    <div className="flex flex-col gap-2" style={{ color: 'var(--qc-text-secondary)' }}>
                      <Space size={6} wrap>
                        {algo ? <span className="qc-chip quiet qc-mono">{algo}</span> : null}
                        {/* 状态从右上角挪到标签行,右上角让位给删除按钮 */}
                        <StatusChip row={record} />
                      </Space>
                      <MetaRow
                        label="Sharpe"
                        value={<span className={`qc-mono${sharpeToneClass(record)}`}>{sharpeText(record)}</span>}
                      />
                      <MetaRow
                        label={t('umt_col_created')}
                        value={
                          <span className="qc-cell-time qc-mono">
                            {record.created ? dayjs(record.created * 1000).format('YYYY-MM-DD HH:mm') : '—'}
                          </span>
                        }
                      />
                      <MetaRow
                        label={t('umt_col_size')}
                        value={<span className="qc-mono">{record.size_mb == null ? '—' : `${record.size_mb} MB`}</span>}
                      />
                      {/* 操作区 renderCardActions 内部已阻止冒泡 */}
                      <div className="pt-2" style={{ borderTop: '1px solid var(--qc-border)' }}>{renderCardActions(record)}</div>
                    </div>
                  </Card>
              );
            }}
          />
          {filtered.length > 0 && (
            <Row justify="center" style={{ marginTop: 16 }}>
              <Pagination
                {...paginationProps}
                total={filtered.length}
                showSizeChanger
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                showTotal={(total) => t('total_items', { total })}
              />
            </Row>
          )}
        </>
      ) : (
        <DataTable<UnifiedModelRow>
          rowKey="file_name"
          columns={columns}
          dataSource={filtered}
          loading={loading}
          /* 列均有显式宽总和 ≈830:容器不足时表格内部横滚且操作列冻结 */
          scroll={{ x: 830 }}
          rowClassName={(record) => (record.file_name === selectedKey ? 'qc-row-selected' : '')}
          /* 行内轻摘要:单行互斥、行点击展开(三角自绘在模型列)、初始不展开 */
          expandable={{
            expandedRowKeys: expandedKey ? [expandedKey] : [],
            onExpandedRowsChange: (keys) => setExpandedKey(keys.length ? String(keys[keys.length - 1]) : ''),
            expandedRowRender: renderExpanded,
            expandRowByClick: true,
            showExpandColumn: false,
          }}
          onRow={(record) => ({
            tabIndex: 0,
            // 行点击选中（primary 5% tint）；文件缺失行不可选中（与列表禁选口径一致）。
            // 展开由 antd expandRowByClick 处理，此处不再重复 toggle。
            onClick: () => {
              if (record.size_mb == null) return;
              setSelectedKey((prev) => (prev === record.file_name ? '' : record.file_name));
            },
            onKeyDown: (e) => {
              // 只响应行自身获得焦点时的按键，避免操作列按钮的回车冒泡到行
              if (e.target !== e.currentTarget) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setExpandedKey((prev) => (prev === record.file_name ? '' : record.file_name));
              } else if (e.key === 'Escape') {
                setExpandedKey('');
              }
            },
            style: { cursor: record.size_mb == null ? 'default' : 'pointer' },
          })}
          pagination={paginationProps}
          emptyTitle={hasFilters ? t('no_data') : t('no_models')}
          emptyDescription={hasFilters ? t('bt_no_match_desc') : undefined}
        />
      )}

      <RegisterModelModal
        row={registerRow}
        onClose={() => setRegisterRow(null)}
        onSuccess={() => {
          setRegisterRow(null);
          loadRows();
        }}
      />
      <ModelDetailDrawer row={detailRow} onClose={() => setDetailRow(null)} />
      <RLBacktestModal row={backtestRow} onClose={() => setBacktestRow(null)} />
    </>
  );
}
