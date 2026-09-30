/**
 * 因子分析页面：分析工作台 + 因子库
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Tabs } from 'antd';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import FactorCompare from './FactorCompare';
import FactorLibrary from './FactorLibrary';
import FactorMining from './FactorMining';
import FactorWorkbench from './FactorWorkbench';

const FactorAnalysis: React.FC = () => {
  const { t } = useTranslation();

  useEffect(() => {
    setPageTitle(t('factor_analysis'));
  }, [t]);

  return (
    <PageContainer title={t('factor_analysis')}>
      <Tabs
        defaultActiveKey="workbench"
        items={[
          { key: 'workbench', label: t('factor_workbench'), children: <FactorWorkbench /> },
          { key: 'library', label: t('factor_library'), children: <FactorLibrary /> },
          { key: 'compare', label: t('factor_compare') || '因子对比', children: <FactorCompare /> },
          { key: 'mining', label: 'LLM 挖掘', children: <FactorMining /> },
        ]}
      />
    </PageContainer>
  );
};

export default FactorAnalysis;
