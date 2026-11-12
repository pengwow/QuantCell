/**
 * 账户管理设置页
 * 功能：展示当前登录用户信息、修改密码、注销登录
 * 适用场景：前后端分离部署时，布局上不常驻用户菜单，用户相关功能收敛到系统设置中
 */
import { useState } from 'react';
import { App, Avatar, Button, Card, Descriptions, Form, Input, Modal, Popconfirm, Space, Tag } from 'antd';
import type { Rule } from 'antd/es/form';
import { useTranslation } from 'react-i18next';
import { IconLock, IconLogout, IconUser } from '@tabler/icons-react';
import { getAccessToken, removeToken } from '@/utils/tokenManager';
import { clearUserRoleInfo } from '@/utils/roleManager';

// 角色码 → 展示词条 key（文案经组件内 t() 取出，保持 i18n 单一事实源）
const ROLE_LABEL_KEYS: Record<string, string> = {
  admin: 'account_role_admin',
  user: 'account_role_user',
};

// 注销后需要清除的本地凭证（与登录时写入的字段一一对应）
const AUTH_STORAGE_KEYS = [
  'access_token',
  'refresh_token',
  'user_role',
  'is_guest',
  'username',
  'user_id',
  'nickname',
];

/** 读取当前登录用户信息（登录时由 LoginPage 写入 localStorage） */
const readAccountInfo = () => ({
  username: localStorage.getItem('username') || '-',
  nickname: localStorage.getItem('nickname') || '',
  userId: localStorage.getItem('user_id') || '-',
  role: localStorage.getItem('user_role') || 'user',
  isGuest: localStorage.getItem('is_guest') === 'true',
});

/** 清除全部本地登录态 */
const clearAllAuthData = () => {
  removeToken();
  AUTH_STORAGE_KEYS.forEach((key) => localStorage.removeItem(key));
  clearUserRoleInfo();
};

/** 调后端改密接口，失败抛异常（消息优先透传后端，请求非 JSON 响应时使用调用方传入的兜底文案） */
const changePasswordApi = async (oldPassword: string, newPassword: string, fallbackMsg: string) => {
  const token = getAccessToken();
  const res = await fetch('/api/v1/auth/change-password', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    let msg = fallbackMsg;
    try {
      const data = await res.json();
      msg = data?.detail || data?.message || msg;
    } catch {
      // 忽略，保留默认
    }
    throw new Error(msg);
  }
};

