/**
 * 站内通知收件箱页（/notifications）
 *
 * 页面 chrome 按规范收口（demo 无本页视图，基准 = 规范 + 已收口列表页）：
 * - §5 page-head：PageContainer 标题 16/650 + mono 真值副标「未读 x · 已读 y」
 *   （两值均为收件箱接口返回的权威计数）+ 右侧 ≤3 个 30px 动作钮
 * - §6.6 工具栏：读写态 Segmented（global.css §6.9 全局收口，页面不加钩子类）+ 任务域 Select
 * - §6.3 qc-card 列表 + §6.13 空态 QcEmpty；行渲染复用共享组件 InboxItemRow（其内部样式不在本页）
 * 列表按 id 倒序游标分页；未读数的权威值在收件箱接口返回的 unread_count（loadList 时同步进 store）。
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { DeleteOutlined } from '@ant-design/icons';
import { Button, Card, Flex, Popconfirm, Segmented, Select, Spin, Typography } from 'antd';

import { InboxItemRow, LEVEL_COLORS } from '@/components/NotificationInbox';
import PageContainer from '@/components/PageContainer';
import PageToolbar from '@/components/ui/PageToolbar';
import { QcEmpty } from '@/components/ui/DataTable';
import { useNotificationStore } from '@/store/notificationStore';
import { TASK_SOURCES } from '@/utils/taskRoutes';

// ponytail: 每页 20 条与后端默认一致；游标取当前列表最后一条 id
const PAGE_SIZE = 20;

const InboxPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { items, unreadCount, readCount, hasMore, loading, loadList, markAllRead, removeItem, clearRead } =
    useNotificationStore();

  // 过滤态是页面局部状态（不进 store：预览面板始终看全量，不受页面过滤影响）
  const [readFilter, setReadFilter] = useState<'all' | 'unread' | 'read'>('all');
  const [taskType, setTaskType] = useState<string | null>(null);

  const listParams = () => ({
    unread: readFilter === 'all' ? undefined : readFilter === 'unread',
    taskType: taskType ?? undefined,
  });

  const reload = useCallback(() => {
    void loadList({ limit: PAGE_SIZE, ...listParams() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadList, readFilter, taskType]);

  useEffect(() => {
    reload();
  }, [reload]);

  const loadOlder = () => {
    const last = items[items.length - 1];
    if (last) void loadList({ limit: PAGE_SIZE, beforeId: last.id, ...listParams() });
  };

  const handleMarkAllRead = () => {
    void markAllRead();
  };

  const handleClearRead = () => {
    void clearRead(PAGE_SIZE);
  };

  const handleDelete = (id: number) => {
    void removeItem(id);
  };

  return (
    <PageContainer
      title={t('message_center')}
      // 副标 = mono 真值口径行：未读 / 已读计数（store 内接口权威值，非本地估算）
      subtitle={`${t('filter_unread')} ${unreadCount} · ${t('filter_read')} ${readCount}`}
      actions={
        <>
          <Button
            danger
            disabled={readCount === 0}
            onClick={handleClearRead}
            style={{ height: 30, padding: '0 12px', fontSize: 12 }}
          >
            {t('clear_read')}
          </Button>
          <Button
            type="primary"
            disabled={unreadCount === 0}
            onClick={handleMarkAllRead}
            style={{ height: 30, padding: '0 12px', fontSize: 12, fontWeight: 550 }}
          >
            {t('mark_all_read')}
          </Button>
        </>
      }
    >
      <PageToolbar
        filters={
          <Flex gap={8} wrap>
            <Segmented
              value={readFilter}
              onChange={(v) => setReadFilter(v as 'all' | 'unread' | 'read')}
              options={[
                { label: t('filter_all'), value: 'all' },
                { label: t('filter_unread'), value: 'unread' },
                { label: t('filter_read'), value: 'read' },
              ]}
            />
            <Select
              allowClear
              aria-label={t('task_filter_placeholder')}
              placeholder={t('task_filter_placeholder')}
              value={taskType}
              onChange={(v) => setTaskType(v ?? null)}
              style={{ minWidth: 140 }}
              options={TASK_SOURCES.map((s) => ({ value: s, label: t(`task_type_${s}`) }))}
            />
          </Flex>
        }
      />

      <Card className="qc-card">
        <Spin spinning={loading && items.length === 0}>
          {items.length === 0 && !loading ? (
            <QcEmpty
              title={t('inbox_empty')}
              action={
                <button
                  type="button"
                  className="qc-mini-btn pri"
                  onClick={() => navigate('/setting/notifications')}
                >
                  {t('inbox_empty_action')}
                </button>
              }
            />
          ) : (
            // antd v6 的 List 已废弃，这里用原生 div 列表替代（分隔线用 --qc-border）
            <div>
              {items.map((item) => (
                <div
                  key={item.id}
                  className="group relative border-b py-3"
                  style={{ borderColor: 'var(--qc-border)' }}
                >
                  {/* 右侧留出 hover 删除按钮的位置，避免与时间戳重叠 */}
                  <div className="pr-9">
                    <InboxItemRow item={item} />
                  </div>
                  <div className="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100">
                    <Popconfirm
                      title={t('delete_notification_confirm')}
                      onConfirm={() => handleDelete(item.id)}
                      okButtonProps={{ danger: true }}
                    >
                      <Button
                        danger
                        size="small"
                        type="text"
                        icon={<DeleteOutlined />}
                        aria-label={t('delete')}
                      />
                    </Popconfirm>
                  </div>
                </div>
              ))}
              <div className="flex justify-center pt-3">
                {hasMore ? (
                  <Button loading={loading} onClick={loadOlder}>
                    {t('load_older')}
                  </Button>
                ) : (
                  <Typography.Text type="secondary">{t('no_more_notifications')}</Typography.Text>
                )}
              </div>
            </div>
          )}
        </Spin>
      </Card>

      {/* 级别图例：色点含义说明，避免用户猜颜色（色值取共享组件 LEVEL_COLORS，与行内圆点同源） */}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {(['info', 'success', 'warning', 'error'] as const).map((lv) => (
          <span
            key={lv}
            className="flex items-center gap-1.5"
            style={{ color: 'var(--qc-text-tertiary)', fontSize: 11 }}
          >
            <span className="size-1.5 rounded-full" style={{ background: LEVEL_COLORS[lv] }} />
            {t(`level_${lv}`)}
          </span>
        ))}
      </div>
    </PageContainer>
  );
};

export default InboxPage;
