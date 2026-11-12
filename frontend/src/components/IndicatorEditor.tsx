/**
 * 指标编辑器组件
 * 提供Python代码编辑、AI生成（带思维链）、代码验证功能
 */

import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  CheckCircleOutlined,
  QuestionCircleOutlined,
  RobotOutlined,
  SaveOutlined,
  PlayCircleOutlined,
  LoadingOutlined,
  ThunderboltOutlined,
  CodeOutlined,
  CheckOutlined,
  CloseOutlined,
  BellOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  Modal,
  Input,
  Button,
  Tabs,
  Alert,
  Spin,
  Space,
  Tooltip,
  App,
  Card,
} from 'antd';
import { useTranslation } from 'react-i18next';
import Editor, { type OnMount } from '@monaco-editor/react';
import { useIndicators, type Indicator, defaultIndicatorCode } from '../hooks/useIndicators';
import { indicatorApi, type ThinkingChainEventData, type IndicatorQualityHint } from '../api';
import { useGuestRestriction } from '../hooks/useGuestRestriction';
import IndicatorAlertTab from './IndicatorAlertTab';
import IndicatorVersionHistory from './IndicatorVersionHistory';
import { QUANT_COLORS } from '@/utils/colors';

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
  const { isGuest } = useGuestRestriction();
  const { message } = App.useApp();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode] = useState(defaultIndicatorCode);
  const [aiPrompt, setAiPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('code');
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  
  // 思维链状态
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [thinkingProgress, setThinkingProgress] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const streamCancelRef = useRef<(() => void) | null>(null);

  // AI生成结果（预览用，采纳后才更新到code）
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);
  const [generatedQuality, setGeneratedQuality] = useState<{ score: number; level: string; hints: IndicatorQualityHint[] } | null>(null);

  // 验证结果
  const [verifyResult, setVerifyResult] = useState<{
    valid: boolean;
    message: string;
    plots_count?: number;
    signals_count?: number;
    quality?: { score: number; level: string; hints: IndicatorQualityHint[] } | null;
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
      // 重置AI生成结果
      setGeneratedCode(null);
      setGeneratedQuality(null);
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
      message.warning(t('indicator.codeEmpty'));
      return;
    }

    setLoading(true);
    try {
      const response = await verifyCode(code);
      // 响应拦截器已解包业务 data，此处直接使用返回值
      const result = response;
      const normalizedResult = {
        ...result,
        valid: result.valid === true,
        quality: result.quality ?? null,
        message: result.message ?? '',
      };
      setVerifyResult(normalizedResult);
      if (normalizedResult.valid) {
        message.success(t('indicator.verifySuccess'));
      } else {
        message.error(normalizedResult.message || t('indicator.verifyFailed'));
      }
    } catch (err) {
      // 显示详细的错误信息
      const errorMessage = (axios.isAxiosError(err) ? err.response?.data?.message : '') || (err instanceof Error ? err.message : '') || t('indicator.verifyError');
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // AI生成代码（带思维链）
  const handleAIGenerate = async () => {
    if (!aiPrompt.trim()) {
      message.warning(t('indicator.aiPromptEmpty'));
      return;
    }

    setAiLoading(true);
    setIsGenerating(true);
    setThinkingProgress(5);
    // 立即初始化思维链步骤，确保UI即刻显示（后续SSE事件会更新标题和状态）
    setThinkingSteps([
      { title: t('ie_think_step_analyze'), description: t('ie_think_step_analyze_desc'), status: 'pending' },
      { title: t('ie_think_step_design'), description: t('ie_think_step_design_desc'), status: 'pending' },
      { title: t('ie_think_step_generate'), description: t('ie_think_step_generate_desc'), status: 'pending' },
      { title: t('ie_think_step_verify'), description: t('ie_think_step_verify_desc'), status: 'pending' },
    ]);

    try {
      // 使用指标专用流式生成API（4步思维链）
      const cancelStream = indicatorApi.generateIndicatorStream(
        {
          prompt: aiPrompt,
          existingCode: code,
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
                  title: i === data.current_step ? data.step_title : t('ie_think_step_fallback', { i }),
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
        (result: { code?: string; raw_content?: string; quality?: { score: number; level: string; hints: IndicatorQualityHint[] } }) => {
          if (result.code) {
            // 存储到预览状态，不直接更新代码编辑器
            setGeneratedCode(result.code);
            setGeneratedQuality(result.quality || null);
            message.success(t('indicator.aiGenerateSuccess'));
          }
          setThinkingProgress(100);
          setThinkingSteps((prev) => 
            prev.map((step) => ({ ...step, status: 'completed' }))
          );
          setIsGenerating(false);
          setAiLoading(false);
        },
        // onError - 错误处理
        (error: Error) => {
          message.error(t('indicator.aiGenerateError') + ': ' + error.message);
          setIsGenerating(false);
          setAiLoading(false);
        }
      );
      
      streamCancelRef.current = cancelStream;
    } catch {
      message.error(t('indicator.aiGenerateError'));
      setIsGenerating(false);
      setAiLoading(false);
    }
  };

  // 采纳AI生成的代码
  const handleAdoptCode = () => {
    if (generatedCode) {
      setCode(generatedCode);
      setGeneratedCode(null);
      setGeneratedQuality(null);
      message.success(t('indicator.adoptSuccess'));
      // 切换到代码编辑标签页
      setActiveTab('code');
    }
  };

  // 拒绝AI生成的代码
  const handleRejectCode = () => {
    setGeneratedCode(null);
    setGeneratedQuality(null);
    message.info(t('indicator.rejectCode'));
  };

  // 保存指标
  const handleSave = async () => {
    if (!name.trim()) {
      message.warning(t('indicator.nameEmpty'));
      return;
    }
    if (!code.trim()) {
      message.warning(t('indicator.codeEmpty'));
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
        message.success(t('indicator.updateSuccess'));
      } else {
        savedIndicator = await createIndicator({
          name,
          description,
          code,
        });
        message.success(t('indicator.createSuccess'));
      }
      
      onSave(savedIndicator);
      onClose();
    } catch {
      message.error(editingIndicator 
        ? t('indicator.updateError')
        : t('indicator.createError')
      );
    } finally {
      setLoading(false);
    }
  };

  // 编辑器挂载处理
  const handleEditorDidMount: OnMount = (editor) => {
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
                  {t('thinking_progress')}
                </>
              ) : (
                <>
                  <CheckCircleOutlined className="text-green-500" />
                  {t('thinking_complete')}
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
          {t('indicator.codeEditor')}
        </span>
      ),
      children: (
        <div className="code-editor-container">
          {/* 验证结果：质量评分 */}
          {verifyResult && (
            <Alert
              type={verifyResult.valid ? 'success' : 'error'}
              showIcon
              style={{ marginBottom: 16 }}
              title={
                <Space>
                  <span>{verifyResult.valid ? t('indicator.verifySuccess') : t('indicator.verifyFailed')}</span>
                  {verifyResult.quality && (
                    <Tooltip
                      title={
                        <div style={{ maxWidth: 320 }}>
                          <div style={{ fontWeight: 600, marginBottom: 6 }}>{t('ie_quality_intro')}</div>
                          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                            <li>{t('ie_quality_rule_dangerous_module')}</li>
                            <li>{t('ie_quality_rule_code_safety')}</li>
                            <li>{t('ie_quality_rule_output_format')}</li>
                            <li>{t('ie_quality_rule_other')}</li>
                          </ul>
                          <div style={{ marginTop: 8, color: QUANT_COLORS.warning }}>
                            {t('ie_quality_scale')}
                          </div>
                          {verifyResult.quality.hints && verifyResult.quality.hints.length > 0 && (
                            <>
                              <div style={{ marginTop: 8, fontWeight: 600 }}>{t('ie_quality_issues_found')}</div>
                              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                                {verifyResult.quality.hints.slice(0, 3).map((hint, i) => (
                                  <li key={i}>
                                    <span style={{ color: hint.severity === 'error' ? QUANT_COLORS.negative : hint.severity === 'warn' ? QUANT_COLORS.warning : QUANT_COLORS.info }}>
                                      [{hint.severity}]
                                    </span> {hint.message || hint.rule}
                                  </li>
                                ))}
                              </ul>
                            </>
                          )}
                        </div>
                      }
                    >
                      <span style={{
                        fontSize: 12,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: verifyResult.quality.score >= 80 ? '#f6ffed' : verifyResult.quality.score >= 60 ? '#fffbe6' : '#fff2f0',
                        color: verifyResult.quality.score >= 80 ? QUANT_COLORS.positive : verifyResult.quality.score >= 60 ? QUANT_COLORS.warning : QUANT_COLORS.negative,
                        cursor: 'help',
                      }}>
                        {t('ie_quality_score', { score: verifyResult.quality.score, level: verifyResult.quality.level })}
                        <QuestionCircleOutlined style={{ marginLeft: 4, fontSize: 11 }} />
                      </span>
                    </Tooltip>
                  )}
                  {verifyResult.plots_count != null && (
                    <span style={{ fontSize: 12, color: '#666' }}>
                      {t('ie_quality_plots_signals', { plots: verifyResult.plots_count, signals: verifyResult.signals_count || 0 })}
                    </span>
                  )}
                </Space>
              }
              description={!verifyResult.valid ? verifyResult.message : undefined}
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
          {t('indicator.aiGenerate')}
        </span>
      ),
      children: (
        <div className="ai-generate-container">
          <Alert
            title={t('indicator.aiTip')}
            description={t('indicator.aiDescription')}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          
          {/* 验证结果：质量评分 */}
          {verifyResult && verifyResult.quality && (
            <Alert
              type={verifyResult.valid ? 'success' : 'error'}
              showIcon
              style={{ marginBottom: 16 }}
              title={
                <Space>
                  <span>{verifyResult.valid ? t('indicator.verifySuccess') : t('indicator.verifyFailed')}</span>
                  <Tooltip
                    title={
                      <div style={{ maxWidth: 320 }}>
                        <div style={{ fontWeight: 600, marginBottom: 6 }}>{t('ie_quality_intro')}</div>
                        <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                          <li>{t('ie_quality_rule_dangerous_module')}</li>
                          <li>{t('ie_quality_rule_code_safety')}</li>
                          <li>{t('ie_quality_rule_output_format')}</li>
                          <li>{t('ie_quality_rule_other')}</li>
                        </ul>
                        <div style={{ marginTop: 8, color: QUANT_COLORS.warning }}>
                          {t('ie_quality_scale')}
                        </div>
                      </div>
                    }
                  >
                    <span style={{
                      fontSize: 12, padding: '2px 8px', borderRadius: 4, cursor: 'help',
                      background: verifyResult.quality.score >= 80 ? '#f6ffed' : verifyResult.quality.score >= 60 ? '#fffbe6' : '#fff2f0',
                      color: verifyResult.quality.score >= 80 ? QUANT_COLORS.positive : verifyResult.quality.score >= 60 ? QUANT_COLORS.warning : QUANT_COLORS.negative,
                    }}>
                      {t('ie_quality_score', { score: verifyResult.quality.score, level: verifyResult.quality.level })}
                      <QuestionCircleOutlined style={{ marginLeft: 4, fontSize: 11 }} />
                    </span>
                  </Tooltip>
                  {verifyResult.plots_count != null && (
                    <span style={{ fontSize: 12, color: '#666' }}>
                      {t('ie_quality_plots_signals', { plots: verifyResult.plots_count, signals: verifyResult.signals_count || 0 })}
                    </span>
                  )}
                </Space>
              }
              description={!verifyResult.valid ? verifyResult.message : undefined}
            />
          )}
          
          {/* 思维链显示 */}
          {renderThinkingChain()}
          
          {/* AI生成结果预览 */}
          {generatedCode && (
            <Card
              title={
                <Space>
                  <CheckCircleOutlined style={{ color: QUANT_COLORS.positive }} />
                  <span>{t('indicator.generatedCodePreview')}</span>
                  {generatedQuality && (
                    <Tooltip
                      title={
                        <div style={{ maxWidth: 320 }}>
                          <div style={{ fontWeight: 600, marginBottom: 6 }}>{t('ie_quality_intro')}</div>
                          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                            <li>{t('ie_quality_rule_dangerous_module')}</li>
                            <li>{t('ie_quality_rule_code_safety')}</li>
                            <li>{t('ie_quality_rule_output_format')}</li>
                            <li>{t('ie_quality_rule_other')}</li>
                          </ul>
                          <div style={{ marginTop: 8, color: QUANT_COLORS.warning }}>
                            {t('ie_quality_scale')}
                          </div>
                          {generatedQuality.hints && generatedQuality.hints.length > 0 && (
                            <>
                              <div style={{ marginTop: 8, fontWeight: 600 }}>{t('ie_quality_issues_found')}</div>
                              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                                {generatedQuality.hints.slice(0, 3).map((hint: IndicatorQualityHint, i: number) => (
                                  <li key={i}>
                                    <span style={{ color: hint.severity === 'error' ? QUANT_COLORS.negative : hint.severity === 'warn' ? QUANT_COLORS.warning : QUANT_COLORS.info }}>
                                      [{hint.severity}]
                                    </span> {hint.message || hint.rule}
                                  </li>
                                ))}
                                {generatedQuality.hints.length > 3 && (
                                  <li style={{ color: '#999' }}>{t('ie_quality_more_issues', { n: generatedQuality.hints.length - 3 })}</li>
                                )}
                              </ul>
                            </>
                          )}
                        </div>
                      }
                    >
                      <span style={{ 
                        fontSize: 12, 
                        padding: '2px 8px', 
                        borderRadius: 4,
                        background: generatedQuality.score >= 80 ? '#f6ffed' : generatedQuality.score >= 60 ? '#fffbe6' : '#fff2f0',
                        color: generatedQuality.score >= 80 ? QUANT_COLORS.positive : generatedQuality.score >= 60 ? QUANT_COLORS.warning : QUANT_COLORS.negative,
                        cursor: 'help',
                      }}>
                        {t('ie_quality_score', { score: generatedQuality.score, level: generatedQuality.level })}
                        <QuestionCircleOutlined style={{ marginLeft: 4, fontSize: 11 }} />
                      </span>
                    </Tooltip>
                  )}
                </Space>
              }
              style={{ marginBottom: 16 }}
              extra={
                <Space>
                  <Button
                    icon={<CloseOutlined />}
                    size="small"
                    onClick={handleRejectCode}
                  >
                    {t('indicator.reject')}
                  </Button>
                  <Button
                    type="primary"
                    icon={<CheckOutlined />}
                    size="small"
                    onClick={handleAdoptCode}
                  >
                    {t('indicator.adopt')}
                  </Button>
                </Space>
              }
            >
              <Editor
                height="300px"
                defaultLanguage="python"
                value={generatedCode}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: 'on',
                  readOnly: true,
                  automaticLayout: true,
                  tabSize: 4,
                  wordWrap: 'on',
                }}
                theme="vs-dark"
              />
            </Card>
          )}
          
          <TextArea
            rows={4}
            placeholder={t('indicator.aiPromptPlaceholder')}
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
            {aiLoading ? t('indicator.aiGenerating') : t('indicator.aiGenerateBtn')}
          </Button>
        </div>
      ),
    },
    // 提醒页签：仅已保存的指标可配置（规则表通过 indicator_id 关联）
    ...(editingIndicator?.id
      ? [
          {
            key: 'alerts',
            label: (
              <span>
                <BellOutlined />
                {t('indicator.alerts')}
              </span>
            ),
            children: <IndicatorAlertTab indicatorId={editingIndicator.id} />,
          },
          // 版本历史页签（原指标实验室迁入）：仅已保存的指标有快照
          {
            key: 'history',
            label: (
              <span>
                <ClockCircleOutlined />
                {t('indicatorVersion.title')}
              </span>
            ),
            children: (
              <IndicatorVersionHistory
                indicatorId={editingIndicator.id}
                onRolledBack={(updated) => {
                  // 回滚已生成新快照并切换服务端当前版本，编辑器同步装载回滚后的代码
                  setName(updated.name);
                  setDescription(updated.description || '');
                  setCode(updated.code || defaultIndicatorCode);
                }}
              />
            ),
          },
        ]
      : []),
  ];

  return (
    <Modal
      title={
        <Space>
          <CodeOutlined />
          {editingIndicator 
            ? t('indicator.editTitle')
            : t('indicator.createTitle')
          }
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={800}
      footer={[
        <Button key="cancel" onClick={onClose}>
          {t('common.cancel')}
        </Button>,
        <Button
          key="verify"
          icon={verifyResult?.valid ? <CheckCircleOutlined /> : <PlayCircleOutlined />}
          onClick={handleVerify}
          loading={loading}
        >
          {t('indicator.verify')}
        </Button>,
        <Tooltip key="save-tooltip" title={isGuest ? t('ie_guest_save_restricted') : ''}>
          <Button
            key="save"
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={loading}
            disabled={isGuest}
          >
            {t('common.save')}
          </Button>
        </Tooltip>,
      ]}
    >
      <Spin spinning={loading}>
        {/* 基本信息 */}
        <div className="indicator-basic-info">
          <div className="form-item">
            <label>{t('indicator.name')}</label>
            <Input
              placeholder={t('indicator.namePlaceholder')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              showCount
            />
          </div>
          <div className="form-item">
            <label>{t('indicator.description')}</label>
            <Input.TextArea
              placeholder={t('indicator.descriptionPlaceholder')}
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
