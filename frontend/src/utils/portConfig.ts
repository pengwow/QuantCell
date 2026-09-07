// 端口配置管理工具
// 用于从后端获取当前服务的端口配置，并动态更新 API baseURL 和 WebSocket 连接地址

export interface PortConfig {
  fastapi: number;
  zmq_data: number;
  zmq_control: number;
  zmq_status: number;
  zmq_broadcast: number;
  metadata?: {
    pid: number;
    start_time: string;
    last_updated: string;
  };
}

/**
 * 后端 /api/system/ports 返回的 data 结构
 * 各服务的端口位于各自的子对象中（port 字段）
 */
interface PortsResponseData {
  fastapi?: { port?: number };
  zmq_data?: { port?: number };
  zmq_control?: { port?: number };
  zmq_status?: { port?: number };
  zmq_broadcast?: { port?: number };
  metadata?: PortConfig['metadata'];
}

const DEFAULT_PORTS: PortConfig = {
  fastapi: 8000,
  zmq_data: 5555,
  zmq_control: 5556,
  zmq_status: 5557,
  zmq_broadcast: 5558,
};

let cachedPortConfig: PortConfig | null = null;

export async function fetchPortConfig(): Promise<PortConfig> {
  try {
    const possibleUrls = [
      '/api/system/ports',
      'http://localhost:8000/api/system/ports',
      `http://localhost:${DEFAULT_PORTS.fastapi}/api/system/ports`,
    ];

    let response: Response | null = null;

    for (const url of possibleUrls) {
      try {
        response = await fetch(url, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(3000),
        });

        if (response.ok) {
          break;
        }
      } catch (error) {
        console.warn(`[PortConfig] 无法从 ${url} 获取端口配置:`, error);
        continue;
      }
    }

    if (!response || !response.ok) {
      throw new Error('无法连接到后端服务');
    }

    const result = await response.json();

    if (result.code === 0 && result.data) {
      const data = result.data as PortsResponseData;

      const portConfig: PortConfig = {
        fastapi: data.fastapi?.port ?? DEFAULT_PORTS.fastapi,
        zmq_data: data.zmq_data?.port ?? DEFAULT_PORTS.zmq_data,
        zmq_control: data.zmq_control?.port ?? DEFAULT_PORTS.zmq_control,
        zmq_status: data.zmq_status?.port ?? DEFAULT_PORTS.zmq_status,
        zmq_broadcast: data.zmq_broadcast?.port ?? DEFAULT_PORTS.zmq_broadcast,
        metadata: data.metadata,
      };

      cachedPortConfig = portConfig;
      console.log('[PortConfig] 成功获取端口配置:', portConfig);
      return portConfig;
    } else {
      throw new Error(result.message || '返回数据格式错误');
    }
  } catch (error) {
    console.warn('[PortConfig] 获取端口配置失败，使用默认值:', error);
    return { ...DEFAULT_PORTS };
  }
}

export function getCachedPortConfig(): PortConfig | null {
  return cachedPortConfig;
}

export function getApiBaseUrl(portConfig?: PortConfig): string {
  const config = portConfig || cachedPortConfig || DEFAULT_PORTS;
  const port = config.fastapi;

  if (import.meta.env.DEV && port !== 8000) {
    return `http://localhost:${port}`;
  }

  return '';
}

export function getWebSocketUrl(path: string, portConfig?: PortConfig): string {
  const config = portConfig || cachedPortConfig || DEFAULT_PORTS;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname;
  const port = config.fastapi;

  const isDefaultPort = (protocol === 'ws:' && port === 80) ||
                        (protocol === 'wss:' && port === 443) ||
                        (port === parseInt(window.location.port));

  const portSuffix = isDefaultPort ? '' : `:${port}`;

  return `${protocol}//${host}${portSuffix}${path}`;
}

export async function initializePortConfig(): Promise<PortConfig> {
  try {
    const config = await fetchPortConfig();

    if (config.fastapi !== DEFAULT_PORTS.fastapi) {
      console.warn(`[PortConfig] 检测到后端使用非默认端口: ${config.fastapi}`);
    }

    return config;
  } catch (error) {
    console.error('[PortConfig] 初始化失败:', error);
    return { ...DEFAULT_PORTS };
  }
}

export function clearCachedPortConfig(): void {
  cachedPortConfig = null;
}
