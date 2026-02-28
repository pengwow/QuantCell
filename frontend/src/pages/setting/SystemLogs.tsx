/**
 * 系统日志组件
 * 功能：显示系统日志，支持刷新和加载更多
 */
import { useState, useEffect, useCallback } from 'react';
import { Button, Card, Spin, Empty, Tag, Collapse } from 'antd';
import { ReloadOutlined, DownOutlined } from '@ant-design/icons';
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
    <Card
      className="settings-panel"
      title={
        <div className="flex items-center justify-between">
          <span>{t('system_logs') || '系统日志'}</span>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
          >
            {t('refresh') || '刷新'}
          </Button>
        </div>
      }
      variant="outlined"
    >
      <Spin spinning={loading} tip={t('loading') || '加载中...'}>
        {logs.length === 0 ? (
          <Empty description={t('no_logs') || '暂无日志'} />
        ) : (
          <>
            {/* 日志显示区域 - 黑色终端风格 */}
            <div
              className="rounded-lg p-4 font-mono text-sm overflow-auto"
              style={{
                backgroundColor: '#1e1e1e',
                color: '#d4d4d4',
                maxHeight: '400px',
                minHeight: '200px',
              }}
            >
              {logs.map((log, index) => (
                <div key={log.id || index} className="mb-2">
                  <div className="flex items-start gap-2">
                    {/* 时间戳 */}
                    <span className="text-gray-500 shrink-0">
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
                        header={<span className="text-xs text-gray-500">{t('details') || '详情'}</span>}
                        key="1"
                      >
                        <pre
                          className="text-xs overflow-auto p-2 rounded"
                          style={{
                            backgroundColor: '#2d2d2d',
                            color: '#d4d4d4',
                            maxHeight: '200px',
                          }}
                        >
                          {JSON.stringify(log.data, null, 2)}
                        </pre>
                      </Panel>
                    </Collapse>
                  )}
                </div>
              ))}
            </div>

            {/* 加载更多按钮 */}
            {hasMore && (
              <div className="flex justify-center mt-4">
                <Button
                  onClick={handleLoadMore}
                  loading={loadingMore}
                  disabled={!hasMore}
                >
                  {t('load_more') || '加载更多'}
                </Button>
              </div>
            )}

            {/* 日志统计 */}
            <div className="text-center text-xs text-gray-400 mt-2">
              {t('total_logs', { count: total }) || `共 ${total} 条日志`}
            </div>
          </>
        )}
      </Spin>
    </Card>
  );
};

export default SystemLogs;
