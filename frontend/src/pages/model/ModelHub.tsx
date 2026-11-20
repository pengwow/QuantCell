import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Tabs } from 'antd';
import PageContainer from '@/components/PageContainer';
import UnifiedModelTable from './components/UnifiedModelTable';
import type { ModelHubStats } from './components/UnifiedModelTable';
import TrainingWorkbench from './components/TrainingWorkbench';
import EnsembleWorkbench from './components/EnsembleWorkbench';
import { useTranslation } from 'react-i18next';
import RLBacktestHistory from './components/RLBacktestHistory';

export default function ModelHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { t } = useTranslation();
  // deep link:?tab=train → 训练工作台,?tab=ensemble → 模型集成,?tab=history → RL 回测历史,
  // 无参/其他 → 模型总表(默认)
  const rawTab = searchParams.get('tab');
  const tab =
    rawTab === 'train' || rawTab === 'ensemble' || rawTab === 'history' ? rawTab : 'models';
  const [refreshKey, setRefreshKey] = useState(0);
  // 页头副标统计：由模型总表按 /models/unified 全量口径上报（§5 page-sub，只写可算出的数字）
  const [stats, setStats] = useState<ModelHubStats | null>(null);
  const handleStats = useCallback((s: ModelHubStats) => setStats(s), []);

  // 副标组合：全部词条复用既有 i18n 键（umt_total / umt_status_*），stage 码保持英文原值；
  // shadow / archived / 未注册 / 文件缺失仅在计数 > 0 时出现
  const subtitle = useMemo(() => {
    if (!stats) return undefined;
    const parts = [
      t('umt_total', { total: stats.total }),
      `production ${stats.production}`,
      `staging ${stats.staging}`,
    ];
    if (stats.shadow > 0) parts.push(`shadow ${stats.shadow}`);
    if (stats.archived > 0) parts.push(`archived ${stats.archived}`);
    if (stats.unregistered > 0) parts.push(`${t('umt_status_unregistered')} ${stats.unregistered}`);
    if (stats.missing > 0) parts.push(`${t('umt_status_missing')} ${stats.missing}`);
    return parts.join(' · ');
  }, [stats, t]);

  const handleTabChange = (key: string) => {
    // replace:Tab 切换不留历史记录
    setSearchParams(key === 'models' ? {} : { tab: key }, { replace: true });
  };

  // 训练成功 → 切回总表并强制刷新(refreshKey 驱动 useEffect 重拉)
  const goToListAfterTrain = () => {
    setSearchParams({}, { replace: true });
    setRefreshKey((k) => k + 1);
  };

  return (
    <PageContainer title={t('model_hub')} subtitle={subtitle}>
      <Tabs
        activeKey={tab}
        onChange={handleTabChange}
        items={[
          { key: 'models', label: '模型总表', children: <UnifiedModelTable refreshKey={refreshKey} onStats={handleStats} /> },
          { key: 'train', label: '训练工作台', children: <TrainingWorkbench onTrainSuccess={goToListAfterTrain} /> },
          { key: 'ensemble', label: '模型集成', children: <EnsembleWorkbench /> },
          // RL 回测历史只读页签；既有三个 label 硬编码中文（该页未接 i18n），保持原样不扩大 diff
          { key: 'history', label: t('rl_backtest_history'), children: <RLBacktestHistory /> },
        ]}
      />
    </PageContainer>
  );
}
