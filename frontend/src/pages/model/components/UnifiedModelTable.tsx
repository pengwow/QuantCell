import { useEffect, useMemo, useState } from 'react';
import { App as AntdApp, Button, Flex, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import {
  BarChartOutlined,
  DownloadOutlined,
  EyeOutlined,
  ReloadOutlined,
  RestOutlined,
  RocketOutlined,
  RollbackOutlined,
  SearchOutlined,
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
  // pageSize 全站开关,返回值是元组(同 RLModelList 既有用法)
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [current, setCurrent] = useState(1);

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

  const columns: TableProps<UnifiedModelRow>['columns'] = [
    {
      title: '模型名称',
      dataIndex: 'file_name',
      key: 'file_name',
      ellipsis: true,
      render: (text: string, record: UnifiedModelRow) => (
        <Space size="small">
          {record.algorithm && record.algorithm !== '-' && <Tag color="blue">{record.algorithm.toUpperCase()}</Tag>}
          <Text style={{ maxWidth: 260 }} ellipsis={{ tooltip: record.model_id ? `${text}（${record.model_id}）` : text }}>
            {record.model_id ?? text}
          </Text>
        </Space>
      ),
    },
    { title: '状态', key: 'status', width: 110, render: (_, record) => <StatusTag row={record} /> },
    {
      title: 'Sharpe',
      key: 'sharpe',
      width: 90,
      align: 'right',
      render: (_, record) => {
        // 未注册/无指标显示占位;兼容 sharpe_ratio 与 sharpe 两种键名
        const v = record.metrics?.sharpe_ratio ?? record.metrics?.sharpe;
        return v == null ? '-' : Number(v).toFixed(2);
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created',
      key: 'created',
      width: 170,
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
    {
      title: '操作',
      key: 'actions',
      width: 280,
      render: (_, record) => {
        const s = statusOf(record);
        // 文件缺失条目仅可看详情(注册表无 delete/生命周期操作不可用)
        if (s === 'missing') {
          return (
            <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailRow(record)}>
              详情
            </Button>
          );
        }
        return (
          <Space size={4} wrap>
            <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailRow(record)}>
              详情
            </Button>
            {!record.registered && (
              <Button size="small" type="primary" onClick={() => setRegisterRow(record)}>
                注册
              </Button>
            )}
            {record.registered && record.stage !== 'production' && (
              <Button
                size="small"
                type="primary"
                icon={<RocketOutlined />}
                onClick={() => record.model_id && handlePromote(record.model_id)}
              >
                晋升
              </Button>
            )}
            {record.registered && record.stage === 'production' && (
              <>
                {/* 下载走 <a download> 不经 axios:后端该端点刻意不带 Authorization(见 model_routes.download) */}
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  href={`/api/v1/models/${encodeURIComponent(record.model_id ?? '')}/download`}
                >
                  下载
                </Button>
                <Popconfirm
                  title="确定取消晋升吗？"
                  description="模型将从 production 移回 staging"
                  okText="确定"
                  cancelText="取消"
                  onConfirm={() => record.model_id && handleUnpromote(record.model_id)}
                >
                  <Button size="small" icon={<RollbackOutlined />}>
                    取消晋升
                  </Button>
                </Popconfirm>
              </>
            )}
            <Button size="small" type="link" danger icon={<RestOutlined />} onClick={() => handleDelete(record)} />
          </Space>
        );
      },
    },
  ];

  return (
    <Flex vertical gap={16}>
      <Flex gap={8} wrap="wrap">
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
      <Table<UnifiedModelRow>
        rowKey="file_name"
        size="middle"
        columns={columns}
        dataSource={filtered}
        loading={loading}
        scroll={{ x: 'max-content' }}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys.slice(-1).map(String)), // 单选携带
          getCheckboxProps: (record) => ({ disabled: record.size_mb == null }), // 无文件不可选
        }}
        pagination={{
          current,
          pageSize,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (page, size) => {
            // 条数变化写回全局配置(与 RLModelList 既有口径一致)
            if (size !== pageSize) setPageSize(size);
            setCurrent(page);
          },
        }}
      />
      <RegisterModelModal
        row={registerRow}
        onClose={() => setRegisterRow(null)}
        onSuccess={() => {
          setRegisterRow(null);
          loadRows();
        }}
      />
      <ModelDetailDrawer row={detailRow} onClose={() => setDetailRow(null)} />
    </Flex>
  );
}
