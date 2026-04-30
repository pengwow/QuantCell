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
  Badge,
  Divider,
} from 'antd';
import {
  ClearOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { useWorkerStore } from '../../store/workerStore';

// WorkerLog 类型定义（避免循环依赖）
interface WorkerLog {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  source: string;
  message: string;
}

const { Option } = Select;

// 日志级别配置（与系统日志保持一致的颜色方案）
const LOG_LEVELS = [
  { value: 'DEBUG', label: 'DEBUG', color: 'default' },
  { value: 'INFO', label: 'INFO', color: 'blue' },
  { value: 'WARNING', label: 'WARNING', color: 'orange' },
  { value: 'ERROR', label: 'ERROR', color: 'red' },
  { value: 'CRITICAL', label: 'CRITICAL', color: 'purple' },
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

  const [selectedLevels, setSelectedLevels] = useState<string[]>(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']);
  const [isPaused, setIsPaused] = useState(false);
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
      connectLogStream(workerId);
    } else if (isPaused) {
      console.log(`⏸️ [WorkerLogs] 已暂停，不自动连接`);
    }

    return () => {
      if (!isPaused) {
        console.log(`🔌 [WorkerLogs] 清理: 断开 Worker ${workerId} 日志流`);
        disconnectLogStream();
      }
    };
  }, [workerId, connectLogStream, disconnectLogStream, isPaused]);

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
    const newPausedState = !isPaused;  // 先计算新状态

    setIsPaused(newPausedState);       // 更新状态

    // 根据新状态立即执行操作（不依赖异步更新的状态）
    if (newPausedState) {
      // 即将暂停 → 立即断开 WebSocket
      console.log('⏸️ [WorkerLogs] 暂停日志流');
      disconnectLogStream();
    } else {
      // 即将恢复 → 立即重新连接 WebSocket
      console.log('▶️ [WorkerLogs] 恢复日志流');
      connectLogStream(workerId);
    }
  }, [isPaused, workerId, connectLogStream, disconnectLogStream]);

  // 格式化时间戳
  const formatTimestamp = (timestamp: string) => {
    try {
      return dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss');
    } catch {
      return timestamp;
    }
  };

  return (
    <div>
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FileTextOutlined />
          <span className="text-lg font-medium">{t('real_time_logs') || '实时日志'}</span>
          <Badge
            status={isLogStreamConnected ? 'processing' : 'default'}
            text={isLogStreamConnected ? (t('connected') || '已连接') : (t('disconnected') || '未连接')}
          />
          {isPaused && <Tag color="orange">{t('paused') || '已暂停'}</Tag>}
        </div>

        {/* 控制按钮组 */}
        <div className="flex items-center gap-2">
          {/* 日志级别过滤 */}
          <Select
            mode="multiple"
            placeholder={t('filter_by_level') || '按级别过滤'}
            value={selectedLevels}
            onChange={setSelectedLevels}
            style={{ width: 180 }}
            size="small"
            maxTagCount={2}
            popupMatchSelectWidth={false}
          >
            {LOG_LEVELS.map((level) => (
              <Option key={level.value} value={level.value}>
                <Tag color={level.color} style={{ margin: 0 }}>{level.label}</Tag>
              </Option>
            ))}
          </Select>

          {/* 智能滚动状态指示 */}
          <Tooltip title={autoScroll ? (t('auto_tracking') || '自动跟踪最新日志') : (t('manual_scroll') || '手动浏览历史日志')}>
            <Badge status={autoScroll ? 'success' : 'default'} />
          </Tooltip>

          {/* 暂停/恢复 */}
          <Tooltip title={isPaused ? (t('resume') || '恢复' ) : (t('pause') || '暂停')}>
            <button
              onClick={handleTogglePause}
              className="p-1.5 rounded hover:bg-stone-700 text-stone-300 hover:text-white transition-colors"
            >
              {isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            </button>
          </Tooltip>

          {/* 清除日志 */}
          <Tooltip title={t('clear_logs') || '清除日志'}>
            <button
              onClick={handleClear}
              disabled={logs.length === 0}
              className="p-1.5 rounded hover:bg-stone-700 text-stone-300 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ClearOutlined />
            </button>
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
            <a
              onClick={handleClear}
              className={`text-xs cursor-pointer ${
                logs.length > 0
                  ? 'text-blue-400 hover:text-blue-300'
                  : 'text-stone-600 cursor-not-allowed'
              }`}
            >
              {t('clear_logs') || '清除日志'}
            </a>
            <Divider orientation="vertical" className="bg-stone-600 mx-2" />
            <span className="text-xs text-stone-500">
              {t('total_logs') || '总数'}: {logs.length} | {t('filtered_logs') || '过滤'}:{filteredLogs.length}
            </span>

            {/* 智能滚动状态指示 */}
            {autoScroll && !isPaused ? (
              <>
                <Divider orientation="vertical" className="bg-stone-600 mx-2" />
                <span className="text-xs text-green-400 flex items-center gap-1">
                  <SyncOutlined spin style={{ fontSize: '10px' }} />
                  {t('auto_tracking') || '自动跟踪最新日志'}
                </span>
              </>
            ) : !autoScroll && !isPaused ? (
              <>
                <Divider orientation="vertical" className="bg-stone-600 mx-2" />
                <span className="text-xs text-blue-300">
                  {t('manual_browsing') || '手动浏览历史日志'}
                </span>
              </>
            ) : null}

            {isPaused && (
              <>
                <Divider orientation="vertical" className="bg-stone-600 mx-2" />
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
