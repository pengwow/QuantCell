/**
 * 因子库左栏：挖掘/新建入口 + 搜索筛选 + 精简目录表。
 * 数据来自容器单次 catalog() 请求，行点击只改选中态，无异步竞态。
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tag,
  theme,
  type TableColumnsType,
} from 'antd';
import { PlusOutlined, RobotOutlined, SearchOutlined } from '@ant-design/icons';
import type { FactorCatalogItem } from '@/api/factor';
import {
  CATEGORY_COLOR,
  categoryLabel,
  STATUS_COLOR,
  factorSource,
  type FactorSource,
} from './factorMeta';
import FactorFormModal from './FactorFormModal';

interface Props {
  catalog: FactorCatalogItem[];
  loading: boolean;
  loadError: boolean;
  selected: string | null;
  onSelect: (name: string) => void;
  onRefresh: () => Promise<void> | void;
  onMine: () => void;
}

const FactorLibraryPane: React.FC<Props> = ({
  catalog,
  loading,
  loadError,
  selected,
  onSelect,
  onRefresh,
  onMine,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | FactorSource>('all');
  const [createOpen, setCreateOpen] = useState(false);

  const statusLabel = (s: FactorCatalogItem['lifecycle_status']) =>
    t(`factor_status_${s.toLowerCase()}`) || s;

  const sourceLabel = (src: FactorSource) => t(`factor_lib_source_${src}`) || src;

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
      width: 72,
      render: (_, r) => <Tag>{sourceLabel(factorSource(r))}</Tag>,
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
      width: 56,
      align: 'right',
    },
  ];

  return (
    <Card
      size="small"
      title={t('factor_lib_card_title') || '因子库'}
      extra={
        <Space size="small">
          <Button size="small" icon={<RobotOutlined />} onClick={onMine}>
            {t('factor_lib_mine_btn') || 'LLM 挖掘'}
          </Button>
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('factor_lib_create_btn') || '新建因子'}
          </Button>
        </Space>
      }
      styles={{ body: { padding: 12 } }}
    >
      <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
        <Space size="small" wrap>
          <Input
            allowClear
            size="small"
            prefix={<SearchOutlined />}
            style={{ width: 150 }}
            placeholder={t('factor_lib_search_ph') || '搜索因子名 / 名称'}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Select
            size="small"
            style={{ width: 120 }}
            value={categoryFilter}
            onChange={setCategoryFilter}
            options={[
              { value: 'all', label: t('factor_lib_filter_category') || '全部分类' },
              ...categoryOptions.map((c) => ({ value: c, label: categoryLabel(c, t) })),
            ]}
          />
          <Select
            size="small"
            style={{ width: 110 }}
            value={sourceFilter}
            onChange={(v) => setSourceFilter(v)}
            options={[
              { value: 'all', label: t('factor_lib_filter_source') || '全部来源' },
              { value: 'builtin', label: t('factor_lib_source_builtin') || '内置' },
              { value: 'expression', label: t('factor_lib_source_expression') || '表达式' },
              { value: 'code', label: t('factor_lib_source_code') || '代码' },
              { value: 'composite', label: t('factor_lib_source_composite') || '合成' },
            ]}
          />
        </Space>

        {loadError ? (
          <Alert
            type="error"
            showIcon
            message={t('factor_lib_load_failed') || '因子库加载失败'}
            action={
              <Button size="small" onClick={() => void onRefresh()}>
                {t('factor_lib_retry') || '重试'}
              </Button>
            }
          />
        ) : (
          <Table
            rowKey="name"
            size="small"
            loading={loading}
            dataSource={filtered}
            columns={columns}
            pagination={false}
            // 列总宽 460：窄窗口下退化为横向滚动，绝不再把首列压成竖排
            scroll={{ x: 460, y: 'calc(100vh - 280px)' }}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('factor_lib_empty') || '暂无因子'} />,
            }}
            onRow={(r) => ({
              onClick: () => onSelect(r.name),
              style: {
                cursor: 'pointer',
                background: r.name === selected ? token.colorPrimaryBg : undefined,
              },
            })}
          />
        )}
      </Space>

      <FactorFormModal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onSaved={handleCreated}
      />
    </Card>
  );
};

export default FactorLibraryPane;
