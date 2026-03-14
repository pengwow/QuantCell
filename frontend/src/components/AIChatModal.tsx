import { useState, useEffect, useRef } from 'react';
import {
  Button,
  Modal,
  message,
  Spin,
} from 'antd';
import {
  DeleteOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ArrowUpOutlined,
  RedoOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Bubble, Sender, ThoughtChain } from '@ant-design/x';
import { aiModelApi } from '../api';

// AI模型配置类型
export interface AIModel {
  id: number;
  provider: string;
  name: string;
  api_host: string;
  models: string[];
  is_default: boolean;
  is_enabled: boolean;
}

// 思维链步骤状态类型
export interface ThinkingChainStepState {
  title: string;
  description: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
}

// 思维链SSE事件数据类型
export interface ThinkingChainEventData {
  current_step: number;
  total_steps: number;
  step_title: string;
  step_description?: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  progress: number;
  message?: string;
}

// AI消息类型
export interface Message {
  id: string;
  type: 'user' | 'ai';
  content: string;
  timestamp: Date;
  status?: 'generating' | 'completed' | 'error';
  code?: string;
}

// 流式生成回调类型（优化版）
// 移除onChunk，改为一次性返回完整结果
export type StreamGenerateCallback = (
  content: string,
  modelId: string | null,
  modelName: string,
  onComplete: (result: { content: string; code?: string }) => void,
  onError: (error: Error) => void,
  onThinkingChain?: (data: ThinkingChainEventData) => void
) => (() => void); // 返回取消函数

