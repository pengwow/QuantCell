import PageContainer from '@/components/PageContainer';
import { pluginRegistry } from '@/plugins/PluginRegistry';

interface PluginPageProps {
  pluginName: string;
}

export default function PluginPage({ pluginName }: PluginPageProps) {
  const route = pluginRegistry.getRoutes().find((r) => r.pluginName === pluginName);

  if (route?.element) {
    return <>{route.element}</>;
  }

  return (
    <PageContainer title={`插件: ${pluginName}`}>
      <p className="text-gray-500 dark:text-gray-400">此插件尚未提供前端页面组件。</p>
    </PageContainer>
  );
}
