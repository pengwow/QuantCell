/**
 * Worker Logs Panel
 *
 * 实时显示Worker日志的面板组件
 * 支持WebSocket连接、日志级别过滤、自动滚动等功能
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card,
  List,
  Tag,
  Space,
  Button,
  Select,
  Tooltip,
  Badge,
  Empty,
  Alert,
  Switch,
  Typography,
} from 'antd';
import {
  ClearOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
  FileTextOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  BugOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { WorkerLog } from '../../types/worker';
import { useWorkerStore } from '../../store/workerStore';

const { Text } = Typography;
const { Option } = Select;

// 日志级别配置
const LOG_LEVELS = [
  { value: 'DEBUG', label: 'DEBUG', color: 'default', icon: <BugOutlined /> },
  { value: 'INFO', label: 'INFO', color: 'blue', icon: <InfoCircleOutlined /> },
  { value: 'WARNING', label: 'WARNING', color: 'orange', icon: <WarningOutlined /> },
  { value: 'ERROR', label: 'ERROR', color: 'red', icon: <CloseCircleOutlined /> },
  { value: 'CRITICAL', label: 'CRITICAL', color: 'purple', icon: <CloseCircleOutlined /> },
];

interface WorkerLogsPanelProps {
  workerId: number;
  maxHeight?: number;
}

const WorkerLogsPanel: React.FC<WorkerLogsPanelProps> = ({
  workerId,
  maxHeight = 400,
}) => {
  const { t } = useTranslation();
  const {
    logs,
    isLogStreamConnected,
    connectLogStream,
    disconnectLogStream,
    clearLogs,
  } = useWorkerStore();

  const [selectedLevels, setSelectedLevels] = useState<string[]>(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const prevLogsLength = useRef(logs.length);

  // 连接WebSocket
  useEffect(() => {
    if (workerId && !isPaused) {
      connectLogStream(workerId);
    }
    return () => {
      disconnectLogStream();
    };
  }, [workerId, connectLogStream, disconnectLogStream, isPaused]);

  // 自动滚动
  useEffect(() => {
    if (autoScroll && !isPaused && listRef.current && logs.length > prevLogsLength.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
    prevLogsLength.current = logs.length;
  }, [logs, autoScroll, isPaused]);

  // 过滤日志
  const filteredLogs = React.useMemo(() => {
    return logs.filter((log) => selectedLevels.includes(log.level));
  }, [logs, selectedLevels]);

  // 处理清除日志
  const handleClear = useCallback(() => {
    clearLogs();
  }, [clearLogs]);

  // 处理暂停/恢复
  const handleTogglePause = useCallback(() => {
    setIsPaused(!isPaused);
    if (isPaused) {
      // 恢复时重新连接
      connectLogStream(workerId);
    } else {
      // 暂停时断开连接
      disconnectLogStream();
    }
  }, [isPaused, workerId, connectLogStream, disconnectLogStream]);

  // 渲染日志级别标签
  const renderLevelTag = (level: string) => {
    const levelConfig = LOG_LEVELS.find((l) => l.value === level) || LOG_LEVELS[1];
    return (
      <Tag color={levelConfig.color} icon={levelConfig.icon} style={{ minWidth: 70, textAlign: 'center' }}>
        {level}
      </Tag>
    );
  };

  // 渲染日志项
  const renderLogItem = (log: WorkerLog, index: number) => {
    const timestamp = new Date(log.timestamp).toLocaleTimeString();

    return (
      <List.Item
        key={`${log.timestamp}-${index}`}
        style={{
          padding: '8px 12px',
          borderBottom: '1px solid #f0f0f0',
          fontFamily: 'monospace',
          fontSize: 12,
          backgroundColor: index % 2 === 0 ? '#fafafa' : '#fff',
        }}
      >
        <Space align="start" style={{ width: '100%' }}>
          <Text type="secondary" style={{ minWidth: 80, fontSize: 11 }}>
            {timestamp}
          </Text>
          {renderLevelTag(log.level)}
          <Text style={{ flex: 1, wordBreak: 'break-all' }}>{log.message}</Text>
        </Space>
      </List.Item>
    );
  };

  return (
    <Card
      title={
        <Space>
          <FileTextOutlined />
          {t('real_time_logs')}
          <Badge
            status={isLogStreamConnected ? 'processing' : 'default'}
            text={isLogStreamConnected ? t('connected') : t('disconnected')}
          />
          {isPaused && <Tag color="orange">{t('paused')}</Tag>}
        </Space>
      }
      extra={
        <Space>
          {/* 日志级别过滤 */}
          <Select
            mode="multiple"
            placeholder={t('filter_by_level')}
            value={selectedLevels}
            onChange={setSelectedLevels}
            style={{ width: 200 }}
            size="small"
            maxTagCount={2}
          >
            {LOG_LEVELS.map((level) => (
              <Option key={level.value} value={level.value}>
                {level.label}
              </Option>
            ))}
          </Select>

          {/* 自动滚动开关 */}
          <Tooltip title={t('auto_scroll')}>
            <Switch
              size="small"
              checked={autoScroll}
              onChange={setAutoScroll}
              checkedChildren={<SyncOutlined spin />}
              unCheckedChildren={<PauseCircleOutlined />}
            />
          </Tooltip>

          {/* 暂停/恢复 */}
          <Tooltip title={isPaused ? t('resume') : t('pause')}>
            <Button
              type="text"
              size="small"
              icon={isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              onClick={handleTogglePause}
            />
          </Tooltip>

          {/* 清除日志 */}
          <Tooltip title={t('clear_logs')}>
            <Button
              type="text"
              size="small"
              icon={<ClearOutlined />}
              onClick={handleClear}
              disabled={logs.length === 0}
            />
          </Tooltip>
        </Space>
      }
      bodyStyle={{ padding: 0 }}
    >
      {/* 连接状态提示 */}
      {!isLogStreamConnected && !isPaused && (
        <Alert
          message={t('log_stream_disconnected')}
          type="warning"
          showIcon
          banner
          style={{ marginBottom: 0 }}
        />
      )}

      {/* 日志列表 */}
      <div
        ref={listRef}
        style={{
          maxHeight,
          overflow: 'auto',
          backgroundColor: '#fff',
        }}
      >
        {filteredLogs.length === 0 ? (
          <Empty
            description={isPaused ? t('logs_paused') : t('no_logs')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ padding: '40px 0' }}
          />
        ) : (
          <List
            dataSource={filteredLogs}
            renderItem={renderLogItem}
            size="small"
            style={{ margin: 0 }}
          />
        )}
      </div>

      {/* 日志统计 */}
      <div
        style={{
          padding: '8px 12px',
          borderTop: '1px solid #f0f0f0',
          backgroundColor: '#fafafa',
          fontSize: 12,
          color: '#666',
        }}
      >
        <Space>
          <span>{t('total_logs')}: {logs.length}</span>
          <span>|</span>
          <span>{t('filtered_logs')}: {filteredLogs.length}</span>
          {isPaused && (
            <>
              <span>|</span>
              <Text type="warning">{t('stream_paused')}</Text>
            </>
          )}
        </Space>
      </div>
    </Card>
  );
};

export default WorkerLogsPanel;
