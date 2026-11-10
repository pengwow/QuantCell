import { useEffect } from 'react';
import { App as AntdApp, Form, Input, Modal } from 'antd';
import { modelApi, type UnifiedModelRow } from '@/api/modelApi';

interface RegisterModelModalProps {
  row: UnifiedModelRow | null; // 目标未注册文件行
  onClose: () => void;
  onSuccess: () => void;
}

export default function RegisterModelModal({ row, onClose, onSuccess }: RegisterModelModalProps) {
  const [form] = Form.useForm();
  const { message } = AntdApp.useApp();

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
      message.success('模型注册成功');
      form.resetFields();
      onSuccess();
    } catch (err) {
      message.error(`注册失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <Modal
      title={`注册模型 - ${row?.file_name ?? ''}`}
      open={!!row}
      onOk={handleOk}
      onCancel={onClose}
      okText="注册"
      cancelText="取消"
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="模型名称" rules={[{ required: true, message: '请输入模型名称' }]}>
          <Input placeholder="默认为文件名,可自定义" />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={3} placeholder="选填,训练背景/用途等" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
