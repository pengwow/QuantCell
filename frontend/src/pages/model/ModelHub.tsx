import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Tabs } from 'antd';
import PageContainer from '@/components/PageContainer';
import UnifiedModelTable from './components/UnifiedModelTable';
import type { ModelHubStats } from './components/UnifiedModelTable';
import TrainingWorkbench from './components/TrainingWorkbench';
import EnsembleWorkbench from './components/EnsembleWorkbench';
import RetrainLedgerModal, { retrainGateText } from './components/RetrainLedgerModal';
import { rlApi } from '@/api/rlApi';
import { useTranslation } from 'react-i18next';

export default function ModelHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  // deep link:?tab=train → 训练工作台,?tab=ensemble → 模型集成, 无参/其他 → 模型总表(默认)
  // RL 回测历史已并入回测中心（同名页签下线）：旧 ?tab=history 书签直接落到 /backtest
  const rawTab = searchParams.get('tab');
  useEffect(() => {
    if (rawTab === 'history') navigate('/backtest', { replace: true });
  }, [rawTab, navigate]);
  const tab = rawTab === 'train' || rawTab === 'ensemble' ? rawTab : 'models';
  const [refreshKey, setRefreshKey] = useState(0);
  // 页头副标统计：由模型总表按 /models/unified 全量口径上报（§5 page-sub，只写可算出的数字）
  const [stats, setStats] = useState<ModelHubStats | null>(null);
  const handleStats = useCallback((s: ModelHubStats) => setStats(s), []);
  // 页头副标双闸状态：GET /rl/lifecycle/state 真值；请求失败保持 null（该段不渲染，不写死缺省）
  const [gates, setGates] = useState<{ retrain: boolean; promote: boolean } | null>(null);
  useEffect(() => {
    let alive = true;
    rlApi
      .lifecycleState()
      .then((d) => {
        // 字段不完整同样按失败处理，绝不落「双闸关闭」假缺省
        if (alive && typeof d?.auto_retrain_enabled === 'boolean' && typeof d?.auto_promote_enabled === 'boolean') {
          setGates({ retrain: d.auto_retrain_enabled, promote: d.auto_promote_enabled });
        }
      })
      .catch(() => {
        /* 副标统计行降级：双闸段静默缺席，不影响页面主体 */
      });
    return () => {
      alive = false;
    };
  }, []);
  // 重训台账（只读 Modal）
  const [ledgerOpen, setLedgerOpen] = useState(false);

  // 副标组合：全部词条复用既有 i18n 键（umt_total / umt_status_*），stage 码保持英文原值；
  // shadow / archived / 未注册 / 文件缺失仅在计数 > 0 时出现；双闸段取端点真值（与 demo 的 page-sub 同位）
  const subtitle = useMemo(() => {
    if (!stats && !gates) return undefined;
    const parts: string[] = [];
    if (stats) {
      parts.push(
        t('umt_total', { total: stats.total }),
        `production ${stats.production}`,
        `staging ${stats.staging}`,
      );
      if (stats.shadow > 0) parts.push(`shadow ${stats.shadow}`);
      if (stats.archived > 0) parts.push(`archived ${stats.archived}`);
      if (stats.unregistered > 0) parts.push(`${t('umt_status_unregistered')} ${stats.unregistered}`);
      if (stats.missing > 0) parts.push(`${t('umt_status_missing')} ${stats.missing}`);
    }
    if (gates) parts.push(retrainGateText(gates.retrain, gates.promote));
    return parts.join(' · ');
  }, [stats, gates, t]);

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
    <PageContainer
      title={t('model_hub')}
      subtitle={subtitle}
      // 页头操作区（与 demo page-actions 同位）：新建训练直达训练工作台页签（同步直跑，
      // 不做排队语义）；重训台账是只读 Modal，审批链路不在页面头
      actions={
        <>
          <Button
            type="primary"
            onClick={() => setSearchParams({ tab: 'train' }, { replace: true })}
          >
            {t('model_hub.new_training')}
          </Button>
          <Button onClick={() => setLedgerOpen(true)}>{t('model_hub.retrain_ledger')}</Button>
        </>
      }
    >
      <Tabs
        activeKey={tab}
        onChange={handleTabChange}
        items={[
          { key: 'models', label: '模型总表', children: <UnifiedModelTable refreshKey={refreshKey} onStats={handleStats} /> },
          { key: 'train', label: '训练工作台', children: <TrainingWorkbench onTrainSuccess={goToListAfterTrain} /> },
          { key: 'ensemble', label: '模型集成', children: <EnsembleWorkbench /> },
          // 页签 label 硬编码中文（该页未接 i18n），保持原样不扩大 diff
        ]}
      />
      <RetrainLedgerModal open={ledgerOpen} onClose={() => setLedgerOpen(false)} />
    </PageContainer>
  );
}
