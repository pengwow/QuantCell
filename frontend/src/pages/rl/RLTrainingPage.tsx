/**
 * RLTrainingPage — RL training configuration and monitoring page.
 *
 * Allows users to configure and start RL training, view progress,
 * and compare trained models.
 */
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
} from 'antd';
import { PlayCircleOutlined, ExperimentOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;
const { Option } = Select;

interface RLTrainConfig {
  algorithm: 'ppo' | 'sac' | 'dqn';
  total_timesteps: number;
  reward_type: string;
  walk_forward: boolean;
  hpo: boolean;
}

export default function RLTrainingPage() {
  const [form] = Form.useForm<RLTrainConfig>();
  const [training, setTraining] = useState(false);

  const handleStartTraining = async (values: RLTrainConfig) => {
    setTraining(true);
    try {
      const response = await fetch('/api/v2/rl/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });

      if (response.ok) {
        const data = await response.json();
        message.success(`训练已启动，任务ID: ${data.task_id}`);
      } else {
        message.error('训练启动失败');
      }
    } catch {
      message.error('网络错误，请检查连接');
    } finally {
      setTraining(false);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <ExperimentOutlined /> RL 训练
      </Title>
      <Text type="secondary">
        配置并启动强化学习训练，支持 PPO/SAC/DQN 算法。
      </Text>

      <Card style={{ marginTop: 24, maxWidth: 600 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            algorithm: 'ppo',
            total_timesteps: 10000,
            reward_type: 'pnl',
            walk_forward: false,
            hpo: false,
          }}
          onFinish={handleStartTraining}
        >
          <Form.Item
            label="算法"
            name="algorithm"
            rules={[{ required: true }]}
          >
            <Select>
              <Option value="ppo">PPO (Proximal Policy Optimization)</Option>
              <Option value="sac">SAC (Soft Actor-Critic)</Option>
              <Option value="dqn">DQN (Deep Q-Network)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="训练步数"
            name="total_timesteps"
            rules={[{ required: true }]}
          >
            <InputNumber min={1000} max={1000000} step={1000} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            label="奖励函数"
            name="reward_type"
          >
            <Select>
              <Option value="pnl">PnL (盈亏)</Option>
              <Option value="sharpe">Sharpe Ratio (夏普比率)</Option>
              <Option value="sortino">Sortino Ratio (索提诺比率)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="Walk-Forward 验证"
            name="walk_forward"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="超参数优化 (HPO)"
            name="hpo"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<PlayCircleOutlined />}
                loading={training}
              >
                开始训练
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
