/**
 * 右栏 ④ 模型：GET /models/unified（modelApi.unifiedModels，与模型页总表同源）。
 * 顶部是训练任务面板（TrainPanel，异步训练 + 进度），下方模型总表只读展示
 * （名称/阶段/算法/关键指标）；promote/unpromote 复用 UnifiedModelTable
 * 已确认的 API 契约（modelApi.promoteModel / unpromoteModel），规则一致：
 * 已注册且 stage!==production 可晋升，stage===production 可回退（unpromote 二次确认）。
 * 行动作已扩展训练→回测→部署闭环（P1 batch3）：回测 = ModelBacktestDrawer（工作台内嵌），
 * 部署 = DeployConfirmModal（paper 二次确认卡），部署成功后切换 worker + 决策流 Tab。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Empty, Space, Spin, Table, Tag, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import {
  CloudUploadOutlined,
  LineChartOutlined,
  ReloadOutlined,
  RocketOutlined,
  RollbackOutlined,
} from '@ant-design/icons';
import { modelApi } from '@/api/modelApi';
import type { UnifiedModelRow } from '@/api/modelApi';
import { useWorkbenchStore } from '../../store/workbenchStore';
import TrainPanel from './TrainPanel';
import ModelBacktestDrawer from './ModelBacktestDrawer';
import DeployConfirmModal from './DeployConfirmModal';
import type { DeployPrefill } from './DeployConfirmModal';

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

  // 「训练→回测→部署」闭环的行内动作状态（数据不进 store：两卡互斥、生命周期跟 Tab）
  const [btRow, setBtRow] = useState<UnifiedModelRow | null>(null);
  const [deployRow, setDeployRow] = useState<UnifiedModelRow | null>(null);
  const [deployPrefill, setDeployPrefill] = useState<DeployPrefill | null>(null);

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

  /** 回测抽屉「去部署」→ 关抽屉开确认卡（prefill 本次回测参数） */
  const handleGoDeploy = (prefill: DeployPrefill) => {
    if (!btRow) return;
    setDeployPrefill(prefill);
    setDeployRow(btRow);
    setBtRow(null);
  };

  /** 确认卡创建成功：切 worker 选择器到新进程 + 决策流 Tab（URL 由 Agent 既有回写同步） */
  const handleDeployed = (newWorkerId: number) => {
    const store = useWorkbenchStore.getState();
    if (store.workerId !== newWorkerId) store.setWorker(newWorkerId);
    store.setTab('decisions');
  };

  /** 总表直开部署：不带 prefill（确认卡走默认值） */
  const openDeploy = (row: UnifiedModelRow) => {
    setDeployPrefill(null);
    setDeployRow(row);
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
      width: 130,
      render: (_: unknown, row) => {
        if (!row.file_name) return null;
        return (
          <Space size={2}>
            <Tooltip title={t('wb_bt_action')}>
              <Button size="small" type="text" icon={<LineChartOutlined />} onClick={() => setBtRow(row)} />
            </Tooltip>
            <Tooltip title={t('wb_deploy_action')}>
              <Button size="small" type="text" icon={<CloudUploadOutlined />} onClick={() => openDeploy(row)} />
            </Tooltip>
            {row.registered && row.model_id && row.stage !== 'production' && (
              <Tooltip title={t('umt_action_promote')}>
                <Button size="small" type="text" icon={<RocketOutlined />} onClick={() => handlePromote(row.model_id!)} />
              </Tooltip>
            )}
            {row.registered && row.model_id && row.stage === 'production' && (
              <Tooltip title={t('umt_action_unpromote')}>
                <Button size="small" type="text" icon={<RollbackOutlined />} onClick={() => handleUnpromote(row.model_id!)} />
              </Tooltip>
            )}
          </Space>
        );
      },
    },
  ];

  if (!workerId) {
    return (
      <div className="wb-models">
        {/* 训练任务与 worker 无关，未选 worker 时仍可用 */}
        <TrainPanel onTrained={refresh} />
        <Empty description={t('wb_select_worker')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="wb-models">
      <TrainPanel onTrained={refresh} />
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

      {/* 行动作：回测抽屉（内嵌）与部署二次确认卡（互斥打开） */}
      <ModelBacktestDrawer row={btRow} onClose={() => setBtRow(null)} onDeploy={handleGoDeploy} />
      <DeployConfirmModal
        row={deployRow}
        prefill={deployPrefill}
        onClose={() => setDeployRow(null)}
        onDeployed={handleDeployed}
      />
    </div>
  );
}
