/**
 * 插件配置模块
 * 功能：动态加载和显示插件的配置项
 */
import React from 'react';
import { Card, Form, Input, Select, Switch, InputNumber, Tooltip, Spin } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { PluginConfig } from './types';

interface PluginsProps {
  pluginConfigs: PluginConfig[];
  currentTab: string;
  pluginConfigValues: Record<string, Record<string, any>>;
  setPluginConfigValues: React.Dispatch<React.SetStateAction<Record<string, Record<string, any>>>>;
  pluginLoadingStates: Record<string, boolean>;
  pluginErrorMessages: Record<string, string>;
  pluginManager: any;
}

const Plugins: React.FC<PluginsProps> = ({
  pluginConfigs,
  currentTab,
  pluginConfigValues,
  setPluginConfigValues,
  pluginLoadingStates,
  pluginErrorMessages,
  pluginManager
}) => {
  return (
    <>
      {pluginConfigs.map(pluginConfig => (
        <div key={pluginConfig.name} style={{ display: currentTab === `plugin-${pluginConfig.name}` ? 'block' : 'none' }}>
          <Card className="settings-panel" title={pluginConfig.menuName} variant="outlined">
            <Form layout="vertical">
              {pluginConfig.configs.map(configItem => (
                <Card key={configItem.key} size="small" style={{ marginBottom: 16 }}>
                  {/* 加载状态显示 */}
                  {pluginLoadingStates[pluginConfig.name] ? (
                    <div style={{ textAlign: 'center', padding: '40px' }}>
                      <Spin size="large" />
                      <div style={{ marginTop: '16px', color: '#666' }}>加载插件配置中...</div>
                    </div>
                  ) : (
                    <>
                      {/* 错误信息显示 */}
                      {pluginErrorMessages[pluginConfig.name] && (
                        <div style={{ 
                          padding: '16px', 
                          marginBottom: '16px', 
                          backgroundColor: '#fff2f0', 
                          border: '1px solid #ffccc7', 
                          borderRadius: '4px',
                          color: '#ff4d4f'
                        }}>
                          <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>加载错误</div>
                          <div>{pluginErrorMessages[pluginConfig.name]}</div>
                          <div style={{ marginTop: '8px', fontSize: '12px', color: '#999' }}>
                            已使用插件默认配置
                          </div>
                        </div>
                      )}
                      {/* 配置项渲染 */}
                      {configItem.type === 'string' && (
                        <Form.Item
                          label={
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              {configItem.description}
                              <Tooltip title={configItem.description} placement="right">
                                <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                              </Tooltip>
                            </div>
                          }
                        >
                          <Input
                            placeholder={configItem.description}
                            value={
                              pluginConfigValues[pluginConfig.name]?.[configItem.key] !== undefined ? 
                                pluginConfigValues[pluginConfig.name][configItem.key] : 
                                (window.APP_CONFIG?.[configItem.key] !== undefined ? 
                                  window.APP_CONFIG[configItem.key] : 
                                  configItem.value
                                )
                            }
                            onChange={(e) => {
                              const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                              if (pluginInstance) {
                                const value = e.target.value;
                                const pluginName = pluginConfig.name;
                                // 更新插件实例的配置
                                pluginInstance.instance.setConfig(configItem.key, value);
                                // 更新插件配置值状态
                                setPluginConfigValues(prev => {
                                  const updatedValues = {
                                    ...prev,
                                    [pluginName]: {
                                      ...prev[pluginName],
                                      [configItem.key]: value
                                    }
                                  };
                                  return updatedValues;
                                });
                              }
                            }}
                          />
                        </Form.Item>
                      )}
                      {configItem.type === 'number' && (
                        <Form.Item
                          label={
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              {configItem.description}
                              <Tooltip title={configItem.description} placement="right">
                                <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                              </Tooltip>
                            </div>
                          }
                        >
                          <InputNumber
                            style={{ width: '100%' }}
                            value={
                              pluginConfigValues[pluginConfig.name]?.[configItem.key] !== undefined ? 
                                pluginConfigValues[pluginConfig.name][configItem.key] : 
                                (window.APP_CONFIG?.[configItem.key] !== undefined ? 
                                  Number(window.APP_CONFIG[configItem.key]) : 
                                  Number(configItem.value)
                                )
                            }
                            onChange={(value: number | null) => {
                              const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                              if (pluginInstance) {
                                const finalValue = value || 0;
                                const pluginName = pluginConfig.name;
                                // 更新插件实例的配置
                                pluginInstance.instance.setConfig(configItem.key, finalValue);
                                // 更新插件配置值状态
                                setPluginConfigValues(prev => {
                                  const updatedValues = {
                                    ...prev,
                                    [pluginName]: {
                                      ...prev[pluginName],
                                      [configItem.key]: finalValue
                                    }
                                  };
                                  return updatedValues;
                                });
                              }
                            }}
                          />
                        </Form.Item>
                      )}
                      {configItem.type === 'boolean' && (
                        <Form.Item
                          label={
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              {configItem.description}
                              <Tooltip title={configItem.description} placement="right">
                                <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                              </Tooltip>
                            </div>
                          }
                        >
                          <Switch
                            checkedChildren="启用"
                            unCheckedChildren="禁用"
                            checked={
                              pluginConfigValues[pluginConfig.name]?.[configItem.key] !== undefined ? 
                                pluginConfigValues[pluginConfig.name][configItem.key] : 
                                (window.APP_CONFIG?.[configItem.key] !== undefined ? 
                                  (window.APP_CONFIG[configItem.key] === 'true' || window.APP_CONFIG[configItem.key] === true) : 
                                  (configItem.value === 'true' || configItem.value === true)
                                )
                            }
                            onChange={(checked) => {
                              const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                              if (pluginInstance) {
                                const pluginName = pluginConfig.name;
                                // 更新插件实例的配置
                                pluginInstance.instance.setConfig(configItem.key, checked);
                                // 更新插件配置值状态
                                setPluginConfigValues(prev => {
                                  const updatedValues = {
                                    ...prev,
                                    [pluginName]: {
                                      ...prev[pluginName],
                                      [configItem.key]: checked
                                    }
                                  };
                                  return updatedValues;
                                });
                              }
                            }}
                          />
                        </Form.Item>
                      )}
                      {configItem.type === 'select' && configItem.options && (
                        <Form.Item
                          label={
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              {configItem.description}
                              <Tooltip title={configItem.description} placement="right">
                                <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                              </Tooltip>
                            </div>
                          }
                        >
                          <Select
                            options={configItem.options.map((option: any) => ({
                              value: option,
                              label: option
                            }))}
                            value={
                              pluginConfigValues[pluginConfig.name]?.[configItem.key] || 
                              window.APP_CONFIG?.[configItem.key] || 
                              configItem.value
                            }
                            onChange={(value) => {
                              const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                              if (pluginInstance) {
                                const pluginName = pluginConfig.name;
                                // 更新插件实例的配置
                                pluginInstance.instance.setConfig(configItem.key, value);
                                // 更新插件配置值状态
                                setPluginConfigValues(prev => {
                                  const updatedValues = {
                                    ...prev,
                                    [pluginName]: {
                                      ...prev[pluginName],
                                      [configItem.key]: value
                                    }
                                  };
                                  return updatedValues;
                                });
                              }
                            }}
                          />
                        </Form.Item>
                      )}
                    </>
                  )}
                </Card>
              ))}
            </Form>
          </Card>
        </div>
      ))}
    </>
  );
};

export default Plugins;
