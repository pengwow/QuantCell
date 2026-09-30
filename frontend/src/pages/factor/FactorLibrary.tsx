import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  type TableColumnsType,
} from 'antd';
import { DeleteOutlined, EditOutlined, HistoryOutlined, PlusOutlined } from '@ant-design/icons';
import {
  factorApi,
  type FactorCatalogItem,
  type FactorDetail,
  type LifecycleStatus,
} from '@/api/factor';
import FactorSnapshotsModal from './FactorSnapshotsModal';

const CATEGORY_COLOR: Record<string, string> = {
  price: 'blue',
  momentum: 'green',
  volatility: 'orange',
  volume_price: 'cyan',
  technical: 'purple',
  fundamental: 'default',
  custom: 'geekblue',
};

const STATUS_COLOR: Record<LifecycleStatus, string> = {
  DISCOVERED: 'default',
  INSPECTED: 'blue',
  PAPER_TRADING: 'gold',
  LIVE: 'green',
  RETIRED: 'red',
};

const STATUS_LABEL: Record<LifecycleStatus, string> = {
  DISCOVERED: '已发现',
  INSPECTED: '已验证',
  PAPER_TRADING: '纸面交易',
  LIVE: '实盘',
  RETIRED: '已退役',
};

/** 合法的下一状态（与后端 LIFECYCLE_TRANSITIONS 保持一致） */
const NEXT_STATUS: Record<LifecycleStatus, LifecycleStatus[]> = {
  DISCOVERED: ['INSPECTED', 'RETIRED'],
  INSPECTED: ['DISCOVERED', 'PAPER_TRADING', 'RETIRED'],
  PAPER_TRADING: ['INSPECTED', 'LIVE', 'RETIRED'],
  LIVE: ['PAPER_TRADING', 'RETIRED'],
  RETIRED: [],
};

/** 拦截器 reject 的错误文案统一取 message */
const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';
const num = (v: number | null | undefined, digits = 3) =>
  v === null || v === undefined ? '—' : v.toFixed(digits);

const FactorLibrary: React.FC = () => {
  const [data, setData] = useState<FactorCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<FactorDetail | null>(null);
  const [snapshotFactor, setSnapshotFactor] = useState<string | null>(null);
  const [form] = Form.useForm<{ factor_name: string; expression: string }>();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData((await factorApi.catalog()).factors);
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

  const changeLifecycle = async (r: FactorCatalogItem, status: LifecycleStatus) => {
    try {
      await factorApi.updateLifecycle(r.name, status);
      message.success('状态已更新');
      refresh();
    } catch (e) {
      // 失败时提示并刷新，Select 受控值随档案数据还原
      message.error(errMsg(e));
      refresh();
    }
  };

  const columns: TableColumnsType<FactorCatalogItem> = [
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
      title: '状态',
      dataIndex: 'lifecycle_status',
      width: 110,
      render: (s: LifecycleStatus) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag>,
    },
    {
      title: '最近 IC/IR',
      key: 'last_ic_ir',
      width: 130,
      render: (_, r) =>
        r.last_metrics ? (
          <Space size={4}>
            <span>{num(r.last_metrics.ic_mean)}</span>
            <span>/</span>
            <span>{num(r.last_metrics.ic_ir)}</span>
          </Space>
        ) : (
          '—'
        ),
    },
    {
      title: '表达式',
      dataIndex: 'expression',
      render: (e: string) => <code style={{ fontSize: 12 }}>{e || '—'}</code>,
    },
    {
      title: '操作',
      key: 'action',
      width: 380,
      render: (_, r) => (
        <Space size="small" wrap>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => setSnapshotFactor(r.name)}>
            快照{r.snapshot_count > 0 ? ` (${r.snapshot_count})` : ''}
          </Button>
          {!r.builtin && r.lifecycle_status !== 'RETIRED' && (
            <Select
              size="small"
              style={{ width: 130 }}
              value={r.lifecycle_status}
              onChange={(v) => changeLifecycle(r, v)}
              options={[
                { value: r.lifecycle_status, label: STATUS_LABEL[r.lifecycle_status], disabled: true },
                ...NEXT_STATUS[r.lifecycle_status].map((s) => ({
                  value: s,
                  label: STATUS_LABEL[s],
                })),
              ]}
            />
          )}
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
            extra="列：open/high/low/close/volume/quote_volume/vwap/amount；时序函数：Ref/MA/Std/RSI/MACD/KDJ/BBANDS；截面函数（需多品种）：cs_rank(表达式)/cs_zscore(表达式)；支持四则运算与嵌套，如 MA(cs_rank(close-open),5)"
            rules={[{ required: true, message: '请输入表达式' }]}
          >
            <Input.TextArea rows={3} placeholder="如 close / Ref(close, 5) - 1" />
          </Form.Item>
        </Form>
      </Modal>
      <FactorSnapshotsModal
        factorName={snapshotFactor ?? ''}
        open={!!snapshotFactor}
        onClose={() => setSnapshotFactor(null)}
      />
    </Card>
  );
};

export default FactorLibrary;
