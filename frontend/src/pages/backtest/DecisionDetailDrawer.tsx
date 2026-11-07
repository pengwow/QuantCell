/**
 * 决策详情抽屉：按 (_seq, fingerprint) 定位单条决策录制行，展示完整录制内容。
 * 数据源由 fetchDetail 注入（回测 / Worker 决策详情端点，按 JSONL 行号读行，fp 校验防错位）。
 * 区块与 spec 4.4 对应：
 *   ① 最终决策 = decision 本体；② 市场快照 / ③ Prompt 输入 = 录制 state/questions；
 *   ④ 模型输出 = s1_raw / s2_raw / s2_thinking（旧任务无这些字段，显式「未录制」占位）。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Collapse,
  Drawer,
  Empty,
  Input,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { DecisionDetailRecord } from '../../types/backtest';

/** 轻列表行中参与定位的子集（由详情页表格传入） */
export interface DrawerRecord {
  _seq?: number;
  fingerprint?: string;
  _ts?: string;
  action: string;
  confidence: number;
  _decider?: string;
  fallback_reason?: string;
}

/** ISO8601 纳秒时间戳截断到毫秒展示（如 2026-11-03 12:34:56.123Z） */
export const fmtDecisionTs = (ts?: string): string =>
  ts ? ts.replace('T', ' ').replace(/(\.\d{3})\d+(Z?)$/, '$1$2') : '-';

/** 降级原因人话化（聚合/弹窗共用）。三段式前两段由 Rust cascade 生成，格式靠测试守护 */
export const humanizeFallbackReason = (reason?: string): string => {
  if (!reason) return '-';
  let body = reason;
  let suffix = '';
  if (body.endsWith('|s2_replay')) {
    body = body.slice(0, -'|s2_replay'.length);
    suffix = '（已回放覆盖）';
  }
  const lc = body.match(/^low_confidence:\s*(\w+):\s*([\d.]+)$/);
  if (lc) return `置信度 ${lc[2]} 低于阈值，规则接管（方向 ${lc[1]}）${suffix}`;
  if (body.startsWith('sdm_error:')) return `S1 调用异常: ${body.slice(10).trim()}${suffix}`;
  if (body.startsWith('fallback_error:')) return `规则兜底异常: ${body.slice(15).trim()}${suffix}`;
  return `${body}${suffix}`;
};

const fmtNum = (v: unknown, digits = 4): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '-';

const prettyJson = (s: string): string => {
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return s;
  }
};

const preStyle: React.CSSProperties = {
  margin: 0,
  padding: 8,
  background: 'rgba(128,128,128,0.08)',
  borderRadius: 6,
  fontSize: 12,
  fontFamily: 'monospace',
  maxHeight: 320,
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
};

/** 键值表：短值单行内联；长 JSON 格式化进可滚动 pre 完整展示；支持字段名搜索 */
const KVTable = ({ data, search }: { data: Record<string, unknown>; search: string }) => {
  const rows = Object.entries(data || {})
    .filter(([k]) => !search || k.toLowerCase().includes(search.toLowerCase()))
    .map(([k, v]) => ({ key: k, k, v: JSON.stringify(v) }));
  if (rows.length === 0)
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无匹配字段" />;
  return (
    <Table
      size="small"
      pagination={false}
      scroll={{ y: 320 }}
      dataSource={rows}
      columns={[
        { title: '字段', dataIndex: 'k', width: 220, render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code> },
        {
          title: '值',
          dataIndex: 'v',
          render: (v: string) =>
            v.length <= 80 ? (
              <div style={{ fontFamily: 'monospace', fontSize: 12, wordBreak: 'break-all' }}>{v}</div>
            ) : (
              <pre style={{ ...preStyle, maxHeight: 240 }}>{prettyJson(v)}</pre>
            ),
        },
      ]}
    />
  );
};

