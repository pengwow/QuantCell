/* eslint-disable react-refresh/only-export-components -- Context + Provider + hook 同文件捆绑为常用模式，拆分割裂插件联动逻辑且无功能收益，禁用后降级为整页刷新 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { App } from 'antd';
import {
  pluginApi,
  listenPluginEvents,
  type PluginInfo,
} from '@/api/plugin';
import { pluginRegistry } from './PluginRegistry';

interface PluginContextValue {
  plugins: PluginInfo[];
  loading: boolean;
  refresh: () => Promise<void>;
  enablePlugin: (name: string) => Promise<void>;
  disablePlugin: (name: string) => Promise<void>;
}

const PluginContext = createContext<PluginContextValue>({
  plugins: [],
  loading: true,
  refresh: async () => {},
  enablePlugin: async () => {},
  disablePlugin: async () => {},
});

export function PluginProvider({ children }: { children: ReactNode }) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const { message } = App.useApp();
  const mountedRef = useRef(true);
  // 插件事件流的停止函数（建连被延后，cleanup 时可能还没建立）
  const stopEventsRef = useRef<(() => void) | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const list = await pluginApi.getPlugins();
      if (!mountedRef.current) return;
      setPlugins(list);
      for (const p of list) {
        pluginRegistry.registerPlugin(p);
      }
    } catch (err) {
      message.error(`加载插件列表失败: ${(err as Error).message}`);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [message]);

  const handlePluginEvent = useCallback(
    () => {
      refresh();
    },
    [refresh],
  );

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    // 延后一拍再建连：StrictMode 会 mount → cleanup → mount，同步建连会让第一个
    // EventSource 在建连途中被 close，浏览器控制台报 net::ERR_ABORTED
    const timer = setTimeout(() => {
      stopEventsRef.current = listenPluginEvents(handlePluginEvent);
    }, 0);
    return () => {
      clearTimeout(timer);
      mountedRef.current = false;
      stopEventsRef.current?.();
      stopEventsRef.current = null;
    };
  }, [refresh, handlePluginEvent]);

  const enablePlugin = useCallback(
    async (name: string) => {
      await pluginApi.enablePlugin(name);
      message.success(`插件 ${name} 已标记启用，重启后端服务后生效`);
      await refresh();
    },
    [message, refresh],
  );

  const disablePlugin = useCallback(
    async (name: string) => {
      await pluginApi.disablePlugin(name);
      message.success(`插件 ${name} 已禁用`);
      await refresh();
    },
    [message, refresh],
  );

  const value = useMemo(
    () => ({ plugins, loading, refresh, enablePlugin, disablePlugin }),
    [plugins, loading, refresh, enablePlugin, disablePlugin],
  );

  return <PluginContext.Provider value={value}>{children}</PluginContext.Provider>;
}

export function usePlugins() {
  return useContext(PluginContext);
}
