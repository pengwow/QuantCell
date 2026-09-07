import { useTranslation } from 'react-i18next';
import {
  Card,
  Row,
  Col,
  Descriptions,
  Tag,
  Space,
} from 'antd';
import type { Worker as WorkerType, StrategyParameter } from '../../types/worker';
import { CodeOutlined, TagOutlined } from '@ant-design/icons';
import { strategyApi } from '../../api';
import { useState, useEffect } from 'react';

interface WorkerParamsTabProps {
  worker: WorkerType;
}

const WorkerParamsTab: React.FC<WorkerParamsTabProps> = ({ worker }) => {
  const { t } = useTranslation();

  // 从 config 中提取策略参数（如果存在）
  const config = worker.config || {};
  const tradingConfig = worker.trading_config || {};

  // 动态策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);

  // Worker 实际配置的策略参数值（从 config 或 trading_config 获取）
  const currentStrategyParams: Record<string, any> = (
    (tradingConfig as Record<string, any>)?.strategy_params ||
    config?.strategy_params ||
    {}
  );

  // 加载策略参数定义
  useEffect(() => {
    const loadParams = async () => {
      if (!worker.strategy_info?.id) {
        setStrategyParams([]);
        return;
      }
      setLoadingParams(true);
      try {
        const response = await strategyApi.getStrategyParams(worker.strategy_info.id) as any;
        let params: StrategyParameter[] = [];
        if (Array.isArray(response)) {
          params = response;
        } else if (response?.data && Array.isArray(response.data)) {
          params = response.data;
        } else if (response?.data?.parameters && Array.isArray(response.data.parameters)) {
          params = response.data.parameters;
        }
        setStrategyParams(params);
      } catch (error) {
        console.error('加载策略参数失败:', error);
        setStrategyParams([]);
      } finally {
        setLoadingParams(false);
      }
    };
    loadParams();
  }, [worker.strategy_info?.id]);

  return (
    <div>
      {/* 策略信息 */}
      {worker.strategy_info && (
        <Card
          title={
            <Space>
              <CodeOutlined />
              <span>{t('strategy_info') || '策略信息'}</span>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Row gutter={[24, 16]}>
            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_name') || '策略名称'}>
                  <Tag color="blue">{worker.strategy_info.name}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_type') || '策略类型'}>
                  <Tag icon={<TagOutlined />} color={worker.strategy_info.strategy_type === 'default' ? 'green' : 'purple'}>
                    {worker.strategy_info.strategy_type === 'default'
                      ? (t('default_strategy') || '默认策略')
                      : (t('legacy_strategy') || '旧版策略')}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                <Descriptions.Item label={t('strategy_version') || '策略版本'}>
                  <span style={{ fontWeight: 500 }}>v{worker.strategy_info.version}</span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            {worker.strategy_info.description && (
              <Col span={24}>
                <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
                  <Descriptions.Item label={t('strategy_description') || '策略描述'}>
                    <span>{worker.strategy_info.description}</span>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
            )}
          </Row>
        </Card>
      )}

      {/* 基础配置 */}
      <Card
        title={
          <Space>
            <span>⚙️</span>
            <span>{t('basic_config') || '基础配置'}</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[24, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('symbol') || '交易对'}>
                <Tag color="blue">{worker.symbols?.join(', ') || '-'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('exchange') || '交易所'}>
                <Tag>{worker.exchange}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('timeframe') || 'K线周期'}>
                <Tag color="blue">{worker.timeframe}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('leverage') || '杠杆倍数'}>
                <Tag color="orange">{config.leverage || `${config.leverage || '1'}x`}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('total_investment') || '总投入金额'}>
                <span style={{ fontWeight: 600, color: '#1890ff' }}>
                  ${config.total_investment?.toFixed(2) || '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('order_type') || '下单方式'}>
                <Tag color="cyan">{config.order_type || t('market_order') || '市价单'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      {/* 策略参数 - 动态加载 */}
      <Card
        title={
          <Space>
            <span>📊</span>
            <span>{t('strategy_params') || '策略参数'}</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        {strategyParams.length > 0 ? (
          <Row gutter={[24, 16]}>
            {strategyParams.map((param) => {
              const currentValue = currentStrategyParams[param.param_name];
              const displayValue = currentValue ?? param.default_value ?? param.param_value ?? '-';
              let valueDisplay: React.ReactNode;
              const valueStyle: React.CSSProperties = { fontWeight: 500 };

              if (typeof displayValue === 'number' && param.param_type === 'float') {
                valueDisplay = typeof displayValue === 'number' ? displayValue.toFixed(2) : String(displayValue);
                if (param.param_name?.includes('loss') || param.param_name?.includes('stop')) {
                  valueStyle.color = '#ff4d4f';
                } else if (param.param_name?.includes('profit')) {
                  valueStyle.color = '#52c41a';
                }
              } else if (typeof displayValue === 'boolean') {
                valueDisplay = (
                  <Tag color={displayValue ? 'green' : 'red'}>
                    {displayValue ? '是' : '否'}
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
            <Tag icon={<CodeOutlined />} color="processing">加载中...</Tag>
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
            <Tag>该策略无可编辑参数</Tag>
          </div>
        )}
      </Card>

      {/* 风控参数 */}
      <Card
        title={
          <Space>
            <span>🛡️</span>
            <span>{t('risk_params') || '风控参数'}</span>
          </Space>
        }
      >
        <Row gutter={[24, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('max_drawdown') || '最大回撤限制'}>
                <span style={{ fontWeight: 500, color: '#ff4d4f' }}>
                  {config.max_drawdown_limit || '-'}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('max_position_size') || '最大仓位占比'}>
                <span style={{ fontWeight: 500 }}>
                  {config.max_position_size || '-'}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" styles={{ label: { color: '#666' } }}>
              <Descriptions.Item label={t('trailing_stop') || '移动止损'}>
                <span style={{ fontWeight: 500 }}>
                  {config.trailing_stop || '-'}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>
    </div>
  );
};

export default WorkerParamsTab;
