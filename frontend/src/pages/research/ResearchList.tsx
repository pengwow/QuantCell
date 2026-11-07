/**
 * AI 研究会话列表（PRD §6.3/§6.4，v0.3 起为独立一级页面 /research）。
 * 列表 + 筛选 + 新建抽屉 + 空状态引导；点行进入 /research/:id。
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Grid,
  Pagination,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TableProps } from 'antd';
import {
  AppstoreOutlined,
  CopyOutlined,
  DeleteOutlined,
  EyeOutlined,
  FastForwardOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  StopOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType, type ViewType } from '@/hooks/useViewType';
import { formatTokens } from '@/utils/format';
import PageContainer from '@/components/PageContainer';
import { usePolling } from '@/hooks/usePolling';
import {
  researchApi,
  type ResearchMode,
  type ResearchSession,
  type ResearchStatus,
} from '@/api/research';
import ResearchNewDrawer from './ResearchNewDrawer';

// 状态样式与文案：常量只存 i18n key，渲染时用 t() 取当前语言文案
const STATUS_META: Record<ResearchStatus, { color: string; i18nKey: string }> = {
  pending: { color: 'default', i18nKey: 'research_status_pending' },
  running: { color: 'processing', i18nKey: 'research_status_running' },
  paused: { color: 'warning', i18nKey: 'research_status_paused' },
  completed: { color: 'success', i18nKey: 'research_status_completed' },
  failed: { color: 'error', i18nKey: 'research_status_failed' },
  cancelled: { color: 'default', i18nKey: 'research_status_cancelled' },
};

const ResearchList: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = AntApp.useApp();
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

  // 分页：pageSize 走全局档位（与其他分页页共用开关），offset/limit 下推到后端真分页
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useGlobalPageSize();
  const [viewType, setViewType] = useViewType();
  const screens = Grid.useBreakpoint();

  const load = useCallback(async () => {
    try {
      const res = await researchApi.list({
        mode: mode === 'all' ? undefined : mode,
        status: status === 'all' ? undefined : status,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setSessions(res.sessions);
      setTotal(res.total);
      // 当前页被删空/筛空时回退到最后一个非空页，避免停留在空白页
      if (res.sessions.length === 0 && res.total > 0 && page > 1) {
        setPage(Math.max(1, Math.ceil(res.total / pageSize)));
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [mode, status, page, pageSize, message, t]);

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
      message.error(err instanceof Error ? err.message : t('research_msg_action_failed'));
    }
  };

  // 状态徽标：表格列与卡片视图共用（含排队位次展示）
  const statusTag = (row: ResearchSession) => {
    const label = [t(STATUS_META[row.status]?.i18nKey ?? row.status)];
    if (row.status === 'pending' && row.queue_position) {
      label.push(t('research_queue_position', { pos: row.queue_position }));
    }
    return <Tag color={STATUS_META[row.status]?.color}>{label.join(' · ')}</Tag>;
  };

  // 行内动作集合：动作随会话状态变化，表格（图标模式）与卡片（文字模式）共用
  const actionsFor = (row: ResearchSession) => {
    const actions: {
      key: string;
      icon: ReactNode;
      label: string;
      hint?: string; // disabled 时 Tooltip 替代文案
      danger?: boolean;
      disabled?: boolean;
      onClick: () => void;
    }[] = [
      { key: 'view', icon: <EyeOutlined />, label: t('view'), onClick: () => navigate(`/research/${row.id}`) },
    ];
    if (row.status === 'running' && row.mode === 'deep') {
      actions.push({
        key: 'pause', icon: <PauseCircleOutlined />, label: t('research_action_pause'),
        onClick: () => void act(() => researchApi.pause(row.id), t('research_msg_pause_requested')),
      });
    }
    if (row.status === 'paused') {
      actions.push({
        key: 'resume', icon: <PlayCircleOutlined />, label: t('research_action_resume'),
        onClick: () => void act(() => researchApi.resume(row.id), t('research_msg_resumed')),
      });
    }
    if (row.status === 'completed') {
      actions.push({
        key: 'extend', icon: <FastForwardOutlined />, label: t('research_action_extend'),
        onClick: () => void act(() => researchApi.extend(row.id, { extra_loops: 2 }), t('research_msg_extended', { n: 2 })),
      });
    }
    if (['pending', 'running', 'paused'].includes(row.status)) {
      actions.push({
        key: 'cancel', icon: <StopOutlined />, label: t('cancel'), danger: true,
        onClick: () => void act(() => researchApi.cancel(row.id), t('research_msg_cancelled')),
      });
    }
    actions.push({
      key: 'copy', icon: <CopyOutlined />, label: t('research_action_copy_config'),
      onClick: () => {
        setCopyFrom(row);
        setNewOpen(true);
      },
    });
    // 删除仅对终态开放：非终态会话可能仍有作业在跑，后端同样拦截（409）
    const deletable = ['completed', 'failed', 'cancelled'].includes(row.status);
    actions.push({
      key: 'delete',
      icon: <DeleteOutlined />,
      label: t('delete') || '删除',
      hint: t('research_delete_only_terminal') || '仅已结束的会话可删除',
      danger: true,
      disabled: !deletable,
      onClick: () => {
        modal.confirm({
          title: t('research_delete_confirm_title') || '删除研究会话',
          content: `${t('research_delete_confirm_text') || '将删除该会话及其全部试验与事件记录'}：${row.name}`,
          okText: t('delete') || '删除',
          okButtonProps: { danger: true },
          cancelText: t('cancel'),
          onOk: () => act(() => researchApi.remove(row.id), t('research_msg_deleted') || '已删除'),
        });
      },
    });
    return actions;
  };

  // 操作按钮组：表格行尾（iconOnly=图标+Tooltip，与策略管理页操作列一致）与卡片底部（文字按钮）共用
  const renderActions = (row: ResearchSession, iconOnly = false) => {
    const acts = actionsFor(row);
    if (iconOnly) {
      return (
        // 表格行可点击进入详情，操作列阻止冒泡避免误触发行跳转
        <Space size={4} onClick={(e) => e.stopPropagation()}>
          {acts.map((a) => (
            <Tooltip key={a.key} title={a.disabled && a.hint ? a.hint : a.label}>
              <Button type="text" size="small" danger={a.danger} disabled={a.disabled} icon={a.icon} onClick={a.onClick} />
            </Tooltip>
          ))}
        </Space>
      );
    }
    return (
      <Space size={4} onClick={(e) => e.stopPropagation()} wrap>
        {acts.map((a) => (
          <Button key={a.key} size="small" danger={a.danger} disabled={a.disabled} onClick={a.onClick}>
            {a.label}
          </Button>
        ))}
      </Space>
    );
  };

  const columns: ColumnsType<ResearchSession> = [
    {
      title: t('research_col_session'),
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, row) => (
        <Space size={6}>
          <span>{name || t('research_session_fallback', { id: row.id })}</span>
          <Tag color={row.scenario === 'strategy' ? 'geekblue' : row.scenario === 'model' ? 'purple' : 'cyan'}>
            {t(`research_scenario_${row.scenario}`)}
          </Tag>
          {/* PRD §12 #9：quick 被 extend 后 mode 保留 quick + 记 extended_at，列表用复合徽标区分「快速→深入」 */}
          <Tag color={row.mode === 'quick' && row.extended_at ? 'geekblue' : undefined}>
            {row.mode === 'quick'
              ? (row.extended_at ? t('research_mode_quick_extended') : t('research_mode_quick'))
              : t('research_mode_deep')}
          </Tag>
        </Space>
      ),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      width: 100,
      render: (_, row) => statusTag(row),
    },
    { title: t('research_col_progress'), width: 100, render: (_, row) => `${row.loop_done}/${row.loop_n}` },
    {
      title: t('research_col_best_icir'),
      width: 110,
      render: (_, row) => (typeof row.best_ic_ir === 'number' ? row.best_ic_ir.toFixed(4) : '—'),
    },
    {
      title: t('research_col_cost'),
      width: 150,
      // 悬停显示原始 token 数，避免缩写后丢失精度信息
      render: (_, row) => (
        <Tooltip title={`${row.token_used} tokens`}>
          <span>{t('research_cost_format', { calls: row.llm_calls, tokens: formatTokens(row.token_used, '0') })}</span>
        </Tooltip>
      ),
    },
    {
      title: t('created_at'),
      dataIndex: 'created_at',
      width: 170,
      render: (value: string | null) => (value ? new Date(value).toLocaleString() : '—'),
    },
    {
      title: t('action'),
      width: 130,
      fixed: 'right',
      render: (_, row) => renderActions(row, true),
    },
  ];

  const empty = !loading && sessions.length === 0 && mode === 'all' && status === 'all';

  // 分页配置：表格与卡片视图共用同一页码/条数状态
  const sharedPagination: TableProps<ResearchSession>['pagination'] = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    showTotal: (n) => t('total_items', { total: n }),
  };

  // 翻页与条数变更：条数走全局档位（设置页/其他列表页同步生效）
  const handlePageChange = (next: number, size: number) => {
    if (size !== pageSize) setPageSize(size);
    setPage(next);
  };

  // 筛选变化回到第一页
  const changeFilter = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value);
    setPage(1);
  };

  // 卡片视图：网格布局 + 底部分页；操作按钮随状态变化，与表格行一致
  const renderCardView = () => (
    <>
      {sessions.length === 0 ? (
        <Card>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('research_empty_filtered')} />
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
        {sessions.map((row) => (
          <Col xs={24} sm={12} md={8} lg={6} key={row.id}>
            <Card
              size="small"
              hoverable
              style={{ cursor: 'pointer', height: '100%' }}
              onClick={() => navigate(`/research/${row.id}`)}
              title={
                <Flex justify="space-between" align="center" gap={8}>
                  <span className="truncate" style={{ maxWidth: '70%' }}>
                    {row.name || t('research_session_fallback', { id: row.id })}
                  </span>
                  {statusTag(row)}
                </Flex>
              }
            >
              <Flex vertical gap={8}>
                <Space size={6} wrap>
                  <Tag color={row.scenario === 'strategy' ? 'geekblue' : row.scenario === 'model' ? 'purple' : 'cyan'}>
                    {t(`research_scenario_${row.scenario}`)}
                  </Tag>
                  <Tag color={row.mode === 'quick' && row.extended_at ? 'geekblue' : undefined}>
                    {row.mode === 'quick'
                      ? (row.extended_at ? t('research_mode_quick_extended') : t('research_mode_quick'))
                      : t('research_mode_deep')}
                  </Tag>
                </Space>
                <Flex justify="space-between" align="center">
                  <span className="text-gray-500">{t('research_col_progress')}</span>
                  <span>{`${row.loop_done}/${row.loop_n}`}</span>
                </Flex>
                <Flex justify="space-between" align="center">
                  <span className="text-gray-500">{t('research_col_best_icir')}</span>
                  <span>{typeof row.best_ic_ir === 'number' ? row.best_ic_ir.toFixed(4) : '—'}</span>
                </Flex>
                <Flex justify="space-between" align="center">
                  <span className="text-gray-500">{t('research_col_cost')}</span>
                  <Tooltip title={`${row.token_used} tokens`}>
                    <span>{t('research_cost_format', { calls: row.llm_calls, tokens: formatTokens(row.token_used, '0') })}</span>
                  </Tooltip>
                </Flex>
                <Flex justify="space-between" align="center">
                  <span className="text-gray-500">{t('created_at')}</span>
                  <span className="text-sm">
                    {row.created_at ? new Date(row.created_at).toLocaleString() : '—'}
                  </span>
                </Flex>
                <div className="pt-2 border-t border-gray-100">{renderActions(row)}</div>
              </Flex>
            </Card>
          </Col>
        ))}
        </Row>
      )}
      <Row justify="center" style={{ marginTop: 16 }}>
        <Pagination {...sharedPagination} onChange={handlePageChange} />
      </Row>
    </>
  );

  return (
    <PageContainer title={t('ai_research')}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Flex align="center" justify="space-between" wrap gap={8}>
          <Space wrap>
            <Select
              value={mode}
              style={{ width: 140 }}
              onChange={changeFilter(setMode)}
              options={[
                { value: 'all', label: t('research_filter_mode_all') },
                { value: 'quick', label: t('research_mode_quick') },
                { value: 'deep', label: t('research_mode_deep') },
              ]}
            />
            <Select
              value={status}
              style={{ width: 140 }}
              onChange={changeFilter(setStatus)}
              options={[
                { value: 'all', label: t('research_filter_status_all') },
                ...Object.entries(STATUS_META).map(([value, meta]) => ({
                  value,
                  label: t(meta.i18nKey),
                })),
              ]}
            />
            <Button onClick={() => void load()}>{t('refresh')}</Button>
          </Space>
          <Space>
            <Segmented
              value={viewType}
              onChange={(value) => setViewType(value as ViewType)}
              options={[
                { value: 'list', icon: <UnorderedListOutlined />, label: screens.sm ? t('list_view') : undefined },
                { value: 'card', icon: <AppstoreOutlined />, label: screens.sm ? t('card_view') : undefined },
              ]}
            />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setInitialMode('deep');
                setNewOpen(true);
              }}
            >
              {t('research_new_btn')}
            </Button>
          </Space>
        </Flex>

        {empty ? (
          <Card>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('research_empty_desc')}
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
                    {t('research_mode_deep')}
                  </Button>
                  <Button
                    onClick={() => {
                      setInitialMode('quick');
                      setNewOpen(true);
                    }}
                  >
                    {t('research_mode_quick')}
                  </Button>
                </Space>
                <Alert
                  type="info"
                  showIcon
                  title={t('research_empty_hint')}
                />
              </Space>
            </Empty>
          </Card>
        ) : viewType === 'card' ? (
          renderCardView()
        ) : (
          <Table<ResearchSession>
            rowKey="id"
            size="middle"
            loading={loading}
            columns={columns}
            dataSource={sessions}
            /* 固定列总宽 760px（状态~操作，操作列 fixed:'right'），名称列是唯一弹性列：
               容器不足时剩余空间 ≤ 0 会把它压成 0 宽整列消失，声明 scroll.x 让表格改为内部横滚 */
            scroll={{ x: 960 }}
            pagination={sharedPagination}
            onChange={(pg) => handlePageChange(pg.current ?? 1, pg.pageSize ?? pageSize)}
            onRow={(row) => ({
              onClick: () => navigate(`/research/${row.id}`),
              style: { cursor: 'pointer' },
            })}
            locale={{ emptyText: t('research_empty_filtered') }}
          />
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
      </Space>
    </PageContainer>
  );
};

export default ResearchList;
