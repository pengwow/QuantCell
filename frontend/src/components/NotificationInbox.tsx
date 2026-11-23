/**
 * 站内收件箱共享小组件：级别色点、列表行、Popover 预览面板。
 *
 * 数据由 useNotificationStore 集：面板打开时按需 loadList 拉取，
 * 全部已读调 markAllRead（后端推水位，前端本地清零）。
 */

import { useEffect } from 'react';
import { Badge, Button, Empty, Spin, theme, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';

import { useNotificationStore } from '@/store/notificationStore';
import { taskNotificationRoute } from '@/utils/taskRoutes';
import type { InboxNotificationItem } from '@/api';
import { QUANT_COLORS } from '@/utils/colors';

/**
 * critical 等级暂无独立色相：palette 尚未注册 critical 槽位，
 * 现取值与 error 同源。palette 补槽位后改为派生即可。
 */
const CRITICAL_COLOR = QUANT_COLORS.negative;

/** level → 前景色（未知 level 按 info 兜底）。语义色全部来自 utils/colors（值源自 palettes.ts） */
export const LEVEL_COLORS: Record<string, string> = {
  info: QUANT_COLORS.info,
  success: QUANT_COLORS.positive,
  warning: QUANT_COLORS.warning,
  error: QUANT_COLORS.negative,
  critical: CRITICAL_COLOR,
};

/** 列表行：色点 + 标题（相对/绝对时间）。任务类通知点击 = 单条已读 + 跳转详情/列表页 */
export function InboxItemRow({ item }: { item: InboxNotificationItem }) {
  const navigate = useNavigate();
  const markRead = useNotificationStore((s) => s.markRead);

  const handleClick = () => {
    // 已读失败不影响跳转（后端幂等，下次点击会再置）
    if (!item.read) void markRead(item.id).catch(() => {});
    const route = taskNotificationRoute(item.source, {
      id: typeof item.metadata?.task_id === 'string' ? item.metadata.task_id : null,
      detail: item.metadata,
    });
    if (route) navigate(route);
  };

  return (
    <div
      className="flex cursor-pointer shrink-0 items-start gap-2 overflow-hidden"
      onClick={handleClick}
    >
      <span
        className="mt-[7px] size-1.5 shrink-0 rounded-full"
        style={{ background: LEVEL_COLORS[item.level] ?? LEVEL_COLORS.info }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <Typography.Text
            ellipsis
            className={`text-[13px] leading-[20px] ${item.read ? 'text-foreground/60' : 'font-medium'}`}
          >
            {item.title}
          </Typography.Text>
          <Typography.Text type="secondary" className="shrink-0 text-[11px] leading-[20px]">
            {item.created_at
              ? dayjs(item.created_at).format('MM-DD HH:mm')
              : ''}
          </Typography.Text>
        </div>
        {item.content && (
          <Typography.Paragraph
            ellipsis={{ rows: 2, tooltip: item.content }}
            type="secondary"
            className="!mb-0 !text-[12px] !leading-[18px]"
          >
            {item.content}
          </Typography.Paragraph>
        )}
      </div>
    </div>
  );
}

/**
 * 收件箱预览面板（Sider 消息项的 Popover 内容，也可以复用于其他入口）。
 * 打开时拉取最近 pageSize 条；底部「全部已读」+「查看全部」。
 */
export function NotificationPanel({ pageSize = 15, onViewAll }: { pageSize?: number; onViewAll?: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const { items, unreadCount, hasMore, loading, loadList, markAllRead } = useNotificationStore();

  useEffect(() => {
    void loadList({ limit: pageSize });
    // ponytail: 挂载拉一次即可，面板生命周期短；实时新消息通过 store 的 bumpUnread 增量出现
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const goInbox = () => {
    onViewAll?.();
    navigate('/notifications');
  };

  return (
    <div className="w-[320px]">
      <div className="flex items-center justify-between pb-1">
        <span className="text-sm font-medium">{t('message_center')}</span>
        {unreadCount > 0 && (
          <Button size="small" type="link" onClick={() => void markAllRead()}>
            {t('mark_all_read')}
          </Button>
        )}
      </div>

      <Spin spinning={loading && items.length === 0} size="small">
        {items.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('inbox_empty')} className="!my-2" />
        ) : (
          <div className="flex max-h-[360px] flex-col gap-3 overflow-y-auto py-1">
            {items.map((item) => (
              <InboxItemRow key={item.id} item={item} />
            ))}
          </div>
        )}
      </Spin>

      <div className="flex items-center justify-between border-t border-solid pt-1" style={{ borderColor: token.colorSplit }}>
        {hasMore ? (
          <Button
            size="small"
            type="link"
            onClick={() => {
              const last = items[items.length - 1];
              if (last) void loadList({ limit: pageSize, beforeId: last.id });
            }}
          >
            {t('load_older')}
          </Button>
        ) : (
          <span />
        )}
        <Badge count={unreadCount} size="small" offset={[-2, 2]}>
          <Button size="small" type="link" onClick={goInbox}>
            {t('view_all')}
          </Button>
        </Badge>
      </div>
    </div>
  );
}
