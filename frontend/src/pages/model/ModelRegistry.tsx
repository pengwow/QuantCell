import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Tag,
  Space,
  Card,
  message,
  Modal,
  Form,
  Input,
  InputNumber,
  Drawer,
  Descriptions,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  RocketOutlined,
  EyeOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import PageContainer from '@/components/PageContainer';
import { modelApi, type ModelInfo, type ModelDetail } from '@/api/modelApi';

// walk_forward aggregate 形如 {mean: {...}, std: {...}, n_valid_folds: n},
// 嵌套对象展平为带前缀键(mean.sharpe_ratio)后逐行展示
const flattenKv = (obj: Record<string, unknown>, prefix = ''): [string, unknown][] =>
  Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? flattenKv(v as Record<string, unknown>, `${prefix}${k}.`)
      : ([[`${prefix}${k}`, v]] as [string, unknown][]),
  );

const featureColumns = [
  { title: '特征', dataIndex: 'name', key: 'name' },
  { title: '来源', dataIndex: 'source_display', key: 'source_display' },
  { title: '归一化', dataIndex: 'normalizer', key: 'normalizer', render: (v: string | null) => v ?? '-' },
  {
    title: 'Clip',
    dataIndex: 'clip_range',
    key: 'clip_range',
    render: (v: number[] | null) => (v == null ? '-' : JSON.stringify(v)),
  },
];

