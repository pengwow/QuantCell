import { Card, Progress, Statistic, Row, Col, Typography } from 'antd';
import { LineChartOutlined, ClockCircleOutlined, FieldTimeOutlined, TrophyOutlined } from '@ant-design/icons';

const { Text } = Typography;

export interface TrainingProgress {
  type: 'start' | 'info' | 'progress' | 'complete' | 'error';
  message?: string;
  timestep?: number;
  episode?: number;
  episode_reward?: number;
  mean_reward?: number;
  elapsed_time?: number;
  total_timesteps?: number;
}

interface RLTrainingProgressProps {
  progress: TrainingProgress | null;
  totalTimesteps: number;
}

export default function RLTrainingProgress({ progress, totalTimesteps }: RLTrainingProgressProps) {
  const progressPercent = progress?.timestep && progress?.total_timesteps
    ? Math.min((progress.timestep / progress.total_timesteps) * 100, 100)
    : progress?.timestep && totalTimesteps
    ? Math.min((progress.timestep / totalTimesteps) * 100, 100)
    : 0;

  return (
    <Card style={{ marginBottom: 16 }}>
      <div style={{ marginBottom: 16 }}>
        <Progress
          percent={Math.round(progressPercent)}
          status={progress?.type === 'complete' ? 'success' : 'active'}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
        />
      </div>

      <div style={{ marginBottom: 12 }}>
        <Statistic
          title="当前步数"
          value={progress?.timestep || 0}
          prefix={<LineChartOutlined />}
          suffix={`/ ${totalTimesteps || 0}`}
        />
      </div>

      <Row gutter={16}>
        <Col span={12}>
          <Statistic
            title="当前Episode"
            value={progress?.episode || 0}
            prefix={<ClockCircleOutlined />}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title="耗时"
            value={progress?.elapsed_time || 0}
            precision={1}
            suffix="秒"
            prefix={<FieldTimeOutlined />}
          />
        </Col>
      </Row>

      {progress?.episode_reward !== undefined && (
        <div style={{ marginTop: 12 }}>
          <Statistic
            title="Episode奖励"
            value={progress.episode_reward}
            precision={2}
            valueStyle={{ color: progress.episode_reward >= 0 ? '#52c41a' : '#cf1322' }}
            prefix={<TrophyOutlined />}
          />
        </div>
      )}

      {progress?.message && (
        <div style={{ marginTop: 12, color: '#999' }}>
          {progress.message}
        </div>
      )}
    </Card>
  );
}
