/**
 * 指标编辑器组件
 * 提供Python代码编辑、AI生成（带思维链）、代码验证功能
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  CheckCircleOutlined,
  RobotOutlined,
  SaveOutlined,
  PlayCircleOutlined,
  LoadingOutlined,
  ThunderboltOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import {
  Modal,
  Input,
  Button,
  message,
  Tabs,
  Alert,
  Spin,
  Space,
} from 'antd';
import { useTranslation } from 'react-i18next';
import Editor from '@monaco-editor/react';
import { useIndicators, type Indicator, defaultIndicatorCode } from '../hooks/useIndicators';
import { aiModelApi, type ThinkingChainEventData } from '../api';

interface IndicatorEditorProps {
  visible: boolean;
  editingIndicator: Indicator | null;
  onClose: () => void;
  onSave: (indicator: Indicator) => void;
}

const { TextArea } = Input;

// 思维链步骤状态
interface ThinkingStep {
  title: string;
  description: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
}

const IndicatorEditor: React.FC<IndicatorEditorProps> = ({
  visible,
  editingIndicator,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();
  const { createIndicator, updateIndicator, verifyCode } = useIndicators();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode] = useState(defaultIndicatorCode);
  const [aiPrompt, setAiPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('code');
  const editorRef = useRef<any>(null);
  
  // 思维链状态
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [thinkingProgress, setThinkingProgress] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const streamCancelRef = useRef<(() => void) | null>(null);

  // 验证结果
  const [verifyResult, setVerifyResult] = useState<{
    valid: boolean;
    message: string;
    plots_count?: number;
    signals_count?: number;
  } | null>(null);

  // 初始化编辑器内容
  useEffect(() => {
    if (visible) {
      if (editingIndicator) {
        setName(editingIndicator.name);
        setDescription(editingIndicator.description || '');
        setCode(editingIndicator.code || defaultIndicatorCode);
      } else {
        setName('');
        setDescription('');
        setCode(defaultIndicatorCode);
      }
      setVerifyResult(null);
      setAiPrompt('');
      setActiveTab('code');
      // 重置思维链状态
      setThinkingSteps([]);
      setThinkingProgress(0);
      setIsGenerating(false);
    }
  }, [visible, editingIndicator]);

  // 组件卸载时取消流式生成
  useEffect(() => {
    return () => {
      if (streamCancelRef.current) {
        streamCancelRef.current();
      }
    };
  }, []);

  // 验证代码
  const handleVerify = async () => {
    if (!code.trim()) {
      message.warning(t('indicator.codeEmpty', '代码不能为空'));
      return;
    }

    setLoading(true);
    try {
      const response = await verifyCode(code);
      // 后端返回标准格式: { code: 0, message: "...", data: {...} }
      const result = response.data || response;
      // 处理后端返回的数据，确保 valid 是布尔值
      const normalizedResult = {
        ...result,
        valid: result.valid === true || result.valid === 'true',
      };
      setVerifyResult(normalizedResult);
      if (normalizedResult.valid) {
        message.success(t('indicator.verifySuccess', '代码验证通过'));
      } else {
        message.error(normalizedResult.message || t('indicator.verifyFailed', '代码验证失败'));
      }
    } catch (err: any) {
      // 显示详细的错误信息
      const errorMessage = err?.response?.data?.message || err?.message || t('indicator.verifyError', '验证出错');
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // AI生成代码（带思维链）
  const handleAIGenerate = async () => {
    if (!aiPrompt.trim()) {
      message.warning(t('indicator.aiPromptEmpty', '请输入AI提示词'));
      return;
    }

    setAiLoading(true);
    setIsGenerating(true);
    setThinkingProgress(0);
    // 注：移除 setActiveTab('code')，保持页面在AI生成tab页不动

    try {
      // 使用优化的流式生成API（带思维链）
      const cancelStream = aiModelApi.generateStrategyStream(
        {
          requirement: aiPrompt,
          prompt_category: 'indicator_generation',
        },
        // onThinkingChain - 思维链进度实时更新
        (data: ThinkingChainEventData) => {
          setThinkingProgress(data.progress);
          setThinkingSteps((prev) => {
            // 初始化步骤列表
            if (prev.length === 0 || prev.length !== data.total_steps) {
              const newSteps: ThinkingStep[] = [];
              for (let i = 1; i <= data.total_steps; i++) {
                newSteps.push({
                  title: i === data.current_step ? data.step_title : `步骤 ${i}`,
                  description: i === data.current_step ? (data.step_description || '') : '',
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
                return { ...step, status: 'completed' };
              }
              return step;
            });
          });
        },
        // onDone - 生成完成
        (result) => {
          if (result.code) {
            setCode(result.code);
            message.success(t('indicator.aiGenerateSuccess', 'AI生成完成'));
          }
          setThinkingProgress(100);
          setThinkingSteps((prev) => 
            prev.map((step) => ({ ...step, status: 'completed' }))
          );
          setIsGenerating(false);
          setAiLoading(false);
        },
        // onError - 错误处理
        (error) => {
          message.error(t('indicator.aiGenerateError', 'AI生成失败') + ': ' + error.message);
          setIsGenerating(false);
          setAiLoading(false);
        }
      );
      
      streamCancelRef.current = cancelStream;
    } catch (err) {
      message.error(t('indicator.aiGenerateError', 'AI生成失败'));
      setIsGenerating(false);
      setAiLoading(false);
    }
  };

  // 保存指标
  const handleSave = async () => {
    if (!name.trim()) {
      message.warning(t('indicator.nameEmpty', '请输入指标名称'));
      return;
    }
    if (!code.trim()) {
      message.warning(t('indicator.codeEmpty', '代码不能为空'));
      return;
    }

    setLoading(true);
    try {
      let savedIndicator: Indicator;
      
      if (editingIndicator) {
        savedIndicator = await updateIndicator(editingIndicator.id, {
          name,
          description,
          code,
        });
        message.success(t('indicator.updateSuccess', '更新成功'));
      } else {
        savedIndicator = await createIndicator({
          name,
          description,
          code,
        });
        message.success(t('indicator.createSuccess', '创建成功'));
      }
      
      onSave(savedIndicator);
      onClose();
    } catch (err) {
      message.error(editingIndicator 
        ? t('indicator.updateError', '更新失败') 
        : t('indicator.createError', '创建失败')
      );
    } finally {
      setLoading(false);
    }
  };

  // 编辑器挂载处理
  const handleEditorDidMount = (editor: any) => {
    editorRef.current = editor;
  };

  // 渲染思维链
  const renderThinkingChain = () => {
    if (thinkingSteps.length === 0) return null;
    
    return (
      <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        {/* 思维链步骤 */}
        <div className="space-y-2 mb-3">
          {thinkingSteps.map((step, index) => (
            <div key={index} className="flex items-start gap-2">
              <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                step.status === 'completed' ? 'bg-green-500 text-white' :
                step.status === 'processing' ? 'bg-blue-500 text-white' :
                'bg-gray-300 text-gray-600'
              }`}>
                {step.status === 'completed' ? (
                  <CheckCircleOutlined style={{ fontSize: 12 }} />
                ) : (
                  index + 1
                )}
              </div>
              <div className="flex-1">
                <div className={`text-sm font-medium ${
                  step.status === 'completed' ? 'text-green-600' :
                  step.status === 'processing' ? 'text-blue-600' :
                  'text-gray-600'
                }`}>
                  {step.title}
                </div>
                {step.description && (
                  <div className="text-xs text-gray-500 mt-0.5">{step.description}</div>
                )}
              </div>
            </div>
          ))}
        </div>
        
        {/* 进度条 - 放在思维链底部 */}
        <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-gray-500 flex items-center gap-2">
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
            <span className={`text-xs font-medium ${isGenerating ? 'text-blue-600' : 'text-green-600'}`}>
              {Math.round(thinkingProgress)}%
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all duration-500 ease-out ${isGenerating ? 'bg-blue-500' : 'bg-green-500'}`}
              style={{ width: `${thinkingProgress}%` }}
            />
          </div>
        </div>
      </div>
    );
  };

  const tabItems = [
    {
      key: 'code',
      label: (
        <span>
          <CodeOutlined />
          {t('indicator.codeEditor', '代码编辑')}
        </span>
      ),
      children: (
        <div className="code-editor-container">
          {/* 验证结果提示 */}
          {verifyResult && (
            <Alert
              message={verifyResult.valid ? t('indicator.verifySuccess', '代码验证通过') : t('indicator.verifyFailed', '代码验证失败')}
              description={!verifyResult.valid ? verifyResult.message : undefined}
              type={verifyResult.valid ? 'success' : 'error'}
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}
          <Editor
            height="400px"
            defaultLanguage="python"
            value={code}
            onChange={(value) => setCode(value || '')}
            onMount={handleEditorDidMount}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              roundedSelection: false,
              scrollBeyondLastLine: false,
              readOnly: false,
              automaticLayout: true,
              tabSize: 4,
              insertSpaces: true,
              wordWrap: 'on',
            }}
            theme="vs-dark"
          />
        </div>
      ),
    },
    {
      key: 'ai',
      label: (
        <span>
          <RobotOutlined />
          {t('indicator.aiGenerate', 'AI生成')}
        </span>
      ),
      children: (
        <div className="ai-generate-container">
          <Alert
            message={t('indicator.aiTip', '使用AI智能生成指标代码')}
            description={t('indicator.aiDescription', '描述您想要的指标功能，AI将为您生成相应的Python代码。例如："创建一个基于RSI超买卖信号的双线指标"')}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          
          {/* 思维链显示 */}
          {renderThinkingChain()}
          
          <TextArea
            rows={4}
            placeholder={t('indicator.aiPromptPlaceholder', '请输入指标描述，例如：创建一个基于5日和20日均线交叉产生买卖信号的指标')}
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            disabled={aiLoading}
          />
          <Button
            type="primary"
            icon={aiLoading ? <LoadingOutlined /> : <ThunderboltOutlined />}
            onClick={handleAIGenerate}
            loading={aiLoading}
            disabled={!aiPrompt.trim()}
            style={{ marginTop: 16 }}
            block
          >
            {aiLoading ? t('indicator.aiGenerating', '生成中...') : t('indicator.aiGenerateBtn', 'AI生成代码')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <CodeOutlined />
          {editingIndicator 
            ? t('indicator.editTitle', '编辑指标') 
            : t('indicator.createTitle', '创建指标')
          }
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={800}
      footer={[
        <Button key="cancel" onClick={onClose}>
          {t('common.cancel', '取消')}
        </Button>,
        <Button
          key="verify"
          icon={verifyResult?.valid ? <CheckCircleOutlined /> : <PlayCircleOutlined />}
          onClick={handleVerify}
          loading={loading}
        >
          {t('indicator.verify', '验证代码')}
        </Button>,
        <Button
          key="save"
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={loading}
        >
          {t('common.save', '保存')}
        </Button>,
      ]}
    >
      <Spin spinning={loading}>
        {/* 基本信息 */}
        <div className="indicator-basic-info">
          <div className="form-item">
            <label>{t('indicator.name', '指标名称')}</label>
            <Input
              placeholder={t('indicator.namePlaceholder', '请输入指标名称')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              showCount
            />
          </div>
          <div className="form-item">
            <label>{t('indicator.description', '指标描述')}</label>
            <Input.TextArea
              placeholder={t('indicator.descriptionPlaceholder', '请输入指标描述（可选）')}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              maxLength={500}
              showCount
            />
          </div>
        </div>
        
        {/* 标签页 */}
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
        />
      </Spin>
    </Modal>
  );
};

export default IndicatorEditor;
