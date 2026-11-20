/**
 * 聊天面板 —— 自 Agent.tsx 原样拆出（P1 工作台改造，仅文件移动不改语义）。
 * SSE 消息流/会话切换/意图面板/工具抽屉逻辑全部沿用 agentStore 与既有组件，
 * 本文件不关心右栏工作面板（互不依赖）。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Input,
  Button,
  Spin,
  Modal,
  Tooltip,
  App,
} from 'antd';
import {
  SendOutlined,
  ExclamationCircleOutlined,
  RobotOutlined,
  UserOutlined,
  CodeOutlined,
  DownOutlined,
  RightOutlined,
  LineChartOutlined,
  DashboardOutlined,
  GlobalOutlined,
  FundOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAgentStore } from '../store/agentStore';
import type { ToolCall, Message } from '../store/agentStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { IntentPanelRenderer } from './IntentPanels';
import { useNavigate } from 'react-router-dom';

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

/**
 * 快捷指令：兑现设计文档的「快捷指令条 /train /backtest /deploy」承诺。
 * 点击是「填充不直发」——后端不解析斜杠命令，填自然语言模板更诚实，
 * 也留出改品种/参数的空间。空态能力卡与输入框上方 chips 共用这组数据。
 */
const QUICK_PROMPTS = [
  { key: 'train', icon: <LineChartOutlined /> },     // 行情速览（key 名保留历史命名，语义见 i18n）
  { key: 'backtest', icon: <DashboardOutlined /> },  // 市场情绪
  { key: 'deploy', icon: <GlobalOutlined /> },       // 最新资讯（web 检索）
  { key: 'diagnose', icon: <FundOutlined /> },       // K线分析
] as const;

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
      className="qc-modal"
    >
      <div className="error-detail-content">
        <pre>{errorDetail}</pre>
      </div>
    </Modal>
  );
};

// 消息气泡组件

/**
 * 消息内轻量折叠块（工具结果 / 思考过程共用）：默认收起，展开时长文本限高滚动。
 * 用 button+state 而非 antd Collapse：贴合现有消息样式、不引入额外包裹层。
 */
const CollapsibleBlock = ({
  title,
  variant,
  children,
}: {
  title: string;
  variant: 'tool' | 'reasoning';
  children: React.ReactNode;
}) => {
  const [open, setOpen] = useState(false);
  return (
    <div className={`collapse-block ${variant}`}>
      <button type="button" className="collapse-toggle" onClick={() => setOpen(!open)}>
        {open ? <DownOutlined className="collapse-caret" /> : <RightOutlined className="collapse-caret" />}
        <span>{title}</span>
      </button>
      {open && <div className="collapse-body">{children}</div>}
    </div>
  );
};

/** §6.14 头像：32×32 方形（8px 圆角），底色/字色由 Agent.css 按 token 分流 */
const MessageAvatar = ({ kind, icon }: { kind: 'ai' | 'user' | 'tool' | 'err'; icon: React.ReactNode }) => (
  <div className={`msg-avatar ${kind}`}>{icon}</div>
);

/**
 * §6.14 工具链（demo .chain/.chain-node）：绿轨 + 方徽 + mono 工具名 + 参数摘要 + 状态 chip。
 * 只展示后端 tool_calls/tool_result 已上报字段（名称 / 参数 / 是否有结果），不编造耗时。
 */
