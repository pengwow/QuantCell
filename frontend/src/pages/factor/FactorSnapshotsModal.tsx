import { useEffect, useState } from 'react';
import { message, Modal, Popconfirm, Table, type TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { factorApi, type FactorSnapshotSummary } from '@/api/factor';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';
const num = (v: number | null, digits = 3) => (v === null || v === undefined ? '—' : v.toFixed(digits));

const FactorSnapshotsModal: React.FC<{ factorName: string; open: boolean; onClose: () => void }> = ({
  factorName,
  open,
  onClose,
}) => {
  const { t } = useTranslation();
  const [rows, setRows] = useState<FactorSnapshotSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = () => {
    setLoading(true);
    factorApi
      .listSnapshots(factorName)
      .then((r) => setRows(r.snapshots))
      .catch((e) => message.error(errMsg(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (open) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, factorName]);

  const remove = async (id: number) => {
    try {
      await factorApi.deleteSnapshot(id);
      message.success(t('factor_snap_deleted') || '快照已删除');
      refresh();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const columns: TableColumnsType<FactorSnapshotSummary> = [
    {
      title: t('factor_snap_col_time') || '保存时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string | null) => v?.replace('T', ' ').slice(0, 19) ?? '—',
    },
    {
      title: t('factor_snap_col_scope') || '周期/品种',
      render: (_, r) => `${r.params.interval} × ${r.params.instruments?.length ?? 0}`,
    },
    { title: t('factor_snap_col_samples') || '样本数', dataIndex: 'bar_count', width: 90 },
    { title: t('factor_stat_ic_mean') || 'IC 均值', dataIndex: 'ic_mean', render: (v: number | null) => num(v) },
    { title: t('factor_stat_icir') || 'ICIR', dataIndex: 'ic_ir', render: (v: number | null) => num(v) },
    {
      title: t('factor_stat_ls_return') || '多空收益',
      dataIndex: 'long_short_return',
      render: (v: number | null) => num(v, 4),
    },
    { title: t('factor_snap_col_ic_len') || 'IC 序列长', dataIndex: 'ic_series_len', width: 90 },
    {
      title: t('factor_snap_col_action') || '操作',
      width: 90,
      render: (_, r) => (
        <Popconfirm
          title={t('factor_snap_delete_confirm') || '删除该快照？parquet 将归档'}
          onConfirm={() => remove(r.id)}
        >
          <a>{t('factor_snap_delete_btn') || '删除'}</a>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Modal
      title={`${t('factor_snap_history_title') || '快照历史'}：${factorName}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={900}
    >
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={{ pageSize: 10 }}
      />
    </Modal>
  );
};

export default FactorSnapshotsModal;
