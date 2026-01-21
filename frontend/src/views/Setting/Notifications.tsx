/**
 * 通知设置模块
 * 功能：提供邮件通知、Webhook 通知等通知相关配置
 */
import React from 'react';
import { Card, Form, Input, Switch, Typography } from 'antd';
import type { NotificationSettings } from './types';

interface NotificationsProps {
  notificationSettings: NotificationSettings;
  setNotificationSettings: React.Dispatch<React.SetStateAction<NotificationSettings>>;
}

const Notifications: React.FC<NotificationsProps> = ({
  notificationSettings,
  setNotificationSettings
}) => {
  const { Text } = Typography;
  const [notificationForm] = Form.useForm();

  return (
    <div style={{ display: 'block' }}>
      <Card className="settings-panel" title="通知设置" variant="outlined">
        <Form
          form={notificationForm}
          layout="vertical"
          initialValues={notificationSettings}
        >
          <Card size="small" style={{ marginBottom: 16 }}>
            <Form.Item
              name="enableEmail"
              valuePropName="checked"
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableEmail: checked }))}
                />
                <Text style={{ marginLeft: 8 }}>邮件通知</Text>
              </div>
            </Form.Item>
            <Form.Item
              name="enableWebhook"
              valuePropName="checked"
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableWebhook: checked }))}
                />
                <Text style={{ marginLeft: 8 }}>Webhook 通知</Text>
              </div>
            </Form.Item>
            {notificationSettings.enableWebhook && (
              <Form.Item
                label="Webhook URL"
                name="webhookUrl"
                rules={[{ required: true, message: '请输入 Webhook URL' }]}
              >
                <Input
                  placeholder="请输入 Webhook URL"
                  onChange={(e) => setNotificationSettings(prev => ({ ...prev, webhookUrl: e.target.value }))}
                />
              </Form.Item>
            )}
          </Card>
          <Card size="small">
            <Form.Item
              name="notifyOnAlert"
              valuePropName="checked"
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnAlert: checked }))}
                />
                <Text style={{ marginLeft: 8 }}>告警通知</Text>
              </div>
            </Form.Item>
            <Form.Item
              name="notifyOnTaskComplete"
              valuePropName="checked"
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnTaskComplete: checked }))}
                />
                <Text style={{ marginLeft: 8 }}>任务完成通知</Text>
              </div>
            </Form.Item>
            <Form.Item
              name="notifyOnSystemUpdate"
              valuePropName="checked"
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnSystemUpdate: checked }))}
                />
                <Text style={{ marginLeft: 8 }}>系统更新通知</Text>
              </div>
            </Form.Item>
          </Card>
        </Form>
      </Card>
    </div>
  );
};

export default Notifications;
