/**
 * 基本设置模块
 * 功能：提供用户界面配置、主题设置、语言设置等基本功能
 */
import { Card, Form, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type { UserSettings } from './types';

interface BasicSettingsProps {
  settings: UserSettings;
  setSettings: React.Dispatch<React.SetStateAction<UserSettings>>;
  applyTheme: (theme: 'light' | 'dark' | 'auto') => void;
  i18n: any;
}

const BasicSettings = ({
  settings,
  setSettings,
  applyTheme,
  i18n
}: BasicSettingsProps) => {
  const { t } = useTranslation();
  const [basicForm] = Form.useForm();

  return (
    <div className="block">
      <Card className="settings-panel" title={t('basic_settings') || '基本设置'} variant="outlined">
        <Form
          form={basicForm}
          layout="vertical"
          initialValues={settings}
        >
          <Card size="small">
            <Form.Item
              label={t('theme') || '主题'}
              name="theme"
              rules={[{ required: true, message: t('please_select') || '请选择' }]}
            >
              <Select
                onChange={(value) => {
                  const themeValue = value as 'light' | 'dark' | 'auto';
                  setSettings(prev => ({ ...prev, theme: themeValue }));
                  applyTheme(themeValue);
                }}
                options={[
                  { value: 'light', label: t('light') || '亮色' },
                  { value: 'dark', label: t('dark') || '暗色' },
                  { value: 'auto', label: t('follow_system') || '跟随系统' }
                ]}
              />
            </Form.Item>
            <Form.Item
              label={t('language') || '语言'}
              name="language"
              rules={[{ required: true, message: t('please_select') || '请选择' }]}
            >
              <Select
                onChange={(value) => {
                  setSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }));
                  // 更新i18n语言
                  i18n.changeLanguage(value);
                }}
                options={[
                  { value: 'zh-CN', label: t('chinese') || '简体中文' },
                  { value: 'en-US', label: t('english') || 'English' }
                ]}
              />
            </Form.Item>

            <Form.Item
              label={t('timezone') || '时区'}
              name="timezone"
              rules={[{ required: true, message: t('please_select') || '请选择' }]}
            >
              <Select
                onChange={(value) => {
                  setSettings(prev => ({ ...prev, timezone: value }));
                }}
                options={[
                  { value: 'Asia/Shanghai', label: '上海 (UTC+8)' },
                  { value: 'UTC', label: 'UTC (UTC+0)' },
                  { value: 'Europe/London', label: '伦敦 (UTC+0)' },
                  { value: 'America/New_York', label: '纽约 (UTC-5)' },
                  { value: 'America/Los_Angeles', label: '洛杉矶 (UTC-8)' },
                  { value: 'Asia/Tokyo', label: '东京 (UTC+9)' },
                  { value: 'Asia/Hong_Kong', label: '香港 (UTC+8)' },
                  { value: 'Asia/Singapore', label: '新加坡 (UTC+8)' },
                  { value: 'Australia/Sydney', label: '悉尼 (UTC+10)' },
                  { value: 'Europe/Paris', label: '巴黎 (UTC+1)' },
                  { value: 'Europe/Berlin', label: '柏林 (UTC+1)' },
                  { value: 'America/Chicago', label: '芝加哥 (UTC-6)' }
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
