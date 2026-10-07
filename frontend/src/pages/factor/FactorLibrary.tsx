import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  llm_code: 'magenta',
  llm_composite: 'purple',
};

const STATUS_COLOR: Record<LifecycleStatus, string> = {
  DISCOVERED: 'default',
  INSPECTED: 'blue',
  PAPER_TRADING: 'gold',
  LIVE: 'green',
  RETIRED: 'red',
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
  const { t } = useTranslation();
  const [data, setData] = useState<FactorCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<FactorDetail | null>(null);
  const [snapshotFactor, setSnapshotFactor] = useState<string | null>(null);
  const [form] = Form.useForm<{ factor_name: string; expression: string }>();

  const statusLabel = (s: LifecycleStatus) =>
    t(`factor_status_${s.toLowerCase()}`) || s;

  const categoryLabel = (c: string) => {
    const key = `factor_lib_cat_${c}`;
    const translated = t(key);
    return translated === key ? c : translated;
  };

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
      message.success(t('factor_lib_toast_saved') || '因子已保存');
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
      message.success(t('factor_lib_toast_deleted') || '已删除');
      refresh();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const changeLifecycle = async (r: FactorCatalogItem, status: LifecycleStatus) => {
    try {
      await factorApi.updateLifecycle(r.name, status);
      message.success(t('factor_lib_toast_status_updated') || '状态已更新');
      refresh();
    } catch (e) {
      // 失败时提示并刷新，Select 受控值随档案数据还原
      message.error(errMsg(e));
      refresh();
    }
  };

  const columns: TableColumnsType<FactorCatalogItem> = [
    {
      title: t('factor_lib_col_factor') || '因子',
      dataIndex: 'label',
      render: (_, r) => (
        <Space>
          {r.label}
          {r.builtin && <Tag>{t('factor_lib_builtin') || '内置'}</Tag>}
          {/* 档案接口未回 kind：kind==='code' 的代码因子持久化 category 恒为 llm_code */}
          {(r.kind === 'code' || r.category === 'llm_code') && (
            <Tag color="magenta">{t('factor_lib_code') || '代码'}</Tag>
          )}
          {(r.kind === 'composite' || r.category === 'llm_composite') && (
            <Tag color="purple">{t('factor_lib_composite') || '合成'}</Tag>
          )}
          {!r.supported && <Tag color="error">{t('factor_lib_no_data') || '无数据'}</Tag>}
        </Space>
      ),
    },
    { title: t('factor_lib_col_name') || '名称', dataIndex: 'name' },
    {
      title: t('factor_lib_col_category') || '分类',
      dataIndex: 'category',
      render: (c: string) => (
        <Tag color={CATEGORY_COLOR[c] ?? 'default'}>{categoryLabel(c)}</Tag>
      ),
    },
    {
      title: t('factor_lib_col_status') || '状态',
      dataIndex: 'lifecycle_status',
      width: 110,
      render: (s: LifecycleStatus) => <Tag color={STATUS_COLOR[s]}>{statusLabel(s)}</Tag>,
    },
    {
      title: t('factor_lib_col_last_ic') || '最近 IC/IR',
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
      title: t('factor_lib_col_expr') || '表达式',
      dataIndex: 'expression',
      render: (e: string) => <code style={{ fontSize: 12 }}>{e || '—'}</code>,
    },
    {
      title: t('factor_lib_col_action') || '操作',
      key: 'action',
      width: 380,
      render: (_, r) => (
        <Space size="small" wrap>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => setSnapshotFactor(r.name)}>
            {t('factor_lib_snapshot') || '快照'}
            {r.snapshot_count > 0 ? ` (${r.snapshot_count})` : ''}
          </Button>
          {!r.builtin && r.lifecycle_status !== 'RETIRED' && (
            <Select
              size="small"
              style={{ width: 130 }}
              value={r.lifecycle_status}
              onChange={(v) => changeLifecycle(r, v)}
              options={[
                { value: r.lifecycle_status, label: statusLabel(r.lifecycle_status), disabled: true },
                ...NEXT_STATUS[r.lifecycle_status].map((s) => ({
                  value: s,
                  label: statusLabel(s),
                })),
              ]}
            />
          )}
          <Button size="small" icon={<EditOutlined />} disabled={r.builtin} onClick={() => openEdit(r)}>
            {t('factor_lib_edit') || '编辑'}
          </Button>
          <Popconfirm
            title={t('factor_lib_edit_confirm') || '删除该自定义因子？'}
            disabled={r.builtin}
            onConfirm={() => remove(r)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.builtin}>
              {t('factor_lib_delete') || '删除'}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={t('factor_lib_card_title') || '因子库'}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {t('factor_lib_create_btn') || '新建因子'}
        </Button>
      }
    >
      {/* 因子总量仅数十个，单页全展示，避免新建的自定义因子因排序靠后落在末页看不到 */}
      <Table rowKey="name" loading={loading} dataSource={data} columns={columns} pagination={{ pageSize: 100 }} />
      <Modal
        title={
          editing
            ? t('factor_lib_edit_modal', { name: editing.name }) || `编辑：${editing.name}`
            : t('factor_lib_create_modal') || '新建因子'
        }
        open={open}
        onOk={submit}
        confirmLoading={saving}
        onCancel={() => setOpen(false)}
        okText={t('factor_lib_save') || '保存'}
        cancelText={t('factor_lib_cancel') || '取消'}
        destroyOnClose
        maskClosable={false}
      >
        <Form form={form} layout="vertical" preserve={false} className="mt-4">
          <Form.Item
            name="factor_name"
            label={t('factor_lib_form_name') || '因子名称（英文标识）'}
            rules={[{ required: true, message: t('factor_lib_form_name_req') || '请输入名称' }]}
          >
            <Input
              placeholder={t('factor_lib_form_name_ph') || '如 my_momentum'}
              disabled={!!editing}
            />
          </Form.Item>
          <Form.Item
            name="expression"
            label={t('factor_lib_form_expr') || '表达式'}
            extra={
              t('factor_lib_form_expr_hint') ||
              '列：open/high/low/close/volume/quote_volume/vwap/amount；时序函数：Ref/MA/Std/RSI/MACD/KDJ/BBANDS；截面函数（需多品种）：cs_rank(表达式)/cs_zscore(表达式)；支持四则运算与嵌套，如 MA(cs_rank(close-open),5)'
            }
            rules={[{ required: true, message: t('factor_lib_form_expr_req') || '请输入表达式' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('factor_lib_form_expr_ph') || '如 close / Ref(close, 5) - 1'}
            />
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
