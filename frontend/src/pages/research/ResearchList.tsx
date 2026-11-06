/**
 * AI 研究会话列表（PRD §6.3/§6.4，v0.3 起为独立一级页面 /research）。
 * 列表 + 筛选 + 新建抽屉 + 空状态引导；点行进入 /research/:id。
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Drawer,
  Empty,
  Flex,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, RobotOutlined } from '@ant-design/icons';
import { formatTokens } from '@/utils/format';
import PageContainer from '@/components/PageContainer';
import { usePolling } from '@/hooks/usePolling';
import {
  researchApi,
  type ResearchMode,
  type ResearchSession,
  type ResearchStatus,
} from '@/api/research';
import MiningHistoryPane from '@/pages/factor/MiningHistoryPane';
import ResearchNewDrawer from './ResearchNewDrawer';

const STATUS_META: Record<ResearchStatus, { color: string; label: string }> = {
  pending: { color: 'default', label: '排队中' },
  running: { color: 'processing', label: '运行中' },
  paused: { color: 'warning', label: '已暂停' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
};

const ResearchList: React.FC = () => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'all' | ResearchMode>('all');
  const [status, setStatus] = useState<'all' | ResearchStatus>('all');
  const [newOpen, setNewOpen] = useState(false);
  const [initialMode, setInitialMode] = useState<ResearchMode>('deep');
  // 种子因子：因子详情「基于此因子研究」经 /research?seed=<name> 跳入
  const [seedFactor, setSeedFactor] = useState<string | null>(null);
  // 复制配置：把来源会话带进新建抽屉，按它的 config 预填
  const [copyFrom, setCopyFrom] = useState<ResearchSession | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await researchApi.list({
        mode: mode === 'all' ? undefined : mode,
        status: status === 'all' ? undefined : status,
        limit: 50,
      });
      setSessions(res.sessions);
      setTotal(res.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '会话列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [mode, status, message]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  // 因子详情「基于此因子研究」入口：?seed=<name> 自动打开新建抽屉并带上种子，
  // 读到即清理 query，避免刷新页面重复弹抽屉
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const seed = searchParams.get('seed');
    if (!seed) return;
    setSeedFactor(seed);
    setInitialMode('deep');
    setNewOpen(true);
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  usePolling(load, { interval: 5000 });

  const act = async (action: () => Promise<unknown>, text: string) => {
    try {
      await action();
      message.success(text);
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const columns: ColumnsType<ResearchSession> = [
    {
      title: '会话',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, row) => (
        <Space size={6}>
          <span>{name || `会话 #${row.id}`}</span>
          <Tag color={row.scenario === 'strategy' ? 'geekblue' : 'cyan'}>
            {row.scenario === 'strategy' ? '策略' : '因子'}
          </Tag>
          <Tag>{row.mode === 'quick' ? '快速验证' : '深度研究'}</Tag>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: ResearchStatus) => (
        <Tag color={STATUS_META[value]?.color}>{STATUS_META[value]?.label ?? value}</Tag>
      ),
    },
    { title: '进度', width: 100, render: (_, row) => `${row.loop_done}/${row.loop_n}` },
    {
      title: '最优 IC_IR',
      width: 110,
      render: (_, row) => (typeof row.best_ic_ir === 'number' ? row.best_ic_ir.toFixed(4) : '—'),
    },
    {
      title: '成本',
      width: 150,
      // 悬停显示原始 token 数，避免缩写后丢失精度信息
      render: (_, row) => (
        <Tooltip title={`${row.token_used} tokens`}>
          <span>{`${row.llm_calls} 次 / ${formatTokens(row.token_used, '0')} tokens`}</span>
        </Tooltip>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string | null) => (value ? new Date(value).toLocaleString() : '—'),
    },
    {
      title: '操作',
      width: 260,
      render: (_, row) => (
        <Space size={4} onClick={(e) => e.stopPropagation()} wrap>
          <Button size="small" onClick={() => navigate(`/research/${row.id}`)}>
            查看
          </Button>
          {row.status === 'running' && row.mode === 'deep' && (
            <Button size="small" onClick={() => void act(() => researchApi.pause(row.id), '已请求暂停')}>
              暂停
            </Button>
          )}
          {row.status === 'paused' && (
            <Button size="small" onClick={() => void act(() => researchApi.resume(row.id), '已继续')}>
              继续
            </Button>
          )}
          {row.status === 'completed' && (
            <Button
              size="small"
              onClick={() =>
                void act(() => researchApi.extend(row.id, { extra_loops: 2 }), '已追加 2 轮研究')
              }
            >
              继续研究
            </Button>
          )}
          {['pending', 'running', 'paused'].includes(row.status) && (
            <Button size="small" danger onClick={() => void act(() => researchApi.cancel(row.id), '已取消')}>
              取消
            </Button>
          )}
          <Button
            size="small"
            onClick={() => {
              setCopyFrom(row);
              setNewOpen(true);
            }}
          >
            复制配置
          </Button>
        </Space>
      ),
    },
  ];

  const empty = !loading && sessions.length === 0 && mode === 'all' && status === 'all';

  return (
    <PageContainer title={t('ai_research')}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Flex align="center" justify="space-between" wrap gap={8}>
          <Space wrap>
            <Select
              value={mode}
              style={{ width: 140 }}
              onChange={(value) => setMode(value)}
              options={[
                { value: 'all', label: '全部模式' },
                { value: 'quick', label: '快速验证' },
                { value: 'deep', label: '深度研究' },
              ]}
            />
            <Select
              value={status}
              style={{ width: 140 }}
              onChange={(value) => setStatus(value)}
              options={[
                { value: 'all', label: '全部状态' },
                ...Object.entries(STATUS_META).map(([value, meta]) => ({
                  value,
                  label: meta.label,
                })),
              ]}
            />
            <Button onClick={() => void load()}>刷新</Button>
          </Space>
          <Space>
            <Button onClick={() => setHistoryOpen(true)}>历史挖掘（只读）</Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setInitialMode('deep');
                setNewOpen(true);
              }}
            >
              新建研究
            </Button>
          </Space>
        </Flex>

        {empty ? (
          <Card>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="还没有研究会话。用 AI 提出假设、自动编码与验证，或先跑一轮快速验证。"
            >
              <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                <Space wrap>
                  <Button
                    type="primary"
                    icon={<RobotOutlined />}
                    onClick={() => {
                      setInitialMode('deep');
                      setNewOpen(true);
                    }}
                  >
                    深度研究
                  </Button>
                  <Button
                    onClick={() => {
                      setInitialMode('quick');
                      setNewOpen(true);
                    }}
                  >
                    快速验证
                  </Button>
                </Space>
                <Alert
                  type="info"
                  showIcon
                  title="深度研究会多轮提出假设并自动编码/评估；快速验证复用现有挖掘，成本更低。所有会话都受 LLM 调用与 Token 预算约束。"
                />
              </Space>
            </Empty>
          </Card>
        ) : (
          <>
            <Table<ResearchSession>
              rowKey="id"
              size="middle"
              loading={loading}
              columns={columns}
              dataSource={sessions}
              pagination={false}
              onRow={(row) => ({
                onClick: () => navigate(`/research/${row.id}`),
                style: { cursor: 'pointer' },
              })}
              locale={{ emptyText: '没有符合条件的会话' }}
            />
            <span style={{ color: '#8c8c8c' }}>共 {total} 个会话</span>
          </>
        )}

        <ResearchNewDrawer
          open={newOpen}
          initialMode={initialMode}
          seedFactor={seedFactor}
          copyFrom={copyFrom}
          onClose={() => {
            setNewOpen(false);
            setCopyFrom(null);
            setSeedFactor(null);
          }}
          onCreated={(id) => navigate(`/research/${id}`)}
        />

        <Drawer
          title="历史 LLM 挖掘（只读）"
          open={historyOpen}
          size="50%"
          onClose={() => setHistoryOpen(false)}
          destroyOnClose
        >
          <MiningHistoryPane
            onReuse={() => {
              message.info('请用「新建研究 → 快速验证」复用挖掘参数');
              setHistoryOpen(false);
              setInitialMode('quick');
              setNewOpen(true);
            }}
          />
        </Drawer>
      </Space>
    </PageContainer>
  );
};

export default ResearchList;
