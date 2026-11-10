import { useEffect, useState } from 'react';
import { App as AntdApp, Descriptions, Drawer, Space, Spin, Table, Tag } from 'antd';
import type { TableProps } from 'antd';
import dayjs from 'dayjs';
import { modelApi, type ModelDetail, type ModelFeatureSpec, type UnifiedModelRow } from '@/api/modelApi';

// walk_forward aggregate 嵌套对象展平为带前缀键后逐行展示(自 ModelRegistry.tsx 原样迁入)
const flattenKv = (obj: Record<string, unknown>, prefix = ''): Record<string, string> =>
  Object.fromEntries(
    Object.entries(obj).map(([key, value]) =>
      value != null && typeof value === 'object' && !Array.isArray(value)
        ? [prefix + key, JSON.stringify(value)]
        : [prefix + key, value == null ? '-' : String(value)],
    ),
  );

// 观测与特征规格 feature 列定义(自 ModelRegistry.tsx 原样迁入;字段名以 modelApi.ModelFeatureSpec 为准)
const featureColumns: TableProps<ModelFeatureSpec>['columns'] = [
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '来源', dataIndex: 'source_display', key: 'source_display', ellipsis: true },
  { title: '归一化', dataIndex: 'normalizer', key: 'normalizer', width: 110, render: (v: string | null) => v || '-' },
  {
    title: 'Clip',
    dataIndex: 'clip_range',
    key: 'clip_range',
    width: 130,
    render: (v: number[] | null) => (v ? `[${v[0]}, ${v[1]}]` : '-'),
  },
];

interface ModelDetailDrawerProps {
  row: UnifiedModelRow | null;
  onClose: () => void;
}

export default function ModelDetailDrawer({ row, onClose }: ModelDetailDrawerProps) {
  const { message } = AntdApp.useApp();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!row || !row.registered || !row.model_id) {
      setDetail(null);
      return;
    }
    setLoading(true);
    modelApi
      .getModelDetail(row.model_id)
      .then(setDetail)
      .catch(() => message.error('加载模型详情失败'))
      .finally(() => setLoading(false));
  }, [row, message]);

  const baseKv = detail ? flattenKv({ 名称: detail.name, 版本: detail.version, 阶段: detail.stage, 算法: detail.algorithm }) : {};
  const metricsKv = detail ? flattenKv(detail.metrics) : {};
  const specKv = detail
    ? flattenKv({ spec_version: detail.spec_version, window_size: detail.window_size, trained_at: detail.trained_at })
    : {};
  const fileKv = detail
    ? flattenKv({
        artifact_size_bytes: detail.artifact_size_bytes,
        artifact_hash: detail.artifact_hash,
        storage_uri: detail.storage_uri,
      })
    : {};

  return (
    // antd v6 Drawer 的 width 已弃用,size 同样支持数值宽度
    <Drawer
      title={row ? `模型详情 - ${row.file_name}` : '模型详情'}
      open={!!row}
      onClose={onClose}
      size={520}
      destroyOnHidden
    >
      {!row || (row.registered && loading) ? (
        <Spin />
      ) : row.registered && detail ? (
        <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
          <Descriptions title="基本信息" column={1} size="small" bordered items={Object.entries(baseKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
          {detail.walk_forward && Object.keys(detail.walk_forward).length > 0 && (
            <Descriptions
              title="Walk-Forward(OOS 汇总)"
              column={1}
              size="small"
              bordered
              items={Object.entries(flattenKv(detail.walk_forward as Record<string, unknown>)).map(([k, v]) => ({ key: k, label: k, children: v }))}
            />
          )}
          <Descriptions title="评估指标" column={1} size="small" bordered items={Object.entries(metricsKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
          <Descriptions title="观测与特征规格" column={1} size="small" bordered items={Object.entries(specKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
          {detail.features && detail.features.length > 0 && (
            <>
              <Tag>共 {detail.features.length} 个特征</Tag>
              <Table<ModelFeatureSpec>
                size="small"
                rowKey="name"
                columns={featureColumns}
                dataSource={detail.features}
                pagination={{ pageSize: 8, showSizeChanger: false }}
              />
            </>
          )}
          <Descriptions title="文件" column={1} size="small" bordered items={Object.entries(fileKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
        </Space>
      ) : (
        <Descriptions
          title="文件信息"
          column={1}
          size="small"
          bordered
          items={[
            { key: 'name', label: '文件名', children: row?.file_name ?? '-' },
            { key: 'size', label: '大小', children: row?.size_mb != null ? `${row.size_mb} MB` : '-' },
            { key: 'created', label: '创建时间', children: row?.created ? dayjs(row.created * 1000).format('YYYY-MM-DD HH:mm:ss') : '-' },
            { key: 'path', label: '路径', children: row?.path ?? '-' },
            { key: 'algo', label: '算法', children: (row?.algorithm && row.algorithm !== '-' ? row.algorithm : '-') ?? '-' },
          ]}
        />
      )}
    </Drawer>
  );
}
