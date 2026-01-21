/**
 * API 设置模块
 * 功能：提供 API Key 管理和权限配置
 */
import React from 'react';
import { Card, Form, Input, Switch, Typography, Space, Button } from 'antd';
import { EyeInvisibleOutlined, EyeTwoTone, ReloadOutlined } from '@ant-design/icons';
import type { ApiSettings } from './types';

interface ApiSettingsProps {
  apiSettings: ApiSettings;
  setApiSettings: React.Dispatch<React.SetStateAction<ApiSettings>>;
  regenerateApiKey: () => void;
}

const ApiSettings: React.FC<ApiSettingsProps> = ({
  apiSettings,
  setApiSettings,
  regenerateApiKey
}) => {
  const { Text } = Typography;
  const [apiForm] = Form.useForm();

  const togglePermission = (permissionId: string) => {
    setApiSettings(prev => ({
      ...prev,
      permissions: prev.permissions.map(permission => {
        if (permission.id === permissionId) {
          return {
            ...permission,
            enabled: !permission.enabled
          };
        }
        return permission;
      })
    }));
  };

  return (
    <div style={{ display: 'block' }}>
      <Card className="settings-panel" title="API 配置" variant="outlined">
        <Form
          form={apiForm}
          layout="vertical"
          initialValues={apiSettings}
        >
          <Card size="small" style={{ marginBottom: 16 }}>
            <Form.Item
              label="API Key"
              name="apiKey"
              rules={[{ required: true, message: 'API Key 不能为空' }]}
            >
              <Input.Password
                placeholder="API Key"
                disabled
                iconRender={(visible) => (visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />)}
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button
                  type="default"
                  onClick={regenerateApiKey}
                  icon={<ReloadOutlined />}
                >
                  重新生成
                </Button>
                <Text type="secondary">
                  API Key 用于调用系统 API。请妥善保管，避免泄露。
                </Text>
              </Space>
            </Form.Item>
          </Card>
          <Card size="small">
            {apiSettings.permissions.map(permission => (
              <Form.Item key={permission.id} name={permission.id} noStyle>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <div>
                    <h4 style={{ margin: '0 0 4px 0' }}>{permission.name}</h4>
                    <Text type="secondary" style={{ fontSize: '12px' }}>{permission.description}</Text>
                  </div>
                  <Switch
                    checked={permission.enabled}
                    checkedChildren="启用"
                    unCheckedChildren="禁用"
                    onChange={() => togglePermission(permission.id)}
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
