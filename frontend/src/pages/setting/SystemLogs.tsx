/**
 * 系统日志组件
 * 功能：显示系统日志，支持刷新和加载更多
 */
import { useState, useEffect, useCallback } from 'react';
import { Tag, Collapse, Divider } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { systemApi } from '../../api';
import type { LogRecord, LogLevel, LogQueryResponse } from './types';

const { Panel } = Collapse;

/**
 * 获取日志级别颜色
 */
const getLevelColor = (level: LogLevel): string => {
  switch (level) {
    case 'debug':
      return 'default';
    case 'info':
      return 'blue';
    case 'warn':
      return 'orange';
    case 'error':
      return 'red';
    case 'fatal':
      return 'purple';
    default:
      return 'default';
  }
};

/**
 * 获取日志级别标签
 */
const getLevelLabel = (level: LogLevel): string => {
  switch (level) {
    case 'debug':
      return 'DEBUG';
    case 'info':
      return 'INFO';
    case 'warn':
      return 'WARN';
    case 'error':
      return 'ERROR';
    case 'fatal':
      return 'FATAL';
    default:
      return level.toUpperCase();
  }
};

const SystemLogs = () => {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [page, setPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [total, setTotal] = useState<number>(0);

  const pageSize = 20;

  /**
   * 加载日志
   */
  const loadLogs = useCallback(async (pageNum: number, isLoadMore: boolean = false) => {
    try {
      if (isLoadMore) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }

      const response: LogQueryResponse = await systemApi.getLogs({
        page: pageNum,
        pageSize,
      });

      if (isLoadMore) {
        setLogs(prev => [...prev, ...response.records]);
      } else {
        setLogs(response.records);
      }

      setTotal(response.total);
      setHasMore(response.hasMore);
      setPage(pageNum);
    } catch (error) {
      console.error('加载日志失败:', error);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  /**
   * 刷新日志
  */
  const handleRefresh = () => {
    loadLogs(1, false);
  };

  /**
   * 加载更多
   */
  const handleLoadMore = () => {
    if (hasMore && !loadingMore) {
      loadLogs(page + 1, true);
    }
  };

  // 组件挂载时加载日志
  useEffect(() => {
    loadLogs(1, false);
  }, [loadLogs]);

  return (
    <div>
      {/* 标题 */}
      <h3 className="text-lg font-medium mb-4">{t('system_logs') || '系统日志'}</h3>

      {/* 终端风格日志容器 - 纯黑色背景 */}
      <div className="rounded-md bg-black text-stone-200 overflow-hidden">
        <div className="relative">
          {loading && (
            <div className="absolute top-4 right-8 text-xs text-stone-400">
              {t('loading') || '加载中...'}
            </div>
          )}

          <div className="px-4 py-2">
            {logs.length === 0 ? (
              <>
                <div className="text-xs text-stone-400">
                  {t('no_logs') || '> 暂无日志'}
                </div>
                {/* 空状态时也显示操作链接 */}
                <div className="flex w-full items-center mt-4">
                  <a
                    onClick={handleRefresh}
                    className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer"
                  >
                    {t('refresh_logs') || '刷新日志'}
                  </a>
                </div>
              </>
            ) : (
              <>
                {/* 日志列表 */}
                <div className="flex w-full flex-col overflow-hidden">
                  {logs.map((log, index) => (
                    <div key={log.id || index} className="text-xs leading-relaxed mb-1">
                      <div className="flex items-start gap-2">
                        {/* 时间戳 */}
                        <span className="font-mono whitespace-nowrap text-stone-400 shrink-0">
                          [{dayjs(log.timestamp).format('YYYY-MM-DD HH:mm:ss')}]
                        </span>

                        {/* 日志级别 */}
                        <Tag
                          color={getLevelColor(log.level)}
                          className="shrink-0 m-0"
                          style={{ fontSize: '10px', padding: '0 4px', lineHeight: '16px' }}
                        >
                          {getLevelLabel(log.level)}
                        </Tag>

                        {/* 消息内容 */}
                        <span className="break-all">{log.message}</span>
                      </div>

                      {/* 详细数据（可展开） */}
                      {log.data && (
                        <Collapse
                          ghost
                          className="mt-1 ml-0"
                          expandIcon={({ isActive }) => (
                            <DownOutlined rotate={isActive ? 180 : 0} style={{ fontSize: '10px', color: '#888' }} />
                          )}
                        >
                          <Panel
                            header={<span className="text-xs text-stone-500">{t('details') || '详情'}</span>}
                            key="1"
                          >
                            <pre
                              className="text-xs overflow-auto p-2 rounded bg-stone-800 text-stone-300"
                              style={{ maxHeight: '200px' }}
                            >
                              {JSON.stringify(log.data, null, 2)}
                            </pre>
                          </Panel>
                        </Collapse>
                      )}
                    </div>
                  ))}
                </div>

                {/* 底部操作链接 - 始终显示刷新日志，有条件显示加载更多 */}
                <div className="flex w-full items-center mt-4">
                  <a
                    onClick={handleRefresh}
                    className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer"
                  >
                    {t('refresh_logs') || '刷新日志'}
                  </a>
                  {/* 始终显示加载更多链接，如果 hasMore 为 false 则显示为禁用状态 */}
                  <Divider type="vertical" className="bg-stone-600 mx-2" />
                  {hasMore ? (
                    <a
                      onClick={handleLoadMore}
                      className={`text-xs cursor-pointer ${loadingMore ? 'text-stone-500' : 'text-blue-400 hover:text-blue-300'}`}
                    >
                      {loadingMore ? (t('loading') || '加载中...') : (t('load_more') || '加载更多')}
                    </a>
                  ) : (
                    <span className="text-xs text-stone-600">
                      {t('no_more_logs') || '没有更多了'}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 日志统计 */}
      {logs.length > 0 && (
        <div className="text-center text-xs text-gray-400 mt-2">
          {t('total_logs', { count: total }) || `共 ${total} 条日志`}
        </div>
      )}
    </div>
  );
};

export default SystemLogs;
