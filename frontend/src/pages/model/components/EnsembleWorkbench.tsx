import { useEffect, useState } from 'react';
import type { Key } from 'react';
import {
  App as AntdApp,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { TableProps } from 'antd';
import { DeleteOutlined, ExperimentOutlined, LineChartOutlined, PlusOutlined, RocketOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { ensembleApi } from '@/api/ensembleApi';
import type { EnsembleInfo, EnsemblePredictResult } from '@/api/ensembleApi';
import type { EnsembleBacktestResult } from '@/api/ensembleApi';
import { modelApi } from '@/api/modelApi';
import type { UnifiedModelRow } from '@/api/modelApi';

// 模型文件名 → stem:后端契约用 stem,解析为 MODELS_DIR/{stem}.zip
const fileNameToStem = (name: string) => name.replace(/\.zip$/, '');

const INTERVAL_OPTIONS = [
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
];

export default function EnsembleWorkbench() {
  const { message, modal } = AntdApp.useApp();
  const navigate = useNavigate();
  const [ensembles, setEnsembles] = useState<EnsembleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  // 创建区:已选模型 stem(Tag 可移除)。策略下拉已移除(D2):聚合口径固定均值
  const [selected, setSelected] = useState<string[]>([]);

  // 模型选择弹窗:复用模型总表数据,默认过滤文件缺失条目
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [candidates, setCandidates] = useState<UnifiedModelRow[]>([]);
  const [searchText, setSearchText] = useState('');
  const [modalSelected, setModalSelected] = useState<Key[]>([]);

  // 冒烟预测:正在预测的行 id + 结果弹窗数据(记录行用于对齐成员动作空间)
  const [predictingId, setPredictingId] = useState<string | null>(null);
  const [predictRecord, setPredictRecord] = useState<EnsembleInfo | null>(null);
  const [predictResult, setPredictResult] = useState<EnsemblePredictResult | null>(null);

  // 集成回测:弹窗 + 表单 + 提交中 + 结果
  const [btOpen, setBtOpen] = useState(false);
  const [btRecord, setBtRecord] = useState<EnsembleInfo | null>(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btResult, setBtResult] = useState<EnsembleBacktestResult | null>(null);
  const [btForm] = Form.useForm();

  const loadEnsembles = async () => {
    setLoading(true);
    try {
      const data = await ensembleApi.listEnsembles();
      setEnsembles(Array.isArray(data) ? data : []);
    } catch {
      message.error('加载集成列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEnsembles();
  }, []);

  const openModal = async () => {
    setModalOpen(true);
    setModalLoading(true);
    setSearchText('');
    try {
      const rows = await modelApi.unifiedModels();
      // 文件缺失(size_mb == null)的条目无法参与集成,直接过滤
      setCandidates(Array.isArray(rows) ? rows.filter((r) => r.size_mb != null) : []);
      // 重开弹窗时回显已选
      setModalSelected([...selected]);
    } catch {
      message.error('加载模型列表失败');
    } finally {
      setModalLoading(false);
    }
  };

  const filteredCandidates = candidates.filter((r) => {
    if (!searchText) return true;
    const name = (r.model_id ?? r.file_name).toLowerCase();
    return name.includes(searchText.toLowerCase());
  });

  const confirmSelect = () => {
    setSelected(modalSelected.map(String));
    setModalOpen(false);
  };

  const handleCreate = async () => {
    if (selected.length === 0) return;
    setCreating(true);
    try {
      // D2:聚合口径固定 mean(strategy 在后端仅存档,不影响信号)
      const result = await ensembleApi.createEnsemble({ strategy: 'mean', model_paths: selected });
      message.success(`集成 ${result.ensemble_id} 创建成功`);
      if (result.skipped?.length) {
        message.warning(`其中 ${result.skipped.length} 个模型加载失败被跳过`);
      }
      setSelected([]);
      setModalSelected([]);
      await loadEnsembles();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建失败');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = (record: EnsembleInfo) => {
    modal.confirm({
      title: '删除集成',
      content: `确定删除集成 ${record.id} 吗？该操作不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await ensembleApi.deleteEnsemble(record.id);
        message.success('集成已删除');
        loadEnsembles();
      },
    });
  };

  // D1 零观测冒烟:不传 observation,后端按 meta.features 全填 0(标准化均值点)
  const handlePredict = async (record: EnsembleInfo) => {
    setPredictingId(record.id);
    try {
      const result = await ensembleApi.predict(record.id, {});
      setPredictRecord(record);
      setPredictResult(result);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '冒烟预测失败');
    } finally {
      setPredictingId(null);
    }
  };

  const openBacktest = (record: EnsembleInfo) => {
    setBtRecord(record);
    setBtResult(null);
    btForm.setFieldsValue({ symbol: 'BTCUSDT', interval: '1h', initial_capital: 100000 });
    setBtOpen(true);
  };

  const handleBacktest = async (values: { symbol: string; interval: string; initial_capital: number }) => {
    if (!btRecord) return;
    setBtLoading(true);
    try {
      const result = await ensembleApi.backtestEnsemble(btRecord.id, values);
      setBtResult(result);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '集成回测失败');
    } finally {
      setBtLoading(false);
    }
  };

  // D4:跳策略编辑器新建 RL 策略,经路由 state 预填 ensemble_id
  const goCreateStrategy = (record: EnsembleInfo) => {
    navigate('/strategy-editor', { state: { prefillEnsembleId: record.id } });
  };

  const candidateColumns: TableProps<UnifiedModelRow>['columns'] = [
    {
      title: '模型名称', dataIndex: 'file_name', key: 'file_name', ellipsis: true,
      render: (text: string, record) => (
        <Tooltip title={record.model_id ? `${record.model_id}（${text}）` : text}>
          <span className="truncate">{record.model_id ?? text}</span>
        </Tooltip>
      ),
    },
    {
      title: '算法', dataIndex: 'algorithm', key: 'algorithm', width: 110,
      render: (a: string) => (a && a !== '-' ? <Tag color="blue">{a}</Tag> : '-'),
    },
    {
      title: '大小', dataIndex: 'size_mb', key: 'size_mb', width: 90, align: 'right',
      render: (v: number | null) => (v == null ? '-' : `${v} MB`),
    },
  ];

  const ensembleColumns: TableProps<EnsembleInfo>['columns'] = [
    {
      title: '集成 ID', dataIndex: 'id', key: 'id', width: 120,
      render: (id: string) => <Tag>{id}</Tag>,
    },
    {
      title: '聚合', key: 'strategy', width: 100,
      // D2:方案 A 聚合口径固定均值,records.strategy 仅存档,不再渲染历史投票值
      render: () => <Tag color="blue">均值聚合</Tag>,
    },
    { title: '模型数', dataIndex: 'models', key: 'models', width: 80, align: 'right' },
    {
      title: '模型列表', key: 'model_paths', width: 260,
      render: (_, record) => {
        const members = record.members ?? [];
        // 旧记录无 members 字段时降级为纯名称列表(维持原展示)
        if (members.length === 0) {
          return (
            <Tooltip title={record.model_paths.join('、')}>
              <span className="truncate">{record.model_paths.join('、') || '-'}</span>
            </Tooltip>
          );
        }
        return (
          <Tooltip title={members.map((m) => `${m.stem}（${m.action_space === 'box' ? '连续' : '离散'}）`).join('、')}>
            <Space size={4} wrap>
              {members.map((m) => (
                <span key={m.stem}>
                  {/* 成员动作空间:box=连续(0~1) / discrete=离散投票映射 */}
                  <Tag color={m.action_space === 'box' ? 'blue' : 'default'}>
                    {m.action_space === 'box' ? '连续' : '离散'}
                  </Tag>
                  {m.stem}
                </span>
              ))}
            </Space>
          </Tooltip>
        );
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      className: 'whitespace-nowrap',
      render: (ts: number | null) => (ts ? dayjs(ts * 1000).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作', key: 'actions', width: 190, fixed: 'right',
      render: (_, record) => (
        <Space size={0}>
          <Tooltip title="零观测冒烟预测">
            <Button
              type="text"
              size="small"
              icon={<ExperimentOutlined />}
              loading={predictingId === record.id}
              onClick={() => handlePredict(record)}
            />
          </Tooltip>
          <Tooltip title="集成回测">
            <Button type="text" size="small" icon={<LineChartOutlined />} onClick={() => openBacktest(record)} />
          </Tooltip>
          <Tooltip title="用此集成新建 RL 策略">
            <Button type="text" size="small" icon={<RocketOutlined />} onClick={() => goCreateStrategy(record)} />
          </Tooltip>
          <Tooltip title="删除">
            <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title="创建集成" size="small">
        <Space wrap>
          <Button icon={<PlusOutlined />} onClick={openModal}>选择模型</Button>
          <Button type="primary" disabled={selected.length === 0} loading={creating} onClick={handleCreate}>
            创建集成{selected.length > 0 ? `（${selected.length}）` : ''}
          </Button>
        </Space>
        {selected.length > 0 && (
          <div className="mt-3">
            <Space size={4} wrap>
              {selected.map((s) => (
                <Tag
                  key={s}
                  closable
                  onClose={() => setSelected((prev) => prev.filter((x) => x !== s))}
                >
                  {s}
                </Tag>
              ))}
            </Space>
          </div>
        )}
      </Card>

      <Card title="集成列表" size="small">
        <Table<EnsembleInfo>
          columns={ensembleColumns}
          dataSource={ensembles}
          loading={loading}
          rowKey="id"
          size="small"
          scroll={{ x: 980 }}
          pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
        />
      </Card>

      {/* 冒烟预测结果弹窗:D1 零观测,展示聚合结果 + 成员明细 */}
      <Modal
        title={`冒烟预测 — ${predictRecord?.id ?? ''}`}
        open={predictResult !== null}
        width={560}
        footer={<Button onClick={() => setPredictResult(null)}>关闭</Button>}
        onCancel={() => setPredictResult(null)}
      >
        {predictResult && predictRecord && (
          <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
            <Descriptions size="small" column={3}>
              <Descriptions.Item label="聚合动作">
                <Tag color={predictResult.action_type === 'buy' ? 'green' : 'default'}>
                  {predictResult.action_type === 'buy' ? 'BUY' : 'HOLD'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="目标仓位 ratio">
                {(predictResult.ratio * 100).toFixed(2)}%
              </Descriptions.Item>
              <Descriptions.Item label="一致性置信度">
                {(predictResult.confidence * 100).toFixed(1)}%
              </Descriptions.Item>
            </Descriptions>
            <Table
              size="small"
              rowKey="stem"
              pagination={false}
              dataSource={predictResult.members.map((m) => ({
                stem: m.stem,
                // 动作空间从列表记录 members 元数据按 stem 对号;旧记录缺失显示 '-'
                action_space: predictRecord.members?.find((x) => x.stem === m.stem)?.action_space,
                ratio: m.ratio,
              }))}
              columns={[
                { title: '成员', dataIndex: 'stem', key: 'stem' },
                {
                  title: '类型', dataIndex: 'action_space', key: 'action_space', width: 80,
                  render: (a?: string) =>
                    a ? <Tag color={a === 'box' ? 'blue' : 'default'}>{a === 'box' ? '连续' : '离散'}</Tag> : '-',
                },
                {
                  title: 'ratio', dataIndex: 'ratio', key: 'ratio', width: 110, align: 'right' as const,
                  render: (r: number | null) => (r == null ? <Tag>弃权</Tag> : r.toFixed(4)),
                },
              ]}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              零观测冒烟（observation 全 0，即标准化均值点）：仅验证成员推理与均值聚合管线，不构成交易信号。
            </Typography.Text>
          </Space>
        )}
      </Modal>

      {/* 集成回测弹窗:表单 → 结果(可再次回测) */}
      <Modal
        title={`集成回测 — ${btRecord?.id ?? ''}`}
        open={btOpen}
        width={560}
        onCancel={() => setBtOpen(false)}
        footer={
          btResult
            ? [
                <Button key="again" onClick={() => setBtResult(null)}>再次回测</Button>,
                <Button key="close" type="primary" onClick={() => setBtOpen(false)}>关闭</Button>,
              ]
            : [
                <Button key="cancel" onClick={() => setBtOpen(false)}>取消</Button>,
                <Button key="run" type="primary" loading={btLoading} onClick={() => btForm.submit()}>
                  开始回测
                </Button>,
              ]
        }
      >
        {btResult ? (
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="PnL">{btResult.total_pnl.toFixed(2)} USDT</Descriptions.Item>
            <Descriptions.Item label="收益率">{btResult.total_return_pct.toFixed(2)}%</Descriptions.Item>
            <Descriptions.Item label="Sharpe">{btResult.sharpe_ratio.toFixed(3)}</Descriptions.Item>
            <Descriptions.Item label="最大回撤">{btResult.max_drawdown_pct.toFixed(2)}%</Descriptions.Item>
            <Descriptions.Item label="胜率">{(btResult.win_rate * 100).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="成交笔数">{btResult.num_trades}</Descriptions.Item>
            <Descriptions.Item label="手续费">{btResult.total_fees.toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="资金费盈亏">{btResult.total_funding.toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="K线数">{btResult.data_bars}</Descriptions.Item>
            <Descriptions.Item label="引擎">
              <Tag color="purple">{btResult.engine}</Tag>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Form form={btForm} layout="vertical" onFinish={handleBacktest}>
            <Form.Item name="symbol" label="交易对" rules={[{ required: true, message: '请输入交易对' }]}>
              <Input placeholder="如 BTCUSDT" />
            </Form.Item>
            <Form.Item name="interval" label="K线周期" rules={[{ required: true, message: '请选择周期' }]}>
              <Select options={INTERVAL_OPTIONS} />
            </Form.Item>
            <Form.Item name="initial_capital" label="初始资金" rules={[{ required: true, message: '请输入初始资金' }]}>
              <InputNumber min={1000} step={10000} style={{ width: '100%' }} addonAfter="USDT" />
            </Form.Item>
          </Form>
        )}
      </Modal>

      <Modal
        title="选择模型"
        open={modalOpen}
        width={680}
        onOk={confirmSelect}
        onCancel={() => setModalOpen(false)}
        okText="确定"
        cancelText="取消"
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Input
            placeholder="搜索模型名称"
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <Table<UnifiedModelRow>
            columns={candidateColumns}
            dataSource={filteredCandidates}
            loading={modalLoading}
            size="small"
            pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 条` }}
            // rowKey 用 stem:确认后直接作为 model_paths 传给后端,免去二次映射
            rowKey={(r) => fileNameToStem(r.file_name)}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: modalSelected,
              onChange: (keys) => setModalSelected(keys),
            }}
          />
        </Space>
      </Modal>
    </Space>
  );
}
