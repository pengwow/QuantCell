import { useState, useEffect } from 'react';
import { Card, Table, Button, Select, Input, Space, Tag, message, Form } from 'antd';
import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import PageContainer from '@/components/PageContainer';
import { ensembleApi, EnsembleInfo } from '@/api/ensembleApi';

export default function EnsemblePage() {
  const [ensembles, setEnsembles] = useState<EnsembleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [predictResult, setPredictResult] = useState<any>(null);
  const [form] = Form.useForm();

  useEffect(() => { loadEnsembles(); }, []);

  const loadEnsembles = async () => {
    setLoading(true);
    try {
      const data = await ensembleApi.listEnsembles();
      setEnsembles(Array.isArray(data) ? data : []);
    } catch { message.error('加载集成列表失败'); }
    finally { setLoading(false); }
  };

  const handleCreate = async (values: any) => {
    try {
      await ensembleApi.createEnsemble({
        strategy: values.strategy,
        model_paths: values.model_paths.split(',').map((s: string) => s.trim()),
      });
      message.success('集成创建成功');
      form.resetFields();
      loadEnsembles();
    } catch { message.error('创建失败'); }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id' },
    { title: '策略', dataIndex: 'strategy', key: 'strategy', render: (s: string) => <Tag>{s}</Tag> },
    { title: '模型数', dataIndex: 'models', key: 'models' },
  ];

  return (
    <PageContainer title="集成学习">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card title="创建集成">
          <Form form={form} onFinish={handleCreate} layout="vertical">
            <Form.Item name="strategy" label="投票策略" initialValue="soft_vote">
              <Select>
                <Select.Option value="soft_vote">Soft Vote</Select.Option>
                <Select.Option value="hard_vote">Hard Vote</Select.Option>
                <Select.Option value="weighted">Weighted</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="model_paths" label="模型路径（逗号分隔）" rules={[{ required: true }]}>
              <Input placeholder="/path/m1.onnx, /path/m2.onnx" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>创建</Button>
            </Form.Item>
          </Form>
        </Card>

        <Card title="集成列表">
          <Table columns={columns} dataSource={ensembles} loading={loading} rowKey="id" size="small" />
        </Card>
      </div>
    </PageContainer>
  );
}
