// AI 策略生成对话框
// 流式链路：StrategyChatProvider（XRequest→SSE）→ useXChat 消息流 → Bubble.List 渲染
// 生成结果通过 x-card（A2UI v0.9 命令协议）渲染为交互卡片，支持「采纳代码 / 拒绝」操作
import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Modal, message, Progress, Segmented, Space, Spin } from 'antd';
import {
  DeleteOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  RedoOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Bubble, Sender, ThoughtChain } from '@ant-design/x';
import type { BubbleItemType } from '@ant-design/x';
import { XCard, registerCatalog } from '@ant-design/x-card';
import type { ActionPayload, Catalog, XAgentCommand_v0_9 } from '@ant-design/x-card';
import { useXChat } from '@ant-design/x-sdk';
import type { SSEOutput } from '@ant-design/x-sdk';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { aiModelApi } from '../api';
import type { ThinkingChainEventData } from '../api';
import {
  StrategyChatProvider,
  strategyChatRequest,
} from '../providers/StrategyChatProvider';
import type {
  StrategyChatInput,
  StrategyChatMessage,
  ThinkingChainHandler,
} from '../providers/StrategyChatProvider';

// ---------- 思维链类型 ----------

// 思维链步骤状态
interface ThinkingChainStepState {
  title: string;
  description: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
}

// 预加载思维链接口返回的步骤（不同后端版本字段命名不同，全部声明为可选以兼容）
interface PreloadedStep {
  title?: string;
  name?: string;
  step_name?: string;
  step?: number | string;
  step_number?: number | string;
  description?: string;
  content?: string;
  detail?: string;
}

// ---------- Markdown 渲染（气泡与卡片共用） ----------

// 代码块：带语言标签与复制按钮的深色容器
const CodeBlock = ({ className, children }: { className?: string; children?: React.ReactNode }) => {
  const language = className?.replace('language-', '') || '';
  const codeString = String(children).replace(/\n$/, '');

  return (
    <div className="relative group my-3">
      <div className="flex items-center justify-between bg-gray-800 dark:bg-gray-900 px-4 py-2 rounded-t-lg">
        <span className="text-xs text-gray-400 dark:text-gray-500">{language || 'code'}</span>
        <button
          onClick={() => {
            navigator.clipboard.writeText(codeString);
            message.success('代码已复制');
          }}
          className="text-xs text-gray-400 hover:text-white transition-colors"
        >
          复制
        </button>
      </div>
      <pre className="bg-gray-900 dark:bg-black p-4 rounded-b-lg overflow-x-auto text-sm max-h-[400px] overflow-y-auto">
        <code className={`hljs language-${language} text-gray-100`}>{children}</code>
      </pre>
    </div>
  );
};

// 表格容器：允许横向滚动
const TableWrapper = ({ children }: { children?: React.ReactNode }) => (
  <div className="overflow-x-auto my-3 rounded-lg border border-gray-200 dark:border-gray-700">
    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">{children}</table>
  </div>
);

// 统一 Markdown 渲染入口
const Markdown = ({ text }: { text: string }) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{
      code: CodeBlock,
      table: TableWrapper,
    }}
  >
    {text}
  </ReactMarkdown>
);

// ---------- x-card（A2UI v0.9）策略结果卡片 ----------

// 本地 catalog：声明卡片可用组件的 schema，模块加载时注册一次供所有 surface 共用
const STRATEGY_CATALOG_ID = 'local://strategy_result_catalog.json';

const STRATEGY_CATALOG: Catalog = {
  catalogId: STRATEGY_CATALOG_ID,
  components: {
    Column: { type: 'object', properties: {} },
    Row: { type: 'object', properties: {} },
    MarkdownView: { type: 'object', properties: { text: { type: 'string' } } },
    CodeView: { type: 'object', properties: { code: { type: 'string' } } },
    ActionButton: {
      type: 'object',
      properties: { text: { type: 'string' }, kind: { type: 'string' } },
    },
  },
};
registerCatalog(STRATEGY_CATALOG);

