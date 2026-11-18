import { useTranslation } from 'react-i18next';
import { Card, Row, Col, Descriptions, Tag, Space } from 'antd';
import type { Worker as WorkerType, StrategyParameter } from '../../types/worker';
import { CodeOutlined, TagOutlined } from '@ant-design/icons';
import { getStrategyParameters } from '../../api/workerApi';
import { QUANT_COLORS } from '@/utils/colors';
import { useState, useEffect } from 'react';

interface WorkerParamsTabProps {
  worker: WorkerType;
}

const WorkerParamsTab: React.FC<WorkerParamsTabProps> = ({ worker }) => {
  const { t } = useTranslation();

  // 从 config 中提取策略参数（如果存在）
  const config: Record<string, unknown> = worker.config ?? {};

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
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_name')}>
                  <Tag color="blue">{worker.strategy_info.name}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_type')}>
                  {/* 值域对齐策略库 models（rule/rl）；'default' 为无关联策略时的兜底档，未知值归默认 */}
                  <Tag icon={<TagOutlined />} color={worker.strategy_info.strategy_type === 'rl' ? 'purple' : 'green'}>
                    {worker.strategy_info.strategy_type === 'rl'
                      ? t('rl_strategy')
                      : worker.strategy_info.strategy_type === 'rule'
                        ? t('rule_strategy')
                        : t('default_strategy')}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_version')}>
                  <span style={{ fontWeight: 500 }}>v{worker.strategy_info.version}</span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            {worker.strategy_info.description && (
              <Col span={24}>
                <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
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
        title={
          <Space>
            <span>📊</span>
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
              const valueStyle: React.CSSProperties = { fontWeight: 500 };

              if (typeof displayValue === 'number' && param.param_type === 'float') {
                valueDisplay = typeof displayValue === 'number' ? displayValue.toFixed(2) : String(displayValue);
                if (param.param_name?.includes('loss') || param.param_name?.includes('stop')) {
                  valueStyle.color = QUANT_COLORS.negative;
                } else if (param.param_name?.includes('profit')) {
                  valueStyle.color = QUANT_COLORS.positive;
                }
              } else if (typeof displayValue === 'boolean') {
                valueDisplay = (
                  <Tag color={displayValue ? 'green' : 'red'}>
                    {displayValue ? t('yes') : t('no')}
                  </Tag>
                );
              } else {
                valueDisplay = String(displayValue);
              }

              return (
                <Col key={param.param_name} xs={24} sm={12} md={8}>
                  <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                    <Descriptions.Item
                      label={
                        <Space size={4}>
                          <span>{param.param_name}</span>
                          {param.description && (
                            <Tag
                              style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
                              color="processing"
                            >
                              {param.description.length > 20 ? `${param.description.slice(0, 18)}...` : param.description}
                            </Tag>
                          )}
                        </Space>
                      }
                    >
                      <span style={valueStyle}>{valueDisplay}</span>
                    </Descriptions.Item>
                  </Descriptions>
                </Col>
              );
            })}
          </Row>
        ) : loadingParams ? (
          <div style={{ textAlign: 'center', padding: 30 }}>
            <Tag icon={<CodeOutlined />} color="processing">{t('loading')}</Tag>
          </div>
        ) : Object.keys(currentStrategyParams).length > 0 ? (
          <Row gutter={[24, 16]}>
            {Object.entries(currentStrategyParams).map(([key, value]) => (
              <Col key={key} xs={24} sm={12} md={8}>
                <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                  <Descriptions.Item label={key}>
                    <span style={{ fontWeight: 500 }}>{String(value)}</span>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            ))}
          </Row>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
            <Tag>{t('no_configurable_params')}</Tag>
          </div>
        )}
      </Card>
    </div>
  );
};

export default WorkerParamsTab;
