/**
 * 策略研究列表（design-spec §5 页头 / §6.2 chip / §6.3 卡片 / §6.5 表格 /
 * §6.6 工具栏 / §6.7 分页 / §6.13 空态）。
 * 卡片与表格双视图（视图类型跟随系统设置）+ 搜索 + 模式/状态筛选 + 新建抽屉；
 * 点行/卡片进入 /research/:id。抽屉入参（seed / 复制配置）保持原链路。
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Flex,
  Pagination,
  Row,
  Select,
  Tooltip,
} from 'antd';
import type { TablePaginationConfig } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CopyOutlined,
  DeleteOutlined,
  EyeOutlined,
  FastForwardOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { PAGE_SIZE_OPTIONS, PER_PAGE_OPTIONS } from '@/constants/pagination';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType } from '@/hooks/useViewType';
import { formatTokens } from '@/utils/format';
import PageContainer from '@/components/PageContainer';
import { usePolling } from '@/hooks/usePolling';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import {
  researchApi,
  type ResearchMode,
  type ResearchSession,
  type ResearchStatus,
} from '@/api/research';
import { researchModeChip, researchScenarioChip, researchStatusChip } from './chips';
import ResearchNewDrawer from './ResearchNewDrawer';

/** demo 卡片视图与工具栏是静态稿；真实数据一律取自 /research/sessions 接口 */
const CARD_TIME_FMT = 'MM-DD HH:mm';

/** 状态筛选 chips 顺序（含首位「全部」；词条复用 research_status_*） */
const STATUS_ORDER: ResearchStatus[] = ['pending', 'running', 'paused', 'completed', 'failed', 'cancelled'];

