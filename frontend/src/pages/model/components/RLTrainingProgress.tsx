import { Card, Progress } from 'antd';

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

  // §6.4 KPI 口径：label 11px fg-4 + mono 22px/650。涨绿跌红只用于有正负语义的奖励值，
  // 并发/步数/耗时是中性量，不染色。
  return (
    <Card className="qc-card">
      <div style={{ marginBottom: 16 }}>
        <Progress
          percent={Math.round(progressPercent)}
          status={progress?.type === 'complete' ? 'success' : 'active'}
          // strokeColor 走 CSS 变量（palette 运行时注入）；不用 JS 渐变插值，
          // demo .prog 进度条同为单色填充
          strokeColor="var(--qc-success)"
        />
      </div>

      <div className="qc-kpi-grid">
        <div className="qc-kpi">
          <div className="qc-kpi-lb">当前步数</div>
          <div className="qc-kpi-num">{progress?.timestep || 0}<span className="qc-kpi-sub" style={{ marginLeft: 4 }}>/ {totalTimesteps || 0}</span></div>
        </div>
        <div className="qc-kpi">
          <div className="qc-kpi-lb">当前Episode</div>
          <div className="qc-kpi-num">{progress?.episode || 0}</div>
        </div>
        <div className="qc-kpi">
          <div className="qc-kpi-lb">耗时</div>
          <div className="qc-kpi-num">{(progress?.elapsed_time || 0).toFixed(1)}<span className="qc-kpi-sub" style={{ marginLeft: 4 }}>秒</span></div>
        </div>
        <div className="qc-kpi">
          <div className="qc-kpi-lb">Episode奖励</div>
          <div className={`qc-kpi-num${(progress?.episode_reward ?? 0) >= 0 ? ' up' : ' down'}`}>{(progress?.episode_reward ?? 0).toFixed(2)}</div>
        </div>
      </div>

      {progress?.message && (
        <div style={{ marginTop: 12, color: 'var(--qc-text-secondary)' }}>
          {progress.message}
        </div>
      )}
    </Card>
  );
}
