import { useEffect, useState } from 'react';
import { message, Modal, Popconfirm, Table, type TableColumnsType } from 'antd';
import { factorApi, type FactorSnapshotSummary } from '@/api/factor';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';
const num = (v: number | null, digits = 3) => (v === null || v === undefined ? '—' : v.toFixed(digits));

const FactorSnapshotsModal: React.FC<{ factorName: string; open: boolean; onClose: () => void }> = ({
  factorName,
  open,
  onClose,
}) => {
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
      message.success('快照已删除');
      refresh();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const columns: TableColumnsType<FactorSnapshotSummary> = [
    {
      title: '保存时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string | null) => v?.replace('T', ' ').slice(0, 19) ?? '—',
    },
    { title: '周期/品种', render: (_, r) => `${r.params.interval} × ${r.params.instruments?.length ?? 0}` },
    { title: '样本数', dataIndex: 'bar_count', width: 90 },
    { title: 'IC 均值', dataIndex: 'ic_mean', render: (v: number | null) => num(v) },
    { title: 'ICIR', dataIndex: 'ic_ir', render: (v: number | null) => num(v) },
    { title: '多空收益', dataIndex: 'long_short_return', render: (v: number | null) => num(v, 4) },
    { title: 'IC 序列长', dataIndex: 'ic_series_len', width: 90 },
    {
      title: '操作',
      width: 90,
      render: (_, r) => (
        <Popconfirm title="删除该快照？parquet 将归档" onConfirm={() => remove(r.id)}>
          <a>删除</a>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Modal title={`快照历史：${factorName}`} open={open} onCancel={onClose} footer={null} width={900}>
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
