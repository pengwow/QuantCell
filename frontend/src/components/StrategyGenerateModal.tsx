import { useState, useCallback, useEffect } from 'react';
import {
  Button,
  Modal,
  message,
  Card,
  Space,
  Tag,
  Select,
  Spin,
  Alert,
  Typography,
} from 'antd';
import {
  ThunderboltOutlined,
  CheckCircleOutlined,
  ArrowUpOutlined,
  RedoOutlined,
  CopyOutlined,
  SafetyCertificateOutlined,
  FileTextOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Bubble, Sender, ThoughtChain } from '@ant-design/x';
import { useStrategyGeneration } from '../hooks/useStrategyGeneration';
import type { StrategyTemplate } from '../api';

const { Text } = Typography;

/**
 * 策略生成弹窗组件 Props
 */
export interface StrategyGenerateModalProps {
  open: boolean;
  onClose: () => void;
  onAcceptCode?: (code: string) => void;
  initialRequirement?: string;
}

/**
 * 策略生成弹窗组件
 * 
 * 基于 AIChatModal 封装的策略生成专用组件，集成 useStrategyGeneration Hook，
 * 实现与后端API的真实数据交互。
 */
const StrategyGenerateModal: React.FC<StrategyGenerateModalProps> = ({
  open,
  onClose,
  onAcceptCode,
  initialRequirement = '',
}) => {
  const { t } = useTranslation();

  // 使用策略生成Hook
  const {
    isGenerating,
    thinkingSteps,
    generatedCode,
    generateStrategy,
    validateCode,
    getTemplates,
    cancelGeneration,
    reset,
  } = useStrategyGeneration();

  // 本地状态
  const [inputValue, setInputValue] = useState(initialRequirement);
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const [messages, setMessages] = useState<Array<{
    id: string;
    type: 'user' | 'ai';
    content: string;
    code?: string;
    timestamp: Date;
  }>>([]);

  // 加载模板列表
  useEffect(() => {
    if (open) {
      loadTemplates();
    }
  }, [open]);

  // 初始需求变化时更新输入
  useEffect(() => {
    if (initialRequirement) {
      setInputValue(initialRequirement);
    }
  }, [initialRequirement]);

  // 关闭时重置状态
  useEffect(() => {
    if (!open) {
      reset();
      setInputValue('');
      setMessages([]);
      setValidationResult(null);
      setShowValidation(false);
    }
  }, [open, reset]);

  /**
   * 加载模板列表
   */
  const loadTemplates = async () => {
    try {
      const templateList = await getTemplates();
      // 确保返回的是数组
      if (Array.isArray(templateList)) {
        setTemplates(templateList);
      } else {
        console.warn('模板列表返回格式不正确:', templateList);
        setTemplates([]);
      }
    } catch (err) {
      console.error('加载模板列表失败:', err);
      setTemplates([]);
    }
  };

  /**
   * 处理发送消息
   */
  const handleSendMessage = useCallback(async (value?: string) => {
    const content = value || inputValue;
    if (!content.trim()) {
      message.warning(t('input_empty') || '请输入策略需求');
      return;
    }

    // 添加用户消息
    const userMessage = {
      id: Date.now().toString(),
      type: 'user' as const,
      content: content.trim(),
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    // 调用生成策略
    await generateStrategy(userMessage.content);
  }, [inputValue, generateStrategy, t]);

  /**
   * 处理采纳代码
   */
  const handleAcceptCode = useCallback(() => {
    if (generatedCode && onAcceptCode) {
      onAcceptCode(generatedCode);
      message.success(t('code_accepted') || '代码已采纳');
      onClose();
    }
  }, [generatedCode, onAcceptCode, onClose, t]);

  /**
   * 处理验证代码
   */
  const handleValidateCode = useCallback(async () => {
    if (!generatedCode) {
      message.warning(t('no_code_to_validate') || '没有可验证的代码');
      return;
    }

    setShowValidation(true);
    const result = await validateCode(generatedCode);
    setValidationResult(result);
  }, [generatedCode, validateCode, t]);

  /**
   * 处理重新生成
   */
  const handleRegenerate = useCallback(async () => {
    // 找到最后一条用户消息
    const lastUserMessage = [...messages].reverse().find(m => m.type === 'user');
    if (lastUserMessage) {
      setMessages(prev => prev.filter(m => m.id !== lastUserMessage.id));
      await generateStrategy(lastUserMessage.content);
    }
  }, [messages, generateStrategy]);

  /**
   * 处理选择模板
   */
  const handleSelectTemplate = useCallback((templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (template) {
      setSelectedTemplate(templateId);
      // 构建模板描述作为需求
      const paramDesc = template.parameters
        .map(p => `${p.name}: ${p.default}`)
        .join(', ');
      const requirement = `使用${template.name}模板创建策略，参数：${paramDesc}。${template.description}`;
      setInputValue(requirement);
    }
  }, [templates]);

  /**
   * 渲染思维链
   */
  const renderThinkingChain = () => {
    if (!isGenerating && thinkingSteps.every(s => s.status === 'pending')) {
      return null;
    }

    return (
      <div className="px-4 py-3 bg-white dark:bg-gray-800 mx-4 my-2 rounded-xl shadow-sm">
        <ThoughtChain
          items={thinkingSteps.map((step, index) => ({
            key: index.toString(),
            title: step.title,
            description: step.description,
            status: step.status === 'completed'
              ? 'success'
              : step.status === 'active'
                ? 'loading'
                : undefined,
          }))}
          className="w-full"
        />
      </div>
    );
  };

  /**
   * 渲染代码操作按钮
   */
  const renderCodeActions = () => {
    if (!generatedCode) return null;

    return (
      <div className="flex gap-2 mt-4">
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          onClick={handleAcceptCode}
          className="flex-1"
        >
          {t('accept_code') || '采纳代码'}
        </Button>
        <Button
          icon={<SafetyCertificateOutlined />}
          onClick={handleValidateCode}
          className="flex-1"
        >
          {t('validate_code') || '验证代码'}
        </Button>
        <Button
          icon={<RedoOutlined />}
          onClick={handleRegenerate}
          disabled={isGenerating}
        >
          {t('regenerate') || '重新生成'}
        </Button>
      </div>
    );
  };

  /**
   * 渲染验证结果
   */
  const renderValidationResult = () => {
    if (!showValidation || !validationResult) return null;

    return (
      <Alert
        type={validationResult.valid ? 'success' : 'error'}
        title={validationResult.valid ? '代码验证通过' : '代码验证失败'}
        description={
          <div className="mt-2">
            {validationResult.errors.length > 0 && (
              <div className="mb-2">
                <Text type="danger" strong>错误：</Text>
                <ul className="list-disc list-inside">
                  {validationResult.errors.map((error, idx) => (
                    <li key={idx} className="text-red-500">{error}</li>
                  ))}
                </ul>
              </div>
            )}
            {validationResult.warnings.length > 0 && (
              <div>
                <Text type="warning" strong>警告：</Text>
                <ul className="list-disc list-inside">
                  {validationResult.warnings.map((warning, idx) => (
                    <li key={idx} className="text-yellow-500">{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        }
        className="mt-4"
        closable
        onClose={() => setShowValidation(false)}
      />
    );
  };

  /**
   * 渲染模板选择
   */
  const renderTemplateSelector = () => {
    if (templates.length === 0) return null;

    return (
      <div className="px-4 py-2">
        <Select
          placeholder={t('select_template') || '选择策略模板'}
          style={{ width: '100%' }}
          value={selectedTemplate || undefined}
          onChange={handleSelectTemplate}
          allowClear
        >
          {templates.map(template => (
            <Select.Option key={template.id} value={template.id}>
              <Space>
                <span>{template.name}</span>
                <Tag>{template.category}</Tag>
              </Space>
            </Select.Option>
          ))}
        </Select>
      </div>
    );
  };

  return (
    <Modal
      title={
        <div className="flex justify-between items-center">
          <span className="font-medium">{t('ai_generate_strategy') || 'AI生成策略'}</span>
          {messages.length > 0 && (
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => {
                reset();
                setMessages([]);
              }}
            >
              {t('clear_history') || '清空历史'}
            </Button>
          )}
        </div>
      }
      open={open}
      onCancel={() => {
        if (isGenerating) {
          cancelGeneration();
        }
        onClose();
      }}
      footer={null}
      width={900}
      centered
      styles={{
        body: { padding: 0, maxHeight: '75vh', overflow: 'hidden' },
      }}
    >
      <div className="flex flex-col w-full" style={{ height: '75vh' }}>
        {/* 模板选择 */}
        {renderTemplateSelector()}

        {/* 聊天消息列表 */}
        <div className="flex-1 overflow-y-auto bg-[#f5f5f5] dark:bg-[#141414] w-full">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 dark:text-gray-500">
              <ThunderboltOutlined style={{ fontSize: 48 }} className="mb-4" />
              <p className="text-lg font-medium text-gray-600 dark:text-gray-300">
                {t('ai_strategy_welcome') || '我是AI策略助手，请告诉我您需要什么策略？'}
              </p>
              <p className="text-sm mt-2">
                {t('ai_strategy_example') || '例如：创建一个双均线交叉策略，短期均线10日，长期均线30日'}
              </p>
            </div>
          ) : (
            <div className="w-full">
              {/* 思维链 */}
              {renderThinkingChain()}

              {/* 消息列表 */}
              <Bubble.List
                className="w-full"
                items={messages.map((msg) => ({
                  key: msg.id,
                  role: msg.type,
                  content: msg.content,
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
                  },
                }}
              />

              {/* 生成的代码展示 */}
              {generatedCode && (
                <div className="mx-4 my-4">
                  <Card
                    title={
                      <Space>
                        <FileTextOutlined />
                        <span>{t('generated_code') || '生成的策略代码'}</span>
                      </Space>
                    }
                    extra={
                      <Space>
                        <Button
                          type="text"
                          size="small"
                          icon={<CopyOutlined />}
                          onClick={() => {
                            navigator.clipboard.writeText(generatedCode);
                            message.success(t('copied') || '已复制');
                          }}
                        >
                          {t('copy') || '复制'}
                        </Button>
                      </Space>
                    }
                    className="shadow-sm"
                  >
                    <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                      <code>{generatedCode}</code>
                    </pre>

                    {/* 代码操作按钮 */}
                    {renderCodeActions()}

                    {/* 验证结果 */}
                    {renderValidationResult()}
                  </Card>
                </div>
              )}

              {/* 生成中状态 */}
              {isGenerating && !generatedCode && (
                <div className="mx-4 my-4 p-4 bg-white dark:bg-gray-800 rounded-xl shadow-sm">
                  <Spin tip={t('generating') || '正在生成策略...'} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* 输入区域 */}
        <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-[#141414] p-4">
          <Sender
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSendMessage}
            loading={isGenerating}
            placeholder={t('input_strategy_requirement') || '请输入您的策略需求...'}
            disabled={isGenerating}
            submitType="enter"
            className="rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#1f1f1f]"
            suffix={() => (
              <Button
                type="primary"
                shape="circle"
                icon={<ArrowUpOutlined />}
                onClick={() => handleSendMessage(inputValue)}
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

export default StrategyGenerateModal;
