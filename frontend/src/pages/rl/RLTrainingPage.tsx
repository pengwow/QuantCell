import { useState } from 'react';
import {
  Card,
  Form,
  Select,
  InputNumber,
  Button,
  Space,
  Typography,
  Switch,
  message,
  Descriptions,
  Alert,
  Progress,
  Statistic,
  Row,
  Col,
} from 'antd';
import {
  PlayCircleOutlined,
  ExperimentOutlined,
  TrophyOutlined,
  FieldTimeOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import PageContainer from '../../components/PageContainer';
import { rlApi, type RLTrainResult } from '../../api/rlApi';

const { Option } = Select;
const { Text } = Typography;

interface RLTrainConfig {
  algorithm: string;
  data_source: string;
  total_timesteps: number;
  reward_type: string;
  walk_forward: boolean;
  hpo: boolean;
}

const METRIC_LABELS: Record<string, string> = {
  total_reward: '累计奖励',
  steps: '训练步数',
  algorithm: '算法',
  episodes: '训练回合数',
  avg_episode_reward: '平均回合奖励',
  best_episode_reward: '最佳回合奖励',
  elapsed_seconds: '耗时(秒)',
};

export default function RLTrainingPage() {
  const [form] = Form.useForm<RLTrainConfig>();
  const [training, setTraining] = useState(false);
  const [result, setResult] = useState<RLTrainResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleStartTraining = async (values: RLTrainConfig) => {
    setTraining(true);
    setResult(null);
    setError(null);
    try {
      const data = await rlApi.train(values);
      setResult(data);
      message.success(`训练完成，模型ID: ${data.model_id}`);
    } catch (err: any) {
      const msg = err?.message || '训练失败';
      setError(msg);
      message.error(msg);
    } finally {
      setTraining(false);
    }
  };

  const renderMetricValue = (key: string, value: number | string) => {
    if (typeof value === 'number') {
      if (key.includes('reward')) {
        return <Text strong style={{ color: value >= 0 ? '#52c41a' : '#cf1322' }}>{value.toFixed(2)}</Text>;
      }
      if (key === 'elapsed_seconds') {
        return <Text>{value.toFixed(1)}s</Text>;
      }
      return <Text>{value.toLocaleString()}</Text>;
    }
    return <Text>{String(value)}</Text>;
  };

  return (
    <PageContainer title="RL 训练">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* 左侧: 训练配置 */}
        <Card
          title={
            <Space>
              <ExperimentOutlined />
              强化学习训练配置
            </Space>
          }
        >
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              algorithm: 'ppo',
              data_source: 'BTCUSDT_1h',
              total_timesteps: 1000,
              reward_type: 'pnl',
              walk_forward: false,
              hpo: false,
            }}
            onFinish={handleStartTraining}
          >
            <Form.Item label="算法" name="algorithm" rules={[{ required: true }]}>
              <Select>
                <Option value="ppo">PPO (Proximal Policy Optimization)</Option>
                <Option value="sac">SAC (Soft Actor-Critic)</Option>
                <Option value="dqn">DQN (Deep Q-Network)</Option>
              </Select>
            </Form.Item>

            <Form.Item label="数据源" name="data_source">
              <Select>
                <Option value="BTCUSDT_1h">BTCUSDT 1h</Option>
                <Option value="ETHUSDT_1h">ETHUSDT 1h</Option>
                <Option value="BTCUSDT_4h">BTCUSDT 4h</Option>
              </Select>
            </Form.Item>

            <Form.Item label="训练步数" name="total_timesteps" rules={[{ required: true }]}>
              <InputNumber min={100} max={1000000} step={100} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item label="奖励函数" name="reward_type">
              <Select>
                <Option value="pnl">PnL (盈亏)</Option>
                <Option value="sharpe">Sharpe Ratio (夏普比率)</Option>
                <Option value="sortino">Sortino Ratio (索提诺比率)</Option>
              </Select>
            </Form.Item>

            <Form.Item label="Walk-Forward 验证" name="walk_forward" valuePropName="checked">
              <Switch />
            </Form.Item>

            <Form.Item label="超参数优化 (HPO)" name="hpo" valuePropName="checked">
              <Switch />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                icon={<PlayCircleOutlined />}
                loading={training}
                block
              >
                {training ? '训练中...' : '开始训练'}
              </Button>
            </Form.Item>
          </Form>
        </Card>

        {/* 右侧: 训练结果 */}
        <div>
          {error && (
            <Alert
              type="error"
              message="训练失败"
              description={error}
              style={{ marginBottom: 16 }}
              closable
              onClose={() => setError(null)}
            />
          )}

          {training && (
            <Card style={{ marginBottom: 16 }}>
              <div style={{ textAlign: 'center', padding: 20 }}>
                <Progress type="circle" percent={50} status="active" />
                <div style={{ marginTop: 16 }}>
                  <Text type="secondary">训练进行中，请查看后端日志...</Text>
                </div>
              </div>
            </Card>
          )}

          {result && (
            <>
              {/* 概览卡片 */}
              <Card title="训练概览" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic
                      title="累计奖励"
                      value={result.metrics.total_reward || 0}
                      precision={2}
                      valueStyle={{ color: (result.metrics.total_reward || 0) >= 0 ? '#3f8600' : '#cf1322' }}
                      prefix={<TrophyOutlined />}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="训练步数"
                      value={result.metrics.steps || 0}
                      prefix={<LineChartOutlined />}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="耗时"
                      value={result.metrics.elapsed_seconds || 0}
                      precision={1}
                      suffix="秒"
                      prefix={<FieldTimeOutlined />}
                    />
                  </Col>
                </Row>
              </Card>

              {/* 详细指标 */}
              <Card title="详细指标">
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="模型 ID">
                    <Text code>{result.model_id}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Text type="success">{result.status}</Text>
                  </Descriptions.Item>
                  {Object.entries(result.metrics).map(([key, value]) => (
                    <Descriptions.Item key={key} label={METRIC_LABELS[key] || key}>
                      {renderMetricValue(key, value as number | string)}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              </Card>
            </>
          )}

          {!training && !result && !error && (
            <Card>
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                <ExperimentOutlined style={{ fontSize: 48, marginBottom: 16 }} />
                <div>配置训练参数后点击"开始训练"</div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </PageContainer>
  );
}
