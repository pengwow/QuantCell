import { useEffect, useState } from 'react';
import {
  Layout,
  Input,
  Button,
  Modal,
  Select,
  Tooltip,
  App,
} from 'antd';
import {
  DeleteOutlined,
  HistoryOutlined,
  SettingOutlined,
  ExclamationCircleOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useAgentStore } from './store/agentStore';
import { useWorkbenchStore, isWorkbenchTab } from './store/workbenchStore';
import { workerApi } from '@/api/workerApi';
import { WorkerStatusText, WorkerStatus } from '@/types/worker';
import type { Worker } from '@/types/worker';
import { usePolling } from '@/hooks/usePolling';
import ChatPanel from './components/ChatPanel';
import SessionListDrawer from './components/SessionListDrawer';
import ToolListDrawerWithConfig from './components/ToolListDrawerWithConfig';
import WorkbenchPanel from './components/workbench/WorkbenchPanel';
import './Agent.css';

const { Content } = Layout;

/**
 * Worker 状态 → §6.2 qc-chip 语义档位（彩色 antd Tag 全量退场）：
 * 运行/衔接中带 pdot 脉冲，停机中性，异常红、暂停/中断警告。
 */
const WORKER_CHIP_LEVEL: Record<string, string> = {
  [WorkerStatus.INITIALIZING]: 'info',
  [WorkerStatus.INITIALIZED]: 'quiet',
  [WorkerStatus.STARTING]: 'info',
  [WorkerStatus.RUNNING]: 'ok',
  [WorkerStatus.STOPPING]: 'info',
  [WorkerStatus.STOPPED]: 'quiet',
  [WorkerStatus.ERROR]: 'down',
  [WorkerStatus.RECOVERING]: 'warn',
  [WorkerStatus.RELOADING]: 'info',
  [WorkerStatus.RESTARTING]: 'info',
  [WorkerStatus.PAUSED]: 'warn',
  [WorkerStatus.INTERRUPTED]: 'warn',
};
/** 进行中状态徽标内嵌脉冲点（§6.2 pdot） */
const WORKER_CHIP_PULSING = new Set<string>([
  WorkerStatus.INITIALIZING, WorkerStatus.STARTING, WorkerStatus.RUNNING,
  WorkerStatus.STOPPING, WorkerStatus.RECOVERING, WorkerStatus.RELOADING,
  WorkerStatus.RESTARTING,
]);

