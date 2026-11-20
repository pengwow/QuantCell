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
      <p style={{ color: 'var(--qc-text-tertiary)' }}>此插件尚未提供前端页面组件。</p>
    </PageContainer>
  );
}
