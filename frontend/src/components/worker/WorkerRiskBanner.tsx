/**
 * 总览顶部熔断横幅（spec 2026-11-16 方案 A）
 * - 仅 circuit_breaker_tripped=true 时渲染红色 Alert；正常与请求失败都不出块（不占布局）
 * - 30s 轮询足够：熔断是低频状态变更，完整状态明细在「风控」tab 的 WorkerRiskStatusCard
 * - 不复用 risk_breaker_tripped_desc：其文案写死「参数 Tab」且无来源要素，banner 用专属 key
 */
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert } from 'antd';
import { getRiskStatus } from '../../api/workerApi';
import type { RiskStatusOut } from '../../api/workerApi';

const POLL_INTERVAL_MS = 30_000;

interface WorkerRiskBannerProps {
  workerId: number;
  active?: boolean;
}

const WorkerRiskBanner: React.FC<WorkerRiskBannerProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<RiskStatusOut | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const load = () => {
      getRiskStatus(workerId)
        .then((out) => {
          if (!cancelled) setStatus(out);
        })
        // 拉取失败静默：横幅是提示性组件，缺数据时不该打乱总览布局
        .catch(() => {
          if (!cancelled) setStatus(null);
        });
    };
    load();
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [workerId, active]);

  if (!status?.circuit_breaker_tripped) return null;

  const sourceKey = status.source === 'manual' ? 'risk_source_manual' : 'risk_source_params';

  return (
    <Alert
      type="error"
      showIcon
      title={t('worker_risk_banner_title')}
      description={t('worker_risk_banner_desc', { source: t(sourceKey) })}
      style={{ marginBottom: 16 }}
    />
  );
};

export default WorkerRiskBanner;
