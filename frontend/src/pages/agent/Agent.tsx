import { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Layout,
  Input,
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
} from '@ant-design/icons';
import { useAgentStore } from './store/agentStore';
import type { Message, Tool } from './store/agentStore';
import './Agent.css';

const { Content } = Layout;
const { TextArea } = Input;

// 错误详情弹窗组件
const ErrorDetailModal = ({
  visible,
  onClose,
  errorDetail,
}: {
  visible: boolean;
  onClose: () => void;
  errorDetail: string;
}) => (
  <Modal
    title="错误详情"
    open={visible}
    onCancel={onClose}
    footer={[
      <Button key="close" onClick={onClose}>
        关闭
      </Button>,
    ]}
    width={600}
  >
    <div className="error-detail-content">
      <pre>{errorDetail}</pre>
    </div>
  </Modal>
);

// 消息气泡组件
const ChatMessage = ({ message }: { message: Message }) => {
  const isUser = message.role === 'user';
  const isTool = message.role === 'tool';
  const isError = message.isError;
  const [errorModalVisible, setErrorModalVisible] = useState(false);

  return (
    <>
      <div className={`chat-message ${message.role} ${isError ? 'error' : ''}`}>
        <div className="message-avatar">
          {isUser ? <Avatar icon={<UserOutlined />} /> :
           isTool ? <Avatar icon={<CodeOutlined />} style={{ background: '#52c41a' }} /> :
           isError ? <Avatar icon={<ExclamationCircleOutlined />} style={{ background: '#ff4d4f' }} /> :
           <Avatar icon={<RobotOutlined />} style={{ background: '#1890ff' }} />}
        </div>
        <div className="message-content">
          <div className="message-header">
            <span className="message-role">
              {isUser ? '用户' : isTool ? '工具' : isError ? '错误' : 'AI Agent'}
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
                <Tooltip title="点击查看详细错误信息">
                  <Button
                    type="text"
                    size="small"
                    icon={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
                    onClick={() => setErrorModalVisible(true)}
                    className="error-icon-btn"
                  />
                </Tooltip>
              )}
              {message.content}
            </div>
            {message.toolResult && (
              <div className="tool-result">
                <pre>{message.toolResult}</pre>
              </div>
            )}
          </div>
        </div>
      </div>
      {isError && (
        <ErrorDetailModal
          visible={errorModalVisible}
          onClose={() => setErrorModalVisible(false)}
          errorDetail={message.errorDetail || '无详细错误信息'}
        />
      )}
    </>
  );
};

// 工具列表抽屉
const ToolListDrawer = ({
  visible,
  onClose,
  tools,
}: {
  visible: boolean;
  onClose: () => void;
  tools: Tool[];
}) => (
  <Drawer
    title="可用工具"
    placement="right"
    onClose={onClose}
    open={visible}
    size="default"
  >
    <div className="tool-list">
      {tools.map(tool => (
        <div key={tool.name} className="tool-list-item">
          <Tag color="blue">{tool.name}</Tag>
          <p className="tool-description">{tool.description}</p>
        </div>
      ))}
    </div>
  </Drawer>
);

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
  sessions: any[];
  currentSessionId: string;
  onSwitchSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onClearSession: () => void;
  onDeleteSession: (sessionId: string, e: React.MouseEvent) => void;
}) => {
  return (
    <Drawer
      title="会话列表"
      placement="right"
      onClose={onClose}
      open={visible}
      size="default"
      className="session-drawer"
      extra={
        <Tooltip title="新会话">
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
                      label: '清空消息',
                      icon: <ClearOutlined />,
                      onClick: (e) => {
                        e.domEvent.stopPropagation();
                        onClearSession();
                      },
                    },
                    {
                      key: 'delete',
                      label: (
                        <span style={{ color: '#ff4d4f' }}>
                          <DeleteOutlined /> 删除会话
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
  // 使用 t 函数来避免 TypeScript 的 "declared but never read" 错误
  void t;
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
    message.success('新会话已创建');
    setSessionDrawerOpen(false);
  };

  const handleClearSession = async () => {
    await clearSession(currentSessionId);
    message.success('会话已清空');
  };

  const handleDeleteConfirm = async () => {
    if (confirmText !== '确认删除' || !sessionToDelete) {
      return;
    }

    const success = await deleteSession(sessionToDelete);
    if (success) {
      message.success('会话已删除');
      setDeleteModalVisible(false);
      setConfirmText('');
      setSessionToDelete(null);
    } else {
      message.error('删除失败');
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
    <Layout className="ai-agent-layout">
      {/* 主内容区 */}
      <Layout className="agent-content-layout">
        {/* 头部 */}
        <div className="agent-header">
          <div className="header-left">
            <Tooltip title="会话列表">
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
            <Tooltip title="会话列表">
              <Button
                type="text"
                icon={<HistoryOutlined />}
                onClick={toggleSessionDrawer}
                className={sessionDrawerOpen ? 'active' : ''}
              />
            </Tooltip>
            <Tooltip title="工具列表">
              <Button
                type="text"
                icon={<ToolOutlined />}
                onClick={() => setToolDrawerVisible(true)}
              />
            </Tooltip>
            <Tooltip title="清空会话">
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
              description="开始与 AI Agent 对话"
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
                  <span>AI 正在思考...</span>
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
              placeholder="输入消息，按 Enter 发送，Shift+Enter 换行..."
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
            支持工具调用: {tools.slice(0, 3).map(t => t.name).join(', ')}
            {tools.length > 3 && ` 等 ${tools.length} 个工具`}
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

      {/* 工具列表抽屉 */}
      <ToolListDrawer
        visible={toolDrawerVisible}
        onClose={() => setToolDrawerVisible(false)}
        tools={tools}
      />

      {/* 删除确认 Modal */}
      <Modal
        title={
          <span style={{ color: '#ff4d4f' }}>
            <ExclamationCircleOutlined style={{ marginRight: 8 }} />
            确认删除会话
          </span>
        }
        open={deleteModalVisible}
        onOk={handleDeleteConfirm}
        onCancel={() => {
          setDeleteModalVisible(false);
          setConfirmText('');
          setSessionToDelete(null);
        }}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{
          danger: true,
          disabled: confirmText !== '确认删除',
        }}
      >
        <div style={{ marginBottom: 16 }}>
          <p><strong>您即将删除此会话，该操作不可恢复。</strong></p>

          <div style={{
            background: '#fff2f0',
            border: '1px solid #ffccc7',
            borderRadius: 4,
            padding: 12,
            marginBottom: 16
          }}>
            <p style={{ margin: '0 0 8px 0', fontWeight: 500 }}>删除将影响以下内容：</p>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li>该会话的所有历史消息将被永久删除</li>
              <li>无法再通过此会话ID追溯对话记录</li>
              <li>未整合到长期记忆的近期对话细节将丢失</li>
            </ul>
            <p style={{ margin: '8px 0 0 0', color: '#666' }}>
              <strong>注意：</strong>已整合的长期记忆（MEMORY.md）不受影响
            </p>
          </div>

          <p style={{ marginBottom: 8 }}>
            请输入 <strong style={{ color: '#ff4d4f' }}>确认删除</strong> 以继续：
          </p>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="请输入：确认删除"
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
