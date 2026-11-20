/**
 * 右栏工作面板数据流 hook：
 * - 按激活 Tab 轮询对应端点（真数据），结果写入 workbenchStore 缓存；
 * - worker 变化时拉起/断开日志 SSE（长连接挂 store，随 Tab 切换保持）。
 *
 * 轮询间隔取舍（对齐仓库既有口径，见报告）：
 * - decisions 5s（demo ~4s，后端端点每次全量读录制文件尾部，不宜更密）
 * - positions/orders 5s（与 WorkerPositionSection 的 5s 轮询同口径）
 * - performance / models 由各自 Tab 组件自管（performance 有时间窗状态、models 不轮询）
 */
import { useCallback, useEffect, useRef } from 'react';
import { workerApi, getWorkerDecisions, WorkerLogStreamSSE } from '@/api/workerApi';
import { useWorkbenchStore } from '../store/workbenchStore';
import type { WorkbenchTab } from '../store/workbenchStore';
import type { WorkerLog } from '@/types/worker';

const TAB_INTERVALS: Partial<Record<WorkbenchTab, number>> = {
  decisions: 5000,
  positions: 5000,
};

export function useWorkbenchData() {
  const workerId = useWorkbenchStore((s) => s.workerId);
  const activeTab = useWorkbenchStore((s) => s.activeTab);

  const fetchActive = useCallback(async () => {
    if (!workerId) return;
    const s = useWorkbenchStore.getState();
    try {
      switch (s.activeTab) {
        case 'decisions': {
          const data = await getWorkerDecisions(workerId, 200);
          s.setDecisions(workerId, { total: data?.total ?? 0, decisions: data?.decisions ?? [] });
          break;
        }
        case 'positions': {
          const [positions, orders] = await Promise.allSettled([
            workerApi.getPositions(workerId, { status: 'OPEN' }),
            workerApi.getOrders(workerId),
          ]);
          if (positions.status === 'fulfilled') s.setPositions(workerId, positions.value ?? []);
          if (orders.status === 'fulfilled') s.setOrders(workerId, orders.value?.items ?? []);
          break;
        }
        default:
          break;
      }
    } catch (err) {
      // 静默降级：面板数据失败不打断聊天；缓存保留上一次成功值
      console.warn('[workbench] fetch failed:', err);
    }
  }, [workerId]);

  // Tab/worker 变化：立即拉一次 + 按间隔轮询（间隔随 Tab 走）
  useEffect(() => {
    if (!workerId) return;
    fetchActive();
    const interval = TAB_INTERVALS[activeTab];
    if (!interval) return;
    const timer = window.setInterval(fetchActive, interval);
    return () => window.clearInterval(timer);
  }, [workerId, activeTab, fetchActive]);

  // 日志 SSE：仅 worker 变化时重建连接；Tab 切换不断流（logs 挂 store）
  const streamRef = useRef<WorkerLogStreamSSE | null>(null);
  useEffect(() => {
    if (!workerId) {
      streamRef.current?.disconnect();
      streamRef.current = null;
      return;
    }
    if (streamRef.current && streamRef.current.workerId === workerId) return;

    streamRef.current?.disconnect();
    const store = useWorkbenchStore.getState();
    store.clearLogs();
    const stream = new WorkerLogStreamSSE(workerId);
    streamRef.current = stream;
    stream.onOpen(() => useWorkbenchStore.getState().setLogConnected(true));
    stream.onClose(() => useWorkbenchStore.getState().setLogConnected(false));
    stream.onMessage((raw: Partial<WorkerLog>) => {
      // 事件载荷为后端 log_entry（timestamp/level/message/worker_id），history 与 log
      // 两种事件同一回调；id 非后端契约，仅作展示序号用 0 兜底（列表以 index 作 key）
      useWorkbenchStore.getState().appendLog({
        id: 0,
        worker_id: Number(raw.worker_id ?? workerId),
        level: String(raw.level ?? 'INFO'),
        message: String(raw.message ?? ''),
        source: raw.source,
        timestamp: String(raw.timestamp ?? ''),
      });
    });

    // 延后一拍建连：StrictMode mount→cleanup→mount 时首次 EventSource 尚未建立即被
    // close，浏览器控制台会报 net::ERR_ABORTED（与 WorkerLogsPanel 同款处理）
    const connectTimer = window.setTimeout(() => stream.connect(), 0);
    return () => {
      // ponytail: 重连计数在 WorkerLogStreamSSE 内部（上限 5 次），超限断开后需重挂载才会再连
      window.clearTimeout(connectTimer);
      stream.disconnect();
      if (streamRef.current === stream) streamRef.current = null;
      useWorkbenchStore.getState().setLogConnected(false);
    };
  }, [workerId]);
}