const AccountSettings = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loggingOut, setLoggingOut] = useState(false);
  const [pwdModalOpen, setPwdModalOpen] = useState(false);
  const [changingPwd, setChangingPwd] = useState(false);
  const account = readAccountInfo();

  // 改密表单校验规则
  const newPwdRules: Rule[] = [
    { required: true, message: t('account_new_password_required') },
    { min: 6, message: t('account_new_password_min_length', { min: 6 }) },
  ];

  // 改密提交：先让 antd Form 跑本地校验，再调后端（后端做最终校验+写 users 表）
  const handleChangePassword = async () => {
    try {
      const values = await form.validateFields();
      if (values.newPassword !== values.confirmPassword) {
        message.error(t('account_password_mismatch'));
        return;
      }
      if (values.newPassword === values.oldPassword) {
        message.error(t('account_password_same_as_old'));
        return;
      }
      setChangingPwd(true);
      await changePasswordApi(values.oldPassword, values.newPassword, t('account_change_password_failed'));
      form.resetFields();
      setPwdModalOpen(false);
      message.success(t('account_password_changed'));
    } catch (err) {
      // antd Form.validateFields 失败时抛出带 errorFields 的对象，UI 已自动展示错误；
      // 只有接口/运行时异常才需要额外 message 提示
      if (err instanceof Error) {
        message.error(err.message || t('account_change_password_failed'));
      }
    } finally {
      setChangingPwd(false);
    }
  };

  // 关闭弹窗时清空表单，避免下次打开残留旧输入
  const closePwdModal = () => {
    form.resetFields();
    setPwdModalOpen(false);
  };

  // 注销登录：后端为无状态 JWT，接口只做确认，关键是清除本地凭证并跳转登录页
  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      const token = getAccessToken();
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
    } catch {
      // 网络异常不阻断注销：本地凭证才是登录态的唯一来源，仍继续清除
    } finally {
      clearAllAuthData();
      setLoggingOut(false);
      message.success(t('account_logged_out'));
      // 整页跳转，确保内存中的用户状态随页面卸载一并清空
      window.location.href = '/login';
    }
  };

  return (
    // 垂直排列 antd Card 必须用 antd Space 而非 Tailwind space-y-*：
    // 后者依赖 margin-top，在 antd v5 CSS-in-JS 场景下会失效导致卡片紧贴
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      {/* 账户信息：用户名/昵称/角色/ID，全部只读 */}
      <Card title={t('account_info_title')}>
        <div className="flex items-center gap-4">
          <Avatar size={56} icon={<IconUser size={28} />} />
          <Descriptions column={1} size="small" className="flex-1">
            <Descriptions.Item label={t('username')}>{account.username}</Descriptions.Item>
            <Descriptions.Item label={t('account_nickname')}>{account.nickname || '-'}</Descriptions.Item>
            <Descriptions.Item label={t('account_role')}>
              <Tag color={account.role === 'admin' ? 'red' : 'blue'}>
                {ROLE_LABEL_KEYS[account.role] ? t(ROLE_LABEL_KEYS[account.role]) : account.role}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('account_user_id')}>{account.userId}</Descriptions.Item>
            <Descriptions.Item label={t('account_type')}>
              {account.isGuest ? <Tag>{t('account_guest')}</Tag> : <Tag color="green">{t('account_registered_user')}</Tag>}
            </Descriptions.Item>
          </Descriptions>
        </div>
      </Card>

      {/* 修改密码：入口按钮 + Modal 弹窗（账户安全类操作的业内标准交互） */}
      <Card title={t('account_security_title')}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">{t('account_login_password')}</span>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {t('account_security_hint')}
            </span>
          </div>
          <Button
            icon={<IconLock size="1em" />}
            onClick={() => setPwdModalOpen(true)}
            disabled={account.isGuest}
          >
            {account.isGuest ? t('account_guest_forbidden') : t('account_change_password')}
          </Button>
        </div>
      </Card>

      {/* 修改密码弹窗 */}
      <Modal
        title={t('account_change_password')}
        open={pwdModalOpen}
        onOk={handleChangePassword}
        onCancel={closePwdModal}
        okText={t('account_confirm_change')}
        cancelText={t('cancel')}
        confirmLoading={changingPwd}
        okButtonProps={{ danger: true }}
        destroyOnHidden
        mask={{ closable: false }}
      >
        <Form form={form} layout="vertical" className="mt-4" preserve={false}>
          <Form.Item
            label={t('account_old_password')}
            name="oldPassword"
            rules={[{ required: true, message: t('account_old_password_required') }]}
          >
            <Input.Password placeholder={t('account_current_password_placeholder')} autoComplete="current-password" />
          </Form.Item>
          <Form.Item label={t('account_new_password')} name="newPassword" rules={newPwdRules}>
            <Input.Password placeholder={t('account_new_password_placeholder')} autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label={t('account_confirm_new_password')}
            name="confirmPassword"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: t('account_confirm_password_required') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('account_password_mismatch')));
                },
              }),
            ]}
          >
            <Input.Password placeholder={t('account_confirm_password_placeholder')} autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 注销登录 */}
      <Card title={t('account_logout')}>
        <div className="flex items-center justify-between gap-4">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t('account_logout_hint')}
          </span>
          <Popconfirm
            title={t('account_logout_confirm_title')}
            description={t('account_logout_confirm_desc')}
            okText={t('logout')}
            okButtonProps={{ danger: true }}
            cancelText={t('cancel')}
            onConfirm={handleLogout}
          >
            <Button type="primary" danger icon={<IconLogout size="1em" />} loading={loggingOut}>
              {t('account_logout')}
            </Button>
          </Popconfirm>
        </div>
      </Card>
    </Space>
  );
};

export default AccountSettings;
