/**
 * 右栏占位 Tab（⑦ 事件与拥挤）：
 * 依赖组件A/B 的事件与拥挤算子，后端端点未建，本批仅渲染空态说明，不接假数据。
 * （⑥ 审计已在 P1 batch2 接真，见 ./AuditTab.tsx。）
 */
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';

export function EventsTab() {
  const { t } = useTranslation();
  return (
    <div className="wb-placeholder">
      <Empty
        description={t('wb_placeholder_pending_backend')}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      >
        <span className="wb-placeholder-ref">{t('wb_placeholder_events_hint')}</span>
      </Empty>
    </div>
  );
}
