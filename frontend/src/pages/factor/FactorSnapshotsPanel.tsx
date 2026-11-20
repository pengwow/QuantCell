/**
 * 右栏「快照」页签：某因子的快照历史表 + 行点击 Drawer 回看完整结果（零重算）。
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App as AntApp, Card, Drawer, Flex, Popconfirm, Space, Tooltip, type TableColumnsType } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import {
  factorApi,
  type FactorCatalogItem,
  type FactorSnapshotDetail,
  type FactorSnapshotSummary,
} from '@/api/factor';
import FactorResultView from './FactorResultView';
import DataTable from '@/components/ui/DataTable';
import { num } from './factorMeta';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';

const FactorSnapshotsPanel: React.FC<{
  factor: FactorCatalogItem;
  onChanged: () => void;
}> = ({ factor, onChanged }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [rows, setRows] = useState<FactorSnapshotSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<FactorSnapshotDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // 切因子/快速重取时丢弃过期列表响应
  const reqToken = useRef(0);

  const refresh = () => {
    const token = ++reqToken.current;
    setLoading(true);
    factorApi
      .listSnapshots(factor.name)
      .then((r) => {
        if (token === reqToken.current) setRows(r.snapshots);
      })
      .catch((e) => message.error(errMsg(e)))
      .finally(() => {
        if (token === reqToken.current) setLoading(false);
      });
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [factor.name]);

  const openDetail = async (id: number) => {
    setDetailLoading(true);
    setDetail(null);
    try {
      setDetail(await factorApi.getSnapshot(id));
    } catch (e) {
      // 快照可能已被删：提示并刷新列表
      message.error(errMsg(e));
      refresh();
    } finally {
      setDetailLoading(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await factorApi.deleteSnapshot(id);
      message.success(t('factor_snap_deleted') || '快照已删除');
      refresh();
      onChanged();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const columns: TableColumnsType<FactorSnapshotSummary> = [
    {
      title: t('factor_snap_col_time') || '保存时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string | null) =>
        v ? (
          <span className="qc-cell-time qc-mono">{v.replace('T', ' ').slice(0, 19)}</span>
        ) : (
          <span className="qc-cell-none qc-mono">—</span>
        ),
    },
    {
      title: t('factor_snap_col_scope') || '周期/标的',
      render: (_, r) => (
        <span className="qc-mono">{`${r.params.interval} × ${r.params.instruments?.length ?? 0}`}</span>
      ),
    },
    {
      title: t('factor_snap_col_samples') || '样本数',
      dataIndex: 'bar_count',
      width: 84,
      align: 'right',
      render: (v: number) => <span className="qc-mono">{v}</span>,
    },
    {
      title: t('factor_stat_ic_mean') || 'IC 均值',
      dataIndex: 'ic_mean',
      width: 88,
      align: 'right',
      render: (v: number | null) =>
        v == null ? <span className="qc-cell-none qc-mono">—</span> : <span className="qc-mono">{num(v)}</span>,
    },
    {
      title: t('factor_stat_icir') || 'ICIR',
      dataIndex: 'ic_ir',
      width: 76,
      align: 'right',
      render: (v: number | null) =>
        v == null ? <span className="qc-cell-none qc-mono">—</span> : <span className="qc-mono">{num(v)}</span>,
    },
    {
      title: t('factor_stat_ls_return') || '多空收益',
      dataIndex: 'long_short_return',
      width: 92,
      align: 'right',
      render: (v: number | null) =>
        v == null ? <span className="qc-cell-none qc-mono">—</span> : <span className="qc-mono">{num(v, 4)}</span>,
    },
    {
      title: t('factor_snap_col_ic_len') || 'IC 序列长',
      dataIndex: 'ic_series_len',
      width: 90,
      align: 'right',
      render: (v: number) => <span className="qc-mono">{v}</span>,
    },
    {
      title: t('factor_snap_col_action') || '操作',
      width: 64,
      render: (_, r) => (
        // span 拦截冒泡：Popconfirm 弹层走 Portal，但 React 合成事件沿组件树冒泡，
        // 不拦截会在点确认/取消时同时触发行点击打开详情
        <Flex onClick={(e) => e.stopPropagation()}>
          <Popconfirm
            title={t('factor_snap_delete_confirm') || '删除该快照？parquet 将归档'}
            onConfirm={() => remove(r.id)}
          >
            <Tooltip title={t('factor_snap_delete_btn')}>
              <button
                type="button"
                className="qc-mini-btn qc-icon-only danger"
                aria-label={t('factor_snap_delete_btn')}
              >
                <DeleteOutlined />
              </button>
            </Tooltip>
          </Popconfirm>
        </Flex>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <DataTable
        rowKey="id"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        emptyTitle={t('factor_snap_empty') || '暂无快照'}
        onRow={(r) => ({
          onClick: () => openDetail(r.id),
          style: { cursor: 'pointer' },
        })}
      />
      <Drawer
        title={
          detail
            ? t('factor_snap_detail_title', { id: detail.id }) || `快照详情（#${detail.id}）`
            : t('factor_snap_history_title') || '快照历史'
        }
        open={detailLoading || !!detail}
        size={1000}
        onClose={() => setDetail(null)}
        destroyOnHidden
      >
        {detailLoading || !detail ? (
          <Card loading />
        ) : (
          <FactorResultView result={detail.result} />
        )}
      </Drawer>
    </Space>
  );
};

export default FactorSnapshotsPanel;
