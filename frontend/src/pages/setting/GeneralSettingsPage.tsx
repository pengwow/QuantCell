/**
 * 通用设置子页面
 * 功能：提供主题、语言、分页等通用设置
 */
import { useState, useMemo } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Divider, Form, type RadioChangeEvent, Select, Space, Button, Spin, App, Tooltip } from 'antd';
import { useSettings } from './SettingsContext';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { PER_PAGE_OPTIONS, snapPageSize } from '../../constants/pagination';
import { isTauri } from '../../desktop/env';
import SoftwareUpdateCard from './SoftwareUpdateCard';

// 主题图片路径
const THEME_IMAGES: Record<string, string> = {
  light: '/imgs/themes/light.png',
  dark: '/imgs/themes/dark.png',
  auto: '/imgs/themes/system.png',
};

// 翻译函数类型（与 react-i18next 的 useTranslation 返回值一致）
type TranslateFn = ReturnType<typeof useTranslation>['t'];

// 主题选项
const getThemeOptions = (t: TranslateFn) => [
  { key: 'light', label: t('theme_light'), image: THEME_IMAGES.light },
  { key: 'dark', label: t('theme_dark'), image: THEME_IMAGES.dark },
  { key: 'auto', label: t('theme_auto'), image: THEME_IMAGES.auto },
];

// 语言选项
const getLanguageOptions = (t: TranslateFn) => [
  { value: 'zh-CN', label: t('language_zh_cn') },
  { value: 'en-US', label: 'English' },
];

// 展示类型选项
const getViewTypeOptions = (t: TranslateFn) => [
  { value: 'card', label: t('settings_view_type_card') },
  { value: 'list', label: t('settings_view_type_list') },
];

// 时区选项
const getTimezoneOptions = (t: TranslateFn) => [
  { value: 'Asia/Shanghai', label: t('timezone_shanghai') },
  { value: 'Asia/Hong_Kong', label: t('timezone_hongkong') },
  { value: 'Asia/Tokyo', label: t('timezone_tokyo') },
  { value: 'Asia/Singapore', label: t('timezone_singapore') },
  { value: 'America/New_York', label: t('timezone_newyork') },
  { value: 'America/Los_Angeles', label: t('timezone_losangeles') },
  { value: 'Europe/London', label: t('timezone_london') },
  { value: 'Europe/Paris', label: t('timezone_paris') },
  { value: 'Australia/Sydney', label: t('timezone_sydney') },
  { value: 'UTC', label: t('timezone_utc') },
];

