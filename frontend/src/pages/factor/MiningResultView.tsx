/**
 * LLM 挖掘结果视图：统计摘要 + 候选表（代码回看 / 保存为代码因子）+ 合成因子卡片（保存为合成因子）。
 * 新建挖掘完成与历史详情共用本组件，保存成功统一经 onMined 回调通知外层。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Drawer,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  type TableProps,
} from 'antd';
import {
  factorApi,
  type CompositeConstituent,
  type CompositeFactorResult,
  type FactorMineResult,
  type MinedCandidate,
  type WFFoldMetrics,
} from '@/api/factor';
import { useQuantColors } from '@/utils/colors';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';

const fmt = (v: number | null | undefined, digits: number) =>
  v == null ? '—' : v.toFixed(digits);

/** ISO 时间串 → 'YYYY-MM-DD HH:mm' 紧凑展示 */
const fmtTime = (iso: string) => iso.replace('T', ' ').slice(0, 16);

/** 候选状态 → Tag 颜色（文案由组件内 t() 查表） */
const STATUS_TAG_COLOR: Record<MinedCandidate['status'], string> = {
  success: 'green',
  security_error: 'red',
  output_error: 'orange',
  timeout: 'red',
  resource_error: 'red',
  runtime_error: 'default',
  empty: 'default',
  llm_truncated: 'orange',
};

/** 样本外复核结论 → Tag 颜色（文案由组件内 t() 查表） */
const OOS_TAG_COLOR: Record<NonNullable<MinedCandidate['oos_flag']>, string> = {
  ok: 'green',
  weak: 'orange',
  sign_flip: 'red',
};

/** walk-forward 逐折指标列表：候选展开行与合成因子卡片共用，避免复制粘贴 */
const FoldList: React.FC<{ folds: WFFoldMetrics[] }> = ({ folds }) => {
  const { t } = useTranslation();
  return (
    <Flex vertical gap="small">
      {folds.map((f) => (
        <Flex key={f.index} gap="middle" wrap align="center">
          <Tag style={{ marginInlineEnd: 0 }}>
            {t('factor_mining_fold_window', { n: f.index + 1 }) || `窗口 ${f.index + 1}`}
          </Tag>
          <span style={{ color: '#8c8c8c' }}>
            {fmtTime(f.start)} ~ {fmtTime(f.end)}
          </span>
          <span>IC: {fmt(f.ic_mean, 4)}</span>
          <span>
            {t('factor_mining_fold_cov') || '覆盖率'}:{' '}
            {f.coverage == null ? '—' : `${(f.coverage * 100).toFixed(1)}%`}
          </span>
          <span>bars: {f.bar_count}</span>
        </Flex>
      ))}
    </Flex>
  );
};

/** 合成卡片上的单个指标格：灰色小标签 + 数值 */
const MetricCell: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <Flex vertical gap={0}>
    <span style={{ color: '#8c8c8c', fontSize: 12 }}>{label}</span>
    <span style={{ fontWeight: 600 }}>{value}</span>
  </Flex>
);

