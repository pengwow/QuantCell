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
  Modal,
  Tag,
  Alert,
  Flex,
} from 'antd';
import {
  PlayCircleOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { backtestApi } from '../../api';
import MetricCard from '../../components/MetricCard';
import { formatMetricValue, visibleMetricCards } from './metricCards';
import TradeTable, { type Trade } from '../../components/TradeTable';
import EquityChart from '../../components/EquityChart';
import EChart from '@/components/EChart';
import { useQuantColors } from '@/utils/colors';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'ahooks';

// 后端返回的数据类型定义
interface BacktestMetrics {
  name: string;
  key: string;
  value: number;
  description: string;
  type: string;
}

interface EquityCurvePoint {
  timestamp: number;
  formatted_time: string;
  equity: number;
  balance: number;
  margin?: number;
}

// 因子分析载荷（后端结果 JSON factors 字段）
interface FactorTimeSeries {
  timestamps: number[];
  formatted_times: string[];
  // 每因子一列值（NaN 用 null 表示）；列式紧凑编码，前端按因子名取列
  [factorName: string]: number[] | string[] | null;
}

interface FactorAttribution {
  stats: { mean: number; std: number; min: number; max: number; median: number; q25: number; q75: number };
  ic: number | null;
  rank_ic: number | null;
  icir: number | null;
  group_returns: Record<string, number>;
  long_short_return: number | null;
}

interface BacktestFactors {
  names: string[];
  thresholds: Record<string, { buy?: number; sell?: number }>;
  time_series: FactorTimeSeries;
  trade_factors: Array<Record<string, number | string | null>>;
  attribution: Record<string, FactorAttribution>;
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
    capital_mode?: string;
    [key: string]: unknown;
  };
  strategy_config: Record<string, unknown>;
  metrics: BacktestMetrics[];
  trades: Trade[];
  equity_curve: EquityCurvePoint[];
  factors?: BacktestFactors;
  // 多品种结果：实际有数据的品种列表、当前返回品种
  symbols?: string[];
  selected_symbol?: string | null;
  is_multi_symbol?: boolean;
  // 因无数据被跳过的品种：{品种: 原因}，据此提示用户「选了 N 个标的只剩 M 个」的原因
  skipped_symbols?: Record<string, string>;
  status: string;
  created_at: string;
}

