import { Card, Statistic, Row, Col, Descriptions, Tag, Typography } from 'antd';
import { TrophyOutlined, LineChartOutlined, FieldTimeOutlined } from '@ant-design/icons';

const { Text } = Typography;

export interface TrainingResult {
  model_path: string;
  model_name: string;
  total_timesteps: number;
  training_time_secs: number;
  algorithm: string;
  symbol: string;
  eval_reward_mean: number;
  eval_reward_std: number;
}

interface RLTrainingResultProps {
  result: TrainingResult;
}

export default function RLTrainingResult({ result }: RLTrainingResultProps) {
  return (
    <>
      <Card title="训练结果" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic
              title="评估奖励均值"
              value={result.eval_reward_mean}
              precision={4}
              valueStyle={{ color: result.eval_reward_mean >= 0 ? '#3f8600' : '#cf1322' }}
              prefix={<TrophyOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="训练步数"
              value={result.total_timesteps}
              prefix={<LineChartOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="耗时"
              value={result.training_time_secs}
              precision={1}
              suffix="秒"
              prefix={<FieldTimeOutlined />}
            />
          </Col>
        </Row>
      </Card>

      <Card title="模型信息">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="模型名称">
            <Text code>{result.model_name}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="算法">
            <Tag color="blue">{result.algorithm.toUpperCase()}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="交易对">
            <Tag>{result.symbol}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="评估奖励标准差">
            {result.eval_reward_std.toFixed(4)}
          </Descriptions.Item>
          <Descriptions.Item label="模型路径" span={2}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {result.model_path}
            </Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </>
  );
}
