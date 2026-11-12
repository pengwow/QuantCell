import { useEffect, useState } from 'react';
import { App as AntdApp, Descriptions, Drawer, Space, Spin, Table, Tag } from 'antd';
import type { TableProps } from 'antd';
import dayjs from 'dayjs';
import { modelApi, type ModelDetail, type ModelFeatureSpec, type UnifiedModelRow } from '@/api/modelApi';
import { useTranslation } from 'react-i18next';

// walk_forward aggregate 嵌套对象展平为带前缀键后逐行展示(自 ModelRegistry.tsx 原样迁入)
const flattenKv = (obj: Record<string, unknown>, prefix = ''): Record<string, string> =>
  Object.fromEntries(
    Object.entries(obj).map(([key, value]) =>
      value != null && typeof value === 'object' && !Array.isArray(value)
        ? [prefix + key, JSON.stringify(value)]
        : [prefix + key, value == null ? '-' : String(value)],
    ),
  );

interface ModelDetailDrawerProps {
  row: UnifiedModelRow | null;
  onClose: () => void;
}

export default function ModelDetailDrawer({ row, onClose }: ModelDetailDrawerProps) {
  const { message } = AntdApp.useApp();
  const { t } = useTranslation();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loading, setLoading] = useState(false);

  // 观测与特征规格 feature 列定义(自 ModelRegistry.tsx 原样迁入;字段名以 modelApi.ModelFeatureSpec 为准);列标题走进词条,故移入组件内
  const featureColumns: TableProps<ModelFeatureSpec>['columns'] = [
    { title: t('mdd_col_name'), dataIndex: 'name', key: 'name', ellipsis: true },
    { title: t('mdd_col_source'), dataIndex: 'source_display', key: 'source_display', ellipsis: true },
    { title: t('mdd_col_norm'), dataIndex: 'normalizer', key: 'normalizer', width: 110, render: (v: string | null) => v || '-' },
    {
      title: 'Clip',
      dataIndex: 'clip_range',
      key: 'clip_range',
      width: 130,
      render: (v: number[] | null) => (v ? `[${v[0]}, ${v[1]}]` : '-'),
    },
  ];

  useEffect(() => {
    if (!row || !row.registered || !row.model_id) {
      setDetail(null);
      return;
    }
    setLoading(true);
    modelApi
      .getModelDetail(row.model_id)
      .then(setDetail)
      .catch(() => message.error(t('mdd_msg_load_failed')))
      .finally(() => setLoading(false));
  }, [row, message]);

  const baseKv = detail
    ? flattenKv({ [t('mdd_field_name')]: detail.name, [t('mdd_field_version')]: detail.version, [t('mdd_field_stage')]: detail.stage, [t('mdd_field_algo')]: detail.algorithm })
    : {};
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
      title={row ? t('mdd_title_named', { name: row.file_name }) : t('mdd_title')}
      open={!!row}
      onClose={onClose}
      size={520}
      destroyOnHidden
    >
      {!row || (row.registered && loading) ? (
        <Spin />
      ) : row.registered && detail ? (
        <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
          <Descriptions title={t('mdd_sec_basic')} column={1} size="small" bordered items={Object.entries(baseKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
          {detail.walk_forward && Object.keys(detail.walk_forward).length > 0 && (
            <Descriptions
              title={t('mdd_sec_walk_forward')}
              column={1}
              size="small"
              bordered
              items={Object.entries(flattenKv(detail.walk_forward as Record<string, unknown>)).map(([k, v]) => ({ key: k, label: k, children: v }))}
            />
          )}
          <Descriptions title={t('mdd_sec_metrics')} column={1} size="small" bordered items={Object.entries(metricsKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
          <Descriptions title={t('mdd_sec_spec')} column={1} size="small" bordered items={Object.entries(specKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
          {detail.features && detail.features.length > 0 && (
            <>
              <Tag>{t('mdd_feature_count', { n: detail.features.length })}</Tag>
              <Table<ModelFeatureSpec>
                size="small"
                rowKey="name"
                columns={featureColumns}
                dataSource={detail.features}
                pagination={{ pageSize: 8, showSizeChanger: false }}
              />
            </>
          )}
          <Descriptions title={t('mdd_sec_files')} column={1} size="small" bordered items={Object.entries(fileKv).map(([k, v]) => ({ key: k, label: k, children: v }))} />
        </Space>
      ) : (
        <Descriptions
          title={t('mdd_sec_file_info')}
          column={1}
          size="small"
          bordered
          items={[
            { key: 'name', label: t('mdd_label_file_name'), children: row?.file_name ?? '-' },
            { key: 'size', label: t('mdd_label_size'), children: row?.size_mb != null ? `${row.size_mb} MB` : '-' },
            { key: 'created', label: t('mdd_label_created'), children: row?.created ? dayjs(row.created * 1000).format('YYYY-MM-DD HH:mm:ss') : '-' },
            { key: 'path', label: t('mdd_label_path'), children: row?.path ?? '-' },
            { key: 'algo', label: t('mdd_label_algo'), children: (row?.algorithm && row.algorithm !== '-' ? row.algorithm : '-') ?? '-' },
          ]}
        />
      )}
    </Drawer>
  );
}