const BacktestDetail = () => {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { theme } = useTheme({ localStorageKey: "quantcell-ui-theme" });
  const isDark = theme === 'dark';
  const qc = useQuantColors();

  const [loading, setLoading] = useState(true);
  const [backtestData, setBacktestData] = useState<BacktestResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('all');
  // 多品种时实际传给后端的品种（undefined = 后端默认第一个品种）
  const [querySymbol, setQuerySymbol] = useState<string | undefined>(undefined);
  const [isMultiSymbol, setIsMultiSymbol] = useState(false);
  const [symbols, setSymbols] = useState<string[]>([]);
  // 因无数据被跳过的品种（详情接口 skipped_symbols 字段）
  const [skippedSymbols, setSkippedSymbols] = useState<Record<string, string>>({});
  const [showAllSymbols, setShowAllSymbols] = useState(false);
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
        const response = await backtestApi.getBacktestDetail(backtestId, querySymbol);

        // apiRequest 拦截器已经处理了 ApiResponse，直接返回 data 字段
        // api 层类型遵循共享的 BacktestDetailData，而本页以 BacktestResponse（后端实际结构）为准，二者字段存在差异需桥接断言
        if (response && response.id) {
          setBacktestData(response as unknown as BacktestResponse);
          // 无数据被跳过的品种（旧结果 JSON 无此字段，回退空对象）
          const skipped = (response as unknown as BacktestResponse).skipped_symbols || {};
          setSkippedSymbols(skipped);

          // 品种列表优先用结果 JSON 中实际有数据的品种，回退到回测配置
          const symbolKeys = (response as unknown as BacktestResponse).symbols?.length
            ? ((response as unknown as BacktestResponse).symbols as string[])
            : response.backtest_config?.symbols || [];
          setSymbols(symbolKeys);
          const multi = (response as unknown as BacktestResponse).is_multi_symbol ?? symbolKeys.length > 1;
          setIsMultiSymbol(multi);
          // 多品种默认选中后端返回的品种；单品种保持“全部”
          setSelectedSymbol(multi
            ? ((response as unknown as BacktestResponse).selected_symbol || symbolKeys[0] || 'all')
            : 'all');
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
  }, [backtestId, navigate, querySymbol]);

  /** 多品种切换：驱动后端重新拉取该品种的指标/曲线/成交；切回「全部」时恢复组合视图请求 */
  const handleSymbolChange = (value: string) => {
    setSelectedSymbol(value);
    setFilterSide('all');
    setFilterStatus('all');
    setFilterDateRange(null);
    setQuerySymbol(isMultiSymbol && value !== 'all' ? value : undefined);
  };

  // 从指标数组中获取指定key的指标值
  const getMetricValue = (key: string): number => {
    if (!backtestData?.metrics) return 0;
    const metric = backtestData.metrics.find(m => m.key === key);
    return metric?.value || 0;
  };

  // 完整新契约识别：timestamp + entry_price 同时存在（排除旧 fill 与无 timestamp 的中间版）
  const isContractTrade = (t: Trade) => t.timestamp != null && t.entry_price != null;
  // 是否整个为旧版本引擎产出的结果（无契约字段，无成交明细可展示）
  const rawTrades = backtestData?.trades ?? [];
  const isLegacyOnly = rawTrades.length > 0 && rawTrades.every((t) => !isContractTrade(t));

  // 获取交易列表，根据高级筛选条件进行筛选
  const getTrades = (): Trade[] => {
    // 非契约记录（旧格式/中间版）不适配新表格，直接滤掉
    let trades = rawTrades.filter(isContractTrade);

    // 根据货币对筛选
    if (selectedSymbol && selectedSymbol !== 'all') {
      // 统一去掉 / _ . - 等分隔符再比较，兼容 "BTC/USDT"、"BTCUSDT"、"BTCUSDT.BINANCE" 等写法
      const normalizeSym = (s: string) => s.replace(/[/_.-]/g, '').replace('BINANCE', '').toUpperCase();
      const normalizedSelected = normalizeSym(selectedSymbol);
      trades = trades.filter((trade) => {
        const normalizedTrade = normalizeSym(trade.symbol);
        // 任一方包含另一方即视为同一品种（兼容带交易所后缀等情况）
        return normalizedTrade.includes(normalizedSelected) || normalizedSelected.includes(normalizedTrade);
      });
    }

    // 根据方向筛选（契约 side 为开仓方向 buy/sell）
    if (filterSide && filterSide !== 'all') {
      trades = trades.filter((trade) => trade.side === filterSide);
    }

    // 根据状态筛选
    if (filterStatus && filterStatus !== 'all') {
      trades = trades.filter((trade) => trade.status.toLowerCase() === filterStatus.toLowerCase());
    }

    // 根据日期范围筛选（契约 timestamp 为秒级）
    if (filterDateRange && filterDateRange[0] && filterDateRange[1]) {
      const startDate = new Date(filterDateRange[0]).getTime();
      const endDate = new Date(filterDateRange[1]).getTime();
      trades = trades.filter((trade) => {
        const tradeTime = trade.timestamp * 1000;
        return tradeTime >= startDate && tradeTime <= endDate;
      });
    }

    return trades;
  };

  // 重置筛选条件
  const resetFilters = () => {
    setSelectedSymbol('all');
    setQuerySymbol(undefined);
    setFilterSide('all');
    setFilterStatus('all');
    setFilterDateRange(null);
  };

  // 获取权益曲线数据，转换为 EquityChart 组件期望的格式
  // 包含结余(balance)和净值(equity)两条线
  const getEquityCurve = (): Array<{ datetime: string; equity: number; balance: number; margin?: number }> => {
    return (backtestData?.equity_curve || []).map(point => ({
      datetime: point.formatted_time || new Date(point.timestamp * 1000).toISOString(),
      equity: point.equity,
      balance: point.balance,
      margin: point.margin,
    }));
  };

  // 格式化数字
  const formatNumber = (value: number, decimals = 2): string => {
    if (typeof value === 'number') {
      return value.toFixed(decimals);
    }
    return String(value);
  };

  // 导出报告：后端生成自包含 HTML（配置/指标/权益曲线/成交明细，口径与详情页一致）
  const handleExport = async () => {
    if (!backtestId) return;

    try {
      setExporting(true);
      // 多品种且选了具体品种 → 导出该品种视角；否则由后端导出组合视角
      const symbol = isMultiSymbol && selectedSymbol !== 'all' ? selectedSymbol : undefined;
      const blob = await backtestApi.getBacktestReport(backtestId, symbol);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      // 与后端 report_filename 保持一致（blob 下载取 download 属性名）
      link.download = `回测报告_${backtestId.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      message.success('报告已导出');
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
      // 多品种时把当前查看的品种带给回放页
      const qs = isMultiSymbol && selectedSymbol !== 'all' ? `?symbol=${encodeURIComponent(selectedSymbol)}` : '';
      navigate(`/backtest/replay/${backtestId}${qs}`);
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
              {symbols.length === 0 ? '-' : (
                <>
                  {symbols.slice(0, 3).join('、')}
                  {symbols.length > 3 && (
                    <>
                      {' '}等 {symbols.length} 个
                      <Button type="link" size="small" style={{ padding: 0, marginLeft: 8 }} onClick={() => setShowAllSymbols(true)}>
                        查看全部
                      </Button>
                    </>
                  )}
                </>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="时间周期">
              {backtestConfig.interval || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="交易模式">
              {backtestConfig.trading_mode === 'futures' ? '永续合约' : '现货'}
            </Descriptions.Item>
            <Descriptions.Item label="回测时间">
              {backtestConfig.start_time && backtestConfig.end_time
                ? `${backtestConfig.start_time} 至 ${backtestConfig.end_time}`
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="初始资金">
              {formatNumber(backtestConfig.initial_cash || 0)}
            </Descriptions.Item>
            <Descriptions.Item label="资金使用方式">
              {backtestConfig.capital_mode === 'shared' ? '组合共享资金池' : '各品种独立资金池'}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {backtestData.status}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* 回测概览指标（多品种时右上角切换品种，指标/曲线/成交均按品种展示） */}
        <Card
          title="回测概览"
          className="mb-6"
          extra={isMultiSymbol && symbols.length > 0 ? (
            <Space>
              <span>品种</span>
              <Select
                value={selectedSymbol}
                onChange={handleSymbolChange}
                style={{ width: 150 }}
                options={[{ label: '全部', value: 'all' }, ...symbols.map((s) => ({ label: s, value: s }))]}
              />
            </Space>
          ) : undefined}
        >
          {/* 卡片由 metricCards 清单驱动；共享资金池 + 品种视角只渲染按品种归因的指标 */}
          <Flex vertical gap={16}>
            {/* 无数据被跳过的品种提示：解释「选了 N 个标的跑完只剩 M 个」的原因 */}
            {Object.keys(skippedSymbols).length > 0 && (
              <Alert
                type="warning"
                showIcon
                message={
                  Object.keys(skippedSymbols).length === 1
                    ? `${Object.keys(skippedSymbols)[0]} 在所选时间范围内无本地数据，已跳过本次回测，请补齐数据或调整时间范围`
                    : `以下品种在所选时间范围内无本地数据，已跳过：${Object.keys(skippedSymbols).join('、')}`
                }
              />
            )}
            <Row gutter={[16, 16]}>
              {visibleMetricCards(backtestConfig.capital_mode, selectedSymbol).map((spec) => {
                const value = getMetricValue(spec.key);
                return (
                  <Col key={spec.key} xs={12} sm={8} md={6} lg={4}>
                    <MetricCard
                      label={spec.label}
                      value={formatMetricValue(spec, value)}
                      type={spec.color(value, getMetricValue)}
                      hint={spec.hint}
                    />
                  </Col>
                );
              })}
            </Row>
          </Flex>
        </Card>

        {/* 绩效分析图表 */}
        <Card title="权益曲线" className="mb-6">
          {getEquityCurve().length > 0 ? (
            <EquityChart data={getEquityCurve()} isDark={isDark} />
          ) : (
            <Empty description="暂无权益曲线数据" />
          )}
        </Card>

        {/* 因子分析（品种维度数据，组合视图「全部」下无口径，仅具体品种且配置了 factor_names 时渲染） */}
        {selectedSymbol !== 'all' && backtestData.factors && backtestData.factors.names && backtestData.factors.names.length > 0 && (
          <Card title="因子分析" className="mb-6">
            <Space orientation="vertical" size="large" style={{ display: 'flex', width: '100%' }}>
              {/* 因子概览：名称 + 阈值 */}
              <Descriptions bordered column={{ xs: 1, sm: 2, md: 3 }} size="small">
                <Descriptions.Item label="使用因子">
                  {backtestData.factors.names.join('、')}
                </Descriptions.Item>
                {Object.entries(backtestData.factors.thresholds || {}).map(([fname, th]) => (
                  <Descriptions.Item key={fname} label={`${fname} 阈值`}>
                    {th.buy != null && `买入 ≥ ${th.buy}`}
                    {th.buy != null && th.sell != null && ' / '}
                    {th.sell != null && `卖出 ≤ ${th.sell}`}
                  </Descriptions.Item>
                ))}
              </Descriptions>

              {/* 因子时序曲线 */}
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>因子时序</div>
                {(() => {
                  const ts = backtestData.factors!.time_series;
                  const xData = ts.formatted_times as string[];
                  const series = backtestData.factors!.names.map((name) => ({
                    name,
                    type: 'line',
                    data: (ts[name] as (number | null)[]) || [],
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1.5 },
                  }));
                  return (
                    <EChart
                      option={{
                        tooltip: { trigger: 'axis' },
                        legend: { data: backtestData.factors!.names, top: 0 },
                        grid: { left: 50, right: 20, top: 40, bottom: 40 },
                        xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 10 } },
                        yAxis: { type: 'value', scale: true },
                        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16 }],
                        series,
                        color: qc.chartSeries,
                      }}
                      style={{ height: 320, width: '100%' }}
                    />
                  );
                })()}
              </div>

              {/* 因子归因指标 + 分组收益 */}
              {Object.entries(backtestData.factors.attribution || {}).map(([fname, attr]) => (
                <div key={fname}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>{fname} · 绩效归因</div>
                  <Row gutter={[12, 12]}>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="IC" value={attr.ic != null ? attr.ic.toFixed(4) : 'N/A'} type={attr.ic && attr.ic >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="Rank IC" value={attr.rank_ic != null ? attr.rank_ic.toFixed(4) : 'N/A'} type={attr.rank_ic && attr.rank_ic >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="ICIR" value={attr.icir != null ? attr.icir.toFixed(4) : 'N/A'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="多空收益" value={attr.long_short_return != null ? (attr.long_short_return * 100).toFixed(2) + '%' : 'N/A'} type={attr.long_short_return && attr.long_short_return >= 0 ? 'positive' : 'negative'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="因子均值" value={attr.stats?.mean != null ? attr.stats.mean.toFixed(4) : 'N/A'} />
                    </Col>
                    <Col xs={12} sm={8} md={6} lg={4}>
                      <MetricCard label="因子标准差" value={attr.stats?.std != null ? attr.stats.std.toFixed(4) : 'N/A'} />
                    </Col>
                  </Row>
                  {/* 分组收益柱状图 */}
                  {attr.group_returns && Object.keys(attr.group_returns).length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <EChart
                        option={{
                          tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => (v as number).toFixed(4) },
                          grid: { left: 60, right: 20, top: 20, bottom: 40 },
                          xAxis: { type: 'category', data: Object.keys(attr.group_returns) },
                          yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
                          series: [{
                            type: 'bar',
                            data: Object.values(attr.group_returns),
                            itemStyle: { color: (p: any) => (p.value >= 0 ? qc.positive : qc.negative) },
                          }],
                        }}
                        style={{ height: 220, width: '100%' }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </Space>
          </Card>
        )}

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
            <div style={{ marginBottom: 16, padding: 16, backgroundColor: 'transparent', border: '1px solid var(--ant-color-border)', borderRadius: 8 }}>
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>交易标的</div>
                  <Select
                    value={selectedSymbol}
                    onChange={handleSymbolChange}
                    style={{ width: '100%' }}
                    placeholder="选择交易标的"
                  >
                    {/* 「全部」在单/多品种下都可能是当前值，必须始终渲染 */}
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
          ) : isLegacyOnly ? (
            <Empty description="该回测由旧版本引擎生成，无成交明细" />
          ) : rawTrades.length === 0 ? (
            <Empty
              description={
                getMetricValue('total_trades') > 0
                  ? `该回测有 ${getMetricValue('total_trades')} 笔成交但尚未平仓，无完整交易记录`
                  : '该回测未产生任何成交，请检查策略参数（如价格区间）是否与市场行情匹配'
              }
            />
          ) : (
            <Empty description="暂无交易记录" />
          )}
        </Card>
      </div>

      {/* 全部交易标的弹窗（标的过多时点开查看） */}
      <Modal
        title={`全部交易标的（共 ${symbols.length} 个）`}
        open={showAllSymbols}
        onCancel={() => setShowAllSymbols(false)}
        footer={<Button onClick={() => setShowAllSymbols(false)}>关闭</Button>}
        width={640}
      >
        <div style={{ maxHeight: 500, overflowY: 'auto' }}>
          <Space wrap size={[8, 8]}>
            {symbols.map((s) => (
              <Tag key={s} style={{ fontSize: 13, fontFamily: 'monospace' }}>{s}</Tag>
            ))}
          </Space>
        </div>
      </Modal>
    </PageContainer>
  );
};

export default BacktestDetail;
