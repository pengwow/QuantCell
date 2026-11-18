/**
 * 右栏 ④ 模型：GET /models/unified（modelApi.unifiedModels，与模型页总表同源）。
 * 只读展示（名称/阶段/算法/关键指标）；promote/unpromote 复用 UnifiedModelTable
 * 已确认的 API 契约（modelApi.promoteModel / unpromoteModel），规则一致：
 * 已注册且 stage!==production 可晋升，stage===production 可回退（unpromote 二次确认）。
 */
import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Empty, Spin, Table, Tag, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import { ReloadOutlined, RocketOutlined, RollbackOutlined } from '@ant-design/icons';
import { modelApi } from '@/api/modelApi';
import type { UnifiedModelRow } from '@/api/modelApi';
import { useWorkbenchStore } from '../../store/workbenchStore';

const STAGE_COLORS: Record<string, string> = {
  production: 'green',
  staging: 'gold',
  archived: 'default',
  '': 'default',
};

export default function ModelsTab() {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const workerId = useWorkbenchStore((s) => s.workerId);
  const entry = useWorkbenchStore((s) => s.models);

  const active = !!entry && entry.workerId === workerId;

  const refresh = useCallback(async () => {
    if (!workerId) return;
    try {
      const rows = await modelApi.unifiedModels();
      useWorkbenchStore.getState().setModels(workerId, Array.isArray(rows) ? rows : []);
    } catch (err) {
      message.error(t('wb_models_load_failed', { err: err instanceof Error ? err.message : String(err) }));
    }
  }, [workerId, message, t]);

  // 激活且当前 worker 无有效缓存时自动拉取（注册表低频变更，不轮询，手动刷新兜底）
  const autofetchedRef = useRef('');
  useEffect(() => {
    if (!workerId || active) {
      if (active) autofetchedRef.current = String(workerId);
      return;
    }
    if (autofetchedRef.current === String(workerId)) return;
    autofetchedRef.current = String(workerId);
    refresh();
  }, [workerId, active, refresh]);

  const handlePromote = async (modelId: string) => {
    try {
      await modelApi.promoteModel(modelId);
      message.success(t('umt_msg_promote_ok'));
      refresh();
    } catch (err) {
      message.error(t('umt_msg_promote_failed', { err: err instanceof Error ? err.message : String(err) }));
    }
  };

  const handleUnpromote = (modelId: string) => {
    modal.confirm({
      title: t('umt_action_unpromote'),
      content: t('umt_unpromote_confirm'),
      okText: t('umt_action_ok'),
      cancelText: t('umt_action_cancel'),
      onOk: async () => {
        try {
          await modelApi.unpromoteModel(modelId);
          message.success(t('umt_msg_unpromote_ok'));
          refresh();
        } catch (err) {
          message.error(t('umt_msg_unpromote_failed', { err: err instanceof Error ? err.message : String(err) }));
        }
      },
    });
  };

  const metricOf = (row: UnifiedModelRow): { key: string; value: number } | null => {
    const entries = Object.entries(row.metrics ?? {}).filter(([, v]) => typeof v === 'number');
    if (entries.length === 0) return null;
    const preferred = entries.find(([k]) => k === 'sharpe_ratio');
    return preferred ? { key: preferred[0], value: preferred[1] as number } : { key: entries[0][0], value: entries[0][1] as number };
  };

  const columns: TableColumnsType<UnifiedModelRow> = [
    {
      title: t('wb_model_name'),
      dataIndex: 'file_name',
      ellipsis: true,
      render: (v: string, row) => <Tooltip title={row.model_id || v}><span className="wb-nowrap-mono">{v}</span></Tooltip>,
    },
    {
      title: t('stage'),
      dataIndex: 'stage',
      width: 96,
      render: (v: string, row) =>
        row.registered ? (
          <Tag color={STAGE_COLORS[v] || 'default'}>{v || '-'}</Tag>
        ) : row.size_mb == null ? (
          <Tag color="red">{t('umt_status_missing')}</Tag>
        ) : (
          <Tag>{t('umt_status_unregistered')}</Tag>
        ),
    },
    { title: t('wb_algorithm'), dataIndex: 'algorithm', width: 80, render: (v: string) => v || '-' },
    {
      title: t('wb_key_metric'),
      width: 120,
      align: 'right',
      render: (_: unknown, row) => {
        const m = metricOf(row);
        return m ? <span className="wb-nowrap-mono">{m.key}: {m.value.toFixed(3)}</span> : '-';
      },
    },
    {
      title: t('action'),
      width: 110,
      render: (_: unknown, row) => {
        if (!row.registered || !row.model_id) return null;
        if (row.stage !== 'production') {
          return (
            <Tooltip title={t('umt_action_promote')}>
              <Button size="small" icon={<RocketOutlined />} onClick={() => handlePromote(row.model_id!)} />
            </Tooltip>
          );
        }
        return (
          <Tooltip title={t('umt_action_unpromote')}>
            <Button size="small" icon={<RollbackOutlined />} onClick={() => handleUnpromote(row.model_id!)} />
          </Tooltip>
        );
      },
    },
  ];

  if (!workerId) {
    return <Empty description={t('wb_select_worker')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div className="wb-models">
      <div className="wb-list-meta wb-models-toolbar">
        <span>{t('wb_models_from_registry')}</span>
        <Button size="small" icon={<ReloadOutlined />} onClick={refresh}>
          {t('refresh')}
        </Button>
      </div>
      {!active ? (
        <div className="wb-center-spin">
          <Spin size="small" />
        </div>
      ) : (
        <Table<UnifiedModelRow>
          size="small"
          rowKey={(r) => r.file_name}
          dataSource={entry.data}
          columns={columns}
          pagination={false}
          locale={{ emptyText: t('no_data') }}
        />
      )}
    </div>
  );
}