// 卡片组件树：值通过 path 绑定到各 surface 独立的 dataModel（/result 下）
const STRATEGY_RESULT_COMPONENTS = [
  { id: 'root', component: 'Column', children: ['result-desc', 'result-code', 'result-actions'] },
  { id: 'result-desc', component: 'MarkdownView', text: { path: '/result/content' } },
  { id: 'result-code', component: 'CodeView', code: { path: '/result/code' } },
  { id: 'result-actions', component: 'Row', children: ['result-accept', 'result-reject'] },
  {
    id: 'result-accept',
    component: 'ActionButton',
    text: '采纳代码',
    kind: 'primary',
    action: {
      event: {
        name: 'accept',
        // 触发时按 path 从 dataModel 解析出代码，回传到 onAction 的 payload.context.code.value
        context: { code: { path: '/result/code' } },
      },
    },
  },
  {
    id: 'result-reject',
    component: 'ActionButton',
    text: '拒绝',
    action: { event: { name: 'reject' } },
  },
];

// x-card 自定义组件实现
const CARD_COMPONENTS = {
  // 布局容器：x-card 无内置布局组件，children 由 NodeRenderer 递归渲染后作 React children 注入
  Column: ({ children }: { children?: React.ReactNode }) => (
    <div className="flex flex-col gap-3">{children}</div>
  ),
  Row: ({ children }: { children?: React.ReactNode }) => (
    <div className="flex flex-wrap items-center gap-2">{children}</div>
  ),
  MarkdownView: ({ text }: { text?: string }) => (
    <div className="text-sm leading-relaxed text-gray-700 dark:text-gray-300 prose prose-sm dark:prose-invert max-w-none">
      <Markdown text={text || ''} />
    </div>
  ),
  CodeView: ({ code }: { code?: string }) => <CodeBlock>{code || ''}</CodeBlock>,
  // onAction 由 XCard.Box 注入；点击时上报 action.event.name，context 由 Card 按 path 解析
  ActionButton: ({
    text,
    kind,
    action,
    onAction,
  }: {
    text?: string;
    kind?: string;
    action?: { event?: { name?: string } };
    onAction?: (name: string, context: Record<string, unknown>) => void;
  }) => (
    <Button
      type={kind === 'primary' ? 'primary' : 'default'}
      icon={kind === 'primary' ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
      onClick={() => onAction?.(action?.event?.name || '', {})}
    >
      {text}
    </Button>
  ),
};

// ---------- 组件 Props ----------

// 优化模式下用户未输入附加要求时，气泡里展示的默认描述（重试时据此判断不要把它拼进优化要求）
const OPTIMIZE_DEFAULT_DISPLAY = '优化当前编辑器中的策略代码';

export interface AIChatModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  width?: number;
  height?: string | number;
  welcomeIcon?: React.ReactNode;
  welcomeTitle?: string;
  welcomeDescription?: string;
  inputPlaceholder?: string;
  submitType?: 'enter' | 'shiftEnter';
  /** 编辑器当前代码快照；非空时输入区显示「优化当前代码」模式，发送时自动注入这段代码作为优化上下文 */
  currentCode?: string;
  /** 拼接在用户需求末尾发给后端的提示后缀（如策略类型标记），不显示在气泡里 */
  requirementSuffix?: string;
  onAcceptCode?: (code: string) => void;
  onRejectCode?: () => void;
  className?: string;
  bodyClassName?: string;
}

