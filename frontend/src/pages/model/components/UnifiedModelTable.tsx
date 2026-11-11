import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  App as AntdApp,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Input,
  Grid,
  Pagination,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { TableProps } from 'antd';
import {
  AppstoreOutlined,
  BarChartOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  ReloadOutlined,
  RocketOutlined,
  RollbackOutlined,
  SearchOutlined,
  TagOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { modelApi, type UnifiedModelRow } from '@/api/modelApi';
import { rlApi } from '@/api/rlApi';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import ModelDetailDrawer from './ModelDetailDrawer';
import RegisterModelModal from './RegisterModelModal';

const { Text } = Typography;

// 状态五态:未注册(灰)/staging(蓝)/production(绿)/archived(默认)/文件缺失(橙)
type RowStatus = 'unregistered' | 'missing' | 'staging' | 'production' | 'archived' | string;

function statusOf(row: UnifiedModelRow): RowStatus {
  if (row.registered && row.size_mb == null) return 'missing';
  if (!row.registered) return 'unregistered';
  return row.stage || 'staging';
}

function StatusTag({ row }: { row: UnifiedModelRow }) {
  const s = statusOf(row);
  if (s === 'missing') return <Tag color="orange">文件缺失</Tag>;
  if (s === 'unregistered') return <Tag>未注册</Tag>;
  if (s === 'production') return <Tag color="green">{s}</Tag>;
  if (s === 'archived') return <Tag>{s}</Tag>;
  return <Tag color="blue">{s}</Tag>;
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

// 卡片视图元信息行:label 左 value 右
function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <Flex justify="space-between" gap={8}>
      <Text type="secondary">{label}</Text>
      <Text ellipsis>{value}</Text>
    </Flex>
  );
}

