/**
 * ToolConfigDrawer - 工具参数配置管理抽屉
 *
 * 功能特性:
 * - 左右分栏布局：工具列表 | 参数详情
 * - 实时状态反馈：已配置/未配置/来源标识
 * - 敏感信息自动脱敏显示
 * - 参数编辑与验证
 * - 批量操作：导入/导出配置
 *
 * 设计风格: 专业工具面板 + 暗色科技感
 */

import { useEffect, useState } from 'react';
import {
  Drawer,
  List,
  Card,
  Tag,
  Button,
  Input,
  InputNumber,
  Switch,
  Space,
  Tooltip,
  message,
  Empty,
  Spin,
  Modal,
  Upload,
  Typography,
  Badge,
  Alert,
} from 'antd';
import {
  SettingOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  LockOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  ToolOutlined,
  ReloadOutlined,
  SaveOutlined,
  DeleteOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  InfoCircleOutlined,
  ExportOutlined,
  ImportOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  toolParamApi,
  ToolInfo,
  ToolParamsResponse,
  ToolParamValue,
} from '../../api/agentApi';
import './ToolConfigDrawer.css';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface ToolConfigDrawerProps {
  visible: boolean;
  onClose: () => void;
}

const ToolConfigDrawer: React.FC<ToolConfigDrawerProps> = ({ visible, onClose }) => {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [toolParams, setToolParams] = useState<ToolParamsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editValues, setEditValues] = useState<Record<string, any>>({});
  const [showSensitive, setShowSensitive] = useState<Record<string, boolean>>({});

  // 加载工具列表
  const loadTools = async () => {
    setLoading(true);
    try {
      const data = await toolParamApi.getRegisteredTools();
      setTools(data);
      if (data.length > 0 && !selectedTool) {
        setSelectedTool(data[0].name);
      }
    } catch (error) {
      message.error('加载工具列表失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 加载选中工具的参数
  const loadToolParams = async (toolName: string) => {
    setLoading(true);
    try {
      const data = await toolParamApi.getToolParams(toolName, false);
      setToolParams(data);
      // 初始化编辑值
      const initialValues: Record<string, any> = {};
      Object.entries(data.params).forEach(([key, param]) => {
        initialValues[key] = param.value;
      });
      setEditValues(initialValues);
    } catch (error) {
      message.error('加载参数失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 初始化加载数据
  useEffect(() => {
    if (visible) {
      loadTools();
    }
  }, [visible]);

  // 当选中工具变化时加载参数
  useEffect(() => {
    if (selectedTool && visible) {
      loadToolParams(selectedTool);
    }
  }, [selectedTool, visible]);

  // 切换敏感信息显示
  const toggleShowSensitive = async (paramName: string) => {
    if (!showSensitive[paramName]) {
      // 需要获取真实值
      try {
        const data = await toolParamApi.getToolParams(selectedTool!, true);
        setToolParams(data);
        setEditValues(prev => ({
          ...prev,
          [paramName]: data.params[paramName].value,
        }));
        setShowSensitive(prev => ({ ...prev, [paramName]: true }));
      } catch (error) {
        message.error('获取敏感参数值失败');
      }
    } else {
      // 重新加载脱敏版本
      await loadToolParams(selectedTool!);
      setShowSensitive(prev => ({ ...prev, [paramName]: false }));
    }
  };

  // 更新单个参数
  const handleUpdateParam = async (paramName: string, value: any) => {
    setSaving(true);
    try {
      await toolParamApi.setToolParam(selectedTool!, paramName, value);
      message.success(`参数 ${paramName} 已更新`);
      // 刷新参数列表
      await loadToolParams(selectedTool!);
      await loadTools(); // 刷新工具列表以更新配置计数
    } catch (error: any) {
      message.error(`更新失败: ${error.message || '未知错误'}`);
    } finally {
      setSaving(false);
    }
  };

  // 删除参数
  const handleDeleteParam = async (paramName: string) => {
    Modal.confirm({
      title: '确认删除',
      icon: <QuestionCircleOutlined />,
      content: `确定要删除参数 "${paramName}" 吗？删除后将使用环境变量或默认值。`,
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await toolParamApi.deleteToolParam(selectedTool!, paramName);
          message.success(`参数 ${paramName} 已删除`);
          await loadToolParams(selectedTool!);
          await loadTools();
        } catch (error: any) {
          message.error(`删除失败: ${error.message || '未知错误'}`);
        }
      },
    });
  };

  // 导出配置
  const handleExport = async () => {
    try {
      const config = await toolParamApi.exportToolConfig(selectedTool || undefined);
      const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tool_config_${selectedTool || 'all'}_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success('配置已导出');
    } catch (error) {
      message.error('导出失败');
    }
  };

  // 导入配置
  const handleImport = (file: UploadFile) => {
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const config = JSON.parse(e.target?.result as string);
        Modal.confirm({
          title: '确认导入',
          content: `确定要导入配置吗？这将更新工具参数。`,
          okText: '确认导入',
          cancelText: '取消',
          onOk: async () => {
            try {
              const result = await toolParamApi.importToolConfig(config, false);
              message.success(
                `导入完成: 成功 ${result.imported} 个, 跳过 ${result.skipped} 个`
              );
              if (result.errors.length > 0) {
                console.warn('导入警告:', result.errors);
              }
              await loadTools();
              if (selectedTool) {
                await loadToolParams(selectedTool);
              }
            } catch (error: any) {
              message.error(`导入失败: ${error.message || '未知错误'}`);
            }
          },
        });
      } catch (error) {
        message.error('配置文件格式错误');
      }
    };
    reader.readAsText(file as any);
    return false; // 阻止自动上传
  };

  // 渲染来源标签
  const renderSourceTag = (source: string) => {
    const sourceMap: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
      database: { color: 'blue', icon: <DatabaseOutlined />, text: '数据库' },
      environment: { color: 'green', icon: <GlobalOutlined />, text: '环境变量' },
      default: { color: 'default', icon: <SettingOutlined />, text: '默认值' },
    };

    const config = sourceMap[source] || sourceMap.default;
    return (
      <Tag color={config.color} icon={config.icon}>
        {config.text}
      </Tag>
    );
  };

  // 渲染参数输入控件
  const renderParamInput = (paramName: string, param: ToolParamValue) => {
    if (param.sensitive && !showSensitive[paramName]) {
      return (
        <Space>
          <Input.Password
            value="••••••••"
            disabled
            style={{ width: 200 }}
            iconRender={(visible) =>
              visible ? <EyeOutlined /> : <EyeInvisibleOutlined />
            }
          />
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => toggleShowSensitive(paramName)}
          >
            显示
          </Button>
        </Space>
      );
    }

    switch (param.type) {
      case 'integer':
        return (
          <InputNumber
            value={editValues[paramName]}
            onChange={(value) =>
              setEditValues((prev) => ({ ...prev, [paramName]: value }))
            }
            min={-Infinity}
            max={Infinity}
            style={{ width: '100%' }}
            onPressEnter={(e: any) =>
              handleUpdateParam(paramName, e.target.value)
            }
          />
        );
      case 'float':
        return (
          <InputNumber
            value={editValues[paramName]}
            onChange={(value) =>
              setEditValues((prev) => ({ ...prev, [paramName]: value }))
            }
            step={0.1}
            min={-Infinity}
            max={Infinity}
            style={{ width: '100%' }}
          />
        );
      case 'boolean':
        return (
          <Switch
            checked={editValues[paramName]}
            onChange={(checked) => {
              setEditValues((prev) => ({ ...prev, [paramName]: checked }));
              handleUpdateParam(paramName, checked);
            }}
          />
        );
      default:
        return (
          <TextArea
            value={editValues[paramName]}
            onChange={(e) =>
              setEditValues((prev) => ({ ...prev, [paramName]: e.target.value }))
            }
            autoSize={{ minRows: 1, maxRows: 3 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleUpdateParam(paramName, e.currentTarget.value);
              }
            }}
          />
        );
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <SettingOutlined />
          <span>⚙️ 工具参数配置</span>
        </Space>
      }
      placement="right"
      onClose={onClose}
      open={visible}
      width={900}
      className="tool-config-drawer"
      extra={
        <Space>
          <Tooltip title="刷新">
            <Button
              type="text"
              icon={<ReloadOutlined />}
              onClick={() => {
                loadTools();
                if (selectedTool) loadToolParams(selectedTool);
              }}
              loading={loading}
            />
          </Tooltip>
          <Tooltip title="导出配置">
            <Button
              type="text"
              icon={<ExportOutlined />}
              onClick={handleExport}
            >
              导出
            </Button>
          </Tooltip>
          <Upload
            accept=".json"
            showUploadList={false}
            beforeUpload={handleImport}
          >
            <Tooltip title="导入配置">
              <Button type="text" icon={<ImportOutlined />}>
                导入
              </Button>
            </Tooltip>
          </Upload>
        </Space>
      }
    >
      <div className="tool-config-content">
        {/* 左侧：工具列表 */}
        <div className="tool-list-panel">
          <div className="panel-header">
            <Text strong>已注册工具</Text>
            <Badge count={tools.length} showZero color="#1890ff" />
          </div>

          <Spin spinning={loading}>
            <List
              dataSource={tools}
              renderItem={(tool) => (
                <List.Item
                  className={`tool-item ${selectedTool === tool.name ? 'selected' : ''}`}
                  onClick={() => setSelectedTool(tool.name)}
                >
                  <div className="tool-item-content">
                    <div className="tool-info">
                      <Space>
                        <ToolOutlined />
                        <Text strong>{tool.name}</Text>
                      </Space>
                      <div className="tool-status">
                        {tool.has_required_params ? (
                          <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        ) : (
                          <WarningOutlined style={{ color: '#faad14' }} />
                        )}
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {tool.configured_count}/{tool.param_count}
                        </Text>
                      </div>
                    </div>
                  </div>
                </List.Item>
              )}
              locale={{ emptyText: <Empty description="暂无工具" /> }}
            />
          </Spin>
        </div>

        {/* 右侧：参数详情 */}
        <div className="tool-params-panel">
          {selectedTool && toolParams ? (
            <>
              <div className="params-header">
                <div className="params-title">
                  <Text strong style={{ fontSize: 16 }}>
                    🔧 {selectedTool}
                  </Text>
                  <div className="params-meta">
                    <Tag color="processing">
                      {Object.keys(toolParams.params).length} 个参数
                    </Tag>
                    <Tag color="success">
                      {Object.values(toolParams.params).filter((p) => p.configured).length}{' '}
                      已配置
                    </Tag>
                  </div>
                </div>
                <Alert
                  message="提示"
                  description="修改参数后按 Enter 保存，或点击保存按钮。敏感参数需要点击「显示」按钮查看真实值。"
                  type="info"
                  showIcon
                  closable
                  style={{ marginBottom: 16 }}
                />
              </div>

              <div className="params-list">
                {Object.entries(toolParams.params).map(
                  ([paramName, param]) => (
                    <Card
                      key={paramName}
                      className="param-card"
                      size="small"
                      hoverable={false}
                    >
                      <div className="param-header">
                        <Space>
                          {param.sensitive ? (
                            <LockOutlined style={{ color: '#fa8c16' }} />
                          ) : (
                            <InfoCircleOutlined style={{ color: '#1890ff' }} />
                          )}
                          <Text strong>{paramName}</Text>
                          {param.sensitive && (
                            <Tag color="warning">敏感</Tag>
                          )}
                        </Space>
                        <Space>
                          {renderSourceTag(param.source)}
                          {param.configured && (
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => handleDeleteParam(paramName)}
                            />
                          )}
                        </Space>
                      </div>

                      {param.description && (
                        <Paragraph
                          type="secondary"
                          style={{ fontSize: 12, marginBottom: 8 }}
                        >
                          {param.description}
                        </Paragraph>
                      )}

                      <div className="param-input-wrapper">
                        {renderParamInput(paramName, param)}

                        {(editValues[paramName] !== param.value ||
                          !param.configured) && (
                          <Button
                            type="primary"
                            size="small"
                            icon={<SaveOutlined />}
                            loading={saving}
                            onClick={() =>
                              handleUpdateParam(paramName, editValues[paramName])
                            }
                            style={{ marginLeft: 8 }}
                          >
                            保存
                          </Button>
                        )}
                      </div>
                    </Card>
                  )
                )}
              </div>
            </>
          ) : (
            <Empty
              description="选择一个工具查看参数配置"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </div>
      </div>
    </Drawer>
  );
};

export default ToolConfigDrawer;