const GeneralSettingsPage = () => {
  const { t, i18n } = useTranslation();
  const { message } = App.useApp();
  const {
    generalSettings,
    setGeneralSettings,
    loading,
    saving,
    saveConfig,
    resetConfig,
    applyTheme,
    hasGeneralSettingsChanged,
  } = useSettings();
  const { isGuest, checkPermission } = useGuestRestriction();

  const [themeChanged, setThemeChanged] = useState(false);
  const [localeChanged, setLocaleChanged] = useState(false);

  // 使用 useMemo 缓存翻译后的选项数组
  const THEME_OPTIONS = useMemo(() => getThemeOptions(t), [t]);
  const LANGUAGE_OPTIONS = useMemo(() => getLanguageOptions(t), [t]);
  const VIEW_TYPE_OPTIONS = useMemo(() => getViewTypeOptions(t), [t]);
  const TIMEZONE_OPTIONS = useMemo(() => getTimezoneOptions(t), [t]);

  // 检测表单是否有变更
  const isFormChanged = hasGeneralSettingsChanged();

  // 处理主题变更
  const handleThemeChange = (e: RadioChangeEvent) => {
    const value = e.target.value as 'light' | 'dark' | 'auto';
    if (value !== generalSettings.theme) {
      setThemeChanged(true);
      setGeneralSettings(prev => ({ ...prev, theme: value }));
      applyTheme(value);
      message.success(t('theme_changed'));
    }
  };

  // 处理语言变更（智能版本）
  const handleLanguageChange = (value: string) => {
    // 始终更新设置状态，确保保存按钮能正确响应
    setLocaleChanged(true);
    setGeneralSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }));

    // 只在语言真正改变时才切换 i18n（避免不必要的重渲染）
    if (value !== (i18n.resolvedLanguage ?? i18n.language)) {
      i18n.changeLanguage(value);
      message.success(t('language_changed'));
    }

    // 立即持久化到 localStorage，防止刷新丢失
    localStorage.setItem('quantcell-language', value);
  };

  // 处理分页变更
  const handlePerPageChange = (value: number) => {
    setGeneralSettings(prev => ({ ...prev, defaultPerPage: value }));
  };

  // 处理默认展示类型变更（卡片/列表，全站统一）
  const handleViewTypeChange = (value: 'card' | 'list') => {
    setGeneralSettings(prev => ({ ...prev, defaultViewType: value }));
  };

  // 处理时区变更
  const handleTimezoneChange = (value: string) => {
    setGeneralSettings(prev => ({ ...prev, timezone: value }));
  };

  // 保存配置
  const handleSave = async () => {
    // 检查访客权限
    if (!checkPermission(t('save_system_config'))) {
      return;
    }
    try {
      await saveConfig();
      setThemeChanged(false);
      setLocaleChanged(false);
    } catch (error) {
      // 处理后端返回的权限错误
      if (axios.isAxiosError(error) && error.response?.data?.code === 403) {
        message.error(error.response.data.message || t('guest_save_system_config_restricted'));
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
    <Spin spinning={loading} description={t('loading')}>
      <div className="space-y-6">
        {/* 主题设置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('theme')}</h2>
          <Form layout="vertical">
            <Form.Item
              extra={themeChanged ? t('theme_changed_hint') : undefined}
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
          <h2 className="text-lg font-medium mb-4">{t('language')}</h2>
          <Form layout="vertical">
            <Form.Item
              extra={localeChanged ? t('language_changed_hint') : undefined}
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
          <h2 className="text-lg font-medium mb-4">{t('pagination')}</h2>
          <Form layout="vertical">
            <Form.Item label={t('default_per_page')}>
              <Select
                value={snapPageSize(generalSettings.defaultPerPage || 12)}
                onChange={handlePerPageChange}
                options={PER_PAGE_OPTIONS.map((value) => ({
                  value,
                  label: `${value} ${t('per_page')}`,
                }))}
                className="w-full max-w-md"
              />
            </Form.Item>
            <Form.Item
              label={t('settings_view_type_label')}
              extra={t('settings_view_type_hint')}
            >
              <Select
                value={generalSettings.defaultViewType || 'card'}
                onChange={handleViewTypeChange}
                options={VIEW_TYPE_OPTIONS}
                className="w-full max-w-md"
              />
            </Form.Item>
          </Form>
        </div>

        <Divider />

        {/* 时区设置 */}
        <div>
          <h2 className="text-lg font-medium mb-4">{t('timezone')}</h2>
          <Form layout="vertical">
            <Form.Item label={t('default_timezone')}>
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

        {/* 软件更新：仅桌面端渲染，Web 模式没有升级能力 */}
        {isTauri() && (
          <>
            <SoftwareUpdateCard />
            <Divider />
          </>
        )}

        {/* 操作按钮 */}
        <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Space>
            <Tooltip title={isGuest ? t('guest_reset_restricted') : ''}>
              <Button onClick={handleReset} disabled={saving || isGuest}>
                {t('reset')}
              </Button>
            </Tooltip>
            <Tooltip
              title={
                isGuest
                  ? t('guest_save_config_restricted')
                  : !isFormChanged
                    ? t('settings_save_hint_no_change')
                    : ''
              }
            >
              <Button
                type="primary"
                onClick={handleSave}
                loading={saving}
                disabled={isGuest || !isFormChanged}
              >
                {t('save')}
              </Button>
            </Tooltip>
          </Space>
        </div>
      </div>
    </Spin>
  );
};

export default GeneralSettingsPage;
