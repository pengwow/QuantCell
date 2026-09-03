import { Card, Statistic, Row, Col, Descriptions, Tag, Typography } from 'antd';
import { TrophyOutlined, LineChartOutlined } from '@ant-design/icons';

const { Text } = Typography;

// 对齐后端 /api/v2/rl/train 响应结构：{ model_id, status, metrics }
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
  // metrics 键缺失时兜底为 0，避免 undefined 传入 Statistic
  const num = (k: string) => (typeof m[k] === 'number' ? m[k] : 0);

  return (
    <>
      <Card title="训练结果" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic
              title="夏普比率"
              value={num('sharpe_ratio')}
              precision={2}
              valueStyle={{ color: num('sharpe_ratio') >= 0 ? '#3f8600' : '#cf1322' }}
              prefix={<LineChartOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic title="总收益率" value={num('total_return_pct')} precision={2} suffix="%" />
          </Col>
          <Col span={8}>
            <Statistic title="胜率" value={num('win_rate') * 100} precision={1} suffix="%" prefix={<TrophyOutlined />} />
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={8}>
            <Statistic title="总盈亏" value={num('total_pnl')} precision={2} />
          </Col>
          <Col span={8}>
            <Statistic
              title="最大回撤"
              value={num('max_drawdown_pct')}
              precision={2}
              suffix="%"
              valueStyle={{ color: '#cf1322' }}
            />
          </Col>
          <Col span={8}>
            <Statistic title="盈亏比" value={num('profit_factor')} precision={2} />
          </Col>
        </Row>
      </Card>

      <Card title="模型信息">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="模型 ID">
            <Text code>{result.model_id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color="green">{result.status.toUpperCase()}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="交易次数">
            {num('num_trades')}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </>
  );
}
