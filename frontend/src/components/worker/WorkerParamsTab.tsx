import { useTranslation } from 'react-i18next';
import {
  Card,
  Row,
  Col,
  Descriptions,
  Tag,
  Space,
} from 'antd';
import type { Worker as WorkerType } from '../../types/worker';
import { CodeOutlined, TagOutlined } from '@ant-design/icons';

interface WorkerParamsTabProps {
  worker: WorkerType;
}

const WorkerParamsTab: React.FC<WorkerParamsTabProps> = ({ worker }) => {
  const { t } = useTranslation();

  // 从 config 中提取策略参数（如果存在）
  const config = worker.config || {};

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
              <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
                <Descriptions.Item label={t('strategy_name') || '策略名称'}>
                  <Tag color="blue">{worker.strategy_info.name}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            <Col xs={24} sm={12} md={8}>
              <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
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
              <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
                <Descriptions.Item label={t('strategy_version') || '策略版本'}>
                  <span style={{ fontWeight: 500 }}>v{worker.strategy_info.version}</span>
                </Descriptions.Item>
              </Descriptions>
            </Col>

            {worker.strategy_info.description && (
              <Col span={24}>
                <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
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
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('symbol') || '交易对'}>
                <Tag color="blue">{worker.symbols?.join(', ') || '-'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('exchange') || '交易所'}>
                <Tag>{worker.exchange}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('timeframe') || 'K线周期'}>
                <Tag color="blue">{worker.timeframe}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('leverage') || '杠杆倍数'}>
                <Tag color="orange">{config.leverage || `${config.leverage || '1'}x`}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('total_investment') || '总投入金额'}>
                <span style={{ fontWeight: 600, color: '#1890ff' }}>
                  ${config.total_investment?.toFixed(2) || '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('order_type') || '下单方式'}>
                <Tag color="cyan">{config.order_type || t('market_order') || '市价单'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      {/* 策略参数 */}
      <Card
        title={
          <Space>
            <span>📊</span>
            <span>{t('strategy_params') || '策略参数'}</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[24, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('initial_amount') || '首单金额（自动计算）'}>
                <span style={{ fontWeight: 500 }}>
                  ${config.initial_amount?.toFixed(2) || '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('multiplier') || '加仓倍数'}>
                <span style={{ fontWeight: 500, color: '#52c41a' }}>
                  {config.multiplier?.toFixed(2) || '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('max_layers') || '最大加仓层数'}>
                <span style={{ fontWeight: 500, color: '#52c41a' }}>
                  {config.max_layers || '-'}
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('take_profit_pct') || '相对持仓均价止盈%'}>
                <span style={{ fontWeight: 500 }}>{config.take_profit_pct || '-'}%</span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('stop_loss_pct') || '相对持仓均价止损%'}>
                <span style={{ fontWeight: 500, color: '#ff4d4f' }}>
                  {config.stop_loss_pct || '-'}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('direction') || '交易方向'}>
                <Tag color={config.direction === 'long' ? 'green' : 'red'}>
                  {config.direction === 'long'
                    ? (t('long') || '做多')
                    : config.direction === 'short'
                    ? (t('short') || '做空')
                    : (t('both') || '多（连跌加仓）')
                  }
                </Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
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
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('max_drawdown') || '最大回撤限制'}>
                <span style={{ fontWeight: 500, color: '#ff4d4f' }}>
                  {config.max_drawdown_limit || '-'}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
              <Descriptions.Item label={t('max_position_size') || '最大仓位占比'}>
                <span style={{ fontWeight: 500 }}>
                  {config.max_position_size || '-'}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          <Col xs={24} sm={12} md={8}>
            <Descriptions column={1} size="small" labelStyle={{ color: '#666' }}>
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
