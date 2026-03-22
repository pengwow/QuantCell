/**
 * 回测详情页面
 * 功能：显示单个回测任务的详细信息，包括配置、指标、图表和交易记录
 * 适配后端返回格式：{ id, strategy_name, backtest_config, metrics, trades, equity_curve, ... }
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Button,
  Row,
  Col,
  Select,
  Spin,
  message,
  Empty,
  Descriptions,
  Space,
  DatePicker,
} from 'antd';
import {
  PlayCircleOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { backtestApi } from '../../api';
import MetricCard from '../../components/MetricCard';
import TradeTable from '../../components/TradeTable';
import EquityChart from '../../components/EquityChart';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/router';
import { useTranslation } from 'react-i18next';

// 后端返回的数据类型定义
interface BacktestMetrics {
  name: string;
  key: string;
  value: number;
  description: string;
  type: string;
}

interface BacktestTrade {
  trade_id: string;
  side?: string;
  Side?: string;
  direction?: string;
  Direction?: string;
  quantity: number;
  price: number;
  volume: number;
  commission: string;
  timestamp: number;
  formatted_time: string;
  status?: string;
  Status?: string;
  symbol?: string;
  Symbol?: string;
  instrument_id?: string;
  instrument?: string;
}

interface EquityCurvePoint {
  timestamp: number;
  formatted_time: string;
  equity: number;
  balance: number;
}

// 后端实际返回的数据结构
interface BacktestResponse {
  id: string;
  strategy_name: string;
  backtest_config: {
    symbols: string[];
    interval: string;
    start_time: string;
    end_time: string;
    initial_cash?: number;
    [key: string]: any;
  };
  strategy_config: Record<string, any>;
  metrics: BacktestMetrics[];
  trades: BacktestTrade[];
  equity_curve: EquityCurvePoint[];
  status: string;
  created_at: string;
}

const BacktestDetail = () => {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [backtestData, setBacktestData] = useState<BacktestResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('all');
  const [symbols, setSymbols] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  // 高级筛选状态
  const [filterSide, setFilterSide] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterDateRange, setFilterDateRange] = useState<[string, string] | null>(null);
  const [showAdvancedFilter, setShowAdvancedFilter] = useState(false);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('backtest_detail') || '回测详情');
  }, [t]);

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

        // apiRequest 拦截器已经处理了 ApiResponse，直接返回 data 字段
        if (response && response.id) {
          setBacktestData(response as BacktestResponse);

          // 从 backtest_config 中获取交易标的列表
          const symbolKeys = response.backtest_config?.symbols || [];
          setSymbols(symbolKeys);
          // 默认选中"全部"
          setSelectedSymbol('all');
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

  // 从指标数组中获取指定key的指标值
  const getMetricValue = (key: string): number => {
    if (!backtestData?.metrics) return 0;
    const metric = backtestData.metrics.find(m => m.key === key);
    return metric?.value || 0;
  };

  // 获取交易列表，根据高级筛选条件进行筛选
  const getTrades = (): BacktestTrade[] => {
    let trades = backtestData?.trades || [];

    // 根据货币对筛选
    if (selectedSymbol && selectedSymbol !== 'all') {
      trades = trades.filter((trade: BacktestTrade) => {
        const tradeSymbol = trade.Symbol || trade.symbol || trade.instrument_id || trade.instrument || '';
        // 处理格式不匹配问题：前端显示 "ETH/USDT"，后端返回 "ETHUSDT.BINANCE"
        // 将前端的 "ETH/USDT" 转换为 "ETHUSDT" 进行匹配
        const normalizedSelected = selectedSymbol.replace('/', '').toUpperCase();
        const normalizedTrade = tradeSymbol.toUpperCase();
        // 检查后缀匹配（如 ETHUSDT 匹配 ETHUSDT.BINANCE）
        return normalizedTrade.includes(normalizedSelected) || normalizedSelected.includes(normalizedTrade.replace(/\.BINANCE$/, ''));
      });
    }

    // 根据方向筛选
    if (filterSide && filterSide !== 'all') {
      trades = trades.filter((trade: BacktestTrade) => {
        const side = trade.side || trade.Side || trade.direction || trade.Direction || '';
        return side.toLowerCase() === filterSide.toLowerCase();
      });
    }

    // 根据状态筛选
    if (filterStatus && filterStatus !== 'all') {
      trades = trades.filter((trade: BacktestTrade) => {
        const status = trade.status || trade.Status || '';
        return status.toLowerCase() === filterStatus.toLowerCase();
      });
    }

    // 根据日期范围筛选
    if (filterDateRange && filterDateRange[0] && filterDateRange[1]) {
      const startDate = new Date(filterDateRange[0]).getTime();
      const endDate = new Date(filterDateRange[1]).getTime();
      trades = trades.filter((trade: BacktestTrade) => {
        // 后端返回的 timestamp 是秒级（10位），需要转换为毫秒级（13位）
        let tradeTime = trade.timestamp;
        if (tradeTime && tradeTime.toString().length <= 10) {
          tradeTime = tradeTime * 1000; // 秒转毫秒
        }
        if (!tradeTime && trade.formatted_time) {
          tradeTime = new Date(trade.formatted_time).getTime();
        }
        return tradeTime >= startDate && tradeTime <= endDate;
      });
    }

    return trades;
  };

  // 重置筛选条件
  const resetFilters = () => {
    setSelectedSymbol('all');
    setFilterSide('all');
    setFilterStatus('all');
    setFilterDateRange(null);
  };

  // 获取权益曲线数据，转换为 EquityChart 组件期望的格式
  const getEquityCurve = (): Array<{ datetime: string; Equity: number }> => {
    return (backtestData?.equity_curve || []).map(point => ({
      datetime: point.formatted_time || new Date(point.timestamp * 1000).toISOString(),
      Equity: point.equity,
    }));
  };

  // 格式化百分比 - 后端返回的已经是百分比格式，直接添加%符号
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

  const strategyName = backtestData.strategy_name || 'Unknown';
  const backtestConfig = backtestData.backtest_config || {};

  return (
    <PageContainer title={`${strategyName} - 回测详情`}>
      <div className="space-y-6">
        {/* 页面操作按钮 */}
        <div className="flex flex-wrap justify-start sm:justify-end gap-2">
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
        </div>

        {/* 配置信息 */}
        <Card title="配置信息" className="mb-6">
          <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }}>
            <Descriptions.Item label="策略名称">
              {strategyName}
            </Descriptions.Item>
            <Descriptions.Item label="交易标的">
              {selectedSymbol || symbols.join(', ')}
            </Descriptions.Item>
            <Descriptions.Item label="时间周期">
              {backtestConfig.interval || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="回测时间">
              {backtestConfig.start_time && backtestConfig.end_time
                ? `${backtestConfig.start_time} 至 ${backtestConfig.end_time}`
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="初始资金">
              {formatNumber(backtestConfig.initial_cash || 0)}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {backtestData.status}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* 回测概览指标 */}
        <Card title="回测概览" className="mb-6">
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
                label="年化收益率"
                value={formatPercent(getMetricValue('cagr'))}
                type={getMetricValue('cagr') >= 0 ? 'positive' : 'negative'}
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
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="盈利交易"
                value={formatNumber(getMetricValue('winning_trades'), 0)}
                type="positive"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="亏损交易"
                value={formatNumber(getMetricValue('losing_trades'), 0)}
                type="negative"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="总盈亏"
                value={formatNumber(getMetricValue('total_pnl'))}
                type={getMetricValue('total_pnl') >= 0 ? 'positive' : 'negative'}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="初始权益"
                value={formatNumber(getMetricValue('initial_equity'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="最终权益"
                value={formatNumber(getMetricValue('final_equity'))}
                type={getMetricValue('final_equity') >= getMetricValue('initial_equity') ? 'positive' : 'negative'}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="权益峰值"
                value={formatNumber(getMetricValue('equity_peak'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="索提诺比率"
                value={formatNumber(getMetricValue('sortino_ratio'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="卡尔马比率"
                value={formatNumber(getMetricValue('calmar_ratio'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="平均回撤"
                value={formatPercent(getMetricValue('avg_drawdown'))}
                type="negative"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="年化波动率"
                value={formatPercent(getMetricValue('volatility'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="期望收益"
                value={formatPercent(getMetricValue('expectancy'))}
                type={getMetricValue('expectancy') >= 0 ? 'positive' : 'negative'}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="平均交易"
                value={formatPercent(getMetricValue('avg_trade'))}
                type={getMetricValue('avg_trade') >= 0 ? 'positive' : 'negative'}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="最佳交易"
                value={formatPercent(getMetricValue('best_trade'))}
                type="positive"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="最差交易"
                value={formatPercent(getMetricValue('worst_trade'))}
                type="negative"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="总手续费"
                value={formatNumber(getMetricValue('total_commission'))}
                type="negative"
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="阿尔法"
                value={formatPercent(getMetricValue('alpha'))}
                type={getMetricValue('alpha') >= 0 ? 'positive' : 'negative'}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="贝塔"
                value={formatNumber(getMetricValue('beta'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="SQN"
                value={formatNumber(getMetricValue('sqn'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="凯利准则"
                value={formatNumber(getMetricValue('kelly_criterion'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="暴露时间"
                value={formatPercent(getMetricValue('exposure_time'))}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="回测天数"
                value={formatNumber(getMetricValue('duration_days'), 0)}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="平均持仓时间"
                value={`${formatNumber(getMetricValue('avg_trade_duration_hours'))}h`}
              />
            </Col>
            <Col xs={12} sm={8} md={6} lg={4}>
              <MetricCard
                label="最长持仓时间"
                value={`${formatNumber(getMetricValue('max_trade_duration_hours'))}h`}
              />
            </Col>
          </Row>
        </Card>

        {/* 绩效分析图表 */}
        <Card title="权益曲线" className="mb-6">
          {getEquityCurve().length > 0 ? (
            <EquityChart data={getEquityCurve()} />
          ) : (
            <Empty description="暂无权益曲线数据" />
          )}
        </Card>

        {/* 交易详情 */}
        <Card
          title="交易详情"
          className="mb-6"
          extra={
            <Space>
              <Button
                type={showAdvancedFilter ? 'primary' : 'default'}
                onClick={() => setShowAdvancedFilter(!showAdvancedFilter)}
              >
                筛选
              </Button>
            </Space>
          }
        >
          {/* 高级筛选区域 */}
          {showAdvancedFilter && (
            <div style={{ marginBottom: 16, padding: 16, backgroundColor: '#f5f5f5', borderRadius: 8 }}>
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>交易标的</div>
                  <Select
                    value={selectedSymbol}
                    onChange={setSelectedSymbol}
                    style={{ width: '100%' }}
                    placeholder="选择交易标的"
                  >
                    <Select.Option value="all">全部</Select.Option>
                    {symbols.map((symbol) => (
                      <Select.Option key={symbol} value={symbol}>
                        {symbol}
                      </Select.Option>
                    ))}
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>交易方向</div>
                  <Select
                    value={filterSide}
                    onChange={setFilterSide}
                    style={{ width: '100%' }}
                    placeholder="选择方向"
                  >
                    <Select.Option value="all">全部</Select.Option>
                    <Select.Option value="buy">买入</Select.Option>
                    <Select.Option value="sell">卖出</Select.Option>
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>交易状态</div>
                  <Select
                    value={filterStatus}
                    onChange={setFilterStatus}
                    style={{ width: '100%' }}
                    placeholder="选择状态"
                  >
                    <Select.Option value="all">全部</Select.Option>
                    <Select.Option value="filled">已成交</Select.Option>
                    <Select.Option value="partial">部分成交</Select.Option>
                    <Select.Option value="canceled">已取消</Select.Option>
                  </Select>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>日期范围</div>
                  <DatePicker.RangePicker
                    style={{ width: '100%' }}
                    onChange={(dates) => {
                      if (dates && dates[0] && dates[1]) {
                        setFilterDateRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]);
                      } else {
                        setFilterDateRange(null);
                      }
                    }}
                  />
                </Col>
              </Row>
              <Row style={{ marginTop: 16 }}>
                <Col span={24} style={{ textAlign: 'right' }}>
                  <Button onClick={resetFilters}>重置</Button>
                </Col>
              </Row>
            </div>
          )}

          {/* 筛选结果统计 */}
          <div style={{ marginBottom: 16 }}>
            <span style={{ color: '#8c8c8c' }}>
              共 {getTrades().length} 条记录
              {selectedSymbol !== 'all' && ` | 标的: ${selectedSymbol}`}
              {filterSide !== 'all' && ` | 方向: ${filterSide === 'buy' ? '买入' : '卖出'}`}
              {filterStatus !== 'all' && ` | 状态: ${filterStatus}`}
              {filterDateRange && ` | 日期: ${filterDateRange[0]} 至 ${filterDateRange[1]}`}
            </span>
          </div>

          {getTrades().length > 0 ? (
            <TradeTable data={getTrades()} />
          ) : (
            <Empty description="暂无交易记录" />
          )}
        </Card>
      </div>
    </PageContainer>
  );
};

export default BacktestDetail;
