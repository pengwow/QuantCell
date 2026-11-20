/**
 * Worker 风控状态卡（spec 2026-11-16）
 *
 * 展示 B3 pre-trade 风控运行时状态：装配三态 / 当日盈亏 vs 亏损额度 / 推导熔断态。
 * 数据源 GET /workers/{id}/risk-status；30s 轮询，随 active 生命周期启停。
 */
import { useEffect, useState } from 'react';
import { Alert, Card, Descriptions, Progress, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { getRiskStatus } from '../../api/workerApi';
import type { RiskStatusOut } from '../../api/workerApi';
import { QUANT_COLORS } from '@/utils/colors';
import { formatUSD } from '../../utils/format';

const POLL_INTERVAL_MS = 30_000;

const WorkerRiskStatusCard: React.FC<{
  workerId: number;
  active?: boolean;
  onNavigate?: (tab: string) => void;
}> = ({ workerId, active = true, onNavigate }) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<RiskStatusOut | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    // ponytail: 30s 轮询足够——快照查询廉价，SSE/WebSocket 属过度设计
    const load = () => {
      getRiskStatus(workerId)
        .then((d) => { if (!cancelled) { setStatus(d); setFailed(false); } })
        .catch(() => { if (!cancelled) setFailed(true); });
    };
    load();
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [workerId, active]);

  if (failed) {
    return (
      <Card size="small" title={t('risk_status_title')}>
        <Typography.Text type="secondary">{t('risk_status_failed')}</Typography.Text>
      </Card>
    );
  }
  if (!status) return null;
  if (!status.configured) {
    return (
      <Card size="small" title={t('risk_status_title')}>
        <Typography.Text type="secondary">{t('risk_not_configured')}</Typography.Text>
      </Card>
    );
  }

  const usage = status.loss_usage;
  const usagePct = usage != null ? Math.min(100, Math.max(0, usage * 100)) : 0;

  return (
    <Card size="small" title={t('risk_status_title')} extra={
      <Tag color={status.source === 'manual' ? 'blue' : 'purple'}>{t(status.source === 'manual' ? 'risk_source_manual' : 'risk_source_params')}</Tag>
    }>
      <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
        {status.circuit_breaker_tripped && (
          <Alert type="error" showIcon
            message={t('risk_breaker_tripped_title')}
            description={t('risk_breaker_tripped_desc')} />
        )}
        <Descriptions size="small" column={2}>
          {status.config?.max_position_value != null && (
            <Descriptions.Item label={t('risk_max_position_value')}>
              {formatUSD(status.config.max_position_value)}
            </Descriptions.Item>
          )}
          {status.daily_loss_limit != null && (
            <Descriptions.Item label={t('risk_daily_loss_limit')}>
              {formatUSD(status.daily_loss_limit)}
            </Descriptions.Item>
          )}
          {status.config?.max_leverage != null && (
            <Descriptions.Item label={t('risk_max_leverage')}>
              {status.config.max_leverage}x
            </Descriptions.Item>
          )}
          {status.config?.circuit_breaker_cooldown_secs != null && (
            <Descriptions.Item label={t('risk_breaker_cooldown')}>
              {status.config.circuit_breaker_cooldown_secs}s
            </Descriptions.Item>
          )}
          {status.daily_pnl != null && (
            <Descriptions.Item label={t('risk_daily_pnl')}>
              <Space size="small">
                {/* 负盈亏色：语义跌色走 QUANT_COLORS.negative（palette error 派生，与涨跌语义同源） */}
                <span style={{ color: status.daily_pnl >= 0 ? undefined : QUANT_COLORS.negative }}>
                  {formatUSD(status.daily_pnl, { showSign: true })}
                </span>
                {status.daily_pnl < 0 && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('risk_pnl_paper_note')}
                  </Typography.Text>
                )}
              </Space>
            </Descriptions.Item>
          )}
        </Descriptions>
        {usage != null && status.daily_loss_limit != null && (
          <Progress
            percent={usagePct}
            status={usage >= 1 ? 'exception' : usage >= 0.7 ? 'active' : 'normal'}
            format={() => `${Math.round(usagePct)}%`}
          />
        )}
        {onNavigate && (
          <Typography.Link onClick={() => onNavigate('params')}>{t('risk_goto_params')}</Typography.Link>
        )}
      </Space>
    </Card>
  );
};

export default WorkerRiskStatusCard;