/** 三键概率分布横条（buy 绿 / sell 红 / hold 灰）+ 阈值参考线 */
const ProbBar = ({
  probs,
  thresholds,
}: {
  probs: Record<string, unknown>;
  thresholds?: { open?: number; hold?: number };
}) => {
  const colors: Record<string, string> = { buy: '#52c41a', sell: '#ff4d4f', hold: '#8c8c8c' };
  const labels: Record<string, string> = { buy: '买入', sell: '卖出', hold: '持有' };
  return (
    <div style={{ display: 'flex', gap: 16 }}>
      {['buy', 'sell', 'hold'].map((k) => {
        const p = typeof probs[k] === 'number' ? (probs[k] as number) : 0;
        // Rust 侧门控口径：buy/sell 用 open_threshold，hold 用 hold_threshold
        const th = k === 'hold' ? thresholds?.hold : thresholds?.open;
        return (
          <div key={k} style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span>{labels[k]}</span>
              <span style={{ color: colors[k] }}>{(p * 100).toFixed(1)}%</span>
            </div>
            <div style={{ position: 'relative', height: 6, background: 'rgba(128,128,128,0.15)', borderRadius: 3, marginTop: 4 }}>
              <div
                style={{
                  width: `${Math.max(0, Math.min(100, p * 100))}%`,
                  height: 6,
                  background: colors[k],
                  borderRadius: 3,
                }}
              />
              {typeof th === 'number' && (
                <Tooltip title={`${labels[k]}阈值 ${(th * 100).toFixed(1)}%（meta.open_threshold/hold_threshold）`}>
                  <div
                    style={{
                      position: 'absolute',
                      left: `${Math.min(100, Math.max(0, th * 100))}%`,
                      top: -2,
                      bottom: -2,
                      width: 2,
                      background: '#faad14',
                      transform: 'translateX(-1px)',
                      cursor: 'help',
                    }}
                  />
                </Tooltip>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

interface DecisionDetailDrawerProps {
  /** 按 (seq, fingerprint) 取单条录制详情：回测/Worker 两处注入各自 API */
  fetchDetail: (seq: number, fingerprint: string) => Promise<DecisionDetailRecord>;
  record: DrawerRecord | null; // null = 关闭
  onClose: () => void;
}

export default function DecisionDetailDrawer({ fetchDetail, record, onClose }: DecisionDetailDrawerProps) {
  const [detail, setDetail] = useState<DecisionDetailRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [stateSearch, setStateSearch] = useState('');
  const [qSearch, setQSearch] = useState('');
  // per (seq,fingerprint) 缓存：同一弹窗反复打开不重复请求
  const cache = useRef(new Map<string, DecisionDetailRecord>());
  // fetchDetail 每次渲染都是新闭包，不能进 effect 依赖（否则重复请求）；
  // 用 ref 保存最新实现，effect 只跟随 record 变化
  const fetchRef = useRef(fetchDetail);
  fetchRef.current = fetchDetail;

  useEffect(() => {
    if (!record || record._seq == null) return;
    const fp = record.fingerprint || '';
    const key = `${record._seq}:${fp}`;
    const cached = cache.current.get(key);
    if (cached) {
      setDetail(cached);
      setError('');
      return;
    }
    setLoading(true);
    setError('');
    setDetail(null);
    fetchRef.current(record._seq, fp)
      .then((d) => {
        cache.current.set(key, d);
        setDetail(d);
      })
      .catch((e) => setError(e?.message || String(e)))
      .finally(() => setLoading(false));
  }, [record]);

  const decision = (detail?.decision || {}) as Record<string, unknown>;
  const probs = (decision.probabilities || {}) as Record<string, unknown>;
  const subs = decision.sub_signals as Record<string, unknown> | undefined;
  const isFallback = decision.source === 'fallback';
  const confidence = decision.confidence;
  // 生效阈值与 Rust cascade 门控同口径；旧录制无阈值键时不画线、不显示差值
  const thCfg = detail?.meta
    ? {
        open: typeof detail.meta.open_threshold === 'number' ? detail.meta.open_threshold : undefined,
        hold: typeof detail.meta.hold_threshold === 'number' ? detail.meta.hold_threshold : undefined,
      }
    : undefined;
  const effThreshold = decision.action === 'hold' ? thCfg?.hold : thCfg?.open;

  return (
    <Drawer
      title={record ? `决策详情 · ${fmtDecisionTs(record._ts)}` : '决策详情'}
      open={!!record}
      onClose={onClose}
      width={680}
    >
      {loading && <Spin />}
      {error && <Alert type="warning" showIcon title={`详情加载失败：${error}`} style={{ marginBottom: 12 }} />}
      {detail && (
        <Tabs
          items={[
            {
              key: 'decision',
              label: '① 最终决策',
              children: (
                <>
                  {isFallback && detail.decision.fallback_reason ? (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      title={`规则接管：${humanizeFallbackReason(String(detail.decision.fallback_reason))}`}
                    />
                  ) : null}
                  <Space size="small" wrap style={{ marginBottom: 12 }}>
                    {detail._decider && <Tag color="blue">{detail._decider}</Tag>}
                    <Tooltip title="来源字段 decision.source">
                      <Tag>{isFallback ? '规则兜底' : 'S1 直出'}</Tag>
                    </Tooltip>
                    {detail.meta?.s1_model ? <Tag color="geekblue">S1: {String(detail.meta.s1_model)}</Tag> : null}
                    {detail.meta?.s2_model ? <Tag color="purple">S2: {String(detail.meta.s2_model)}</Tag> : null}
                  </Space>
                  <div style={{ marginBottom: 8 }}>
                    <Typography.Text type="secondary">置信度 </Typography.Text>
                    <Typography.Text strong>{fmtNum(confidence)}</Typography.Text>
                    {typeof confidence === 'number' && typeof effThreshold === 'number' && (
                      <Typography.Text type={confidence >= effThreshold ? 'secondary' : 'warning'}>
                        {' '}｜ 阈值 {fmtNum(effThreshold, 2)}
                        （{confidence >= effThreshold ? '达标' : `低 ${fmtNum(effThreshold - confidence)}`}）
                      </Typography.Text>
                    )}
                  </div>
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', marginBottom: 6 }}>概率分布（decision.probabilities）</div>
                    <ProbBar probs={probs} thresholds={thCfg} />
                  </div>
                  {decision.sdm_usage ? (
                    <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', marginBottom: 8 }}>
                      SDM 计费：input_tokens={String((decision.sdm_usage as Record<string, unknown>).input_tokens ?? '-')}
                      ，cost_usd=
                      {String((decision.sdm_usage as Record<string, unknown>).cost_usd ?? '-')}
                    </div>
                  ) : null}
                  {subs && Object.keys(subs).length > 0 && (
                    <>
                      <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', margin: '8px 0 4px' }}>
                        子信号（decision.sub_signals，仅归因不参与门控）
                      </div>
                      <Table
                        size="small"
                        pagination={false}
                        dataSource={Object.entries(subs).map(([k, v]) => ({ key: k, k, v }))}
                        columns={[
                          { title: '子信号', dataIndex: 'k', width: 240, render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code> },
                          { title: '数值', dataIndex: 'v', render: (v: unknown) => (typeof v === 'number' ? v.toFixed(4) : String(v)) },
                        ]}
                      />
                    </>
                  )}
                </>
              ),
            },
            {
              key: 'state',
              label: '② 市场快照',
              children: (
                <>
                  <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', marginBottom: 6 }}>来源：录制层 state（决策时的行情/持仓快照）</div>
                  <Input
                    placeholder="搜索字段名"
                    allowClear
                    value={stateSearch}
                    onChange={(e) => setStateSearch(e.target.value)}
                    style={{ marginBottom: 8 }}
                  />
                  <KVTable data={(detail.state || {}) as Record<string, unknown>} search={stateSearch} />
                </>
              ),
            },
            {
              key: 'prompt',
              label: '③ Prompt 输入',
              children: (
                <>
                  <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', marginBottom: 6 }}>
                    来源：录制层 questions（发给 S1 的问题集，S2 复用同 state）
                  </div>
                  <Input
                    placeholder="搜索字段名"
                    allowClear
                    value={qSearch}
                    onChange={(e) => setQSearch(e.target.value)}
                    style={{ marginBottom: 8 }}
                  />
                  <KVTable data={(detail.questions || {}) as Record<string, unknown>} search={qSearch} />
                </>
              ),
            },
            {
              key: 'model',
              label: '④ 模型输出',
              children: (
                <>
                  <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', marginBottom: 4 }}>来源：录制层 s1_raw（S1 结构化响应 JSON）</div>
                  {detail.s1_raw ? (
                    <pre style={preStyle}>{prettyJson(detail.s1_raw)}</pre>
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未录制 S1 原始响应（旧版本引擎产生的任务无该字段）" />
                  )}
                  <div style={{ fontSize: 12, color: 'rgba(128,128,128,0.9)', margin: '12px 0 4px' }}>来源：录制层 s2_raw（S2 兜底原始文本，仅兜底时存在）</div>
                  {detail.s2_raw ? (
                    <pre style={preStyle}>{detail.s2_raw}</pre>
                  ) : isFallback ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未录制 S2 原始文本（旧版本引擎产生的任务无该字段）" />
                  ) : null}
                  {detail.s2_thinking && (
                    <Collapse
                      style={{ marginTop: 12 }}
                      items={[{ key: 'thinking', label: 'S2 思考过程（s2_thinking）', children: <pre style={preStyle}>{detail.s2_thinking}</pre> }]}
                    />
                  )}
                </>
              ),
            },
          ]}
        />
      )}
      {!detail && !loading && !error && record && <Empty description="未命中录制内容" />}
    </Drawer>
  );
}
