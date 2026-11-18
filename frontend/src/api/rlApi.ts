import { apiRequest, handleUnauthorized } from './index';
import { getAccessToken } from '../utils/tokenManager';
import { getApiBaseUrl } from '../utils/portConfig';
import type { CreateWorkerRequest } from '../types/worker';

// 与后端 api/rl_routes.py 的 TrainRequest 对齐：symbol 必填，其余有默认值
export interface RLTrainRequest {
  algorithm?: string;
  symbol: string;
  interval?: string;
  candle_type?: string;
  start?: string | null;
  end?: string | null;
  total_timesteps?: number;
  reward_type?: string;
  walk_forward?: boolean;
  wf_splits?: number;
}

export interface RLTrainResult {
  model_id: string;
  status: string;
  metrics: Record<string, number>;
  walk_forward?: unknown;
}

// 与后端 RLService.list_saved_models() 对齐：data/models 下真实 .zip 文件
export interface RLModelInfo {
  name: string;
  path: string;
  size_mb: number;
  created: number;
}

// 与后端 api/rl_routes.py 的 RLBacktestRequest 对齐：model_id 为 data/models 下 .zip 文件 stem；
// 引擎固定统一内核（与实盘同一条主回路），不再提供 engine / reward_type 选项
export interface RLBacktestRequest {
  model_id: string;
  symbol: string;
  interval?: string;
  candle_type?: string;
  initial_capital?: number;
  // 非空时跑集成员聚合回测，model_id 仅作兜底
  ensemble_id?: string;
}

// 后端 run_backtest_task 返回的任务化摘要：结果按策略回测同一契约落盘，
// 凭 task_id 打开详情抽屉 / 详情页（backtestApi.getBacktestDetail）
export interface RLBacktestResult {
  task_id: number | string;
  strategy_name: string;
  engine: string; // 固定 "kernel"
  symbol: string;
  interval: string;
  data_bars: number;
  total_pnl: number;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  num_trades: number;
}

// ============================================
// 异步训练任务（后台训练 + 进度轮询 / SSE）
// ============================================

export type RLTrainTaskStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';

/** GET /rl/train/{task_id} 的响应体 */
export interface RLTrainTask {
  task_id: string;
  status: RLTrainTaskStatus;
  stage?: string | null;
  /** 0..1 */
  progress?: number | null;
  message?: string | null;
  error?: string | null;
  model_path?: string | null;
  meta_path?: string | null;
  elapsed_ms?: number | null;
}

/**
 * SSE 消费类（对标 WorkerLogStreamSSE 的既有写法）：订阅训练进度事件流。
 * 后端事件：state（任务快照 JSON）/ log（日志行文本）/ 15s ping（注释行，EventSource 自动忽略）。
 * 断流不自行重连超限后静默失败——调用方按 5s 轮询兜底（面板里就是这套组合）。
 */
export class RLTrainStreamSSE {
  readonly taskId: string;
  private es: EventSource | null = null;
  private readonly handlers: {
    onState: (task: Partial<RLTrainTask>) => void;
    onLog?: (line: string) => void;
    onOpen?: () => void;
    onError?: () => void;
  };
  private reconnectCount = 0;
  private readonly maxReconnects = 5;
  private manuallyClosed = false;

  constructor(
    taskId: string,
    handlers: {
      onState: (task: Partial<RLTrainTask>) => void;
      onLog?: (line: string) => void;
      onOpen?: () => void;
      onError?: () => void;
    },
  ) {
    this.taskId = taskId;
    this.handlers = handlers;
  }

