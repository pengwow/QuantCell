/**
 * Worker 详情页
 *
 * 6 个 tab 布局（顺序：总览、交易、决策、风控、参数、日志）
 * - URL hash 同步：切换 tab 时更新 hash，刷新页面时根据 hash 恢复
 * - 旧 hash (#performance/#stats) 兼容：自动重定向到 #overview 并 toast 提示
 * - 页面头部「最后更新时间」每 60s 刷新
 * - 所有 tab 标签使用 i18n 翻译
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { App, Card, Button, Tabs, Spin, Alert, Tooltip } from 'antd';
import { ClockCircleOutlined, FolderAddOutlined, LoadingOutlined, ShareAltOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { formatUSD } from '@/utils/format';
import { archiveWorkerJournal } from '../../api/workerApi';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerStatusText } from '../../types/worker';
import { workerStatusChip } from '../../components/worker/statusChip';
import WorkerParamsTab from '../../components/worker/WorkerParamsTab';
import WorkerOverviewTab from '../../components/worker/WorkerOverviewTab';
import WorkerDecisionsTab from '../../components/worker/WorkerDecisionsTab';
import WorkerOrderTab from '../../components/worker/WorkerOrderTab';
import WorkerRiskTab from '../../components/worker/WorkerRiskTab';
import WorkerLogsTab from '../../components/worker/WorkerLogsTab';
import WorkerShareModal from '../../components/worker/WorkerShareModal';
import WorkerEditModal from '../../components/worker/WorkerEditModal';
import { LEGACY_HASH_MAP, VALID_TABS, type TabKey } from './workerDetailTabs';

dayjs.extend(relativeTime);

const DEFAULT_TAB: TabKey = 'overview';

const WorkerDetail = () => {
  const { t } = useTranslation();
  const { workerId } = useParams<{ workerId: string }>();
  const navigate = useNavigate();
  const { message, modal } = App.useApp();

  const [activeTab, setActiveTab] = useState<TabKey>(DEFAULT_TAB);
  // 初始时间戳使用懒初始化，避免每次渲染重新计算
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(() => Date.now());
  // 分享 modal 的 open 状态
  const [shareOpen, setShareOpen] = useState<boolean>(false);
  // 编辑 modal 的 open 状态
  const [editOpen, setEditOpen] = useState<boolean>(false);
  // 风控配置重拉信号量：编辑保存成功后递增，触发风控 tab 的 WorkerRiskControlCard 重拉
  const [riskReloadKey, setRiskReloadKey] = useState<number>(0);

  const {
    workers,
    selectedWorker,
    overview,
    loading,
    error,
    fetchWorkers,
    fetchWorkerDetail,
    setSelectedWorker,
    clearErrors,
  } = useWorkerStore();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('worker_detail'));
  }, [t]);

  // URL hash 同步：初始化时根据 hash 激活 tab，监听 hashchange
  useEffect(() => {
    const applyHash = () => {
      const raw = window.location.hash.replace('#', '').trim();
      if (!raw) {
        setActiveTab(DEFAULT_TAB);
        return;
      }
      // 旧 hash 兼容
      if (raw in LEGACY_HASH_MAP) {
        const newTab = LEGACY_HASH_MAP[raw];
        message.info(t('worker_legacy_hash_merged'), 2);
        window.location.hash = `#${newTab}`;
        return;
      }
      // 合法 tab
      if (VALID_TABS.includes(raw as TabKey)) {
        setActiveTab(raw as TabKey);
      } else {
        setActiveTab(DEFAULT_TAB);
      }
    };
    applyHash();
    window.addEventListener('hashchange', applyHash);
    return () => window.removeEventListener('hashchange', applyHash);
  }, [message, t]);

  // 切换 tab 时更新 URL hash
  const handleTabChange = (key: string) => {
    setActiveTab(key as TabKey);
    if (window.location.hash !== `#${key}`) {
      // 使用 history.replaceState 避免触发额外的 hashchange
      window.history.replaceState(null, '', `#${key}`);
    }
    setLastUpdateTime(Date.now());
  };

  // 拉取 worker 列表以查找当前 worker
  useEffect(() => {
    if (workerId) {
      fetchWorkers();
    }
  }, [workerId, fetchWorkers]);

  // 拉取详情接口数据：_state_info.error_message 仅 GET /workers/{id} 返回（列表接口不含），
  // 头部「失败原因」提示依赖它
  useEffect(() => {
    if (workerId) {
      fetchWorkerDetail(parseInt(workerId));
    }
  }, [workerId, fetchWorkerDetail]);

  // 找到当前查看的 worker
  const currentWorker = workers.find((w) => w.id === parseInt(workerId || '0')) || null;

  // 同步到 selectedWorker
  useEffect(() => {
    if (currentWorker && (!selectedWorker || selectedWorker.id !== currentWorker.id)) {
      setSelectedWorker(currentWorker);
    }
  }, [currentWorker, selectedWorker, setSelectedWorker]);

  // 「最后更新时间」每 60s 刷新（基于 overview 数据 updatedAt + 当前时间）
  useEffect(() => {
    const timer = setInterval(() => {
      setLastUpdateTime(Date.now());
    }, 60_000);
    return () => clearInterval(timer);
  }, []);

  // 归档 journal：二次确认后调用归档 API，成功后刷新详情（journal 移走 → 下次启动 fresh start）
  const handleArchive = useCallback(() => {
    if (!currentWorker) return;
    // paper 走 PaperDriver 内存撮合，从不产生 journal——归档对它无从谈起
    if (currentWorker.trading_config?.trading_mode === 'paper') {
      message.warning(t('worker_archive_paper_hint'));
      return;
    }
    // String() 解耦 status 字面量类型：后端允许 error 态归档，前端类型未必含该字面量
    const status = String(currentWorker.status ?? '');
    // 运行时门槛兜底：按钮 disabled 只是 UI 层拦截，弹窗打开间隙状态可能已变化
    if (!['stopped', 'error'].includes(status)) {
      message.warning(t('worker_archive_not_allowed'));
      return;
    }
    modal.confirm({
      title: t('worker_archive_confirm_title'),
      content: t('worker_archive_confirm_content', { name: currentWorker.name || t('worker_default_name') }),
      okText: t('worker_archive_ok'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          const result = await archiveWorkerJournal(currentWorker.id);
          message.success(t('worker_archive_success', { total: result.archived.length }));
          await fetchWorkerDetail(currentWorker.id);
        } catch (e) {
          // ApiError extends Error，e.message 已由响应拦截器填好后端错误信息
          const errorMsg = e instanceof Error ? e.message : String(e);
          message.error(t('worker_archive_failed', { message: errorMsg }));
        }
      },
    });
  }, [currentWorker, fetchWorkerDetail, message, modal, t]);

  // 只在 worker 确实不存在时整页替换 Spin。不能加 loading 条件：fetchWorkers 会
  // 置 store.loading=true，若此处整页 return 会卸载所有 tab（滚动位置丢失、轮询重启）；
  // 下方 <Spin spinning={loading}> 已提供非破坏性加载遮罩
  if (!currentWorker) {
    return (
      <PageContainer>
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: 400,
          }}
        >
          <Spin indicator={<LoadingOutlined style={{ fontSize: 48 }} spin />} description={t('loading')} />
        </div>
      </PageContainer>
    );
  }

  // 头部基础配置展示所需（口径同原 params tab basic_config 卡）
  const workerConfig = currentWorker.config ?? {};

  // 6 个 tab 顺序：总览 → 交易 → 决策 → 风控 → 参数 → 日志
  // 所有标签使用 i18n
  const tabItems = [
    {
      key: 'overview',
      label: t('overview'),
      children: (
        <WorkerOverviewTab
          workerId={currentWorker.id}
          active={activeTab === 'overview'}
          onNavigate={handleTabChange}
        />
      ),
    },
    {
      key: 'trades',
      label: t('trades'),
      children: <WorkerOrderTab workerId={currentWorker.id} active={activeTab === 'trades'} />,
    },
    {
      key: 'decisions',
      label: t('decisions'),
      children: <WorkerDecisionsTab workerId={currentWorker.id} active={activeTab === 'decisions'} />,
    },
    {
      key: 'risk',
      label: t('risk_tab'),
      children: (
        <WorkerRiskTab
          workerId={currentWorker.id}
          active={activeTab === 'risk'}
          reloadKey={riskReloadKey}
          onEdit={() => setEditOpen(true)}
        />
      ),
    },
    {
      key: 'params',
      label: t('parameters'),
      children: <WorkerParamsTab worker={currentWorker} />,
    },
    {
      key: 'logs',
      label: t('logs'),
      children: <WorkerLogsTab workerId={currentWorker.id} />,
    },
  ];

  // 「最后更新时间」显示文本
  const lastUpdateText = overview?.updatedAt
    ? dayjs(overview.updatedAt).fromNow()
    : dayjs(lastUpdateTime).fromNow();

  // 页头副标（§5 page-sub）：mono 真值口径——编号 · 标的 · 交易所（状态位在右侧 actions 的 chip 上）
  const symbolsText = currentWorker.trading_config?.symbols_config?.symbols?.join(', ') || '—';
  const modeLabel =
    currentWorker.trading_config?.trading_mode === 'live'
      ? t('env_live')
      : currentWorker.trading_config?.trading_mode === 'testnet'
        ? t('env_testnet')
        : t('env_paper');
  const subtitleText = `#${currentWorker.id} · ${symbolsText} · ${currentWorker.trading_config?.exchange || '—'}`;

  // 头部事实条（demo .ws-strip/.s-chip 口径）：中性描边胶囊 + label + mono 真值
  const pnlProfit = currentWorker.total_profit || 0;

  return (
    <PageContainer
      title={currentWorker.name}
      subtitle={subtitleText}
      onBack={() => navigate('/strategy-worker')}
      actions={
        <>
          {workerStatusChip(currentWorker.status, t(WorkerStatusText[currentWorker.status]))}
          <Button
            icon={<ShareAltOutlined />}
            style={{ height: 30 }}
            disabled={!currentWorker}
            onClick={() => setShareOpen(true)}
          >
            {t('share.button')}
          </Button>
          {/* paper 无 journal 可归档：disabled + Tooltip 说明（disabled 按钮事件不触发，
           *  Tooltip 必须包在外层才能悬浮提示） */}
          <Tooltip
            title={
              currentWorker?.trading_config?.trading_mode === 'paper'
                ? t('worker_archive_paper_hint')
                : undefined
            }
          >
            <Button
              danger
              icon={<FolderAddOutlined />}
              style={{ height: 30 }}
              disabled={
                !currentWorker
                || currentWorker.trading_config?.trading_mode === 'paper'
                || !['stopped', 'error'].includes(String(currentWorker.status ?? ''))
              }
              onClick={handleArchive}
            >
              {t('worker_archive_reanchor')}
            </Button>
          </Tooltip>
        </>
      }
    >
      <Spin spinning={loading}>
        {/* 错误提示 */}
        {error && (
          <Alert
            type="error"
            showIcon
            closable
            onClose={clearErrors}
            style={{ marginBottom: 12 }}
            description={error}
          />
        )}

        {/* 启动/运行失败原因：仅 error 状态且有记录时展示（error_message 来自详情接口） */}
        {currentWorker.status === 'error' && selectedWorker?._state_info?.error_message && (
          <Alert
            type="error"
            showIcon
            title={t('error_reason')}
            description={selectedWorker._state_info.error_message}
            style={{ marginBottom: 12 }}
          />
        )}

        {/* 头部事实条：周期 / 模式 / 累计盈亏 / 初始资金 / 杠杆 / 下单方式，最右为最后更新时间 */}
        <div className="qc-strip">
          <span className="qc-strip-item">{t('timeframe')} <b>{currentWorker.trading_config?.interval || '—'}</b></span>
          <span className="qc-strip-item">{t('trading_mode')} <b>{modeLabel}</b></span>
          <span className="qc-strip-item">
            {t('total_profit')}
            <b className={pnlProfit > 0 ? 'qc-cell-up' : pnlProfit < 0 ? 'qc-cell-down' : undefined}>
              {formatUSD(currentWorker.total_profit, { showSign: true })}
            </b>
          </span>
          <span className="qc-strip-item">
            {t('total_investment')}
            <b>${typeof workerConfig.initial_capital === 'number' ? workerConfig.initial_capital.toFixed(2) : '—'}</b>
          </span>
          <span className="qc-strip-item">{t('leverage')} <b>{workerConfig.leverage ? `${String(workerConfig.leverage)}x` : '1x'}</b></span>
          <span className="qc-strip-item">{t('order_type')} <b>{t('market_order')}</b></span>
          <span
            className="qc-mono"
            style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color: 'var(--qc-text-quaternary)' }}
          >
            <ClockCircleOutlined />
            {t('worker_last_updated', { time: lastUpdateText })}
          </span>
        </div>

        {/* 标签页内容区（§6.8 页签：全站统一下划线式，无需 size 特调） */}
        <Card className="qc-card">
          <Tabs
            activeKey={activeTab}
            onChange={handleTabChange}
            items={tabItems}
          />
        </Card>

        {/* 分享配置 Modal（受控） */}
        <WorkerShareModal
          open={shareOpen}
          workerId={currentWorker.id}
          workerName={currentWorker.name}
          onClose={() => setShareOpen(false)}
        />

        {/* 编辑 Worker Modal（受控）：保存成功后刷新列表并递增风控 tab 重拉信号量 */}
        <WorkerEditModal
          visible={editOpen}
          worker={currentWorker}
          onCancel={() => setEditOpen(false)}
          onSuccess={() => {
            fetchWorkers();
            setRiskReloadKey((k) => k + 1);
          }}
        />
      </Spin>
    </PageContainer>
  );
};

export default WorkerDetail;