export default function ModelRegistry() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<ModelDetail | null>(null);

  useEffect(() => {
    loadModels();
  }, []);

  const loadModels = async () => {
    setLoading(true);
    try {
      const data = await modelApi.listModels();
      setModels(Array.isArray(data) ? data : []);
    } catch {
      message.error('加载模型列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handlePromote = async (modelId: string) => {
    try {
      await modelApi.promoteModel(modelId);
      message.success('模型已晋升到生产环境');
      loadModels();
    } catch {
      message.error('晋升失败');
    }
  };

  const handleDetail = async (name: string) => {
    try {
      const data = await modelApi.getModelDetail(name);
      setDetail(data);
      setDetailOpen(true);
    } catch {
      message.error('加载模型详情失败');
    }
  };

  const handleRegister = async (values: { name: string; model_path: string; algorithm?: string; sharpe?: number }) => {
    try {
      await modelApi.registerModel({
        name: values.name,
        model_path: values.model_path,
        metadata: { algorithm: values.algorithm || 'ppo' },
        metrics: values.sharpe ? { sharpe: values.sharpe } : {},
      });
      message.success('模型注册成功');
      setModalOpen(false);
      form.resetFields();
      loadModels();
    } catch {
      message.error('注册失败');
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '版本', dataIndex: 'version', key: 'version' },
    {
      title: '状态',
      dataIndex: 'stage',
      key: 'stage',
      render: (stage: string) => (
        <Tag color={stage === 'production' ? 'green' : stage === 'archived' ? 'default' : 'orange'}>
          {stage || 'development'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: ModelInfo) => (
        <Space>
          {/* 未晋升模型后端已可返回详情(get_latest 兜底),按钮对所有 stage 开放 */}
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleDetail(record.name)}>
            详情
          </Button>
          {record.stage === 'production' ? (
            /* 下载不走 axios:浏览器 <a download> 无法附带 Authorization 头,
                对应后端 download 端点刻意不鉴权(内网假设) */
            <Button
              size="small"
              icon={<DownloadOutlined />}
              href={`/api/v1/models/${encodeURIComponent(record.name)}/download`}
              download
            >
              下载
            </Button>
          ) : (
            <Button
              type="primary"
              size="small"
              icon={<RocketOutlined />}
              onClick={() => handlePromote(record.id)}
            >
              晋升
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="模型注册表">
      <Card
        title="模型注册表"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            注册模型
          </Button>
        }
      >
        <Table columns={columns} dataSource={models} loading={loading} rowKey="id" />
      </Card>

      <Modal
        title="注册新模型"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleRegister}>
          <Form.Item name="name" label="模型名称" rules={[{ required: true }]}>
            <Input placeholder="例如: ppo_btc_v1" />
          </Form.Item>
          <Form.Item name="model_path" label="模型文件路径" rules={[{ required: true }]}>
            <Input placeholder="/path/to/model.onnx" />
          </Form.Item>
          <Form.Item name="algorithm" label="算法">
            <Input placeholder="ppo / sac / dqn" />
          </Form.Item>
          <Form.Item name="sharpe" label="Sharpe Ratio">
            <InputNumber placeholder="1.5" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">注册</Button>
              <Button onClick={() => setModalOpen(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={detail ? `模型详情 - ${detail.name}` : '模型详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={520}
      >
        {detail && (
          <Space orientation="vertical" size="large" style={{ display: 'flex' }}>
            {/* 1. 基本信息 */}
            <Descriptions
              title="基本信息"
              column={1}
              size="small"
              bordered
              items={[
                { key: 'name', label: '名称', children: detail.name },
                { key: 'version', label: '版本', children: detail.version || '-' },
                { key: 'stage', label: '状态', children: <Tag color="green">{detail.stage}</Tag> },
                { key: 'algorithm', label: '算法', children: detail.algorithm },
                { key: 'trained_at', label: '训练时间', children: detail.trained_at },
                { key: 'spec', label: '观测规格版本', children: detail.spec_version },
                { key: 'window', label: '观测窗口', children: String(detail.window_size) },
              ]}
            />

            {/* 2. 评估指标 */}
            <Descriptions
              title="评估指标"
              column={1}
              size="small"
              bordered
              items={[
                {
                  key: 'metrics',
                  label: '注册指标',
                  children:
                    Object.keys(detail.metrics).length > 0 ? (
                      Object.entries(detail.metrics).map(([k, v]) => <div key={k}>{`${k}: ${v}`}</div>)
                    ) : (
                      '-'
                    ),
                },
                {
                  key: 'wf',
                  label: 'Walk-Forward OOS 汇总',
                  children:
                    flattenKv(detail.walk_forward ?? {}).length > 0 ? (
                      flattenKv(detail.walk_forward ?? {}).map(([k, v]) => <div key={k}>{`${k}: ${v}`}</div>)
                    ) : (
                      '-'
                    ),
                },
              ]}
            />

            {/* 3. 观测与特征规格 */}
            <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
              <Typography.Text strong>观测与特征规格</Typography.Text>
              <Descriptions
                column={1}
                size="small"
                bordered
                items={[
                  {
                    key: 'stats',
                    label: '归一化统计量',
                    children: detail.observation_stats_present ? (
                      '已随模型落盘'
                    ) : (
                      <Typography.Text type="warning">缺失,内核侧 Z-Score 将恒为 0</Typography.Text>
                    ),
                  },
                ]}
              />
              {detail.features.length > 0 ? (
                <Table
                  size="small"
                  pagination={false}
                  rowKey="name"
                  dataSource={detail.features}
                  columns={featureColumns}
                />
              ) : (
                <Typography.Text type="secondary">特征未记录</Typography.Text>
              )}
            </Space>

            {/* 4. 文件 */}
            <Descriptions
              title="文件"
              column={1}
              size="small"
              bordered
              items={[
                {
                  key: 'size',
                  label: '文件大小',
                  children: `${(detail.artifact_size_bytes / 1024 / 1024).toFixed(2)} MB`,
                },
                {
                  key: 'hash',
                  label: 'SHA256',
                  children: (
                    <Typography.Text code copyable={{ text: detail.artifact_hash }} style={{ fontSize: 12 }}>
                      {detail.artifact_hash.slice(0, 16)}…
                    </Typography.Text>
                  ),
                },
                {
                  key: 'uri',
                  label: '存储路径',
                  children: (
                    <Typography.Text copyable style={{ fontSize: 12 }}>
                      {detail.storage_uri}
                    </Typography.Text>
                  ),
                },
              ]}
            />
          </Space>
        )}
      </Drawer>
    </PageContainer>
  );
}