  connect(): void {
    if (this.es) return;
    this.manuallyClosed = false;
    this.reconnectCount = 0;

    // EventSource 无法带请求头：token 走 query（与 WorkerLogStreamSSE / plugin SSE 同惯例）；
    // getApiBaseUrl 为空串时是相对路径（Web 同源 / vite 代理），桌面壳下为绝对地址
    const path = `${getApiBaseUrl()}/api/v1/rl/train/${encodeURIComponent(this.taskId)}/events`;
    const token = getAccessToken();
    const url = token ? `${path}?token=${encodeURIComponent(token)}` : path;

    const es = new EventSource(url);
    this.es = es;

    es.onopen = () => {
      this.reconnectCount = 0;
      this.handlers.onOpen?.();
    };

    const handleState = (e: MessageEvent) => {
      try {
        this.handlers.onState(JSON.parse(e.data) as Partial<RLTrainTask>);
      } catch {
        // 非 JSON 快照（异常载荷）忽略，轮询仍会纠正
      }
    };
    es.addEventListener('state', handleState as EventListener);
    es.addEventListener('log', (e: MessageEvent) => {
      this.handlers.onLog?.(String((e as MessageEvent).data ?? ''));
    });
    // 兜底：后端若以未命名事件推同一快照，不丢更新
    es.onmessage = handleState;

    es.onerror = () => {
      if (this.manuallyClosed) return;
      const state = this.es?.readyState;
      if (state === EventSource.CLOSED) {
        this.handlers.onError?.();
        this.disconnect();
        return;
      }
      this.reconnectCount++;
      if (this.reconnectCount >= this.maxReconnects) {
        this.handlers.onError?.();
        this.disconnect();
      }
    };
  }

  disconnect(): void {
    this.manuallyClosed = true;
    this.es?.close();
    this.es = null;
  }
}

/**
 * 训练任务的三个端点是裸 JSON（后端直接 return {"task_id": ...} / snapshot() /
 * {"accepted": true}，没有 {code,message,data} 信封），走 axios 会被响应拦截器
 * 当成未知错误拒绝，故单独走 fetch（与 TrainingWorkbench 的同步训练同一取舍）。
 */
const trainFetch = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const token = getAccessToken();
  const res = await fetch(`${getApiBaseUrl()}/api/v1${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error('登录已过期，请重新登录');
  }
  // 错误体是 FastAPI 的 {"detail": "..."}；成功体是裸业务 JSON
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const detail = (body as { detail?: string } | null)?.detail;
    const err = new Error(detail || `HTTP ${res.status}`) as Error & { code?: number };
    err.code = res.status; // 404 → 面板放弃跟踪该任务
    throw err;
  }
  return body as T;
};

export const rlApi = {
  train: (data: RLTrainRequest) =>
    apiRequest.post<RLTrainResult>('/rl/train', data),
  // 后台训练：202 + {task_id, status}
  trainAsync: (data: RLTrainRequest) =>
    trainFetch<{ task_id: string; status?: string }>('/rl/train/async', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getTrainTask: (taskId: string) =>
    trainFetch<RLTrainTask>(`/rl/train/${encodeURIComponent(taskId)}`),
  cancelTrainTask: (taskId: string) =>
    trainFetch<{ accepted: boolean }>(`/rl/train/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' }),
  // 部署规格（工作台"部署 paper"三步串联第一步）：注册策略并返回可直接 POST /workers 的完整 body
  // （strategy_id/strategy_name 已回填）。裸 JSON 走 trainFetch 通道（同 trainAsync）；
  // 409=任务非完成态/模型缺失、422=meta 校验失败、404=任务不存在；幂等，重复调用安全
  deploySpec: (taskId: string) =>
    trainFetch<{ strategy: Record<string, unknown>; worker: CreateWorkerRequest }>(
      `/rl/train/${encodeURIComponent(taskId)}/deploy-spec`,
      { method: 'POST' },
    ),
  listModels: () =>
    apiRequest.get<RLModelInfo[]>('/rl/models'),
  deleteModel: (name: string) =>
    apiRequest.delete(`/rl/models/${encodeURIComponent(name)}`),
  // 同步回测（kernel 秒级）也可能跑几分钟：timeout:0 关闭 axios 默认超时（与 backtestApi.runBacktest 同策略）
  backtest: (data: RLBacktestRequest) =>
    apiRequest.post<RLBacktestResult>('/rl/backtest', data, { timeout: 0 }),
};