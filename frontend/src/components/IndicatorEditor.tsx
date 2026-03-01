/**
 * 指标编辑器组件
 * 提供Python代码编辑、AI生成、代码验证功能
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

interface IndicatorEditorProps {
  visible: boolean;
  editingIndicator: Indicator | null;
  onClose: () => void;
  onSave: (indicator: Indicator) => void;
}

const { TextArea } = Input;

const IndicatorEditor: React.FC<IndicatorEditorProps> = ({
  visible,
  editingIndicator,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();
  const { createIndicator, updateIndicator, verifyCode, aiGenerateCode } = useIndicators();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode] = useState(defaultIndicatorCode);
  const [aiPrompt, setAiPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    valid: boolean;
    message: string;
    plots_count?: number;
    signals_count?: number;
  } | null>(null);
  const [activeTab, setActiveTab] = useState('code');
  const editorRef = useRef<any>(null);

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
    }
  }, [visible, editingIndicator]);

  // 验证代码
  const handleVerify = async () => {
    if (!code.trim()) {
      message.warning(t('indicator.codeEmpty', '代码不能为空'));
      return;
    }

    setLoading(true);
    try {
      const result = await verifyCode(code);
      setVerifyResult(result);
      if (result.valid) {
        message.success(t('indicator.verifySuccess', '代码验证通过'));
      } else {
        message.error(result.message || t('indicator.verifyFailed', '代码验证失败'));
      }
    } catch (err) {
      message.error(t('indicator.verifyError', '验证出错'));
    } finally {
      setLoading(false);
    }
  };

  // AI生成代码
  const handleAIGenerate = async () => {
    if (!aiPrompt.trim()) {
      message.warning(t('indicator.aiPromptEmpty', '请输入AI提示词'));
      return;
    }

    setAiLoading(true);
    setActiveTab('code');
    
    try {
      let generatedCode = '';
      await aiGenerateCode(
        aiPrompt,
        code,
        (chunk) => {
          generatedCode += chunk;
          setCode(generatedCode);
        },
        () => {
          message.success(t('indicator.aiGenerateSuccess', 'AI生成完成'));
        },
        (error) => {
          message.error(t('indicator.aiGenerateError', 'AI生成失败') + ': ' + error);
        }
      );
    } catch (err) {
      message.error(t('indicator.aiGenerateError', 'AI生成失败'));
    } finally {
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

        {/* 验证结果 */}
        {verifyResult && (
          <Alert
            message={verifyResult.valid ? t('indicator.verifySuccess', '代码验证通过') : t('indicator.verifyFailed', '代码验证失败')}
            description={
              verifyResult.valid ? (
                <Space direction="vertical" size="small">
                  <span>{verifyResult.message}</span>
                  {verifyResult.plots_count !== undefined && (
                    <span>{t('indicator.plotsCount', '绘图数量')}: {verifyResult.plots_count}</span>
                  )}
                  {verifyResult.signals_count !== undefined && (
                    <span>{t('indicator.signalsCount', '信号数量')}: {verifyResult.signals_count}</span>
                  )}
                </Space>
              ) : (
                verifyResult.message
              )
            }
            type={verifyResult.valid ? 'success' : 'error'}
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        {/* 代码编辑/AI生成标签页 */}
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
