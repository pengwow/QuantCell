/**
 * 回测详情页面
 * 功能：显示单个回测任务的详细信息，包括配置、指标、图表和交易记录
 * 适配后端返回格式：{ status, message, symbols: {...}, portfolio: {...}, account: {...}, _meta: {...} }
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
import MetricCard from '../../components/MetricCard';
import TradeTable from '../../components/TradeTable';
import EquityChart from '../../components/EquityChart';
import DrawdownChart from '../../components/DrawdownChart';
import PageContainer from '@/components/PageContainer';

// 后端返回的数据类型定义
interface BacktestMetrics {
  total_return: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  sharpe_ratio: number;
  max_drawdown: number;
}

interface BacktestTrade {
  trade_id: string;
  side: string;
  direction: string;
  quantity: number;
  price: number;
  volume: number;
  commission: string;
  timestamp: number;
  formatted_time: string;
  status: string;
}

interface SymbolData {
  symbol: string;
  timeframe: string;
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
}

interface BacktestResponse {
  status: string;
  message: string;
  symbols: Record<string, SymbolData>;
  portfolio?: {
    metrics: BacktestMetrics;
    equity_curve: Array<{ timestamp: number; equity: number }>;
  };
  account?: {
    initial_balance: number;
    final_balance: number;
    balance: number;
  };
  _meta?: {
    strategy: string;
    formatted_time: string;
  };
}

const BacktestDetail = () => {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [backtestData, setBacktestData] = useState<BacktestResponse | null>(null);
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
        const response = await backtestApi.getBacktestDetail(backtestId);
        
        if (response && response.status === 'success') {
          setBacktestData(response as BacktestResponse);
          
          // 设置交易标的列表
          const symbolKeys = Object.keys(response.symbols || {});
          setSymbols(symbolKeys);
          if (symbolKeys.length > 0) {
            setSelectedSymbol(symbolKeys[0]);
          }
        } else {
          message.error('获取回测数据失败');
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

  // 获取当前选中的交易标的数据
  const getCurrentSymbolData = (): SymbolData | null => {
    if (!backtestData?.symbols || !selectedSymbol) return null;
    return backtestData.symbols[selectedSymbol] || null;
  };

  // 获取指标值（优先从当前symbol获取，否则从portfolio获取）
  const getMetricValue = (key: keyof BacktestMetrics): number => {
    const symbolData = getCurrentSymbolData();
    const metrics = symbolData?.metrics || backtestData?.portfolio?.metrics;
    if (!metrics) return 0;
    return metrics[key] || 0;
  };

  // 获取交易列表
  const getTrades = (): BacktestTrade[] => {
    const symbolData = getCurrentSymbolData();
    return symbolData?.trades || [];
  };

  // 获取权益曲线数据
  const getEquityCurve = (): Array<{ timestamp: number; equity: number }> => {
    return backtestData?.portfolio?.equity_curve || [];
  };

  // 格式化百分比
  const formatPercent = (value: number): string => {
    if (typeof value === 'number') {
      return `${value.toFixed(2)}%`;
    }
    return String(value);
  };

  // 格式化数字
  const formatNumber = (value: number, decimals = 2): string => {
    if (typeof value === 'number') {
      return value.toFixed(decimals);
    }
    return String(value);
  };

  // 导出报告
  const handleExport = async () => {
    if (!backtestData) return;

    try {
      setExporting(true);
      // 简单的导出实现，可以后续完善
      const dataStr = JSON.stringify(backtestData, null, 2);
      const blob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `回测结果_${backtestId}_${new Date().toISOString().slice(0, 10)}.json`;
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
      <PageContainer title="回测详情">
        <div style={{ display: 'flex', justifyContent: 'center', padding: '100px 0' }}>
          <Spin size="large" description="加载中..." />
        </div>
      </PageContainer>
    );
  }

  // 渲染空状态
  if (!backtestData) {
    return (
      <PageContainer title="回测详情">
        <div style={{ padding: '100px 0' }}>
          <Empty description="未找到回测数据" />
        </div>
      </PageContainer>
    );
  }

  const currentSymbolData = getCurrentSymbolData();
  const strategyName = backtestData._meta?.strategy || 'Unknown';

  return (
    <PageContainer title={`${strategyName} - 回测详情`}>
      <div className="space-y-6">
        {/* 页面操作按钮 */}
        <div className="flex justify-end">
          <Space>
            {symbols.length > 0 && (
              <Select
                value={selectedSymbol}
                onChange={setSelectedSymbol}
                style={{ width: 200 }}
                placeholder="选择交易标的"
              >
                {symbols.map((symbol) => (
                  <Select.Option key={symbol} value={symbol}>
                    {backtestData.symbols[symbol]?.symbol || symbol} ({backtestData.symbols[symbol]?.timeframe || ''})
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
              {strategyName}
            </Descriptions.Item>
            <Descriptions.Item label="交易标的">
              {currentSymbolData?.symbol || selectedSymbol}
            </Descriptions.Item>
            <Descriptions.Item label="时间周期">
              {currentSymbolData?.timeframe || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="回测时间">
              {backtestData._meta?.formatted_time || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="初始资金">
              {formatNumber(backtestData.account?.initial_balance || 0)}
            </Descriptions.Item>
            <Descriptions.Item label="最终资金">
              {formatNumber(backtestData.account?.final_balance || 0)}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* 回测概览指标 */}
        <Card title="回测概览">
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="总收益率"
                value={formatPercent(getMetricValue('total_return'))}
                type={getMetricValue('total_return') >= 0 ? 'positive' : 'negative'}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="夏普比率"
                value={formatNumber(getMetricValue('sharpe_ratio'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="最大回撤"
                value={formatPercent(getMetricValue('max_drawdown'))}
                type="negative"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="胜率"
                value={formatPercent(getMetricValue('win_rate'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="盈亏比"
                value={formatNumber(getMetricValue('profit_factor'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="交易次数"
                value={formatNumber(getMetricValue('total_trades'), 0)}
              />
            </Col>
          </Row>
        </Card>

        {/* 绩效分析图表 */}
        <Card title="权益曲线">
          {getEquityCurve().length > 0 ? (
            <EquityChart data={getEquityCurve()} />
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
                    label="盈利交易"
                    value={formatNumber(getMetricValue('winning_trades'), 0)}
                    type="positive"
                  />
                </Col>
                <Col span={12}>
                  <MetricCard
                    label="亏损交易"
                    value={formatNumber(getMetricValue('losing_trades'), 0)}
                    type="negative"
                  />
                </Col>
                <Col span={12}>
                  <MetricCard
                    label="总盈亏"
                    value={formatNumber(getMetricValue('total_pnl'))}
                    type={getMetricValue('total_pnl') >= 0 ? 'positive' : 'negative'}
                  />
                </Col>
                <Col span={12}>
                  <MetricCard
                    label="当前标的回撤"
                    value={formatPercent(getMetricValue('max_drawdown'))}
                    type="negative"
                  />
                </Col>
              </Row>
              <DrawdownChart value={getMetricValue('max_drawdown')} />
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="交易详情">
              {getTrades().length > 0 ? (
                <TradeTable data={getTrades()} />
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
