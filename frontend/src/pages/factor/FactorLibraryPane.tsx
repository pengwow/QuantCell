/**
 * 因子库：§6.6 工具栏（搜索 + 状态 ichips + 分类/来源下拉 + 计数 + 刷新/策略研究）
 * + 目录展示（列表=DataTable 分页表格 / 卡片=Card 网格）。
 * 「新建因子」入口在页头（demo page-actions），弹窗仍由本组件渲染，保存逻辑不变。
 * 数据来自容器单次 catalog() 请求，搜索/筛选/分页全在前端对全量数组做；
 * 「查看详情」（列表操作列/卡片底部）是打开抽屉的唯一入口，无异步竞态。
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Col,
  Flex,
  Pagination,
  Popconfirm,
  Row,
  Select,
  Tooltip,
  type TableColumnsType,
  type TablePaginationConfig,
} from 'antd';
import {
  DeleteOutlined,
  EyeOutlined,
  ReloadOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { factorApi, type FactorCatalogItem } from '@/api/factor';
import {
  categoryLabel,
  factorSource,
  isAiProduced,
  toneColor,
  toneOf,
  type FactorSource,
} from './factorMeta';
import { useQuantColors } from '@/utils/colors';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType } from '@/hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import FactorFormModal from './FactorFormModal';

interface Props {
  catalog: FactorCatalogItem[];
  loading: boolean;
  loadError: boolean;
  selected: string | null;
  onSelect: (name: string) => void;
  onRefresh: () => Promise<void> | void;
  /** 打开「新建因子」弹窗（按钮在页头 demo page-actions） */
  onCreate: () => void;
  /** 新建弹窗开/关（弹窗本体在本组件，保存后的选中逻辑在 handleCreated） */
  createVisible: boolean;
  onCloseCreate: () => void;
}

/** 状态筛选分组：LIVE=有效 / DISCOVERED·INSPECTED·PAPER_TRADING=观察 / RETIRED=失效
 *  （与容器副标 factor_sub_status 的聚合规则一致，副标来自同一 catalog 字段） */
type StatusFilter = 'all' | 'active' | 'watch' | 'retired';

const inGroup = (s: FactorCatalogItem['lifecycle_status'], g: Exclude<StatusFilter, 'all'>) =>
  g === 'active' ? s === 'LIVE' : g === 'retired' ? s === 'RETIRED' : s !== 'LIVE' && s !== 'RETIRED';

const STATUS_CHIPS: Array<{ value: StatusFilter; labelKey: string }> = [
  { value: 'all', labelKey: 'all' },
  { value: 'active', labelKey: 'factor_group_active' },
  { value: 'watch', labelKey: 'factor_group_watch' },
  { value: 'retired', labelKey: 'factor_group_retired' },
];

