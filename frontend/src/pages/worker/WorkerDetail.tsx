import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Button,
  Tabs,
  Spin,
  Row,
  Col,
  Tag,
  Space,
  Descriptions,
  Empty,
  Alert,
} from 'antd';
import {
  ArrowLeftOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/router';
import { useWorkerStore } from '../../store/workerStore';
import { WorkerStatusColor, WorkerStatusText } from '../../types/worker';
import WorkerParamsTab from '../../components/worker/WorkerParamsTab';
import WorkerPositionTab from '../../components/worker/WorkerPositionTab';
import WorkerTradesTab from '../../components/worker/WorkerTradesTab';
import WorkerPerformanceTab from '../../components/worker/WorkerPerformanceTab';
import WorkerLogsTab from '../../components/worker/WorkerLogsTab';

const WorkerDetail = () => {
  const { t } = useTranslation();
  const { workerId } = useParams<{ workerId: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState('params');

  const {
    workers,
    selectedWorker,
    performance,
    trades,
    returnRateData,
    loading,
    loadingPerformance,
    loadingTrades,
    error,
    fetchWorkers,
    setSelectedWorker,
    fetchPerformance,
    fetchTrades,
    fetchReturnRateData,
    clearErrors,
  } = useWorkerStore();

  useEffect(() => {
    setPageTitle(t('worker_detail') || '策略详情');
  }, [t]);

  useEffect(() => {
    if (workerId) {
      const id = parseInt(workerId);
      // 获取所有workers以找到当前选中的worker
      fetchWorkers().then(() => {
        // 获取详情数据
        fetchPerformance(id);
        fetchTrades(id);
        fetchReturnRateData(id);
      });
    }
  }, [workerId, fetchWorkers, fetchPerformance, fetchTrades, fetchReturnRateData]);

  // 找到当前查看的worker（优先从 workers 数组中查找）
  const currentWorker = workers.find(w => w.id === parseInt(workerId || '0')) || null;

  // 如果找到了但还没设置到 selectedWorker，则设置
  useEffect(() => {
    if (currentWorker && (!selectedWorker || selectedWorker.id !== currentWorker.id)) {
      setSelectedWorker(currentWorker);
    }
  }, [currentWorker, selectedWorker, setSelectedWorker]);

  if (loading || !currentWorker) {
    return (
      <PageContainer>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 48 }} spin />} description={t('loading')} />
        </div>
      </PageContainer>
    );
  }

  const tabItems = [
    {
      key: 'params',
      label: t('parameters') || '参数',
      children: <WorkerParamsTab worker={currentWorker} />,
    },
    {
      key: 'position',
      label: t('position') || '持仓',
      children: <WorkerPositionTab workerId={currentWorker.id} />,
    },
    {
      key: 'trades',
      label: t('trades') || '成交',
      children: <WorkerTradesTab workerId={currentWorker.id} />,
    },
    {
      key: 'performance',
      label: t('performance') || '绩效',
      children: <WorkerPerformanceTab />,
    },
    {
      key: 'logs',
      label: t('logs') || '日志',
      children: <WorkerLogsTab workerId={currentWorker.id} />,
    },
  ];

  return (
    <PageContainer>
      <Spin spinning={loading}>
        {/* 返回按钮 - 独立在页面左上角 */}
        <div style={{ marginBottom: 16 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/strategy-worker')}
          >
            {t('back_to_list') || '返回列表'}
          </Button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div style={{ marginBottom: 16 }}>
            <Alert
              message={error}
              type="error"
              showIcon
              closable
              onClose={clearErrors}
            />
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
              </Space>
            </Col>

            <Col>
              <Space>
                <Descriptions size="small" column={2}>
                  <Descriptions.Item label={t('timeframe') || '周期'}>
                    <Tag color="blue">{currentWorker.timeframe}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('total_profit') || '总收益'}>
                    <span style={{
                      fontWeight: 600,
                      fontSize: 16,
                      color: (currentWorker.total_profit || 0) >= 0 ? '#52c41a' : '#ff4d4f'
                    }}>
                      {(currentWorker.total_profit || 0) >= 0 ? '+' : ''}
                      ${Math.abs(currentWorker.total_profit || 0).toFixed(2)}
                    </span>
                  </Descriptions.Item>
                </Descriptions>
              </Space>
            </Col>
          </Row>
        </Card>

        {/* 标签页内容区 */}
        <Card>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            size="large"
          />
        </Card>
      </Spin>
    </PageContainer>
  );
};

export default WorkerDetail;
