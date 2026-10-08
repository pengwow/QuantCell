/**
 * LLM 挖掘抽屉：Tabs[新建挖掘 | 挖掘历史]。
 * 不使用 destroyOnHidden：保留 Tab 状态，使运行中任务重连与历史列表不随抽屉关闭重置。
 * FactorMining 保存因子后经 onMined 通知容器刷新目录并选中新因子。
 */
import { useState } from 'react';
import { Drawer, Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import type { FactorMineLLMParams } from '@/api/factor';
import FactorMining from './FactorMining';
import MiningHistoryPane from './MiningHistoryPane';

const MineLLMDrawer: React.FC<{
  open: boolean;
  onClose: () => void;
  onMined: (name: string) => void;
}> = ({ open, onClose, onMined }) => {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'new' | 'history'>('new');
  // reuseSeq 自增触发 FactorMining 回填，避免相同参数二次复用不触发 effect
  const [reuseParams, setReuseParams] = useState<FactorMineLLMParams | null>(null);
  const [reuseSeq, setReuseSeq] = useState(0);

  const handleReuse = (params: FactorMineLLMParams) => {
    setReuseParams(params);
    setReuseSeq((n) => n + 1);
    setTab('new');
  };

  return (
    <Drawer
      title={t('factor_mining') || 'LLM 挖掘'}
      open={open}
      onClose={onClose}
      size={1200}
      mask={{ closable: false }}
    >
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'new' | 'history')}
        items={[
          {
            key: 'new',
            label: t('factor_mining_tab_new') || '新建挖掘',
            children: (
              <FactorMining onMined={onMined} reuseParams={reuseParams} reuseSeq={reuseSeq} />
            ),
          },
          {
            key: 'history',
            label: t('factor_mining_tab_history') || '挖掘历史',
            children: <MiningHistoryPane onMined={onMined} onReuse={handleReuse} />,
          },
        ]}
      />
    </Drawer>
  );
};

export default MineLLMDrawer;
