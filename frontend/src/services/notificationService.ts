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
 * 通知渠道测试结果（对应后端 /notifications/test 的返回结构）
 */
export interface NotificationTestResult {
  code: number;
  message?: string;
  data?: { result?: { error?: string } };
}

/**
 * 测试通知渠道
 * @param channelId 渠道ID
 * @param config 渠道配置
 * @returns 测试结果
 */
export const testNotificationChannel = async (
  channelId: string,
  config: unknown,
): Promise<NotificationTestResult> => {
  return (await notificationApi.testChannel(channelId, config)) as NotificationTestResult;
};
