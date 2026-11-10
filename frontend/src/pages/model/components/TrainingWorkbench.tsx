import { useRef, useState } from 'react';
import { Alert, App as AntdApp, Button, Card, Flex, Space } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { getAccessToken } from '@/utils/tokenManager';
import RLTrainConfigForm, { RLTrainConfig } from './RLTrainConfigForm';
import RLTrainingProgress, { TrainingProgress } from './RLTrainingProgress';
import RLTrainingResult, { TrainingResult } from './RLTrainingResult';

interface TrainingWorkbenchProps {
  // 训练成功 → ModelHub 切到模型总表 Tab 并刷新列表
  onTrainSuccess: () => void;
}

// 训练工作台：迁自 RLTrainingPage 的主训练流程（去掉模型列表 / 回测区，那两块职责归统一模型总表）
export default function TrainingWorkbench({ onTrainSuccess }: TrainingWorkbenchProps) {
  const { message } = AntdApp.useApp();
  const [training, setTraining] = useState(false);
  const [progress, setProgress] = useState<TrainingProgress | null>(null);
  const [result, setResult] = useState<TrainingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [totalTimesteps, setTotalTimesteps] = useState(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleStartTraining = async (values: RLTrainConfig) => {
    setTraining(true);
    setProgress(null);
    setResult(null);
    setError(null);
    setTotalTimesteps(values.timesteps);

    abortControllerRef.current = new AbortController();

    try {
      // 后端仅有同步训练端点 /api/v1/rl/train（无 SSE 流，故无进度轮询），
      // 训练是长任务，保持 fetch（axios 默认 30s 超时会中断训练），手动带 Authorization
      const response = await fetch('/api/v1/rl/train', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getAccessToken()}`,
        },
        // 表单的 learning_rate/initial_capital 等字段后端 TrainRequest 暂不消费，只传认识的字段
        body: JSON.stringify({
          algorithm: values.algorithm,
          symbol: values.symbol,
          interval: values.interval,
          total_timesteps: values.timesteps,
          reward_type: values.reward,
          walk_forward: values.walk_forward,
        }),
        signal: abortControllerRef.current.signal,
      });

      const payload = await response.json();
      // HTTPException（鉴权/校验失败）返回 {detail}，业务响应返回 {code, message, data}
      if (payload.code !== 0) {
        throw new Error(payload.message || payload.detail || '训练失败');
      }

      const trained: TrainingResult = {
        model_id: payload.data?.model_id ?? '',
        status: payload.data?.status ?? 'completed',
        metrics: payload.data?.metrics ?? {},
      };
      setResult(trained);
      message.success(`训练完成，模型: ${trained.model_id}`);
    } catch (err) {
      // fetch 中断抛 AbortError（DOMException），业务异常为 Error，统一按 { name, message } 读取
      const e = err as { name?: string; message?: string };
      if (e.name === 'AbortError') {
        setError('训练已取消');
      } else {
        const msg = e.message || '训练失败';
        setError(msg);
        message.error(msg);
      }
    } finally {
      setTraining(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancelTraining = () => {
    abortControllerRef.current?.abort();
    setTraining(false);
    setProgress(null);
    message.info('训练已取消');
  };

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }} className="w-full">
      <Card
        title={
          <span>
            <ExperimentOutlined /> 强化学习训练配置
          </span>
        }
      >
        <RLTrainConfigForm
          onSubmit={handleStartTraining}
          training={training}
          backtesting={false}
          onCancel={handleCancelTraining}
        />
      </Card>

      {error && (
        <Alert
          type="error"
          showIcon
          title="训练失败"
          description={error}
          closable
          onClose={() => setError(null)}
        />
      )}

      {training && (
        <RLTrainingProgress progress={progress} totalTimesteps={totalTimesteps} />
      )}

      {result && (
        <Flex vertical gap={12}>
          <RLTrainingResult result={result} />
          {result.status === 'completed' && (
            <Alert
              type="success"
              showIcon
              title="训练完成，产物已写入模型目录"
              action={
                <Button size="small" type="primary" onClick={onTrainSuccess}>
                  前往模型总表查看
                </Button>
              }
            />
          )}
        </Flex>
      )}
    </Space>
  );
}
