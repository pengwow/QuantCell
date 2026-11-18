/**
 * 聊天面板 —— 自 Agent.tsx 原样拆出（P1 工作台改造，仅文件移动不改语义）。
 * SSE 消息流/会话切换/意图面板/工具抽屉逻辑全部沿用 agentStore 与既有组件，
 * 本文件不关心右栏工作面板（互不依赖）。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Input,
  Button,
  Avatar,
  Spin,
  Empty,
  Modal,
  Tag,
  Tooltip,
  App,
} from 'antd';
import {
  SendOutlined,
  ExclamationCircleOutlined,
  ToolOutlined,
  RobotOutlined,
  UserOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAgentStore } from '../store/agentStore';
import type { Message } from '../store/agentStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { IntentPanelRenderer } from './IntentPanels';
import { useNavigate } from 'react-router-dom';
import { QUANT_COLORS } from '@/utils/colors';

/**
 * 意图面板 action.type → 现有路由（路径均取自 router/DynamicRouter.tsx，勿造新页面）。
 * 未列出的 action 走降级提示，清单与原因见 handleIntentAction。
 */
const INTENT_ACTION_ROUTES: Record<string, string> = {
  view_chart: '/chart',            // 行情图表
  view_kline: '/chart',            // K 线看图（无独立 K 线路由，图表页承载）
  backtest_strategy: '/backtest/config',  // 回测配置
  optimize_params: '/backtest/config',    // 参数优化在本轮回测配置里做
  view_code: '/strategy-editor',   // 策略编辑器
  deploy_strategy: '/strategy-worker',    // 创建/启动 worker 即部署
};

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
  const navigate = useNavigate();

  // 处理意图面板操作：能映射到现有页面就直接跳转，其余降级为提示（不造页面）。
  // 降级项的设计归属（等对应路由/交互落地后再接线）：
  //   view_positions / view_history -> 需交易持仓/成交历史页，当前路由表无此页面
  //   place_order / set_stop_loss / adjust_position -> 需在 worker 详情页（/strategy-worker/:workerId）内联执行，非页面跳转
  //   export_report / export_data -> 导出走接口下载，等 Agent 侧导出接口
  //   compare_symbols -> 需多标的对比视图，无对应页面
  //   view_risk_report -> 当前风险结论已由 risk_assessment 面板内联展示，暂无独立报告页
  const handleIntentAction = (actionType: string) => {
    const target = INTENT_ACTION_ROUTES[actionType];
    if (target) {
      navigate(target);
      return;
    }
    antMessage.info(t('agent_execute_action', { action: actionType }));
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

// 聊天面板主组件：消息流 + 输入区（与原 Agent.tsx 渲染结构一致）
const ChatPanel = () => {
  const { t } = useTranslation();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');

  const {
    messages,
    tools,
    loading,
    sendMessage,
  } = useAgentStore();

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

  return (
    <>
      {/* 消息列表 */}
      <div className="agent-content">
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
      </div>

      {/* 输入区 */}
      <div className="agent-input-area">
        <div className="input-wrapper">
          <Input.TextArea
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
    </>
  );
};

export default ChatPanel;
