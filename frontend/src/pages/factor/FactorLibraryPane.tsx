/**
 * 因子库：工具栏（搜索/筛选 + 列表/卡片视图切换）+ 目录展示。
 * 布局对齐策略管理等页面：第一行 搜索(左)+视图切换(右)，第二行 筛选(左)+操作(右)；
 * 列表=带分页表格，卡片=Card 网格 + Pagination。数据来自容器单次 catalog() 请求，
 * 「查看详情」按钮（列表操作列/卡片底部）是打开抽屉的唯一入口，无异步竞态。
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
  Empty,
  Flex,
  Input,
  Pagination,
  Row,
  Select,
  Space,
  Table,
  Tag,
  theme,
  Tooltip,
  type TableColumnsType,
  type TablePaginationConfig,
} from 'antd';
import {
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { factorApi, type FactorCatalogItem } from '@/api/factor';
import {
  CATEGORY_COLOR,
  categoryLabel,
  STATUS_COLOR,
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
import FactorFormModal from './FactorFormModal';

interface Props {
  catalog: FactorCatalogItem[];
  loading: boolean;
  loadError: boolean;
  selected: string | null;
  onSelect: (name: string) => void;
  onRefresh: () => Promise<void> | void;
}

const FactorLibraryPane: React.FC<Props> = ({
  catalog,
  loading,
  loadError,
  selected,
  onSelect,
  onRefresh,
}) => {
  const { t } = useTranslation();
  const { message, modal } = AntdApp.useApp();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const qc = useQuantColors();
  // 视图类型：跟随系统设置「默认展示类型」，页面不提供切换
  const viewType = useViewType();
  // 分页大小来自全局配置（条数切换器即全站开关）
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | FactorSource>('all');
  const [createOpen, setCreateOpen] = useState(false);
  // 列表/卡片共用一份分页状态（与策略管理一致）；pageSize 来自全局配置（条数切换器即全站开关）
  const [pagination, setPagination] = useState<TablePaginationConfig>(() => ({
    current: 1,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (total) => `${t('total_items', { total })}`,
  }));

  // 全局条数变化（设置页/其他页面改动）实时同步到本页分页状态
  useEffect(() => {
    setPagination((p) => ({ ...p, pageSize }));
  }, [pageSize]);

  const statusLabel = (s: FactorCatalogItem['lifecycle_status']) =>
    t(`factor_status_${s.toLowerCase()}`) || s;

  const sourceLabel = (src: FactorSource) => t(`factor_lib_source_${src}`) || src;

  // 筛选条件变化时回到第一页（避免过滤后停留在超出范围的页码）
  const gotoPage1 = () => setPagination((p) => ({ ...p, current: 1 }));

  const categoryOptions = useMemo(
    () => Array.from(new Set(catalog.map((f) => f.category))).sort(),
    [catalog],
  );

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return catalog.filter((f) => {
      if (categoryFilter !== 'all' && f.category !== categoryFilter) return false;
      if (sourceFilter !== 'all' && factorSource(f) !== sourceFilter) return false;
      if (kw && !(`${f.label} ${f.name}`.toLowerCase().includes(kw))) return false;
      return true;
    });
  }, [catalog, keyword, categoryFilter, sourceFilter]);

  const openCreate = () => setCreateOpen(true);

  // 新建成功后：关弹窗、刷新目录、选中新因子（表单与保存逻辑在 FactorFormModal 内）
  const handleCreated = async (name: string) => {
    setCreateOpen(false);
    await onRefresh();
    onSelect(name);
  };

  const columns: TableColumnsType<FactorCatalogItem> = [
    {
      title: t('factor_lib_col_factor') || '因子',
      dataIndex: 'label',
      width: 160,
      render: (_, r) => (
        // 窄目录列：中文标签/英文标识上下双行，各自单行省略（悬浮看全文）；
        // 内置/代码/合成不在这里打 Tag——「来源」列已表达，避免挤宽重叠
        <div style={{ minWidth: 0 }}>
          <div
            title={r.label}
            style={{
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <span
              style={{
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {r.label}
            </span>
            {!r.supported && (
              <Tag color="error" style={{ marginInlineEnd: 0, flexShrink: 0 }}>
                {t('factor_lib_no_data') || '无数据'}
              </Tag>
            )}
          </div>
          <div
            title={r.name}
            style={{
              color: token.colorTextSecondary,
              fontSize: 12,
              lineHeight: 1.5,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {r.name}
          </div>
        </div>
      ),
    },
    {
      title: t('factor_lib_col_category') || '分类',
      dataIndex: 'category',
      width: 92,
      render: (c: string) => <Tag color={CATEGORY_COLOR[c] ?? 'default'}>{categoryLabel(c, t)}</Tag>,
    },
    {
      title: t('factor_detail_meta_source') || '来源',
      width: 100,
      render: (_, r) => (
        <>
          <Tag>{sourceLabel(factorSource(r))}</Tag>
          {isAiProduced(r) && (
            <Tag color="geekblue" style={{ marginInlineStart: 4 }}>
              AI
            </Tag>
          )}
        </>
      ),
    },
    {
      title: t('factor_stat_ic_mean') || 'IC 均值',
      width: 80,
      align: 'right',
      render: (_, r) => {
        const lm = r.last_metrics;
        if (!lm) return <span style={{ color: token.colorTextTertiary }}>—</span>;
        const v = lm.ic_mean ?? 0;
        return (
          <span style={{ color: toneColor(toneOf('ic_mean', v), qc), fontWeight: 500 }}>
            {v.toFixed(4)}
          </span>
        );
      },
    },
    {
      title: t('factor_stat_icir') || 'ICIR',
      width: 72,
      align: 'right',
      render: (_, r) => {
        const lm = r.last_metrics;
        if (!lm) return <span style={{ color: token.colorTextTertiary }}>—</span>;
        const v = lm.ic_ir ?? 0;
        return (
          <span style={{ color: toneColor(toneOf('ic_ir', v), qc), fontWeight: 500 }}>
            {v.toFixed(4)}
          </span>
        );
      },
    },
    {
      title: t('factor_lib_col_status') || '状态',
      dataIndex: 'lifecycle_status',
      width: 80,
      render: (s: FactorCatalogItem['lifecycle_status']) => (
        <Tag color={STATUS_COLOR[s]}>{statusLabel(s)}</Tag>
      ),
    },
    {
      title: t('factor_lib_col_snapshots') || '快照数',
      dataIndex: 'snapshot_count',
      width: 64,
      align: 'right',
    },
    {
      title: t('factor_detail_meta_last_snapshot') || '最近快照',
      width: 130,
      dataIndex: 'last_snapshot_at',
      render: (v: string | null) => (
        v
          ? v.replace('T', ' ').slice(0, 16)
          : <span style={{ color: token.colorTextTertiary }}>—</span>
      ),
    },
    {
      title: t('factor_lib_col_action') || '操作',
      width: 104,
      // 与策略管理等页面操作列统一：图标按钮 + Tooltip 悬浮文案，固定在表格右侧
      fixed: 'right',
      render: (_, r) => (
        <Space size={0}>
          {/* 与卡片视图的「查看详情」同语义：唯一的打开抽屉入口 */}
          <Tooltip title={t('view_details') || '查看详情'}>
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onSelect(r.name)}
            />
          </Tooltip>
          {/* 内置因子受后端保护不可删；删除会同步清理因子档案，本地实现一并移除 */}
          <Tooltip
            title={
              r.builtin
                ? t('factor_lib_delete_builtin_disabled') || '内置因子不可删除'
                : t('delete') || '删除'
            }
          >
            <Button
              type="text"
              size="small"
              danger
              disabled={r.builtin}
              icon={<DeleteOutlined />}
              onClick={() => confirmDeleteFactor(r)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 工具栏：与策略管理一致的「搜索+视图切换 / 筛选+操作」两行布局
  const renderToolbar = () => (
    <Space orientation="vertical" size="middle" style={{ display: 'flex', marginBottom: 8 }}>
      <Flex justify="space-between" align="center" gap="small" wrap="wrap">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          style={{ width: 260, maxWidth: '100%' }}
          placeholder={t('factor_lib_search_ph') || '搜索因子名 / 名称'}
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value);
            gotoPage1();
          }}
        />
      </Flex>
      <Flex justify="space-between" align="center" gap="small" wrap="wrap">
        <Space size="small" wrap>
          <Select
            style={{ width: 140 }}
            value={categoryFilter}
            onChange={(v) => {
              setCategoryFilter(v);
              gotoPage1();
            }}
            options={[
              { value: 'all', label: t('factor_lib_filter_category') || '全部分类' },
              ...categoryOptions.map((c) => ({ value: c, label: categoryLabel(c, t) })),
            ]}
          />
          <Select
            style={{ width: 120 }}
            value={sourceFilter}
            onChange={(v) => {
              setSourceFilter(v);
              gotoPage1();
            }}
            options={[
              { value: 'all', label: t('factor_lib_filter_source') || '全部来源' },
              { value: 'builtin', label: t('factor_lib_source_builtin') || '内置' },
              { value: 'expression', label: t('factor_lib_source_expression') || '表达式' },
              { value: 'code', label: t('factor_lib_source_code') || '代码' },
              { value: 'composite', label: t('factor_lib_source_composite') || '合成' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void onRefresh()}>
            {t('refresh') || '刷新'}
          </Button>
        </Space>
        <Space size="small" wrap>
          {/* 旧 LLM 挖掘已退役：AI 因子挖掘统一走研究模块 */}
          <Button icon={<RobotOutlined />} onClick={() => navigate('/research')}>
            {t('ai_research')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('factor_lib_create_btn') || '新建因子'}
          </Button>
        </Space>
      </Flex>
    </Space>
  );

  // 指标行：左标签右数值，数值按语义评级着色（与表格列同口径）
  const metricRow = (label: string, v: number | null, key: string) => (
    <Flex justify="space-between" align="center">
      <span style={{ color: token.colorTextSecondary }}>{label}</span>
      {v === null || v === undefined ? (
        <span style={{ color: token.colorTextTertiary }}>—</span>
      ) : (
        <span style={{ color: toneColor(toneOf(key, v), qc), fontWeight: 500 }}>
          {v.toFixed(4)}
        </span>
      )}
    </Flex>
  );

  // 删除确认弹窗：表格操作列与卡片右上角 extra 共用
  const confirmDeleteFactor = (r: FactorCatalogItem) => {
    modal.confirm({
      title: t('factor_lib_delete_confirm_title') || '删除因子',
      content: `${t('factor_lib_delete_confirm_text') || '将删除该因子及其本地实现，因子档案同步清理'}：${r.label}（${r.name}）`,
      okText: t('delete') || '删除',
      okButtonProps: { danger: true },
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          await factorApi.remove(r.name);
          message.success(t('factor_lib_msg_deleted') || `已删除因子 ${r.name}`);
          // 目录刷新后父容器会自动纠正 selected（选中的因子被删时回退）
          await onRefresh();
        } catch (err) {
          message.error(err instanceof Error ? err.message : String(err));
        }
      },
    });
  };

  const renderCardView = () => {
    // pageSize 直接用外层全局 hook 值（与列表视图同源），不再声明同名局部变量遮蔽
    const current = (pagination.current as number) || 1;
    const pageData = filtered.slice((current - 1) * pageSize, current * pageSize);

    if (!pageData.length) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('factor_lib_empty') || '暂无因子'}
          style={{ padding: '48px 0' }}
        />
      );
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
                  style={{
                    // 选中因子高亮边框（详情抽屉对应项），与列表行选中背景同语义；
                    // 整卡不可点击，打开抽屉只走「查看详情」按钮
                    borderColor: f.name === selected ? token.colorPrimary : undefined,
                  }}
                  title={
                    <span
                      title={f.label}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        maxWidth: '100%',
                      }}
                    >
                      <span
                        style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      >
                        {f.label}
                      </span>
                      {!f.supported && (
                        <Tag color="error" style={{ marginInlineEnd: 0, flexShrink: 0 }}>
                          {t('factor_lib_no_data') || '无数据'}
                        </Tag>
                      )}
                    </span>
                  }
                  extra={
                    // 删除统一放卡片右上角（与列表视图操作列同口径）：内置因子受保护置灰
                    <Tooltip
                      title={
                        f.builtin
                          ? t('factor_lib_delete_builtin_disabled') || '内置因子不可删除'
                          : t('delete') || '删除'
                      }
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        disabled={f.builtin}
                        icon={<DeleteOutlined />}
                        onClick={() => confirmDeleteFactor(f)}
                      />
                    </Tooltip>
                  }
                >
                  <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
                    <div
                      title={f.name}
                      style={{
                        color: token.colorTextSecondary,
                        fontSize: 12,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {f.name}
                    </div>
                    <Space size={4} wrap style={{ rowGap: 4 }}>
                      <Tag color={CATEGORY_COLOR[f.category] ?? 'default'} style={{ marginInlineEnd: 0 }}>
                        {categoryLabel(f.category, t)}
                      </Tag>
                      <Tag style={{ marginInlineEnd: 0 }}>{sourceLabel(factorSource(f))}</Tag>
                      {isAiProduced(f) && (
                        <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>
                          AI
                        </Tag>
                      )}
                      <Tag color={STATUS_COLOR[f.lifecycle_status]} style={{ marginInlineEnd: 0 }}>
                        {statusLabel(f.lifecycle_status)}
                      </Tag>
                    </Space>
                    <div style={{ borderTop: `1px solid ${token.colorBorderSecondary}` }} />
                    {metricRow(t('factor_stat_ic_mean') || 'IC 均值', lm?.ic_mean ?? null, 'ic_mean')}
                    {metricRow(t('factor_stat_icir') || 'ICIR', lm?.ic_ir ?? null, 'ic_ir')}
                    <Flex justify="space-between" align="center">
                      <span style={{ color: token.colorTextSecondary }}>
                        {t('factor_lib_col_snapshots') || '快照数'}
                      </span>
                      <span>{f.snapshot_count}</span>
                    </Flex>
                    <Flex justify="space-between" align="center">
                      <span style={{ color: token.colorTextSecondary }}>
                        {t('factor_detail_meta_last_snapshot') || '最近快照'}
                      </span>
                      <span style={{ fontSize: 12 }}>
                        {f.last_snapshot_at
                          ? f.last_snapshot_at.replace('T', ' ').slice(0, 16)
                          : <span style={{ color: token.colorTextTertiary }}>—</span>}
                      </span>
                    </Flex>
                    <Button
                      type="primary"
                      size="small"
                      block
                      onClick={() => onSelect(f.name)}
                    >
                      {t('view_details') || '查看详情'}
                    </Button>
                  </Space>
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
            showTotal={(total) => `${t('total_items', { total })}`}
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
    <Table
      rowKey="name"
      size="small"
      loading={loading}
      dataSource={filtered}
      columns={columns}
      // 分页由共享 pagination 状态控制，卡片视图复用同一份页码
      pagination={pagination}
      // 9 列总宽 ~840：窄窗口下横向滚动，绝不再把首列压成竖排
      scroll={{ x: 840 }}
      locale={{
        emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('factor_lib_empty') || '暂无因子'} />,
      }}
      // 行不可点击，选中背景只作为「抽屉打开项」的高亮；打开抽屉走操作列按钮
      onRow={(r) => ({
        style: {
          background: r.name === selected ? token.colorPrimaryBg : undefined,
        },
      })}
      onChange={(next) => {
        // 条数变化写回全局配置，全站生效
        if (next.pageSize && next.pageSize !== pageSize) setPageSize(next.pageSize);
        setPagination(next);
      }}
    />
  );

  return (
    <>
      {renderToolbar()}
      {loadError ? (
        <Alert
          type="error"
          showIcon
          title={t('factor_lib_load_failed') || '因子库加载失败'}
          action={
            <Button size="small" onClick={() => void onRefresh()}>
              {t('factor_lib_retry') || '重试'}
            </Button>
          }
        />
      ) : (
        viewType === 'list' ? renderListView() : renderCardView()
      )}

      <FactorFormModal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onSaved={handleCreated}
      />
    </>
  );
};

export default FactorLibraryPane;
