/**
 * 指标实验室（P2-08）：指标 IDE，聚焦「版本管理 + 沙箱预览」两个能力。
 *
 * - 沙箱预览：未保存的草稿代码也能在后端一次性求值（限 2s），验证指标输出
 * - 版本历史：每次保存自动生成快照，可两两对比（Monaco DiffEditor）、可回滚
 *             （回滚 = 生成 rollback 新快照，历史不丢失）
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Empty,
  Flex,
  List,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { DiffEditor, Editor } from '@monaco-editor/react';
import { IconPlayerPlay } from '@tabler/icons-react';

import { indicatorApi, type Indicator, type IndicatorPreviewResult, type IndicatorVersion } from '@/api';
import { useGuestRestriction } from '@/hooks/useGuestRestriction';

const SOURCE_COLOR: Record<string, string> = {
  create: 'green',
  save: 'blue',
  rollback: 'orange',
};

/** plot 序列的统计摘要（预览结果比全部数据点更适合平铺展示） */
interface PlotSummary {
  name: string;
  color: string;
  count: number;
  latest: string;
  max: string;
  min: string;
}

function summarizePlot(data: Array<number | null>): PlotSummary | null {
  const values = data.filter((v): v is number => v !== null && Number.isFinite(v));
  if (values.length === 0) return null;
  // ponytail: 序列最多几百个点，统计数据直接遍历即可
  let max = values[0];
  let min = values[0];
  for (const v of values) {
    if (v > max) max = v;
    if (v < min) min = v;
  }
  return {
    name: '',
    color: '',
    count: values.length,
    latest: values[values.length - 1].toFixed(4),
    max: max.toFixed(4),
    min: min.toFixed(4),
  };
}

