/**
 * Notification Store
 *
 * 站内通知收件箱状态：列表（游标分页）、未读数、全部已读。
 * 实时新通知由 App.tsx 的 ws 订阅推送进来（bumpUnread），列表数据按需 loadList 拉取。
 */

import { create } from 'zustand';
import { notificationApi } from '../api';
import type { InboxNotificationItem } from '../api';

// ponytail: 列表内存上限 500 条，超限截尾（收件箱页有游标分页兜底），
// 升级路径：store 只存 unreadCount，列表数据挪到页面组件自管
const MAX_ITEMS = 500;

interface NotificationState {
  items: InboxNotificationItem[];
  unreadCount: number;
  /** 已读条数（总数 - 未读），收件箱页「清空已读」按钮禁用态依据 */
  readCount: number;
  hasMore: boolean;
  loading: boolean;

  /** 拉取收件箱列表；beforeId 传游标（取更旧一页并追加），缺省为刷新第一页 */
  loadList: (opts?: { beforeId?: number; limit?: number }) => Promise<void>;
  /** 全部已读：调后端水位接口，成功后本地清零未读数 */
  markAllRead: () => Promise<void>;
  /** 删除单条：后端物理删除，本地移除并取回权威未读数 */
  removeItem: (id: number) => Promise<void>;
  /** 清空已读（保留未读）：后端删除后重拉第一页（本地无已读标记，无法精确过滤） */
  clearRead: (limit: number) => Promise<void>;
  /** ws 实时收到新通知：未读 +1 并插入列表头 */
  bumpUnread: (item: InboxNotificationItem) => void;
}

export const useNotificationStore = create<NotificationState>()((set, get) => ({
  items: [],
  unreadCount: 0,
  readCount: 0,
  hasMore: false,
  loading: false,

  loadList: async (opts) => {
    set({ loading: true });
    try {
      const beforeId = opts?.beforeId;
      const data = await notificationApi.getInbox({ limit: opts?.limit ?? 20, before_id: beforeId });
      set((state) => ({
        items: beforeId ? [...state.items, ...data.items] : data.items,
        hasMore: data.has_more,
        unreadCount: data.unread_count,
        // 游标加载旧页时 read_count 重复覆盖没关系：后续页里总数/未读不变，差值恒定
        readCount: beforeId ? state.readCount : data.read_count,
        loading: false,
      }));
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  markAllRead: async () => {
    await notificationApi.markInboxRead();
    set((state) => ({ unreadCount: 0, readCount: state.readCount + state.unreadCount }));
  },

  removeItem: async (id) => {
    // 未读条目必为 items 前缀（id 单调 + 新通知插头部），按 index 判断删除的是否已读
    const state = get();
    const idx = state.items.findIndex((it) => it.id === id);
    const { unread_count } = await notificationApi.deleteInboxItem(id);
    set((s) => ({
      items: s.items.filter((it) => it.id !== id),
      unreadCount: unread_count,
      readCount: Math.max(state.readCount + (idx >= state.unreadCount ? -1 : 0), 0),
    }));
  },

  clearRead: async (limit) => {
    await notificationApi.clearReadInbox();
    await get().loadList({ limit });
  },

  bumpUnread: (item) => {
    set((state) => ({
      unreadCount: state.unreadCount + 1,
      // 新通知是最新的，插头部；列表超限截尾
      items: [item, ...state.items].slice(0, MAX_ITEMS),
    }));
  },
}));
