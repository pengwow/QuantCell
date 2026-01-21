/**
 * 基本设置模块
 * 功能：提供用户界面配置、主题设置、语言设置等基本功能
 */
import React from 'react';
import { Card, Form, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type { UserSettings } from './types';

interface BasicSettingsProps {
  settings: UserSettings;
  setSettings: React.Dispatch<React.SetStateAction<UserSettings>>;
  applyTheme: (theme: 'light' | 'dark' | 'auto') => void;
  i18n: any;
}

const BasicSettings: React.FC<BasicSettingsProps> = ({
  settings,
  setSettings,
  applyTheme,
  i18n
}) => {
  const { t } = useTranslation();
  const [basicForm] = Form.useForm();

  return (
    <div style={{ display: 'block' }}>
      <Card className="settings-panel" title={t('basic_settings')} variant="outlined">
        <Form
          form={basicForm}
          layout="vertical"
          initialValues={settings}
        >
          <Card size="small">
            <Form.Item
              label={t('theme')}
              name="theme"
              rules={[{ required: true, message: t('please_select') }]}
            >
              <Select
                onChange={(value) => {
                  const themeValue = value as 'light' | 'dark' | 'auto';
                  setSettings(prev => ({ ...prev, theme: themeValue }));
                  applyTheme(themeValue);
                }}
                options={[
                  { value: 'light', label: t('light') },
                  { value: 'dark', label: t('dark') },
                  { value: 'auto', label: t('follow_system') }
                ]}
              />
            </Form.Item>
            <Form.Item
              label={t('language')}
              name="language"
              rules={[{ required: true, message: t('please_select') }]}
            >
              <Select
                onChange={(value) => {
                  setSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }));
                  // 更新i18n语言
                  i18n.changeLanguage(value);
                }}
                options={[
                  { value: 'zh-CN', label: t('chinese') },
                  { value: 'en-US', label: t('english') }
                ]}
              />
            </Form.Item>
          </Card>
        </Form>
      </Card>
    </div>
  );
};

export default BasicSettings;