const AIChatModal: React.FC<AIChatModalProps> = ({
  open,
  onClose,
  title,
  width = 800,
  height = '70vh',
  welcomeIcon,
  welcomeTitle,
  welcomeDescription,
  inputPlaceholder,
  submitType = 'enter',
  currentCode,
  requirementSuffix,
  onAcceptCode,
  onRejectCode,
  className,
  bodyClassName,
}) => {
  const { t } = useTranslation();

  const [inputValue, setInputValue] = useState('');

  // 思维链面板状态
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingChainStepState[]>([]);
  const [thinkingProgress, setThinkingProgress] = useState(0);
  // 思维链缓存
  const thinkingChainCacheRef = useRef<{
    strategy_generation?: ThinkingChainStepState[];
  }>({});

  // ---------- Chat Provider / useXChat 接线 ----------

  // 思维链事件从 Provider 的 transformMessage 经 ref 上抛（仅能传递消息，无法携带组件状态）
  // ref.current 直接存 handler（结构与 Provider 要求的 { current: handler | null } 一致）
  const thinkingRef = useRef<ThinkingChainHandler | null>(null);
  useEffect(() => {
    thinkingRef.current = (data: ThinkingChainEventData) => {
      setThinkingProgress(data.progress);
      setThinkingSteps((prev) => {
        // 首次接收：按 total_steps 建表
        if (prev.length === 0 || prev.length !== data.total_steps) {
          const steps: ThinkingChainStepState[] = [];
          for (let i = 1; i <= data.total_steps; i++) {
            steps.push({
              title: i === data.current_step ? data.step_title : `步骤 ${i}`,
              description: i === data.current_step ? data.step_description || data.message || '' : '',
              status: i < data.current_step ? 'completed' : i === data.current_step ? data.status : 'pending',
            });
          }
          return steps;
        }
        // 后续接收：更新当前步骤，之前的标记完成
        return prev.map((step, index) => {
          const stepNumber = index + 1;
          if (stepNumber === data.current_step) {
            return {
              ...step,
              title: data.step_title,
              description: data.step_description || data.message || '',
              status: data.status,
            };
          }
          if (stepNumber < data.current_step) {
            return { ...step, status: 'completed' as const };
          }
          return step;
        });
      });
    };
  });

  // Provider 实例只创建一次（ref 在组件整个生命周期稳定，无需重建）
  const [provider] = useState(
    () => new StrategyChatProvider({ request: strategyChatRequest, thinkingRef }),
  );

  const {
    messages: chatMessages,
    isRequesting,
    onRequest,
    onReload,
    setMessages,
  } = useXChat<StrategyChatMessage, StrategyChatMessage, StrategyChatInput, SSEOutput>({
    provider,
    // 请求占位气泡：先渲染空 AI 气泡（loading 态由 Bubble 内置处理）
    requestPlaceholder: { role: 'ai', content: '' },
    // 请求失败兜底：错误信息透出到气泡，而不是静默丢弃（ERR_ABORTED 之类可感知）
    requestFallback: (_params, { error }) => ({
      role: 'ai',
      content: error?.message || '生成失败，请重试',
      code: '',
      failed: true,
    }),
  });

  // ---------- 流生命周期 ----------

  // 终止进行中的 SSE 流；abortController 在首次请求才创建，未请求过时 abort 会抛错，兜 try/catch
  const stopStream = useCallback(() => {
    try {
      if (strategyChatRequest.isRequesting) {
        strategyChatRequest.abort();
      }
    } catch {
      // 尚未发起过请求时无需终止
    }
  }, []);

  // 关闭弹窗即终止流
  useEffect(() => {
    if (!open) stopStream();
  }, [open, stopStream]);

  // ---------- 对话模式 ----------

  /** 对话模式：generate=生成新策略；optimize=基于编辑器当前代码优化（仅 currentCode 非空时可选） */
  const [chatMode, setChatMode] = useState<'generate' | 'optimize'>('generate');

  // 每次打开弹窗都回到生成模式，避免上次会话的优化模式串到新会话
  useEffect(() => {
    if (open) setChatMode('generate');
  }, [open]);

  // 组件卸载兜底
  useEffect(() => () => stopStream(), [stopStream]);

  // 思维链恢复为全 pending 的初始状态（新请求/重试/清空时调用）
  const resetThinking = useCallback(() => {
    setThinkingProgress(0);
    setThinkingSteps(
      (thinkingChainCacheRef.current.strategy_generation || []).map((s) => ({ ...s })),
    );
  }, []);

  // ---------- 发送 / 重试 / 清空 ----------

  // 组装请求参数：requirement（带类型后缀，发后端）+ displayContent（仅气泡展示）
  // 优化模式把编辑器当前代码注入 requirement 让模型有上下文；气泡只显示用户附加要求，不塞大段代码
  const buildRequestParams = useCallback(
    (displayContent: string): StrategyChatInput => {
      if (chatMode === 'optimize' && currentCode) {
        // 默认文案是描述而非优化要求，重试时不要重复拼回 requirement
        const extra =
          displayContent && displayContent !== OPTIMIZE_DEFAULT_DISPLAY
            ? `，优化要求：${displayContent}`
            : '';
        const requirement =
          `请优化以下策略代码${extra}，保持原有策略逻辑与接口约定不变，并说明优化点：\n\n` +
          '```python\n' +
          currentCode +
          '\n```' +
          (requirementSuffix || '');
        return { requirement, displayContent: displayContent || OPTIMIZE_DEFAULT_DISPLAY };
      }
      return { requirement: displayContent + (requirementSuffix || ''), displayContent };
    },
    [chatMode, currentCode, requirementSuffix],
  );

  const handleSend = (value?: string) => {
    const content = (value ?? inputValue).trim();
    // 优化模式允许空输入直接发送（默认要求：保持逻辑不变做质量优化）；生成模式必须有内容
    if (!content && chatMode !== 'optimize') {
      message.warning(t('input_empty') || '请输入内容');
      return;
    }
    // 同一时刻只保留一条生成流：新请求主动顶掉旧流（被顶掉的气泡以 abort 状态过滤）
    stopStream();
    resetThinking();
    onRequest(buildRequestParams(content));
    setInputValue('');
  };

  // 向前查找最近一条用户消息内容，作为重试输入
  const findPrecedingUserContent = (msgKey: string): string | null => {
    const idx = chatMessages.findIndex((m) => String(m.id) === msgKey);
    for (let i = idx - 1; i >= 0; i--) {
      if (chatMessages[i].message.role === 'user') {
        return chatMessages[i].message.content;
      }
    }
    return null;
  };

  const handleRetry = (msgKey: string | number) => {
    if (isRequesting) return;
    const key = String(msgKey);
    const displayContent = findPrecedingUserContent(key);
    if (!displayContent) {
      message.warning('没有找到可重试的原始输入');
      return;
    }
    // 重试复用同一条消息 id，旧的策略结果卡片内容会过期，先删除对应 surface
    const surfaceId = `strategy-${key}`;
    if (registeredSurfacesRef.current.has(surfaceId)) {
      registeredSurfacesRef.current.delete(surfaceId);
      setCommands((prev) => [...prev, { version: 'v0.9', deleteSurface: { surfaceId } }]);
    }
    resetThinking();
    onReload(key, buildRequestParams(displayContent));
  };

  const handleClearMessages = () => {
    // 清空历史前先终止仍在进行的生成流
    stopStream();
    setMessages([]);
    setCommands([]);
    registeredSurfacesRef.current.clear();
    resetThinking();
  };

  // ---------- x-card 命令队列 ----------

  const [commands, setCommands] = useState<XAgentCommand_v0_9[]>([]);
  const registeredSurfacesRef = useRef<Set<string>>(new Set());

  // 成功且带代码的 AI 消息 → 追加卡片三连命令（建 surface / 写数据 / 挂组件树）
  useEffect(() => {
    const next: XAgentCommand_v0_9[] = [];
    chatMessages.forEach((info) => {
      const msg = info.message;
      if (info.status !== 'success' || !msg.code) return;
      const surfaceId = `strategy-${String(info.id)}`;
      if (registeredSurfacesRef.current.has(surfaceId)) return;
      registeredSurfacesRef.current.add(surfaceId);
      next.push(
        { version: 'v0.9', createSurface: { surfaceId, catalogId: STRATEGY_CATALOG_ID } },
        {
          version: 'v0.9',
          updateDataModel: {
            surfaceId,
            path: '/result',
            value: { content: msg.content || '', code: msg.code },
          },
        },
        {
          version: 'v0.9',
          updateComponents: { surfaceId, components: STRATEGY_RESULT_COMPONENTS },
        },
      );
    });
    if (next.length > 0) {
      setCommands((prev) => [...prev, ...next]);
    }
  }, [chatMessages]);

  // 卡片操作回调：采纳把代码交给编辑器，拒绝提示可继续提问
  const handleCardAction = (payload: ActionPayload) => {
    if (payload.name === 'accept') {
      const code = (payload.context as Record<string, { value?: string }> | undefined)?.code?.value;
      if (code) {
        onAcceptCode?.(code);
      } else {
        message.warning('代码内容为空，无法采纳');
      }
    } else if (payload.name === 'reject') {
      onRejectCode?.();
    }
  };

  // ---------- 预加载思维链 ----------

  const preloadThinkingChain = useCallback(async () => {
    try {
      const chainType = 'strategy_generation';
      const cached = thinkingChainCacheRef.current[chainType];
      if (cached) {
        setThinkingSteps(cached.map((s) => ({ ...s })));
        return;
      }
      const result = await aiModelApi.preloadThinkingChain(chainType);
      if (result?.steps?.length) {
        // 兼容不同后端版本的字段命名
        const steps: ThinkingChainStepState[] = result.steps.map((step: PreloadedStep, index: number) => ({
          title: step.title || step.name || step.step_name || `步骤 ${step.step || step.step_number || index + 1}`,
          description: step.description || step.content || step.detail || '',
          status: 'pending' as const,
        }));
        thinkingChainCacheRef.current[chainType] = steps;
        setThinkingSteps(steps.map((s) => ({ ...s })));
      } else {
        console.warn('[AIChatModal] 思维链返回数据无 steps 字段:', result);
      }
    } catch (error) {
      console.error('[AIChatModal] 预加载思维链失败:', error);
    }
  }, []);

  useEffect(() => {
    if (open) preloadThinkingChain();
  }, [open, preloadThinkingChain]);

  // ---------- 渲染辅助 ----------

  // ThoughtChain 步骤状态映射
  const getThinkingItems = () =>
    thinkingSteps.map((step, index) => {
      let status: 'success' | 'loading' | 'error' | undefined;
      if (step.status === 'completed') status = 'success';
      else if (step.status === 'processing') status = 'loading';
      else if (step.status === 'error') status = 'error';
      return { key: index.toString(), title: step.title, description: step.description, status };
    });

  // useXChat 消息 → 气泡列表；主动取消（abort）的气泡不残留
  const bubbleItems = (chatMessages.filter((info) => info.status !== 'abort') as Array<{
    id: string | number;
    status: string;
    message: StrategyChatMessage;
  }>).map((info) => ({
    key: String(info.id),
    role: info.message.role,
    content: info.message.content,
    loading: info.message.role === 'ai' && (info.status === 'loading' || info.status === 'updating'),
    status: info.status as BubbleItemType['status'],
    extraInfo: { code: info.message.code, failed: info.message.failed },
  }));

  // AI 气泡内容：失败态 / 策略结果卡片 / 普通 Markdown
  const renderAiBubble = (data: BubbleItemType) => {
    const ext = data.extraInfo as { code?: string; failed?: boolean } | undefined;
    const content = (data.content as string) || '';
    if (ext?.failed) {
      return (
        <div className="flex items-start gap-2 text-sm text-red-600 dark:text-red-400 py-1">
          <CloseCircleOutlined className="mt-0.5" />
          <span>{content || t('generate_error') || '生成失败，请重试'}</span>
        </div>
      );
    }
    // 成功且带代码：渲染策略结果卡片（卡片本体由 x-card 命令队列驱动）
    if (ext?.code && data.status === 'success') {
      return <XCard.Card id={`strategy-${String(data.key)}`} />;
    }
    if (!content) return null; // 空占位：loading 点由气泡自身渲染
    return <Markdown text={content} />;
  };

  // AI 气泡 footer：复制 + 重试（生成中不显示）
  const renderAiFooter = (data: BubbleItemType) => {
    if (data.status !== 'success' && data.status !== 'error') return null;
    const ext = data.extraInfo as { code?: string; failed?: boolean } | undefined;
    // 有代码复制代码（用户最关心），否则复制说明文本
    const copyText = ext?.code || (data.content as string) || '';
    return (
      <Space size="small" className="mt-1">
        <Button
          type="text"
          size="small"
          icon={<CopyOutlined />}
          onClick={() => {
            navigator.clipboard.writeText(copyText);
            message.success('已复制');
          }}
        >
          {t('copy') || '复制'}
        </Button>
        <Button
          type="text"
          size="small"
          icon={<RedoOutlined />}
          disabled={isRequesting}
          onClick={() => handleRetry(data.key)}
        >
          {t('retry') || '重试'}
        </Button>
      </Space>
    );
  };

  // 气泡角色配置：user 固定样式；ai 用函数式配置以读取每条消息的扩展信息
  const bubbleRoles = {
    user: {
      placement: 'end' as const,
      variant: 'filled' as const,
      className: 'rounded-2xl px-4 py-3',
    },
    ai: (data: BubbleItemType) => ({
      placement: 'start' as const,
      variant: 'filled' as const,
      className: 'rounded-2xl px-4 py-3 shadow-sm',
      contentRender: () => renderAiBubble(data),
      footer: () => renderAiFooter(data),
    }),
  };

  return (
    <Modal
      title={
        <div className="flex items-center justify-between w-full pr-8">
          <span className="font-medium">{title || t('ai_chat') || 'AI 对话'}</span>
          {chatMessages.length > 0 && (
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              onClick={handleClearMessages}
            >
              {t('clear_history') || '清空历史'}
            </Button>
          )}
        </div>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={width}
      centered
      styles={{
        body: { padding: 0, maxHeight: height, overflow: 'hidden' },
      }}
      className={className}
    >
      <div className={`flex flex-col w-full ${bodyClassName}`} style={{ height }}>
        {/* 消息区 */}
        <div className="flex-1 min-h-0 overflow-y-auto bg-[#f5f5f5] dark:bg-[#141414] w-full">
          {chatMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 dark:text-gray-500">
              {welcomeIcon || <ThunderboltOutlined style={{ fontSize: 48 }} className="mb-4" />}
              <p className="text-lg font-medium text-gray-600 dark:text-gray-300">
                {welcomeTitle || t('ai_welcome') || '我是AI助手，有什么可以帮您的？'}
              </p>
              {welcomeDescription && <p className="text-sm mt-2">{welcomeDescription}</p>}
            </div>
          ) : (
            <div className="w-full py-2">
              {thinkingSteps.length > 0 && (
                // 思维链进度面板
                <div className="px-4 py-3 bg-white dark:bg-gray-800 mx-4 mb-2 rounded-xl shadow-sm">
                  <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
                    {thinkingSteps.length > 1 ? (
                      <ThoughtChain items={getThinkingItems()} className="w-full" />
                    ) : (
                      thinkingSteps[0]?.description && (
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {thinkingSteps[0].description}
                        </span>
                      )
                    )}
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2 shrink-0">
                        {isRequesting ? (
                          <>
                            <Spin size="small" />
                            {t('thinking_progress') || '思考进度'}
                          </>
                        ) : (
                          <>
                            <CheckCircleOutlined className="text-green-500" />
                            {t('thinking_complete') || '思考完成'}
                          </>
                        )}
                      </span>
                      <Progress
                        percent={Math.round(thinkingProgress)}
                        size="small"
                        showInfo={false}
                        status={isRequesting ? 'active' : 'success'}
                        className="flex-1 !m-0"
                      />
                      <span
                        className={`text-xs font-medium shrink-0 w-9 text-right ${
                          isRequesting
                            ? 'text-blue-600 dark:text-blue-400'
                            : 'text-green-600 dark:text-green-400'
                        }`}
                      >
                        {Math.round(thinkingProgress)}%
                      </span>
                    </div>
                  </Space>
                </div>
              )}

              {/* 消息列表；Card 元素渲染在 Box 上下文内才能消费命令队列 */}
              <XCard.Box
                commands={commands}
                components={CARD_COMPONENTS}
                onAction={handleCardAction}
              >
                <Bubble.List
                  className="w-full px-4"
                  items={bubbleItems}
                  role={bubbleRoles}
                  autoScroll
                />
              </XCard.Box>
            </div>
          )}
        </div>

        {/* 输入区：模式切换（仅在携带编辑器代码时显示「优化当前代码」）+ Sender；loading 时 Sender 自带停止按钮 */}
        <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-[#141414] p-4">
          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
            {currentCode?.trim() && (
              <Segmented
                size="small"
                value={chatMode}
                onChange={(value) => setChatMode(value as 'generate' | 'optimize')}
                options={[
                  { value: 'generate', label: '生成新策略' },
                  { value: 'optimize', label: '优化当前代码' },
                ]}
              />
            )}
            <Sender
              value={inputValue}
              onChange={setInputValue}
              onSubmit={(msg) => handleSend(msg)}
              onCancel={stopStream}
              loading={isRequesting}
              placeholder={
                chatMode === 'optimize'
                  ? inputPlaceholder
                    ? `${inputPlaceholder}（可留空，直接优化当前代码）`
                    : '可留空，直接优化当前代码；也可补充优化要求...'
                  : inputPlaceholder || t('input_placeholder') || '请输入...'
              }
              submitType={submitType}
              className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#1f1f1f]"
            />
          </Space>
        </div>
      </div>
    </Modal>
  );
};

export default AIChatModal;
