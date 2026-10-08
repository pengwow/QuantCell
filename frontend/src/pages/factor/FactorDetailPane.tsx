/**
 * 右栏因子详情：头部（生命周期/编辑/删除）+ 概览/分析/快照三页签。
 * 写操作（生命周期、编辑、删除、快照增删、分析完成）统一回调 onRefreshCatalog 刷新左栏。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App as AntApp,
  Button,
  Card,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tabs,
  Tag,
} from 'antd';
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import {
  factorApi,
  type FactorCatalogItem,
  type LifecycleStatus,
} from '@/api/factor';
import { NEXT_STATUS, STATUS_COLOR, factorSource } from './factorMeta';
import FactorOverviewPanel from './FactorOverviewPanel';
import FactorAnalyzePanel from './FactorAnalyzePanel';
import FactorSnapshotsPanel from './FactorSnapshotsPanel';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';

const FactorDetailPane: React.FC<{
  factor: FactorCatalogItem | null;
  onRefreshCatalog: () => void;
}> = ({ factor, onRefreshCatalog }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [tab, setTab] = useState<'overview' | 'analyze' | 'snapshots'>('overview');
  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [categorySaving, setCategorySaving] = useState(false);
  const [form] = Form.useForm<{ expression: string }>();

  if (!factor) {
    return (
      <Card>
        <Empty description={t('factor_detail_empty') || '请在左侧选择因子'} />
      </Card>
    );
  }

  const statusLabel = (s: LifecycleStatus) => t(`factor_status_${s.toLowerCase()}`) || s;

  const changeLifecycle = async (status: LifecycleStatus) => {
    try {
      await factorApi.updateLifecycle(factor!.name, status);
      message.success(t('factor_lib_toast_status_updated') || '状态已更新');
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
      onRefreshCatalog();
    }
  };

  const changeCategory = async (category: string) => {
    setCategorySaving(true);
    try {
      await factorApi.updateCategory(factor!.name, category);
      message.success(t('factor_lib_toast_category_updated') || '分类已更新');
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
      onRefreshCatalog();
    } finally {
      setCategorySaving(false);
    }
  };

  const openEdit = () => {
    form.setFieldsValue({ expression: factor!.expression });
    setEditOpen(true);
  };

  const submitEdit = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      await factorApi.add(factor!.name, v.expression.trim());
      message.success(t('factor_lib_toast_saved') || '因子已保存');
      setEditOpen(false);
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    try {
      await factorApi.remove(factor!.name);
      message.success(t('factor_lib_toast_deleted') || '已删除');
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const locked = factor.builtin || factor.lifecycle_status === 'RETIRED';

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card size="small">
        <Flex justify="space-between" align="center" wrap="wrap" gap="small">
          <Flex gap="small" align="center" wrap>
            <span style={{ fontSize: 16, fontWeight: 600 }}>{factor.label}</span>
            <span style={{ color: '#999' }}>{factor.name}</span>
            {factor.builtin && <Tag>{t('factor_lib_builtin') || '内置'}</Tag>}
            {factorSource(factor) === 'code' && <Tag color="magenta">{t('factor_lib_code') || '代码'}</Tag>}
            {factorSource(factor) === 'composite' && <Tag color="purple">{t('factor_lib_composite') || '合成'}</Tag>}
            {!factor.supported && <Tag color="error">{t('factor_lib_no_data') || '无数据'}</Tag>}
          </Flex>
          <Flex gap="small" align="center">
            {locked ? (
              <Tag color={STATUS_COLOR[factor.lifecycle_status]} style={{ marginInlineEnd: 0 }}>
                {statusLabel(factor.lifecycle_status)}
              </Tag>
            ) : (
              <Select
                size="small"
                style={{ width: 140 }}
                value={factor.lifecycle_status}
                onChange={changeLifecycle}
                options={[
                  { value: factor.lifecycle_status, label: statusLabel(factor.lifecycle_status), disabled: true },
                  ...NEXT_STATUS[factor.lifecycle_status].map((s) => ({ value: s, label: statusLabel(s) })),
                ]}
              />
            )}
            <Button size="small" icon={<EditOutlined />} disabled={factor.builtin} onClick={openEdit}>
              {t('factor_lib_edit') || '编辑'}
            </Button>
            <Popconfirm
              title={t('factor_lib_edit_confirm') || '删除该自定义因子？'}
              disabled={factor.builtin}
              onConfirm={remove}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={factor.builtin}>
                {t('factor_lib_delete') || '删除'}
              </Button>
            </Popconfirm>
          </Flex>
        </Flex>
      </Card>

      <Card
        styles={{ body: { paddingTop: 8 } }}
      >
        <Tabs
          activeKey={tab}
          onChange={(k) => setTab(k as typeof tab)}
          items={[
            {
              key: 'overview',
              label: t('factor_detail_tab_overview') || '概览',
              children: (
                <FactorOverviewPanel
                  factor={factor}
                  onGoAnalyze={() => setTab('analyze')}
                  onCategoryChange={changeCategory}
                  categorySaving={categorySaving}
                />
              ),
            },
            {
              key: 'analyze',
              label: t('factor_detail_tab_analyze') || '分析',
              children: <FactorAnalyzePanel factor={factor} onAnalyzed={onRefreshCatalog} />,
            },
            {
              key: 'snapshots',
              label: t('factor_detail_tab_snapshots') || '快照',
              children: <FactorSnapshotsPanel factor={factor} onChanged={onRefreshCatalog} />,
            },
          ]}
        />
      </Card>

      <Modal
        title={t('factor_lib_edit_modal', { name: factor.name }) || `编辑：${factor.name}`}
        open={editOpen}
        onOk={submitEdit}
        confirmLoading={saving}
        onCancel={() => setEditOpen(false)}
        okText={t('factor_lib_save') || '保存'}
        cancelText={t('factor_lib_cancel') || '取消'}
        destroyOnHidden
        mask={{ closable: false }}
      >
        <Form form={form} layout="vertical" preserve={false} className="mt-4">
          <Form.Item
            name="expression"
            label={t('factor_lib_form_expr') || '表达式'}
            extra={t('factor_lib_form_expr_hint') || ''}
            rules={[{ required: true, message: t('factor_lib_form_expr_req') || '请输入表达式' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default FactorDetailPane;
