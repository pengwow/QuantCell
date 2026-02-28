/**
 * 回测详情页面
 * 功能：显示单个回测任务的详细信息，包括配置、指标、图表和交易记录
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Button,
  Row,
  Col,
  Space,
  Select,
  Spin,
  message,
  Empty,
  Descriptions,
  Divider,
} from 'antd';
import {
  PlayCircleOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { backtestApi } from '../../api';
import { generateBacktestReportHtml } from '../../utils/exportBacktest';
import MetricCard from '../../components/MetricCard';
import TradeTable from '../../components/TradeTable';
import EquityChart from '../../components/EquityChart';
import DrawdownChart from '../../components/DrawdownChart';
import type { BacktestDetailData } from '../../types/backtest';
import PageContainer from '@/components/PageContainer';

const BacktestDetail = () => {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [detailData, setDetailData] = useState<BacktestDetailData | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [symbols, setSymbols] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);

  // 加载回测详情数据
  useEffect(() => {
    if (!backtestId) {
      message.error('回测ID不存在');
      navigate('/backtest');
      return;
    }

    const fetchDetail = async () => {
      try {
        setLoading(true);
        const data = await backtestApi.getBacktestDetail(backtestId);
        setDetailData(data);

        // 设置交易标的列表
        if (data.backtest_config?.symbols) {
          const symbolList = Array.isArray(data.backtest_config.symbols)
            ? data.backtest_config.symbols
            : [data.backtest_config.symbols];
          setSymbols(symbolList);
          if (symbolList.length > 0) {
            setSelectedSymbol(symbolList[0]);
          }
        }
      } catch (error) {
        message.error('加载回测详情失败');
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [backtestId, navigate]);

  // 获取指标值
  const getMetricValue = (key: string): number | string => {
    const metric = detailData?.metrics.find((m) => m.key === key);
    return metric?.value ?? '-';
  };

  // 格式化百分比
  const formatPercent = (value: number | string): string => {
    if (typeof value === 'number') {
      return `${(value * 100).toFixed(2)}%`;
    }
    return String(value);
  };

  // 格式化数字
  const formatNumber = (value: number | string, decimals = 2): string => {
    if (typeof value === 'number') {
      return value.toFixed(decimals);
    }
    return String(value);
  };

  // 导出报告
  const handleExport = async () => {
    if (!detailData) return;

    try {
      setExporting(true);
      const htmlContent = generateBacktestReportHtml(detailData);

      // 创建下载链接
      const blob = new Blob([htmlContent], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `回测报告_${detailData.strategy_name}_${new Date().toISOString().slice(0, 10)}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      message.success('报告导出成功');
    } catch (error) {
      message.error('导出报告失败');
      console.error(error);
    } finally {
      setExporting(false);
    }
  };

  // 跳转到回放页面
  const handleReplay = () => {
    if (backtestId) {
      navigate(`/backtest/replay/${backtestId}`);
    }
  };

  // 渲染加载状态
  if (loading) {
    return (
      <PageContainer title={detailData?.strategy_name || '回测详情'}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '100px 0' }}>
          <Spin size="large" tip="加载中..." />
        </div>
      </PageContainer>
    );
  }

  // 渲染空状态
  if (!detailData) {
    return (
      <PageContainer title="回测详情">
        <div style={{ padding: '100px 0' }}>
          <Empty description="未找到回测数据" />
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer title={detailData.strategy_name}>
      <div className="space-y-6">
        {/* 页面操作按钮 */}
        <div className="flex justify-end">
          <Space>
            {symbols.length > 1 && (
              <Select
                value={selectedSymbol}
                onChange={setSelectedSymbol}
                style={{ width: 150 }}
                placeholder="选择交易标的"
              >
                {symbols.map((symbol) => (
                  <Select.Option key={symbol} value={symbol}>
                    {symbol}
                  </Select.Option>
                ))}
              </Select>
            )}
            <Button
              icon={<PlayCircleOutlined />}
              onClick={handleReplay}
              type="primary"
            >
              回放
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExport}
              loading={exporting}
            >
              导出报告
            </Button>
          </Space>
        </div>

      {/* 配置信息 */}
      <Card title="配置信息">
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }}>
          <Descriptions.Item label="策略名称">
            {detailData.strategy_name}
          </Descriptions.Item>
          <Descriptions.Item label="交易标的">
            {Array.isArray(detailData.backtest_config.symbols)
              ? detailData.backtest_config.symbols.join(', ')
              : detailData.backtest_config.symbols}
          </Descriptions.Item>
          <Descriptions.Item label="时间范围">
            {detailData.backtest_config.start_time} ~ {detailData.backtest_config.end_time}
          </Descriptions.Item>
          <Descriptions.Item label="周期">
            {detailData.backtest_config.interval}
          </Descriptions.Item>
          <Descriptions.Item label="初始资金">
            {detailData.backtest_config.initial_cash}
          </Descriptions.Item>
          <Descriptions.Item label="手续费率">
            {detailData.backtest_config.commission}
          </Descriptions.Item>
        </Descriptions>
        {detailData.strategy_config?.params && (
          <>
            <Divider style={{ margin: '16px 0' }} />
            <Descriptions bordered column={1}>
              <Descriptions.Item label="策略参数">
                <pre style={{ margin: 0, background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                  {JSON.stringify(detailData.strategy_config.params, null, 2)}
                </pre>
              </Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Card>

      {/* 回测概览指标 */}
      <Card title="回测概览">
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={8} md={6} lg={4}>
            <MetricCard
              label="总收益率"
              value={formatPercent(getMetricValue('Return [%]'))}
              type={Number(getMetricValue('Return [%]')) >= 0 ? 'positive' : 'negative'}
            />
          </Col>
          <Col xs={12} sm={8} md={6} lg={4}>
            <MetricCard
              label="年化收益率"
              value={formatPercent(getMetricValue('Return (Ann.) [%]'))}
              type={Number(getMetricValue('Return (Ann.) [%]')) >= 0 ? 'positive' : 'negative'}
            />
          </Col>
          <Col xs={12} sm={8} md={6} lg={4}>
            <MetricCard
              label="最大回撤"
              value={formatPercent(getMetricValue('Max. Drawdown [%]'))}
              type="negative"
            />
          </Col>
          <Col xs={12} sm={8} md={6} lg={4}>
            <MetricCard
              label="夏普比率"
              value={formatNumber(getMetricValue('Sharpe Ratio'))}
            />
          </Col>
          <Col xs={12} sm={8} md={6} lg={4}>
            <MetricCard
              label="胜率"
              value={formatPercent(getMetricValue('Win Rate [%]'))}
            />
          </Col>
          <Col xs={12} sm={8} md={6} lg={4}>
            <MetricCard
              label="交易次数"
              value={formatNumber(getMetricValue('# Trades'), 0)}
            />
          </Col>
        </Row>
      </Card>

      {/* 绩效分析图表 */}
      <Card title="绩效分析">
        {detailData.equity_curve && detailData.equity_curve.length > 0 ? (
          <EquityChart data={detailData.equity_curve} />
        ) : (
          <Empty description="暂无权益曲线数据" />
        )}
      </Card>

      {/* 风险分析和交易详情 */}
      <Row gutter={24}>
        <Col xs={24} lg={12}>
          <Card title="风险分析">
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <MetricCard
                  label="波动率"
                  value={formatPercent(getMetricValue('Volatility (Ann.) [%]'))}
                />
              </Col>
              <Col span={12}>
                <MetricCard
                  label="索提诺比率"
                  value={formatNumber(getMetricValue('Sortino Ratio'))}
                />
              </Col>
              <Col span={12}>
                <MetricCard
                  label="卡尔马比率"
                  value={formatNumber(getMetricValue('Calmar Ratio'))}
                />
              </Col>
              <Col span={12}>
                <MetricCard
                  label="信息比率"
                  value={formatNumber(getMetricValue('Information Ratio'))}
                />
              </Col>
            </Row>
            <DrawdownChart value={Number(getMetricValue('Max. Drawdown [%]'))} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="交易详情">
            {detailData.trades && detailData.trades.length > 0 ? (
              <TradeTable data={detailData.trades} />
            ) : (
              <Empty description="暂无交易记录" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
    </PageContainer>
  );
};

export default BacktestDetail;
