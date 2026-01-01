import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Space, Tag, message, Popconfirm, Tooltip } from 'antd';
import { PlusOutlined, PlayCircleOutlined, PauseCircleOutlined, DeleteOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnType } from 'antd/es/table';

// 导入API服务
import { scheduledTaskApi } from '../../api';

// 导入类型定义
import type { ScheduledTask } from '../../types';

/**
 * 定时任务管理页面
 * 功能：管理系统中的定时任务，包括查看列表、创建、编辑、删除、运行、暂停等操作
 */
const ScheduledTasks: React.FC = () => {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // 加载定时任务列表
  const loadTasks = async () => {
    try {
      setLoading(true);
      const data = await scheduledTaskApi.getTasks();
      setTasks(data.tasks || []);
    } catch (error) {
      console.error('加载定时任务失败:', error);
      message.error('加载定时任务失败');
    } finally {
      setLoading(false);
    }
  };

  // 组件挂载时加载定时任务列表
  useEffect(() => {
    loadTasks();
  }, []);

  // 运行定时任务
  const handleRunTask = async (taskId: number) => {
    try {
      await scheduledTaskApi.runTask(taskId.toString());
      message.success('定时任务已开始执行');
      // 刷新任务列表
      loadTasks();
    } catch (error) {
      console.error('运行定时任务失败:', error);
      message.error('运行定时任务失败');
    }
  };

  // 暂停定时任务
  const handlePauseTask = async (taskId: number) => {
    try {
      await scheduledTaskApi.pauseTask(taskId.toString());
      message.success('定时任务已暂停');
      // 刷新任务列表
      loadTasks();
    } catch (error) {
      console.error('暂停定时任务失败:', error);
      message.error('暂停定时任务失败');
    }
  };

  // 恢复定时任务
  const handleResumeTask = async (taskId: number) => {
    try {
      await scheduledTaskApi.resumeTask(taskId.toString());
      message.success('定时任务已恢复');
      // 刷新任务列表
      loadTasks();
    } catch (error) {
      console.error('恢复定时任务失败:', error);
      message.error('恢复定时任务失败');
    }
  };

  // 删除定时任务
  const handleDeleteTask = async (taskId: number) => {
    try {
      await scheduledTaskApi.deleteTask(taskId.toString());
      message.success('定时任务已删除');
      // 刷新任务列表
      loadTasks();
    } catch (error) {
      console.error('删除定时任务失败:', error);
      message.error('删除定时任务失败');
    }
  };

  // 编辑定时任务
  const handleEditTask = (taskId: number) => {
    // 导航到编辑页面
    navigate(`/scheduled-tasks/edit/${taskId}`);
  };

  // 新建定时任务
  const handleCreateTask = () => {
    // 导航到创建页面
    navigate('/scheduled-tasks/create');
  };

  // 状态标签颜色映射
  const statusColorMap: Record<string, string> = {
    pending: 'blue',
    running: 'green',
    completed: 'purple',
    failed: 'red',
    paused: 'orange',
  };

  // 任务类型标签颜色映射
  const taskTypeColorMap: Record<string, string> = {
    download_crypto: 'cyan',
  };

  // 表格列配置
  const columns: ColumnType<ScheduledTask>[] = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      width: 200,
    },
    {
      title: '任务类型',
      dataIndex: 'task_type',
      key: 'task_type',
      ellipsis: true,
      width: 150,
      render: (taskType) => (
        <Tag color={taskTypeColorMap[taskType] || 'default'}>
          {taskType}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {status}
        </Tag>
      ),
    },
    {
      title: '频率类型',
      dataIndex: 'frequency_type',
      key: 'frequency_type',
      ellipsis: true,
      width: 120,
    },
    {
      title: '下次执行时间',
      dataIndex: 'next_run_time',
      key: 'next_run_time',
      width: 180,
      render: (nextRunTime) => nextRunTime ? new Date(nextRunTime).toLocaleString() : '-',
    },
    {
      title: '上次执行时间',
      dataIndex: 'last_run_time',
      key: 'last_run_time',
      width: 180,
      render: (lastRunTime) => lastRunTime ? new Date(lastRunTime).toLocaleString() : '-',
    },
    {
      title: '执行次数',
      dataIndex: 'run_count',
      key: 'run_count',
      width: 100,
      align: 'center',
    },
    {
      title: '成功次数',
      dataIndex: 'success_count',
      key: 'success_count',
      width: 100,
      align: 'center',
      render: (successCount) => (
        <span style={{ color: '#52c41a' }}>{successCount}</span>
      ),
    },
    {
      title: '失败次数',
      dataIndex: 'fail_count',
      key: 'fail_count',
      width: 100,
      align: 'center',
      render: (failCount) => (
        <span style={{ color: '#ff4d4f' }}>{failCount}</span>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      align: 'center',
      render: (_, record) => (
        <Space size="middle">
          <Tooltip title="编辑任务">
            <Button
              type="link"
              icon={<EditOutlined />}
              onClick={() => handleEditTask(record.id)}
            />
          </Tooltip>
          
          {record.status === 'running' ? (
            <Tooltip title="暂停任务">
              <Button
                type="link"
                danger
                icon={<PauseCircleOutlined />}
                onClick={() => handlePauseTask(record.id)}
              />
            </Tooltip>
          ) : record.status === 'paused' ? (
            <Tooltip title="恢复任务">
              <Button
                type="link"
                icon={<PlayCircleOutlined />}
                onClick={() => handleResumeTask(record.id)}
              />
            </Tooltip>
          ) : (
            <Tooltip title="运行任务">
              <Button
                type="link"
                icon={<PlayCircleOutlined />}
                onClick={() => handleRunTask(record.id)}
              />
            </Tooltip>
          )}
          
          <Tooltip title="立即执行">
            <Button
              type="link"
              icon={<ReloadOutlined />}
              onClick={() => handleRunTask(record.id)}
            />
          </Tooltip>
          
          <Popconfirm
            title="确定要删除这个任务吗？"
            onConfirm={() => handleDeleteTask(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除任务">
              <Button
                type="link"
                danger
                icon={<DeleteOutlined />}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="scheduled-tasks-page">
      <Card
        title="定时任务管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateTask}
          >
            新建任务
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          onRow={(record) => ({
            onClick: () => handleEditTask(record.id),
          })}
          scroll={{ x: 1200 }}
        />
      </Card>
    </div>
  );
};

export default ScheduledTasks;