export default function UnifiedModelTable({ refreshKey }: { refreshKey: number }) {
  const { message, modal } = AntdApp.useApp();
  const [rows, setRows] = useState<UnifiedModelRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [algoFilter, setAlgoFilter] = useState<string>();
  const [stageFilter, setStageFilter] = useState<string>();
  // 单选行(携带给回测占位);存 file_name 作为 rowKey
  const [selected, setSelected] = useState<string[]>([]);
  const [registerRow, setRegisterRow] = useState<UnifiedModelRow | null>(null);
  const [detailRow, setDetailRow] = useState<UnifiedModelRow | null>(null);
  // 视图切换:卡片(默认,对齐 ResearchList 网格浏览习惯)/列表
  const [view, setView] = useState<'card' | 'list'>('card');
  // pageSize 全站开关,返回值是元组(同 RLModelList 既有用法)
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [current, setCurrent] = useState(1);
  const screens = Grid.useBreakpoint();

  const loadRows = async () => {
    setLoading(true);
    try {
      const data = await modelApi.unifiedModels();
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      message.error(`加载模型总表失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
  }, [refreshKey]);

  // refreshKey 变化后数据可能变短,防止 pageNum 越界空页
  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    if (current > totalPages) setCurrent(totalPages);
  }, [rows, pageSize, current]);

  const kw = keyword.trim().toLowerCase();
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

  const stageOptions = [
    { value: 'unregistered', label: '未注册' },
    { value: 'staging', label: 'staging' },
    { value: 'production', label: 'production' },
    { value: 'archived', label: 'archived' },
    { value: 'missing', label: '文件缺失' },
  ];

  const handlePromote = async (modelId: string) => {
    try {
      await modelApi.promoteModel(modelId);
      message.success('晋升成功');
      loadRows();
    } catch (err) {
      message.error(`晋升失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleUnpromote = async (modelId: string) => {
    try {
      await modelApi.unpromoteModel(modelId);
      message.success('已取消晋升,模型回到 staging');
      loadRows();
    } catch (err) {
      message.error(`取消晋升失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleDelete = (row: UnifiedModelRow) => {
    const stem = row.file_name.replace(/\.zip$/, '');
    modal.confirm({
      title: '删除模型文件',
      content: `确定删除 "${row.file_name}" 吗？文件删除后不可恢复；已注册条目将变为「文件缺失」。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await rlApi.deleteModel(stem);
          message.success('模型文件已删除');
          setSelected((prev) => (prev.includes(row.file_name) ? prev.filter((k) => k !== row.file_name) : prev));
          loadRows();
        } catch (err) {
          message.error(`删除失败：${err instanceof Error ? err.message : String(err)}`);
        }
      },
    });
  };

  // 动作统一入口:表格操作列(iconOnly=图标+Tooltip)与卡片底部(文字按钮)共用,风格对齐 ResearchList
  const actionsFor = (record: UnifiedModelRow) => {
    const acts: { key: string; icon: ReactNode; label: string; danger?: boolean; onClick: () => void }[] = [
      { key: 'view', icon: <EyeOutlined />, label: '详情', onClick: () => setDetailRow(record) },
    ];
    // 文件缺失条目仅可看详情(注册表条目的 delete/生命周期操作不可用)
    if (statusOf(record) === 'missing') return acts;
    if (!record.registered) {
      acts.push({ key: 'register', icon: <TagOutlined />, label: '注册', onClick: () => setRegisterRow(record) });
    }
    if (record.registered && record.stage !== 'production') {
      acts.push({
        key: 'promote',
        icon: <RocketOutlined />,
        label: '晋升',
        onClick: () => record.model_id && handlePromote(record.model_id),
      });
    }
    if (record.registered && record.stage === 'production') {
      acts.push({
        key: 'download',
        icon: <DownloadOutlined />,
        label: '下载',
        // 下载不经 axios:后端该端点刻意不带 Authorization(见 model_routes.download),location 跳转直接触发下载
        onClick: () => {
          window.location.href = `/api/v1/models/${encodeURIComponent(record.model_id ?? '')}/download`;
        },
      });
      acts.push({
        key: 'unpromote',
        icon: <RollbackOutlined />,
        label: '取消晋升',
        onClick: () => {
          if (!record.model_id) return;
          modal.confirm({
            title: '取消晋升',
            content: '模型将从 production 移回 staging',
            okText: '确定',
            cancelText: '取消',
            onOk: () => handleUnpromote(record.model_id!),
          });
        },
      });
    }
    acts.push({
      key: 'delete',
      icon: <DeleteOutlined />,
      label: '删除',
      danger: true,
      onClick: () => handleDelete(record),
    });
    return acts;
  };

  const renderActions = (record: UnifiedModelRow, iconOnly = false) => {
    const acts = actionsFor(record);
    if (iconOnly) {
      return (
        // 表格操作列图标按钮 + Tooltip(与策略管理页操作列一致);行内点击不冒泡
        <Space size={4} onClick={(e) => e.stopPropagation()}>
          {acts.map((a) => (
            <Tooltip key={a.key} title={a.label}>
              <Button type="text" size="small" danger={a.danger} icon={a.icon} onClick={a.onClick} />
            </Tooltip>
          ))}
        </Space>
      );
    }
    return (
      <Space size={4} onClick={(e) => e.stopPropagation()} wrap>
        {/* 删除已上移卡片右上角 extra,文字按钮组不再重复展示 */}
        {acts
          .filter((a) => a.key !== 'delete')
          .map((a) => (
            <Button key={a.key} size="small" danger={a.danger} onClick={a.onClick}>
              {a.label}
            </Button>
          ))}
      </Space>
    );
  };

  const columns: TableProps<UnifiedModelRow>['columns'] = [
    {
      title: '模型名称',
      dataIndex: 'file_name',
      key: 'file_name',
      ellipsis: true,
      // 对齐 ResearchList 会话列:显式宽保证 scroll.x 容器不足时列不被压 0
      width: 300,
      render: (text: string, record: UnifiedModelRow) => (
        <Space size="small">
          {algoLabel(record) && <Tag color="blue">{algoLabel(record)}</Tag>}
          <Text style={{ maxWidth: 260 }} ellipsis={{ tooltip: record.model_id ? `${text}（${record.model_id}）` : text }}>
            {record.model_id ?? text}
          </Text>
        </Space>
      ),
    },
    { title: '状态', key: 'status', width: 110, render: (_, record) => <StatusTag row={record} /> },
    { title: 'Sharpe', key: 'sharpe', width: 90, align: 'right', render: (_, record) => sharpeText(record) },
    {
      title: '创建时间',
      dataIndex: 'created',
      key: 'created',
      width: 170,
      // nowrap:完整时间戳一行展示,避免被截
      className: 'whitespace-nowrap',
      render: (ts: number | null) => (ts ? dayjs(ts * 1000).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '大小',
      dataIndex: 'size_mb',
      key: 'size_mb',
      width: 90,
      align: 'right',
      render: (v: number | null) => (v == null ? '-' : `${v} MB`),
    },
    // 固定列:容器横向滚动时操作始终可见(production 行最多 4 个图标按钮,140 容纳)
    { title: '操作', key: 'actions', width: 140, fixed: 'right', render: (_, record) => renderActions(record, true) },
  ];

  // 双视图共享同一分页配置:列表视图交给 Table,卡片视图配 Grid + Pagination
  const paginationProps = {
    current,
    pageSize,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (t: number) => `共 ${t} 条`,
    onChange: (page: number, size: number) => {
      // 条数变化写回全局配置(与 RLModelList 既有口径一致)
      if (size !== pageSize) setPageSize(size);
      setCurrent(page);
    },
  };

  // 卡片视图当前页数据(与表格同源同分页,筛选/翻页行为一致)
  const pageRows = useMemo(
    () => filtered.slice((current - 1) * pageSize, current * pageSize),
    [filtered, current, pageSize],
  );

  return (
    <>
      <Card>
        <Flex vertical gap={16}>
          <Flex gap={8} wrap="wrap" align="center" justify="space-between">
            <Flex gap={8} wrap="wrap" align="center">
              <Input
                allowClear
                placeholder="搜索文件名 / 模型 ID"
                prefix={<SearchOutlined />}
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                style={{ width: 240 }}
              />
              <Select
                allowClear
                placeholder="算法"
                value={algoFilter}
                onChange={(v) => setAlgoFilter(v)}
                options={algoOptions}
                style={{ width: 120 }}
              />
              <Select
                allowClear
                placeholder="状态"
                value={stageFilter}
                onChange={(v) => setStageFilter(v)}
                options={stageOptions}
                style={{ width: 140 }}
              />
              <Button type="text" icon={<ReloadOutlined />} onClick={loadRows} title="刷新" />
              {selected.length > 0 && (
                <Button
                  type="primary"
                  icon={<BarChartOutlined />}
                  // ponytail: RL 回测占位随迁(上游 RLTrainingPage 即此行为),回测开放时改接真实跳转
                  onClick={() => message.warning(`RL 回测暂未开放（${selected[0]}）`)}
                >
                  回测选中模型
                </Button>
              )}
            </Flex>
            <Segmented
              value={view}
              onChange={(v) => setView(v as 'card' | 'list')}
              // 图标+文字与 ResearchList 视图切换一致;小屏只留图标
              options={[
                { value: 'card', icon: <AppstoreOutlined />, label: screens.sm ? '卡片' : undefined },
                { value: 'list', icon: <UnorderedListOutlined />, label: screens.sm ? '列表' : undefined },
              ]}
            />
          </Flex>

          {view === 'card' ? (
            pageRows.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: '48px 0' }} />
            ) : (
              <Row gutter={[16, 16]}>
                {pageRows.map((record) => {
                  const algo = algoLabel(record);
                  const isSelected = selected.includes(record.file_name);
                  const nameTooltip = record.model_id ? `${record.file_name}（${record.model_id}）` : record.file_name;
                  return (
                    <Col key={record.file_name} xs={24} sm={12} md={8} lg={6}>
                      <Card
                        size="small"
                        hoverable
                        style={{ cursor: 'pointer', height: '100%', ...(isSelected ? { borderColor: 'var(--tw-color-info)' } : {}) }}
                        onClick={() => {
                          // 对齐表格禁选口径:文件缺失(无文件)不可选中
                          if (record.size_mb == null) return;
                          setSelected((prev) => (prev.includes(record.file_name) ? [] : [record.file_name]));
                        }}
                        title={<span className="truncate" title={nameTooltip}>{record.model_id ?? record.file_name}</span>}
                        extra={
                          statusOf(record) !== 'missing' && (
                            <Tooltip title="删除">
                              <Button
                                type="text"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                // 删除统一放卡片右上角;点击不可穿透到卡片选中
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDelete(record);
                                }}
                              />
                            </Tooltip>
                          )
                        }
                      >
                        <Flex vertical gap={8}>
                          <Space size={6} wrap>
                            {algo ? <Tag color="blue">{algo}</Tag> : null}
                            {/* 状态从右上角挪到标签行,右上角让位给删除按钮 */}
                            <StatusTag row={record} />
                          </Space>
                          <MetaRow label="Sharpe" value={sharpeText(record)} />
                          <MetaRow
                            label="创建时间"
                            value={record.created ? dayjs(record.created * 1000).format('YYYY-MM-DD HH:mm') : '-'}
                          />
                          <MetaRow label="大小" value={record.size_mb == null ? '-' : `${record.size_mb} MB`} />
                          {/* 操作区 renderActions 内部已阻止冒泡 */}
                          <div className="pt-2 border-t border-gray-100">{renderActions(record)}</div>
                        </Flex>
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            )
          ) : (
            <Table<UnifiedModelRow>
              rowKey="file_name"
              size="middle"
              columns={columns}
              dataSource={filtered}
              loading={loading}
              /* 固定列总宽 900px(名称 300 + 其余列显式宽),所有列都有显式宽:
                 容器不足时若无 scroll.x,无宽列会被压成 0 宽整列消失,声明后表格内部横滚且操作列冻结 */
              scroll={{ x: 900 }}
              rowSelection={{
                selectedRowKeys: selected,
                onChange: (keys) => setSelected(keys.slice(-1).map(String)), // 单选携带
                getCheckboxProps: (record) => ({ disabled: record.size_mb == null }), // 无文件不可选
              }}
              pagination={paginationProps}
            />
          )}

          {view === 'card' && filtered.length > 0 && (
            <Row justify="center" style={{ marginTop: 16 }}>
              <Pagination {...paginationProps} total={filtered.length} />
            </Row>
          )}
        </Flex>
      </Card>
      <RegisterModelModal
        row={registerRow}
        onClose={() => setRegisterRow(null)}
        onSuccess={() => {
          setRegisterRow(null);
          loadRows();
        }}
      />
      <ModelDetailDrawer row={detailRow} onClose={() => setDetailRow(null)} />
    </>
  );
}