const ResearchList: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = AntApp.useApp();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  // total 初始为 null：首屏未加载时页头副标不渲染「共 0 个会话」的假口径
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'all' | ResearchMode>('all');
  const [status, setStatus] = useState<'all' | ResearchStatus>('all');
  // 关键词即时过滤（demo .tsearch 即时生效）：后端 list 接口无 keyword 参数，
  // ponytail: 搜索走「拉取前 100 条（后端 limit 上限 le=100）+ 客户端过滤」，
  // 超过 100 条的存量会话搜不到；升级路径＝后端补 keyword 检索后换服务端过滤
  const [keyword, setKeyword] = useState('');
  const [searchRows, setSearchRows] = useState<ResearchSession[] | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [initialMode, setInitialMode] = useState<ResearchMode>('deep');
  // 种子因子：因子详情「基于此因子研究」经 /research?seed=<name> 跳入
  const [seedFactor, setSeedFactor] = useState<string | null>(null);
  // 复制配置：把来源会话带进新建抽屉，按它的 config 预填
  const [copyFrom, setCopyFrom] = useState<ResearchSession | null>(null);

  // 分页：pageSize 走全局档位（与其他分页页共用开关），offset/limit 下推到后端真分页
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useGlobalPageSize();
  // 视图类型：跟随系统设置「默认展示类型」，页面不提供切换
  const viewType = useViewType();

  const searching = keyword.trim() !== '';
  const hasFilter = searching || mode !== 'all' || status !== 'all';

  const load = useCallback(async () => {
    const listParams = {
      mode: mode === 'all' ? undefined : mode,
      status: status === 'all' ? undefined : status,
    };
    try {
      // 主请求：按页取；搜索时并行拉全量窗口（≤100 条）做客户端过滤
      const [paged, allRows] = await Promise.all([
        researchApi.list({ ...listParams, limit: pageSize, offset: (page - 1) * pageSize }),
        searching
          ? researchApi.list({ ...listParams, limit: 100, offset: 0 })
          : Promise.resolve(null),
      ]);
      setSessions(paged.sessions);
      setTotal(paged.total);
      setSearchRows(allRows ? allRows.sessions : null);
      // 当前页被删空/筛空时回退到最后一个非空页，避免停留在空白页
      if (paged.sessions.length === 0 && paged.total > 0 && page > 1) {
        setPage(Math.max(1, Math.ceil(paged.total / pageSize)));
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('research_msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [mode, status, page, pageSize, searching, message, t]);

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

  // 行内动作集合：动作随会话状态变化，表格（图标模式）与卡片（文字模式）共用
  // 删除确认弹窗：表格操作列与卡片右上角 extra 共用
  const confirmDeleteSession = (row: ResearchSession) => {
    modal.confirm({
      title: t('research_delete_confirm_title'),
      content: `${t('research_delete_confirm_text')}：${row.name}`,
      okText: t('delete'),
      okButtonProps: { danger: true },
      cancelText: t('cancel'),
      onOk: () => act(() => researchApi.remove(row.id), t('research_msg_deleted')),
    });
  };

  const actionsFor = (row: ResearchSession) => {
    const actions: {
      key: string;
      icon: React.ReactNode;
      label: string;
      hint?: string; // disabled 时 Tooltip 替代文案
      danger?: boolean;
      pri?: boolean; // 主操作（demo 卡片「查看明细」位）用主色 tint
      disabled?: boolean;
      onClick: () => void;
    }[] = [
      { key: 'view', icon: <EyeOutlined />, label: t('view'), pri: true, onClick: () => navigate(`/research/${row.id}`) },
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
      label: t('delete'),
      hint: t('research_delete_only_terminal'),
      danger: true,
      disabled: !deletable,
      onClick: () => confirmDeleteSession(row),
    });
    return actions;
  };

  // 表格操作列（iconOnly）：§6.1 icon-btn 口径的 24px 透明底图标钮，必须带 aria-label
  const renderCellActions = (row: ResearchSession) => (
    <div className="qc-row-actions" onClick={(e) => e.stopPropagation()}>
      {actionsFor(row).map((a) => (
        <Tooltip key={a.key} title={a.disabled && a.hint ? a.hint : a.label}>
          <button
            type="button"
            className={`qc-mini-btn qc-icon-only${a.danger ? ' danger' : ''}`}
            aria-label={a.label}
            disabled={a.disabled}
            onClick={a.onClick}
          >
            {a.icon}
          </button>
        </Tooltip>
      ))}
    </div>
  );

  const columns: ColumnsType<ResearchSession> = [
    {
      title: t('research_col_session'),
      dataIndex: 'name',
      ellipsis: true,
      width: 300,
      render: (name: string, row) => (
        <span className="qc-cell-strat" title={name}>
          {name || t('research_session_fallback', { id: row.id })}
        </span>
      ),
    },
    {
      // 场景/模式标签从「会话」列拆出独立展示，避免名称与标签挤在一列相互截断
      title: t('tags'),
      width: 140,
      render: (_, row) => (
        <span className="qc-row-chips">
          {researchScenarioChip(row, t)}
          {researchModeChip(row, t)}
        </span>
      ),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      width: 110,
      render: (_, row) => researchStatusChip(row, t),
    },
    {
      title: t('research_col_progress'),
      width: 70,
      render: (_, row) => <span className="qc-mono">{`${row.loop_done}/${row.loop_n}`}</span>,
    },
    {
      title: t('research_col_best_icir'),
      width: 100,
      render: (_, row) =>
        typeof row.best_ic_ir === 'number' ? (
          <span className="qc-mono">{row.best_ic_ir.toFixed(4)}</span>
        ) : (
          <span className="qc-cell-none qc-mono">—</span>
        ),
    },
    {
      title: t('research_col_cost'),
      width: 170,
      // nowrap：「13 次 / 139.5K tokens」整体阅读，禁止中间折行
      className: 'whitespace-nowrap',
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
      width: 160,
      // nowrap：完整时间戳一行展示，避免「2026/11/7 0…」被截
      className: 'whitespace-nowrap',
      render: (value: string | null) => (value ? <span className="qc-cell-time qc-mono">{new Date(value).toLocaleString()}</span> : '—'),
    },
    {
      title: t('action'),
      width: 150,
      fixed: 'right',
      render: (_, row) => renderCellActions(row),
    },
  ];

  // —— 数据口径：非搜索走服务端分页窗口；搜索走全量窗口的客户端过滤切片 ——
  const kw = keyword.trim().toLowerCase();
  const searchedRows = (searchRows ?? []).filter(
    (row) =>
      (row.name || '').toLowerCase().includes(kw) ||
      String(row.id).includes(kw) ||
      t('research_session_fallback', { id: row.id }).includes(kw),
  );
  const effTotal = searching ? searchedRows.length : (total ?? 0);
  const pageRows = searching
    ? searchedRows.slice((page - 1) * pageSize, page * pageSize)
    : sessions;

  // 筛选变化回到第一页（§6.6 过滤联动）
  const changeFilter = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value);
    setPage(1);
  };

  // 翻页与条数变更：条数走全局档位（设置页/其他列表页同步生效）；条数变更页码归 1（§7）
  const handlePageChange = (next: number, size: number) => {
    if (size !== pageSize) {
      setPageSize(size);
      setPage(1);
      return;
    }
    setPage(next);
  };

  const paginationCfg: TablePaginationConfig = {
    current: page,
    pageSize,
    total: effTotal,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    onChange: handlePageChange,
  };

  // 工具栏右侧计数「显示 x-y / 共 z」（§6.6 .r-count；空数据归 0）
  const shownRange = () => {
    const start = effTotal === 0 ? 0 : (page - 1) * pageSize + 1;
    const end = Math.min(page * pageSize, effTotal);
    return t('shown_range', { start, end, total: effTotal });
  };

  const openNew = (m: ResearchMode) => {
    setInitialMode(m);
    setNewOpen(true);
  };

  const renderEmpty = () => (
    <QcEmpty
      title={hasFilter ? t('research_empty_filtered') : t('research_empty_desc')}
      description={hasFilter ? undefined : t('research_empty_hint')}
      action={
        hasFilter ? undefined : (
          <Flex gap={8} style={{ marginTop: 6 }}>
            <button type="button" className="qc-mini-btn pri" onClick={() => openNew('deep')}>
              {t('research_mode_deep')}
            </button>
            <button type="button" className="qc-mini-btn" onClick={() => openNew('quick')}>
              {t('research_mode_quick')}
            </button>
          </Flex>
        )
      }
    />
  );

  // §6.7 分页条（与 DataTable 表格分页同一套 .qc-pg-bar 原语，卡片视图复用）
  const renderPgBar = () =>
    effTotal > 0 ? (
      <div className="qc-pg-bar">
        <div className="qc-pg-info">
          <span>{t('total_items', { total: effTotal })}</span>
          <span className="qc-pg-sep">·</span>
          <span>{t('per_page')}</span>
          <Select
            size="small"
            className="qc-pg-size"
            value={pageSize}
            popupMatchSelectWidth={false}
            aria-label={t('per_page')}
            onChange={(size) => handlePageChange(1, size)}
            options={PER_PAGE_OPTIONS.map((n) => ({ value: n, label: String(n) }))}
          />
        </div>
        <Pagination
          size="small"
          className="qc-pagination"
          showLessItems
          showQuickJumper
          showSizeChanger={false}
          current={page}
          pageSize={pageSize}
          total={effTotal}
          onChange={handlePageChange}
          itemRender={(pg, type, node) =>
            type === 'jump-prev' || type === 'jump-next' ? (
              <span className="qc-pg-ellipsis">…</span>
            ) : (
              node
            )
          }
        />
      </div>
    ) : null;

  // 卡片视图 — §6.3 demo .w-head/.w-row2/.card-foot 排版：卡名 mono、chip 组 + mono 时间、
  // 指标行 mono 数值；真实字段（进度/IC_IR/成本/时间/动作）原样保留
  const renderCardView = () => (
    <>
      {pageRows.length === 0 && !loading ? (
        renderEmpty()
      ) : (
        <Row gutter={[12, 12]}>
          {pageRows.map((row) => {
            // 与 actionsFor 同口径：仅终态会话可删除（非终态后端同样拦截 409）
            const deletable = ['completed', 'failed', 'cancelled'].includes(row.status);
            const name = row.name || t('research_session_fallback', { id: row.id });
            return (
              <Col xs={24} sm={12} md={8} lg={6} key={row.id}>
                <Card
                  size="small"
                  hoverable
                  /* §6.3 卡片 chrome（qc-card：bgc 底/--bd 边/10px 圆角/12·14 内边距/head 13px·650）
                     由 global.css 列表卡片段提供（并行车道合入，缺失时回退 antd Card 默认） */
                  className="qc-card"
                  style={{ cursor: 'pointer', height: '100%' }}
                  onClick={() => navigate(`/research/${row.id}`)}
                  title={
                    <span className="qc-mono font-medium truncate" style={{ maxWidth: '100%' }} title={name}>
                      {name}
                    </span>
                  }
                  extra={
                    // 删除统一放卡片右上角；点击不可穿透到卡片跳转
                    <Tooltip title={!deletable ? (t('research_delete_only_terminal')) : (t('delete'))}>
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        disabled={!deletable}
                        onClick={(e) => {
                          e.stopPropagation();
                          confirmDeleteSession(row);
                        }}
                      />
                    </Tooltip>
                  }
                >
                  <Flex vertical gap={8}>
                    <Flex align="center" justify="space-between" gap={6}>
                      <span className="qc-row-chips">
                        {researchScenarioChip(row, t)}
                        {researchModeChip(row, t)}
                        {researchStatusChip(row, t)}
                      </span>
                      <Tooltip title={row.created_at ? new Date(row.created_at).toLocaleString() : ''}>
                        <span className="qc-cell-time qc-mono">
                          {row.created_at ? dayjs(row.created_at).format(CARD_TIME_FMT) : '—'}
                        </span>
                      </Tooltip>
                    </Flex>
                    <Flex justify="space-between" align="center">
                      <span style={{ color: 'var(--qc-text-tertiary)' }}>{t('research_col_progress')}</span>
                      <span className="qc-mono">{`${row.loop_done}/${row.loop_n}`}</span>
                    </Flex>
                    <Flex justify="space-between" align="center">
                      <span style={{ color: 'var(--qc-text-tertiary)' }}>{t('research_col_best_icir')}</span>
                      {typeof row.best_ic_ir === 'number' ? (
                        <span className="qc-mono">{row.best_ic_ir.toFixed(4)}</span>
                      ) : (
                        <span className="qc-cell-none qc-mono">—</span>
                      )}
                    </Flex>
                    <Flex justify="space-between" align="center">
                      <span style={{ color: 'var(--qc-text-tertiary)' }}>{t('research_col_cost')}</span>
                      <Tooltip title={`${row.token_used} tokens`}>
                        <span className="qc-mono">{t('research_cost_format', { calls: row.llm_calls, tokens: formatTokens(row.token_used, '0') })}</span>
                      </Tooltip>
                    </Flex>
                    {/* 操作按钮与表格行同一套动作（文字态，删除已上移卡片右上角） */}
                    <div
                      className="qc-row-actions"
                      style={{ flexWrap: 'wrap', paddingTop: 8, borderTop: '1px dashed var(--qc-border)' }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {actionsFor(row)
                        .filter((a) => a.key !== 'delete')
                        .map((a) => (
                          <button
                            key={a.key}
                            type="button"
                            className={`qc-mini-btn${a.pri ? ' pri' : ''}${a.danger ? ' danger' : ''}`}
                            disabled={a.disabled}
                            onClick={a.onClick}
                          >
                            {a.pri ? a.icon : null}
                            {a.label}
                          </button>
                        ))}
                    </div>
                  </Flex>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
      {renderPgBar()}
    </>
  );

  const renderListView = () => (
    <DataTable<ResearchSession>
      rowKey="id"
      loading={loading}
      columns={columns}
      dataSource={searching ? searchedRows : sessions}
      remote={!searching}
      /* 固定列总宽 860px（标签~操作，会话列 300px），所有列都有显式宽：
         容器不足时若无 scroll.x，无宽列会被压成 0 宽整列消失，声明后表格改为内部横滚 */
      scroll={{ x: 1160 }}
      pagination={effTotal > 0 ? paginationCfg : false}
      emptyTitle={hasFilter ? t('research_empty_filtered') : t('research_empty_desc')}
      emptyDescription={hasFilter ? undefined : t('research_empty_hint')}
      emptyAction={
        hasFilter ? undefined : (
          <Flex gap={8} style={{ marginTop: 6 }}>
            <button type="button" className="qc-mini-btn pri" onClick={() => openNew('deep')}>
              {t('research_mode_deep')}
            </button>
            <button type="button" className="qc-mini-btn" onClick={() => openNew('quick')}>
              {t('research_mode_quick')}
            </button>
          </Flex>
        )
      }
      onRow={(row) => ({
        onClick: () => navigate(`/research/${row.id}`),
        style: { cursor: 'pointer' },
      })}
    />
  );

  return (
    <PageContainer
      title={t('ai_research')}
      // 页头副标 mono 口径行（§5）：只写接口能算出的数字
      subtitle={total != null ? t('research_total_sessions', { total }) : undefined}
      actions={
        <>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            style={{ height: 30, padding: '0 12px', fontSize: 12, fontWeight: 550 }}
            onClick={() => openNew('deep')}
          >
            {t('research_new_btn')}
          </Button>
          <Button
            style={{ height: 30, padding: '0 12px', fontSize: 12 }}
            onClick={() => navigate('/backtest')}
          >
            {t('backtest_center')}
          </Button>
        </>
      }
    >
      <PageToolbar
        search={{
          value: keyword,
          onChange: (value) => {
            setKeyword(value);
            setPage(1);
          },
          placeholder: t('search'),
          ariaLabel: t('search'),
        }}
        filters={
          <>
            <Select
              aria-label={t('research_filter_mode_all')}
              value={mode}
              style={{ width: 140 }}
              onChange={changeFilter(setMode)}
              options={[
                { value: 'all', label: t('research_filter_mode_all') },
                { value: 'quick', label: t('research_mode_quick') },
                { value: 'deep', label: t('research_mode_deep') },
              ]}
            />
            <div role="group" aria-label={t('research_filter_status_all')} style={{ display: 'contents' }}>
              {(['all', ...STATUS_ORDER] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  className={`qc-ichip${status === value ? ' qc-ichip-on' : ''}`}
                  onClick={() => changeFilter(setStatus)(value)}
                >
                  {value === 'all' ? t('research_filter_status_all') : t(`research_status_${value}`)}
                </button>
              ))}
            </div>
          </>
        }
        count={shownRange()}
        actions={
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            {t('refresh')}
          </Button>
        }
      />

      {viewType === 'card' ? renderCardView() : renderListView()}

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
    </PageContainer>
  );
};

export default ResearchList;
