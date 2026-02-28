/**
 * 基本设置子页面
 * 功能：提供主题、语言、时区设置
 */
import { Button, Space, Spin } from 'antd';
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useSettings } from './SettingsContext';
import BasicSettings from './BasicSettings';
import PageContainer from '@/components/PageContainer';

const BasicSettingsPage = () => {
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

  // 保存配置
  const handleSave = async () => {
    await saveConfig();
  };

  // 重置配置
  const handleReset = () => {
    resetConfig();
    // 重置后应用默认语言
    i18n.changeLanguage('zh-CN');
  };

  return (
    <PageContainer title={t('basic_settings') || '基本设置'}>
      <Spin spinning={loading} tip={t('loading') || '加载中...'}>
        <div className="space-y-6">
          <BasicSettings
            settings={userSettings}
            setSettings={setUserSettings}
            applyTheme={applyTheme}
            i18n={i18n}
          />

          {/* 操作按钮 */}
          <div className="flex justify-end gap-4 pt-4 border-t border-gray-200">
            <Space>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleReset}
                disabled={saving}
              >
                {t('reset') || '重置'}
              </Button>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={saving}
              >
                {t('save') || '保存'}
              </Button>
            </Space>
          </div>
        </div>
      </Spin>
    </PageContainer>
  );
};

export default BasicSettingsPage;
