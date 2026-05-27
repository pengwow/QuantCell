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
    const stop = listenPluginEvents(handlePluginEvent);
    return () => {
      mountedRef.current = false;
      stop();
    };
  }, [refresh, handlePluginEvent]);

  const enablePlugin = useCallback(
    async (name: string) => {
      await pluginApi.enablePlugin(name);
      message.success(`插件 ${name} 已启用`);
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
