/**
 * 右栏 WorkPanel：Tab 化工作面板（可折叠为 0，聊天占满）。
 * Tab 键写入 URL ?tab=（DynamicRouter 不动，Agent 页自管查询参数）。
 */
import { Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { useWorkbenchStore } from '../../store/workbenchStore';
import { useWorkbenchData } from '../../hooks/useWorkbenchData';
import DecisionsTab from './DecisionsTab';
import PositionsTab from './PositionsTab';
import PerformanceTab from './PerformanceTab';
import ModelsTab from './ModelsTab';
import LogsTab from './LogsTab';
import AuditTab from './AuditTab';
import SelfLoopTab from './SelfLoopTab';
import { EventsTab } from './placeholders';

export default function WorkbenchPanel() {
  const { t } = useTranslation();
  const activeTab = useWorkbenchStore((s) => s.activeTab);
  const setTab = useWorkbenchStore((s) => s.setTab);

  // 数据轮询 + 日志 SSE 生命周期挂面板容器：折叠时 Tab 不销毁、流不断
  useWorkbenchData();

  const items = [
    { key: 'decisions', label: t('wb_tab_decisions'), children: <DecisionsTab /> },
    { key: 'positions', label: t('wb_tab_positions'), children: <PositionsTab /> },
    { key: 'performance', label: t('wb_tab_performance'), children: <PerformanceTab /> },
    { key: 'models', label: t('wb_tab_models'), children: <ModelsTab /> },
    { key: 'logs', label: t('wb_tab_logs'), children: <LogsTab /> },
    { key: 'audit', label: t('wb_tab_audit'), children: <AuditTab /> },
    { key: 'events', label: t('wb_tab_events'), children: <EventsTab /> },
    { key: 'selfloop', label: t('wb_tab_selfloop'), children: <SelfLoopTab /> },
  ];

  return (
    <Tabs
      activeKey={activeTab}
      onChange={(k) => setTab(k as typeof activeTab)}
      size="small"
      items={items}
      className="wb-tabs"
      tabBarStyle={{ marginBottom: 8, padding: '0 8px' }}
    />
  );
}
