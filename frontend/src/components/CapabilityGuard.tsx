import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Result, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { isCapabilityEnabled, useCapabilityStore, type CapabilityKey } from '@/store/capabilityStore';

/**
 * 能力守卫（P2-02）：包裹能力域页面路由。
 * 能力关闭时渲染 403 降级页（菜单隐藏后直达 URL 的兜底），未就绪时显示加载态。
 */
export default function CapabilityGuard({ capability, children }: { capability: CapabilityKey; children: ReactNode }) {
  const { t } = useTranslation();
  const capabilities = useCapabilityStore((s) => s.capabilities);
  const loadCapabilities = useCapabilityStore((s) => s.loadCapabilities);

  useEffect(() => {
    void loadCapabilities();
  }, [loadCapabilities]);

  if (capabilities === null) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spin size="large" />
      </div>
    );
  }

  if (!isCapabilityEnabled(capabilities, capability)) {
    return (
      <div className="flex h-full items-center justify-center">
        <Result
          status="403"
          title={t('capability_disabled_title')}
          subTitle={t('capability_disabled_desc', { capability })}
        />
      </div>
    );
  }

  return <>{children}</>;
}
