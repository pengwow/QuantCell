/**
 * 模型 Tab 顶部：训练任务面板（P1 batch2）。
 *
 * 后端契约（异步训练）：
 *   POST /rl/train/async → {task_id}
 *   GET  /rl/train/{task_id} → {status: queued|running|done|error|cancelled, stage, progress, message, error, model_path, meta_path, elapsed_ms}
 *   GET  /rl/train/{task_id}/events → SSE（state 快照 / log 行 / 15s ping）
 *   POST /rl/train/{task_id}/cancel
 *
 * 数据流：SSE 做即时更新，5s 轮询兜底（SSE 断流 / 首帧丢失 / 后端不支持 SSE 时不断档）。
 * 两条通道都只在「模型 Tab 激活 + 任务未终态」时跑（非激活 Tab 不跑，沿用工作台口径）。
 * 表单参数与模型页训练表单一致（TrainingWorkbench 的 RLTrainRequest 映射）。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { App, Alert, Button, Form, Input, InputNumber, Progress, Select, Spin, Switch } from 'antd';
import { useTranslation } from 'react-i18next';
import { rlApi, RLTrainStreamSSE } from '@/api/rlApi';
import type { RLTrainTask } from '@/api/rlApi';
import { useWorkbenchStore } from '../../store/workbenchStore';
import { TRAIN_STATUS_LEVELS, formatElapsed, isTrainTaskTerminal } from './workbenchFormat';

/** 任务 id 落 localStorage：跨页面刷新继续跟踪同一次训练（部署确认卡凭它关联最近一次训练） */
export const TASK_KEY = 'quantcell_workbench_rl_train_task';
const POLL_MS = 5000;

interface TrainFormValues {
  symbol: string;
  interval: string;
  algorithm: string;
  total_timesteps: number;
  reward_type: string;
  walk_forward: boolean;
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

export default function TrainPanel({ onTrained }: { onTrained?: () => void }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const isActive = useWorkbenchStore((s) => s.activeTab) === 'models';

  const [form] = Form.useForm<TrainFormValues>();
  const [taskId, setTaskId] = useState<string | null>(() => localStorage.getItem(TASK_KEY));
  const [task, setTask] = useState<RLTrainTask | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sseAlive, setSseAlive] = useState(false);
  const [, forceTick] = useState(0);

  /** 本地计时起点（后端 elapsed_ms 缺失时的兜底跑表） */
  const startedAtRef = useRef(0);
  /** 终态只提示一次（SSE 与轮询可能同时到达同一终态） */
  const notifiedRef = useRef('');

  const inFlight = !!taskId && !(task && isTrainTaskTerminal(task.status));

  useEffect(() => {
    if (taskId) localStorage.setItem(TASK_KEY, taskId);
    else localStorage.removeItem(TASK_KEY);
  }, [taskId]);

  const fetchTask = useCallback(async () => {
    if (!taskId) return;
    try {
      const next = await rlApi.getTrainTask(taskId);
      setTask(next);
      setLoadError(null);
    } catch (err) {
      // 后端未起 / 任务记录被清理：保留上次快照，仅提示；404 视为任务不存在，放弃跟踪
      setLoadError(errText(err));
      if ((err as { code?: number }).code === 404) {
        message.warning(t('wb_train_task_gone', { id: taskId }));
        setTaskId(null);
        setTask(null);
      }
    }
  }, [taskId, message, t]);

  // SSE：仅激活 Tab + 未终态时建流；终态/切走即断开
  useEffect(() => {
    if (!isActive || !taskId || !inFlight) return;
    const stream = new RLTrainStreamSSE(taskId, {
      onState: (patch) => setTask((prev) => ({ ...(prev ?? { task_id: taskId, status: 'queued' }), ...patch })),
      onOpen: () => setSseAlive(true),
      onError: () => setSseAlive(false),
    });
    // 延后一拍建连：StrictMode mount→cleanup→mount 时首个 EventSource 未建立即被 close
    // 会报 net::ERR_ABORTED（与 useWorkbenchData / WorkerLogsPanel 同款处理）
    const timer = window.setTimeout(() => stream.connect(), 0);
    return () => {
      window.clearTimeout(timer);
      stream.disconnect();
      setSseAlive(false);
    };
  }, [isActive, taskId, inFlight]);

