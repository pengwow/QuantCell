/**
 * 日志设置统一页面 - 与项目风格统一
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  Table,
  Button,
  Input,
  Space,
  Tag,
  Switch,
  InputNumber,
  Radio,
  Progress,
  Row,
  Col,
  Modal,
  Alert,
  Descriptions,
  Tooltip,
  Spin,
  message as antMessage,
  Divider,
} from 'antd';
import {
  IconSearch,
  IconRefresh,
  IconTrash,
  IconSettings,
  IconChartPie,
  IconSortAscending,
  IconSortDescending,
  IconAlertTriangle,
  IconFile,
  IconDownload,
  IconDatabase,
  IconDeviceFloppy,
  IconRotateDot,
} from '@tabler/icons-react';
import { systemApi } from '../../api';
import type { LogDirectoryNode, LogFileInfo, LogAutoCleanupConfig, CleanupResult } from './types';

interface LogSettingsUnifiedProps {
  onClose?: () => void;
}

function LogSettingsUnified({ onClose }: LogSettingsUnifiedProps) {
  // ========== 状态定义 ==========
  const [directoryTree, setDirectoryTree] = useState<LogDirectoryNode | null>(null);
  const [diskUsage, setDiskUsage] = useState<any>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<LogFileInfo | null>(null);
  const [currentDir, setCurrentDir] = useState<string>('');
  const [searchText, setSearchText] = useState('');
  const [sortOrder, setSortOrder] = useState<'ascend' | 'descend'>('descend');

  // 自动清理配置
  const defaultConfig: LogAutoCleanupConfig = {
    enabled: false,
    retention_days: 30,
    max_size_gb: 10,
    cleanup_schedule: 'weekly',
    space_used: 0,
    last_cleanup_time: null,
    next_cleanup_time: null,
  };
  const [config, setConfig] = useState<LogAutoCleanupConfig>({ ...defaultConfig });
  const [originalConfig, setOriginalConfig] = useState<LogAutoCleanupConfig | null>(null);

  // 清理操作相关
  const [deleteModalVisible, setDeleteModalVisible] = useState(false);
  const [riskConfirmed, setRiskConfirmed] = useState(false);
  const [lastResult, setLastResult] = useState<CleanupResult | null>(null);

  // 加载状态
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // 详情抽屉展开状态
  const [detailExpanded, setDetailExpanded] = useState(false);

  // ========== 数据加载 ==========
  const loadAllData = useCallback(async () => {
    try {
      setLoading(true);
      const [dirData, diskData, configData] = await Promise.all([
        systemApi.getLogDirectory(),
        systemApi.getLogDiskUsage(),
        systemApi.getAutoCleanupConfig(),
      ]);

      // axios拦截器已解包 response.data.data，直接使用返回值
      setDirectoryTree(dirData);
      setDiskUsage(diskData);

      if (configData) {
        setConfig(configData);
        setOriginalConfig(configData);
      }

      // 默认选中"全部"（根目录）
      if (!currentDir && dirData) {
        setCurrentDir(dirData.path);
      }
    } catch (error) {
      antMessage.error('加载数据失败');
      console.error('加载日志数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [currentDir]);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // ========== 计算属性 ==========
  const currentFiles = useMemo(() => {
    if (!directoryTree) return [];

    let files: LogFileInfo[] = [];
    if (currentDir === directoryTree.path) {
      files = directoryTree.children?.flatMap(child => child.files || []) || [];
    } else {
      const targetDir = directoryTree.children?.find(child => child.path === currentDir);
      files = targetDir?.files || [];
    }

    if (searchText) {
      files = files.filter(file =>
        file.name.toLowerCase().includes(searchText.toLowerCase())
      );
    }

    files = [...files].sort((a, b) => {
      const multiplier = sortOrder === 'ascend' ? 1 : -1;
      return (a.size - b.size) * multiplier;
    });

    return files;
  }, [directoryTree, currentDir, searchText, sortOrder]);

  const stats = useMemo(() => {
    const selectedFiles = currentFiles.filter(file => selectedKeys.has(file.path));
    return {
      count: selectedFiles.length,
      totalSize: selectedFiles.reduce((sum, file) => sum + file.size, 0),
    };
  }, [currentFiles, selectedKeys]);

  const getSpacePercent = useCallback(() => {
    if (!diskUsage || !diskUsage.total_space || diskUsage.total_space <= 0) return 0;
    return Math.min((diskUsage.used_space / diskUsage.total_space) * 100, 100);
  }, [diskUsage]);

  const isDirty = useMemo(() => {
    if (!originalConfig) return false;
    return JSON.stringify(config) !== JSON.stringify(originalConfig);
  }, [config, originalConfig]);

  // ========== 事件处理 ==========
  const toggleSort = () => {
    setSortOrder(prev => prev === 'ascend' ? 'descend' : 'ascend');
  };

  const handleSelectChange = (selectedRowKeys: React.Key[]) => {
    setSelectedKeys(new Set(selectedRowKeys as string[]));
  };

  const handleRowClick = async (record: LogFileInfo) => {
    setSelectedFile(record);
    setDetailExpanded(true);

    // 异步加载文件详情（包括行数）
    try {
      const detailInfo = await systemApi.getLogFileDetail(record.path);
      if (detailInfo && detailInfo.line_count !== undefined) {
        setSelectedFile(prev => prev ? { ...prev, ...detailInfo } : detailInfo);
      }
    } catch (error) {
      console.error('获取文件详情失败:', error);
    }
  };

  const handleSaveConfig = async () => {
    try {
      setSaving(true);
      await systemApi.updateAutoCleanupConfig(config);
      setOriginalConfig({ ...config });
      antMessage.success('配置已保存');
    } catch (error) {
      antMessage.error('保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  const handleResetConfig = () => {
    Modal.confirm({
      title: '确认重置',
      content: '确定要重置所有配置为默认值吗？此操作不可撤销。',
      okText: '确认重置',
      cancelText: '取消',
      onOk: () => {
        if (originalConfig) {
          setConfig({ ...originalConfig });
          antMessage.info('已恢复为上次保存的配置');
        }
      },
    });
  };

  const handleExportConfig = () => {
    const exportData = {
      autoCleanup: config,
      exportedAt: new Date().toISOString(),
      version: '1.2.0',
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `log-config-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    antMessage.success('配置已导出');
  };

  const handleDeleteSelected = async () => {
    if (!riskConfirmed) return;

    const filesToDelete = currentFiles.filter(file => selectedKeys.has(file.path));
    if (filesToDelete.length === 0) return;

    try {
      setDeleting(true);
      const result = await systemApi.deleteLogFilesBatch(
        filesToDelete.map(f => f.path)
      );

      setLastResult(result);
      setSelectedKeys(new Set());
      setDeleteModalVisible(false);
      setRiskConfirmed(false);

      await loadAllData();

      if (result.errors.length === 0) {
        antMessage.success(`成功删除 ${result.deleted_count} 个文件`);
      } else {
        antMessage.warning(`删除完成：${result.deleted_count} 成功，${result.errors.length} 失败`);
      }
    } catch (error) {
      antMessage.error('删除操作失败');
    } finally {
      setDeleting(false);
    }
  };

  // ========== 表格列定义 ==========
  const columns = [
    {
      title: '文件名',
      dataIndex: 'name',
      render: (name: string, record: LogFileInfo) => (
        <div className="flex items-center gap-2">
          <IconFile size={16} className="text-blue-500" />
          <span className="font-mono text-sm">{name}</span>
        </div>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      width: 100,
      sorter: true,
      sortOrder,
      render: (size: number) => (
        <Tag color="blue">{formatSize(size)}</Tag>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 90,
      render: (type: string) => {
        const colors: Record<string, string> = {
          application: 'blue',
          system: 'green',
          api: 'orange',
        };
        return <Tag color={colors[type] || 'default'}>{type}</Tag>;
      },
    },
    {
      title: '修改时间',
      dataIndex: 'modified_time',
      width: 160,
      render: (time: string) => (
        <span className="text-xs text-gray-600">
          {getRelativeTime(time)}
        </span>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 60,
      render: (_: any, record: LogFileInfo) => (
        <Button
          type="link"
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            handleRowClick(record);
          }}
        >
          详情
        </Button>
      ),
    },
  ];

  // ========== 辅助函数 ==========
  function formatSize(bytes: number): string {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function getRelativeTime(timeStr: string): string {
    try {
      let time: Date;

      // 兼容多种时间格式
      if (!timeStr || timeStr === '-' || timeStr === 'None' || timeStr === 'null') {
        return '-';
      }

      // 处理 ISO 格式（带或不带时区）
      time = new Date(timeStr);

      // 检查日期是否有效
      if (isNaN(time.getTime())) {
        return '-';
      }

      const now = new Date();
      const diffMs = now.getTime() - time.getTime();

      // 如果时间在未来，显示原始日期
      if (diffMs < 0) {
        return time.toLocaleDateString('zh-CN');
      }

      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return '刚刚';
      if (diffMins < 60) return `${diffMins}分钟前`;
      if (diffHours < 24) return `${diffHours}小时前`;
      if (diffDays < 7) return `${diffDays}天前`;
      return time.toLocaleDateString('zh-CN');
    } catch {
      return '-';
    }
  }

  function getProgressColor(percent: number): string {
    if (percent > 85) return '#f5222d';
    if (percent > 70) return '#faad14';
    return '#52c41a';
  }

  // ========== 渲染 ==========
  return (
    <div className="log-settings-unified">
      {/* 主体内容区 */}
      <main className="p-4">
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
          {/* 左侧：文件管理区 */}
          <div className="xl:col-span-3 space-y-4">
            
            {/* 筛选工具栏 */}
            <Card size="small" className="shadow-sm">
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Input
                    placeholder="搜索文件名..."
                    prefix={<IconSearch size={16} className="text-gray-400" />}
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    allowClear
                    style={{ flex: 1, minWidth: 200 }}
                  />
                  <Tooltip title={`排序: ${sortOrder === 'descend' ? '降序' : '升序'}`}>
                    <Button
                      icon={sortOrder === 'ascend' ? <IconSortAscending size={18} /> : <IconSortDescending size={18} />}
                      onClick={toggleSort}
                    />
                  </Tooltip>
                  <Button
                    icon={<IconRefresh size={16} />}
                    onClick={loadAllData}
                    loading={loading}
                  >
                    刷新
                  </Button>
                  <Tooltip title="导出当前配置为JSON文件">
                    <Button
                      icon={<IconDownload size={16} />}
                      onClick={handleExportConfig}
                    >
                      导出
                    </Button>
                  </Tooltip>
                  {onClose && (
                    <Button onClick={onClose}>
                      返回
                    </Button>
                  )}
                </div>

                {selectedKeys.size > 0 && (
                  <div className="flex items-center justify-between p-2 bg-blue-50 rounded border border-blue-200">
                    <span className="text-sm text-gray-700">
                      已选择 <strong>{stats.count}</strong> 个文件（总计 <strong className="text-blue-600">{formatSize(stats.totalSize)}</strong>）
                    </span>
                    <Button
                      danger
                      size="small"
                      icon={<IconTrash size={14} />}
                      onClick={() => setDeleteModalVisible(true)}
                    >
                      批量删除
                    </Button>
                  </div>
                )}
              </div>
            </Card>

            {/* 目录标签组 */}
            {directoryTree && (
              <Card size="small" className="shadow-sm">
                <div className="flex gap-2 flex-wrap">
                  <Tag.CheckableTag
                    checked={currentDir === directoryTree.path}
                    onChange={() => setCurrentDir(directoryTree.path)}
                  >
                    📁 全部 ({directoryTree.file_count || 0})
                  </Tag.CheckableTag>
                  {directoryTree.children.map(child => {
                    return (
                      <Tag.CheckableTag
                        key={child.path}
                        checked={currentDir === child.path}
                        onChange={() => setCurrentDir(child.path)}
                      >
                        📂 {child.name} ({child.file_count || 0})
                      </Tag.CheckableTag>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* 文件列表表格 */}
            <Spin spinning={loading}>
              <Card size="small" className="shadow-sm" styles={{ body: { padding: 0 } }}>
                <Table
                  columns={columns}
                  dataSource={currentFiles}
                  rowKey="path"
                  pagination={{
                    pageSize: 8,
                    showTotal: (total) => `共 ${total} 个文件`,
                    size: 'small',
                    showSizeChanger: false,
                  }}
                  size="small"
                  rowSelection={{
                    type: 'checkbox',
                    selectedRowKeys: Array.from(selectedKeys),
                    onChange: handleSelectChange,
                  }}
                  onRow={(record) => ({
                    onClick: () => handleRowClick(record),
                    style: { cursor: 'pointer' },
                  })}
                  rowClassName={(record) => (selectedKeys.has(record.path) ? 'bg-blue-50' : '')}
                />
              </Card>
            </Spin>

            {/* 文件详情抽屉 */}
            {selectedFile && detailExpanded && (
              <Card
                size="small"
                title={
                  <div className="flex items-center justify-between w-full pr-4">
                    <span className="font-medium">📄 {selectedFile.name}</span>
                    <Button
                      type="text"
                      size="small"
                      onClick={() => setDetailExpanded(false)}
                    >
                      收起
                    </Button>
                  </div>
                }
                className="shadow-sm"
              >
                <Descriptions column={{ xs: 1, sm: 2 }} size="small" bordered>
                  <Descriptions.Item label="大小">
                    <Tag color="blue">{formatSize(selectedFile.size)}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="类型">
                    <Tag>{selectedFile.type}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="路径" span={2}>
                    <code className="text-xs bg-gray-100 px-2 py-1 rounded break-all block">
                      {selectedFile.path}
                    </code>
                  </Descriptions.Item>
                  <Descriptions.Item label="修改时间">
                    {getRelativeTime(selectedFile.modified_time) !== '-' ? new Date(selectedFile.modified_time).toLocaleString('zh-CN') : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="日期标签">
                    <Tag color="geekblue">{selectedFile.date}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="日志行数" span={2}>
                    {selectedFile.line_count?.toLocaleString() || '-'} 行
                  </Descriptions.Item>
                </Descriptions>

                <Divider style={{ margin: '12px 0' }} />

                <div className="flex gap-2 justify-end">
                  <Button size="small">预览</Button>
                  <Button size="small" type="primary" ghost>下载</Button>
                  <Button size="small" danger ghost icon={<IconTrash size={14} />}>删除此文件</Button>
                </div>
              </Card>
            )}
          </div>

          {/* 右侧：配置控制区 */}
          <div className="xl:col-span-2 space-y-4">
            
            {/* 存储概览 */}
            {diskUsage && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <IconDatabase size={16} />
                    存储概览
                  </span>
                }
                className="shadow-sm"
              >
                <div className="text-center mb-3">
                  <Progress
                    type="circle"
                    percent={Math.round(getSpacePercent())}
                    strokeColor={getProgressColor(getSpacePercent())}
                    size={100}
                    format={(percent) => <span style={{ fontSize: 20, fontWeight: 'bold' }}>{percent}%</span>}
                  />
                </div>

                <Row gutter={[12, 12]}>
                  <Col span={12}>
                    <div className="text-center p-2 bg-gray-50 rounded">
                      <div className="text-xs text-gray-500">总空间</div>
                      <div className="font-medium">{formatSize(diskUsage.total_space || 0)}</div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div className="text-center p-2 bg-blue-50 rounded">
                      <div className="text-xs text-gray-500">已用空间</div>
                      <div className="font-medium text-blue-600">{formatSize(diskUsage.used_space || 0)}</div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div className="text-center p-2 bg-green-50 rounded">
                      <div className="text-xs text-gray-500">剩余空间</div>
                      <div className="font-medium text-green-600">{formatSize(diskUsage.free_space || 0)}</div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div className="text-center p-2 bg-orange-50 rounded">
                      <div className="text-xs text-gray-500">文件总数</div>
                      <div className="font-medium text-orange-600">
                        {directoryTree?.file_count || currentFiles.length || 0} 个
                      </div>
                    </div>
                  </Col>
                </Row>
              </Card>
            )}

            {/* 自动清理策略 */}
            <Card
              size="small"
              title={
                <div className="flex items-center justify-between w-full pr-4">
                  <span className="flex items-center gap-2">
                    <IconSettings size={16} />
                    自动清理策略
                  </span>
                  <Switch
                    size="small"
                    checked={config.enabled}
                    onChange={(checked) => setConfig(prev => ({ ...prev, enabled: checked }))}
                    checkedChildren="开"
                    unCheckedChildren="关"
                  />
                </div>
              }
              className="shadow-sm"
            >
              {config.enabled ? (
                <div className="space-y-4">
                  <div>
                    <div className="text-sm font-medium text-gray-700 mb-2">保留策略</div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-600">保留最近</span>
                      <InputNumber
                        min={1}
                        max={365}
                        size="small"
                        value={config.retention_days}
                        onChange={(value) => setConfig(prev => ({ ...prev, retention_days: value || 30 }))}
                        style={{ width: 80 }}
                        addonAfter="天"
                      />
                      <span className="text-sm text-gray-400">的日志</span>
                    </div>
                  </div>

                  <Divider style={{ margin: '8px 0' }} />

                  <div>
                    <div className="text-sm font-medium text-gray-700 mb-2">空间限制</div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-600">超过</span>
                      <InputNumber
                        min={0}
                        max={1000}
                        size="small"
                        value={config.max_size_gb}
                        onChange={(value) => setConfig(prev => ({ ...prev, max_size_gb: value || 0 }))}
                        style={{ width: 80 }}
                        addonAfter="GB"
                      />
                      <span className="text-sm text-gray-400">时自动清理</span>
                    </div>
                    {config.max_size_gb > 0 && (
                      <Progress
                        percent={Math.min((config.space_used / (config.max_size_gb * 1024)) * 100, 100)}
                        status={config.space_used > config.max_size_gb * 512 ? 'exception' : 'active'}
                        size="small"
                        className="mt-2"
                      />
                    )}
                  </div>

                  <Divider style={{ margin: '8px 0' }} />

                  <div>
                    <div className="text-sm font-medium text-gray-700 mb-2">执行计划</div>
                    <Radio.Group
                      size="small"
                      value={config.cleanup_schedule}
                      onChange={(e) => setConfig(prev => ({ ...prev, cleanup_schedule: e.target.value }))}
                      optionType="button"
                      buttonStyle="solid"
                    >
                      <Radio.Button value="daily">每天</Radio.Button>
                      <Radio.Button value="weekly">每周</Radio.Button>
                      <Radio.Button value="monthly">每月</Radio.Button>
                    </Radio.Group>
                    
                    {config.last_cleanup_time && (
                      <div className="text-xs text-gray-500 mt-2">
                        上次执行: {new Date(config.last_cleanup_time).toLocaleString('zh-CN')}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-4 text-gray-400">
                  <IconSettings size={32} className="mx-auto mb-2 opacity-30" />
                  <p className="text-xs">自动清理已禁用</p>
                  <p className="text-xs mt-1 text-gray-300">开启上方开关以启用配置选项</p>
                </div>
              )}
            </Card>

            {/* 各类型统计 */}
            {diskUsage?.log_types && Object.keys(diskUsage.log_types).length > 0 && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <IconChartPie size={16} />
                    各类型统计
                  </span>
                }
                className="shadow-sm"
              >
                <div className="space-y-3">
                  {Object.entries(diskUsage.log_types).map(([type, info]: [string, any]) => {
                    const totalBytes = info?.total_size || 0;
                    const maxBytes = Math.max(...Object.values(diskUsage.log_types).map((i: any) => i?.total_size || 0), 1);
                    const percent = (totalBytes / maxBytes) * 100;
                    
                    const colors: Record<string, string> = {
                      application: '#1890ff',
                      system: '#52c41a',
                      api: '#fa8c16',
                    };
                    
                    return (
                      <div key={type}>
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-sm">
                            <Tag size="small" color={colors[type] || 'default'}>{type}</Tag>
                          </span>
                          <span className="text-xs text-gray-500">
                            {(totalBytes / 1024 / 1024).toFixed(2)} MB · {info?.count || 0} 个
                          </span>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${percent}%`,
                              backgroundColor: colors[type] || '#1890ff',
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* 操作按钮区 */}
            <Card size="small" className="shadow-sm">
              <div className="flex gap-2">
                <Button
                  type="primary"
                  size="small"
                  icon={<IconDeviceFloppy size={14} />}
                  onClick={handleSaveConfig}
                  loading={saving}
                  disabled={!isDirty}
                  block
                >
                  保存配置
                </Button>
                <Button
                  size="small"
                  icon={<IconRotateDot size={14} />}
                  onClick={handleResetConfig}
                  block
                >
                  重置
                </Button>
              </div>
              
              {!isDirty && originalConfig && (
                <div className="mt-2 text-center text-xs text-gray-400">
                  ✓ 配置已是最新状态
                </div>
              )}
            </Card>

            {/* 最近操作结果 */}
            {lastResult && (
              <Alert
                type={lastResult.errors.length === 0 ? 'success' : 'warning'}
                showIcon
                closable
                onClose={() => setLastResult(null)}
                message={
                  lastResult.errors.length === 0 ?
                    `✅ 成功删除 ${lastResult.deleted_count} 个文件` :
                    `⚠️ 完成：${lastResult.deleted_count} 成功，${lastResult.errors.length} 失败`
                }
                description={`释放空间: ${formatSize(lastResult.freed_space)}`}
                className="rounded"
              />
            )}
          </div>
        </div>
      </main>

      {/* 删除确认对话框 */}
      <Modal
        title={
          <span className="flex items-center gap-2">
            <IconAlertTriangle size={20} className="text-orange-500" />
            批量删除确认
          </span>
        }
        open={deleteModalVisible}
        onCancel={() => {
          setDeleteModalVisible(false);
          setRiskConfirmed(false);
        }}
        footer={[
          <Button key="cancel" onClick={() => { setDeleteModalVisible(false); setRiskConfirmed(false); }}>
            取消
          </Button>,
          <Button
            key="delete"
            type="primary"
            danger
            loading={deleting}
            disabled={!riskConfirmed}
            onClick={handleDeleteSelected}
          >
            确认删除
          </Button>,
        ]}
        width={480}
      >
        <div className="space-y-4">
          <Alert type="warning" showIcon message="此操作不可撤销" description="删除的文件将无法恢复，请谨慎操作。" />

          <div>
            <p className="font-medium mb-2">待删除文件列表：</p>
            <div className="max-h-32 overflow-y-auto bg-gray-50 rounded p-2">
              {currentFiles
                .filter(file => selectedKeys.has(file.path))
                .map(file => (
                  <div key={file.path} className="flex justify-between py-1 px-2 hover:bg-gray-100 rounded text-sm">
                    <span className="truncate max-w-[240px] font-mono">{file.name}</span>
                    <Tag size="small" color="red">{formatSize(file.size)}</Tag>
                  </div>
                ))}
            </div>
          </div>

          <div className="bg-red-50 border border-red-200 p-2 rounded">
            <p className="text-sm">
              总计：<span className="font-bold text-red-600">{formatSize(stats.totalSize)}</span>
              {' '}(<span className="font-bold text-red-600">{stats.count}</span> 个文件)
            </p>
          </div>

          <div className="flex items-start gap-2">
            <input
              type="checkbox"
              id="risk-confirm"
              checked={riskConfirmed}
              onChange={(e) => setRiskConfirmed(e.target.checked)}
              className="mt-0.5"
            />
            <label htmlFor="risk-confirm" className="text-sm text-gray-600 cursor-pointer">
              我已了解此操作的风险，确认永久删除以上文件
            </label>
          </div>

          {deleting && (
            <div className="text-center py-2">
              <Progress percent={50} status="active" showInfo={false} />
              <p className="text-sm text-gray-500 mt-1">正在删除...</p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}

export default LogSettingsUnified;
