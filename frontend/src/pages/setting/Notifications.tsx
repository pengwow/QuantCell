/**
 * 通知设置模块
 * 功能：提供邮件通知、Webhook 通知等通知相关配置
 */
import { Card, Form, Input, Switch, Typography } from 'antd';
import type { NotificationSettings } from './types';

interface NotificationsProps {
  notificationSettings: NotificationSettings;
  setNotificationSettings: React.Dispatch<React.SetStateAction<NotificationSettings>>;
}

const Notifications = ({
  notificationSettings,
  setNotificationSettings
}: NotificationsProps) => {
  const { Text } = Typography;
  const [notificationForm] = Form.useForm();

  return (
    <div className="block">
      <Card className="settings-panel" title="通知设置" variant="outlined">
        <Form
          form={notificationForm}
          layout="vertical"
          initialValues={notificationSettings}
        >
          <Card size="small" className="mb-4">
            <Form.Item
              name="enableEmail"
              valuePropName="checked"
            >
              <div className="flex items-center">
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableEmail: checked }))}
                />
                <Text className="ml-2">邮件通知</Text>
              </div>
            </Form.Item>
            <Form.Item
              name="enableWebhook"
              valuePropName="checked"
            >
              <div className="flex items-center">
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableWebhook: checked }))}
                />
                <Text className="ml-2">Webhook 通知</Text>
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
              <div className="flex items-center">
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnAlert: checked }))}
                />
                <Text className="ml-2">告警通知</Text>
              </div>
            </Form.Item>
            <Form.Item
              name="notifyOnTaskComplete"
              valuePropName="checked"
            >
              <div className="flex items-center">
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnTaskComplete: checked }))}
                />
                <Text className="ml-2">任务完成通知</Text>
              </div>
            </Form.Item>
            <Form.Item
              name="notifyOnSystemUpdate"
              valuePropName="checked"
            >
              <div className="flex items-center">
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnSystemUpdate: checked }))}
                />
                <Text className="ml-2">系统更新通知</Text>
              </div>
            </Form.Item>
          </Card>
        </Form>
      </Card>
    </div>
  );
};

export default Notifications;
