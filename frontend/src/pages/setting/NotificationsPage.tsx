/**
 * 通知设置子页面
 * 功能：提供邮件通知、Webhook 通知等通知相关配置
 */
import { Button, Space, Spin } from 'antd';
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useSettings } from './SettingsContext';
import Notifications from './Notifications';
import PageContainer from '@/components/PageContainer';

const NotificationsPage = () => {
  const { t } = useTranslation();
  const {
    notificationSettings,
    setNotificationSettings,
    loading,
    saving,
    saveConfig,
    resetConfig,
  } = useSettings();

  // 保存配置
  const handleSave = async () => {
    await saveConfig();
  };

  // 重置配置
  const handleReset = () => {
    resetConfig();
  };

  return (
    <PageContainer title={t('notification_settings') || '通知设置'}>
      <Spin spinning={loading} tip={t('loading') || '加载中...'}>
        <div className="space-y-6">
          <Notifications
            notificationSettings={notificationSettings}
            setNotificationSettings={setNotificationSettings}
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

export default NotificationsPage;