export function IndicatorLabPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { getButtonDisabled, getButtonTooltip } = useGuestRestriction();

  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [indicatorsLoading, setIndicatorsLoading] = useState(true);
  const [selected, setSelected] = useState<Indicator | null>(null);

  // 沙箱预览
  const [draftCode, setDraftCode] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState<IndicatorPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState('');

  // 版本历史
  const [versions, setVersions] = useState<IndicatorVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [diffVersions, setDiffVersions] = useState<[number, number] | null>(null);
  const [diffData, setDiffData] = useState<{ a: IndicatorVersion; b: IndicatorVersion } | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);

  const loadIndicators = useCallback(async () => {
    setIndicatorsLoading(true);
    try {
      const data = await indicatorApi.getIndicators();
      setIndicators(data);
    } catch (err) {
      message.error(`${t('indicatorLab.load_failed')}: ${err}`);
    } finally {
      setIndicatorsLoading(false);
    }
  }, [message, t]);

  const loadVersions = useCallback(async (indicatorId: number) => {
    setVersionsLoading(true);
    try {
      setVersions(await indicatorApi.getIndicatorVersions(indicatorId));
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIndicators();
  }, [loadIndicators]);

  // 选中指标：默认把当前代码装进草稿编辑器，并加载版本列表
  const handleSelect = useCallback(
    (indicator: Indicator) => {
      setSelected(indicator);
      setDraftCode(indicator.code);
      setPreviewResult(null);
      setPreviewError('');
      setDiffVersions(null);
      void loadVersions(indicator.id);
    },
    [loadVersions],
  );

  const handlePreview = useCallback(async () => {
    if (!draftCode.trim()) return;
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const result = await indicatorApi.previewIndicator({ code: draftCode });
      setPreviewResult(result);
    } catch (err: unknown) {
      setPreviewResult(null);
      // 后端把求值失败统一放在 message 里返回（HTTP 200 + code=400）
      setPreviewError(String(err));
    } finally {
      setPreviewLoading(false);
    }
  }, [draftCode]);

  const plotSummaries = useMemo(() => {
    if (!previewResult?.plots) return [];
    return previewResult.plots
      .map((p) => {
        const s = summarizePlot(p.data);
        return s ? { ...s, name: p.name, color: p.color || '#1890ff' } : null;
      })
      .filter((v): v is PlotSummary => v !== null);
  }, [previewResult]);

  const handleDiff = useCallback(async () => {
    if (!selected || !diffVersions) return;
    const [a, b] = diffVersions;
    setDiffLoading(true);
    try {
      setDiffData(await indicatorApi.diffIndicatorVersions(selected.id, a, b));
    } catch (err) {
      message.error(`${t('indicatorLab.diff_failed')}: ${err}`);
    } finally {
      setDiffLoading(false);
    }
  }, [selected, diffVersions, message, t]);

  const handleRollback = useCallback(
    async (versionNo: number) => {
      if (!selected) return;
      setRollbackLoading(true);
      try {
        const updated = await indicatorApi.rollbackIndicatorVersion(selected.id, versionNo);
        message.success(`${t('indicatorLab.rollback_success')} v${updated.version ?? '?'}`);
        setDraftCode(updated.code);
        setSelected({ ...selected, code: updated.code, version: updated.version });
        await loadVersions(selected.id);
        await loadIndicators();
      } catch (err) {
        message.error(`${t('indicatorLab.rollback_failed')}: ${err}`);
      } finally {
        setRollbackLoading(false);
      }
    },
    [selected, message, t, loadVersions, loadIndicators],
  );

  const versionColumns = [
    { title: t('indicatorLab.version'), dataIndex: 'version_no', width: 90, render: (v: number) => `v${v}` },
    {
      title: t('indicatorLab.source'),
      dataIndex: 'source',
      width: 100,
      render: (s: string, record: IndicatorVersion) => (
        <Space size={4}>
          <Tag color={SOURCE_COLOR[s] || 'default'}>{s}</Tag>
          {record.is_current && <Tag color="gold">{t('indicatorLab.current')}</Tag>}
        </Space>
      ),
    },
    { title: t('indicatorLab.snapshot_name'), dataIndex: 'name', ellipsis: true },
    { title: t('indicatorLab.time'), dataIndex: 'created_at', width: 170 },
    {
      title: t('indicatorLab.actions'),
      key: 'actions',
      width: 230,
      render: (_: unknown, record: IndicatorVersion) => {
        const checked = diffVersions?.includes(record.version_no) ?? false;
        return (
          <Space size={4}>
            <Checkbox
              checked={checked}
              onChange={(e) => {
                const no = record.version_no;
                if (e.target.checked) {
                  // 至多勾选两个版本
                  setDiffVersions((prev) => (prev ? (prev.includes(no) ? prev : [prev[1], no]) : [no, no]));
                } else {
                  setDiffVersions(null);
                }
              }}
            />
            <Popconfirm
              title={t('indicatorLab.rollback_confirm', { version: `v${record.version_no}` })}
              onConfirm={() => void handleRollback(record.version_no)}
              okButtonProps={{ loading: rollbackLoading }}
            >
              <Button size="small" disabled={getButtonDisabled()} title={getButtonTooltip()}>
                {t('indicatorLab.rollback')}
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Flex gap={16} align="stretch" style={{ height: '100%' }}>
      {/* 指标列表 */}
      <Card
        title={t('indicatorLab.indicators')}
        style={{ width: 300, flexShrink: 0 }}
        styles={{ body: { overflow: 'auto', maxHeight: 'calc(100vh - 220px)' } }}
      >
        {indicatorsLoading ? (
          <Spin />
        ) : indicators.length === 0 ? (
          <Empty description={t('indicatorLab.no_indicators')} />
        ) : (
          <List
            size="small"
            dataSource={indicators}
            renderItem={(item) => (
              <List.Item
                onClick={() => handleSelect(item)}
                style={{
                  cursor: 'pointer',
                  borderRadius: 6,
                  padding: '6px 8px',
                  background: selected?.id === item.id ? 'rgba(24,144,255,0.1)' : undefined,
                }}
              >
                <List.Item.Meta
                  title={
                    <Space size={4}>
                      <Typography.Text ellipsis style={{ maxWidth: 180 }}>
                        {item.name}
                      </Typography.Text>
                      <Tag color="blue">v{item.version ?? 1}</Tag>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* IDE 区 */}
      <Flex vertical flex={1} gap={0} style={{ minWidth: 0 }}>
        {selected ? (
          <Card
            title={
              <Space size={8}>
                <span>{selected.name}</span>
                <Tag color="blue">
                  {t('indicatorLab.current_version')} v{selected.version ?? 1}
                </Tag>
              </Space>
            }
            style={{ flex: 1 }}
            styles={{ body: { height: 'calc(100vh - 210px)', overflow: 'auto' } }}
          >
            <Tabs
              items={[
                {
                  key: 'preview',
                  label: t('indicatorLab.tab_preview'),
                  children: (
                    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                      <Alert
                        type="info"
                        showIcon
                        message={t('indicatorLab.preview_hint')}
                      />
                      <div style={{ border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
                        <Editor
                          height="320px"
                          language="python"
                          theme="vs-dark"
                          value={draftCode}
                          onChange={(v) => setDraftCode(v ?? '')}
                          options={{ minimap: { enabled: false } }}
                        />
                      </div>
                      <Space>
                        <Button
                          type="primary"
                          icon={<IconPlayerPlay size="1em" />}
                          loading={previewLoading}
                          onClick={() => void handlePreview()}
                        >
                          {t('indicatorLab.run_preview')}
                        </Button>
                        <Typography.Text type="secondary">{t('indicatorLab.preview_note')}</Typography.Text>
                      </Space>

                      {previewError ? (
                        <Alert type="error" showIcon message={t('indicatorLab.preview_failed')} description={previewError} />
                      ) : null}

                      {previewResult?.success ? (
                        <>
                          <Typography.Title level={5} style={{ margin: 0 }}>
                            {t('indicatorLab.outputs')}（plots: {previewResult.plots.length}, signals: {previewResult.signals.length}）
                          </Typography.Title>
                          <Table
                            size="small"
                            rowKey="name"
                            pagination={false}
                            loading={previewLoading}
                            dataSource={plotSummaries}
                            columns={[
                              {
                                title: t('indicatorLab.plot_name'),
                                dataIndex: 'name',
                                render: (name: string, record: PlotSummary) => (
                                  <Space size={6}>
                                    <span
                                      style={{
                                        display: 'inline-block',
                                        width: 10,
                                        height: 10,
                                        borderRadius: 2,
                                        background: record.color,
                                      }}
                                    />
                                    {name}
                                  </Space>
                                ),
                              },
                              { title: t('indicatorLab.samples'), dataIndex: 'count', width: 90 },
                              { title: t('indicatorLab.latest'), dataIndex: 'latest', width: 110 },
                              { title: t('indicatorLab.max'), dataIndex: 'max', width: 110 },
                              { title: t('indicatorLab.min'), dataIndex: 'min', width: 110 },
                            ]}
                          />
                        </>
                      ) : null}
                    </Space>
                  ),
                },
                {
                  key: 'versions',
                  label: t('indicatorLab.tab_versions'),
                  children: (
                    <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
                      <Flex justify="space-between" align="center">
                        <Typography.Text type="secondary">{t('indicatorLab.versions_hint')}</Typography.Text>
                        <Button
                          type="primary"
                          disabled={!diffVersions}
                          loading={diffLoading}
                          onClick={() => void handleDiff()}
                        >
                          {t('indicatorLab.diff_selected')}
                        </Button>
                      </Flex>
                      <Table
                        size="small"
                        rowKey="version_no"
                        loading={versionsLoading}
                        pagination={false}
                        dataSource={versions}
                        columns={versionColumns}
                        locale={{ emptyText: <Empty description={t('indicatorLab.no_versions')} /> }}
                      />
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        ) : (
          <Card style={{ flex: 1 }}>
            <Empty description={t('indicatorLab.select_indicator')} style={{ marginTop: 80 }} />
          </Card>
        )}
      </Flex>

      {/* 版本对比弹窗：Monaco DiffEditor 渲染两个快照的代码差异 */}
      <Modal
        open={diffVersions !== null}
        title={
          diffVersions
            ? `${t('indicatorLab.diff_title')} v${diffVersions[0]} ↔ v${diffVersions[1]}`
            : t('indicatorLab.diff_title')
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
}

export default IndicatorLabPage;
