/**
 * LLM 挖掘历史：运行记录列表（自动刷新进行中）+ 详情 Drawer（回看结果 / 复用参数 / 删除）。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App as AntApp,
  Button,
  Card,
  Drawer,
  Flex,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import {
  factorApi,
  type FactorMineLLMParams,
  type MiningRunDetail,
  type MiningRunStatus,
  type MiningRunSummary,
} from '@/api/factor';
import MiningResultView from './MiningResultView';

const STATUS_COLOR: Record<MiningRunStatus, string> = {
  running: 'processing',
  completed: 'green',
  failed: 'error',
  interrupted: 'default',
};

const MiningHistoryPane: React.FC<{
  onMined?: (name: string) => void;
  onReuse: (params: FactorMineLLMParams) => void;
}> = ({ onMined, onReuse }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [rows, setRows] = useState<MiningRunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<MiningRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const reqToken = useRef(0);

  const statusLabel = (s: MiningRunStatus) => t(`factor_mining_run_${s}`) || s;
  const fmtTime = (iso: string | null) => (iso ? iso.replace('T', ' ').slice(0, 16) : '—');

  const refresh = useCallback(async () => {
    const token = ++reqToken.current;
    setLoading(true);
    try {
      const r = await factorApi.listMineRuns(20, (page - 1) * 20);
      if (token === reqToken.current) {
        setRows(r.runs);
        setTotal(r.total);
      }
    } catch {
      /* 列表刷新失败保留旧数据 */
    } finally {
      if (token === reqToken.current) setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 仅当列表存在进行中记录时 10s 轮询
  const hasRunning = rows.some((r) => r.status === 'running');
  useEffect(() => {
    if (!hasRunning) return;
    const timer = setInterval(() => void refresh(), 10_000);
    return () => clearInterval(timer);
  }, [hasRunning, refresh]);

  const openDetail = async (id: number) => {
    setDetailLoading(true);
    try {
      setDetail(await factorApi.getMineRun(id));
    } catch (e) {
      message.error((e as Error)?.message || '加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await factorApi.deleteMineRun(id);
      message.success(t('factor_mining_toast_run_deleted') || '记录已删除');
      setDetail(null);
      void refresh();
    } catch (e) {
      message.error((e as Error)?.message || '删除失败');
    }
  };

  const columns: TableColumnsType<MiningRunSummary> = [
    {
      title: t('factor_mining_history_col_time') || '开始时间',
      dataIndex: 'created_at',
      width: 150,
      render: (v: string | null) => fmtTime(v),
    },
    {
      title: t('factor_wb_form_instruments') || '品种',
      key: 'symbols',
      width: 160,
      render: (_, r) => (r.params.instruments ?? []).join(', '),
    },
    {
      title: t('factor_wb_form_interval') || '周期',
      key: 'interval',
      width: 80,
      render: (_, r) => r.params.interval,
    },
    {
      title: t('factor_mining_history_col_rounds') || '轮×候选',
      key: 'shape',
      width: 90,
      render: (_, r) => `${r.params.n_rounds}×${r.params.n_candidates}`,
    },
    {
      title: t('factor_mining_col_status') || '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: MiningRunStatus) => (
        <Tag color={STATUS_COLOR[s]} style={{ marginInlineEnd: 0 }}>
          {statusLabel(s)}
        </Tag>
      ),
    },
    {
      title: t('factor_mining_history_col_stats') || '生成/成功/失败',
      key: 'stats',
      width: 130,
      render: (_, r) =>
        r.stats
          ? `${r.stats.generated}/${r.stats.succeeded}/${r.stats.failed}`
          : '—',
    },
    {
      title: t('factor_mining_col_action') || '操作',
      key: 'actions',
      width: 150,
      render: (_, r) => (
        <Flex gap="small">
          <Button size="small" onClick={() => void openDetail(r.id)}>
            {t('factor_mining_history_detail') || '详情'}
          </Button>
          <Popconfirm
            title={t('factor_mining_history_delete_confirm') || '删除该挖掘记录？'}
            okText={t('factor_mining_btn_delete') || '删除'}
            cancelText={t('factor_lib_cancel') || '取消'}
            disabled={r.status === 'running'}
            onConfirm={() => void remove(r.id)}
          >
            <Button size="small" danger disabled={r.status === 'running'}>
              {t('factor_mining_btn_delete') || '删除'}
            </Button>
          </Popconfirm>
        </Flex>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Table<MiningRunSummary>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showSizeChanger: false,
          onChange: setPage,
        }}
        locale={{ emptyText: t('factor_mining_history_empty') || '暂无挖掘记录' }}
      />

      <Drawer
        open={!!detail}
        title={
          detail
            ? `${t('factor_mining_history_detail_title') || '挖掘记录'} #${detail.id}`
            : ''
        }
        size={900}
        onClose={() => setDetail(null)}
        extra={
          detail && (
            <Flex gap="small">
              <Button size="small" onClick={() => onReuse(detail.params)}>
                {t('factor_mining_btn_reuse') || '复用参数重挖'}
              </Button>
            </Flex>
          )
        }
      >
        {detail && (
          <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
            <Flex gap="middle" align="center" wrap>
              <Tag color={STATUS_COLOR[detail.status]} style={{ marginInlineEnd: 0 }}>
                {statusLabel(detail.status)}
              </Tag>
              <span style={{ color: '#8c8c8c' }}>
                {fmtTime(detail.created_at)} ~ {fmtTime(detail.finished_at)}
              </span>
            </Flex>
            {detail.status === 'failed' && detail.error && (
              <Typography.Text type="danger" style={{ whiteSpace: 'pre-wrap' }}>
                {detail.error}
              </Typography.Text>
            )}
            {detail.status === 'interrupted' && (
              <Typography.Text type="secondary">
                {t('factor_mining_run_interrupted_tip') ||
                  '任务因服务重启或过期中断，可点击右上角「复用参数重挖」'}
              </Typography.Text>
            )}
            <Card loading={detailLoading}>
              {detail.result ? (
                <MiningResultView result={detail.result} onMined={onMined} />
              ) : (
                <span style={{ color: '#8c8c8c' }}>
                  {t('factor_mining_history_no_result') || '该记录没有可回看的挖掘结果'}
                </span>
              )}
            </Card>
          </Space>
        )}
      </Drawer>
    </Space>
  );
};

export default MiningHistoryPane;
