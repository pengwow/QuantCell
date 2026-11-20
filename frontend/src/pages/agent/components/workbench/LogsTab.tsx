/**
 * 右栏 ⑤ 日志：SSE 实时日志流（GET /workers/{id}/monitoring/logs/stream，含 history 回放）。
 * 连接由 useWorkbenchData 挂在 store 上（worker 变化才重建），本组件只做展示：
 * 级别着色 / 自动滚动（贴底才跟随）/ 暂停 / 清空。demo 的 WS 口径换成后端推荐的 SSE：
 * 断线自动重连由 WorkerLogStreamSSE 内建（上限 5 次），token 走 query 与既有页一致。
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Empty, Space } from 'antd';
import { ClearOutlined, PauseCircleOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useWorkbenchStore } from '../../store/workbenchStore';
import type { WorkerLog } from '@/types/worker';

const LEVEL_COLORS: Record<string, string> = {
  ERROR: 'var(--agent-down)',
  WARNING: 'var(--agent-warn)',
  WARN: 'var(--agent-warn)',
};

export default function LogsTab() {
  const { t } = useTranslation();
  const workerId = useWorkbenchStore((s) => s.workerId);
  const logs = useWorkbenchStore((s) => s.logs);
  const connected = useWorkbenchStore((s) => s.logConnected);
  const clearLogs = useWorkbenchStore((s) => s.clearLogs);
  const [paused, setPaused] = useState(false);
  // 暂停时冻结的展示快照：恢复后跟上最新
  const [frozen, setFrozen] = useState<WorkerLog[] | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (paused) {
      setFrozen(logs);
    } else {
      setFrozen(null);
    }
    // 仅响应 paused 翻转；logs 的高频更新不重渲染快照
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused]);

  useEffect(() => {
    if (paused) return;
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs, paused]);

  if (!workerId) {
    return <Empty description={t('wb_select_worker')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const visible = paused ? (frozen ?? []) : logs;

  return (
    <div className="wb-logs">
      <div className="wb-logs-toolbar">
        <Space size={6} align="center">
          <span className={`qc-chip ${connected ? 'ok' : 'quiet'}`}>
            {connected && <span className="qc-pdot" />}
            {connected ? t('wb_log_connected') : t('wb_log_disconnected')}
          </span>
          <Button
            size="small"
            icon={paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            onClick={() => setPaused(!paused)}
          >
            {paused ? t('wb_log_resume') : t('wb_log_pause')}
          </Button>
          <Button size="small" icon={<ClearOutlined />} onClick={clearLogs}>
            {t('wb_log_clear')}
          </Button>
        </Space>
      </div>
      <div className="wb-log-stream" ref={listRef}>
        {visible.length === 0 ? (
          <div className="wb-log-empty">{t('no_data')}</div>
        ) : (
          visible.map((log, idx) => (
            <div key={idx} className="wb-log-line">
              <span className="wb-log-ts">{(log.timestamp || '').slice(11, 23)}</span>
              <span className="wb-log-level" style={{ color: LEVEL_COLORS[log.level.toUpperCase()] || 'inherit' }}>
                {log.level.toUpperCase()}
              </span>
              <span className="wb-log-msg">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
