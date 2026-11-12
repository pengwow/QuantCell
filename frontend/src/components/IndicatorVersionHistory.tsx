/**
 * 指标版本历史（原「指标实验室」的版本管理能力迁入图表页指标编辑器）：
 * 每次保存/回滚自动生成快照，支持两两代码对比（Monaco DiffEditor）与回滚。
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Checkbox, Empty, Flex, Modal, Popconfirm, Space, Spin, Table, Tag } from 'antd';
import { DiffEditor } from '@monaco-editor/react';

import { indicatorApi, type Indicator, type IndicatorVersion } from '@/api';
import { useGuestRestriction } from '@/hooks/useGuestRestriction';

const SOURCE_COLOR: Record<string, string> = {
  create: 'green',
  save: 'blue',
  rollback: 'orange',
};

interface IndicatorVersionHistoryProps {
  indicatorId: number;
  /** 回滚成功后回调：编辑器用返回的最新指标更新本地代码 */
  onRolledBack: (indicator: Indicator) => void;
}

const IndicatorVersionHistory = ({ indicatorId, onRolledBack }: IndicatorVersionHistoryProps) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { getButtonDisabled, getButtonTooltip } = useGuestRestriction();

  const [versions, setVersions] = useState<IndicatorVersion[]>([]);
  const [loading, setLoading] = useState(false);
  // 至多勾选两个版本做对比
  const [diffVersions, setDiffVersions] = useState<[number, number] | null>(null);
  const [diffData, setDiffData] = useState<{ a: IndicatorVersion; b: IndicatorVersion } | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);

  const loadVersions = useCallback(async () => {
    setLoading(true);
    try {
      setVersions(await indicatorApi.getIndicatorVersions(indicatorId));
    } finally {
      setLoading(false);
    }
  }, [indicatorId]);

  useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  const handleDiff = useCallback(async () => {
    if (!diffVersions) return;
    const [a, b] = diffVersions;
    setDiffLoading(true);
    try {
      setDiffData(await indicatorApi.diffIndicatorVersions(indicatorId, a, b));
    } catch (err) {
      message.error(`${t('indicatorVersion.diff_failed')}: ${err}`);
    } finally {
      setDiffLoading(false);
    }
  }, [diffVersions, indicatorId, message, t]);

  const handleRollback = useCallback(
    async (versionNo: number) => {
      setRollbackLoading(true);
      try {
        // 回滚 = 生成 rollback 新快照并在服务端切换当前版本，历史不丢失
        const updated = await indicatorApi.rollbackIndicatorVersion(indicatorId, versionNo);
        message.success(`${t('indicatorVersion.rollback_success')} v${updated.version ?? '?'}`);
        await loadVersions();
        onRolledBack(updated);
      } catch (err) {
        message.error(`${t('indicatorVersion.rollback_failed')}: ${err}`);
      } finally {
        setRollbackLoading(false);
      }
    },
    [indicatorId, message, t, loadVersions, onRolledBack],
  );

  const columns = [
    { title: t('indicatorVersion.version'), dataIndex: 'version_no', width: 80, render: (v: number) => `v${v}` },
    {
      title: t('indicatorVersion.source'),
      dataIndex: 'source',
      width: 100,
      render: (s: string, record: IndicatorVersion) => (
        <Space size={4}>
          <Tag color={SOURCE_COLOR[s] || 'default'}>{s}</Tag>
          {record.is_current && <Tag color="gold">{t('indicatorVersion.current')}</Tag>}
        </Space>
      ),
    },
    { title: t('indicatorVersion.snapshot_name'), dataIndex: 'name', ellipsis: true },
    { title: t('indicatorVersion.time'), dataIndex: 'created_at', width: 170 },
    {
      title: t('indicatorVersion.actions'),
      key: 'actions',
      width: 200,
      render: (_: unknown, record: IndicatorVersion) => {
        const checked = diffVersions?.includes(record.version_no) ?? false;
        return (
          <Space size={4}>
            <Checkbox
              checked={checked}
              onChange={(e) => {
                const no = record.version_no;
                if (e.target.checked) {
                  // 至多保留两个勾选：新勾选挤掉最早的
                  setDiffVersions((prev) => (prev ? (prev.includes(no) ? prev : [prev[1], no]) : [no, no]));
                } else {
                  setDiffVersions(null);
                }
              }}
            />
            <Popconfirm
              title={t('indicatorVersion.rollback_confirm', { version: `v${record.version_no}` })}
              onConfirm={() => void handleRollback(record.version_no)}
              okButtonProps={{ loading: rollbackLoading }}
            >
              <Button size="small" disabled={getButtonDisabled()} title={getButtonTooltip()}>
                {t('indicatorVersion.rollback')}
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Flex vertical gap={12}>
      <Flex justify="space-between" align="center">
        <span>{t('indicatorVersion.hint')}</span>
        <Button type="primary" disabled={!diffVersions} loading={diffLoading} onClick={() => void handleDiff()}>
          {t('indicatorVersion.diff_selected')}
        </Button>
      </Flex>
      <Table
        size="small"
        rowKey="version_no"
        loading={loading}
        pagination={false}
        dataSource={versions}
        columns={columns}
        locale={{ emptyText: <Empty description={t('indicatorVersion.no_versions')} /> }}
      />

      {/* 版本对比弹窗：Monaco DiffEditor 渲染两个快照的代码差异 */}
      <Modal
        open={diffVersions !== null}
        title={
          diffVersions
            ? `${t('indicatorVersion.diff_title')} v${diffVersions[0]} ↔ v${diffVersions[1]}`
            : t('indicatorVersion.diff_title')
        }
        footer={null}
        onCancel={() => {
          setDiffVersions(null);
          setDiffData(null);
        }}
        width={960}
        destroyOnHidden
      >
        {diffData?.a && diffData?.b ? (
          <DiffEditor
            height="560px"
            language="python"
            theme="vs-dark"
            original={diffData.a.code ?? ''}
            modified={diffData.b.code ?? ''}
            options={{ renderSideBySide: true, minimap: { enabled: false } }}
          />
        ) : diffVersions ? (
          <Spin style={{ display: 'block', margin: '40px auto' }} />
        ) : (
          <Empty />
        )}
      </Modal>
    </Flex>
  );
};

export default IndicatorVersionHistory;
