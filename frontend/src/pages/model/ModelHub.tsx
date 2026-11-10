import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Tabs } from 'antd';
import PageContainer from '@/components/PageContainer';
import UnifiedModelTable from './components/UnifiedModelTable';
import TrainingWorkbench from './components/TrainingWorkbench';
import EnsembleWorkbench from './components/EnsembleWorkbench';

export default function ModelHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  // deep link:?tab=train → 训练工作台,?tab=ensemble → 模型集成,无参/其他 → 模型总表(默认)
  const rawTab = searchParams.get('tab');
  const tab = rawTab === 'train' || rawTab === 'ensemble' ? rawTab : 'models';
  const [refreshKey, setRefreshKey] = useState(0);

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
    <PageContainer title="模型中心">
      {/* type="card": 卡片式页签,与策略管理页 Tabs 风格统一 */}
      <Tabs
        type="card"
        activeKey={tab}
        onChange={handleTabChange}
        items={[
          { key: 'models', label: '模型总表', children: <UnifiedModelTable refreshKey={refreshKey} /> },
          { key: 'train', label: '训练工作台', children: <TrainingWorkbench onTrainSuccess={goToListAfterTrain} /> },
          { key: 'ensemble', label: '模型集成', children: <EnsembleWorkbench /> },
        ]}
      />
    </PageContainer>
  );
}
