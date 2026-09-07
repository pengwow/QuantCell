/**
 * Worker Logs Panel
 *
 * 实时显示Worker日志的面板组件（终端风格）
 * 支持WebSocket连接、日志级别过滤、自动滚动等功能
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Tag,
  Select,
  Tooltip,
  Button,
} from 'antd';
import {
  ClearOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useWorkerStore } from '../../store/workerStore';
import { fetchRecentLogs } from '../../api/workerApi';

const { Option } = Select;

// 日志级别配置（与 NautilusTrader 实际输出保持一致）
const LOG_LEVELS = [
  { value: 'DEBUG', label: 'DEBUG', color: 'default' },
  { value: 'INFO', label: 'INFO', color: 'blue' },
  { value: 'WARN', label: 'WARN', color: 'orange' },
  { value: 'ERROR', label: 'ERROR', color: 'red' },
];

interface WorkerLogsPanelProps {
  workerId: number;
  maxHeight?: number;
}

const getLevelColor = (level: string): string => {
  const levelConfig = LOG_LEVELS.find((l) => l.value === level);
  return levelConfig?.color || 'default';
};

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

  const [selectedLevels, setSelectedLevels] = useState<string[]>(['DEBUG', 'INFO', 'WARN', 'ERROR']);
  const [isPaused, setIsPaused] = useState(false);

  // 使用 ref 存储 connectLogStream/disconnectLogStream 避免引用变化触发无限循环
  const connectLogStreamRef = useRef(connectLogStream);
  const disconnectLogStreamRef = useRef(disconnectLogStream);
  connectLogStreamRef.current = connectLogStream;
  disconnectLogStreamRef.current = disconnectLogStream;
  // 智能滚动状态
  const [autoScroll, setAutoScroll] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const prevLogsLength = useRef(logs.length);
  // 用于判断用户是否手动滚动了（距离底部超过阈值）
  const SCROLL_THRESHOLD = 100; // 距离底部 100px 以内视为"在底部"

  // 连接WebSocket - 仅在未暂停时自动连接
  useEffect(() => {
    if (!isPaused && workerId) {
      console.log(`🔗 [WorkerLogs] 自动连接 Worker ${workerId} 日志流`);
      connectLogStreamRef.current(workerId);
    } else if (isPaused) {
      console.log(`⏸️ [WorkerLogs] 已暂停，不自动连接`);
    }

    return () => {
      console.log(`🔌 [WorkerLogs] 清理: 断开 Worker ${workerId} 日志流`);
      disconnectLogStreamRef.current();
    };
  }, [workerId, isPaused]);

  // 从 LogRingBuffer 加载最近日志作为初始内容
  const [initialLogsLoaded, setInitialLogsLoaded] = useState(false);
  const loadInitialLogsFromBuffer = useCallback(async () => {
    try {
      const res = await fetchRecentLogs(workerId, { limit: 100 });
      if (res.code === 0 && res.data.logs.length > 0) {
        // 缓冲区内有日志则跳过首次加载等待流式推送
        clearLogs();
        setInitialLogsLoaded(true);
      }
    } catch (error) {
      console.warn('[WorkerLogsPanel] 加载初始日志失败（非致命）:', error);
    }
  }, [workerId, clearLogs]);

  // 组件挂载时加载初始日志
  useEffect(() => {
    if (workerId && !initialLogsLoaded) {
      loadInitialLogsFromBuffer();
    }
  }, [workerId, initialLogsLoaded, loadInitialLogsFromBuffer]);

  // 智能自动滚动逻辑
  useEffect(() => {
    if (autoScroll && !isPaused && listRef.current && logs.length > prevLogsLength.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
    prevLogsLength.current = logs.length;
  }, [logs, autoScroll, isPaused]);

  // 处理滚动事件 - 检测用户是否手动向上滚动
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const element = e.currentTarget;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;

    if (distanceFromBottom < SCROLL_THRESHOLD) {
      // 用户滚动到接近底部，恢复自动滚动
      if (!autoScroll) {
        setAutoScroll(true);
      }
    } else {
      // 用户向上滚动查看历史日志，暂停自动滚动
      if (autoScroll) {
        setAutoScroll(false);
      }
    }
  }, [autoScroll]);

  // 过滤日志
  const filteredLogs = React.useMemo(() => {
    return logs.filter((log) => selectedLevels.includes(log.level));
  }, [logs, selectedLevels]);

  // 处理清除日志
  const handleClear = useCallback(() => {
    clearLogs();
  }, [clearLogs]);

  // 处理暂停/恢复 - 使用函数式更新避免竞态条件
  const handleTogglePause = useCallback(() => {
    const newPausedState = !isPaused;

    setIsPaused(newPausedState);

    if (newPausedState) {
      console.log('⏸️ [WorkerLogs] 暂停日志流');
      disconnectLogStreamRef.current();
    } else {
      console.log('▶️ [WorkerLogs] 恢复日志流');
      connectLogStreamRef.current(workerId);
    }
  }, [isPaused, workerId]);

  // 格式化时间戳（UTC → 本地时区）
  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      const pad = (n: number) => n.toString().padStart(2, '0');
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    } catch {
      return timestamp;
    }
  };

  return (
    <div>
      {/* 标题栏 - 第一行 */}
      <div className="mb-3">
        <div className="flex items-center gap-2">
          <FileTextOutlined />
          <span className="text-lg font-medium">{t('real_time_logs') || '实时日志'}</span>
          {isPaused && <Tag color="orange">{t('paused') || '已暂停'}</Tag>}
        </div>
      </div>

      {/* 控制按钮组 - 第二行 */}
      <div className="flex items-center justify-between mb-4">
        {/* 左侧：日志级别过滤下拉列表 */}
        <Select
          mode="multiple"
          placeholder={t('filter_by_level') || '按级别过滤'}
          value={selectedLevels}
          onChange={setSelectedLevels}
          style={{ width: 360 }}
          size="small"
          maxTagCount='responsive'
          popupMatchSelectWidth={false}
        >
          {LOG_LEVELS.map((level) => (
            <Option key={level.value} value={level.value}>
              <Tag color={level.color} style={{ margin: 0 }}>{level.label}</Tag>
            </Option>
          ))}
        </Select>

        {/* 右侧：操作按钮组（2个按钮） */}
        <div className="flex items-center gap-2">
          {/* 暂停/恢复 */}
          <Tooltip title={isPaused ? (t('resume') || '恢复' ) : (t('pause') || '暂停')}>
            <Button
              type={isPaused ? 'primary' : 'default'}
              size="small"
              icon={isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              onClick={handleTogglePause}
            >
              {isPaused ? (t('resume') || '恢复') : (t('pause') || '暂停')}
            </Button>
          </Tooltip>

          {/* 清除日志 */}
          <Tooltip title={t('clear_logs') || '清除日志'}>
            <Button
              size="small"
              icon={<ClearOutlined />}
              onClick={handleClear}
              disabled={logs.length === 0}
            >
              {t('clear_logs') || '清除'}
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* 终端风格日志容器 - 黑色背景，使用 flex 布局固定底部操作栏 */}
      <div
        className="rounded-md bg-black text-stone-200 flex flex-col"
        style={{ maxHeight: maxHeight + 80 }}
      >
        {/* 1. 固定顶部：连接状态提示 */}
        {!isLogStreamConnected && !isPaused && (
          <div className="px-4 py-2 bg-yellow-900/30 border-b border-yellow-800/50 shrink-0">
            <span className="text-xs text-yellow-400">
              ⚠ {t('log_stream_disconnected') || '日志流未连接'}
            </span>
          </div>
        )}

        {/* 2. 可滚动中间区域：日志列表 */}
        <div
          ref={listRef}
          className="flex-1 px-4 py-2 overflow-auto min-h-0"
          onScroll={handleScroll}
        >
          {filteredLogs.length === 0 ? (
            <div className="text-xs text-stone-400 py-8">
              {'> '}
              {isPaused
                ? (t('logs_paused') || '日志已暂停')
                : (t('no_logs') || '> 暂无日志，等待连接...')}
            </div>
          ) : (
            /* 终端风格日志列表 */
            <div className="flex w-full flex-col">
              {filteredLogs.map((log, index) => (
                <div key={`${log.timestamp}-${index}`} className="text-xs leading-relaxed mb-1">
                  {log.source === 'raw' ? (
                    <span className="font-mono break-all text-stone-300">{log.message}</span>
                  ) : (
                    <div className="flex items-start gap-2">
                      {/* 时间戳 - 终端风格 */}
                      <span className="font-mono whitespace-nowrap text-stone-400 shrink-0">
                        [{formatTimestamp(log.timestamp)}]
                      </span>

                      {/* 日志级别标签 - 紧凑样式 */}
                      <Tag
                        color={getLevelColor(log.level)}
                        className="shrink-0 m-0"
                        style={{ fontSize: '10px', padding: '0 4px', lineHeight: '16px' }}
                      >
                        {log.level}
                      </Tag>

                      {/* 消息内容 */}
                      <span className="break-all">{log.message}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 3. 固定底部：操作栏（不随滚动移动） */}
        <div
          className="px-4 py-2 border-t border-stone-700 bg-black shrink-0"
          style={{
            position: 'sticky',
            bottom: 0,
            zIndex: 10,
          }}
        >
          <div className="flex w-full items-center">
            <span className="text-xs text-stone-500">
              {t('total_logs') || '总数'}: {logs.length} | {t('filtered_logs') || '过滤'}:{filteredLogs.length}
            </span>

            {isPaused && (
              <>
                <span className="mx-2 text-stone-600">|</span>
                <span className="text-xs text-yellow-400">
                  {t('stream_paused') || '流已暂停'}
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkerLogsPanel;
