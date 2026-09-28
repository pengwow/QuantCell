/**
 * 账户管理设置页
 * 功能：展示当前登录用户信息、修改密码、注销登录
 * 适用场景：前后端分离部署时，布局上不常驻用户菜单，用户相关功能收敛到系统设置中
 */
import { useState } from 'react';
import { App, Avatar, Button, Card, Descriptions, Form, Input, Modal, Popconfirm, Space, Tag } from 'antd';
import type { Rule } from 'antd/es/form';
import { IconLock, IconLogout, IconUser } from '@tabler/icons-react';
import { getAccessToken, removeToken } from '@/utils/tokenManager';
import { clearUserRoleInfo } from '@/utils/roleManager';

// 角色码 → 中文展示
const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  user: '普通用户',
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

/** 调后端改密接口，失败抛异常（消息已从后端透传） */
const changePasswordApi = async (oldPassword: string, newPassword: string) => {
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
    let msg = '修改失败';
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
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loggingOut, setLoggingOut] = useState(false);
  const [pwdModalOpen, setPwdModalOpen] = useState(false);
  const [changingPwd, setChangingPwd] = useState(false);
  const account = readAccountInfo();

  // 改密表单校验规则
  const newPwdRules: Rule[] = [
    { required: true, message: '请输入新密码' },
    { min: 6, message: '新密码至少需要 6 个字符' },
  ];

  // 改密提交：先让 antd Form 跑本地校验，再调后端（后端做最终校验+写 users 表）
  const handleChangePassword = async () => {
    try {
      const values = await form.validateFields();
      if (values.newPassword !== values.confirmPassword) {
        message.error('两次输入的新密码不一致');
        return;
      }
      if (values.newPassword === values.oldPassword) {
        message.error('新密码不能与旧密码相同');
        return;
      }
      setChangingPwd(true);
      await changePasswordApi(values.oldPassword, values.newPassword);
      form.resetFields();
      setPwdModalOpen(false);
      message.success('密码修改成功');
    } catch (err) {
      // antd Form.validateFields 失败时抛出带 errorFields 的对象，UI 已自动展示错误；
      // 只有接口/运行时异常才需要额外 message 提示
      if (err instanceof Error) {
        message.error(err.message || '密码修改失败');
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
      message.success('已注销登录');
      // 整页跳转，确保内存中的用户状态随页面卸载一并清空
      window.location.href = '/login';
    }
  };

  return (
    // 垂直排列 antd Card 必须用 antd Space 而非 Tailwind space-y-*：
    // 后者依赖 margin-top，在 antd v5 CSS-in-JS 场景下会失效导致卡片紧贴
    <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
      {/* 账户信息：用户名/昵称/角色/ID，全部只读 */}
      <Card title="账户信息">
        <div className="flex items-center gap-4">
          <Avatar size={56} icon={<IconUser size={28} />} />
          <Descriptions column={1} size="small" className="flex-1">
            <Descriptions.Item label="用户名">{account.username}</Descriptions.Item>
            <Descriptions.Item label="昵称">{account.nickname || '-'}</Descriptions.Item>
            <Descriptions.Item label="角色">
              <Tag color={account.role === 'admin' ? 'red' : 'blue'}>
                {ROLE_LABELS[account.role] || account.role}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="用户 ID">{account.userId}</Descriptions.Item>
            <Descriptions.Item label="账户类型">
              {account.isGuest ? <Tag>访客</Tag> : <Tag color="green">注册用户</Tag>}
            </Descriptions.Item>
          </Descriptions>
        </div>
      </Card>

      {/* 修改密码：入口按钮 + Modal 弹窗（账户安全类操作的业内标准交互） */}
      <Card title="账户安全" extra={<IconLock size={18} />}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">登录密码</span>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              定期修改密码可提升账户安全，修改时需验证当前密码。
            </span>
          </div>
          <Button
            icon={<IconLock size="1em" />}
            onClick={() => setPwdModalOpen(true)}
            disabled={account.isGuest}
          >
            {account.isGuest ? '访客不可修改' : '修改密码'}
          </Button>
        </div>
      </Card>

      {/* 修改密码弹窗 */}
      <Modal
        title="修改密码"
        open={pwdModalOpen}
        onOk={handleChangePassword}
        onCancel={closePwdModal}
        okText="确认修改"
        cancelText="取消"
        confirmLoading={changingPwd}
        okButtonProps={{ danger: true }}
        destroyOnClose
        maskClosable={false}
      >
        <Form form={form} layout="vertical" className="mt-4" preserve={false}>
          <Form.Item label="旧密码" name="oldPassword" rules={[{ required: true, message: '请输入旧密码' }]}>
            <Input.Password placeholder="请输入当前密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item label="新密码" name="newPassword" rules={newPwdRules}>
            <Input.Password placeholder="请输入新密码（至少 6 个字符）" autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认新密码"
            name="confirmPassword"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的新密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password placeholder="请再次输入新密码" autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 注销登录 */}
      <Card title="注销登录">
        <div className="flex items-center justify-between gap-4">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            注销后将清除本机登录凭证并返回登录页，需要重新登录才能继续使用。
          </span>
          <Popconfirm
            title="确认注销登录？"
            description="当前登录态将被清除，未保存的数据请先保存。"
            okText="注销"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={handleLogout}
          >
            <Button type="primary" danger icon={<IconLogout size="1em" />} loading={loggingOut}>
              注销登录
            </Button>
          </Popconfirm>
        </div>
      </Card>
    </Space>
  );
};

export default AccountSettings;
