import { useState, useEffect } from 'react';
import {
  Button,
  Modal,
  message,
} from 'antd';
import {
  DeleteOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ArrowUpOutlined,
  RedoOutlined,
  CopyOutlined,
  UserOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Bubble, Sender, ThoughtChain, CodeHighlighter } from '@ant-design/x';
import { Avatar } from 'antd';
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

// AI消息类型
export interface Message {
  id: string;
  type: 'user' | 'ai';
  content: string;
  timestamp: Date;
  status?: 'generating' | 'completed' | 'error';
  code?: string;
}

// 思考步骤类型
export interface ThinkingStep {
  label: string;
  status: 'pending' | 'active' | 'completed';
}

// AIChatModal 组件 Props
export interface AIChatModalProps {
  // 基础配置
  open: boolean;
  onClose: () => void;
  title?: string;
  width?: number;
  height?: string | number;

  // 欢迎信息配置
  welcomeIcon?: React.ReactNode;
  welcomeTitle?: string;
  welcomeDescription?: string;

  // 输入配置
  inputPlaceholder?: string;
  submitType?: 'enter' | 'shiftEnter';

  // 模型配置
  modelSelectorEnabled?: boolean;
  defaultModelId?: number;
  onModelChange?: (modelId: number, modelName: string) => void;

  // 消息处理
  onSendMessage: (content: string, modelId: number | null, modelName: string) => Promise<{
    content: string;
    code?: string;
  }>;

  // 代码操作
  onAcceptCode?: (code: string) => void;
  onRejectCode?: () => void;

  // 思考步骤配置
  thinkingSteps?: string[];
  showThinkingSteps?: boolean;

  // 自定义渲染
  renderMessageContent?: (msg: Message) => React.ReactNode;
  renderActions?: (msg: Message) => React.ReactNode;

  // 样式配置
  className?: string;
  bodyClassName?: string;
}

