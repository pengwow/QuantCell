/**
 * Worker Logs Panel
 *
 * 实时显示Worker日志的面板组件（终端风格）
 * 支持WebSocket连接、日志级别过滤、自动滚动等功能
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
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

// 日志级别（与 NautilusTrader 实际输出保持一致）；着色收敛到 .qc-term-lv-*（§2.3 语义变量）
const LOG_LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR'] as const;

// 级别 → qc-term-lv 类（未知级别回退 debug 的中性灰）
const LEVEL_CLS: Record<string, string> = {
  DEBUG: 'debug',
  INFO: 'info',
  WARN: 'warn',
  ERROR: 'error',
};

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

  const [selectedLevels, setSelectedLevels] = useState<string[]>(['DEBUG', 'INFO', 'WARN', 'ERROR']);
  const [isPaused, setIsPaused] = useState(false);

  // 使用 ref 存储 connectLogStream/disconnectLogStream 避免引用变化触发无限循环
  const connectLogStreamRef = useRef(connectLogStream);
  const disconnectLogStreamRef = useRef(disconnectLogStream);

  // 在 effect 中同步 ref 指向的最新函数，避免渲染阶段直接读写 ref（react-hooks/refs）
  useEffect(() => {
    connectLogStreamRef.current = connectLogStream;
    disconnectLogStreamRef.current = disconnectLogStream;
  }, [connectLogStream, disconnectLogStream]);
  // 智能滚动状态
  const [autoScroll, setAutoScroll] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const prevLogsLength = useRef(logs.length);
  // 用于判断用户是否手动滚动了（距离底部超过阈值）
  const SCROLL_THRESHOLD = 100; // 距离底部 100px 以内视为"在底部"

  // 连接日志流 - 仅在未暂停时自动连接
  //
  // 延后一拍再建连：开发环境的 React StrictMode 会 mount → cleanup → mount，
  // 同步建连会让第一次的 EventSource 在建连途中被 close，浏览器控制台报
  // net::ERR_ABORTED。延后后 cleanup 能取消掉这次尚未发生的建连。
  useEffect(() => {
    if (isPaused || !workerId) {
      console.log(`⏸️ [WorkerLogs] 已暂停，不自动连接`);
      return;
    }

    const connectTimer = setTimeout(() => {
      console.log(`🔗 [WorkerLogs] 自动连接 Worker ${workerId} 日志流`);
      connectLogStreamRef.current(workerId);
    }, 0);

    return () => {
      clearTimeout(connectTimer);
      console.log(`🔌 [WorkerLogs] 清理: 断开 Worker ${workerId} 日志流`);
      disconnectLogStreamRef.current();
    };
  }, [workerId, isPaused]);

  // 从 LogRingBuffer 加载最近日志作为初始内容
  const [initialLogsLoaded, setInitialLogsLoaded] = useState(false);

  // 组件挂载时加载初始日志（setState 放在 then 回调中，避免同步 setState 触发级联渲染）
  useEffect(() => {
    if (workerId && !initialLogsLoaded) {
      fetchRecentLogs(workerId, { limit: 100 })
        .then((res) => {
          if (res.code === 0 && res.data.logs.length > 0) {
            // 缓冲区内有日志则跳过首次加载等待流式推送
            clearLogs();
            setInitialLogsLoaded(true);
          }
        })
        .catch((error) => {
          console.warn('[WorkerLogsPanel] 加载初始日志失败（非致命）:', error);
        });
    }
  }, [workerId, initialLogsLoaded, clearLogs]);

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

  // 处理暂停/恢复 - 连接/断开由上面的 effect 统一负责，
  // 这里只切状态，避免手动建连与 effect 的 cleanup 抢同一条流
  const handleTogglePause = useCallback(() => {
    const newPausedState = !isPaused;
    setIsPaused(newPausedState);
    console.log(newPausedState ? '⏸️ [WorkerLogs] 暂停日志流' : '▶️ [WorkerLogs] 恢复日志流');
  }, [isPaused]);

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
      {/* 标题栏 - 第一行（§6.3 卡头字号） */}
      <div className="mb-3 flex items-center gap-2">
        <FileTextOutlined />
        <span style={{ fontSize: 13.5, fontWeight: 650 }}>{t('real_time_logs')}</span>
        {isPaused && <span className="qc-chip warn">{t('paused')}</span>}
      </div>

      {/* 控制按钮组 - 第二行 */}
      <div className="flex items-center justify-between mb-4">
        {/* 左侧：日志级别过滤下拉列表 */}
        <Select
          mode="multiple"
          placeholder={t('filter_by_level')}
          value={selectedLevels}
          onChange={setSelectedLevels}
          style={{ width: 360, maxWidth: '100%' }}
          size="small"
          maxTagCount='responsive'
          popupMatchSelectWidth={false}
        >
          {LOG_LEVELS.map((level) => (
            <Option key={level} value={level}>
              <span className={`qc-term-lv qc-term-lv-${LEVEL_CLS[level] ?? 'debug'}`}>{level}</span>
            </Option>
          ))}
        </Select>

        {/* 右侧：操作按钮组（2个按钮） */}
        <div className="flex items-center gap-2">
          {/* 暂停/恢复 */}
          <Tooltip title={isPaused ? (t('resume') ) : (t('pause'))}>
            <Button
              type={isPaused ? 'primary' : 'default'}
              size="small"
              icon={isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              onClick={handleTogglePause}
            >
              {isPaused ? (t('resume')) : (t('pause'))}
            </Button>
          </Tooltip>

          {/* 清除日志 */}
          <Tooltip title={t('clear_logs')}>
            <Button
              size="small"
              icon={<ClearOutlined />}
              onClick={handleClear}
              disabled={logs.length === 0}
            >
              {t('clear_logs')}
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* 终端风格日志容器（.qc-term：变量驱动的暗色词法平面，亮暗主题自适应） */}
      <div className="qc-term" style={{ maxHeight: maxHeight + 80 }}>
        {/* 1. 固定顶部：连接状态提示 */}
        {!isLogStreamConnected && !isPaused && (
          <div className="qc-term-bar" style={{ color: 'var(--qc-warning)' }}>
            <span>⚠ {t('log_stream_disconnected')}</span>
          </div>
        )}

        {/* 2. 可滚动中间区域：日志列表 */}
        <div
          ref={listRef}
          className="qc-term-body"
          onScroll={handleScroll}
        >
          {filteredLogs.length === 0 ? (
            <div style={{ padding: '24px 0' }}>
              {'> '}
              {isPaused
                ? (t('logs_paused'))
                : (t('no_logs'))}
            </div>
          ) : (
            /* 终端风格日志列表 */
            <div className="flex w-full flex-col">
              {filteredLogs.map((log, index) => (
                <div key={`${log.timestamp}-${index}`} className="mb-1">
                  {log.source === 'raw' ? (
                    <span className="break-all qc-term-msg">{log.message}</span>
                  ) : (
                    <div className="flex items-start gap-2">
                      {/* 时间戳 - 终端风格 */}
                      <span className="qc-term-ts">
                        [{formatTimestamp(log.timestamp)}]
                      </span>

                      {/* 日志级别 - 紧凑词法标签 */}
                      <span className={`qc-term-lv qc-term-lv-${LEVEL_CLS[log.level] ?? 'debug'}`}>
                        {log.level}
                      </span>

                      {/* 消息内容 */}
                      <span className="qc-term-msg">{log.message}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 3. 固定底部：操作栏（不随滚动移动） */}
        <div
          className="qc-term-foot"
          style={{
            position: 'sticky',
            bottom: 0,
            zIndex: 10,
          }}
        >
          <span>
            {t('total_logs')}: <span className="qc-mono">{logs.length}</span>
            {' | '}
            {t('filtered_logs')}: <span className="qc-mono">{filteredLogs.length}</span>
          </span>

          {isPaused && (
            <span style={{ color: 'var(--qc-warning)' }}>
              {t('stream_paused')}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default WorkerLogsPanel;