// 主页面
const Agent = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const [toolDrawerVisible, setToolDrawerVisible] = useState(false);
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false);
  const [deleteModalVisible, setDeleteModalVisible] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState('');
  const [workers, setWorkers] = useState<Worker[]>([]);

  const {
    sessions,
    currentSessionId,
    tools,
    switchSession,
    createSession,
    clearSession,
    deleteSession,
    fetchSessions,
    fetchTools,
  } = useAgentStore();

  // —— 工作面板状态（store 持有，URL 查询参数做持久化：/agent?tab=decisions&worker=1）——
  const workerId = useWorkbenchStore((s) => s.workerId);
  const activeTab = useWorkbenchStore((s) => s.activeTab);
  const collapsed = useWorkbenchStore((s) => s.collapsed);
  const setWorker = useWorkbenchStore((s) => s.setWorker);
  const setTab = useWorkbenchStore((s) => s.setTab);
  const togglePanel = useWorkbenchStore((s) => s.togglePanel);

  // 初始化：会话 + 工具列表（原逻辑）
  useEffect(() => {
    fetchSessions();
    fetchTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, []);

  // Worker 选择器数据：列表轻量（DB 行 + 状态），30s 轮询保持状态徽标新鲜
  const fetchWorkers = async () => {
    try {
      const data = await workerApi.getWorkers({ page_size: 100 });
      setWorkers(data?.items ?? []);
    } catch (err) {
      console.warn('[agent] workers load failed:', err);
    }
  };
  usePolling(fetchWorkers, { interval: 30000 });

  // URL → store（进入页面/前进后退时同步），worker 缺省选中首个运行中项
  useEffect(() => {
    const tab = searchParams.get('tab');
    if (isWorkbenchTab(tab)) setTab(tab);
    const w = Number(searchParams.get('worker'));
    if (Number.isInteger(w) && w > 0 && w !== useWorkbenchStore.getState().workerId) {
      setWorker(w);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在挂载/URL 外部变化时对齐
  }, [searchParams]);

  // store → URL（用户交互触发；replace 不产生历史噪音）。
  // 读 getState() 而非渲染闭包：挂载首拍 URL→store 对齐与回写同 commit 执行时，
  // 闭包还是 store 初值，会把 URL 里的 tab/worker 打回默认（实测发生过）。
  useEffect(() => {
    const { workerId: curWorker, activeTab: curTab } = useWorkbenchStore.getState();
    const next = new URLSearchParams(searchParams);
    let dirty = false;
    if (curWorker != null && next.get('worker') !== String(curWorker)) {
      next.set('worker', String(curWorker));
      dirty = true;
    }
    if (next.get('tab') !== curTab) {
      next.set('tab', curTab);
      dirty = true;
    }
    if (dirty) setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- searchParams 只读当前值，避免与上方对齐效应互相触发
  }, [workerId, activeTab]);

  // workers 首次到位且 URL/store 均无 worker → 缺省选中首个运行中 worker
  useEffect(() => {
    if (workerId != null || workers.length === 0) return;
    if (searchParams.get('worker')) return;
    const preferred = workers.find(w => w.status === 'running') ?? workers[0];
    if (preferred) setWorker(preferred.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅在 workers 首次就绪时补一次缺省
  }, [workers, workerId]);

  // 切到列表里还没有的 worker（工作台新建 worker 后立即切换 / URL 直达旧 id）：
  // 立即补拉一次，不等 30s 轮询，避免选择器短暂显示裸 id
  useEffect(() => {
    if (workerId == null) return;
    if (workers.some((w) => w.id === workerId)) return;
    fetchWorkers();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchWorkers 为内联函数，仅跟随 workerId 触发
  }, [workerId]);

  const currentWorker = workers.find(w => w.id === workerId);

  const handleSelectWorker = (value: number) => {
    setWorker(value);
  };

  const handleNewSession = async () => {
    await createSession();
    message.success(t('agent_session_created'));
    setSessionDrawerOpen(false);
  };

  // 清空不可恢复，双入口（顶栏 + 会话抽屉）统一在此加确认再执行
  const handleClearSession = () => {
    modal.confirm({
      title: t('agent_clear_confirm_title'),
      content: t('agent_clear_confirm_content'),
      okText: t('agent_clear_session'),
      cancelText: t('cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await clearSession(currentSessionId);
        message.success(t('agent_session_cleared'));
      },
    });
  };

  const handleDeleteConfirm = async () => {
    if (confirmText !== t('confirm_delete') || !sessionToDelete) {
      return;
    }

    const success = await deleteSession(sessionToDelete);
    if (success) {
      message.success(t('agent_session_deleted'));
      setDeleteModalVisible(false);
      setConfirmText('');
      setSessionToDelete(null);
    } else {
      message.error(t('delete_failed'));
    }
  };

  const showDeleteConfirm = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessionToDelete(sessionId);
    setDeleteModalVisible(true);
  };

  const toggleSessionDrawer = () => {
    setSessionDrawerOpen(!sessionDrawerOpen);
  };

  return (
    // ponytail: Agent 是全屏双栏工作台，ai-agent-layout + page-fullscreen 抵消 ConsoleLayout 的 padding（机制不动）
    <Layout className="ai-agent-layout page-fullscreen">
      {/* 主内容区：顶栏 + 双栏 */}
      <Layout className="agent-content-layout">
        {/* 顶栏（会话历史 / 工具参数 / 清空；worker 选择域 + 面板折叠） */}
        <div className="agent-header">
          <div className="header-left">
            <Tooltip title={t('agent_session_history')}>
              <Button
                type="text"
                icon={<HistoryOutlined />}
                onClick={toggleSessionDrawer}
                className={sessionDrawerOpen ? 'active' : ''}
              />
            </Tooltip>
            <span className="session-name">
              {sessions.find(s => s.id === currentSessionId)?.name || 'AI Agent'}
            </span>
          </div>
          <div className="header-right">
            <div className="wb-worker-select">
              <span className="wb-worker-label">Worker</span>
              <Select
                size="small"
                variant="borderless"
                value={workerId ?? undefined}
                onChange={handleSelectWorker}
                placeholder={t('wb_select_worker')}
                loading={workers.length === 0}
                popupMatchSelectWidth={false}
                style={{ minWidth: 150 }}
                options={workers.map(w => ({
                  value: w.id,
                  label: `${w.name} (#${w.id})`,
                }))}
                notFoundContent={<span style={{ fontSize: 12 }}>{workers.length === 0 ? t('wb_no_workers') : null}</span>}
              />
              {currentWorker && (
                <Tooltip title={t(WorkerStatusText[currentWorker.status] ?? currentWorker.status)}>
                  <span
                    className={`qc-chip ${WORKER_CHIP_LEVEL[currentWorker.status] ?? 'quiet'} wb-worker-status`}
                  >
                    {WORKER_CHIP_PULSING.has(currentWorker.status) && <span className="qc-pdot" />}
                    {t(WorkerStatusText[currentWorker.status] ?? currentWorker.status)}
                  </span>
                </Tooltip>
              )}
            </div>
            <Tooltip title={t('agent_tool_settings')}>
              <Button
                type="text"
                icon={<SettingOutlined />}
                onClick={() => setToolDrawerVisible(true)}
              />
            </Tooltip>
            <Tooltip title={t('agent_clear_session')}>
              <Button
                type="text"
                icon={<DeleteOutlined />}
                onClick={handleClearSession}
              />
            </Tooltip>
            <Tooltip title={collapsed ? t('wb_expand_panel') : t('wb_collapse_panel')}>
              <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={togglePanel}
              />
            </Tooltip>
          </div>
        </div>

        {/* 双栏主体：左聊天 ~55%，右工作面板 ~45%（可折叠为 0） */}
        <Content className="agent-workbench">
          <div className="agent-chat-col">
            <ChatPanel />
          </div>
          {!collapsed && (
            <div className="agent-work-col">
              <WorkbenchPanel />
            </div>
          )}
        </Content>
      </Layout>

      {/* 会话列表抽屉 */}
      <SessionListDrawer
        visible={sessionDrawerOpen}
        onClose={() => setSessionDrawerOpen(false)}
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSwitchSession={switchSession}
        onCreateSession={handleNewSession}
        onClearSession={handleClearSession}
        onDeleteSession={showDeleteConfirm}
      />

      {/* 工具列表抽屉（集成参数配置） */}
      <ToolListDrawerWithConfig
        visible={toolDrawerVisible}
        onClose={() => setToolDrawerVisible(false)}
        tools={tools}
      />

      {/* 删除确认 Modal */}
      <Modal
        title={
          <span className="delete-modal-title">
            <ExclamationCircleOutlined style={{ marginRight: 8 }} />
            {t('agent_confirm_delete_session')}
          </span>
        }
        open={deleteModalVisible}
        onOk={handleDeleteConfirm}
        onCancel={() => {
          setDeleteModalVisible(false);
          setConfirmText('');
          setSessionToDelete(null);
        }}
        okText={t('confirm_delete')}
        cancelText={t('cancel')}
        okButtonProps={{
          danger: true,
          disabled: confirmText !== t('confirm_delete'),
        }}
        className="delete-confirm-modal qc-modal"
      >
        <div style={{ marginBottom: 16 }}>
          <p><strong>{t('agent_delete_warning_main')}</strong></p>

          <div className="delete-warning-box">
            <p className="delete-warning-title">{t('agent_delete_warning_title')}</p>
            <ul className="delete-warning-list">
              <li>{t('agent_delete_warning_item1')}</li>
              <li>{t('agent_delete_warning_item2')}</li>
              <li>{t('agent_delete_warning_item3')}</li>
            </ul>
            <p className="delete-warning-note">
              <strong>{t('agent_delete_warning_note_prefix')}</strong>{t('agent_delete_warning_note_body')}
            </p>
          </div>

          <p className="delete-confirm-hint">
            {t('please_input')} <strong className="delete-confirm-highlight">{t('confirm_delete')}</strong> {t('agent_to_continue')}
          </p>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={`${t('please_input')}：${t('confirm_delete')}`}
            style={{ width: '100%' }}
          />
        </div>
      </Modal>
    </Layout>
  );
};

// 使用 App 组件包裹以提供上下文支持
const AgentWithApp = () => (
  <App>
    <Agent />
  </App>
);

export default AgentWithApp;
