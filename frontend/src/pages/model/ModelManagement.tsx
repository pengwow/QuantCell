/**
 * 模型管理页面
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Button,
  Table,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Select,
  Progress,
  message,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined, EyeOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import PageContainer from '@/components/PageContainer';

const { Option } = Select;

interface Model {
  id: string;
  name: string;
  type: string;
  status: 'trained' | 'training' | 'untrained';
  accuracy: number;
  mse: number;
  mae: number;
  r2: number;
  createdAt: string;
}

const ModelManagement = () => {
  const { t } = useTranslation();
  const [models, setModels] = useState<Model[]>([
    { id: '1', name: 'LSTM价格预测', type: 'LSTM', status: 'trained', accuracy: 0.85, mse: 0.02, mae: 0.12, r2: 0.78, createdAt: '2024-01-15' },
    { id: '2', name: '随机森林分类', type: 'RandomForest', status: 'trained', accuracy: 0.82, mse: 0.03, mae: 0.15, r2: 0.75, createdAt: '2024-01-10' },
    { id: '3', name: 'XGBoost回归', type: 'XGBoost', status: 'training', accuracy: 0, mse: 0, mae: 0, r2: 0, createdAt: '2024-01-20' },
  ]);
  const [modalVisible, setModalVisible] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [form] = Form.useForm();

  const columns = [
    { title: '模型名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = { trained: 'success', training: 'processing', untrained: 'default' };
        const textMap: Record<string, string> = { trained: '已训练', training: '训练中', untrained: '未训练' };
        return <Tag color={colorMap[status]}>{textMap[status]}</Tag>;
      },
    },
    { title: '准确率', dataIndex: 'accuracy', key: 'accuracy', render: (v: number) => v ? `${(v * 100).toFixed(2)}%` : '-' },
    { title: 'MSE', dataIndex: 'mse', key: 'mse', render: (v: number) => v ? v.toFixed(4) : '-' },
    { title: 'MAE', dataIndex: 'mae', key: 'mae', render: (v: number) => v ? v.toFixed(4) : '-' },
    { title: 'R²', dataIndex: 'r2', key: 'r2', render: (v: number) => v ? v.toFixed(4) : '-' },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Model) => (
        <Space>
          <Button icon={<EyeOutlined />} size="small" onClick={() => { setSelectedModel(record); setDetailVisible(true); }}>详情</Button>
          <Button icon={<PlayCircleOutlined />} size="small" disabled={record.status === 'training'}>训练</Button>
          <Button icon={<EditOutlined />} size="small">编辑</Button>
          <Button icon={<DeleteOutlined />} size="small" danger onClick={() => handleDelete(record.id)}>删除</Button>
        </Space>
      ),
    },
  ];

  const handleDelete = (id: string) => {
    setModels(models.filter(m => m.id !== id));
    message.success('删除成功');
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setModels([...models, { ...values, id: Date.now().toString(), status: 'untrained', accuracy: 0, mse: 0, mae: 0, r2: 0, createdAt: new Date().toISOString() }]);
    setModalVisible(false);
    form.resetFields();
  };

  const performanceChartOption = {
    title: { text: '模型性能对比' },
    radar: {
      indicator: [
        { name: '准确率', max: 1 },
        { name: 'R²', max: 1 },
        { name: '稳定性', max: 1 },
        { name: '速度', max: 1 },
        { name: '泛化能力', max: 1 },
      ],
    },
    series: [{
      type: 'radar',
      data: [
        { value: [0.85, 0.78, 0.8, 0.7, 0.75], name: 'LSTM' },
        { value: [0.82, 0.75, 0.85, 0.9, 0.8], name: 'RandomForest' },
      ],
    }],
  };

  return (
    <PageContainer title={t('model_management')}>
      <Card
        title={t('model_management')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            新建模型
          </Button>
        }
      >
        <Table columns={columns} dataSource={models} rowKey="id" />
      </Card>

      <Modal title="新建模型" open={modalVisible} onOk={handleSave} onCancel={() => setModalVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="模型名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label="模型类型" rules={[{ required: true }]}>
            <Select>
              <Option value="LSTM">LSTM</Option>
              <Option value="RandomForest">RandomForest</Option>
              <Option value="XGBoost">XGBoost</Option>
              <Option value="LightGBM">LightGBM</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="模型详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={800}>
        {selectedModel && (
          <>
            <p><strong>模型名称:</strong> {selectedModel.name}</p>
            <p><strong>模型类型:</strong> {selectedModel.type}</p>
            <p><strong>状态:</strong> <Tag color={selectedModel.status === 'trained' ? 'success' : 'processing'}>{selectedModel.status}</Tag></p>
            {selectedModel.status === 'training' && <Progress percent={65} status="active" />}
            <ReactECharts option={performanceChartOption} style={{ height: 400, marginTop: 20 }} />
          </>
        )}
      </Modal>
    </PageContainer>
  );
};

export default ModelManagement;
