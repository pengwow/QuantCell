/**
 * 工具列表抽屉（集成参数配置）—— 自 Agent.tsx 原样拆出（P1 工作台改造，仅文件移动不改语义）。
 */
import { useState } from 'react';
import axios from 'axios';
import {
  Input,
  InputNumber,
  Button,
  Spin,
  Empty,
  Drawer,
  Tag,
  Tooltip,
  App,
  Switch,
  Space,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  LockOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  EyeOutlined,
  SaveOutlined,
  ReloadOutlined,
  DownOutlined,
  UpOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  toolParamApi,
  ToolParamsResponse,
  ToolParamValue,
} from '@/api/agentApi';
import type { Tool } from '../store/agentStore';
import { QUANT_COLORS } from '@/utils/colors';

const { Text } = Typography;

// 工具列表抽屉（集成参数配置功能）
const ToolListDrawerWithConfig = ({
  visible,
  onClose,
  tools,
}: {
  visible: boolean;
  onClose: () => void;
  tools: Tool[];
}) => {
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [toolsParams, setToolsParams] = useState<Record<string, ToolParamsResponse>>({});
  const [loadingParams, setLoadingParams] = useState<Set<string>>(new Set());
  const [editingValues, setEditingValues] = useState<Record<string, Record<string, unknown>>>({});
  const [showSensitive, setShowSensitive] = useState<Record<string, Record<string, boolean>>>({});
  const { message } = App.useApp();
  const { t } = useTranslation();

  // 切换工具展开/折叠
  const toggleExpand = async (toolName: string) => {
    const newExpanded = new Set(expandedTools);
    if (newExpanded.has(toolName)) {
      newExpanded.delete(toolName);
    } else {
      newExpanded.add(toolName);
      // 加载参数
      if (!toolsParams[toolName]) {
        await loadToolParams(toolName);
      }
    }
    setExpandedTools(newExpanded);
  };

  // 加载工具参数
  const loadToolParams = async (toolName: string) => {
    setLoadingParams(prev => new Set(prev).add(toolName));
    try {
      const data = await toolParamApi.getToolParams(toolName, false);
      setToolsParams(prev => ({ ...prev, [toolName]: data }));
      
      // 初始化编辑值（仅当有参数时）
      if (data.params && Object.keys(data.params).length > 0) {
        const initialValues: Record<string, unknown> = {};
        Object.entries(data.params).forEach(([key, param]) => {
          initialValues[key] = param.value;
        });
        setEditingValues(prev => ({ ...prev, [toolName]: initialValues }));
      }
    } catch (error) {
      // 404 表示工具无参数模板，这不是错误
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        setToolsParams(prev => ({ 
          ...prev, 
          [toolName]: { tool_name: toolName, params: {} } 
        }));
      } else {
        message.error(t('agent_load_tool_params_failed', { name: toolName }));
      }
    } finally {
        setLoadingParams(prev => {
          const next = new Set(prev);
          next.delete(toolName);
          return next;
        });
    }
  };

  // 切换敏感参数显示
  const toggleSensitive = async (toolName: string, paramName: string) => {
    if (!showSensitive[toolName]?.[paramName]) {
      try {
        const data = await toolParamApi.getToolParams(toolName, true);
        setToolsParams(prev => ({ ...prev, [toolName]: data }));
        setEditingValues(prev => ({
          ...prev,
          [toolName]: {
            ...prev[toolName],
            [paramName]: data.params[paramName].value,
          },
        }));
        setShowSensitive(prev => ({
          ...prev,
          [toolName]: { ...prev[toolName], [paramName]: true },
        }));
      } catch {
        message.error(t('agent_sensitive_value_failed'));
      }
    } else {
      // 重新加载脱敏版本
      await loadToolParams(toolName);
      setShowSensitive(prev => ({
        ...prev,
        [toolName]: { ...prev[toolName], [paramName]: false },
      }));
    }
  };

  // 更新参数
  const handleUpdateParam = async (toolName: string, paramName: string, value: unknown) => {
    try {
      await toolParamApi.setToolParam(toolName, paramName, value);
      message.success(t('agent_param_updated', { name: paramName }));
      await loadToolParams(toolName); // 刷新参数
    } catch (error) {
      message.error(t('agent_update_failed', { message: error instanceof Error ? error.message : t('unknown_error') }));
    }
  };

  // 渲染来源标签
  const renderSourceTag = (source: string) => {
    const config: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
      database: { color: 'blue', icon: <DatabaseOutlined />, text: t('agent_source_database') },
      environment: { color: 'green', icon: <GlobalOutlined />, text: t('env_variables') },
      default: { color: 'default', icon: <SettingOutlined />, text: t('default_value') },
    };
    const c = config[source] || config.default;
    return <Tag color={c.color} icon={c.icon}>{c.text}</Tag>;
  };

  // 渲染参数输入控件
  const renderParamInput = (
    toolName: string,
    paramName: string,
    param: ToolParamValue
  ) => {
    if (param.sensitive && !showSensitive[toolName]?.[paramName]) {
      return (
        <Space>
          <Input.Password
            value="••••••••"
            disabled
            style={{ width: 160 }}
            size="small"
          />
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => toggleSensitive(toolName, paramName)}
          >
            {t('show')}
          </Button>
        </Space>
      );
    }

    switch (param.type) {
      case 'integer':
        return (
          <InputNumber
            size="small"
            value={editingValues[toolName]?.[paramName] as number}
            onChange={(value) =>
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: value },
              }))
            }
            style={{ width: 120 }}
            onPressEnter={(e: React.KeyboardEvent<HTMLInputElement>) =>
              handleUpdateParam(toolName, paramName, e.currentTarget.value)
            }
          />
        );
      case 'float':
        return (
          <InputNumber
            size="small"
            value={editingValues[toolName]?.[paramName] as number}
            onChange={(value) =>
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: value },
              }))
            }
            step={0.1}
            style={{ width: 120 }}
          />
        );
      case 'boolean':
        return (
          <Switch
            size="small"
            checked={Boolean(editingValues[toolName]?.[paramName])}
            onChange={(checked) => {
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: checked },
              }));
              handleUpdateParam(toolName, paramName, checked);
            }}
          />
        );
      default:
        return (
          <Input
            size="small"
            value={editingValues[toolName]?.[paramName] as string}
            onChange={(e) =>
              setEditingValues(prev => ({
                ...prev,
                [toolName]: { ...prev[toolName], [paramName]: e.target.value },
              }))
            }
            onPressEnter={(e) =>
              handleUpdateParam(toolName, paramName, e.currentTarget.value)
            }
            style={{ width: 160 }}
          />
        );
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <SettingOutlined />
          <span>{t('agent_tool_settings')}</span>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => {
              setToolsParams({});
              // 重命名局部变量避免与翻译函数 t 遮蔽冲突
              tools.forEach(tool => loadToolParams(tool.name));
            }}
          >
            {t('agent_refresh_config')}
          </Button>
        </Space>
      }
      placement="right"
      onClose={onClose}
      open={visible}
      size="large"
      className="tool-list-config-drawer"
    >
      <p className="tool-list-note">{t('agent_tool_settings_note')}</p>
      <div className="tool-list-with-config">
        {tools.map(tool => {
          const isExpanded = expandedTools.has(tool.name);
          const params = toolsParams[tool.name];
          const isLoading = loadingParams.has(tool.name);

          return (
            <div key={tool.name} className={`tool-item-wrapper ${isExpanded ? 'expanded' : ''}`}>
              {/* 工具项头部 */}
              <div
                className="tool-item-header"
                onClick={() => toggleExpand(tool.name)}
              >
                <div className="tool-item-info">
                  <Space>
                    <Tag color="blue">{tool.name}</Tag>
                    {params && (
                      params.params && Object.values(params.params).some(p => p.configured) ? (
                        <CheckCircleOutlined style={{ color: QUANT_COLORS.positive }} />
                      ) : null
                    )}
                  </Space>
                </div>
                <Space>
                  <Tooltip title={isExpanded ? t('agent_collapse_params') : t('agent_expand_params')}>
                    {isExpanded ? <UpOutlined /> : <DownOutlined />}
                  </Tooltip>
                </Space>
              </div>

              {/* 工具描述 */}
              <p className="tool-description">{tool.description}</p>

              {/* 展开的参数面板 */}
              {isExpanded && (
                <div className="tool-params-panel">
                  {isLoading ? (
                    <Spin size="small" tip={t('loading')} />
                  ) : params && params.params && Object.keys(params.params).length > 0 ? (
                    <div className="params-container">
                      {Object.entries(params.params).map(
                        ([paramName, param]) => (
                          <div key={paramName} className="param-row">
                            <div className="param-info">
                              <Space size={4}>
                                {param.sensitive ? (
                                  <LockOutlined
                                    style={{
                                      fontSize: 12,
                                      color: QUANT_COLORS.warning,
                                    }}
                                  />
                                ) : null}
                                <Text
                                  strong
                                  style={{ fontSize: 12 }}
                                >
                                  {paramName}
                                </Text>
                                {renderSourceTag(param.source)}
                              </Space>
                              {param.description && (
                                <Text
                                  type="secondary"
                                  style={{
                                    fontSize: 11,
                                    display: 'block',
                                    marginTop: 2,
                                  }}
                                >
                                  {param.description}
                                </Text>
                              )}
                            </div>

                            <div className="param-action">
                              <Space size={4}>
                                {renderParamInput(
                                  tool.name,
                                  paramName,
                                  param
                                )}
                                {(editingValues[tool.name]?.[paramName] !==
                                  param.value ||
                                  !param.configured) && (
                                  <Button
                                    type="primary"
                                    size="small"
                                    icon={<SaveOutlined />}
                                    onClick={() =>
                                      handleUpdateParam(
                                        tool.name,
                                        paramName,
                                        editingValues[tool.name]?.[
                                          paramName
                                        ]
                                      )
                                    }
                                  >
                                    {t('save')}
                                  </Button>
                                )}
                              </Space>
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  ) : (
                    // 工具存在但无参数或已加载完成无参数
                    <Empty
                      description={
                        <span style={{ fontSize: 11 }}>
                          {t('agent_no_params_needed')}
                        </span>
                      }
                      styles={{ image: { height: 35 } }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Drawer>
  );
};

export default ToolListDrawerWithConfig;