const ToolChain = ({ calls, hasResult }: { calls: ToolCall[]; hasResult: boolean }) => {
  const { t } = useTranslation();
  return (
    <div className="tool-chain">
      {calls.map((tc) => {
        const args = JSON.stringify(tc.arguments ?? {});
        return (
          <div className="chain-node" key={tc.id}>
            <div className="chain-head">
              <span className="tool-chip">&lt;/&gt;</span>
              <span className="chain-name">{tc.name}</span>
              <span className="chain-args" title={args}>{args === '{}' ? '' : args}</span>
              <span className={`chain-status ${hasResult ? 'chip-ok' : 'chip-run'}`}>
                {hasResult ? t('level_success') : t('in_progress')}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

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
        <MessageAvatar
          kind={isUser ? 'user' : isTool ? 'tool' : isError ? 'err' : 'ai'}
          icon={
            isUser ? <UserOutlined /> :
            isTool ? <CodeOutlined /> :
            isError ? <ExclamationCircleOutlined /> :
            <RobotOutlined />
          }
        />
        <div className="message-content">
          <div className="message-header">
            <span className="message-role">
              {isUser ? t('agent_user') : isTool ? t('agent_tool') : isError ? t('error') : (message.roleName || 'AI Agent')}
            </span>
            {/* 迭代徽标：仅在 SSE 上报过 ReAct 轮次时出现（纯展示，无额外请求） */}
            {message.iteration && (
              <span className="message-iteration">
                {message.iteration.max > 0
                  ? t('agent_iteration_badge', {
                      current: message.iteration.current,
                      max: message.iteration.max,
                    })
                  : t('agent_iteration_badge_no_max', { current: message.iteration.current })}
              </span>
            )}
            <span className="message-time">
              {message.timestamp ? new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) : ''}
            </span>
          </div>
          <div className={`message-body ${isError ? 'error-body' : ''}`}>
            {!isUser && !isTool && message.reasoning && (
              <CollapsibleBlock variant="reasoning" title={t('agent_reasoning')}>
                <pre>{message.reasoning}</pre>
              </CollapsibleBlock>
            )}
            <div className="message-text">
              {isError && (
                <Tooltip title={t('agent_click_view_error')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<ExclamationCircleOutlined style={{ color: 'var(--qc-error)' }} />}
                    onClick={() => setErrorModalVisible(true)}
                    className="error-icon-btn"
                  />
                </Tooltip>
              )}
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          </div>
          {/* 工具链按 §6.14 出气泡外左侧绿轨；有结果时以「已返回」折叠块展示，不再重复进行中行 */}
          {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
            <ToolChain calls={message.toolCalls} hasResult={!!message.toolResult} />
          )}
          {/* 工具输出默认折叠，不再全量刷屏 */}
          {message.toolResult && (
            <CollapsibleBlock variant="tool" title={t('agent_tool_result')}>
              <pre>{message.toolResult}</pre>
            </CollapsibleBlock>
          )}
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
  const inputRef = useRef<React.ComponentRef<typeof Input.TextArea>>(null);
  const [inputValue, setInputValue] = useState('');

  const {
    messages,
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

  // 快捷指令（空态能力卡 / chips 条共用）：填充输入框并聚焦，不直接发送
  const applyPrompt = (key: (typeof QUICK_PROMPTS)[number]['key']) => {
    setInputValue(t(`agent_quick_${key}_prompt`));
    inputRef.current?.focus();
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
          // 空态：定位描述 + 四类能力引导，点击即填充对应指令
          <div className="chat-empty">
            <div className="chat-empty-title">{t('agent_empty_title')}</div>
            <div className="chat-empty-desc">{t('agent_empty_desc')}</div>
            <div className="chat-empty-caps">
              {QUICK_PROMPTS.map(cap => (
                <button
                  key={cap.key}
                  className="chat-empty-cap"
                  onClick={() => applyPrompt(cap.key)}
                >
                  <span className="cap-icon">{cap.icon}</span>
                  <span className="cap-copy">
                    <span className="cap-label">{t(`agent_quick_${cap.key}_label`)}</span>
                    <span className="cap-desc">{t(`agent_quick_${cap.key}_desc`)}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
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
        {/* 快捷指令条：常驻轻量 chips，点击填充输入框 */}
        <div className="quick-commands">
          {QUICK_PROMPTS.map(cap => (
            <button
              key={cap.key}
              className="quick-chip"
              disabled={loading}
              onClick={() => applyPrompt(cap.key)}
            >
              {cap.icon}
              <span>{t(`agent_quick_${cap.key}_label`)}</span>
            </button>
          ))}
        </div>
        <div className="input-wrapper">
          <Input.TextArea
            ref={inputRef}
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
          {t('agent_input_hint')}
        </div>
      </div>
    </>
  );
};

export default ChatPanel;
