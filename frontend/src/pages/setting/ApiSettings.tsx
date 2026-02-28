/**
 * API设置模块
 * 功能：提供 API Key 管理和权限配置
 */
import { Card, Form, Input, Button, Switch, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ApiSettings as ApiSettingsType } from './types';

interface ApiSettingsProps {
  apiSettings: ApiSettingsType;
  setApiSettings: React.Dispatch<React.SetStateAction<ApiSettingsType>>;
}

const ApiSettings = ({
  apiSettings,
  setApiSettings
}: ApiSettingsProps) => {
  const { Text } = Typography;
  const [apiForm] = Form.useForm();

  // 重新生成 API Key
  const regenerateApiKey = () => {
    // 生成新的 API Key
    const newApiKey = Array.from({ length: 32 }, () =>
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[Math.floor(Math.random() * 62)]
    ).join('');

    setApiSettings(prev => ({ ...prev, apiKey: newApiKey }));
    message.success('API Key 已重新生成');
  };

  // 切换权限
  const togglePermission = (permissionId: string, enabled: boolean) => {
    setApiSettings(prev => ({
      ...prev,
      permissions: prev.permissions.map(permission =>
        permission.id === permissionId ? { ...permission, enabled } : permission
      )
    }));
  };

  return (
    <div className="block">
      <Card className="settings-panel" title="API 设置" variant="outlined">
        <Form
          form={apiForm}
          layout="vertical"
          initialValues={apiSettings}
        >
          <Card size="small" className="mb-4">
            <Form.Item
              label="API Key"
              name="apiKey"
            >
              <div className="flex items-center">
                <Input.Password
                  value={apiSettings.apiKey}
                  readOnly
                  className="flex-1"
                />
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  onClick={regenerateApiKey}
                  className="ml-2"
                >
                  重新生成
                </Button>
              </div>
            </Form.Item>
          </Card>
          <Card size="small">
            <Text className="block mb-4 font-medium">API 权限</Text>
            {apiSettings.permissions.map(permission => (
              <Form.Item
                key={permission.id}
                name={['permissions', permission.id]}
                valuePropName="checked"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <Text className="font-medium">{permission.name}</Text>
                    <Text type="secondary" className="block text-sm">
                      {permission.description}
                    </Text>
                  </div>
                  <Switch
                    checked={permission.enabled}
                    checkedChildren="启用"
                    unCheckedChildren="禁用"
                    onChange={(checked) => togglePermission(permission.id, checked)}
                  />
                </div>
              </Form.Item>
            ))}
          </Card>
        </Form>
      </Card>
    </div>
  );
};

export default ApiSettings;