  // 5s 轮询兜底：SSE 断流时仍能收敛到终态
  useEffect(() => {
    if (!isActive || !taskId || !inFlight) return;
    fetchTask();
    const timer = window.setInterval(fetchTask, POLL_MS);
    return () => window.clearInterval(timer);
  }, [isActive, taskId, inFlight, fetchTask]);

  // 未终态时 1s 重渲染，让「用时」持续走表
  useEffect(() => {
    if (!isActive || !inFlight) return;
    const timer = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isActive, inFlight]);

  // 终态一次性提示；成功触发模型列表刷新（新模型文件随后出现在总表）
  useEffect(() => {
    if (!taskId || !task || !isTrainTaskTerminal(task.status)) return;
    const key = `${taskId}:${task.status}`;
    if (notifiedRef.current === key) return;
    notifiedRef.current = key;
    if (task.status === 'done') {
      message.success(t('wb_train_done', { id: taskId }));
      onTrained?.();
    } else if (task.status === 'error') {
      message.error(t('wb_train_failed', { err: task.error || '-' }));
    } else {
      message.info(t('wb_train_cancelled_msg'));
    }
  }, [task, taskId, message, onTrained, t]);

  const handleStart = async (values: TrainFormValues) => {
    setSubmitting(true);
    try {
      const res = await rlApi.trainAsync({
        algorithm: values.algorithm,
        symbol: values.symbol.trim(),
        interval: values.interval,
        total_timesteps: values.total_timesteps,
        reward_type: values.reward_type,
        walk_forward: values.walk_forward,
      });
      const id = res?.task_id ? String(res.task_id) : '';
      if (!id) throw new Error(t('wb_train_bad_response'));
      startedAtRef.current = Date.now();
      notifiedRef.current = '';
      setTask(null);
      setLoadError(null);
      setTaskId(id);
      setFormOpen(false);
      message.success(t('wb_train_submitted', { id }));
    } catch (err) {
      message.error(t('wb_train_submit_failed', { err: errText(err) }));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelTask = async () => {
    if (!taskId) return;
    try {
      await rlApi.cancelTrainTask(taskId);
      // 乐观置为 cancelled 让按钮与进度条立刻进终态；以随后一次拉取为准
      setTask((prev) => (prev ? { ...prev, status: 'cancelled' } : prev));
      fetchTask();
    } catch (err) {
      message.error(t('wb_train_cancel_failed', { err: errText(err) }));
    }
  };

  /* 每渲染取一次当前时间：未终态时靠上面的 1s 定时器重渲染让用时走表 */
  const elapsedMs =
    task?.elapsed_ms != null
      ? task.elapsed_ms
      : startedAtRef.current && inFlight
        ? Date.now() - startedAtRef.current
        : null;

  const percent = task?.status === 'done' ? 100 : Math.round((task?.progress ?? 0) * 100);
  const barStatus =
    task?.status === 'error' ? 'exception' : task?.status === 'done' ? 'success' : task?.status === 'cancelled' ? 'normal' : 'active';

  return (
    <div className="wb-train">
      <div className="wb-train-head">
        <span className="wb-section-title wb-train-title">{t('wb_train_section')}</span>
        <span className="wb-train-actions">
          {taskId && inFlight && (
            <Button size="small" danger onClick={handleCancelTask}>
              {t('wb_train_cancel')}
            </Button>
          )}
          <Button size="small" type={formOpen ? 'default' : 'primary'} onClick={() => setFormOpen((o) => !o)}>
            {formOpen ? t('cancel') : t('wb_train_start')}
          </Button>
        </span>
      </div>

      {formOpen && (
        <Form<TrainFormValues>
          form={form}
          layout="vertical"
          size="small"
          className="wb-train-form"
          initialValues={{
            algorithm: 'ppo',
            symbol: 'BTCUSDT',
            interval: '1h',
            total_timesteps: 100000,
            reward_type: 'sharpe',
            walk_forward: false,
          }}
          onFinish={handleStart}
        >
          <div className="wb-train-form-row">
            <Form.Item label={t('rlcf_label_symbol')} name="symbol" rules={[{ required: true }]} className="wb-train-form-item">
              <Input placeholder="BTCUSDT" />
            </Form.Item>
            <Form.Item label={t('rlcf_label_interval')} name="interval" className="wb-train-form-item">
              <Select
                options={[
                  { value: '15m', label: t('rlcf_opt_15m') },
                  { value: '1h', label: t('rlcf_opt_1h') },
                  { value: '4h', label: t('rlcf_opt_4h') },
                  { value: '1d', label: t('rlcf_opt_1d') },
                ]}
              />
            </Form.Item>
          </div>
          <div className="wb-train-form-row">
            <Form.Item label={t('rlcf_label_algorithm')} name="algorithm" className="wb-train-form-item">
              <Select
                options={[
                  { value: 'ppo', label: 'PPO' },
                  { value: 'sac', label: 'SAC' },
                  { value: 'a2c', label: 'A2C' },
                ]}
              />
            </Form.Item>
            <Form.Item label={t('rlcf_label_reward')} name="reward_type" className="wb-train-form-item">
              <Select
                options={[
                  { value: 'pnl', label: t('rlcf_opt_pnl') },
                  { value: 'sharpe', label: t('rlcf_opt_sharpe') },
                  { value: 'sortino', label: t('rlcf_opt_sortino') },
                ]}
              />
            </Form.Item>
          </div>
          <div className="wb-train-form-row">
            <Form.Item label={t('rlcf_label_timesteps')} name="total_timesteps" rules={[{ required: true }]} className="wb-train-form-item">
              <InputNumber min={100} max={10000000} step={1000} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label={t('rlcf_label_walk_forward')} name="walk_forward" valuePropName="checked" className="wb-train-form-item">
              <Switch size="small" />
            </Form.Item>
          </div>
          <Button type="primary" size="small" htmlType="submit" loading={submitting} block>
            {t('rlcf_btn_start')}
          </Button>
        </Form>
      )}

      {!taskId ? (
        <div className="wb-train-empty">{t('wb_train_no_task')}</div>
      ) : !task ? (
        loadError ? (
          <Alert type="warning" showIcon title={t('wb_train_load_failed', { err: loadError })} />
        ) : (
          <div className="wb-center-spin">
            <Spin size="small" />
          </div>
        )
      ) : (
        <div className={`wb-train-card wb-train-${task.status}`}>
          <div className="wb-train-row">
            <span className={`qc-chip ${TRAIN_STATUS_LEVELS[task.status] ?? 'quiet'} wb-train-status`}>
              {t(`wb_train_status_${task.status}`, { defaultValue: task.status })}
            </span>
            <span className="wb-nowrap-mono wb-train-id">{task.task_id || taskId}</span>
            <span className="wb-train-elapsed">
              {t('wb_train_elapsed')} {formatElapsed(elapsedMs)}
            </span>
          </div>
          {task.stage && <div className="wb-train-stage">{t('wb_train_stage')}: {task.stage}</div>}
          <Progress percent={percent} status={barStatus} size="small" />
          {task.message && <div className="wb-train-msg">{task.message}</div>}
          {task.error && <div className="wb-train-err">{task.error}</div>}
          {task.status === 'done' && task.model_path && (
            <div className="wb-train-path" title={task.model_path}>
              {t('wb_train_model_path')}: {task.model_path}
            </div>
          )}
          {inFlight && !sseAlive && <div className="wb-train-hint">{t('wb_train_poll_fallback')}</div>}
        </div>
      )}

      {task && loadError && <Alert type="warning" showIcon title={t('wb_train_load_failed', { err: loadError })} />}
    </div>
  );
}
