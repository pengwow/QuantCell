import { getAccessToken } from '../utils/tokenManager';
import { apiRequest } from './index';

export type PluginStatus = 'installed' | 'enabled' | 'disabled' | 'pending_restart' | 'error';
export type LoadType = 'hot' | 'restart';
export type InstallSource = 'zip' | 'git' | 'manual';

export interface PluginInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  load_type: LoadType;
  status: PluginStatus;
  install_source: InstallSource;
  install_path: string;
  permissions: string[];
  config_schema: Record<string, unknown> | null;
  frontend_entry: string | null;
  installed_at: string;
  updated_at: string;
  error_message: string | null;
}

export const pluginApi = {
  getPlugins: (): Promise<PluginInfo[]> =>
    apiRequest.get<{ plugins: PluginInfo[] }>('/plugins/').then((d) => d.plugins),

  getPlugin: (name: string): Promise<PluginInfo> =>
    apiRequest.get<PluginInfo>(`/plugins/${name}`),

  installFromZip: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiRequest.post('/plugins/install/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  installFromGit: (url: string, branch?: string) =>
    apiRequest.post('/plugins/install/git', { url, branch }),

  uninstallPlugin: (name: string) =>
    apiRequest.delete(`/plugins/${name}`),

  enablePlugin: (name: string) =>
    apiRequest.post(`/plugins/${name}/enable`),

  disablePlugin: (name: string) =>
    apiRequest.post(`/plugins/${name}/disable`),

  getPluginConfig: (name: string) =>
    apiRequest.get(`/plugins/${name}/config`),
};

export interface PluginEvent {
  event: string;
  data: {
    name: string;
    status: string;
    error?: string;
  };
}

export function listenPluginEvents(
  onEvent: (evt: PluginEvent) => void,
): () => void {
  const token = getAccessToken();
  const url = `/api/plugins/events${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  const es = new EventSource(url);

  es.onmessage = (msg: MessageEvent) => {
    try {
      const data = JSON.parse(msg.data);
      onEvent({ event: 'message', data });
    } catch {
      // 忽略解析错误
    }
  };

  const trackedEvents = [
    'plugin_loaded',
    'plugin_unloaded',
    'plugin_installed',
    'plugin_uninstalled',
    'plugin_error',
  ];
  for (const evt of trackedEvents) {
    es.addEventListener(evt, ((e: MessageEvent) => {
      try {
        onEvent({ event: evt, data: JSON.parse(e.data) });
      } catch {
        // 忽略解析错误
      }
    }) as EventListener);
  }

  es.onerror = () => {
    es.close();
  };

  return () => es.close();
}
