import { useEffect } from 'react';
import { App as AntdApp, Form, Input, Modal } from 'antd';
import { modelApi, type UnifiedModelRow } from '@/api/modelApi';
import { useTranslation } from 'react-i18next';

interface RegisterModelModalProps {
  row: UnifiedModelRow | null; // 目标未注册文件行
  onClose: () => void;
  onSuccess: () => void;
}

export default function RegisterModelModal({ row, onClose, onSuccess }: RegisterModelModalProps) {
  const [form] = Form.useForm();
  const { message } = AntdApp.useApp();
  const { t } = useTranslation();

  useEffect(() => {
    if (row) {
      // 默认名 = 文件 stem:与 seed 命名约定(注册名 == zip stem)一致,保证注册后能 join 回文件
      form.setFieldsValue({ name: row.file_name.replace(/\.zip$/, ''), description: '' });
    }
  }, [row, form]);

  const handleOk = async () => {
    if (!row?.path) return;
    const values = await form.validateFields();
    try {
      await modelApi.registerModel({
        name: values.name,
        model_path: row.path,
        metadata: {
          description: values.description || '',
          ...(row.algorithm && row.algorithm !== '-' ? { algorithm: row.algorithm } : {}),
          // model_path 写入 metadata 作为 join 锚点(来源路径)
          model_path: row.path,
        },
        metrics: {},
      });
      message.success(t('rmreg_msg_success'));
      form.resetFields();
      onSuccess();
    } catch (err) {
      message.error(t('rmreg_msg_failed', { msg: err instanceof Error ? err.message : String(err) }));
    }
  };

  return (
    <Modal
      title={t('rmreg_title', { name: row?.file_name ?? '' })}
      open={!!row}
      onOk={handleOk}
      onCancel={onClose}
      okText={t('rmreg_ok')}
      cancelText={t('rmreg_cancel')}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item name="name" label={t('rmreg_label_name')} rules={[{ required: true, message: t('rmreg_rule_name') }]}>
          <Input placeholder={t('rmreg_ph_name')} />
        </Form.Item>
        <Form.Item name="description" label={t('rmreg_label_desc')}>
          <Input.TextArea rows={3} placeholder={t('rmreg_ph_desc')} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
