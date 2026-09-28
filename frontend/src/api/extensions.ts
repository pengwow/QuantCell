import { apiRequest } from './index';

/**
 * 桌面端可选扩展接口（RL 训练链等重依赖的按需安装）。
 * 响应拦截器已解包 ApiResponse envelope，泛型直接是业务数据类型。
 */

export interface ExtensionInfo {
  id: string;
  name: string;
  category: string;
  description: string;
  deps: string[];
  approx_size_mb: number;
  live_size_mb: number | null;
  purpose: string;
  installed: boolean;
  versions: Record<string, string>;
}

export type InstallStatus =
  | 'idle'
  | 'resolving'
  | 'downloading'
  | 'installing'
  | 'done'
  | 'error';

export interface InstallProgress {
  task_id: string | null;
  status: InstallStatus;
  pct: number;
  detail: string;
}

export const extensionsApi = {
  list: (): Promise<ExtensionInfo[]> => apiRequest.get('/api/v1/extensions'),

  install: (id: string): Promise<{ task_id: string }> =>
    apiRequest.post(`/api/v1/extensions/${id}/install`),

  progress: (id: string): Promise<InstallProgress> =>
    apiRequest.get(`/api/v1/extensions/${id}/progress`),

  uninstall: (id: string): Promise<null> =>
    apiRequest.post(`/api/v1/extensions/${id}/uninstall`),
};
