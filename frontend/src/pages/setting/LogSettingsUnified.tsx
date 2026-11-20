/**
 * 日志设置统一页面 - 与项目风格统一
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  Button,
  Input,
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
  App,
  Divider,
  Space,
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
import { useTranslation } from 'react-i18next';
import type { LogDirectoryNode, LogFileInfo, LogAutoCleanupConfig, LogDiskUsage, LogTypeInfo, CleanupResult } from './types';
import DataTable from '@/components/ui/DataTable';
import { useQuantColors } from '@/utils/colors';

interface LogSettingsUnifiedProps {
  onClose?: () => void;
}

function LogSettingsUnified({ onClose }: LogSettingsUnifiedProps) {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const qcColors = useQuantColors();
  // ========== 状态定义 ==========
  const [directoryTree, setDirectoryTree] = useState<LogDirectoryNode | null>(null);
  const [diskUsage, setDiskUsage] = useState<LogDiskUsage | null>(null);
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

  // 分页状态
  const [pageSize, setPageSize] = useState(8);
  const [page, setPage] = useState(1);
  const [selectAllPages, setSelectAllPages] = useState(false);

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
      message.error(t('log_load_data_failed'));
      console.error('Failed to load log data:', error);
    } finally {
      setLoading(false);
    }
  }, [currentDir, message]);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // 过滤条件变化时页码归 1（§6.6 过滤与分页联动）
  useEffect(() => {
    setPage(1);
  }, [searchText, currentDir, sortOrder]);

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
      console.error('Failed to get file detail:', error);
    }
  };

  const handleSaveConfig = async () => {
    try {
      setSaving(true);
      await systemApi.updateAutoCleanupConfig(config);
      setOriginalConfig({ ...config });
      message.success(t('config_saved'));
    } catch {
      message.error(t('log_save_config_failed'));
    } finally {
      setSaving(false);
    }
  };

  const handleResetConfig = () => {
    modal.confirm({
      title: t('log_confirm_reset'),
      content: t('log_reset_confirm_content'),
      okText: t('log_confirm_reset'),
      cancelText: t('cancel'),
      onOk: () => {
        if (originalConfig) {
          setConfig({ ...originalConfig });
          message.info(t('log_config_restored'));
        }
      },
    });
  };

  // 导出选中日志文件为ZIP
  const handleExportLogs = async () => {
    if (selectedKeys.size === 0) {
      message.warning(t('log_select_files_first'));
      return;
    }

    try {
      const filePaths = Array.from(selectedKeys);
      const blob = await systemApi.downloadLogFilesBatch(filePaths);

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `log_files_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.zip`;
      a.click();
      URL.revokeObjectURL(url);

      message.success(t('log_export_success', { count: filePaths.length }));
    } catch (error) {
      console.error('Failed to export log files:', error);
      message.error(t('log_export_failed'));
    }
  };

  // 全选/取消全选（跨页）
  const handleSelectAllPages = (checked: boolean) => {
    setSelectAllPages(checked);
    if (checked) {
      setSelectedKeys(new Set(currentFiles.map(f => f.path)));
    } else {
      setSelectedKeys(new Set());
    }
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
        message.success(t('log_delete_success_count', { count: result.deleted_count }));
      } else {
        message.warning(t('log_delete_partial', { success: result.deleted_count, failed: result.errors.length }));
      }
    } catch {
      message.error(t('delete_failed'));
    } finally {
      setDeleting(false);
    }
  };

  // ========== 表格列定义 ==========
  const columns = [
    {
      title: t('log_file_name'),
      dataIndex: 'name',
      render: (name: string) => (
        <div className="flex items-center gap-2">
          <IconFile size={16} style={{ color: 'var(--qc-info)' }} />
          <span className="font-mono text-sm">{name}</span>
        </div>
      ),
    },
    {
      title: t('log_size'),
      dataIndex: 'size',
      width: 100,
      sorter: true,
      sortOrder,
      render: (size: number) => (
        <span className="qc-chip quiet font-mono">{formatSize(size)}</span>
      ),
    },
    {
      title: t('type'),
      dataIndex: 'type',
      width: 90,
      render: (type: string) => {
        const cls: Record<string, string> = {
          application: 'qc-chip info',
          system: 'qc-chip ok',
          api: 'qc-chip warn',
        };
        return <span className={cls[type] || 'qc-chip quiet'}>{type}</span>;
      },
    },
    {
      title: t('log_modified_time'),
      dataIndex: 'modified_time',
      width: 160,
      render: (time: string) => (
        <span className="text-xs" style={{ color: 'var(--qc-text-secondary)' }}>
          {getRelativeTime(time)}
        </span>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 60,
      render: (_: unknown, record: LogFileInfo) => (
        <Button
          type="link"
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            handleRowClick(record);
          }}
        >
          {t('details')}
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
      // 兼容多种时间格式
      if (!timeStr || timeStr === '-' || timeStr === 'None' || timeStr === 'null') {
        return '-';
      }

      // 处理 ISO 格式（带或不带时区）
      const time = new Date(timeStr);

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

      if (diffMins < 1) return t('log_time_just_now');
      if (diffMins < 60) return t('log_time_minutes_ago', { count: diffMins });
      if (diffHours < 24) return t('log_time_hours_ago', { count: diffHours });
      if (diffDays < 7) return t('log_time_days_ago', { count: diffDays });
      return time.toLocaleDateString('zh-CN');
    } catch {
      return '-';
    }
  }

  function getProgressColor(percent: number): string {
    if (percent > 85) return qcColors.negative;
    if (percent > 70) return qcColors.warning;
    return qcColors.positive;
  }

  // ========== 渲染 ==========
  return (
    <div className="log-settings-unified">
      {/* 主体内容区 */}
      <main className="p-5">
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">
          {/* 左侧：文件管理区 */}
          <div className="xl:col-span-3">
            <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            {/* 筛选工具栏 */}
            <Card size="small" className="qc-card">
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Input
                    placeholder={t('log_search_placeholder')}
                    prefix={<IconSearch size={16} style={{ color: 'var(--qc-text-quaternary)' }} />}
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    allowClear
                    style={{ flex: 1, minWidth: 200 }}
                  />
                  <Tooltip title={t('log_sort_tooltip', { order: sortOrder === 'descend' ? t('log_sort_desc') : t('log_sort_asc') })}>
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
                    {t('refresh')}
                  </Button>
                  <Tooltip title={t('log_export_tooltip')}>
                    <Button
                      icon={<IconDownload size={16} />}
                      onClick={handleExportLogs}
                      disabled={selectedKeys.size === 0}
                    >
                      {t('export')}
                    </Button>
                  </Tooltip>
                  {onClose && (
                    <Button onClick={onClose}>
                      {t('back')}
                    </Button>
                  )}
                </div>

                {selectedKeys.size > 0 && (
                  <div
                    className="flex items-center justify-between p-2 rounded"
                    style={{
                      background: 'color-mix(in srgb, var(--qc-info) 8%, transparent)',
                      border: '1px solid color-mix(in srgb, var(--qc-info) 40%, transparent)',
                    }}
                  >
                    <span className="text-sm" style={{ color: 'var(--qc-text)' }}>
                      {t('log_selected_prefix')} <strong>{stats.count}</strong> {t('log_selected_middle')} <strong style={{ color: 'var(--qc-info)' }}>{formatSize(stats.totalSize)}</strong>{t('log_selected_suffix')}
                    </span>
                    <Button
                      danger
                      size="small"
                      icon={<IconTrash size={14} />}
                      onClick={() => setDeleteModalVisible(true)}
                    >
                      {t('log_batch_delete')}
                    </Button>
                  </div>
                )}
              </div>
            </Card>

            {/* 目录标签组 */}
            {directoryTree && (
              <Card size="small" className="qc-card">
                <div className="flex gap-2 flex-wrap">
                  <Tag.CheckableTag
                    checked={currentDir === directoryTree.path}
                    onChange={() => setCurrentDir(directoryTree.path)}
                  >
                    {t('log_dir_all', { count: directoryTree.file_count || 0 })}
                  </Tag.CheckableTag>
                  {directoryTree.children.map(child => {
                    return (
                      <Tag.CheckableTag
                        key={child.path}
                        checked={currentDir === child.path}
                        onChange={() => setCurrentDir(child.path)}
                      >
                        {t('log_dir_item', { name: child.name, count: child.file_count || 0 })}
                      </Tag.CheckableTag>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* 文件列表表格 */}
            <Spin spinning={loading}>
              <Card size="small" className="qc-card" styles={{ body: { padding: 0 } }}>
                <div
                  className="flex items-center gap-2 p-2 border-b flex-wrap"
                  style={{ background: 'var(--qc-surface-raised)', borderBottom: '1px solid var(--qc-border)' }}
                >
                  <span className="text-sm" style={{ color: 'var(--qc-text-secondary)' }}>{t('log_select_all_label')}</span>
                  <Switch
                    size="small"
                    checked={selectAllPages}
                    onChange={handleSelectAllPages}
                    checkedChildren={t('all')}
                    unCheckedChildren={t('none')}
                  />
                  {selectedKeys.size > 0 && (
                    <span className="text-xs" style={{ color: 'var(--qc-info)' }}>
                      {t('log_selected_count', { selected: selectedKeys.size, total: currentFiles.length })}
                    </span>
                  )}
                </div>
                <DataTable
                  columns={columns}
                  dataSource={currentFiles}
                  rowKey="path"
                  scroll={{ x: 'max-content' }}
                  pagination={{
                    pageSize,
                    current: page,
                    total: currentFiles.length,
                    showSizeChanger: true,
                    pageSizeOptions: [8, 15, 25, 50, 100],
                    onChange: (nextPage, size) => {
                      setPage(nextPage);
                      if (size !== pageSize) {
                        setPageSize(size);
                        setSelectAllPages(false);
                      }
                    },
                  }}
                  rowSelection={{
                    type: 'checkbox',
                    selectedRowKeys: Array.from(selectedKeys),
                    onChange: handleSelectChange,
                  }}
                  onRow={(record) => ({
                    onClick: () => handleRowClick(record),
                    style: { cursor: 'pointer' },
                  })}
                />
              </Card>
            </Spin>

            {/* 文件详情抽屉 */}
            {selectedFile && detailExpanded && (
              <Card
                size="small"
                title={
                  <div className="flex items-center justify-between w-full pr-4">
                    <span className="font-medium truncate font-mono">📄 {selectedFile.name}</span>
                    <Button
                      type="text"
                      size="small"
                      onClick={() => setDetailExpanded(false)}
                    >
                      {t('collapse')}
                    </Button>
                  </div>
                }
                className="qc-card"
              >
                <Descriptions column={2} size="small" bordered styles={{ label: { color: 'var(--qc-text-quaternary)', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 11, letterSpacing: '.02em' }, content: { fontSize: 12 } }}>
                  <Descriptions.Item label={t('log_size')}>
                    <span className="qc-chip quiet font-mono">{formatSize(selectedFile.size)}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('type')}>
                    <span className="qc-chip quiet">{selectedFile.type}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('log_path')} span={2}>
                    <code
                      className="text-xs px-2 py-1 rounded break-all block"
                      style={{ background: 'var(--qc-surface-raised)', color: 'var(--qc-text-secondary)' }}
                    >
                      {selectedFile.path}
                    </code>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('log_modified_time')}>
                    {getRelativeTime(selectedFile.modified_time) !== '-' ? new Date(selectedFile.modified_time).toLocaleString('zh-CN') : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('log_date_label')}>
                    <span className="qc-chip quiet font-mono">{selectedFile.date}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('log_line_count')} span={2}>
                    {/* i18next 的 count 是复数保留参数必须为 number；此处传字符串走下方占位符 */}
                    {t('log_lines_value', { lines: selectedFile.line_count?.toLocaleString() || '-' })}
                  </Descriptions.Item>
                </Descriptions>

                <Divider style={{ margin: '12px 0' }} />

                <div className="flex gap-2 justify-end">
                  <Button size="small">{t('preview')}</Button>
                  <Button size="small" type="primary" ghost>{t('log_download')}</Button>
                  <Button size="small" danger ghost icon={<IconTrash size={14} />}>{t('log_delete_this_file')}</Button>
                </div>
              </Card>
            )}
            </Space>
          </div>

          {/* 右侧：配置控制区 */}
          <div className="xl:col-span-2">
            <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            
            {/* 存储概览 */}
            {diskUsage && (
              <Card
                size="small"
                title={
                  <span className="flex items-center gap-2">
                    <IconDatabase size={16} />
                    {t('log_storage_overview')}
                  </span>
                }
                className="qc-card"
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
                    <div className="text-center p-2 rounded" style={{ background: 'var(--qc-surface-raised)' }}>
                      <div className="text-xs" style={{ color: 'var(--qc-text-quaternary)' }}>{t('log_total_space')}</div>
                      <div className="font-medium font-mono">{formatSize(diskUsage.total_space || 0)}</div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div className="text-center p-2 rounded" style={{ background: 'var(--qc-surface-raised)' }}>
                      <div className="text-xs" style={{ color: 'var(--qc-text-quaternary)' }}>{t('log_used_space')}</div>
                      <div className="font-medium font-mono" style={{ color: 'var(--qc-info)' }}>{formatSize(diskUsage.used_space || 0)}</div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div className="text-center p-2 rounded" style={{ background: 'var(--qc-surface-raised)' }}>
                      <div className="text-xs" style={{ color: 'var(--qc-text-quaternary)' }}>{t('log_free_space')}</div>
                      <div className="font-medium font-mono" style={{ color: 'var(--qc-success)' }}>{formatSize(diskUsage.free_space || 0)}</div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div className="text-center p-2 rounded" style={{ background: 'var(--qc-surface-raised)' }}>
                      <div className="text-xs" style={{ color: 'var(--qc-text-quaternary)' }}>{t('log_file_total')}</div>
                      <div className="font-medium font-mono" style={{ color: 'var(--qc-warning)' }}>
                        {t('log_count_files', { count: directoryTree?.file_count || currentFiles.length || 0 })}
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
                    {t('log_auto_cleanup_title')}
                  </span>
                  <Switch
                    size="small"
                    checked={config.enabled}
                    onChange={(checked) => setConfig(prev => ({ ...prev, enabled: checked }))}
                    checkedChildren={t('settings_switch_on')}
                    unCheckedChildren={t('settings_switch_off')}
                  />
                </div>
              }
              className="qc-card"
            >
              {config.enabled ? (
                <div className="space-y-6">
                  <div>
                    <div className="mb-2 font-medium" style={{ fontSize: 13, color: 'var(--qc-text)' }}>{t('log_retention_policy')}</div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm" style={{ color: 'var(--qc-text-secondary)' }}>{t('log_retention_prefix')}</span>
                      <Space.Compact size="small">
                        <InputNumber
                          min={1}
                          max={365}
                          size="small"
                          value={config.retention_days}
                          onChange={(value) => setConfig(prev => ({ ...prev, retention_days: value || 30 }))}
                          style={{ width: 80 }}
                        />
                        <Input
                          readOnly
                          value={t('log_unit_day')}
                          className="w-10 text-center"
                          aria-label={t('log_unit_day')}
                        />
                      </Space.Compact>
                      <span className="text-sm" style={{ color: 'var(--qc-text-quaternary)' }}>{t('log_retention_suffix')}</span>
                    </div>
                  </div>

                  <Divider style={{ margin: '16px 0' }} />

                  <div>
                    <div className="mb-2 font-medium" style={{ fontSize: 13, color: 'var(--qc-text)' }}>{t('log_space_limit')}</div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm" style={{ color: 'var(--qc-text-secondary)' }}>{t('log_space_limit_prefix')}</span>
                      <Space.Compact size="small">
                        <InputNumber
                          min={0}
                          max={1000}
                          size="small"
                          value={config.max_size_gb}
                          onChange={(value) => setConfig(prev => ({ ...prev, max_size_gb: value || 0 }))}
                          style={{ width: 80 }}
                        />
                        <Input
                          readOnly
                          value="GB"
                          className="w-10 text-center"
                          aria-label="GB"
                        />
                      </Space.Compact>
                      <span className="text-sm" style={{ color: 'var(--qc-text-quaternary)' }}>{t('log_space_limit_suffix')}</span>
                    </div>
                    {config.max_size_gb > 0 && (
                      <Progress
                        percent={Math.min((config.space_used / (config.max_size_gb * 1024)) * 100, 100)}
                        status={config.space_used > config.max_size_gb * 512 ? 'exception' : 'active'}
                        size="small"
                        className="mt-3"
                      />
                    )}
                  </div>

                  <Divider style={{ margin: '16px 0' }} />

                  <div>
                    <div className="mb-2 font-medium" style={{ fontSize: 13, color: 'var(--qc-text)' }}>{t('log_schedule_title')}</div>
                    <Radio.Group
                      size="small"
                      value={config.cleanup_schedule}
                      onChange={(e) => setConfig(prev => ({ ...prev, cleanup_schedule: e.target.value }))}
                      optionType="button"
                      buttonStyle="solid"
                    >
                      <Radio.Button value="daily">{t('log_schedule_daily')}</Radio.Button>
                      <Radio.Button value="weekly">{t('log_schedule_weekly')}</Radio.Button>
                      <Radio.Button value="monthly">{t('log_schedule_monthly')}</Radio.Button>
                    </Radio.Group>
                    
                    {config.last_cleanup_time && (
                      <div className="mt-3 text-xs" style={{ color: 'var(--qc-text-quaternary)' }}>
                        {t('log_last_run', { time: new Date(config.last_cleanup_time).toLocaleString('zh-CN') })}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8" style={{ color: 'var(--qc-text-quaternary)' }}>
                  <IconSettings size={32} className="mx-auto mb-2 opacity-30" />
                  <p className="text-xs">{t('log_cleanup_disabled')}</p>
                  <p className="mt-1 text-xs" style={{ color: 'color-mix(in srgb, var(--qc-text-quaternary) 78%, transparent)' }}>{t('log_cleanup_disabled_hint')}</p>
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
                    {t('log_type_stats_title')}
                  </span>
                }
                className="qc-card"
              >
                <div className="space-y-4">
                  {Object.entries(diskUsage.log_types).map(([type, info]: [string, LogTypeInfo]) => {
                    const totalBytes = info.total_size || 0;
                    const maxBytes = Math.max(...Object.values(diskUsage.log_types).map((i: LogTypeInfo) => i.total_size || 0), 1);
                    const percent = (totalBytes / maxBytes) * 100;

                    const colors: Record<string, string> = {
                      application: qcColors.info,
                      system: qcColors.positive,
                      api: qcColors.warning,
                    };

                    return (
                      <div key={type}>
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-sm">
                            <span className={type === 'application' ? 'qc-chip info' : type === 'system' ? 'qc-chip ok' : type === 'api' ? 'qc-chip warn' : 'qc-chip quiet'}>{type}</span>
                          </span>
                          <span className="text-xs font-mono" style={{ color: 'var(--qc-text-quaternary)' }}>
                            {t('log_type_stats_item', { size: (totalBytes / 1024 / 1024).toFixed(2), count: info?.count || 0 })}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--qc-surface-raised)' }}>
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${percent}%`,
                              backgroundColor: colors[type] || qcColors.info,
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
            <Card size="small" className="qc-card">
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
                  {t('log_save_config')}
                </Button>
                <Button
                  size="small"
                  icon={<IconRotateDot size={14} />}
                  onClick={handleResetConfig}
                  block
                >
                  {t('reset')}
                </Button>
              </div>
              
              {!isDirty && originalConfig && (
                <div className="mt-2 text-center text-xs" style={{ color: 'var(--qc-text-quaternary)' }}>
                  {t('log_config_up_to_date')}
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
                title={
                  lastResult.errors.length === 0 ?
                    t('log_delete_success_alert', { count: lastResult.deleted_count }) :
                    t('log_delete_partial_alert', { success: lastResult.deleted_count, failed: lastResult.errors.length })
                }
                description={t('log_freed_space', { size: formatSize(lastResult.freed_space) })}
                className="rounded"
              />
            )}
            </Space>
          </div>
        </div>
      </main>

      {/* 删除确认对话框 */}
      <Modal
        className="qc-modal"
        title={
          <span className="flex items-center gap-2">
            <IconAlertTriangle size={20} style={{ color: 'var(--qc-warning)' }} />
            {t('log_batch_delete_confirm')}
          </span>
        }
        open={deleteModalVisible}
        onCancel={() => {
          setDeleteModalVisible(false);
          setRiskConfirmed(false);
        }}
        footer={[
          <Button key="cancel" onClick={() => { setDeleteModalVisible(false); setRiskConfirmed(false); }}>
            {t('cancel')}
          </Button>,
          <Button
            key="delete"
            type="primary"
            danger
            loading={deleting}
            disabled={!riskConfirmed}
            onClick={handleDeleteSelected}
          >
            {t('confirm_delete')}
          </Button>,
        ]}
        width={480}
      >
        <div className="space-y-4">
          <Alert type="warning" showIcon title={t('log_irreversible')} description={t('log_irreversible_desc')} />

          <div>
            <p className="font-medium mb-2">{t('log_files_to_delete')}</p>
            <div className="max-h-32 overflow-y-auto rounded p-2" style={{ background: 'var(--qc-surface-raised)' }}>
              {currentFiles
                .filter(file => selectedKeys.has(file.path))
                .map(file => (
                  <div key={file.path} className="flex justify-between py-1 px-2 hover:bg-[var(--qc-surface-hover)] rounded text-sm">
                    <span className="truncate max-w-[240px] font-mono">{file.name}</span>
                    <span className="qc-chip quiet font-mono">{formatSize(file.size)}</span>
                  </div>
                ))}
            </div>
          </div>

          <div
            className="p-2 rounded"
            style={{
              background: 'var(--qc-error-soft-bg)',
              border: '1px solid color-mix(in srgb, var(--qc-error) 40%, transparent)',
            }}
          >
            <p className="text-sm">
              {t('log_delete_total_label')}<span className="font-bold" style={{ color: 'var(--qc-error)' }}>{formatSize(stats.totalSize)}</span>
              {' '}(<span className="font-bold" style={{ color: 'var(--qc-error)' }}>{stats.count}</span> {t('log_files_suffix')})
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
            <label htmlFor="risk-confirm" className="text-sm cursor-pointer" style={{ color: 'var(--qc-text-secondary)' }}>
              {t('log_risk_confirm_label')}
            </label>
          </div>

          {deleting && (
            <div className="text-center py-2">
              <Progress percent={50} status="active" showInfo={false} />
              <p className="mt-1 text-sm" style={{ color: 'var(--qc-text-secondary)' }}>{t('log_deleting')}</p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}

export default LogSettingsUnified;
