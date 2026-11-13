/**
 * 站内通知收件箱页（/notifications）
 *
 * 列表（按 id 倒序游标分页）+ 全部已读 + 空状态引导去通知渠道配置。
 * 未读数的权威值在收件箱接口返回的 unread_count（loadList 时同步进 store）。
 */

import { use, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { DeleteOutlined } from '@ant-design/icons';
import { Badge, Button, Card, Empty, Popconfirm, Space, Spin, theme, Typography } from 'antd';

import { InboxItemRow, LEVEL_COLORS } from '@/components/NotificationInbox';
import { useNotificationStore } from '@/store/notificationStore';

// ponytail: 每页 20 条与后端默认一致；游标取当前列表最后一条 id
const PAGE_SIZE = 20;

const InboxPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const { items, unreadCount, readCount, hasMore, loading, loadList, markAllRead, removeItem, clearRead } =
    useNotificationStore();

  useEffect(() => {
    void loadList({ limit: PAGE_SIZE });
    // ponytail: 仅挂载拉取首页；此后实时新通知由 store.bumpUnread 增量插入
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadOlder = () => {
    const last = items[items.length - 1];
    if (last) void loadList({ limit: PAGE_SIZE, beforeId: last.id });
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
    <div className="mx-auto w-full max-w-[880px] px-4 py-4">
      <Card
        title={
          <Space size="small">
            <span>{t('message_center')}</span>
            {unreadCount > 0 && <Badge count={unreadCount} size="small" />}
          </Space>
        }
        extra={
          <Space size="small">
            <Button disabled={readCount === 0} onClick={handleClearRead} type="link">
              {t('clear_read')}
            </Button>
            <Button disabled={unreadCount === 0} onClick={handleMarkAllRead} type="link">
              {t('mark_all_read')}
            </Button>
          </Space>
        }
      >
        <Spin spinning={loading && items.length === 0}>
          {items.length === 0 && !loading ? (
            <Empty description={t('inbox_empty')}>
              <Button type="primary" onClick={() => navigate('/setting/notifications')}>
                {t('inbox_empty_action')}
              </Button>
            </Empty>
          ) : (
            // antd v6 的 List 已废弃，这里用原生 div 列表替代（分隔线用 token 边框色）
            <div>
              {items.map((item) => (
                <div
                  key={item.id}
                  className="group relative border-b py-3"
                  style={{ borderColor: token.colorBorderSecondary }}
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
                      <Button danger size="small" type="text" icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </div>
                </div>
              ))}
              <div className="flex justify-center pt-3">
                {hasMore ? (
                  <Button loading={loading} onClick={loadOlder} type="link">
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

      {/* 级别图例：色点含义说明，避免用户猜颜色 */}
      <div className="mt-2 flex flex-wrap items-center gap-3 px-1">
        {(['info', 'success', 'warning', 'error'] as const).map((lv) => (
          <span key={lv} className="flex items-center gap-1 text-xs text-foreground/60">
            <span className="size-1.5 rounded-full" style={{ background: LEVEL_COLORS[lv] }} />
            {t(`level_${lv}`)}
          </span>
        ))}
      </div>
    </div>
  );
};

export default InboxPage;
