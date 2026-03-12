/**
 * 通用设置子页面
 * 功能：提供主题、语言、分页等通用设置
 * 参考：/Users/liupeng/workspace/certimate-main/ui/src/pages/settings/SettingsAppearance.tsx
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Divider, Form, type RadioChangeEvent, Select, Space, Button, Spin, message, Tooltip, Input } from 'antd';
import { useSettings } from './SettingsContext';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';

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

// 时区选项
const TIMEZONE_OPTIONS = [
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (中国标准时间, UTC+8)' },
  { value: 'Asia/Hong_Kong', label: 'Asia/Hong_Kong (香港时间, UTC+8)' },
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo (日本标准时间, UTC+9)' },
  { value: 'Asia/Singapore', label: 'Asia/Singapore (新加坡时间, UTC+8)' },
  { value: 'America/New_York', label: 'America/New_York (美国东部时间, UTC-5/UTC-4)' },
  { value: 'America/Los_Angeles', label: 'America/Los_Angeles (美国西部时间, UTC-8/UTC-7)' },
  { value: 'Europe/London', label: 'Europe/London (格林尼治时间, UTC+0/UTC+1)' },
  { value: 'Europe/Paris', label: 'Europe/Paris (中欧时间, UTC+1/UTC+2)' },
  { value: 'Australia/Sydney', label: 'Australia/Sydney (澳大利亚东部时间, UTC+10/UTC+11)' },
  { value: 'UTC', label: 'UTC (协调世界时, UTC+0)' },
];

const GeneralSettingsPage = () => {
  const { t, i18n } = useTranslation();
  const {
    generalSettings,
    setGeneralSettings,
    loading,
    saving,
    saveConfig,
    resetConfig,
    applyTheme,
  } = useSettings();
  const { isGuest, checkPermission } = useGuestRestriction();

  const [themeChanged, setThemeChanged] = useState(false);
  const [localeChanged, setLocaleChanged] = useState(false);

  // 处理主题变更
  const handleThemeChange = (e: RadioChangeEvent) => {
    const value = e.target.value as 'light' | 'dark' | 'auto';
    if (value !== generalSettings.theme) {
      setThemeChanged(true);
      setGeneralSettings(prev => ({ ...prev, theme: value }));
      applyTheme(value);
      message.success(t('theme_changed') || '主题已切换');
    }
  };

  // 处理语言变更
  const handleLanguageChange = (value: string) => {
    if (value !== (i18n.resolvedLanguage ?? i18n.language)) {
      setLocaleChanged(true);
      setGeneralSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }));
      i18n.changeLanguage(value);
      message.success(t('language_changed') || '语言已切换');
    }
  };

  // 处理分页变更
  const handlePerPageChange = (value: number) => {
    setGeneralSettings(prev => ({ ...prev, defaultPerPage: value }));
  };

  // 处理时区变更
  const handleTimezoneChange = (value: string) => {
    setGeneralSettings(prev => ({ ...prev, timezone: value }));
  };

  // 保存配置
  const handleSave = async () => {
    // 检查访客权限
    if (!checkPermission('保存系统配置')) {
      return;
    }
    try {
      await saveConfig();
      setThemeChanged(false);
      setLocaleChanged(false);
    } catch (error: any) {
      // 处理后端返回的权限错误
      if (error?.response?.data?.code === 403) {
        message.error(error.response.data.message || '访客用户无法保存系统配置');
      }
    }
  };

  // 重置配置
  const handleReset = () => {
    resetConfig();
    i18n.changeLanguage('zh-CN');
    setThemeChanged(false);
    setLocaleChanged(false);
  };

  return (
    <Spin spinning={loading} description={t('loading') || '加载中...'}>
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
                      generalSettings.theme === item.key
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
                        generalSettings.theme === item.key
                          ? 'border-blue-500 bg-blue-500'
                          : 'border-gray-300 dark:border-gray-600'
                      }`}>
                        {generalSettings.theme === item.key && (
                          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      <span className={`text-sm font-medium ${
                        generalSettings.theme === item.key ? 'text-blue-600 dark:text-blue-400' : ''
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
                value={generalSettings.language}
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
                value={generalSettings.defaultPerPage || 10}
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

        <Divider />

        {/* 时区设置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('timezone') || '时区'}</h2>
          <Form layout="vertical">
            <Form.Item label={t('default_timezone') || '默认时区'}>
              <Select
                value={generalSettings.timezone || 'Asia/Shanghai'}
                onChange={handleTimezoneChange}
                options={TIMEZONE_OPTIONS}
                className="w-full max-w-md"
                showSearch
                filterOption={(input, option) =>
                  (option?.label || '').toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </Form>
        </div>

        <Divider />

        {/* 用户配置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('user_settings') || '用户设置'}</h2>
          <Form layout="vertical">
            <Form.Item label={t('username') || '用户名'}>
              <Input
                value={generalSettings.user?.username || ''}
                onChange={(e) => setGeneralSettings(prev => ({
                  ...prev,
                  user: { ...prev.user, username: e.target.value }
                }))}
                placeholder={t('enter_username') || '请输入用户名'}
                className="w-full max-w-md"
              />
            </Form.Item>
            <Form.Item label={t('password') || '密码'}>
              <Input.Password
                value={generalSettings.user?.password || ''}
                onChange={(e) => setGeneralSettings(prev => ({
                  ...prev,
                  user: { ...prev.user, password: e.target.value }
                }))}
                placeholder={t('enter_password') || '请输入密码'}
                className="w-full max-w-md"
              />
            </Form.Item>
          </Form>
        </div>

        {/* 操作按钮 */}
        <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Space>
            <Tooltip title={isGuest ? '访客用户无法重置配置' : ''}>
              <Button onClick={handleReset} disabled={saving || isGuest}>
                {t('reset') || '重置'}
              </Button>
            </Tooltip>
            <Tooltip title={isGuest ? '访客用户无法保存配置' : ''}>
              <Button type="primary" onClick={handleSave} loading={saving} disabled={isGuest}>
                {t('save') || '保存'}
              </Button>
            </Tooltip>
          </Space>
        </div>
      </div>
    </Spin>
  );
};

export default GeneralSettingsPage;
