import { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  Layout,
  Input,
  InputNumber,
  Button,
  Avatar,
  Spin,
  Empty,
  Drawer,
  Tag,
  Tooltip,
  Modal,
  Dropdown,
  App,
  Switch,
  Space,
  Typography,
} from 'antd';
import {
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ToolOutlined,
  RobotOutlined,
  UserOutlined,
  CodeOutlined,
  ClearOutlined,
  MoreOutlined,
  ExclamationCircleOutlined,
  MessageOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  LockOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  EyeOutlined,
  SaveOutlined,
  ReloadOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { useAgentStore } from './store/agentStore';
import type { Message, Session, Tool } from './store/agentStore';
import {
  toolParamApi,
  ToolParamsResponse,
  ToolParamValue,
} from '../../api/agentApi';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { IntentPanelRenderer } from './components/IntentPanels';
import './Agent.css';
import { QUANT_COLORS } from '@/utils/colors';

const { Content } = Layout;
const { TextArea } = Input;
const { Text } = Typography;

// 错误详情弹窗组件
const ErrorDetailModal = ({
  visible,
  onClose,
  errorDetail,
}: {
  visible: boolean;
  onClose: () => void;
  errorDetail: string;
}) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={t('agent_error_detail')}
      open={visible}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>
          {t('close_button')}
        </Button>,
      ]}
      width={600}
    >
      <div className="error-detail-content">
        <pre>{errorDetail}</pre>
      </div>
    </Modal>
  );
};

