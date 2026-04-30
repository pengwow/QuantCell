/**
 * LogCleanupManager - 日志清理管理器
 * 提供单个/批量删除日志文件的功能，带二次确认机制
 */
import { useState, useEffect, useCallback } from 'react';
import { App } from 'antd';
import {
  Table,
  Checkbox,
  Button,
  Modal,
  Progress,
  Space,
  Tag,
  Alert,
  Popconfirm,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  IconTrash,
  IconRefresh,
  IconCheck,
  IconX,
  IconAlertTriangle,
} from '@tabler/icons-react';
import { systemApi } from '../../api';
import type { LogFileInfo, CleanupResult, LogDirectoryNode } from './types';

const LogCleanupManager: React.FC = () => {
  const { message: antMessage } = App.useApp();
  const [loading, setLoading] = useState<boolean>(false);
  const [files, setFiles] = useState<LogFileInfo[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [deleteModalVisible, setDeleteModalVisible] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteProgress, setDeleteProgress] = useState(0);
  const [riskConfirmed, setRiskConfirmed] = useState(false);
  const [lastResult, setLastResult] = useState<CleanupResult | null>(null);

  // 加载文件列表
  const loadFiles = useCallback(async () => {
    try {
      setLoading(true);
      const data: LogDirectoryNode = await systemApi.getLogDirectory();

      // 展平所有文件
      const allFiles: LogFileInfo[] = [];
      data.children?.forEach(child => {
        allFiles.push(...child.files);
      });

      setFiles(allFiles.sort((a, b) => b.size - a.size));
    } catch (error) {
      console.error('加载文件列表失败:', error);
      antMessage.error('无法加载日志文件列表');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  // 全选/取消全选
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedKeys(new Set(files.map(f => f.path)));
    } else {
      setSelectedKeys(new Set());
    }
  };

  // 选择单个文件
  const handleSelectFile = (path: string, checked: boolean) => {
    setSelectedKeys(prev => {
      const newSet = new Set(prev);
      if (checked) {
        newSet.add(path);
      } else {
        newSet.delete(path);
      }
      return newSet;
    });
  };

  // 计算选中文件的统计信息
  const getSelectedStats = () => {
    const selected = files.filter(f => selectedKeys.has(f.path));
    return {
      count: selected.length,
      totalSize: selected.reduce((sum, f) => sum + f.size, 0),
    };
  };

  // 格式化大小
  const formatSize = (bytes: number): string => {
    for (const unit of ['B', 'KB', 'MB', 'GB', 'TB']) {
      if (Math.abs(bytes) < 1024) {
        return `${bytes.toFixed(2)} ${unit}`;
      }
      bytes /= 1024;
    }
    return `${bytes.toFixed(2)} PB`;
  };

  // 执行删除操作
  const executeDelete = async () => {
    try {
      setDeleting(true);
      setDeleteProgress(0);

      const selectedPaths = Array.from(selectedKeys);
      const total = selectedPaths.length;

      // 模拟进度（实际是批量删除API调用）
      const result: CleanupResult = await systemApi.deleteLogFilesBatch(selectedPaths);

      // 更新进度
      setDeleteProgress(100);

      setTimeout(() => {
        setLastResult(result);
        setDeleting(false);
        setDeleteModalVisible(false);
        setSelectedKeys(new Set());
        setRiskConfirmed(false);

        if (result.success && result.errors.length === 0) {
          antMessage.success(`成功删除 ${result.deleted_count} 个文件，释放 ${formatSize(result.freed_space)}`);
        } else if (result.success) {
          antMessage.warning(
            `删除完成：${result.deleted_count} 成功，${result.errors.length} 失败`
          );
        } else {
          antMessage.error('删除过程中出现错误');
        }

        // 刷新列表
        loadFiles();
      }, 500);

    } catch (error) {
      console.error('删除失败:', error);
      antMessage.error('删除失败，请重试');
      setDeleting(false);
    }
  };

  // 表格列定义
  const columns: ColumnsType<LogFileInfo> = [
    {
      title: '',
      key: 'select',
      width: 50,
      render: (_: any, record: LogFileInfo) => (
        <Checkbox
          checked={selectedKeys.has(record.path)}
          onChange={(e) => handleSelectFile(record.path, e.target.checked)}
        />
      ),
    },
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => (
        <span className="font-mono text-sm">{text}</span>
      ),
    },
    {
      title: '类型',
      dataIndex: 'log_type',
      key: 'log_type',
      width: 120,
      render: (type: string) => (
        <Tag color="geekblue">{type || '-'}</Tag>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size_formatted',
      key: 'size',
      width: 120,
      sorter: (a, b) => a.size - b.size,
      render: (size: string) => (
        <Tag color={parseInt(size) > 1048576 ? 'red' : 'blue'}>
          {size}
        </Tag>
      ),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_time',
      key: 'modified_time',
      width: 180,
      render: (time: string) => (
        <span className="text-xs text-gray-600">
          {new Date(time).toLocaleString('zh-CN')}
        </span>
      ),
    },
  ];

  const stats = getSelectedStats();

  return (
    <div className="p-6">
      {/* 结果提示 */}
      {lastResult && (
        <Alert
          type={lastResult.errors.length === 0 ? 'success' : 'warning'}
          showIcon
          closable
          onClose={() => setLastResult(null)}
          message={
            lastResult.errors.length === 0 ?
              `✅ 上次操作：成功删除 ${lastResult.deleted_count} 个文件，释放 ${formatSize(lastResult.freed_space)}` :
              `⚠️ 上次操作：${lastResult.deleted_count} 成功，${lastResult.errors.length} 失败`
          }
          className="mb-4"
        />
      )}

      {/* 工具栏 */}
      <div className="flex items-center justify-between mb-4">
        <Space>
          <Checkbox
            indeterminate={selectedKeys.size > 0 && selectedKeys.size < files.length}
            checked={selectedKeys.size === files.length && files.length > 0}
            onChange={(e) => handleSelectAll(e.target.checked)}
          >
            全选
          </Checkbox>

          {selectedKeys.size > 0 && (
            <Tag color="blue">
              已选: {stats.count} 个文件 ({formatSize(stats.totalSize)})
            </Tag>
          )}
        </Space>

        <Space>
          <Button
            icon={<IconRefresh size={16} />}
            onClick={loadFiles}
            loading={loading}
          >
            刷新
          </Button>

          <Button
            type="primary"
            danger
            icon={<IconTrash size={16} />}
            disabled={selectedKeys.size === 0}
            onClick={() => setDeleteModalVisible(true)}
          >
            批量删除所选
          </Button>
        </Space>
      </div>

      {/* 文件表格 */}
      <Table
        columns={columns}
        dataSource={files}
        rowKey="path"
        loading={loading}
        pagination={{
          pageSize: 15,
          showTotal: (total) => `共 ${total} 个文件`,
          size: 'small',
        }}
        size="middle"
        rowClassName={record =>
          selectedKeys.has(record.path) ? 'bg-blue-50' : ''
        }
      />

      {/* 确认删除对话框 */}
      <Modal
        title={
          <span className="flex items-center gap-2">
            <IconAlertTriangle size={20} className="text-orange-500" />
            批量删除确认
          </span>
        }
        open={deleteModalVisible}
        onCancel={() => {
          if (!deleting) {
            setDeleteModalVisible(false);
            setRiskConfirmed(false);
          }
        }}
        footer={[
          <Button
            key="cancel"
            onClick={() => {
              setDeleteModalVisible(false);
              setRiskConfirmed(false);
            }}
            disabled={deleting}
          >
            取消
          </Button>,
          <Button
            key="confirm"
            type="primary"
            danger
            icon={<IconTrash size={16} />}
            loading={deleting}
            disabled={!riskConfirmed || deleting}
            onClick={executeDelete}
          >
            {deleting ? '删除中...' : '确认全部删除'}
          </Button>,
        ]}
        width={600}
      >
        {/* 警告信息 */}
        <Alert
          type="warning"
          showIcon
          icon={<IconAlertTriangle />}
          message="此操作不可撤销！"
          description="删除后数据将永久丢失，请谨慎操作"
          className="mb-4"
        />

        {/* 删除项汇总 */}
        <div className="bg-gray-50 p-4 rounded-md mb-4">
          <p className="font-semibold mb-2">即将删除以下文件：</p>
          <div className="max-h-40 overflow-y-auto space-y-1">
            {Array.from(selectedKeys).slice(0, 10).map(path => {
              const file = files.find(f => f.path === path);
              return file ? (
                <div key={path} className="flex justify-between text-sm">
                  <span className="truncate mr-4">{file.name}</span>
                  <Tag color="red" className="ml-2">{file.size_formatted}</Tag>
                </div>
              ) : null;
            })}
            {selectedKeys.size > 10 && (
              <p className="text-sm text-gray-500 text-center">
                ... 还有 {selectedKeys.size - 10} 个文件
              </p>
            )}
          </div>
        </div>

        {/* 统计信息 */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="text-center p-3 bg-red-50 rounded-md">
            <p className="text-sm text-gray-600">总计释放</p>
            <p className="text-xl font-bold text-red-600">
              {formatSize(stats.totalSize)}
            </p>
          </div>
          <div className="text-center p-3 bg-blue-50 rounded-md">
            <p className="text-sm text-gray-600">删除数量</p>
            <p className="text-xl font-bold text-blue-600">
              {stats.count} 个文件
            </p>
          </div>
        </div>

        {/* 风险确认 */}
        <label className="flex items-start gap-2 cursor-pointer">
          <Checkbox
            checked={riskConfirmed}
            onChange={(e) => setRiskConfirmed(e.target.checked)}
            disabled={deleting}
          />
          <span className="text-sm text-gray-700">
            我已了解风险，确认要永久删除以上 {stats.count} 个日志文件，
            总计释放 {formatSize(stats.totalSize)} 空间
          </span>
        </label>

        {/* 进度条 */}
        {deleting && (
          <div className="mt-4">
            <Progress
              percent={deleteProgress}
              status="active"
              strokeColor={{
                '0%': '#108ee9',
                '100%': '#87d068',
              }}
            />
            <p className="text-center text-sm text-gray-600 mt-2">
              正在删除文件...
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default LogCleanupManager;
