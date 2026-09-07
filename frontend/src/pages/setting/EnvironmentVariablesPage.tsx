/**
 * 环境变量设置页面
 * 管理系统的环境变量配置，以 key-value 格式存储
 */
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Space,
  App,
  Popconfirm,
  Spin,
  Switch,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { envVarApi } from '../../api';
import type { EnvVariable, EnvVariableListResponse } from './types';

/**
 * 归一化 getList 返回的数据结构（兼容 { data: { items } } 与直接 { items } 两种响应形态）
 */
const toEnvListItems = (result: unknown): EnvVariable[] => {
  const direct = result as EnvVariableListResponse | undefined;
  if (direct?.items) return direct.items;
  const wrapped = result as { data?: EnvVariableListResponse } | undefined;
  return wrapped?.data?.items ?? [];
};

const EnvironmentVariablesPage = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dataSource, setDataSource] = useState<EnvVariable[]>([]);
  const [editingRecord, setEditingRecord] = useState<EnvVariable | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();

  const loadEnvVars = useCallback(async () => {
    setLoading(true);
    try {
      const result = await envVarApi.getList();
      const items = toEnvListItems(result);
      setDataSource(items);
    } catch {
      message.error(t('load_env_vars_failed'));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    loadEnvVars();
  }, [loadEnvVars]);

  const openAddModal = () => {
    setEditingRecord(null);
    form.resetFields();
    setModalVisible(true);
  };

  const openEditModal = (record: EnvVariable) => {
    setEditingRecord(record);
    form.setFieldsValue({
      key: record.key,
      value: record.is_sensitive ? '' : record.value || '',
      description: record.description || '',
      is_sensitive: record.is_sensitive,
    });
    setModalVisible(true);
  };

  const handleDelete = async (key: string) => {
    try {
      await envVarApi.delete(key);
      message.success(t('delete_success'));
      loadEnvVars();
    } catch {
      message.error(t('delete_failed'));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      const currentItems = [...dataSource];
      const newItem: EnvVariable = {
        key: values.key,
        value: values.value || '',
        description: values.description || '',
        is_sensitive: editingRecord
          ? editingRecord.is_sensitive
          : (values.is_sensitive || false),
      };

      if (editingRecord) {
        const idx = currentItems.findIndex((item) => item.key === editingRecord.key);
        if (idx !== -1) {
          currentItems[idx] = newItem;
        }
        await envVarApi.save(currentItems);
      } else {
        currentItems.push(newItem);
        await envVarApi.save(currentItems);
      }

      message.success(t('save_env_vars_success'));
      setModalVisible(false);
      loadEnvVars();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return;
      }
      message.error(t('save_env_vars_failed'));
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<EnvVariable> = [
    {
      title: t('env_var_key'),
      dataIndex: 'key',
      key: 'key',
      ellipsis: true,
    },
    {
      title: t('env_var_value'),
      dataIndex: 'value',
      key: 'value',
      ellipsis: true,
      render: (_: string, record: EnvVariable) => {
        if (record.is_sensitive) {
          return '******';
        }
        return record.value || '-';
      },
    },
    {
      title: t('description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: t('actions') || t('action'),
      key: 'actions',
      width: 160,
      align: 'center',
      render: (_: unknown, record: EnvVariable) => (
        <Space size="small" onClick={(e) => e.stopPropagation()}>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={(e) => { e.stopPropagation(); openEditModal(record); }}
          >
            {t('edit')}
          </Button>
          <Popconfirm
            title={t('confirm_delete_env_var')}
            onConfirm={() => handleDelete(record.key)}
            okText={t('ok') || t('confirm')}
            cancelText={t('cancel')}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => e.stopPropagation()}
            >
              {t('delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Spin spinning={loading}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium m-0">
            {t('env_variables')}
          </h2>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
            {t('add')}
          </Button>
        </div>

        <Table
          columns={columns}
          dataSource={dataSource.map((item) => ({ ...item, _key: item.key }))}
          rowKey="_key"
          pagination={false}
          size="middle"
          onRow={(record: EnvVariable) => ({
            onClick: () => openEditModal(record),
            style: { cursor: 'pointer' },
          })}
          locale={{
            emptyText: t('no_env_vars'),
          }}
        />

        <Modal
          title={
            editingRecord
              ? t('edit_env_var')
              : t('add_env_var')
          }
          open={modalVisible}
          onOk={handleSubmit}
          onCancel={() => setModalVisible(false)}
          confirmLoading={saving}
          okText={t('save')}
          cancelText={t('cancel')}
        >
          <Form
            form={form}
            layout="vertical"
          >
            <Form.Item
              name="key"
              label={t('env_var_key')}
              rules={[
                { required: true, message: t('please_input_key') },
                {
                  pattern: /^[A-Za-z_][A-Za-z0-9_]*$/,
                  message: t('invalid_key_format'),
                },
              ]}
            >
              <Input placeholder="DATABASE_URL" disabled={!!editingRecord} />
            </Form.Item>

            <Form.Item
              name="value"
              label={t('env_var_value')}
              rules={[{ required: true, message: t('please_input_value') }]}
            >
              <Input placeholder={t('enter_value')} />
            </Form.Item>

            <Form.Item
              name="description"
              label={t('description')}
            >
              <Input.TextArea
                rows={2}
                placeholder={t('enter_description')}
              />
            </Form.Item>

            <Form.Item
              name="is_sensitive"
              label={t('is_sensitive')}
              valuePropName="checked"
              initialValue={false}
            >
              <Switch disabled={!!editingRecord} />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </Spin>
  );
};

export default EnvironmentVariablesPage;