const FactorLibraryPane: React.FC<Props> = ({
  catalog,
  loading,
  loadError,
  selected,
  onSelect,
  onRefresh,
  onCreate,
  createVisible,
  onCloseCreate,
}) => {
  const { t } = useTranslation();
  const { message } = AntdApp.useApp();
  const navigate = useNavigate();
  const qc = useQuantColors();
  // 视图类型：跟随系统设置「默认展示类型」，页面不提供切换
  const viewType = useViewType();
  // 分页大小来自全局配置（条数切换器即全站开关）
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | FactorSource>('all');
  // 列表/卡片共用一份分页状态（与策略管理一致）
  const [pagination, setPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize,
  }));

  // 全局条数变化（设置页/其他页面改动）实时同步到本页分页状态
  useEffect(() => {
    setPagination((p) => ({ ...p, pageSize }));
  }, [pageSize]);

  const statusLabel = (s: FactorCatalogItem['lifecycle_status']) =>
    t(`factor_status_${s.toLowerCase()}`) || s;

  const sourceLabel = (src: FactorSource) => t(`factor_lib_source_${src}`) || src;

  // 状态 → §6.2 chip 语气（有效=ok / 观察=warn / 失效=down，demo 原文）
  const statusChip = (s: FactorCatalogItem['lifecycle_status']) => {
    const tone = s === 'LIVE' ? 'ok' : s === 'RETIRED' ? 'down' : 'warn';
    return <span className={`qc-chip ${tone}`}>{statusLabel(s)}</span>;
  };

  // §6.6 过滤联动：过滤条件变化后页码归 1（历史雷区：搜索不重置页码）
  const gotoPage1 = () => setPagination((p) => ({ ...p, current: 1 }));

  const categoryOptions = useMemo(
    () => Array.from(new Set(catalog.map((f) => f.category))).sort(),
    [catalog],
  );

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return catalog.filter((f) => {
      if (statusFilter !== 'all' && !inGroup(f.lifecycle_status, statusFilter)) return false;
      if (categoryFilter !== 'all' && f.category !== categoryFilter) return false;
      if (sourceFilter !== 'all' && factorSource(f) !== sourceFilter) return false;
      if (kw && !(`${f.label} ${f.name}`.toLowerCase().includes(kw))) return false;
      return true;
    });
  }, [catalog, keyword, statusFilter, categoryFilter, sourceFilter]);

  const hasFilter =
    keyword.trim() !== '' || statusFilter !== 'all' || categoryFilter !== 'all' || sourceFilter !== 'all';

  // 工具栏计数「显示 x-y / 共 z」（11px fg-4 mono，PageToolbar 内置样式）
  const current = (pagination.current as number) || 1;
  const shownRange = (start: number, end: number, total: number) =>
    t('shown_range', { start, end, total });
  const countText = shownRange(
    filtered.length === 0 ? 0 : (current - 1) * pageSize + 1,
    Math.min(current * pageSize, filtered.length),
    filtered.length,
  );

  // 新建成功后：刷新目录、选中新因子（表单与保存逻辑在 FactorFormModal 内）
  const handleCreated = async (name: string) => {
    onCloseCreate();
    await onRefresh();
    onSelect(name);
  };

  // 删除确认（Popconfirm）：表格操作列与卡片右上角 extra 共用
  const deleteConfirm = (r: FactorCatalogItem) => (
    <Popconfirm
      title={t('factor_lib_delete_confirm_title')}
      description={`${t('factor_lib_delete_confirm_text')}${r.label}（${r.name}）`}
      okText={t('delete')}
      cancelText={t('cancel')}
      okButtonProps={{ danger: true }}
      onConfirm={async () => {
        try {
          await factorApi.remove(r.name);
          message.success(t('factor_lib_msg_deleted'));
          // 目录刷新后父容器会自动纠正 selected（选中的因子被删时回退）
          await onRefresh();
        } catch (err) {
          message.error(err instanceof Error ? err.message : String(err));
        }
      }}
    >
      <Tooltip
        title={
          r.builtin
            ? t('factor_lib_delete_builtin_disabled')
            : t('delete')
        }
      >
        <button
          type="button"
          className="qc-mini-btn qc-icon-only danger"
          aria-label={r.builtin ? t('factor_lib_delete_builtin_disabled') : t('delete')}
          disabled={r.builtin}
          onClick={(e) => e.stopPropagation()}
        >
          <DeleteOutlined />
        </button>
      </Tooltip>
    </Popconfirm>
  );

  const columns: TableColumnsType<FactorCatalogItem> = [
    {
      title: t('factor_lib_col_factor'),
      dataIndex: 'label',
      width: 170,
      render: (_, r) => (
        // 窄目录列：中文展示名 / 英文标识（mono）上下双行，各自单行省略（悬浮看全文）；
        // 内置/代码/合成不在这里打 chip——「来源」列已表达，避免挤宽重叠
        <div style={{ minWidth: 0 }} title={r.name}>
          <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {r.label}
          </div>
          <div className="qc-cell-id" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {r.name}
            {!r.supported && (
              <span className="qc-chip down" style={{ marginInlineStart: 6 }}>
                {t('factor_lib_no_data')}
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      title: t('factor_lib_col_category'),
      dataIndex: 'category',
      width: 92,
      render: (c: string) => <span className="qc-chip info">{categoryLabel(c, t)}</span>,
    },
    {
      title: t('factor_detail_meta_source'),
      width: 110,
      render: (_, r) => (
        <span className="qc-row-chips">
          <span className="qc-chip quiet">{sourceLabel(factorSource(r))}</span>
          {isAiProduced(r) && <span className="qc-chip pri">AI</span>}
        </span>
      ),
    },
    {
      title: t('factor_stat_ic_mean'),
      width: 88,
      align: 'right',
      render: (_, r) => {
        const lm = r.last_metrics;
        if (!lm || lm.ic_mean == null) return <span className="qc-cell-none qc-mono">—</span>;
        const v = lm.ic_mean;
        return (
          <span className="qc-mono" style={{ color: toneColor(toneOf('ic_mean', v), qc), fontWeight: 500 }}>
            {v.toFixed(4)}
          </span>
        );
      },
    },
    {
      title: t('factor_stat_icir'),
      width: 76,
      align: 'right',
      render: (_, r) => {
        const lm = r.last_metrics;
        if (!lm || lm.ic_ir == null) return <span className="qc-cell-none qc-mono">—</span>;
        const v = lm.ic_ir;
        return (
          <span className="qc-mono" style={{ color: toneColor(toneOf('ic_ir', v), qc), fontWeight: 500 }}>
            {v.toFixed(4)}
          </span>
        );
      },
    },
    {
      title: t('factor_lib_col_status'),
      dataIndex: 'lifecycle_status',
      width: 88,
      render: (s: FactorCatalogItem['lifecycle_status']) => statusChip(s),
    },
    {
      title: t('factor_lib_col_snapshots'),
      dataIndex: 'snapshot_count',
      width: 72,
      align: 'right',
      render: (v: number) => <span className="qc-mono">{v}</span>,
    },
    {
      title: t('factor_detail_meta_last_snapshot'),
      width: 130,
      dataIndex: 'last_snapshot_at',
      render: (v: string | null) =>
        v ? (
          <span className="qc-cell-time qc-mono">{v.replace('T', ' ').slice(0, 16)}</span>
        ) : (
          <span className="qc-cell-none qc-mono">—</span>
        ),
    },
    {
      title: t('factor_lib_col_action'),
      width: 80,
      // 与策略管理等页面操作列统一：24px 图标钮 + Tooltip 悬浮文案，固定在表格右侧
      fixed: 'right',
      render: (_, r) => (
        <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
          {/* 与卡片视图的「查看详情」同语义：唯一的打开抽屉入口 */}
          <Tooltip title={t('view_details')}>
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('view_details')}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(r.name);
              }}
            >
              <EyeOutlined />
            </button>
          </Tooltip>
          {/* 内置因子受后端保护不可删；删除会同步清理因子档案，本地实现一并移除 */}
          {deleteConfirm(r)}
        </div>
      ),
    },
  ];

  // 工具栏 — §6.6：搜索 → 状态 chips + 分类/来源下拉 → 计数 → 刷新/策略研究
  const renderToolbar = () => (
    <PageToolbar
      search={{
        value: keyword,
        onChange: (value) => {
          setKeyword(value);
          gotoPage1();
        },
        placeholder: t('factor_lib_search_ph'),
        ariaLabel: t('factor_lib_search_ph'),
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
                  gotoPage1();
                }}
              >
                {t(chip.labelKey)}
              </button>
            ))}
          </div>
          <Select
            aria-label={t('factor_lib_filter_category')}
            style={{ width: 130 }}
            value={categoryFilter}
            onChange={(v) => {
              setCategoryFilter(v);
              gotoPage1();
            }}
            options={[
              { value: 'all', label: t('factor_lib_filter_category') },
              ...categoryOptions.map((c) => ({ value: c, label: categoryLabel(c, t) })),
            ]}
          />
          <Select
            aria-label={t('factor_lib_filter_source')}
            style={{ width: 118 }}
            value={sourceFilter}
            onChange={(v) => {
              setSourceFilter(v);
              gotoPage1();
            }}
            options={[
              { value: 'all', label: t('factor_lib_filter_source') },
              { value: 'builtin', label: t('factor_lib_source_builtin') },
              { value: 'expression', label: t('factor_lib_source_expression') },
              { value: 'code', label: t('factor_lib_source_code') },
              { value: 'composite', label: t('factor_lib_source_composite') },
            ]}
          />
        </>
      }
      count={countText}
      actions={
        <>
          <Button icon={<ReloadOutlined />} onClick={() => void onRefresh()}>
            {t('refresh')}
          </Button>
          {/* 旧 LLM 挖掘已退役：AI 因子挖掘统一走研究模块 */}
          <Button icon={<RobotOutlined />} onClick={() => navigate('/research')}>
            {t('ai_research')}
          </Button>
        </>
      }
    />
  );

  // 指标行：左标签右数值，数值按语义评级着色（与表格列同口径）
  const metricRow = (label: string, v: number | null, key: string) => (
    <Flex justify="space-between" align="center">
      <span style={{ color: 'var(--qc-text-secondary)' }}>{label}</span>
      {v === null || v === undefined ? (
        <span className="qc-cell-none qc-mono">—</span>
      ) : (
        <span className="qc-mono" style={{ color: toneColor(toneOf(key, v), qc), fontWeight: 500 }}>
          {v.toFixed(4)}
        </span>
      )}
    </Flex>
  );

  const emptyView = (
    <QcEmpty
      title={hasFilter ? t('factor_lib_no_match_title') : t('factor_lib_empty')}
      description={hasFilter ? t('factor_lib_no_match_desc') : undefined}
      action={
        hasFilter ? undefined : (
          <button type="button" className="qc-mini-btn pri" onClick={onCreate}>
            {t('factor_lib_create_btn')}
          </button>
        )
      }
    />
  );

  const renderCardView = () => {
    // 分页与列表视图共用同一份状态（pageSize 来自全局 hook）
    const pageData = filtered.slice((current - 1) * pageSize, current * pageSize);

    if (!pageData.length) {
      return emptyView;
    }

    return (
      <>
        <Row gutter={[16, 16]}>
          {pageData.map((f) => {
            const lm = f.last_metrics;
            return (
              <Col xs={24} sm={12} md={8} lg={6} key={f.name}>
                <Card
                  size="small"
                  style={{ boxShadow: 'var(--qc-shadow-card)' }}
                  // 选中因子高亮（详情抽屉对应项），与列表行选中背景同语义；
                  // 整卡不可点击，打开抽屉只走「查看详情」按钮
                  className={f.name === selected ? 'qc-card-selected' : ''}
                  title={
                    <span
                      title={f.label}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 5,
                        maxWidth: '100%',
                      }}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {f.label}
                      </span>
                      {!f.supported && (
                        <span className="qc-chip down" style={{ flexShrink: 0 }}>
                          {t('factor_lib_no_data')}
                        </span>
                      )}
                    </span>
                  }
                  extra={deleteConfirm(f)}
                >
                  <Flex vertical gap={8}>
                    <div className="qc-cell-id" title={f.name}
                      style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                    >
                      {f.name}
                    </div>
                    <span className="qc-row-chips">
                      <span className="qc-chip info">{categoryLabel(f.category, t)}</span>
                      <span className="qc-chip quiet">{sourceLabel(factorSource(f))}</span>
                      {isAiProduced(f) && <span className="qc-chip pri">AI</span>}
                      {statusChip(f.lifecycle_status)}
                    </span>
                    <div style={{ borderTop: '1px solid var(--qc-border)' }} />
                    {metricRow(t('factor_stat_ic_mean'), lm?.ic_mean ?? null, 'ic_mean')}
                    {metricRow(t('factor_stat_icir'), lm?.ic_ir ?? null, 'ic_ir')}
                    <Flex justify="space-between" align="center">
                      <span style={{ color: 'var(--qc-text-secondary)' }}>
                        {t('factor_lib_col_snapshots')}
                      </span>
                      <span className="qc-mono">{f.snapshot_count}</span>
                    </Flex>
                    <Flex justify="space-between" align="center">
                      <span style={{ color: 'var(--qc-text-secondary)' }}>
                        {t('factor_detail_meta_last_snapshot')}
                      </span>
                      {f.last_snapshot_at ? (
                        <span className="qc-cell-time qc-mono">
                          {f.last_snapshot_at.replace('T', ' ').slice(0, 16)}
                        </span>
                      ) : (
                        <span className="qc-cell-none qc-mono">—</span>
                      )}
                    </Flex>
                    <button
                      type="button"
                      className="qc-mini-btn pri"
                      style={{ width: '100%' }}
                      onClick={() => onSelect(f.name)}
                    >
                      {t('view_details')}
                    </button>
                  </Flex>
                </Card>
              </Col>
            );
          })}
        </Row>
        <Row justify="center" style={{ marginTop: 16 }}>
          <Pagination
            current={current}
            pageSize={pageSize}
            total={filtered.length}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => t('total_items', { total })}
            onChange={(page, size) => {
              // 条数变化写回全局配置，全站生效
              setPageSize(size);
              setPagination((p) => ({ ...p, current: page, pageSize: size }));
            }}
          />
        </Row>
      </>
    );
  };

  const renderListView = () => (
    <DataTable<FactorCatalogItem>
      columns={columns}
      loading={loading}
      dataSource={filtered}
      rowKey="name"
      // 9 列总宽 ~840：窄窗口下横向滚动，绝不再把首列压成竖排
      scroll={{ x: 840 }}
      // 选中背景只作为「抽屉打开项」的高亮；打开抽屉走操作列按钮，点行同效
      rowClassName={(r) => (r.name === selected ? 'qc-row-selected' : '')}
      onRow={(r) => ({
        onClick: () => onSelect(r.name),
        style: { cursor: 'pointer' },
      })}
      pagination={{
        current,
        pageSize,
        onChange: (pg, size) => {
          // 条数变化写回全局配置，全站生效
          if (size !== pageSize) setPageSize(size);
          setPagination((p) => ({ ...p, current: pg, pageSize: size }));
        },
      }}
      emptyTitle={hasFilter ? t('factor_lib_no_match_title') : t('factor_lib_empty')}
      emptyDescription={hasFilter ? t('factor_lib_no_match_desc') : undefined}
      emptyAction={
        hasFilter ? undefined : (
          <button type="button" className="qc-mini-btn pri" onClick={onCreate}>
            {t('factor_lib_create_btn')}
          </button>
        )
      }
    />
  );

  return (
    <>
      {renderToolbar()}
      {loadError ? (
        <Alert
          type="error"
          showIcon
          title={t('factor_lib_load_failed')}
          action={
            <Button size="small" onClick={() => void onRefresh()}>
              {t('factor_lib_retry')}
            </Button>
          }
        />
      ) : (
        viewType === 'list' ? renderListView() : renderCardView()
      )}

      <FactorFormModal
        open={createVisible}
        onCancel={onCloseCreate}
        onSaved={handleCreated}
      />
    </>
  );
};

export default FactorLibraryPane;
