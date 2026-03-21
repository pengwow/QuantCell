/**
 * 回测模块 API 接口
 * 提供回测相关的所有 API 调用
 */

import { apiRequest } from './index';
import { BacktestProgressData } from '../types/backtest';



/**
 * 获取回测任务进度
 * @param taskId 回测任务ID
 * @returns 回测进度数据
 */
export async function getBacktestProgress(taskId: string): Promise<BacktestProgressData | null> {
  try {
    // apiRequest.get 已经通过响应拦截器处理了 ApiResponse，直接返回 data 字段
    const data = await apiRequest.get<BacktestProgressData>(
      `/backtest/progress/${taskId}`
    );

    console.log('[getBacktestProgress] 获取到数据:', JSON.stringify(data, null, 2));

    if (!data) {
      console.warn('[getBacktestProgress] 响应为空');
      return null;
    }

    // 检查是否是有效的进度数据（必须有 task_id 字段）
    if (data.task_id) {
      return data;
    }

    console.warn('[getBacktestProgress] 返回的数据格式不正确，缺少 task_id');
    return null;
  } catch (error) {
    console.error('[getBacktestProgress] 获取回测进度出错:', error);
    return null;
  }
}

/**
 * 订阅回测进度（WebSocket）
 * @param taskId 回测任务ID
 * @param onProgress 进度更新回调函数
 * @returns 取消订阅函数
 */
export function subscribeBacktestProgress(
  taskId: string,
  onProgress: (data: BacktestProgressData) => void
): () => void {
  // 获取 WebSocket 基础 URL
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = window.location.host;
  const wsUrl = `${wsProtocol}//${wsHost}/api/backtest/progress/${taskId}/stream`;
  
  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 3;
  let reconnectTimeout: NodeJS.Timeout | null = null;
  
  // 连接 WebSocket
  const connect = () => {
    try {
      ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        console.log(`WebSocket 连接成功: ${taskId}`);
        reconnectAttempts = 0;
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as BacktestProgressData;
          onProgress(data);
        } catch (error) {
          console.error('解析 WebSocket 消息失败:', error);
        }
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
      };
      
      ws.onclose = () => {
        // 如果任务未完成，尝试重连
        if (reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
          console.log(`WebSocket 断开，${delay}ms 后尝试重连 (${reconnectAttempts}/${maxReconnectAttempts})`);
          reconnectTimeout = setTimeout(connect, delay);
        }
      };
    } catch (error) {
      console.error('创建 WebSocket 连接失败:', error);
    }
  };
  
  // 开始连接
  connect();
  
  // 返回取消订阅函数
  return () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
    }
    if (ws) {
      ws.close();
      ws = null;
    }
  };
}

/**
 * 检查 WebSocket 是否可用
 * @returns 是否支持 WebSocket
 */
export function isWebSocketSupported(): boolean {
  return typeof WebSocket !== 'undefined';
}

/**
 * 轮询获取回测进度（优化版）
 * @param taskId 回测任务ID
 * @param onProgress 进度更新回调函数
 * @param options 轮询配置选项
 * @returns 停止轮询函数
 */
export function pollBacktestProgress(
  taskId: string,
  onProgress: (data: BacktestProgressData) => void,
  options: {
    initialInterval?: number;
    maxInterval?: number;
    maxRetries?: number;
    timeout?: number;
  } = {}
): () => void {
  const {
    initialInterval = 500,
    maxInterval = 5000,
    maxRetries = 60, // 最多重试60次
    timeout = 300000 // 5分钟超时
  } = options;

  let isRunning = true;
  let timeoutId: NodeJS.Timeout | null = null;
  let retryCount = 0;
  let currentInterval = initialInterval;
  const startTime = Date.now();

  const poll = async () => {
    if (!isRunning) return;

    // 检查是否超时
    if (Date.now() - startTime > timeout) {
      console.warn('轮询超时');
      onProgress({
        task_id: taskId,
        status: 'failed',
        current_stage: 'execution',
        overall_progress: 0,
        data_prep: { status: 'failed', progress: 0, current_step: 'checking', checked_symbols: 0, total_symbols: 0 },
        execution: { status: 'failed', progress: 0, current_symbol: '', completed_symbols: 0, total_symbols: 0 },
        analysis: { status: 'failed', progress: 0 },
        error: { stage: 'polling', message: '轮询超时，请检查网络连接或重试' },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      } as BacktestProgressData);
      isRunning = false;
      return;
    }

    // 检查是否超过最大重试次数
    if (retryCount >= maxRetries) {
      console.warn('达到最大重试次数');
      onProgress({
        task_id: taskId,
        status: 'failed',
        current_stage: 'execution',
        overall_progress: 0,
        data_prep: { status: 'failed', progress: 0, current_step: 'checking', checked_symbols: 0, total_symbols: 0 },
        execution: { status: 'failed', progress: 0, current_symbol: '', completed_symbols: 0, total_symbols: 0 },
        analysis: { status: 'failed', progress: 0 },
        error: { stage: 'polling', message: '获取进度失败次数过多，请检查网络连接或重试' },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      } as BacktestProgressData);
      isRunning = false;
      return;
    }

    try {
      console.log(`[pollBacktestProgress] 开始获取进度，taskId: ${taskId}`);
      const data = await getBacktestProgress(taskId);
      console.log(`[pollBacktestProgress] 获取到数据:`, data ? '有数据' : '无数据');

      retryCount = 0; // 重置重试计数
      currentInterval = initialInterval; // 重置间隔

      if (data) {
        console.log(`[pollBacktestProgress] 调用 onProgress，状态: ${data.status}`);
        onProgress(data);

        // 如果任务已完成或失败，停止轮询
        if (data.status === 'completed' || data.status === 'failed') {
          console.log(`[pollBacktestProgress] 任务${data.status}，停止轮询`);
          isRunning = false;
          return;
        }
      } else {
        // 数据为空，增加重试计数
        retryCount++;
        console.warn(`[pollBacktestProgress] 获取进度数据为空 (${retryCount}/${maxRetries})`);
      }
    } catch (error) {
      retryCount++;
      console.error(`[pollBacktestProgress] 轮询出错 (${retryCount}/${maxRetries}):`, error);
      // 指数退避
      currentInterval = Math.min(currentInterval * 1.5, maxInterval);
    }

    // 继续轮询
    if (isRunning) {
      timeoutId = setTimeout(poll, currentInterval);
    }
  };

  // 开始轮询
  poll();

  // 返回停止轮询函数
  return () => {
    isRunning = false;
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  };
}

/**
 * 智能获取回测进度（优先使用 WebSocket，回退到轮询）
 * @param taskId 回测任务ID
 * @param onProgress 进度更新回调函数
 * @returns 取消订阅/停止函数
 */
export function watchBacktestProgress(
  taskId: string,
  onProgress: (data: BacktestProgressData) => void
): () => void {
  // 如果支持 WebSocket，优先使用 WebSocket
  if (isWebSocketSupported()) {
    return subscribeBacktestProgress(taskId, onProgress);
  }
  
  // 否则使用轮询
  return pollBacktestProgress(taskId, onProgress);
}
