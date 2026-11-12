/**
 * 模型管理页面
 */
import { useState, useEffect } from 'react';
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
import EChart from '@/components/EChart';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';

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

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('model_management'));
  }, [t]);

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
    { title: t('mm_field_name'), dataIndex: 'name', key: 'name' },
    { title: t('mm_col_type'), dataIndex: 'type', key: 'type' },
    {
      title: t('mm_col_status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = { trained: 'success', training: 'processing', untrained: 'default' };
        const textMap: Record<string, string> = {
          trained: t('mm_status_trained'),
          training: t('mm_status_training'),
          untrained: t('mm_status_untrained'),
        };
        return <Tag color={colorMap[status]}>{textMap[status]}</Tag>;
      },
    },
    { title: t('mm_col_accuracy'), dataIndex: 'accuracy', key: 'accuracy', render: (v: number) => v ? `${(v * 100).toFixed(2)}%` : '-' },
    { title: 'MSE', dataIndex: 'mse', key: 'mse', render: (v: number) => v ? v.toFixed(4) : '-' },
    { title: 'MAE', dataIndex: 'mae', key: 'mae', render: (v: number) => v ? v.toFixed(4) : '-' },
    { title: 'R²', dataIndex: 'r2', key: 'r2', render: (v: number) => v ? v.toFixed(4) : '-' },
    {
      title: t('mm_col_actions'),
      key: 'action',
      render: (_: unknown, record: Model) => (
        <Space>
          <Button icon={<EyeOutlined />} size="small" onClick={() => { setSelectedModel(record); setDetailVisible(true); }}>{t('mm_action_detail')}</Button>
          <Button icon={<PlayCircleOutlined />} size="small" disabled={record.status === 'training'}>{t('mm_action_train')}</Button>
          <Button icon={<EditOutlined />} size="small">{t('mm_action_edit')}</Button>
          <Button icon={<DeleteOutlined />} size="small" danger onClick={() => handleDelete(record.id)}>{t('mm_action_delete')}</Button>
        </Space>
      ),
    },
  ];

  const handleDelete = (id: string) => {
    setModels(models.filter(m => m.id !== id));
    message.success(t('mm_msg_deleted'));
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setModels([...models, { ...values, id: Date.now().toString(), status: 'untrained', accuracy: 0, mse: 0, mae: 0, r2: 0, createdAt: new Date().toISOString() }]);
    setModalVisible(false);
    form.resetFields();
  };

  const performanceChartOption = {
    title: { text: t('mm_chart_title') },
    radar: {
      indicator: [
        { name: t('mm_col_accuracy'), max: 1 },
        { name: 'R²', max: 1 },
        { name: t('mm_radar_stability'), max: 1 },
        { name: t('mm_radar_speed'), max: 1 },
        { name: t('mm_radar_generalization'), max: 1 },
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
            {t('mm_btn_create')}
          </Button>
        }
      >
        <Table columns={columns} dataSource={models} rowKey="id" />
      </Card>

      <Modal title={t('mm_btn_create')} open={modalVisible} onOk={handleSave} onCancel={() => setModalVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('mm_field_name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label={t('mm_field_type')} rules={[{ required: true }]}>
            <Select>
              <Option value="LSTM">LSTM</Option>
              <Option value="RandomForest">RandomForest</Option>
              <Option value="XGBoost">XGBoost</Option>
              <Option value="LightGBM">LightGBM</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('mm_detail_title')} open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={800}>
        {selectedModel && (
          <>
            <p><strong>{t('mm_field_name')}:</strong> {selectedModel.name}</p>
            <p><strong>{t('mm_field_type')}:</strong> {selectedModel.type}</p>
            <p><strong>{t('mm_col_status')}:</strong> <Tag color={selectedModel.status === 'trained' ? 'success' : 'processing'}>{selectedModel.status}</Tag></p>
            {selectedModel.status === 'training' && <Progress percent={65} status="active" />}
            <EChart option={performanceChartOption} style={{ height: 400, marginTop: 20 }} />
          </>
        )}
      </Modal>
    </PageContainer>
  );
};

export default ModelManagement;
