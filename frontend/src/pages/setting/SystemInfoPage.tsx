/**
 * 系统信息子页面
 * 功能：显示系统版本、运行状态、资源使用等信息
 */
import { Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSettings } from './SettingsContext';
import SystemInfo from './SystemInfo';
import PageContainer from '@/components/PageContainer';

const SystemInfoPage = () => {
  const { t } = useTranslation();
  const { systemInfo, loading } = useSettings();

  return (
    <PageContainer title={t('system_info') || '系统信息'}>
      <Spin spinning={loading} tip={t('loading') || '加载中...'}>
        <SystemInfo systemInfo={systemInfo} />
      </Spin>
    </PageContainer>
  );
};

export default SystemInfoPage;
