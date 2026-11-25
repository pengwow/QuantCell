/**
 * 人工风控配置卡（从 WorkerParamsTab 拆出，逻辑零改动）
 *
 * 三态展示：启用明细 / 已停用 / 继承策略参数
 * 数据源 GET /workers/{id}/risk-control；reloadKey 由父页面递增触发重拉
 */

import { useTranslation } from 'react-i18next';
import { Button, Card, Col, Descriptions, Row, Space, Spin, Tooltip } from 'antd';
import { ExclamationCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import type { RiskControlOut } from '../../types/worker';
import { getRiskControl } from '../../api/workerApi';
import { QUANT_COLORS } from '@/utils/colors';
import { useState, useEffect } from 'react';

/** 人工风控展示行的 7 个数值字段（key 收窄为字面量联合，risk[key] 无需断言） */
type RiskDisplayKey =
  | 'max_position_pct'
  | 'max_position_size'
  | 'daily_loss_limit'
  | 'daily_loss_amount'
  | 'max_drawdown'
  | 'max_leverage'
  | 'circuit_breaker_cooldown_secs';

/**
 * 人工风控展示行（启用明细态)：key 为 RiskControlOut 数值字段。
 * label / engineDefault 存的是 i18n key，渲染处经 t() 翻译；
 * engineDefault = 该字段未配置（null）时引擎实际生效的默认档，硬编码出处：
 * - 亏损/回撤/杠杆/冷却：axon-risk config.rs `RiskConfig::default()`
 * - 仓位两行：axon-worker risk_check.rs 桥接口径 max_position_value=None = 不做仓位检查
 *   （引擎默认的数量口径仓位限额已在桥层禁用，未配置就是真不限制）
 * - 「亏损上限占比」引擎无占比默认档，生效的是固定金额 10,000 USDT，故与金额行同文
 * ponytail: 前端内嵌默认值有与引擎漂移的风险，升级路径是后端接口回带默认值字段
 */
const RISK_DISPLAY_ROWS: { key: RiskDisplayKey; label: string; unit: 'pct' | 'usdt' | 'x' | 'min'; engineDefault: string }[] = [
  { key: 'max_position_pct', label: 'worker_risk_max_position_pct', unit: 'pct', engineDefault: 'worker_risk_unlimited' },
  { key: 'max_position_size', label: 'worker_risk_max_position_size', unit: 'usdt', engineDefault: 'worker_risk_unlimited' },
  { key: 'daily_loss_limit', label: 'worker_risk_daily_loss_limit', unit: 'pct', engineDefault: 'worker_risk_engine_default_loss' },
  { key: 'daily_loss_amount', label: 'worker_risk_daily_loss_amount', unit: 'usdt', engineDefault: 'worker_risk_engine_default_loss' },
  { key: 'max_drawdown', label: 'worker_risk_max_drawdown_limit', unit: 'pct', engineDefault: 'worker_risk_engine_default_drawdown' },
  { key: 'max_leverage', label: 'worker_risk_max_leverage', unit: 'x', engineDefault: 'worker_risk_engine_default_leverage' },
  { key: 'circuit_breaker_cooldown_secs', label: 'worker_risk_cooldown', unit: 'min', engineDefault: 'worker_risk_engine_default_cooldown' },
];

interface WorkerRiskControlCardProps {
  workerId: number;
  /** 「编辑」按钮回调（父页面联动 EditModal） */
  onEdit?: () => void;
  /** 递增触发风控配置重拉：编辑弹窗保存成功后由父页面更新，避免展示旧值 */
  reloadKey?: number;
}

const WorkerRiskControlCard: React.FC<WorkerRiskControlCardProps> = ({ workerId, onEdit, reloadKey = 0 }) => {
  const { t } = useTranslation();

  /**
   * 后端口径 → 展示文本：% 字段 0-1 → xx%，冷却秒 → 分钟；加零位小数避免 15.0%。
   * 只负责已配置值的格式化，未配置（null）的「引擎默认」分支在渲染处处理。
   * 定义在组件内是因为「分钟」单位后缀需要经 t() 翻译。
   */
  const fmtRiskValue = (v: number, unit: 'pct' | 'usdt' | 'x' | 'min'): string => {
    switch (unit) {
      case 'pct':
        return `${+(v * 100).toFixed(4)}%`;
      case 'usdt':
        return `${v.toLocaleString('en-US')} USDT`;
      case 'x':
        return `${v}x`;
      case 'min':
        return `${+(v / 60).toFixed(2)} ${t('worker_risk_minutes')}`;
    }
  };

  // 人工风控配置（GET null = 从未配置过 → 继承策略参数）
  const [risk, setRisk] = useState<RiskControlOut | null>(null);
  const [riskLoaded, setRiskLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRiskControl(workerId)
      .then((out) => {
        if (!cancelled) setRisk(out);
      })
      .catch((error) => {
        console.error(t('risk_control_load_failed'), error);
      })
      .finally(() => {
        if (!cancelled) setRiskLoaded(true);
      });
    return () => {
      cancelled = true;
    };
    // reloadKey 仅作为重拉信号（编辑保存成功后由父页面递增），不参与 effect 内部逻辑
  }, [workerId, reloadKey]);

  return (
    <Card
      className="qc-card"
      title={
        <Space>
          {/* 盾形图标与 WorkerParamsTab 的卡头图标体系一致（emoji 不入卡头） */}
          <SafetyCertificateOutlined />
          <span>{t('risk_params')}</span>
          {risk?.enabled && <span className="qc-chip ok">{t('worker_risk_guard_active')}</span>}
        </Space>
      }
      extra={onEdit && <Button size="small" onClick={onEdit}>{t('edit')}</Button>}
    >
      {!riskLoaded ? (
        <div style={{ textAlign: 'center', padding: 30 }}>
          <Spin size="small" />
        </div>
      ) : risk === null ? (
        <div style={{ textAlign: 'center', padding: 30, color: 'var(--qc-text-tertiary)' }}>
          {t('worker_risk_inherit_strategy')}
        </div>
      ) : !risk.enabled ? (
        <div style={{ textAlign: 'center', padding: 30, color: 'var(--qc-text-tertiary)' }}>
          {t('worker_risk_guard_disabled')}
        </div>
      ) : (
        <Row gutter={[24, 16]}>
          {RISK_DISPLAY_ROWS.map(({ key, label, unit, engineDefault }) => {
            // 联合键索引直接比较 narrowing 不可靠，先提取局部变量
            const v = risk[key];
            return (
              <Col key={key} xs={24} sm={12} md={8}>
                <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                  <Descriptions.Item label={t(label)}>
                    {v === null || v === undefined ? (
                      // 未配置 → 引擎默认档：保持原染色警示，感叹号悬浮展示具体默认值
                      <span
                        style={{
                          fontWeight: 500,
                          color: unit === 'pct' || unit === 'usdt' ? QUANT_COLORS.negative : undefined,
                        }}
                      >
                        {t('worker_risk_engine_default')}
                        <Tooltip title={t('worker_risk_engine_default_tooltip', { value: t(engineDefault) })}>
                          {/* 提示图标：警示语义走 --qc-warning token（亮暗随主题换挡） */}
                          <ExclamationCircleOutlined
                            style={{ marginLeft: 4, fontSize: 12, color: 'var(--qc-warning)', cursor: 'help' }}
                          />
                        </Tooltip>
                      </span>
                    ) : (
                      <span
                        style={{
                          fontWeight: 500,
                          color: unit === 'pct' || unit === 'usdt' ? QUANT_COLORS.negative : undefined,
                        }}
                      >
                        {fmtRiskValue(v, unit)}
                      </span>
                    )}
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            );
          })}
          <Col span={24}>
            <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
              <Descriptions.Item label={t('updated_at')}>
                <span style={{ color: 'var(--qc-text-tertiary)' }}>
                  {risk.updated_at ? new Date(risk.updated_at).toLocaleString() : '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      )}
    </Card>
  );
};

export default WorkerRiskControlCard;
