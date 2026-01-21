/**
 * 策略代理页面组件
 * 功能：策略代理功能的主页面
 */
import { useEffect, useState, lazy, Suspense } from 'react';
import { useStrategyStore } from '../store';
import { Card, Button, Table, Row, Col, Typography, Space, Tag, Statistic, Spin } from 'antd';

// 动态导入 ReactECharts
const ReactECharts = lazy(() => import('echarts-for-react'));
import dayjs from 'dayjs';
import { exportStrategyAgentToHtml } from '../utils/exportStrategyAgent';
import '../styles/StrategyAgent.css';

const { Title, Text, Paragraph } = Typography;

const StrategyAgent = () => {
  // 从状态管理中获取数据和操作方法
  const {
    strategies,
    selectedStrategy,
    isLoading,
    loadStrategies,
    loadExecutionStats,
    viewStrategyDetail,
    toggleStrategyStatus,
    pauseStrategy,
    resumeStrategy,
    createNewStrategy,
    refreshData
  } = useStrategyStore();

  // 本地状态
  const [currentStrategy, setCurrentStrategy] = useState<string | null>(null);

  // 组件挂载时加载数据
  useEffect(() => {
    loadStrategies();
    loadExecutionStats();
  }, [loadStrategies, loadExecutionStats]);

  // 处理策略选择
  const handleStrategySelect = (strategyId: string) => {
    setCurrentStrategy(strategyId);
    viewStrategyDetail(strategyId);
  };

  // 处理导出功能
  const handleExport = () => {
    if (!selectedStrategy) return;
    
    // 收集导出数据，只包含当前选中策略
    const exportData = {
      selectedStrategy: selectedStrategy,
      exportTime: new Date().toLocaleString()
    };
    
    // 生成文件名，包含策略名称
    const safeStrategyName = selectedStrategy.name.replace(/[^\w\s]/gi, '').replace(/\s+/g, '-').toLowerCase();
    const filename = `strategy-${safeStrategyName}-report-${new Date().toISOString().slice(0, 10)}.html`;
    
    // 调用导出函数
    exportStrategyAgentToHtml(exportData, filename);
  };

  // 渲染收益率图表
  const renderReturnRateChart = (strategy: any) => {
    const option = {
      title: {
        text: '收益率曲线',
        left: 'center',
        textStyle: {
          color: '#fff',
          fontSize: 14
        }
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const data = params[0];
          return `${data.name}<br/>收益率: ${data.value.toFixed(2)}%`;
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: strategy.returnRateData.map((item: any) => item.timestamp),
        axisLabel: {
          color: '#aaa',
          fontSize: 10
        },
        axisLine: {
          lineStyle: {
            color: '#444'
          }
        }
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          color: '#aaa',
          formatter: '{value}%'
        },
        axisLine: {
          lineStyle: {
            color: '#444'
          }
        },
        splitLine: {
          lineStyle: {
            color: '#333'
          }
        }
      },
      series: [
        {
          name: '收益率',
          type: 'line',
          smooth: true,
          data: strategy.returnRateData.map((item: any) => item.value),
          lineStyle: {
            color: strategy.currentReturn >= 0 ? '#52c41a' : '#ff4d4f',
            width: 2
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                {
                  offset: 0,
                  color: strategy.currentReturn >= 0 ? 'rgba(82, 196, 26, 0.3)' : 'rgba(255, 77, 79, 0.3)'
                },
                {
                  offset: 1,
                  color: strategy.currentReturn >= 0 ? 'rgba(82, 196, 26, 0.1)' : 'rgba(255, 77, 79, 0.1)'
                }
              ]
            }
          },
          itemStyle: {
            color: strategy.currentReturn >= 0 ? '#52c41a' : '#ff4d4f'
          }
        }
      ]
    };

    return (
      <Suspense fallback={<div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Spin size="large" /></div>}>
        <ReactECharts option={option} style={{ height: 300, width: '100%' }} />
      </Suspense>
    );
  };

  // 交易记录表格列定义
  const tradeColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (text: string) => dayjs(text).format('YYYY-MM-DD HH:mm:ss')
    },
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol'
    },
    {
      title: '类型',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => (
        <Tag color={action === 'buy' ? 'green' : 'red'}>
          {action === 'buy' ? '买入' : '卖出'}
        </Tag>
      )
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => `$${price.toFixed(2)}`
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      render: (quantity: number) => quantity.toFixed(4)
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number) => `$${amount.toFixed(2)}`
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'filled' ? 'blue' : status === 'pending' ? 'orange' : 'gray'}>
          {status === 'filled' ? '已成交' : status === 'pending' ? '挂单中' : '已取消'}
        </Tag>
      )
    }
  ];

  return (
    <div className="strategy-agent-container">
      <header className="page-header">
        <Title level={2} className="header-title">策略代理</Title>
        <div className="header-actions">
          <Button type="primary" onClick={createNewStrategy}>新建策略</Button>
          <Button onClick={refreshData}>刷新</Button>
          <Button onClick={handleExport} disabled={!selectedStrategy}>导出报告</Button>
        </div>
      </header>

      <Row gutter={[16, 16]}>
        {/* 左侧策略列表 */}
        <Col xs={24} lg={6}>
          <Card title="策略列表" className="strategy-list-card">
            {isLoading ? (
              <div className="loading-state">加载中...</div>
            ) : (
              <Space orientation="vertical" style={{ width: '100%' }}>
                {strategies.map(strategy => (
                  <Card
                    key={strategy.id}
                    className={`strategy-card ${currentStrategy === strategy.id ? 'selected' : ''}`}
                    onClick={() => handleStrategySelect(strategy.id)}
                    hoverable
                  >
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong>{strategy.name}</Text>
                        <Tag color={
                          strategy.status === 'active' ? 'green' :
                          strategy.status === 'paused' ? 'orange' : 'gray'
                        }>
                          {strategy.statusText}
                        </Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {strategy.description}
                      </Text>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text style={{ fontSize: 12 }}>
                          总收益率: <Text strong style={{ color: strategy.totalReturn >= 0 ? '#52c41a' : '#ff4d4f' }}>
                            {strategy.totalReturn.toFixed(2)}%
                          </Text>
                        </Text>
                        <Text style={{ fontSize: 12 }}>
                          今日收益: <Text strong style={{ color: strategy.currentReturn >= 0 ? '#52c41a' : '#ff4d4f' }}>
                            {strategy.currentReturn.toFixed(2)}%
                          </Text>
                        </Text>
                      </Space>
                      <Space style={{ width: '100%', justifyContent: 'space-between', marginTop: 8 }}>
                        {strategy.status === 'active' && (
                          <>
                            <Button size="small" danger onClick={(e) => { e.stopPropagation(); pauseStrategy(strategy.id); }}>
                              暂停
                            </Button>
                            <Button size="small" onClick={(e) => { e.stopPropagation(); toggleStrategyStatus(strategy.id); }}>
                              停止
                            </Button>
                          </>
                        )}
                        {strategy.status === 'paused' && (
                          <>
                            <Button size="small" type="primary" onClick={(e) => { e.stopPropagation(); resumeStrategy(strategy.id); }}>
                              恢复
                            </Button>
                            <Button size="small" onClick={(e) => { e.stopPropagation(); toggleStrategyStatus(strategy.id); }}>
                              停止
                            </Button>
                          </>
                        )}
                        {strategy.status === 'inactive' && (
                          <Button size="small" type="primary" style={{ width: '100%' }} onClick={(e) => { e.stopPropagation(); toggleStrategyStatus(strategy.id); }}>
                            启动
                          </Button>
                        )}
                      </Space>
                    </Space>
                  </Card>
                ))}
              </Space>
            )}
          </Card>
        </Col>

        {/* 右侧详细信息 */}
        <Col xs={24} lg={18}>
          {selectedStrategy ? (
            <>
              {/* 策略概览 */}
              <Card className="strategy-overview-card">
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={8}>
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      <Title level={4}>{selectedStrategy.name}</Title>
                      <Paragraph>{selectedStrategy.description}</Paragraph>
                      <Space>
                        <Text>状态: </Text>
                        <Tag color={
                          selectedStrategy.status === 'active' ? 'green' :
                          selectedStrategy.status === 'paused' ? 'orange' : 'gray'
                        }>
                          {selectedStrategy.statusText}
                        </Tag>
                      </Space>
                      {selectedStrategy.status === 'active' && (
                        <Space>
                          <Text>启动时间: </Text>
                          <Text>{selectedStrategy.startTime}</Text>
                        </Space>
                      )}
                      <Space>
                        <Text>最后交易: </Text>
                        <Text>{selectedStrategy.lastTradeTime || '暂无交易'}</Text>
                      </Space>
                    </Space>
                  </Col>
                  <Col xs={24} md={16}>
                    {renderReturnRateChart(selectedStrategy)}
                  </Col>
                </Row>
              </Card>

              {/* 策略性能指标 */}
              <Card title="性能指标" className="performance-metrics-card">
                <Row gutter={[16, 16]}>
                  <Col xs={12} md={6}>
                    <Statistic title="胜率" value={selectedStrategy.performance.winRate} suffix="%" />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="盈亏比" value={selectedStrategy.performance.profitLossRatio} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="最大回撤" value={selectedStrategy.performance.maxDrawdown} suffix="%" />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="夏普比率" value={selectedStrategy.performance.sharpeRatio} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="总交易数" value={selectedStrategy.performance.totalTrades} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="盈利交易" value={selectedStrategy.performance.winningTrades} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title="亏损交易" value={selectedStrategy.performance.losingTrades} />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic 
                      title="总收益" 
                      value={selectedStrategy.performance.totalProfit - selectedStrategy.performance.totalLoss} 
                      suffix="$"
                      valueStyle={{ color: (selectedStrategy.performance.totalProfit - selectedStrategy.performance.totalLoss) >= 0 ? '#52c41a' : '#ff4d4f' }}
                    />
                  </Col>
                </Row>
              </Card>

              {/* 交易记录 */}
              <Card title="交易记录" className="trade-records-card">
                <Table 
                  columns={tradeColumns} 
                  dataSource={selectedStrategy.tradeRecords} 
                  rowKey="id"
                  pagination={{ pageSize: 5 }}
                />
              </Card>
            </>
          ) : (
            <Card className="empty-state-card">
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <Text type="secondary">请选择一个策略查看详细信息</Text>
              </div>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
};

export default StrategyAgent;
