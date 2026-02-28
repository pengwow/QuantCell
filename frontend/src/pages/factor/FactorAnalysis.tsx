/**
 * 因子分析页面
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
  message,
  Tabs,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import PageContainer from '@/components/PageContainer';

const { Option } = Select;
const { TabPane } = Tabs;

interface Factor {
  id: string;
  name: string;
  expression: string;
  description: string;
  category: string;
  status: 'active' | 'inactive';
}

const FactorAnalysis = () => {
  const { t } = useTranslation();
  const [factors, setFactors] = useState<Factor[]>([
    { id: '1', name: 'PE', expression: 'close / eps', description: '市盈率', category: '估值', status: 'active' },
    { id: '2', name: 'PB', expression: 'close / bps', description: '市净率', category: '估值', status: 'active' },
    { id: '3', name: 'ROE', expression: 'net_profit / equity', description: '净资产收益率', category: '质量', status: 'active' },
  ]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingFactor, setEditingFactor] = useState<Factor | null>(null);
  const [form] = Form.useForm();

  const columns = [
    { title: '因子名称', dataIndex: 'name', key: 'name' },
    { title: '表达式', dataIndex: 'expression', key: 'expression' },
    { title: '描述', dataIndex: 'description', key: 'description' },
    { title: '分类', dataIndex: 'category', key: 'category' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'active' ? 'success' : 'default'}>
          {status === 'active' ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Factor) => (
        <Space>
          <Button icon={<PlayCircleOutlined />} size="small">计算</Button>
          <Button icon={<EditOutlined />} size="small" onClick={() => handleEdit(record)}>编辑</Button>
          <Button icon={<DeleteOutlined />} size="small" danger onClick={() => handleDelete(record.id)}>删除</Button>
        </Space>
      ),
    },
  ];

  const handleEdit = (factor: Factor) => {
    setEditingFactor(factor);
    form.setFieldsValue(factor);
    setModalVisible(true);
  };

  const handleDelete = (id: string) => {
    setFactors(factors.filter(f => f.id !== id));
    message.success('删除成功');
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    if (editingFactor) {
      setFactors(factors.map(f => f.id === editingFactor.id ? { ...f, ...values } : f));
    } else {
      setFactors([...factors, { ...values, id: Date.now().toString() }]);
    }
    setModalVisible(false);
    setEditingFactor(null);
    form.resetFields();
  };

  const icChartOption = {
    title: { text: 'IC分析' },
    xAxis: { type: 'category', data: ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05'] },
    yAxis: { type: 'value' },
    series: [{ data: [0.05, 0.08, 0.03, 0.06, 0.04], type: 'bar' }],
  };

  return (
    <PageContainer title={t('factor_analysis')}>
      <Card
        title={t('factor_analysis')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            新建因子
          </Button>
        }
      >
        <Tabs defaultActiveKey="list">
          <TabPane tab="因子列表" key="list">
            <Table columns={columns} dataSource={factors} rowKey="id" />
          </TabPane>
          <TabPane tab="IC分析" key="ic">
            <ReactECharts option={icChartOption} style={{ height: 400 }} />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title={editingFactor ? '编辑因子' : '新建因子'}
        open={modalVisible}
        onOk={handleSave}
        onCancel={() => { setModalVisible(false); setEditingFactor(null); form.resetFields(); }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="因子名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="expression" label="表达式" rules={[{ required: true }]}>
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true }]}>
            <Select>
              <Option value="估值">估值</Option>
              <Option value="质量">质量</Option>
              <Option value="动量">动量</Option>
              <Option value="波动">波动</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
};

export default FactorAnalysis;
