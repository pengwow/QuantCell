import { Card, Statistic, Row, Col, Descriptions, Tag, Typography } from 'antd';
import { TrophyOutlined, LineChartOutlined } from '@ant-design/icons';
import { QUANT_COLORS } from '@/utils/colors';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

// 对齐后端 /api/v1/rl/train 响应结构：{ model_id, status, metrics }
export interface TrainingResult {
  model_id: string;
  status: string;
  metrics: Record<string, number>;
}

interface RLTrainingResultProps {
  result: TrainingResult;
}

export default function RLTrainingResult({ result }: RLTrainingResultProps) {
  const m = result.metrics || {};
  const { t } = useTranslation();
  // metrics 键缺失时兜底为 0，避免 undefined 传入 Statistic
  const num = (k: string) => (typeof m[k] === 'number' ? m[k] : 0);

  return (
    <>
      <Card title={t('rlres_title_result')}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic
              title={t('rlres_metric_sharpe')}
              value={num('sharpe_ratio')}
              precision={2}
              styles={{ content: { color: num('sharpe_ratio') >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative } }}
              prefix={<LineChartOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic title={t('rlres_metric_return')} value={num('total_return_pct')} precision={2} suffix="%" />
          </Col>
          <Col span={8}>
            <Statistic title={t('rlres_metric_win_rate')} value={num('win_rate') * 100} precision={1} suffix="%" prefix={<TrophyOutlined />} />
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={8}>
            <Statistic title={t('rlres_metric_pnl')} value={num('total_pnl')} precision={2} />
          </Col>
          <Col span={8}>
            <Statistic
              title={t('rlres_metric_max_dd')}
              value={num('max_drawdown_pct')}
              precision={2}
              suffix="%"
              styles={{ content: { color: QUANT_COLORS.negative } }}
            />
          </Col>
          <Col span={8}>
            <Statistic title={t('rlres_metric_pf')} value={num('profit_factor')} precision={2} />
          </Col>
        </Row>
      </Card>

      <Card title={t('rlres_title_model')}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label={t('rlres_label_model_id')}>
            <Text code>{result.model_id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label={t('rlres_label_status')}>
            <Tag color="green">{result.status.toUpperCase()}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('rlres_label_trades')}>
            {num('num_trades')}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </>
  );
}
