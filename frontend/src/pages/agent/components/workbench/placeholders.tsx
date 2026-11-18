/**
 * 右栏占位 Tab（⑥ 审计 / ⑦ 事件与拥挤）：
 * 后端配套端点未建（审计查询 API 见设计文档 §2A.2；事件与拥挤依赖组件A/B），
 * 本批仅渲染空态说明，不接假数据。
 */
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';

export function AuditTab() {
  const { t } = useTranslation();
  return (
    <div className="wb-placeholder">
      <Empty
        description={t('wb_placeholder_pending_backend')}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      >
        <span className="wb-placeholder-ref">{t('wb_placeholder_audit_hint')}</span>
      </Empty>
    </div>
  );
}

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
