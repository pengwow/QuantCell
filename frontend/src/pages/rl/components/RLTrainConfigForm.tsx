import { Form, Select, InputNumber, Button, Space, Typography, Switch } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';

const { Option } = Select;

export interface RLTrainConfig {
  symbol: string;
  interval: string;
  algorithm: string;
  timesteps: number;
  reward: string;
  learning_rate: number;
  initial_capital: number;
  transaction_cost: number;
  lookback_days: number;
  walk_forward: boolean;
  hpo: boolean;
}

interface RLTrainConfigFormProps {
  onSubmit: (values: RLTrainConfig) => void;
  training: boolean;
  backtesting: boolean;
  onCancel?: () => void;
}

export default function RLTrainConfigForm({
  onSubmit,
  training,
  backtesting,
  onCancel,
}: RLTrainConfigFormProps) {
  const [form] = Form.useForm<RLTrainConfig>();

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{
        algorithm: 'ppo',
        symbol: 'BTCUSDT',
        interval: '1h',
        timesteps: 10000,
        reward: 'pnl',
        learning_rate: 3e-4,
        initial_capital: 100000,
        transaction_cost: 0.001,
        lookback_days: 90,
        walk_forward: false,
        hpo: false,
      }}
      onFinish={onSubmit}
    >
      <Form.Item label="算法" name="algorithm" rules={[{ required: true }]}>
        <Select>
          <Option value="ppo">PPO (Proximal Policy Optimization)</Option>
          <Option value="sac">SAC (Soft Actor-Critic)</Option>
          <Option value="a2c">A2C (Advantage Actor-Critic)</Option>
        </Select>
      </Form.Item>

      <Form.Item label="交易对" name="symbol" rules={[{ required: true }]}>
        <Select>
          <Option value="BTCUSDT">BTCUSDT</Option>
          <Option value="ETHUSDT">ETHUSDT</Option>
          <Option value="SOLUSDT">SOLUSDT</Option>
        </Select>
      </Form.Item>

      <Form.Item label="K线周期" name="interval">
        <Select>
          <Option value="15m">15分钟</Option>
          <Option value="1h">1小时</Option>
          <Option value="4h">4小时</Option>
          <Option value="1d">1天</Option>
        </Select>
      </Form.Item>

      <Form.Item label="训练步数" name="timesteps" rules={[{ required: true }]}>
        <InputNumber min={100} max={1000000} step={1000} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label="奖励函数" name="reward">
        <Select>
          <Option value="pnl">PnL (盈亏)</Option>
          <Option value="sharpe">Sharpe Ratio (夏普比率)</Option>
          <Option value="sortino">Sortino Ratio (索提诺比率)</Option>
        </Select>
      </Form.Item>

      <Form.Item label="学习率" name="learning_rate">
        <InputNumber min={1e-6} max={1e-2} step={1e-5} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label="初始资金" name="initial_capital">
        <InputNumber min={1000} max={10000000} step={1000} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label="交易费率" name="transaction_cost">
        <InputNumber min={0} max={0.1} step={0.0001} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label="回看天数" name="lookback_days">
        <InputNumber min={1} max={365} step={1} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label="Walk-Forward 验证" name="walk_forward" valuePropName="checked">
        <Switch disabled />
      </Form.Item>

      <Form.Item label="超参数优化 (HPO)" name="hpo" valuePropName="checked">
        <Switch disabled />
      </Form.Item>

      <Form.Item>
        <Space style={{ width: '100%' }}>
          <Button
            type="primary"
            htmlType="submit"
            icon={<ExperimentOutlined />}
            loading={training}
            disabled={backtesting}
            style={{ flex: 1 }}
          >
            {training ? '训练中...' : '开始训练'}
          </Button>
          {training && onCancel && (
            <Button onClick={onCancel}>取消</Button>
          )}
        </Space>
      </Form.Item>
    </Form>
  );
}
