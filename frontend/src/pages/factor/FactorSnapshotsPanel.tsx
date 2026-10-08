/**
 * 右栏「快照」页签：某因子的快照历史表 + 行点击 Drawer 回看完整结果（零重算）。
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App as AntApp, Card, Drawer, Popconfirm, Space, Table, type TableColumnsType } from 'antd';
import {
  factorApi,
  type FactorCatalogItem,
  type FactorSnapshotDetail,
  type FactorSnapshotSummary,
} from '@/api/factor';
import FactorResultView from './FactorResultView';
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
        // span 拦截冒泡：Popconfirm 弹层走 Portal，但 React 合成事件沿组件树冒泡，
        // 不拦截会在点确认/取消时同时触发行点击打开详情
        <span onClick={(e) => e.stopPropagation()}>
          <Popconfirm
            title={t('factor_snap_delete_confirm') || '删除该快照？parquet 将归档'}
            onConfirm={() => remove(r.id)}
          >
            <a style={{ color: '#ff4d4f' }}>{t('factor_snap_delete_btn') || '删除'}</a>
          </Popconfirm>
        </span>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        locale={{ emptyText: t('factor_snap_empty') || '暂无快照' }}
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