// AIChatModal 组件 Props
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
  modelSelectorEnabled?: boolean;
  defaultModelId?: string;
  onModelChange?: (modelId: string, modelName: string) => void;
  // 同步方式（二选一）
  onSendMessage?: (content: string, modelId: string | null, modelName: string) => Promise<{
    content: string;
    code?: string;
  }>;
  // 流式方式（二选一）
  onStreamGenerate?: StreamGenerateCallback;
  onAcceptCode?: (code: string) => void;
  onRejectCode?: () => void;
  renderMessageContent?: (msg: Message) => React.ReactNode;
  renderActions?: (msg: Message) => React.ReactNode;
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
  modelSelectorEnabled = true,
  onModelChange,
  onSendMessage,
  onStreamGenerate,
  onAcceptCode,
  onRejectCode,
  renderMessageContent,
  renderActions,
  className,
  bodyClassName,
}) => {
  const { t } = useTranslation();

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [selectedModelName, setSelectedModelName] = useState<string>('');

  // 流式生成取消函数引用
  const streamCancelRef = useRef<(() => void) | null>(null);

  
  // 思维链状态 - 动态从后端获取
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingChainStepState[]>([]);
  const [, setCurrentStep] = useState(0);
  const [thinkingProgress, setThinkingProgress] = useState(0);
  const [, setIsPreloadingChain] = useState(true);
  
  // 思维链缓存
  const thinkingChainCacheRef = useRef<{
    strategy_generation?: ThinkingChainStepState[];
    indicator_generation?: ThinkingChainStepState[];
  }>({});

  useEffect(() => {
    if (open) {
      // 并行预加载默认模型和思维链配置
      setIsPreloadingChain(true);
      if (modelSelectorEnabled) {
        loadDefaultModel();
      }
      preloadThinkingChain();
    }
  }, [open, modelSelectorEnabled]);

  
  const preloadThinkingChain = async () => {
    try {
      setIsPreloadingChain(true);
      // 检查缓存
      const chainType = 'strategy_generation';
      if (thinkingChainCacheRef.current[chainType]) {
        setThinkingSteps(thinkingChainCacheRef.current[chainType]!);
        setThinkingProgress(0); // 初始化进度为0
        setIsPreloadingChain(false);
        return;
      }

      const result = await aiModelApi.preloadThinkingChain(chainType);
      console.log('预加载思维链配置:', result);
      
      if (result && result.steps) {
        const steps: ThinkingChainStepState[] = result.steps.map((step: any) => ({
          title: step.title,
          description: step.description || '',
          status: 'pending' as const,
        }));
        
        // 缓存预加载的思维链
        thinkingChainCacheRef.current[chainType] = steps;
        setThinkingSteps(steps);
        setThinkingProgress(0); // 初始化进度为0
      }
    } catch (error) {
      console.error('预加载思维链失败:', error);
    } finally {
      setIsPreloadingChain(false);
    }
  };

  const loadDefaultModel = async () => {
    try {
      const result = await aiModelApi.getDefaultProviderModels();
      console.log('getDefaultProviderModels返回结果:', result);
      if (result?.model) {
        const model = result.model;
        console.log('设置的模型ID:', model.id, '类型:', typeof model.id);
        setSelectedModelId(model.id);
        setSelectedModelName(model.name);
        onModelChange?.(model.id, model.name);
      }
    } catch (error) {
      console.error('加载默认模型失败:', error);
    }
  };

  const handleClearMessages = () => {
    setMessages([]);
    setCurrentStep(0);
    setThinkingProgress(0);
    setThinkingSteps([]);
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) {
      message.warning(t('input_empty') || '请输入内容');
      return;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsGenerating(true);
    setCurrentStep(0);
    setThinkingProgress(0);

    // 如果有流式生成回调，使用流式方式（优化版：移除onChunk，一次性返回完整结果）
    if (onStreamGenerate) {
      // 先添加一个生成中的消息占位
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'ai',
        content: '',
        timestamp: new Date(),
        status: 'generating',
      }]);

      const cancelStream = onStreamGenerate(
        userMessage.content,
        selectedModelId || null,
        selectedModelName,
        // onComplete - 生成完成（一次性返回完整结果）
        (result: { content: string; code?: string }) => {
          // 更新消息内容
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg?.type === 'ai') {
              return [
                ...prev.slice(0, -1),
                {
                  ...lastMsg,
                  content: result.content,
                  status: 'completed',
                  code: result.code,
                }
              ];
            }
            return [...prev, {
              id: (Date.now() + 1).toString(),
              type: 'ai',
              content: result.content,
              timestamp: new Date(),
              status: 'completed',
              code: result.code,
            }];
          });
          
          // 更新思维链状态为全部完成
          setThinkingProgress(100);
          setThinkingSteps((prev) => 
            prev.map((step) => ({ ...step, status: 'completed' as const }))
          );
          
          setIsGenerating(false);
        },
        // onError - 生成错误
        (error: Error) => {
          console.error('流式生成失败:', error);
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg?.type === 'ai') {
              return [
                ...prev.slice(0, -1),
                {
                  ...lastMsg,
                  content: t('generate_error') || '生成失败，请重试',
                  status: 'error',
                }
              ];
            }
            return [...prev, {
              id: (Date.now() + 1).toString(),
              type: 'ai',
              content: t('generate_error') || '生成失败，请重试',
              timestamp: new Date(),
              status: 'error',
            }];
          });
          setIsGenerating(false);
        },
        // onThinkingChain - 处理思维链SSE事件（保留流式）
        (data: ThinkingChainEventData) => {
          setCurrentStep(data.current_step);
          setThinkingProgress(data.progress);
          setThinkingSteps((prev) => {
            // 初始化步骤列表（如果是第一次接收）
            if (prev.length === 0 || prev.length !== data.total_steps) {
              const newSteps: ThinkingChainStepState[] = [];
              for (let i = 1; i <= data.total_steps; i++) {
                newSteps.push({
                  title: i === data.current_step ? data.step_title : `步骤 ${i}`,
                  description: i === data.current_step ? (data.step_description || data.message || '') : '',
                  status: i < data.current_step ? 'completed' : i === data.current_step ? data.status : 'pending',
                });
              }
              return newSteps;
            }
            // 更新现有步骤
            return prev.map((step, index) => {
              const stepNumber = index + 1;
              if (stepNumber === data.current_step) {
                return {
                  ...step,
                  title: data.step_title,
                  description: data.step_description || data.message || '',
                  status: data.status,
                };
              } else if (stepNumber < data.current_step) {
                return { ...step, status: 'completed' as const };
              }
              return step;
            });
          });
        }
      );

      // 保存取消函数到 ref，以便在组件卸载时取消
      streamCancelRef.current = cancelStream;
    } else if (onSendMessage) {
      // 使用同步方式（同步方式不支持思维链显示）
      try {
        console.log('发送消息时的selectedModelId:', selectedModelId);
        const result = await onSendMessage(
          userMessage.content,
          selectedModelId || null,
          selectedModelName
        );

        setMessages((prev) =>
          [...prev,
          {
            id: (Date.now() + 1).toString(),
            type: 'ai',
            content: result.content,
            timestamp: new Date(),
            status: 'completed',
            code: result.code,
          }]
        );
      } catch (error) {
        console.error('发送消息失败:', error);
        setMessages((prev) =>
          [...prev,
          {
            id: (Date.now() + 1).toString(),
            type: 'ai',
            content: t('generate_error') || '生成失败，请重试',
            timestamp: new Date(),
            status: 'error',
          }]
        );
      } finally {
        setIsGenerating(false);
      }
    }
  };

  const getMessageContent = (msg: Message) => {
    if (renderMessageContent) {
      return renderMessageContent(msg);
    }

    if (msg.code) {
      return (
        <div className="space-y-4">
          {/* <div className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</div> */}
          <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
            <code>{msg.code}</code>
          </pre>
          {renderActions && renderActions(msg)}
          {msg.type === 'ai' && msg.code && (
            <div className="flex gap-3 pt-2">
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={() => onAcceptCode?.(msg.code!)}
                className="flex-1"
              >
                {t('accept_code') || '采纳代码'}
              </Button>
              <Button
                icon={<CloseCircleOutlined />}
                onClick={onRejectCode}
                className="flex-1"
              >
                {t('reject_code') || '拒绝'}
              </Button>
            </div>
          )}
        </div>
      );
    }

    return <div className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</div>;
  };

  // 更新思维链状态 - 根据后端数据动态渲染
  const getThinkingItems = () => {
    return thinkingSteps.map((step, index) => {
      // 将后端状态映射到ThoughtChain组件的状态
      let status: 'success' | 'loading' | 'error' | undefined;
      if (step.status === 'completed') {
        status = 'success';
      } else if (step.status === 'processing') {
        status = 'loading';
      } else if (step.status === 'error') {
        status = 'error';
      }

      return {
        key: index.toString(),
        title: step.title,
        description: step.description,
        status,
      };
    });
  };

  return (
    <Modal
      title={
        <div className="flex items-center justify-between w-full pr-8">
          <span className="font-medium">{title || t('ai_chat') || 'AI 对话'}</span>
          {messages.length > 0 && (
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
        <div className="flex-1 overflow-y-auto bg-[#f5f5f5] dark:bg-[#141414] w-full">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 dark:text-gray-500">
              {welcomeIcon || <ThunderboltOutlined style={{ fontSize: 48 }} className="mb-4" />}
              <p className="text-lg font-medium text-gray-600 dark:text-gray-300">
                {welcomeTitle || t('ai_welcome') || '我是AI助手，有什么可以帮您的？'}
              </p>
              {welcomeDescription && (
                <p className="text-sm mt-2">{welcomeDescription}</p>
              )}
            </div>
          ) : (
            <div className="w-full">
              {/* 思维链 - 带进度显示和动画效果 */}
              {/* 修改：只要有思维链步骤就显示，不仅限于生成中 */}
              {thinkingSteps.length > 0 && (
                <div className="px-4 py-3 bg-white dark:bg-gray-800 mx-4 my-2 rounded-xl shadow-sm transition-all duration-300 ease-in-out">
                  {/* 思维链步骤 */}
                  <ThoughtChain
                    items={getThinkingItems()}
                    className="w-full"
                  />
                  {/* 进度条 - 放在思维链底部 */}
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                        {isGenerating ? (
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
                      <span className={`text-xs font-medium ${isGenerating ? 'text-blue-600 dark:text-blue-400' : 'text-green-600 dark:text-green-400'}`}>
                        {Math.round(thinkingProgress)}%
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-2 rounded-full transition-all duration-500 ease-out ${isGenerating ? 'bg-blue-500' : 'bg-green-500'}`}
                        style={{ width: `${thinkingProgress}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}
              <Bubble.List
                className="w-full"
                items={messages.map((msg) => ({
                  key: msg.id,
                  role: msg.type,
                  content: getMessageContent(msg),
                  loading: msg.status === 'generating' && msg.type === 'ai',
                }))}
                role={{
                  user: {
                    placement: 'end',
                    variant: 'filled',
                    className: 'rounded-2xl px-4 py-3',
                  },
                  ai: {
                    placement: 'start',
                    variant: 'filled',
                    className: 'rounded-2xl px-4 py-3 shadow-sm',
                    typing: { effect: 'typing', step: 2, interval: 50 },
                    footer: (content: string) => (
                      <div className="flex gap-2 mt-2 ml-0">
                        <Button
                          type="text"
                          size="small"
                          icon={<CopyOutlined />}
                          onClick={() => {
                            navigator.clipboard.writeText(content);
                            message.success('已复制');
                          }}
                        >
                          复制
                        </Button>
                        <Button
                          type="text"
                          size="small"
                          icon={<RedoOutlined />}
                          onClick={() => {
                            handleSendMessage();
                          }}
                        >
                          重试
                        </Button>
                      </div>
                    ),
                  },
                }}
                autoScroll
              />
            </div>
          )}
        </div>

        <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-[#141414] p-4">
          <Sender
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSendMessage}
            loading={isGenerating}
            placeholder={inputPlaceholder || t('input_placeholder') || '请输入...'}
            disabled={isGenerating}
            submitType={submitType}
            prefix={undefined}
            className="rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#1f1f1f]"
            suffix={() => (
              <Button
                type="primary"
                shape="circle"
                icon={<ArrowUpOutlined />}
                onClick={handleSendMessage}
                loading={isGenerating}
                disabled={!inputValue.trim() || isGenerating}
                style={{ 
                  width: 36, 
                  height: 36,
                }}
              />
            )}
          />
        </div>
      </div>
    </Modal>
  );
};

export default AIChatModal;