import { useEffect, useState } from 'react';
import { pluginRegistry } from '@/plugins/PluginRegistry';

interface PluginPageProps {
  pluginName: string;
}

export default function PluginPage({ pluginName }: PluginPageProps) {
  const [containerRef, setContainerRef] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    const route = pluginRegistry.getRoutes().find((r) => r.pluginName === pluginName);
    if (!route || !containerRef) return;

    // 如果插件注册了 React 组件，直接渲染
    if (route.element) {
      return;
    }
  }, [pluginName, containerRef]);

  const route = pluginRegistry.getRoutes().find((r) => r.pluginName === pluginName);

  if (route?.element) {
    return <>{route.element}</>;
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">插件页面: {pluginName}</h1>
      <p className="text-gray-500">此插件尚未提供前端页面组件。</p>
    </div>
  );
}