/**
 * AI 聊天弹窗组件
 * 通用的 AI 对话弹窗，支持模型选择、消息列表、代码展示等功能
 */
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
  onAcceptCode,
  onRejectCode,
  thinkingSteps: customThinkingSteps,
  showThinkingSteps = true,
  renderMessageContent,
  renderActions,
  className,
  bodyClassName,
}) => {
  const { t } = useTranslation();

  // 消息列表
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentThinkingStep, setCurrentThinkingStep] = useState(0);

  // 模型配置（已隐藏模型选择器，简化处理）
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [selectedModelName, setSelectedModelName] = useState<string>('');

  // 默认思考步骤
  const defaultThinkingSteps = [
    t('thinking_analyze') || '分析需求...',
    t('thinking_design') || '设计策略结构...',
    t('thinking_generate') || '生成代码...',
    t('thinking_optimize') || '优化代码...',
  ];
  const thinkingSteps = customThinkingSteps || defaultThinkingSteps;

  // 加载默认模型名称
  useEffect(() => {
    if (open && modelSelectorEnabled) {
      loadDefaultModel();
    }
  }, [open, modelSelectorEnabled]);

  // 加载默认模型名称
  const loadDefaultModel = async () => {
    try {
      // 使用新接口获取默认提供商的模型列表
      const result = await aiModelApi.getDefaultProviderModels();
      // API 拦截器已经处理了 code，直接返回 data
      if (result?.models && result.models.length > 0) {
        // 使用第一个启用的模型
        const firstModel = result.models[0];
        setSelectedModelId(firstModel.id);
        setSelectedModelName(firstModel.name);
        onModelChange?.(Number(firstModel.id), firstModel.name);
      }
    } catch (error) {
      console.error('加载默认模型失败:', error);
    }
  };

  // 清空消息
  const handleClearMessages = () => {
    setMessages([]);
    setCurrentThinkingStep(0);
  };

  // 发送消息
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
    setCurrentThinkingStep(0);

    // 创建AI消息占位符
    const aiMessageId = (Date.now() + 1).toString();
    const aiMessage: Message = {
      id: aiMessageId,
      type: 'ai',
      content: '',
      timestamp: new Date(),
      status: 'generating',
    };
    setMessages((prev) => [...prev, aiMessage]);

    try {
      // 模拟思考过程
      if (showThinkingSteps) {
        for (let i = 0; i < thinkingSteps.length; i++) {
          setCurrentThinkingStep(i);
          await new Promise((resolve) => setTimeout(resolve, 800));
        }
      }

      // 调用外部处理函数
      const result = await onSendMessage(
        userMessage.content,
        Number(selectedModelId),
        selectedModelName
      );

      // 更新AI消息
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? {
                ...msg,
                content: result.content,
                status: 'completed',
                code: result.code,
              }
            : msg
        )
      );
    } catch (error: any) {
      const errorMsg = error?.message || t('generate_failed') || '生成失败';
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? { ...msg, content: errorMsg, status: 'error' }
            : msg
        )
      );
      message.error(errorMsg);
    } finally {
      setIsGenerating(false);
      setCurrentThinkingStep(0);
    }
  };

  // 渲染默认的 AI 消息内容
  const renderDefaultMessageContent = (msg: Message) => {
    if (msg.type === 'user') {
      return msg.content;
    }

    return (
      <div>
        {/* 思考过程 - 使用 Ant Design X ThoughtChain 组件 */}
        {showThinkingSteps && msg.status === 'generating' && (
          <div className="mb-3">
            <ThoughtChain
              items={thinkingSteps.map((step, stepIndex) => ({
                key: String(stepIndex),
                title: step,
                status:
                  stepIndex < currentThinkingStep
                    ? 'success'
                    : stepIndex === currentThinkingStep
                    ? 'loading'
                    : undefined,
                description:
                  stepIndex === currentThinkingStep
                    ? t('thinking_in_progress') || '进行中...'
                    : stepIndex < currentThinkingStep
                    ? t('thinking_completed') || '已完成'
                    : t('thinking_pending') || '等待中',
              }))}
            />
          </div>
        )}

        {/* AI回复内容 */}
        <div className="mb-3">
          <p className="text-gray-700 dark:text-gray-300 mb-2">{msg.content}</p>
        </div>

        {/* 生成的代码 - 使用 CodeHighlighter */}
        {msg.code && (
          <div className="mb-3">
            <CodeHighlighter
              lang="python"
              header={t('generated_code') || '生成的代码'}
              className="rounded-lg overflow-hidden"
            >
              {msg.code}
            </CodeHighlighter>
          </div>
        )}

        {/* 默认的采纳/拒绝按钮 */}
        {msg.status === 'completed' && msg.code && !renderActions && (
          <div className="flex gap-2 mt-3 justify-end">
            <Button
              size="small"
              icon={<CloseCircleOutlined />}
              onClick={() => {
                onRejectCode?.();
                message.info(t('rejected') || '已拒绝');
              }}
            >
              {t('reject') || '拒绝'}
            </Button>
            <Button
              type="primary"
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => {
                if (msg.code) {
                  onAcceptCode?.(msg.code);
                  message.success(t('accepted') || '已采纳');
                  onClose();
                }
              }}
            >
              {t('accept') || '采纳'}
            </Button>
          </div>
        )}

        {/* 自定义操作按钮 */}
        {renderActions && renderActions(msg)}
      </div>
    );
  };

  // 渲染消息内容
  const getMessageContent = (msg: Message) => {
    if (renderMessageContent) {
      return renderMessageContent(msg);
    }
    return renderDefaultMessageContent(msg);
  };

  return (
    <Modal
      title={
        <div className="flex justify-between items-center pr-8">
          <span className="font-medium">{title || t('ai_chat') || 'AI 对话'}</span>
          {messages.length > 0 && (
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              onClick={handleClearMessages}
              className="ml-4"
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
      <div className={`flex flex-col ${bodyClassName}`} style={{ height }}>
        {/* 聊天消息列表 */}
        <div className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900">
          {messages.length === 0 ? (
            <div className="text-center text-gray-400 py-10">
              {welcomeIcon || <ThunderboltOutlined style={{ fontSize: 48 }} className="mb-4" />}
              <p>{welcomeTitle || t('ai_welcome') || '我是AI助手，有什么可以帮您的？'}</p>
              {welcomeDescription && (
                <p className="text-sm mt-2">{welcomeDescription}</p>
              )}
            </div>
          ) : (
            <Bubble.List
              items={messages.map((msg) => ({
                key: msg.id,
                role: msg.type,
                content: getMessageContent(msg),
                loading: msg.status === 'generating' && msg.type === 'ai',
              }))}
              role={{
                user: {
                  placement: 'end',
                  variant: 'shadow',
                  shape: 'corner',
                  className: 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100',
                  avatar: <Avatar icon={<UserOutlined />} style={{ background: '#1677ff' }} />,
                },
                ai: {
                  placement: 'start',
                  variant: 'shadow',
                  shape: 'corner',
                  className: 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100',
                  avatar: <Avatar icon={<RobotOutlined />} style={{ background: '#52c41a' }} />,
                  typing: { effect: 'typing', step: 2, interval: 50 },
                  footer: (content: string) => (
                    <div className="flex gap-2 mt-2">
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
          )}
        </div>

        {/* 输入区域 */}
        <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <Sender
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSendMessage}
            loading={isGenerating}
            placeholder={inputPlaceholder || t('input_placeholder') || '请输入...'}
            disabled={isGenerating}
            submitType={submitType}
            // 自定义前缀 - 模型选择器（已隐藏）
            prefix={undefined}
            // 自定义后缀 - 发送按钮
            suffix={() => (
              <Button
                type="primary"
                shape="circle"
                icon={<ArrowUpOutlined />}
                onClick={handleSendMessage}
                loading={isGenerating}
                disabled={!inputValue.trim() || isGenerating}
                style={{ width: 36, height: 36 }}
              />
            )}
          />
        </div>
      </div>
    </Modal>
  );
};

export default AIChatModal;
