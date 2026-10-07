/**
 * 因子分析页面：分析工作台 + 因子库 + 对比 + LLM 挖掘
 *
 * - Tab 状态与 URL ?tab= 同步，支持挖掘页保存后跳回工作台；
 * - 分析历史提升到本层持有，切 Tab 不丢失（会话级内存，最多保留 10 条）。
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import type { FactorAnalyzeParams, FactorAnalyzeResult } from '@/api/factor';
import FactorCompare from './FactorCompare';
import FactorLibrary from './FactorLibrary';
import FactorMining from './FactorMining';
import FactorWorkbench from './FactorWorkbench';

/** 单次成功分析的历史条目（会话级，不持久化） */
export interface AnalyzeHistoryItem {
  id: string;
  ts: number;
  params: FactorAnalyzeParams;
  result: FactorAnalyzeResult;
}

const HISTORY_LIMIT = 10;
const TAB_KEYS = ['workbench', 'library', 'compare', 'mining'] as const;

const FactorAnalysis: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = TAB_KEYS.includes(searchParams.get('tab') as (typeof TAB_KEYS)[number])
    ? (searchParams.get('tab') as (typeof TAB_KEYS)[number])
    : 'workbench';
  const [history, setHistory] = useState<AnalyzeHistoryItem[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);

  useEffect(() => {
    setPageTitle(t('factor_analysis'));
  }, [t]);

  const switchTab = useCallback(
    (key: string) => {
      // 切 Tab 只保留 tab 参数，清掉联动用的一次性参数（factor/syms/run 等）
      setSearchParams({ tab: key }, { replace: true });
    },
    [setSearchParams],
  );

  const pushHistory = useCallback((item: AnalyzeHistoryItem) => {
    setHistory((prev) => [item, ...prev].slice(0, HISTORY_LIMIT));
    setActiveHistoryId(item.id);
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    setActiveHistoryId(null);
  }, []);

  return (
    <PageContainer title={t('factor_analysis')}>
      <Tabs
        activeKey={tab}
        onChange={switchTab}
        items={[
          {
            key: 'workbench',
            label: t('factor_workbench'),
            children: (
              <FactorWorkbench
                history={history}
                activeHistoryId={activeHistoryId}
                onSelectHistory={setActiveHistoryId}
                onPushHistory={pushHistory}
                onClearHistory={clearHistory}
              />
            ),
          },
          { key: 'library', label: t('factor_library'), children: <FactorLibrary /> },
          {
            key: 'compare',
            label: t('factor_compare') || '因子对比',
            children: <FactorCompare />,
          },
          { key: 'mining', label: t('factor_mining') || 'LLM Mining', children: <FactorMining /> },
        ]}
      />
    </PageContainer>
  );
};

export default FactorAnalysis;
