/**
 * 策略编辑器组件
 * 功能：提供策略代码编辑、执行和结果预览功能
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  message,
  Spin,
  Tabs,
  Modal,
  Input,
  Descriptions,
} from 'antd';
import {
  PlayCircleOutlined,
  SaveOutlined,
  CodeOutlined,
  EyeOutlined,
  ReloadOutlined,
  BackwardOutlined,
  RobotOutlined,
} from '@ant-design/icons';

import MonacoEditor from '@monaco-editor/react';
import { useTranslation } from 'react-i18next';
import { strategyApi } from '../api';

interface Strategy {
  name: string;
  file_name: string;
  file_path: string;
  description: string;
  version: string;
  params: Array<{
    name: string;
    type: string;
    default: any;
    description: string;
    required: boolean;
  }>;
  created_at: string;
  updated_at: string;
  code: string;
}

const StrategyEditor: React.FC = () => {
  // const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [editorLoading, setEditorLoading] = useState<boolean>(false);
  const [code, setCode] = useState<string>('');
  const [editor, setEditor] = useState<any>(null);
  const [scrollListener, setScrollListener] = useState<(() => void) | null>(null);

  const [aiModalVisible, setAiModalVisible] = useState<boolean>(false);
  const [aiInput, setAiInput] = useState<string>('');
  const [aiLoading, setAiLoading] = useState<boolean>(false);
  const [aiHistory, setAiHistory] = useState<Array<{ type: 'user' | 'ai'; content: string }>>([]);
  
  // 策略名称编辑状态
  const [isEditingName, setIsEditingName] = useState<boolean>(false);
  const [tempName, setTempName] = useState<string>('');
  
  // 策略版本编辑状态
  const [isEditingVersion, setIsEditingVersion] = useState<boolean>(false);
  const [tempVersion, setTempVersion] = useState<string>('');
  
  // 策略描述编辑状态
  const [isEditingDescription, setIsEditingDescription] = useState<boolean>(false);
  const [tempDescription, setTempDescription] = useState<string>('');
  
  const navigate = useNavigate();
  const params = useParams<{ strategyName?: string }>();
  const { t } = useTranslation();

  // 开始编辑策略名称
  const handleStartEditName = () => {
    if (selectedStrategy) {
      setTempName(selectedStrategy.name);
      setIsEditingName(true);
    }
  };

  // 保存策略名称
  const handleSaveName = () => {
    if (selectedStrategy && tempName.trim()) {
      setSelectedStrategy(prev => prev ? { ...prev, name: tempName.trim() } : null);
      setIsEditingName(false);
    }
  };

  // 处理临时名称变化
  const handleTempNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempName(e.target.value);
  };

  // 开始编辑策略版本
  const handleStartEditVersion = () => {
    if (selectedStrategy) {
      setTempVersion(selectedStrategy.version);
      setIsEditingVersion(true);
    }
  };

  // 保存策略版本
  const handleSaveVersion = () => {
    if (selectedStrategy && tempVersion.trim()) {
      setSelectedStrategy(prev => prev ? { ...prev, version: tempVersion.trim() } : null);
      setIsEditingVersion(false);
    }
  };

  // 处理临时版本变化
  const handleTempVersionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempVersion(e.target.value);
  };

  // 开始编辑策略描述
  const handleStartEditDescription = () => {
    if (selectedStrategy) {
      setTempDescription(selectedStrategy.description);
      setIsEditingDescription(true);
    }
  };

  // 保存策略描述
  const handleSaveDescription = () => {
    if (selectedStrategy) {
      setSelectedStrategy(prev => prev ? { ...prev, description: tempDescription } : null);
      setIsEditingDescription(false);
    }
  };

  // 处理临时描述变化
  const handleTempDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTempDescription(e.target.value);
  };

  // 处理编辑器滚动事件
  const handleEditorScroll = () => {
    if (!editor) return;
    
    const scrollTop = editor.getScrollTop();
    const scrollHeight = editor.getScrollHeight();
    const clientHeight = editor.getLayoutInfo().contentHeight;
    
    // 获取编辑器元素在页面中的位置
    const editorElement = document.querySelector('.monaco-editor') as HTMLElement;
    if (!editorElement) return;
    
    const rect = editorElement.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const pageScrollTop = window.pageYOffset || document.documentElement.scrollTop;
    
    // 1. 编辑器滚动到顶部时，页面滚动到顶部
    if (scrollTop <= 0 && pageScrollTop > 0) {
      window.scrollTo({ top: pageScrollTop - 50, behavior: 'smooth' });
    }
    
    // 2. 编辑器滚动到底部时，页面滚动到底部
    if (scrollTop + clientHeight >= scrollHeight - 10) {
      window.scrollTo({ top: pageScrollTop + 50, behavior: 'smooth' });
    }
    
    // 3. 编辑器在可视区域外时，自动滚动页面使其可见
    if (rect.top < 100) {
      // 编辑器顶部在可视区域上方，向上滚动页面
      window.scrollTo({ top: pageScrollTop - (100 - rect.top), behavior: 'smooth' });
    } else if (rect.bottom > viewportHeight - 100) {
      // 编辑器底部在可视区域下方，向下滚动页面
      window.scrollTo({ top: pageScrollTop + (rect.bottom - (viewportHeight - 100)), behavior: 'smooth' });
    }
  };

  // 清理事件监听器
  useEffect(() => {
    return () => {
      // 组件卸载时清理编辑器滚动事件监听器
      if (editor && scrollListener) {
        // MonacoEditor 的事件监听器移除方式取决于具体实现
        // 由于 MonacoEditor 实例的 onDidScrollChange 方法返回一个可销毁对象，我们需要保存这个对象来销毁监听器
        // 但当前我们没有保存销毁函数，所以这里需要修改 onMount 回调来保存销毁函数
      }
    };
  }, [editor, scrollListener]);

  // 组件挂载时，如果有策略名称参数，加载对应策略
  useEffect(() => {
    if (params.strategyName) {
      loadStrategyByName(params.strategyName);
    } else {
      // 创建新策略
      handleCreateStrategy();
    }
  }, [params.strategyName]);

  // 根据名称加载策略
  const loadStrategyByName = async (strategyName: string) => {
    try {
      setEditorLoading(true);
      // 调用实际API获取策略详情
      const response = await strategyApi.getStrategyDetail(strategyName);
      const strategy = response;
      setSelectedStrategy(strategy);
      setCode(strategy.code);
    } catch (error) {
      console.error('加载策略失败:', error);
      message.error('加载策略失败');
    } finally {
      setEditorLoading(false);
    }
  };
  
  // 返回策略管理页面
  const handleBack = () => {
    navigate('/strategy-management');
  };

  // 创建新策略
  const handleCreateStrategy = () => {
    const newStrategy: Strategy = {
      name: 'new_strategy',
      file_name: 'new_strategy.py',
      file_path: '',
      description: '新策略',
      version: '1.0.0',
      params: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code: '# 新策略模板\nfrom strategy import StrategyBase\n\nclass NewStrategy(StrategyBase):\n    \"\""\n    新策略模板\n    \"\"\"\n    # 策略参数\n    param1 = 10\n    param2 = 20.0\n    param3 = \"test\"\n    \n    def on_initialize(self):\n        \"\""初始化策略\"\""\n        pass\n    \n    def on_update_indicators(self, data):\n        \"\""更新技术指标\"\""\n        pass\n    \n    def on_generate_signals(self, data):\n        \"\""生成交易信号\"\""\n        return []\n    \n    def on_execute_orders(self, signals):\n        \"\""执行订单\"\""\n        return []\n    \n    def on_risk_control(self, signals):\n        \"\""风险控制\"\""\n        return signals\n    \n    def on_update_performance(self):\n        \"\""更新绩效指标\"\""\n        pass\n    \n    def on_evaluate_performance(self):\n        \"\""绩效评估\"\""\n        return {}\n    \n    def on_stop(self):\n        \"\""停止策略\"\""\n        pass\n',
    };
    
    setSelectedStrategy(newStrategy);
    setCode(newStrategy.code);
  };

  // 保存策略
  const handleSaveStrategy = async () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
      return;
    }
    
    Modal.confirm({
      title: '确认保存策略',
      content: '您确定要保存当前策略吗？',
      okText: '保存',
      okType: 'primary',
      cancelText: '取消',
      onOk: async () => {
        try {
          setLoading(true);
          
          // 调用保存策略的API
          await strategyApi.uploadStrategyFile({
            strategy_name: selectedStrategy.name,
            file_content: code,
            version: selectedStrategy.version,
            description: selectedStrategy.description
          });
          
          message.success('策略保存成功');
        } catch (error) {
          console.error('保存策略失败:', error);
          message.error('保存策略失败');
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // 重置策略代码
  const handleResetCode = () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
      return;
    }
    
    Modal.confirm({
      title: '确认重置策略代码',
      content: '您确定要重置当前策略代码吗？所有未保存的更改将丢失。',
      okText: '重置',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => {
        if (selectedStrategy) {
          setCode(selectedStrategy.code);
          message.success('策略代码已重置');
        }
      },
    });
  };

  // 回测策略
  const handleBacktestStrategy = () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
      return;
    }
    
    navigate('/backtest', { state: { strategy: selectedStrategy, showConfig: true } });
  };


  // 打开AI优化模态框
  const handleOpenAIModal = () => {
    setAiModalVisible(true);
  };
  
  // 关闭AI优化模态框
  const handleCloseAIModal = () => {
    setAiModalVisible(false);
  };
  
  // 发送AI请求
  const handleSendAIRequest = async () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
      return;
    }
    
    try {
      setAiLoading(true);
      
      // 添加用户输入到历史记录
      const newHistory = [...aiHistory, { type: 'user' as const, content: aiInput }];
      setAiHistory(newHistory);
      setAiInput('');
      
      // 模拟AI回复（使用mock数据）
      setTimeout(() => {
        // 模拟AI回复
        const aiResponse = '这是AI优化后的策略代码...\n' + code;
        
        // 更新历史记录
        const updatedHistory = [...newHistory, { type: 'ai' as const, content: aiResponse }];
        setAiHistory(updatedHistory);
        
        // 更新编辑器内容
        setCode(aiResponse);
        
        setAiLoading(false);
        message.success('AI优化完成');
      }, 2000);
    } catch (error) {
      console.error('AI优化失败:', error);
      message.error('AI优化失败');
      setAiLoading(false);
    }
  };
  
  // 清空AI对话历史
  const handleClearAIHistory = () => {
    setAiHistory([]);
  };



  // 编辑器选项
  const editorOptions = {
    language: 'python',
    theme: 'vs-dark',
    fontSize: 14,
    minimap: { enabled: true },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    insertSpaces: true,
    formatOnType: true,
    formatOnPaste: true,
    lineNumbers: true,
    scrollbar: { vertical: 'auto', horizontal: 'auto' },
    wordWrap: 'on',
  };

  return (
    <div style={{ padding: '20px' }}>
      {/* 页面头部 */}
      <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Button
            type="default"
            icon={<BackwardOutlined />}
            onClick={handleBack}
            style={{ marginRight: '16px' }}
          >
            {t('back')}
          </Button>
          {isEditingName ? (
            <div style={{ position: 'relative' }}>
              <Input
                type="text"
                value={tempName}
                onChange={handleTempNameChange}
                onKeyPress={(e) => e.key === 'Enter' && handleSaveName()}
                onBlur={handleSaveName}
                autoFocus
                style={{ 
                  fontSize: '20px', 
                  fontWeight: 500, 
                  border: '1px solid #1890ff', 
                  borderRadius: '4px',
                  width: '300px',
                  margin: 0
                }}
              />
            </div>
          ) : (
            <h2 
              style={{ margin: 0, fontSize: '20px', fontWeight: 500, cursor: 'pointer' }}
              onClick={handleStartEditName}
            >
              {selectedStrategy ? selectedStrategy.name : t('strategy_editor')}
            </h2>
          )}
        </div>
        
        {/* 操作按钮组 */}
        <Space>
          <Button
            type="default"
            icon={<ReloadOutlined />}
            onClick={handleResetCode}
            loading={loading}
          >
            {t('reset')}
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleBacktestStrategy}
            loading={loading}
          >
            {t('backtest')}
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSaveStrategy}
            loading={loading}
          >
            {t('save')}
          </Button>
          <Button
            type="default"
            icon={<RobotOutlined />}
            onClick={handleOpenAIModal}
            loading={aiLoading}
            disabled={true}
          >
            {t('ai_optimize')}
          </Button>
        </Space>
      </div>
      
      {/* 主内容区域 */}
      <Card>
        <Spin spinning={editorLoading} tip="加载中...">
          <Tabs 
            defaultActiveKey="editor" 
            tabBarStyle={{ marginBottom: 0 }}
            items={[
              {
                key: 'editor',
                label: <><CodeOutlined /> {t('editor')}</>,
                children: (
                  <div style={{ width: '100%', minHeight: '600px' }}>
                    <MonacoEditor
                      height="600px"
                      language="python"
                      value={code}
                      onChange={(value) => setCode(value || '')}
                      options={editorOptions as any}
                      onMount={(editorInstance: any) => {
                        setEditor(editorInstance);
                        // 监听编辑器滚动事件，保存销毁函数
                        const disposable = editorInstance.onDidScrollChange(() => {
                          handleEditorScroll();
                        });
                        // 保存销毁函数，用于组件卸载时清理
                        setScrollListener(() => disposable.dispose());
                      }}
                    />
                  </div>
                )
              },
              {
                key: 'preview',
                label: <><EyeOutlined /> {t('preview')}</>,
                children: (
                  <div style={{ padding: '20px' }}>
                    <h3>{t('strategy_information')}</h3>
                    <Descriptions bordered column={1} style={{ marginBottom: '20px' }}>
                      <Descriptions.Item label={t('name')}>
                        {isEditingName ? (
                          <Space>
                            <Input
                              value={tempName}
                              onChange={handleTempNameChange}
                              onPressEnter={handleSaveName}
                              onBlur={handleSaveName}
                              autoFocus
                            />
                          </Space>
                        ) : (
                          <span onClick={handleStartEditName} style={{ cursor: 'pointer' }}>
                            {selectedStrategy?.name || ''}
                          </span>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('version')}>
                        {isEditingVersion ? (
                          <Space>
                            <Input
                              value={tempVersion}
                              onChange={handleTempVersionChange}
                              onPressEnter={handleSaveVersion}
                              onBlur={handleSaveVersion}
                              autoFocus
                            />
                          </Space>
                        ) : (
                          <span onClick={handleStartEditVersion} style={{ cursor: 'pointer' }}>
                            {selectedStrategy?.version || ''}
                          </span>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('description')}>
                        {isEditingDescription ? (
                          <Space>
                            <Input.TextArea
                              value={tempDescription}
                              onChange={handleTempDescriptionChange}
                              onPressEnter={handleSaveDescription}
                              onBlur={handleSaveDescription}
                              autoFocus
                              rows={3}
                            />
                          </Space>
                        ) : (
                          <span onClick={handleStartEditDescription} style={{ cursor: 'pointer' }}>
                            {selectedStrategy?.description || t('no_description')}
                          </span>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('created_at')}>{selectedStrategy ? new Date(selectedStrategy.created_at).toLocaleString() : ''}</Descriptions.Item>
                      <Descriptions.Item label={t('updated_at')}>{selectedStrategy ? new Date(selectedStrategy.updated_at).toLocaleString() : ''}</Descriptions.Item>
                    </Descriptions>
                    
                    <h3 style={{ marginTop: '20px' }}>{t('parameter_list')}</h3>
                    {selectedStrategy?.params && selectedStrategy.params.length > 0 ? (
                      <Descriptions bordered column={1}>
                        {selectedStrategy.params.map((param, index) => (
                          <Descriptions.Item key={index} label={param.name}>
                            <div>
                              <p style={{ margin: '0 0 8px 0' }}>{param.description || t('no_description')}</p>
                              <small>{t('type')}: {param.type}, {t('default_value')}: {JSON.stringify(param.default)}</small>
                            </div>
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    ) : (
                      <div style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
                        {t('no_parameters')}
                      </div>
                    )}
                  </div>
                )
              }
            ]}
          />
        </Spin>
      </Card>

      {/* AI对话模态框 */}
      <Modal
        title={t('ai_optimize')}
        open={aiModalVisible}
        onCancel={handleCloseAIModal}
        footer={null}
        width={800}
        centered
      >
        <div style={{ height: '500px', display: 'flex', flexDirection: 'column' }}>
          {/* 对话历史 */}
          <div style={{ flex: 1, overflowY: 'auto', marginBottom: '16px', padding: '16px', background: '#f5f5f5', borderRadius: '4px' }}>
            {aiHistory.length > 0 ? (
              aiHistory.map((item, index) => (
                <div key={index} style={{ marginBottom: '16px', display: 'flex', flexDirection: item.type === 'user' ? 'row-reverse' : 'row' }}>
                  <div style={{ 
                    maxWidth: '70%', 
                    padding: '12px', 
                    borderRadius: '8px', 
                    backgroundColor: item.type === 'user' ? '#1890ff' : '#fff', 
                    color: item.type === 'user' ? '#fff' : '#000',
                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)'
                  }}>
                    {item.content}
                  </div>
                </div>
              ))
            ) : (
              <div style={{ textAlign: 'center', color: '#999', padding: '20px' }}>
                {t('ai_empty_history')}
              </div>
            )}
          </div>
          
          {/* 输入区域 */}
          <div style={{ display: 'flex', gap: '16px' }}>
            <Input.TextArea
              placeholder={t('ai_input_placeholder')}
              value={aiInput}
              onChange={(e) => setAiInput(e.target.value)}
              onPressEnter={() => handleSendAIRequest()}
              autoSize={{ minRows: 1, maxRows: 3 }}
              style={{ flex: 1 }}
            />
            <Space>
              <Button onClick={handleClearAIHistory} disabled={true}>{t('clear')}</Button>
              <Button type="primary" onClick={handleSendAIRequest} loading={aiLoading} disabled={true}>
                {t('send')}
              </Button>
            </Space>
          </div>
        </div>
      </Modal>


    </div>
  );
};

export default StrategyEditor;
