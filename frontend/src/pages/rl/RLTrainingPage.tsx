import { useState, useEffect, useRef } from 'react';
import { Card, Alert, message } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import PageContainer from '../../components/PageContainer';
import { rlApi } from '../../api/rlApi';
import { getAccessToken } from '../../utils/tokenManager';
import RLTrainConfigForm, { RLTrainConfig } from './components/RLTrainConfigForm';
import RLModelList, { RLModel } from './components/RLModelList';
import RLTrainingProgress, { TrainingProgress } from './components/RLTrainingProgress';
import RLTrainingResult, { TrainingResult } from './components/RLTrainingResult';
import RLBacktestResult, { BacktestResult } from './components/RLBacktestResult';

export default function RLTrainingPage() {
  const [training, setTraining] = useState(false);
  const [progress, setProgress] = useState<TrainingProgress | null>(null);
  const [result, setResult] = useState<TrainingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<RLModel[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [backtesting, setBacktesting] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [totalTimesteps, setTotalTimesteps] = useState(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 加载模型列表
  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      // 走 rlApi：baseURL=/api 补全为后端真实路由 /api/v2/rl/models，拦截器自动带 Authorization
      // 响应拦截器已解包 ApiResponse，直接得到 [{ name }] 数组
      const data = await rlApi.listModels();
      setModels((data || []).map((m: { name: string }) => ({ ...m, path: m.name, size_kb: 0 })));
    } catch (err) {
      console.error('加载模型列表失败:', err);
    }
  };

  const handleStartTraining = async (values: RLTrainConfig) => {
    setTraining(true);
    setProgress(null);
    setResult(null);
    setError(null);
    setBacktestResult(null);
    setTotalTimesteps(values.timesteps);

    abortControllerRef.current = new AbortController();

    try {
      // 后端仅有同步训练端点 /api/v2/rl/train（无 SSE 流），此前调用的 /api/rl/train/stream 从未存在
      // 训练是长任务，保持 fetch（axios 默认 30s 超时会中断训练），手动带 Authorization
      const response = await fetch('/api/v2/rl/train', {
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

      const result: TrainingResult = {
        model_id: payload.data?.model_id ?? '',
        status: payload.data?.status ?? 'completed',
        metrics: payload.data?.metrics ?? {},
      };
      setResult(result);
      message.success(`训练完成，模型: ${result.model_id}`);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setError('训练已取消');
      } else {
        const msg = err?.message || '训练失败';
        setError(msg);
        message.error(msg);
      }
    } finally {
      setTraining(false);
      abortControllerRef.current = null;
      // 训练完成后刷新模型列表
      fetchModels();
    }
  };

  const handleCancelTraining = () => {
    abortControllerRef.current?.abort();
    setTraining(false);
    setProgress(null);
    message.info('训练已取消');
  };

  const handleBacktest = async () => {
    if (!selectedModel) {
      message.warning('请选择一个模型');
      return;
    }

    setBacktesting(true);
    setBacktestResult(null);

    try {
      const response = await fetch('/api/rl/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_path: selectedModel,
          symbol: 'BTCUSDT',
          interval: '1h',
          lookback_days: 30,
        }),
      });

      const data = await response.json();
      if (data.code === 0) {
        setBacktestResult(data.data);
        message.success('回测完成');
      } else {
        throw new Error(data.message || '回测失败');
      }
    } catch (err: any) {
      message.error(err?.message || '回测失败');
    } finally {
      setBacktesting(false);
    }
  };

  const handleDeleteModel = async (modelName: string) => {
    try {
      const response = await fetch(`/api/rl/models/${modelName}`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (data.code === 0) {
        message.success(`模型 ${modelName} 已删除`);
        fetchModels();
        if (selectedModel.includes(modelName)) {
          setSelectedModel('');
        }
      } else {
        message.error(data.message || '删除失败');
      }
    } catch (err: any) {
      message.error(err?.message || '删除失败');
    }
  };

  return (
    <PageContainer title="RL 训练">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* 左侧: 训练配置 + 模型列表 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 训练配置 */}
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
              backtesting={backtesting}
              onCancel={handleCancelTraining}
            />
          </Card>

          {/* 模型列表 */}
          <RLModelList
            models={models}
            selectedModel={selectedModel}
            onSelectModel={setSelectedModel}
            onDeleteModel={handleDeleteModel}
            onRefresh={fetchModels}
            onBacktest={handleBacktest}
            backtesting={backtesting}
            training={training}
          />
        </div>

        {/* 右侧: 训练进度 + 结果 */}
        <div>
          {/* 错误提示 */}
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

          {/* 训练进度 */}
          {training && (
            <RLTrainingProgress
              progress={progress}
              totalTimesteps={totalTimesteps}
            />
          )}

          {/* 训练结果 */}
          {result && <RLTrainingResult result={result} />}

          {/* 回测结果 */}
          {backtestResult && <RLBacktestResult result={backtestResult} />}

          {/* 空状态 */}
          {!training && !result && !error && !backtestResult && (
            <Card>
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                <ExperimentOutlined style={{ fontSize: 48, marginBottom: 16 }} />
                <div>配置训练参数后点击"开始训练"</div>
                <div style={{ marginTop: 8 }}>或从下方模型列表选择模型进行回测</div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </PageContainer>
  );
}
