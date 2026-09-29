import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  type TableColumnsType,
} from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { factorApi, type FactorDetail } from '@/api/factor';

const CATEGORY_COLOR: Record<string, string> = {
  price: 'blue',
  momentum: 'green',
  volatility: 'orange',
  volume_price: 'cyan',
  technical: 'purple',
  fundamental: 'default',
  custom: 'geekblue',
};

/** 拦截器 reject 的错误文案统一取 message */
const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';

const FactorLibrary: React.FC = () => {
  const [data, setData] = useState<FactorDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<FactorDetail | null>(null);
  const [form] = Form.useForm<{ factor_name: string; expression: string }>();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData((await factorApi.listDetail()).factors);
    } catch (e) {
      message.error(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setOpen(true);
  };

  const openEdit = (r: FactorDetail) => {
    setEditing(r);
    form.setFieldsValue({ factor_name: r.name, expression: r.expression });
    setOpen(true);
  };

  const submit = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      // 编辑自定义因子本质是同名 upsert；内置因子在按钮层已禁用
      await factorApi.add(v.factor_name.trim(), v.expression.trim());
      message.success('因子已保存');
      setOpen(false);
      refresh();
    } catch (e) {
      message.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (r: FactorDetail) => {
    try {
      await factorApi.remove(r.name);
      message.success('已删除');
      refresh();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const columns: TableColumnsType<FactorDetail> = [
    {
      title: '因子',
      dataIndex: 'label',
      render: (_, r) => (
        <Space>
          {r.label}
          {r.builtin && <Tag>内置</Tag>}
          {!r.supported && <Tag color="error">无数据</Tag>}
        </Space>
      ),
    },
    { title: '名称', dataIndex: 'name' },
    {
      title: '分类',
      dataIndex: 'category',
      render: (c: string) => <Tag color={CATEGORY_COLOR[c] ?? 'default'}>{c}</Tag>,
    },
    {
      title: '表达式',
      dataIndex: 'expression',
      render: (e: string) => <code style={{ fontSize: 12 }}>{e || '—'}</code>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, r) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} disabled={r.builtin} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Popconfirm title="删除该自定义因子？" disabled={r.builtin} onConfirm={() => remove(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.builtin}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="因子库"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建因子
        </Button>
      }
    >
      {/* 因子总量仅数十个，单页全展示，避免新建的自定义因子因排序靠后落在末页看不到 */}
      <Table rowKey="name" loading={loading} dataSource={data} columns={columns} pagination={{ pageSize: 100 }} />
      <Modal
        title={editing ? `编辑：${editing.name}` : '新建因子'}
        open={open}
        onOk={submit}
        confirmLoading={saving}
        onCancel={() => setOpen(false)}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        maskClosable={false}
      >
        <Form form={form} layout="vertical" preserve={false} className="mt-4">
          <Form.Item
            name="factor_name"
            label="因子名称（英文标识）"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如 my_momentum" disabled={!!editing} />
          </Form.Item>
          <Form.Item
            name="expression"
            label="表达式"
            extra="列：open/high/low/close/volume/quote_volume/vwap/amount；函数：Ref/MA/Std/RSI/MACD/KDJ/BBANDS；支持四则运算"
            rules={[{ required: true, message: '请输入表达式' }]}
          >
            <Input.TextArea rows={3} placeholder="如 close / Ref(close, 5) - 1" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default FactorLibrary;
