/**
 * Worker 详情页
 *
 * 5 个 tab 布局（顺序：总览、持仓、委托、参数、日志）
 * - URL hash 同步：切换 tab 时更新 hash，刷新页面时根据 hash 恢复
 * - 旧 hash (#performance/#stats) 兼容：自动重定向到 #overview 并 toast 提示
 * - 页面头部 Card 增加「最后更新时间」字段，每 60s 刷新
 * - 所有 tab 标签使用 i18n 翻译
 */

import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { App, Card, Button, Tabs, Spin, Row, Col, Tag, Space, Descriptions } from 'antd';
import { ArrowLeftOutlined, ClockCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import relativeTime from 'dayjs/plugin/relativeTime';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerStatusColor, WorkerStatusText } from '../../types/worker';
import WorkerParamsTab from '../../components/worker/WorkerParamsTab';
import WorkerOverviewTab from '../../components/worker/WorkerOverviewTab';
import WorkerPositionTab from '../../components/worker/WorkerPositionTab';
import WorkerOrderTab from '../../components/worker/WorkerOrderTab';
import WorkerLogsTab from '../../components/worker/WorkerLogsTab';

dayjs.extend(relativeTime);

// Tab key 类型
type TabKey = 'params' | 'overview' | 'positions' | 'orders' | 'logs';

// 合法 tab key
const VALID_TABS: TabKey[] = ['params', 'overview', 'positions', 'orders', 'logs'];

// 旧 hash -> 新 hash 映射
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
  const { message } = App.useApp();

  const [activeTab, setActiveTab] = useState<TabKey>(DEFAULT_TAB);
  // 初始时间戳使用懒初始化，避免每次渲染重新计算
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(() => Date.now());

  const {
    workers,
    selectedWorker,
    overview,
    loading,
    error,
    fetchWorkers,
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

  if (loading || !currentWorker) {
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

  // 5 个 tab 顺序：总览 → 持仓 → 委托 → 参数 → 日志
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
      key: 'orders',
      label: t('orders') || '委托',
      children: <WorkerOrderTab workerId={currentWorker.id} active={activeTab === 'orders'} />,
    },
    {
      key: 'params',
      label: t('parameters') || '参数',
      children: <WorkerParamsTab worker={currentWorker} />,
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
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/strategy-worker')}>
            {t('back_to_list') || '返回列表'}
          </Button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div style={{ marginBottom: 16 }}>
            <Card>
              <Space>
                <span style={{ color: '#ff4d4f' }}>{error}</span>
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
                  <Tag color={WorkerStatusColor[currentWorker.status]}>
                    {WorkerStatusText[currentWorker.status]}
                  </Tag>
                </Space>

                <Space size="middle">
                  <Tag color="blue">{currentWorker.symbols?.join(', ') || '-'}</Tag>
                  <Tag>{currentWorker.exchange}</Tag>
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
                  <Tag color="blue">{currentWorker.timeframe}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('total_profit') || '总收益'}>
                  <span
                    style={{
                      fontWeight: 600,
                      fontSize: 16,
                      color:
                        (currentWorker.total_profit || 0) >= 0 ? '#52c41a' : '#ff4d4f',
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

        {/* 标签页内容区 */}
        <Card>
          <Tabs
            activeKey={activeTab}
            onChange={handleTabChange}
            items={tabItems}
            size="large"
          />
        </Card>
      </Spin>
    </PageContainer>
  );
};

export default WorkerDetail;
