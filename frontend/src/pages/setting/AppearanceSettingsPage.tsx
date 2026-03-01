/**
 * 外观设置子页面
 * 功能：提供主题、语言、分页等外观设置
 * 参考：/Users/liupeng/workspace/certimate-main/ui/src/pages/settings/SettingsAppearance.tsx
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Divider, Form, type RadioChangeEvent, Select, Space, Button, Spin, message } from 'antd';
import { useSettings } from './SettingsContext';

// 主题图片路径
const THEME_IMAGES: Record<string, string> = {
  light: '/imgs/themes/light.png',
  dark: '/imgs/themes/dark.png',
  auto: '/imgs/themes/system.png',
};

// 主题选项
const THEME_OPTIONS = [
  { key: 'light', label: '浅色', image: THEME_IMAGES.light },
  { key: 'dark', label: '暗黑', image: THEME_IMAGES.dark },
  { key: 'auto', label: '自动', image: THEME_IMAGES.auto },
];

// 语言选项
const LANGUAGE_OPTIONS = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en-US', label: 'English' },
];

// 分页选项
const PER_PAGE_OPTIONS = [10, 15, 20, 30, 50, 100];

const AppearanceSettingsPage = () => {
  const { t, i18n } = useTranslation();
  const {
    userSettings,
    setUserSettings,
    loading,
    saving,
    saveConfig,
    resetConfig,
    applyTheme,
  } = useSettings();

  const [themeChanged, setThemeChanged] = useState(false);
  const [localeChanged, setLocaleChanged] = useState(false);

  // 处理主题变更
  const handleThemeChange = (e: RadioChangeEvent) => {
    const value = e.target.value as 'light' | 'dark' | 'auto';
    if (value !== userSettings.theme) {
      setThemeChanged(true);
      setUserSettings(prev => ({ ...prev, theme: value }));
      applyTheme(value);
      message.success(t('theme_changed') || '主题已切换');
    }
  };

  // 处理语言变更
  const handleLanguageChange = (value: string) => {
    if (value !== (i18n.resolvedLanguage ?? i18n.language)) {
      setLocaleChanged(true);
      setUserSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }));
      i18n.changeLanguage(value);
      message.success(t('language_changed') || '语言已切换');
    }
  };

  // 处理分页变更
  const handlePerPageChange = (value: number) => {
    setUserSettings(prev => ({ ...prev, defaultPerPage: value }));
  };

  // 保存配置
  const handleSave = async () => {
    await saveConfig();
    setThemeChanged(false);
    setLocaleChanged(false);
  };

  // 重置配置
  const handleReset = () => {
    resetConfig();
    i18n.changeLanguage('zh-CN');
    setThemeChanged(false);
    setLocaleChanged(false);
  };

  return (
    <Spin spinning={loading} tip={t('loading') || '加载中...'}>
      <div className="space-y-6">
        {/* 主题设置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('theme') || '主题'}</h2>
          <Form layout="vertical">
            <Form.Item
              extra={themeChanged ? t('theme_changed_hint') || '主题已更改，刷新页面后生效' : undefined}
            >
              <div className="flex gap-4 flex-wrap">
                {THEME_OPTIONS.map((item) => (
                  <div
                    key={item.key}
                    className={`relative flex-1 min-w-[120px] max-w-[200px] cursor-pointer overflow-hidden rounded-lg border border-solid transition-colors ${
                      userSettings.theme === item.key
                        ? 'border-blue-500 ring-2 ring-blue-500/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-blue-400'
                    }`}
                    onClick={() => handleThemeChange({ target: { value: item.key } } as RadioChangeEvent)}
                  >
                    {/* 主题预览图 */}
                    <div className="h-24 w-full overflow-hidden">
                      <img
                        src={item.image}
                        alt={item.label}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="p-3 bg-white dark:bg-gray-800 flex items-center gap-2">
                      <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                        userSettings.theme === item.key
                          ? 'border-blue-500 bg-blue-500'
                          : 'border-gray-300 dark:border-gray-600'
                      }`}>
                        {userSettings.theme === item.key && (
                          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      <span className={`text-sm font-medium ${
                        userSettings.theme === item.key ? 'text-blue-600 dark:text-blue-400' : ''
                      }`}>{item.label}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Form.Item>
          </Form>
        </div>

        <Divider />

        {/* 语言设置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('language') || '语言'}</h2>
          <Form layout="vertical">
            <Form.Item
              extra={localeChanged ? t('language_changed_hint') || '语言已更改' : undefined}
            >
              <Select
                value={userSettings.language}
                onChange={handleLanguageChange}
                options={LANGUAGE_OPTIONS}
                className="w-full max-w-md"
              />
            </Form.Item>
          </Form>
        </div>

        <Divider />

        {/* 分页设置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('pagination') || '分页'}</h2>
          <Form layout="vertical">
            <Form.Item label={t('default_per_page') || '列表页默认显示数量'}>
              <Select
                value={userSettings.defaultPerPage || 15}
                onChange={handlePerPageChange}
                options={PER_PAGE_OPTIONS.map((value) => ({
                  value,
                  label: `${value} ${t('per_page') || '条每页'}`,
                }))}
                className="w-full max-w-md"
              />
            </Form.Item>
          </Form>
        </div>

        {/* 操作按钮 */}
        <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Space>
            <Button onClick={handleReset} disabled={saving}>
              {t('reset') || '重置'}
            </Button>
            <Button type="primary" onClick={handleSave} loading={saving}>
              {t('save') || '保存'}
            </Button>
          </Space>
        </div>
      </div>
    </Spin>
  );
};

export default AppearanceSettingsPage;