// 消息气泡组件
const ChatMessage = ({ message }: { message: Message }) => {
  const isUser = message.role === 'user';
  const isTool = message.role === 'tool';
  const isError = message.isError;
  const [errorModalVisible, setErrorModalVisible] = useState(false);
  const { message: antMessage } = App.useApp();
  const { t } = useTranslation();

  // 处理意图面板操作
  const handleIntentAction = (actionType: string) => {
    antMessage.info(t('agent_execute_action', { action: actionType }));
    // TODO: 根据 actionType 跳转到相应功能页面或执行操作
  };

  // 判断是否为 AI 消息且有意图信息
  const hasIntent = !isUser && !isTool && message.intent;

  return (
    <>
      <div className={`chat-message ${message.role} ${isError ? 'error' : ''}`}>
        <div className="message-avatar">
          {isUser ? <Avatar icon={<UserOutlined />} /> :
           isTool ? <Avatar icon={<CodeOutlined />} style={{ background: QUANT_COLORS.positive }} /> :
           isError ? <Avatar icon={<ExclamationCircleOutlined />} style={{ background: QUANT_COLORS.negative }} /> :
           <Avatar icon={<RobotOutlined />} style={{ background: QUANT_COLORS.info }} />}
        </div>
        <div className="message-content">
          <div className="message-header">
            <span className="message-role">
              {isUser ? t('agent_user') : isTool ? t('agent_tool') : isError ? t('error') : (message.roleName || 'AI Agent')}
            </span>
            <span className="message-time">
              {new Date(message.timestamp).toLocaleTimeString()}
            </span>
          </div>
          <div className={`message-body ${isError ? 'error-body' : ''}`}>
            {message.toolCalls && (
              <div className="tool-calls">
                {message.toolCalls.map(tc => (
                  <Tag key={tc.id} color="blue" icon={<ToolOutlined />}>
                    {tc.name}
                  </Tag>
                ))}
              </div>
            )}
            <div className="message-text">
              {isError && (
                <Tooltip title={t('agent_click_view_error')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<ExclamationCircleOutlined style={{ color: QUANT_COLORS.negative }} />}
                    onClick={() => setErrorModalVisible(true)}
                    className="error-icon-btn"
                  />
                </Tooltip>
              )}
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
            {message.toolResult && (
              <div className="tool-result">
                <pre>{message.toolResult}</pre>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 根据意图显示专属面板 */}
      {hasIntent && (
        <IntentPanelRenderer
          intent={message.intent!}
          roleName={message.roleName || t('agent_ai_assistant')}
          content={message.content}
          structuredData={message.structuredData || {}}
          actions={message.actions || []}
          onAction={handleIntentAction}
        />
      )}

      {isError && (
        <ErrorDetailModal
          visible={errorModalVisible}
          onClose={() => setErrorModalVisible(false)}
          errorDetail={message.errorDetail || t('agent_no_error_detail')}
        />
      )}
    </>
  );
};

// 工具列表抽屉（集成参数配置功能）
const ToolListDrawerWithConfig = ({
  visible,
  onClose,
  tools,
}: {
  visible: boolean;
  onClose: () => void;
  tools: Tool[];
}) => {
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [toolsParams, setToolsParams] = useState<Record<string, ToolParamsResponse>>({});
  const [loadingParams, setLoadingParams] = useState<Set<string>>(new Set());
  const [editingValues, setEditingValues] = useState<Record<string, Record<string, unknown>>>({});
  const [showSensitive, setShowSensitive] = useState<Record<string, Record<string, boolean>>>({});
  const { message } = App.useApp();
  const { t } = useTranslation();

  // 切换工具展开/折叠
  const toggleExpand = async (toolName: string) => {
    const newExpanded = new Set(expandedTools);
    if (newExpanded.has(toolName)) {
      newExpanded.delete(toolName);
    } else {
      newExpanded.add(toolName);
      // 加载参数
      if (!toolsParams[toolName]) {
        await loadToolParams(toolName);
      }
    }
    setExpandedTools(newExpanded);
  };

  // 加载工具参数
  const loadToolParams = async (toolName: string) => {
    setLoadingParams(prev => new Set(prev).add(toolName));
    try {
      const data = await toolParamApi.getToolParams(toolName, false);
      setToolsParams(prev => ({ ...prev, [toolName]: data }));
      
      // 初始化编辑值（仅当有参数时）
      if (data.params && Object.keys(data.params).length > 0) {
        const initialValues: Record<string, unknown> = {};
        Object.entries(data.params).forEach(([key, param]) => {
          initialValues[key] = param.value;
        });
        setEditingValues(prev => ({ ...prev, [toolName]: initialValues }));
      }
    } catch (error) {
      // 404 表示工具无参数模板，这不是错误
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        setToolsParams(prev => ({ 
          ...prev, 
          [toolName]: { tool_name: toolName, params: {} } 
        }));
      } else {
        message.error(t('agent_load_tool_params_failed', { name: toolName }));
      }
    } finally {
        setLoadingParams(prev => {
          const next = new Set(prev);
          next.delete(toolName);
          return next;
        });
    }
  };

  // 切换敏感参数显示
  const toggleSensitive = async (toolName: string, paramName: string) => {
    if (!showSensitive[toolName]?.[paramName]) {
      try {
        const data = await toolParamApi.getToolParams(toolName, true);
        setToolsParams(prev => ({ ...prev, [toolName]: data }));
        setEditingValues(prev => ({
          ...prev,
          [toolName]: {
            ...prev[toolName],
            [paramName]: data.params[paramName].value,
          },
        }));
        setShowSensitive(prev => ({
          ...prev,
          [toolName]: { ...prev[toolName], [paramName]: true },
        }));
      } catch {
        message.error(t('agent_sensitive_value_failed'));
      }
    } else {
      // 重新加载脱敏版本
      await loadToolParams(toolName);
      setShowSensitive(prev => ({
        ...prev,
        [toolName]: { ...prev[toolName], [paramName]: false },
      }));
    }
  };

  // 更新参数
  const handleUpdateParam = async (toolName: string, paramName: string, value: unknown) => {
    try {
      await toolParamApi.setToolParam(toolName, paramName, value);
      message.success(t('agent_param_updated', { name: paramName }));
      await loadToolParams(toolName); // 刷新参数
    } catch (error) {
      message.error(t('agent_update_failed', { message: error instanceof Error ? error.message : t('unknown_error') }));
    }
  };

  // 渲染来源标签
  const renderSourceTag = (source: string) => {
    const config: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
      database: { color: 'blue', icon: <DatabaseOutlined />, text: t('agent_source_database') },
      environment: { color: 'green', icon: <GlobalOutlined />, text: t('env_variables') },
      default: { color: 'default', icon: <SettingOutlined />, text: t('default_value') },
    };
    const c = config[source] || config.default;
    return <Tag color={c.color} icon={c.icon}>{c.text}</Tag>;
  };

  // 渲染参数输入控件
  const renderParamInput = (
    toolName: string,
    paramName: string,
    param: ToolParamValue
  ) => {
    if (param.sensitive && !showSensitive[toolName]?.[paramName]) {
      return (
        <Space>
          <Input.Password
            value="••••••••"
            disabled
            style={{ width: 160 }}
            size="small"
          />
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => toggleSensitive(toolName, paramName)}
          >
            {t('show')}
          </Button>
        </Space>
      );
    }

    switch (param.type) {
      case 'integer':
        return (
          <InputNumber
            size="small"
            value={editingValues[toolName]?.[paramName] as number}
            onChange={(value) =>
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: value },
              }))
            }
            style={{ width: 120 }}
            onPressEnter={(e: React.KeyboardEvent<HTMLInputElement>) =>
              handleUpdateParam(toolName, paramName, e.currentTarget.value)
            }
          />
        );
      case 'float':
        return (
          <InputNumber
            size="small"
            value={editingValues[toolName]?.[paramName] as number}
            onChange={(value) =>
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: value },
              }))
            }
            step={0.1}
            style={{ width: 120 }}
          />
        );
      case 'boolean':
        return (
          <Switch
            size="small"
            checked={Boolean(editingValues[toolName]?.[paramName])}
            onChange={(checked) => {
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: checked },
              }));
              handleUpdateParam(toolName, paramName, checked);
            }}
          />
        );
      default:
        return (
          <Input
            size="small"
            value={editingValues[toolName]?.[paramName] as string}
            onChange={(e) =>
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: e.target.value },
              }))
            }
            onPressEnter={(e) =>
              handleUpdateParam(toolName, paramName, e.currentTarget.value)
            }
            style={{ width: 160 }}
          />
        );
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <ToolOutlined />
          <span>{t('agent_available_tools')}</span>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => {
              setToolsParams({});
              // 重命名局部变量避免与翻译函数 t 遮蔽冲突
              tools.forEach(tool => loadToolParams(tool.name));
            }}
          >
            {t('agent_refresh_config')}
          </Button>
        </Space>
      }
      placement="right"
      onClose={onClose}
      open={visible}
      size="large"
      className="tool-list-config-drawer"
    >
      <div className="tool-list-with-config">
        {tools.map(tool => {
          const isExpanded = expandedTools.has(tool.name);
          const params = toolsParams[tool.name];
          const isLoading = loadingParams.has(tool.name);

          return (
            <div key={tool.name} className={`tool-item-wrapper ${isExpanded ? 'expanded' : ''}`}>
              {/* 工具项头部 */}
              <div
                className="tool-item-header"
                onClick={() => toggleExpand(tool.name)}
              >
                <div className="tool-item-info">
                  <Space>
                    <Tag color="blue">{tool.name}</Tag>
                    {params && (
                      params.params && Object.values(params.params).some(p => p.configured) ? (
                        <CheckCircleOutlined style={{ color: QUANT_COLORS.positive }} />
                      ) : null
                    )}
                  </Space>
                </div>
                <Space>
                  <Tooltip title={isExpanded ? t('agent_collapse_params') : t('agent_expand_params')}>
                    {isExpanded ? <UpOutlined /> : <DownOutlined />}
                  </Tooltip>
                </Space>
              </div>

              {/* 工具描述 */}
              <p className="tool-description">{tool.description}</p>

              {/* 展开的参数面板 */}
              {isExpanded && (
                <div className="tool-params-panel">
                  {isLoading ? (
                    <Spin size="small" tip={t('loading')} />
                  ) : params && params.params && Object.keys(params.params).length > 0 ? (
                    <div className="params-container">
                      {Object.entries(params.params).map(
                        ([paramName, param]) => (
                          <div key={paramName} className="param-row">
                            <div className="param-info">
                              <Space size={4}>
                                {param.sensitive ? (
                                  <LockOutlined
                                    style={{
                                      fontSize: 12,
                                      color: QUANT_COLORS.warning,
                                    }}
                                  />
                                ) : null}
                                <Text
                                  strong
                                  style={{ fontSize: 12 }}
                                >
                                  {paramName}
                                </Text>
                                {renderSourceTag(param.source)}
                              </Space>
                              {param.description && (
                                <Text
                                  type="secondary"
                                  style={{
                                    fontSize: 11,
                                    display: 'block',
                                    marginTop: 2,
                                  }}
                                >
                                  {param.description}
                                </Text>
                              )}
                            </div>

                            <div className="param-action">
                              <Space size={4}>
                                {renderParamInput(
                                  tool.name,
                                  paramName,
                                  param
                                )}
                                {(editingValues[tool.name]?.[paramName] !==
                                  param.value ||
                                  !param.configured) && (
                                  <Button
                                    type="primary"
                                    size="small"
                                    icon={<SaveOutlined />}
                                    onClick={() =>
                                      handleUpdateParam(
                                        tool.name,
                                        paramName,
                                        editingValues[tool.name]?.[
                                          paramName
                                        ]
                                      )
                                    }
                                  >
                                    {t('save')}
                                  </Button>
                                )}
                              </Space>
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  ) : (
                    // 工具存在但无参数或已加载完成无参数
                    <Empty
                      description={
                        <span style={{ fontSize: 11 }}>
                          {t('agent_no_params_needed')}
                        </span>
                      }
                      styles={{ image: { height: 35 } }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Drawer>
  );
};

// 会话列表抽屉组件
const SessionListDrawer = ({
  visible,
  onClose,
  sessions,
  currentSessionId,
  onSwitchSession,
  onCreateSession,
  onClearSession,
  onDeleteSession,
}: {
  visible: boolean;
  onClose: () => void;
  sessions: Session[];
  currentSessionId: string;
  onSwitchSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onClearSession: () => void;
  onDeleteSession: (sessionId: string, e: React.MouseEvent) => void;
}) => {
  const { t } = useTranslation();
  return (
    <Drawer
      title={t('agent_session_list')}
      placement="right"
      onClose={onClose}
      open={visible}
      size="default"
      className="session-drawer"
      extra={
        <Tooltip title={t('agent_new_session')}>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={onCreateSession}
          />
        </Tooltip>
      }
    >
      <div className="session-list">
        {sessions.map(session => (
          <Tooltip
            key={session.id}
            title={new Date(session.updatedAt).toLocaleString()}
            placement="left"
          >
            <div
              className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
              onClick={() => {
                onSwitchSession(session.id);
                onClose();
              }}
            >
              <span className="session-name-text">{session.name}</span>
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'clear',
                      label: t('agent_clear_messages'),
                      icon: <ClearOutlined />,
                      onClick: (e) => {
                        e.domEvent.stopPropagation();
                        onClearSession();
                      },
                    },
                    {
                      key: 'delete',
                      label: (
                        <span style={{ color: QUANT_COLORS.negative }}>
                          <DeleteOutlined /> {t('agent_delete_session')}
                        </span>
                      ),
                      danger: true,
                      onClick: (e) => {
                        e.domEvent.stopPropagation();
                        onDeleteSession(session.id, e.domEvent as React.MouseEvent);
                      },
                    },
                  ],
                }}
                trigger={['click']}
              >
                <Button
                  type="text"
                  size="small"
                  icon={<MoreOutlined />}
                  onClick={(e) => e.stopPropagation()}
                  className="session-more-btn"
                />
              </Dropdown>
            </div>
          </Tooltip>
        ))}
      </div>
    </Drawer>
  );
};

// 主页面
const Agent = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');
  const [toolDrawerVisible, setToolDrawerVisible] = useState(false);
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false);
  const [deleteModalVisible, setDeleteModalVisible] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState('');

  const {
    messages,
    sessions,
    currentSessionId,
    tools,
    loading,
    sendMessage,
    fetchSessions,
    switchSession,
    createSession,
    clearSession,
    deleteSession,
    fetchTools,
  } = useAgentStore();

  // 初始化
  useEffect(() => {
    fetchSessions();
    fetchTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, []);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;
    const content = inputValue;
    setInputValue('');
    await sendMessage(content);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewSession = async () => {
    await createSession();
    message.success(t('agent_session_created'));
    setSessionDrawerOpen(false);
  };

  const handleClearSession = async () => {
    await clearSession(currentSessionId);
    message.success(t('agent_session_cleared'));
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
    // ponytail: Agent 是全屏聊天界面，page-fullscreen 抵消 ConsoleLayout Content 的 padding
    <Layout className="ai-agent-layout page-fullscreen">
      {/* 主内容区 */}
      <Layout className="agent-content-layout">
        {/* 头部 */}
        <div className="agent-header">
          <div className="header-left">
            <Tooltip title={t('agent_session_list')}>
              <Button
                type="text"
                icon={<MessageOutlined />}
                onClick={toggleSessionDrawer}
                className={sessionDrawerOpen ? 'active' : ''}
              />
            </Tooltip>
            <span className="session-name">
              {sessions.find(s => s.id === currentSessionId)?.name || 'AI Agent'}
            </span>
          </div>
          <div className="header-right">
            <Tooltip title={t('agent_session_list')}>
              <Button
                type="text"
                icon={<HistoryOutlined />}
                onClick={toggleSessionDrawer}
                className={sessionDrawerOpen ? 'active' : ''}
              />
            </Tooltip>
            <Tooltip title={t('agent_tool_list')}>
              <Button
                type="text"
                icon={<ToolOutlined />}
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
          </div>
        </div>

        {/* 消息列表 */}
        <Content className="agent-content">
          {messages.length === 0 ? (
            <Empty
              description={t('agent_start_chat')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            <div className="messages-container">
              {messages.map(msg => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              {loading && (
                <div className="loading-indicator">
                  <Spin size="small" />
                  <span>{t('agent_thinking')}</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </Content>

        {/* 输入区 */}
        <div className="agent-input-area">
          <div className="input-wrapper">
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('agent_input_placeholder')}
              autoSize={{ minRows: 1, maxRows: 6 }}
              disabled={loading}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              loading={loading}
              disabled={!inputValue.trim()}
            />
          </div>
          <div className="input-hint">
            {t('agent_support_tools', { tools: tools.slice(0, 3).map(tool => tool.name).join(', ') })}
            {tools.length > 3 && ` ${t('agent_and_more_tools', { total: tools.length })}`}
          </div>
        </div>
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
        className="delete-confirm-modal"
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
