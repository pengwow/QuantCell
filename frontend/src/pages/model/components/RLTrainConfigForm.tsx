import { Form, Select, InputNumber, Button, Space, Switch } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();

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
      <Form.Item label={t('rlcf_label_algorithm')} name="algorithm" rules={[{ required: true }]}>
        <Select>
          <Option value="ppo">PPO (Proximal Policy Optimization)</Option>
          <Option value="sac">SAC (Soft Actor-Critic)</Option>
          <Option value="a2c">A2C (Advantage Actor-Critic)</Option>
        </Select>
      </Form.Item>

      <Form.Item label={t('rlcf_label_symbol')} name="symbol" rules={[{ required: true }]}>
        <Select>
          <Option value="BTCUSDT">BTCUSDT</Option>
          <Option value="ETHUSDT">ETHUSDT</Option>
          <Option value="SOLUSDT">SOLUSDT</Option>
        </Select>
      </Form.Item>

      <Form.Item label={t('rlcf_label_interval')} name="interval">
        <Select>
          <Option value="15m">{t('rlcf_opt_15m')}</Option>
          <Option value="1h">{t('rlcf_opt_1h')}</Option>
          <Option value="4h">{t('rlcf_opt_4h')}</Option>
          <Option value="1d">{t('rlcf_opt_1d')}</Option>
        </Select>
      </Form.Item>

      <Form.Item label={t('rlcf_label_timesteps')} name="timesteps" rules={[{ required: true }]}>
        <InputNumber min={100} max={1000000} step={1000} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label={t('rlcf_label_reward')} name="reward">
        <Select>
          <Option value="pnl">{t('rlcf_opt_pnl')}</Option>
          <Option value="sharpe">{t('rlcf_opt_sharpe')}</Option>
          <Option value="sortino">{t('rlcf_opt_sortino')}</Option>
        </Select>
      </Form.Item>

      <Form.Item label={t('rlcf_label_learning_rate')} name="learning_rate">
        <InputNumber min={1e-6} max={1e-2} step={1e-5} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label={t('rlcf_label_initial_capital')} name="initial_capital">
        <InputNumber min={1000} max={10000000} step={1000} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label={t('rlcf_label_fee')} name="transaction_cost">
        <InputNumber min={0} max={0.1} step={0.0001} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label={t('rlcf_label_lookback')} name="lookback_days">
        <InputNumber min={1} max={365} step={1} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item label={t('rlcf_label_walk_forward')} name="walk_forward" valuePropName="checked">
        <Switch disabled />
      </Form.Item>

      <Form.Item label={t('rlcf_label_hpo')} name="hpo" valuePropName="checked">
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
            {training ? t('rlcf_btn_training') : t('rlcf_btn_start')}
          </Button>
          {training && onCancel && (
            <Button onClick={onCancel}>{t('rlcf_btn_cancel')}</Button>
          )}
        </Space>
      </Form.Item>
    </Form>
  );
}
