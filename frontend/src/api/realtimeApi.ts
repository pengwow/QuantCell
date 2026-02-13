/**
 * 实时数据API接口
 * 
 * 提供实时引擎控制相关的API调用
 */

import { apiRequest } from './index';

// 实时引擎控制响应（API返回的data字段）
export interface RealtimeControlResponse {
  success: boolean;
}

// 实时引擎配置
export interface RealtimeConfig {
  realtime_enabled: boolean;
  data_mode: 'realtime' | 'cache';
  default_exchange?: string;
}

// 实时引擎状态
export interface RealtimeStatus {
  status: string;
  connected: boolean;
  connected_exchanges?: string[];
  total_exchanges?: number;
  config?: RealtimeConfig;
}

/**
 * 获取实时引擎状态
 * @returns 实时引擎状态
 */
export const getRealtimeStatus = async (): Promise<RealtimeStatus> => {
  const response = await apiRequest.get<RealtimeStatus>('/realtime/status');
  return response;
};

/**
 * 启动实时引擎
 * @returns 启动结果
 */
export const startRealtimeEngine = async (): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/start');
  return response;
};

/**
 * 停止实时引擎
 * @returns 停止结果
 */
export const stopRealtimeEngine = async (): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/stop');
  return response;
};

/**
 * 重启实时引擎
 * @returns 重启结果
 */
export const restartRealtimeEngine = async (): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/restart');
  return response;
};

/**
 * 连接交易所
 * @returns 连接结果
 */
export const connectExchange = async (): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/connect');
  return response;
};

/**
 * 断开交易所连接
 * @returns 断开结果
 */
export const disconnectExchange = async (): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/disconnect');
  return response;
};

/**
 * 获取实时引擎配置
 * @returns 配置信息
 */
export const getRealtimeConfig = async (): Promise<RealtimeConfig> => {
  const response = await apiRequest.get<RealtimeConfig>('/realtime/config');
  return response;
};

/**
 * 更新实时引擎配置
 * @param config 配置对象
 * @returns 更新结果
 */
export const updateRealtimeConfig = async (config: Partial<RealtimeConfig>): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/config', config);
  return response;
};

/**
 * 订阅K线数据频道
 * @param channels 频道列表，如 ['BTCUSDT@kline_1m', 'ETHUSDT@kline_5m']
 * @returns 订阅结果
 */
export const subscribeKlineChannels = async (channels: string[]): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/subscribe', channels);
  return response;
};

/**
 * 取消订阅K线数据频道
 * @param channels 频道列表
 * @returns 取消订阅结果
 */
export const unsubscribeKlineChannels = async (channels: string[]): Promise<RealtimeControlResponse> => {
  const response = await apiRequest.post<RealtimeControlResponse>('/realtime/unsubscribe', channels);
  return response;
};

/**
 * 获取支持的数据类型
 * @returns 数据类型列表
 */
export const getSupportedDataTypes = async (): Promise<string[]> => {
  const response = await apiRequest.get<string[]>('/realtime/data-types');
  return response;
};

/**
 * 获取支持的时间间隔
 * @returns 时间间隔列表
 */
export const getSupportedIntervals = async (): Promise<string[]> => {
  const response = await apiRequest.get<string[]>('/realtime/intervals');
  return response;
};

export default {
  getRealtimeStatus,
  startRealtimeEngine,
  stopRealtimeEngine,
  restartRealtimeEngine,
  connectExchange,
  disconnectExchange,
  getRealtimeConfig,
  updateRealtimeConfig,
  subscribeKlineChannels,
  unsubscribeKlineChannels,
  getSupportedDataTypes,
  getSupportedIntervals,
};
