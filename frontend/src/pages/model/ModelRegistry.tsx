import { useState, useEffect } from 'react';
import { Table, Button, Tag, Space, message, Modal, Form, Input, InputNumber } from 'antd';
import { PlusOutlined, RocketOutlined } from '@ant-design/icons';
import PageContainer from '@/components/PageContainer';
import { modelApi, type ModelInfo } from '@/api/modelApi';

export default function ModelRegistry() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

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
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'production' ? 'green' : status === 'staging' ? 'orange' : 'default'}>
          {status || 'development'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: ModelInfo) => (
        <Space>
          {record.status !== 'production' && (
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
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>模型注册表</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          注册模型
        </Button>
      </div>
      <Table columns={columns} dataSource={models} loading={loading} rowKey="id" />

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
    </PageContainer>
  );
}
