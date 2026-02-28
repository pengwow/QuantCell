import { useState, useEffect } from 'react';
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
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useResponsive } from '../../hooks/useResponsive';
import { strategyApi } from '../../api';
import { setPageTitle } from '@/router';
import PageContainer from '@/components/PageContainer';

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

/**
 * 策略编辑器组件
 * 功能：提供策略代码编辑、执行和结果预览功能
 */
const StrategyEditor = () => {
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [editorLoading, setEditorLoading] = useState<boolean>(false);
  const [code, setCode] = useState<string>('');

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
  const { isMobile } = useResponsive();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(params.strategyName || t('strategy_editor') || '策略编辑器');
  }, [params.strategyName, t]);

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
      const response = await strategyApi.getStrategyDetail(strategyName) as Strategy;
      setSelectedStrategy(response);
      setCode(response.code);
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
      code: `# 新策略模板
from strategy import StrategyBase

class NewStrategy(StrategyBase):
    """
    新策略模板
    """
    # 策略参数
    param1 = 10
    param2 = 20.0
    param3 = "test"

    def on_initialize(self):
        """初始化策略"""
        pass

    def on_update_indicators(self, data):
        """更新技术指标"""
        pass

    def on_generate_signals(self, data):
        """生成交易信号"""
        return []

    def on_execute_orders(self, signals):
        """执行订单"""
        return []

    def on_risk_control(self, signals):
        """风险控制"""
        return signals

    def on_update_performance(self):
        """更新绩效指标"""
        pass

    def on_evaluate_performance(self):
        """绩效评估"""
        return {}

    def on_stop(self):
        """停止策略"""
        pass
`,
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

    navigate('/backtest-config', { state: { strategy: selectedStrategy, showConfig: true } });
  };

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

  // 根据编辑/创建模式确定页面标题
  const pageTitle = params.strategyName
    ? t('edit_strategy') || '编辑策略'
    : t('create_strategy') || '创建策略';

  return (
    <PageContainer title={pageTitle}>
      {/* 页面头部 */}
      <div className="flex flex-wrap justify-between items-center gap-4 mb-4">
        <div className="flex items-center flex-grow min-w-0">
          <Button
            type="default"
            icon={<BackwardOutlined />}
            onClick={handleBack}
            className="mr-4"
          >
            {t('back') || '返回'}
          </Button>
          {isEditingName ? (
            <div className="relative flex-grow min-w-0">
              <Input
                type="text"
                value={tempName}
                onChange={handleTempNameChange}
                onKeyPress={(e) => e.key === 'Enter' && handleSaveName()}
                onBlur={handleSaveName}
                autoFocus
                className="text-xl font-medium border-blue-500 rounded w-full max-w-xs"
              />
            </div>
          ) : (
            <h2
              className="text-xl font-medium m-0 cursor-pointer truncate"
              style={{
                maxWidth: isMobile ? '100%' : 'calc(100% - 100px)',
                whiteSpace: isMobile ? 'normal' : 'nowrap',
              }}
              onClick={handleStartEditName}
            >
              {selectedStrategy ? selectedStrategy.name : t('strategy_editor') || '策略编辑器'}
            </h2>
          )}
        </div>

        {/* 操作按钮组 */}
        <Space
          wrap
          className={isMobile ? 'w-full justify-start' : ''}
        >
          <Button
            type="default"
            icon={<ReloadOutlined />}
            onClick={handleResetCode}
            loading={loading}
          >
            {t('reset') || '重置'}
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleBacktestStrategy}
            loading={loading}
          >
            {t('backtest') || '回测'}
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSaveStrategy}
            loading={loading}
          >
            {t('save') || '保存'}
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
                label: <><CodeOutlined /> {t('editor') || '编辑器'}</>,
                children: (
                  <div className="w-full" style={{ minHeight: '600px' }}>
                    <textarea
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      className="w-full h-full min-h-[600px] p-4 font-mono text-sm bg-gray-900 text-gray-100 rounded resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                      style={{
                        fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                        lineHeight: '1.6',
                      }}
                      spellCheck={false}
                    />
                  </div>
                )
              },
              {
                key: 'preview',
                label: <><EyeOutlined /> {t('preview') || '预览'}</>,
                children: (
                  <div className="p-5">
                    <h3 className="mb-4">{t('strategy_information') || '策略信息'}</h3>
                    <Descriptions bordered column={1} className="mb-5">
                      <Descriptions.Item label={t('name') || '名称'}>
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
                          <span onClick={handleStartEditName} className="cursor-pointer">
                            {selectedStrategy?.name || ''}
                          </span>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('version') || '版本'}>
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
                          <span onClick={handleStartEditVersion} className="cursor-pointer">
                            {selectedStrategy?.version || ''}
                          </span>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('description') || '描述'}>
                        {isEditingDescription ? (
                          <Space>
                            <Input.TextArea
                              value={tempDescription}
                              onChange={handleTempDescriptionChange}
                              onBlur={handleSaveDescription}
                              autoFocus
                              rows={3}
                            />
                          </Space>
                        ) : (
                          <span onClick={handleStartEditDescription} className="cursor-pointer">
                            {selectedStrategy?.description || t('no_description') || '暂无描述'}
                          </span>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('created_at') || '创建时间'}>
                        {selectedStrategy ? new Date(selectedStrategy.created_at).toLocaleString() : ''}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('updated_at') || '更新时间'}>
                        {selectedStrategy ? new Date(selectedStrategy.updated_at).toLocaleString() : ''}
                      </Descriptions.Item>
                    </Descriptions>

                    <h3 className="mt-5 mb-4">{t('parameter_list') || '参数列表'}</h3>
                    {selectedStrategy?.params && selectedStrategy.params.length > 0 ? (
                      <Descriptions bordered column={1}>
                        {selectedStrategy.params.map((param, index) => (
                          <Descriptions.Item key={index} label={param.name}>
                            <div>
                              <p className="mb-2">{param.description || t('no_description') || '暂无描述'}</p>
                              <small>{t('type') || '类型'}: {param.type}, {t('default_value') || '默认值'}: {JSON.stringify(param.default)}</small>
                            </div>
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    ) : (
                      <div className="p-5 text-center text-gray-400">
                        {t('no_parameters') || '暂无参数'}
                      </div>
                    )}
                  </div>
                )
              }
            ]}
          />
        </Spin>
      </Card>
    </PageContainer>
  );
};

export default StrategyEditor;
