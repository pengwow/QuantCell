import { useTranslation } from 'react-i18next';
import { Card, Row, Col, Descriptions, Space, Spin, Tooltip, Typography } from 'antd';
import type { Worker as WorkerType, StrategyParameter } from '../../types/worker';
import { CodeOutlined } from '@ant-design/icons';
import { getStrategyParameters } from '../../api/workerApi';
import { useState, useEffect } from 'react';

// 策略类型 → §6.2 chip 语义档：RL=pri、规则=info、未知=quiet
const STRATEGY_TYPE_CHIP: Record<string, string> = { rl: ' pri', rule: ' info' };

interface WorkerParamsTabProps {
  worker: WorkerType;
}

const WorkerParamsTab: React.FC<WorkerParamsTabProps> = ({ worker }) => {
  const { t } = useTranslation();

  // 从 config 中提取策略参数（如果存在）
  const config: Record<string, unknown> = worker.config ?? {};

  // 按标的参数覆盖（只读展示，spec 2026-11-28 §7）
  const bySymbol = ((worker?.config as Record<string, unknown> | undefined)?.strategy_params_by_symbol ??
    {}) as Record<string, Record<string, unknown>>;
  const overrideSymbols = Object.keys(bySymbol);

  // 动态策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);

  // Worker 实际配置的策略参数值（从 config 或 trading_config 获取）
  const rawParams =
    (worker.trading_config as Record<string, unknown> | undefined)?.strategy_params ??
    config.strategy_params ??
    {};
  const currentStrategyParams: Record<string, unknown> =
    rawParams && typeof rawParams === 'object' ? (rawParams as Record<string, unknown>) : {};

  // 加载策略参数定义（后端合并策略库 schema + worker 覆盖值，按 worker 维度查询）
  useEffect(() => {
    const loadParams = async () => {
      if (!worker.id) {
        setStrategyParams([]);
        return;
      }
      setLoadingParams(true);
      try {
        const params = await getStrategyParameters(worker.id);
        setStrategyParams(params);
      } catch (error) {
        console.error('加载策略参数失败:', error);
        setStrategyParams([]);
      } finally {
        setLoadingParams(false);
      }
    };
    loadParams();
  }, [worker.id]);

  return (
    <div>
      {/* 策略信息 */}
      {worker.strategy_info && (
        <Card
          className="qc-card"
          title={
            <Space>
              <CodeOutlined />
              <span>{t('strategy_info')}</span>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Row gutter={[24, 16]}>
            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                <Descriptions.Item label={t('strategy_name')}>
                  {/* 标识类中性 mono（§6.5）：名称不上色 */}
                  <span className="qc-mono">{worker.strategy_info.name}</span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                <Descriptions.Item label={t('strategy_type')}>
                  {/* 值域对齐策略库 models（rule/rl）；'default' 为无关联策略时的兜底档，未知值归默认 */}
                  <span className={`qc-chip${STRATEGY_TYPE_CHIP[worker.strategy_info.strategy_type] ?? ' quiet'}`}>
                    {worker.strategy_info.strategy_type === 'rl'
                      ? t('rl_strategy')
                      : worker.strategy_info.strategy_type === 'rule'
                        ? t('rule_strategy')
                        : t('default_strategy')}
                  </span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                <Descriptions.Item label={t('strategy_version')}>
                  <span className="qc-mono">v{worker.strategy_info.version}</span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            {worker.strategy_info.description && (
              <Col span={24}>
                <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                  <Descriptions.Item label={t('strategy_description')}>
                    <span>{worker.strategy_info.description}</span>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            )}
          </Row>
        </Card>
      )}

      {/* 策略参数 - 动态加载 */}
      <Card
        className="qc-card"
        title={
          <Space>
            <CodeOutlined />
            <span>{t('strategy_params')}</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        {strategyParams.length > 0 ? (
          <Row gutter={[24, 16]}>
            {strategyParams.map((param) => {
              const currentValue = currentStrategyParams[param.param_name];
              // 生效值优先级：运行配置覆盖 > 后端合并的 param_value（快照覆盖 ?? schema 默认）> schema 默认
              const displayValue = currentValue ?? param.param_value ?? param.default_value ?? '-';
              let valueDisplay: React.ReactNode;

              if (typeof displayValue === 'number' && param.param_type === 'float') {
                // 数值 mono；loss/stop 归 down、profit 归 up（涨跌语义，不按词感乱染色）
                const dirCls = param.param_name?.includes('loss') || param.param_name?.includes('stop')
                  ? ' qc-cell-down'
                  : param.param_name?.includes('profit')
                    ? ' qc-cell-up'
                    : '';
                valueDisplay = (
                  <span className={`qc-mono${dirCls}`}>
                    {typeof displayValue === 'number' ? displayValue.toFixed(2) : String(displayValue)}
                  </span>
                );
              } else if (typeof displayValue === 'boolean') {
                // 布尔开关：true=ok / false=quiet（未开启不是错误）
                valueDisplay = (
                  <span className={`qc-chip${displayValue ? ' ok' : ' quiet'}`}>
                    {displayValue ? t('yes') : t('no')}
                  </span>
                );
              } else {
                valueDisplay = <span className="qc-mono">{String(displayValue)}</span>;
              }

              return (
                <Col key={param.param_name} xs={24} sm={12} md={8}>
                  <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                    <Descriptions.Item
                      label={
                        <Space size={4}>
                          <span className="qc-mono">{param.param_name}</span>
                          {param.description && (
                            <Tooltip title={param.description}>
                              <span style={{ fontSize: 10.5, color: 'var(--qc-text-quaternary)' }}>
                                {param.description.length > 20 ? `${param.description.slice(0, 18)}...` : param.description}
                              </span>
                            </Tooltip>
                          )}
                        </Space>
                      }
                    >
                      {valueDisplay}
                    </Descriptions.Item>
                  </Descriptions>
                </Col>
              );
            })}
          </Row>
        ) : loadingParams ? (
          <div style={{ textAlign: 'center', padding: 30 }}>
            <Spin size="small" />
          </div>
        ) : Object.keys(currentStrategyParams).length > 0 ? (
          <Row gutter={[24, 16]}>
            {Object.entries(currentStrategyParams).map(([key, value]) => (
              <Col key={key} xs={24} sm={12} md={8}>
                <Descriptions column={1} size="small" styles={{ label: { color: 'var(--qc-text-secondary)' } }}>
                  <Descriptions.Item label={<span className="qc-mono">{key}</span>}>
                    <span className="qc-mono">{String(value)}</span>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            ))}
          </Row>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--qc-text-tertiary)' }}>
            {t('no_configurable_params')}
          </div>
        )}
      </Card>

      {/* 按标的参数覆盖（只读展示，spec 2026-11-28 §7） */}
      {overrideSymbols.length > 0 && (
        <Card size="small" title={t('strategyParams.override_button')}>
          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
            {overrideSymbols.map((sym) => (
              <Typography.Text key={sym} type="secondary" style={{ fontSize: 12 }}>
                {sym}：{JSON.stringify(bySymbol[sym])}
              </Typography.Text>
            ))}
          </Space>
        </Card>
      )}
    </div>
  );
};

export default WorkerParamsTab;
