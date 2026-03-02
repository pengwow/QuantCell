/**
 * 通知设置服务
 * 封装通知渠道配置的API调用
 */
import { notificationApi } from '../api';

/**
 * 获取通知渠道配置
 * @returns 通知渠道配置列表数据
 */
export const getNotificationChannels = async (): Promise<{ channels: any[] }> => {
  return notificationApi.getChannels();
};

/**
 * 保存通知渠道配置
 * @param channels 通知渠道配置列表
 * @returns 保存结果数据
 */
export const saveNotificationChannels = async (channels: any[]): Promise<{ channels: any[] }> => {
  return notificationApi.saveChannels(channels);
};

/**
 * 测试通知渠道
 * @param channelId 渠道ID
 * @param config 渠道配置
 * @returns 测试结果
 */
export const testNotificationChannel = async (channelId: string, config: any): Promise<any> => {
  return notificationApi.testChannel(channelId, config);
};
