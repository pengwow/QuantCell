/**
 * Worker 分享系统 公开 API Client
 *
 * 提供无需登录即可访问的分享页数据获取能力。
 * 不包含任何受保护的写操作（创建/撤销走 workerApi）。
 */
import { apiRequest } from './index';
import type { ShareSnapshot } from '../types/worker';

/**
 * 获取分享页只读快照
 *
 * 公开端点，无需鉴权。
 * - 合法 token：返回 200 + snapshot
 * - 过期/撤销/一次性已用：返回 404
 * - 同 IP 60s 内最多 30 次（v1 仅打日志）
 *
 * @param token 分享 token（明文，从 URL 路径中获取）
 */
export const getShareSnapshot = (token: string): Promise<ShareSnapshot> => {
  return apiRequest.get(`/share/${token}`);
};