const covText = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`;

/** 合成因子结果卡片：成分权重 / train 与样本外指标 / OOS 结论 / WF 逐折 / 保存入口 */
const CompositeCard: React.FC<{ comp: CompositeFactorResult; onSave: () => void }> = ({
  comp,
  onSave,
}) => {
  const { t } = useTranslation();
  if (comp.error) {
    return (
      <Card size="small" title={t('factor_mining_comp_err_title') || '合成因子（IC 加权 zscore）'}>
        <Alert
          type="error"
          showIcon
          message={t('factor_mining_comp_err_msg') || '合成失败（不影响本次挖掘结果）'}
          description={comp.error}
        />
      </Card>
    );
  }
  const m = comp.metrics;
  const oos = comp.metrics_oos;
  const constituentColumns: TableProps<CompositeConstituent>['columns'] = [
    {
      title: '#',
      key: 'idx',
      width: 48,
      render: (_, __, index) => index + 1,
    },
    {
      title: t('factor_mining_comp_table_hash') || '代码 hash',
      dataIndex: 'code_hash',
      render: (h: string) => <Tag style={{ marginInlineEnd: 0 }}>{h.slice(0, 8)}</Tag>,
    },
    {
      title: t('factor_mining_comp_table_weight') || '权重',
      dataIndex: 'weight',
      align: 'right',
      render: (w: number) => (
        <Tag color={w >= 0 ? 'green' : 'red'} style={{ marginInlineEnd: 0 }}>
          {w >= 0 ? '+' : ''}
          {(w * 100).toFixed(1)}%
        </Tag>
      ),
    },
  ];

  const oosText = (flag: NonNullable<CompositeFactorResult['oos_flag']>) => {
    switch (flag) {
      case 'ok':
        return t('factor_mining_oos_stable') || '稳定';
      case 'weak':
        return t('factor_mining_oos_weak') || '衰减';
      case 'sign_flip':
        return t('factor_mining_oos_sign_flip') || '符号反转';
      default:
        return flag;
    }
  };

  return (
    <Card
      size="small"
      title={
        t('factor_mining_comp_card_title_with_n', { n: comp.n ?? 0 }) ||
        `合成因子（IC 加权 zscore）· ${comp.n ?? 0} 成分`
      }
      extra={
        <Button size="small" type="primary" onClick={onSave}>
          {t('factor_mining_comp_btn_save') || '保存为因子'}
        </Button>
      }
    >
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Table<CompositeConstituent>
          size="small"
          pagination={false}
          rowKey="code_hash"
          dataSource={comp.constituents ?? []}
          columns={constituentColumns}
        />
        <Flex gap="large" wrap align="center">
          <MetricCell label={t('factor_mining_comp_metric_train_ic') || 'Train IC'} value={fmt(m?.ic_mean, 4)} />
          <MetricCell
            label={t('factor_mining_comp_metric_train_cov') || 'Train 覆盖率'}
            value={covText(m?.coverage)}
          />
          <MetricCell
            label={t('factor_mining_comp_metric_train_bars') || 'Train bars'}
            value={String(m?.bar_count ?? '—')}
          />
          <MetricCell
            label={t('factor_mining_comp_metric_oos_ic') || '样本外 IC'}
            value={fmt(oos?.ic_mean, 4)}
          />
          <MetricCell
            label={t('factor_mining_comp_metric_oos_cov') || '样本外覆盖率'}
            value={covText(oos?.coverage)}
          />
          <MetricCell
            label={t('factor_mining_comp_metric_oos_bars') || '样本外 bars'}
            value={String(oos?.bar_count ?? '—')}
          />
          {comp.oos_flag && (
            <Tag color={OOS_TAG_COLOR[comp.oos_flag]}>{oosText(comp.oos_flag)}</Tag>
          )}
        </Flex>
        {comp.oos_note && (
          <span style={{ color: '#d46b08', whiteSpace: 'pre-wrap' }}>{comp.oos_note}</span>
        )}
        {comp.folds?.length ? (
          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
            <span style={{ color: '#8c8c8c' }}>
              {t('factor_mining_comp_wf_label') || 'walk-forward 各折复核'}
            </span>
            <FoldList folds={comp.folds} />
          </Space>
        ) : null}
      </Space>
    </Card>
  );
};

const MiningResultView: React.FC<{
  result: FactorMineResult;
  onMined?: (name: string) => void;
}> = ({ result, onMined }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const qc = useQuantColors();
  const [drawerRow, setDrawerRow] = useState<MinedCandidate | null>(null);
  // Popconfirm 内嵌命名 Input 的局部状态：打开时写入当前行与默认名称，确认时取最新值
  const [saveRow, setSaveRow] = useState<MinedCandidate | null>(null);
  const [saveName, setSaveName] = useState('');
  const [saving, setSaving] = useState(false);
  // 合成因子「保存为因子」Modal
  const [compModalOpen, setCompModalOpen] = useState(false);
  const [compSaving, setCompSaving] = useState(false);
  const [compForm] = Form.useForm<{ factor_name: string; description?: string }>();

  const oosText = (flag: NonNullable<MinedCandidate['oos_flag']>) => {
    switch (flag) {
      case 'ok':
        return t('factor_mining_oos_stable') || '稳定';
      case 'weak':
        return t('factor_mining_oos_weak') || '衰减';
      case 'sign_flip':
        return t('factor_mining_oos_sign_flip') || '符号反转';
      default:
        return flag;
    }
  };

  const statusText = (status: MinedCandidate['status']) => {
    switch (status) {
      case 'success':
        return t('factor_mining_status_success') || '有效';
      case 'security_error':
        return t('factor_mining_status_sec') || '安全拦截';
      case 'output_error':
        return t('factor_mining_status_output') || '输出不合规';
      case 'timeout':
      case 'resource_error':
        return t('factor_mining_status_timeout') || '超时/资源限制';
      case 'runtime_error':
        return t('factor_mining_status_runtime') || '运行失败';
      case 'empty':
        return t('factor_mining_status_empty') || '空响应';
      case 'llm_truncated':
        return t('factor_mining_status_truncated') || '思考超限';
      default:
        return status;
    }
  };

  // 表格数据：按轮次升序；同轮成功候选按 fitness 降序，失败候选排在成功之后
  const dataSource = [...result.candidates].sort((a, b) => {
    if (a.round !== b.round) return a.round - b.round;
    const rank = (r: MinedCandidate) => (r.status === 'success' ? 0 : 1);
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    const fa = a.metrics?.fitness ?? Number.NEGATIVE_INFINITY;
    const fb = b.metrics?.fitness ?? Number.NEGATIVE_INFINITY;
    return fb - fa;
  });

  // Popconfirm 确认：reject 时气泡保持打开，便于改名重试
  const handleSave = async () => {
    if (!saveRow) return;
    const name = saveName.trim();
    if (!name) {
      message.warning(t('factor_mining_toast_name_req') || '请输入因子名称');
      throw new Error('empty name');
    }
    setSaving(true);
    try {
      await factorApi.addCodeFactor(name, saveRow.code);
      message.success(
        t('factor_mining_toast_saved', { name }) || `已保存到因子库：${name}，正在带入工作台分析…`,
      );
      setSaveRow(null);
      onMined?.(name);
    } catch (err) {
      message.error(errMsg(err));
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const openSaveComposite = () => {
    const firstHash = result.composite?.constituents?.[0]?.code_hash.slice(0, 8) ?? '';
    compForm.resetFields();
    compForm.setFieldsValue({ factor_name: `llm_comp_${firstHash}`, description: '' });
    setCompModalOpen(true);
  };

  // 合成因子保存：constituents 从 candidates 的 code_hash → 完整 code 组装，
  // weight/ts_stats 取挖掘时冻结在 train 的合成结果
  const handleSaveComposite = async () => {
    const v = await compForm.validateFields();
    const comp = result.composite;
    if (!comp || !comp.constituents || !comp.train_window) {
      message.error(t('factor_mining_toast_comp_incomplete') || '合成因子结果不完整，无法保存');
      return;
    }
    const codeByHash = new Map(
      result.candidates.filter((c) => c.status === 'success').map((c) => [c.code_hash, c.code]),
    );
    let constituents;
    try {
      constituents = comp.constituents.map((c) => {
        const code = codeByHash.get(c.code_hash);
        if (!code) throw new Error(`缺少成分代码：${c.code_hash}`);
        return { code, weight: c.weight, ts_stats: c.ts_stats };
      });
    } catch (err) {
      message.error(errMsg(err));
      return;
    }
    setCompSaving(true);
    try {
      await factorApi.addCompositeFactor({
        factor_name: v.factor_name.trim(),
        description: v.description?.trim() || '',
        constituents,
        train_window: comp.train_window,
      });
      const savedName = v.factor_name.trim();
      message.success(
        t('factor_mining_toast_comp_saved', { name: savedName }) ||
          `合成因子已保存到因子库：${savedName}，正在带入工作台分析…`,
      );
      setCompModalOpen(false);
      onMined?.(savedName);
    } catch (err) {
      message.error(errMsg(err));
    } finally {
      setCompSaving(false);
    }
  };

  const columns: TableProps<MinedCandidate>['columns'] = [
    {
      title: t('factor_mining_col_round') || '轮次',
      dataIndex: 'round',
      key: 'round',
      width: 70,
      align: 'center',
    },
    {
      title: t('factor_mining_col_status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: MinedCandidate['status'], row) => {
        return (
          <Flex gap="small" align="center">
            <Tag color={STATUS_TAG_COLOR[status]} style={{ marginInlineEnd: 0 }}>
              {statusText(status)}
            </Tag>
            {status === 'success' && row.redundant && (
              <Tooltip
                title={
                  t('factor_mining_col_redundant_tip', {
                    similar: (row.redundant_with || '').slice(0, 8),
                    corr: row.redundant_corr ?? '—',
                  }) ||
                  `与 ${(row.redundant_with || '').slice(0, 8)} 的因子相关系数 ${row.redundant_corr ?? '—'}`
                }
              >
                <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                  {t('factor_mining_col_redundant') || '重复'}
                </Tag>
              </Tooltip>
            )}
          </Flex>
        );
      },
    },
    {
      title: t('factor_mining_col_fitness') || 'fitness',
      key: 'fitness',
      align: 'right',
      width: 90,
      render: (_, row) => {
        const v = row.metrics?.fitness;
        return v == null ? (
          '—'
        ) : (
          <span style={{ color: v >= 0 ? qc.positive : qc.negative }}>{v.toFixed(2)}</span>
        );
      },
    },
    {
      title: t('factor_mining_col_ic') || 'IC',
      key: 'ic_mean',
      align: 'right',
      width: 90,
      render: (_, row) => fmt(row.metrics?.ic_mean, 4),
    },
    {
      title: t('factor_mining_col_oos_ic') || '样本外IC',
      key: 'oos_ic',
      align: 'right',
      width: 100,
      render: (_, row) => fmt(row.metrics_oos?.ic_mean, 4),
    },
    {
      title: t('factor_mining_col_oos') || 'OOS',
      key: 'oos_flag',
      align: 'center',
      width: 90,
      render: (_, row) => {
        const flag = row.oos_flag;
        return flag ? (
          <Tag color={OOS_TAG_COLOR[flag]}>{oosText(flag)}</Tag>
        ) : (
          '—'
        );
      },
    },
    {
      title: t('factor_mining_col_wf') || 'WF一致性',
      key: 'wf_consistency',
      align: 'right',
      width: 100,
      render: (_, row) => {
        const v = row.metrics_oos?.sign_consistency;
        return v == null ? '—' : `${Math.round(v * 100)}%`;
      },
    },
    {
      title: t('factor_mining_col_ir') || 'IR',
      key: 'ic_ir',
      align: 'right',
      width: 90,
      render: (_, row) => fmt(row.metrics?.ic_ir, 3),
    },
    {
      title: t('factor_stat_coverage') || '覆盖率',
      key: 'coverage',
      align: 'right',
      width: 90,
      render: (_, row) => {
        const v = row.metrics?.coverage;
        return v == null ? '—' : `${(v * 100).toFixed(1)}%`;
      },
    },
    {
      title: t('factor_stat_turnover') || '换手',
      key: 'turnover',
      align: 'right',
      width: 100,
      render: (_, row) => fmt(row.metrics?.turnover, 4),
    },
    {
      title: t('factor_stat_ls_return') || '多空收益',
      key: 'long_short_return',
      align: 'right',
      width: 110,
      render: (_, row) => fmt(row.metrics?.long_short_return, 5),
    },
    {
      title: t('factor_mining_col_action') || '操作',
      key: 'actions',
      fixed: 'right',
      width: 170,
      render: (_, row) => (
        <Flex gap="small">
          <Button size="small" onClick={() => setDrawerRow(row)}>
            {t('factor_mining_btn_code') || '代码'}
          </Button>
          {row.status === 'success' && (
            <Popconfirm
              title={t('factor_mining_popconfirm_title') || '保存为因子'}
              description={
                <Input
                  value={saveName}
                  onChange={(ev) => setSaveName(ev.target.value)}
                  placeholder={t('factor_mining_popconfirm_placeholder') || '因子名称'}
                />
              }
              okText={t('factor_lib_save') || '保存'}
              cancelText={t('factor_lib_cancel') || '取消'}
              okButtonProps={{ loading: saving }}
              onOpenChange={(open) => {
                if (open) {
                  // 打开瞬间写入当前行与默认名，保证 onConfirm 拿到与该行一致的最新名称
                  setSaveRow(row);
                  setSaveName(`llm_${(row.code_hash || '').slice(0, 8)}`);
                }
              }}
              onConfirm={handleSave}
            >
              <Button size="small" type="link">
                {t('factor_mining_btn_save_row') || '保存为因子'}
              </Button>
            </Popconfirm>
          )}
        </Flex>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Flex gap="large" wrap>
        <Statistic title={t('factor_mining_stats_generated') || '生成'} value={result.stats.generated} />
        <Statistic title={t('factor_mining_stats_unique') || '去重后'} value={result.stats.unique} />
        <Statistic
          title={t('factor_mining_stats_succeeded') || '成功'}
          value={result.stats.succeeded}
          styles={{ content: { color: qc.positive } }}
        />
        <Statistic
          title={t('factor_mining_stats_redundant') || '重复'}
          value={result.stats.redundant ?? 0}
          styles={{ content: { color: '#d46b08' } }}
        />
        <Statistic
          title={t('factor_mining_stats_failed') || '失败'}
          value={result.stats.failed}
          styles={{ content: { color: qc.negative } }}
        />
      </Flex>
      <Table<MinedCandidate>
        rowKey={(r) => `${r.round}-${r.candidate}-${r.code_hash || 'empty'}`}
        columns={columns}
        dataSource={dataSource}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 'max-content' }}
        expandable={{
          rowExpandable: (r) =>
            !!r.error || !!r.oos_note || !!r.metrics_oos?.folds?.length,
          expandedRowRender: (r) => (
            <Flex vertical gap="small">
              {r.error && (
                <span style={{ color: '#cf1322', whiteSpace: 'pre-wrap' }}>{r.error}</span>
              )}
              {r.oos_note && (
                <span style={{ color: '#d46b08', whiteSpace: 'pre-wrap' }}>{r.oos_note}</span>
              )}
              {r.metrics_oos?.folds && <FoldList folds={r.metrics_oos.folds} />}
            </Flex>
          ),
        }}
        locale={{ emptyText: t('factor_mining_empty') || '暂无挖掘结果，请先在上方配置并开始挖掘' }}
      />
      {result.composite && <CompositeCard comp={result.composite} onSave={openSaveComposite} />}

      <Drawer
        open={!!drawerRow}
        title={
          drawerRow
            ? t('factor_mining_drawer_title', { round: drawerRow.round, cand: drawerRow.candidate }) ||
              `轮次${drawerRow.round} 候选${drawerRow.candidate}`
            : ''
        }
        size={640}
        onClose={() => setDrawerRow(null)}
      >
        {drawerRow?.code ? (
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 13 }}>{drawerRow.code}</pre>
        ) : (
          t('factor_mining_drawer_no_code') || '无代码'
        )}
      </Drawer>

      <Modal
        title={t('factor_mining_modal_comp_title') || '保存合成因子'}
        open={compModalOpen}
        onOk={handleSaveComposite}
        confirmLoading={compSaving}
        onCancel={() => setCompModalOpen(false)}
        okText={t('factor_lib_save') || '保存'}
        cancelText={t('factor_lib_cancel') || '取消'}
        destroyOnHidden
        mask={{ closable: false }}
      >
        <Form form={compForm} layout="vertical" preserve={false}>
          <Form.Item
            name="factor_name"
            label={t('factor_lib_form_name') || '因子名称（英文标识）'}
            extra="字母开头，仅含字母/数字/下划线；保存后可在因子库中按普通因子分析、对比与保存快照"
            rules={[
              { required: true, message: t('factor_lib_form_name_req') || '请输入因子名称' },
              {
                pattern: /^[A-Za-z][A-Za-z0-9_]{0,99}$/,
                message: '需以字母开头，仅含字母数字下划线，长度 1-100',
              },
            ]}
          >
            <Input placeholder={t('factor_lib_form_name_ph') || '如 llm_comp_ab12cd34'} />
          </Form.Item>
          <Form.Item name="description" label={t('factor_mining_modal_desc') || '描述（可选）'}>
            <Input.TextArea
              rows={2}
              maxLength={300}
              placeholder={t('factor_mining_modal_desc_ph') || '该合成因子的含义/成分说明'}
            />
          </Form.Item>
          <span style={{ color: '#8c8c8c' }}>
            {t('factor_mining_modal_hint', { n: result.composite?.n ?? 0 }) ||
              `将保存 ${result.composite?.n ?? 0} 个成分的冻结权重与 train 时序统计，重新分析时按冻结口径组合。`}
          </span>
        </Form>
      </Modal>
    </Space>
  );
};

export default MiningResultView;
