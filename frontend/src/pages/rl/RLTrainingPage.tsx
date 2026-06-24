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
} from 'antd';
import { PlayCircleOutlined, ExperimentOutlined } from '@ant-design/icons';
import PageContainer from '../../components/PageContainer';
import { rlApi, type RLTrainResult } from '../../api/rlApi';

const { Option } = Select;

interface RLTrainConfig {
  algorithm: string;
  data_source: string;
  total_timesteps: number;
  reward_type: string;
  walk_forward: boolean;
  hpo: boolean;
}

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

  return (
    <PageContainer title="RL 训练">
      <Card
        title={
          <Space>
            <ExperimentOutlined />
            强化学习训练配置
          </Space>
        }
        style={{ maxWidth: 600 }}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            algorithm: 'ppo',
            data_source: 'BTCUSDT_1h',
            total_timesteps: 100000,
            reward_type: 'sharpe',
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
            <InputNumber min={1000} max={1000000} step={1000} style={{ width: '100%' }} />
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
            >
              开始训练
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {error && (
        <Alert
          type="error"
          message="训练失败"
          description={error}
          style={{ marginTop: 16, maxWidth: 600 }}
          closable
          onClose={() => setError(null)}
        />
      )}

      {result && (
        <Card title="训练结果" style={{ marginTop: 16, maxWidth: 600 }}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="模型 ID">{result.model_id}</Descriptions.Item>
            <Descriptions.Item label="状态">{result.status}</Descriptions.Item>
            {Object.entries(result.metrics).map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                {typeof value === 'number' ? value.toFixed(4) : String(value)}
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>
      )}
    </PageContainer>
  );
}
