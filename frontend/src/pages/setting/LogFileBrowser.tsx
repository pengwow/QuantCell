/**
 * LogFileBrowser - 日志文件浏览器
 * 提供日志文件的目录树展示、文件列表和详情查看功能
 */
import { useState, useEffect, useCallback } from 'react';
import { App } from 'antd';
import {
  Table,
  Tag,
  Descriptions,
  Spin,
  Empty,
  Input,
  Button,
  Space,
  Tooltip,
  Card,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  IconRefresh,
  IconSearch,
  IconFile,
  IconFolder,
  IconInfoCircle,
  IconSortAscending,
  IconSortDescending,
} from '@tabler/icons-react';
import { systemApi } from '../../api';
import type { LogFileInfo, LogDirectoryNode } from './types';

const LogFileBrowser: React.FC = () => {
  const { message: antMessage } = App.useApp();
  const [loading, setLoading] = useState<boolean>(false);
  const [directoryTree, setDirectoryTree] = useState<LogDirectoryNode | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<LogFileInfo[]>([]);
  const [currentDir, setCurrentDir] = useState<string>('');
  const [searchText, setSearchText] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<'ascend' | 'descend'>('descend');

  // 加载目录树数据
  const loadDirectoryTree = useCallback(async () => {
    try {
      setLoading(true);
      const data = await systemApi.getLogDirectory();
      setDirectoryTree(data);
      if (!currentDir && data?.children?.length > 0) {
        setCurrentDir(data.children[0].path);
      }
    } catch (error) {
      console.error('加载目录树失败:', error);
      antMessage.error('无法加载日志文件列表');
    } finally {
      setLoading(false);
    }
  }, [currentDir]);

  useEffect(() => {
    loadDirectoryTree();
  }, [loadDirectoryTree]);

  // 获取当前目录的文件列表
  const getCurrentFiles = (): LogFileInfo[] => {
    if (!directoryTree) return [];

    let files: LogFileInfo[] = [];

    const findDir = (nodes: LogDirectoryNode['children']): LogDirectoryNode | undefined => {
      for (const node of nodes) {
        if (node.path === currentDir) return node;
        if (node.children.length > 0) {
          const found = findDir(node.children);
          if (found) return found;
        }
      }
      return undefined;
    };

    if (currentDir === directoryTree.path) {
      directoryTree.children.forEach(child => {
        files = [...files, ...child.files];
      });
    } else {
      const dir = findDir(directoryTree.children);
      if (dir) {
        files = dir.files;
      }
    }

    // 应用搜索过滤
    if (searchText) {
      files = files.filter(file =>
        file.name.toLowerCase().includes(searchText.toLowerCase())
      );
    }

    // 排序
    files.sort((a, b) =>
      sortOrder === 'ascend' ? a.size - b.size : b.size - a.size
    );

    return files;
  };

  // 表格列定义
  const columns: ColumnsType<LogFileInfo> = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: LogFileInfo) => (
        <div className="flex items-center gap-2">
          <IconFile size={16} className="text-blue-500" />
          <span className="font-mono text-sm">{text}</span>
        </div>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size_formatted',
      key: 'size',
      sorter: true,
      sortOrder,
      width: 120,
      render: (text: string) => (
        <Tag color="blue">{text}</Tag>
      ),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_time',
      key: 'modified_time',
      width: 180,
      render: (text: string) => (
        <span className="text-xs text-gray-600">
          {new Date(text).toLocaleString('zh-CN')}
        </span>
      ),
    },
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 120,
      render: (text: string) => (
        text ? <Tag color="geekblue">{text}</Tag> : '-'
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: LogFileInfo) => (
        <Tooltip title="查看详情">
          <Button
            type="link"
            size="small"
            icon={<IconInfoCircle size={14} />}
            onClick={() => setSelectedFiles([record])}
          />
        </Tooltip>
      ),
    },
  ];

  // 切换排序
  const toggleSort = () => {
    setSortOrder(prev => prev === 'ascend' ? 'descend' : 'ascend');
  };

  return (
    <div className="p-6">
      {/* 工具栏 */}
      <div className="flex items-center justify-between mb-4">
        <Space>
          <Input
            placeholder="搜索文件名..."
            prefix={<IconSearch size={16} />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: 250 }}
          />
          <Tooltip title="切换排序">
            <Button
              icon={
                sortOrder === 'ascend' ?
                  <IconSortAscending size={16} /> :
                  <IconSortDescending size={16} />
              }
              onClick={toggleSort}
            />
          </Tooltip>
        </Space>

        <Space>
          <Button
            icon={<IconRefresh size={16} />}
            onClick={loadDirectoryTree}
            loading={loading}
          >
            刷新
          </Button>
        </Space>
      </div>

      {/* 目录标签页（简化版） */}
      {directoryTree && (
        <div className="flex gap-2 mb-4 flex-wrap">
          <Tag.CheckableTag
            checked={currentDir === directoryTree.path}
            onChange={() => setCurrentDir(directoryTree.path)}
          >
            📁 全部 ({directoryTree.file_count} 个文件)
          </Tag.CheckableTag>
          {directoryTree.children.map(child => (
            <Tag.CheckableTag
              key={child.path}
              checked={currentDir === child.path}
              onChange={() => setCurrentDir(child.path)}
            >
              📂 {child.name} ({child.file_count})
            </Tag.CheckableTag>
          ))}
        </div>
      )}

      {/* 主内容区：左侧表格 + 右侧详情 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 文件列表表格 */}
        <div className="lg:col-span-2">
          <Spin spinning={loading}>
            <Table
              columns={columns}
              dataSource={getCurrentFiles()}
              rowKey="path"
              pagination={{
                pageSize: 10,
                showTotal: (total) => `共 ${total} 个文件`,
                size: 'small',
              }}
              size="middle"
              locale={{
                emptyText: <Empty description="暂无日志文件" />,
              }}
            />
          </Spin>
        </div>

        {/* 文件详情面板 */}
        <div className="lg:col-span-1">
          {selectedFiles.length > 0 ? (
            <Card
              size="small"
              title="文件详情"
              className="shadow-sm"
            >
              <Descriptions
                column={1}
                size="small"
                bordered
                labelStyle={{ width: 100, backgroundColor: '#fafafa' }}
              >
                <Descriptions.Item label="文件名">
                  <span className="font-mono text-sm">
                    {selectedFiles[0].name}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="完整路径">
                  <span className="text-xs break-all">
                    {selectedFiles[0].path}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="文件大小">
                  <Tag color="blue">{selectedFiles[0].size_formatted}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">
                  {selectedFiles[0].created_time ?
                    new Date(selectedFiles[0].created_time).toLocaleString('zh-CN') :
                    '-'
                  }
                </Descriptions.Item>
                <Descriptions.Item label="修改时间">
                  {new Date(selectedFiles[0].modified_time).toLocaleString('zh-CN')}
                </Descriptions.Item>
                <Descriptions.Item label="日志类型">
                  <Tag>{selectedFiles[0].log_type || '-'}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="日志条数">
                  {selectedFiles[0].line_count ?
                    `${selectedFiles[0].line_count.toLocaleString()} 条` :
                    '-'
                  }
                </Descriptions.Item>
              </Descriptions>
            </Card>
          ) : (
            <Card size="small" className="shadow-sm">
              <Empty
                description="选择一个文件查看详情"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

export default LogFileBrowser;
