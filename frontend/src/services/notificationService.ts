/**
 * 通知设置服务
 * 封装通知渠道配置的API调用
 */
import { notificationApi } from '../api';

/**
 * 获取通知渠道配置
 * @returns 通知渠道配置列表数据
 */
export const getNotificationChannels = async (): Promise<{ channels: unknown[] }> => {
  return notificationApi.getChannels();
};

/**
 * 保存通知渠道配置
 * @param channels 通知渠道配置列表
 * @returns 保存结果数据
 */
export const saveNotificationChannels = async (channels: unknown[]): Promise<{ channels: unknown[] }> => {
  return notificationApi.saveChannels(channels);
};

/**
 * 页面态的测试结果（页面按 success 渲染成功/失败卡片）。
 * 注意 axios 拦截器已把标准 ApiResponse 解包成「成功时返回 data、失败时抛 ApiError」，
 * 后端的 code/message 不会透传出来，成败由 promise 的 resolve/reject 区分。
 */
export interface NotificationTestResult {
  success: boolean;
  message: string;
}

/**
 * 测试通知渠道
 * @param channelId 渠道ID
 * @param config 渠道配置
 */
export const testNotificationChannel = async (
  channelId: string,
  config: unknown,
): Promise<void> => {
  // 拦截器在业务码非 0/HTTP 错误时抛 ApiError，await 正常返回即后端确认发送成功
  await notificationApi.testChannel(channelId, config);
};
