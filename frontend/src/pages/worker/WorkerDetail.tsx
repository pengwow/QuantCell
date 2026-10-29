import { QUANT_COLORS } from '@/utils/colors';
/**
 * Worker 详情页
 *
 * 6 个 tab 布局（顺序：总览、持仓、成交分组、委托、参数、日志）
 * - URL hash 同步：切换 tab 时更新 hash，刷新页面时根据 hash 恢复
 * - 旧 hash (#performance/#stats) 兼容：自动重定向到 #overview 并 toast 提示
 * - 页面头部 Card 增加「最后更新时间」字段，每 60s 刷新
 * - 所有 tab 标签使用 i18n 翻译
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { App, Card, Button, Tabs, Spin, Row, Col, Tag, Space, Descriptions, Alert } from 'antd';
import { ArrowLeftOutlined, ClockCircleOutlined, FolderAddOutlined, LoadingOutlined, ShareAltOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import relativeTime from 'dayjs/plugin/relativeTime';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { archiveWorkerJournal } from '../../api/workerApi';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerStatusColor, WorkerStatusText } from '../../types/worker';
import WorkerParamsTab from '../../components/worker/WorkerParamsTab';
import WorkerOverviewTab from '../../components/worker/WorkerOverviewTab';
import WorkerPositionTab from '../../components/worker/WorkerPositionTab';
import WorkerTradesGroupedTab from '../../components/worker/WorkerTradesGroupedTab';
import WorkerOrderTab from '../../components/worker/WorkerOrderTab';
import WorkerLogsTab from '../../components/worker/WorkerLogsTab';
import WorkerShareModal from '../../components/worker/WorkerShareModal';
import WorkerEditModal from '../../components/worker/WorkerEditModal';

dayjs.extend(relativeTime);

// Tab key 类型
type TabKey = 'params' | 'overview' | 'positions' | 'tradesGrouped' | 'orders' | 'logs';

// 合法 tab key
const VALID_TABS: TabKey[] = ['params', 'overview', 'positions', 'tradesGrouped', 'orders', 'logs'];

// 旧 hash -> 新 hash 映射
// TODO(ux-hash-compat): 这是 URL hash 的 UX 兼容（旧分享链接），并非旧数据协议；
// 待旧版分享链接自然淘汰（预计 2026-12）后移除。
const LEGACY_HASH_MAP: Record<string, TabKey> = {
  performance: 'overview',
  stats: 'overview',
  trading_stats: 'overview',
  position: 'positions', // 单数兼容
};

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
  // 参数 tab 重拉信号量：编辑保存成功后递增，触发 WorkerParamsTab 重拉风控配置
  const [paramsReloadKey, setParamsReloadKey] = useState<number>(0);

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
    setPageTitle(t('worker_detail') || '策略详情');
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
        message.info('该视图已合并到 总览', 2);
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
  }, [message]);

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
    // String() 解耦 status 字面量类型：后端允许 error 态归档，前端类型未必含该字面量
    const status = String(currentWorker.status ?? '');
    // 运行时门槛兜底：按钮 disabled 只是 UI 层拦截，弹窗打开间隙状态可能已变化
    if (!['stopped', 'error'].includes(status)) {
      message.warning('仅已停止或异常状态的 Worker 可归档');
      return;
    }
    modal.confirm({
      title: '归档 journal 并 fresh start？',
      content: `journal 将移动到 archive/ 目录，下次启动以 ${currentWorker.name || '该 Worker'} 的当前权益为基准重新锚定，不再对账历史记录。实盘账户请先人工核对交易所实际持仓与本地记录一致。`,
      okText: '归档',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const result = await archiveWorkerJournal(currentWorker.id);
          message.success(`已归档 ${result.archived.length} 个文件，下次启动 fresh start`);
          await fetchWorkerDetail(currentWorker.id);
        } catch (e) {
          // ApiError extends Error，e.message 已由响应拦截器填好后端错误信息
          const errorMsg = e instanceof Error ? e.message : String(e);
          message.error(`归档失败: ${errorMsg}`);
        }
      },
    });
  }, [currentWorker, fetchWorkerDetail, message, modal]);

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

  // 6 个 tab 顺序：总览 → 持仓 → 成交分组 → 委托 → 参数 → 日志
  // 所有标签使用 i18n；key 兜底保证 key 缺失时显示正确中文
  const tabItems = [
    {
      key: 'overview',
      label: t('overview') || '总览',
      children: (
        <WorkerOverviewTab
          workerId={currentWorker.id}
          active={activeTab === 'overview'}
          onNavigate={handleTabChange}
        />
      ),
    },
    {
      key: 'positions',
      label: t('position') || '持仓',
      children: <WorkerPositionTab workerId={currentWorker.id} active={activeTab === 'positions'} />,
    },
    {
      key: 'tradesGrouped',
      // trades_grouped 尚未入库 i18n 资源，defaultValue 兜底避免直接显示 key
      label: t('trades_grouped', '成交分组'),
      children: <WorkerTradesGroupedTab workerId={currentWorker.id} active={activeTab === 'tradesGrouped'} />,
    },
    {
      key: 'orders',
      label: t('orders') || '委托',
      children: <WorkerOrderTab workerId={currentWorker.id} active={activeTab === 'orders'} />,
    },
    {
      key: 'params',
      label: t('parameters') || '参数',
      children: (
        <WorkerParamsTab
          worker={currentWorker}
          reloadKey={paramsReloadKey}
          onEdit={() => setEditOpen(true)}
        />
      ),
    },
    {
      key: 'logs',
      label: t('logs') || '日志',
      children: <WorkerLogsTab workerId={currentWorker.id} />,
    },
  ];

  // 「最后更新时间」显示文本
  const lastUpdateText = overview?.updatedAt
    ? dayjs(overview.updatedAt).fromNow()
    : dayjs(lastUpdateTime).fromNow();

  return (
    <PageContainer>
      <Spin spinning={loading}>
        {/* 返回按钮 - 独立在页面左上角 */}
        <div style={{ marginBottom: 16 }}>
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/strategy-worker')}>
              {t('back_to_list') || '返回列表'}
            </Button>
            <Button
              icon={<ShareAltOutlined />}
              onClick={() => setShareOpen(true)}
              disabled={!currentWorker}
            >
              {t('share.button') || '分享'}
            </Button>
            <Button
              danger
              icon={<FolderAddOutlined />}
              disabled={!currentWorker || !['stopped', 'error'].includes(String(currentWorker.status ?? ''))}
              onClick={handleArchive}
            >
              归档重锚
            </Button>
          </Space>
        </div>

        {/* 错误提示 */}
        {error && (
          <div style={{ marginBottom: 16 }}>
            <Card>
              <Space>
                <span style={{ color: QUANT_COLORS.negative }}>{error}</span>
                <Button size="small" onClick={clearErrors}>
                  关闭
                </Button>
              </Space>
            </Card>
          </div>
        )}

        {/* 页面头部 */}
        <Card style={{ marginBottom: 16 }}>
          <Row gutter={[16, 16]} align="middle">
            <Col flex="auto">
              <Space size="large" wrap>
                <Space size="middle">
                  <span style={{ fontSize: 20, fontWeight: 600 }}>{currentWorker.name}</span>
                  {currentWorker.strategy_type === 'rl' && <Tag color="purple">RL</Tag>}
                  {currentWorker.strategy_type === 'rule' && <Tag color="green">规则</Tag>}
                  <Tag color={WorkerStatusColor[currentWorker.status]}>
                    {WorkerStatusText[currentWorker.status]}
                  </Tag>
                </Space>

                <Space size="middle">
                  <Tag color="blue">{currentWorker.trading_config?.symbols_config?.symbols?.join(', ') || '-'}</Tag>
                  <Tag>{currentWorker.trading_config?.exchange}</Tag>
                </Space>

                <Space size="small">
                  <ClockCircleOutlined style={{ color: '#999' }} />
                  <span style={{ color: '#666', fontSize: 13 }}>
                    最后更新：{lastUpdateText}
                  </span>
                </Space>
              </Space>
            </Col>

            <Col>
              <Descriptions size="small" column={2}>
                <Descriptions.Item label={t('timeframe') || '周期'}>
                  <Tag color="blue">{currentWorker.trading_config?.timeframe}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('total_profit') || '总收益'}>
                  <span
                    style={{
                      fontWeight: 600,
                      fontSize: 16,
                      color:
                        (currentWorker.total_profit || 0) >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
                    }}
                  >
                    {(currentWorker.total_profit || 0) >= 0 ? '+' : ''}$
                    {Math.abs(currentWorker.total_profit || 0).toFixed(2)}
                  </span>
                </Descriptions.Item>
              </Descriptions>
            </Col>
          </Row>
        </Card>

        {/* 启动/运行失败原因：仅 error 状态且有记录时展示（error_message 来自详情接口） */}
        {currentWorker.status === 'error' && selectedWorker?._state_info?.error_message && (
          <Alert
            type="error"
            showIcon
            message={t('error_reason') || '失败原因'}
            description={selectedWorker._state_info.error_message}
            style={{ marginBottom: 16 }}
          />
        )}

        {/* 标签页内容区 */}
        <Card>
          <Tabs
            activeKey={activeTab}
            onChange={handleTabChange}
            items={tabItems}
            size="large"
          />
        </Card>

        {/* 分享配置 Modal（受控） */}
        <WorkerShareModal
          open={shareOpen}
          workerId={currentWorker.id}
          workerName={currentWorker.name}
          onClose={() => setShareOpen(false)}
        />

        {/* 编辑 Worker Modal（受控）：保存成功后刷新列表并递增参数 tab 重拉信号量 */}
        <WorkerEditModal
          visible={editOpen}
          worker={currentWorker}
          onCancel={() => setEditOpen(false)}
          onSuccess={() => {
            fetchWorkers();
            setParamsReloadKey((k) => k + 1);
          }}
        />
      </Spin>
    </PageContainer>
  );
};

export default WorkerDetail;
