/**
 * 数据质量组件
 * 功能：显示和管理数据质量报告，包括K线数据的完整性、连续性、有效性、唯一性和覆盖率
 */
import { useState, useEffect } from 'react';
import { dataApi } from '../api';
import { Spin, Card, Progress, Table, Select, Button, message, Space, Typography, Divider, Tabs, Tag, Pagination, Modal } from 'antd';
import { ReloadOutlined, InfoCircleOutlined, CalendarOutlined, BarChartOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

interface DuplicateRecord {
  id: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  row_number: number;
}

interface DuplicateGroup {
  group_type: string;
  key: string;
  records: DuplicateRecord[];
  count: number;
}



interface KlineQualityReport {
  symbol: string;
  interval: string;
  overall_status: string;
  checks: {
    integrity: {
      status: string;
      missing_columns: string[];
      missing_values: Record<string, number>;
      total_records: number;
    };
    continuity: {
      status: string;
      expected_records: number;
      actual_records: number;
      missing_records: number;
      missing_periods: string[];
      coverage_ratio: number;
      missing_time_ranges: Array<{
        start: string;
        end: string;
        duration: string;
        count: number;
      }>;
    };
    validity: {
      status: string;
      negative_prices: string[];
      negative_volumes: string[];
      invalid_high_low: string[];
      invalid_price_logic: string[];
      abnormal_price_changes: Array<{
        timestamp: string;
        change_pct: number;
      }>;
      abnormal_volumes: Array<{
        timestamp: string;
        volume: number;
        avg_30d_volume: number;
      }>;
      price_gaps: Array<{
        timestamp: string;
        gap_pct: number;
      }>;
      total_invalid_records: number;
    };
    consistency: {
      status: string;
      time_format_issues: string[];
      duplicate_codes: string[];
      code_name_mismatches: string[];
      inconsistent_adj_factors: string[];
    };
    logic: {
      status: string;
      trading_time_issues: string[];
      suspension_issues: string[];
      price_limit_issues: string[];
    };
    uniqueness: {
      status: string;
      duplicate_records: number;
      duplicate_periods: string[];
      duplicate_code_timestamp: string[];
      duplicate_details?: DuplicateGroup[]; // 新增：重复记录的详细信息
    };
    coverage: {
      status: string;
      data_start_date: string;
      data_end_date: string;
      expected_start_date: string;
      expected_end_date: string;
      missing_historical_data: boolean;
      missing_future_data: boolean;
      historical_gap_days: number;
      future_gap_days: number;
    };
  };
  total_records: number;
}

interface DataQualityProps {
  systemConfig: {
    exchange: string;
    crypto_trading_mode: string;
  };
}

const DataQuality = ({ systemConfig }: DataQualityProps) => {
  // 数据质量报告状态
  const [qualityReport, setQualityReport] = useState<KlineQualityReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState('1d');
  const [symbolOptions, setSymbolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [isLoadingSymbols, setIsLoadingSymbols] = useState(false);
  // 重复记录相关状态
  const [duplicateDetails, setDuplicateDetails] = useState<DuplicateGroup[]>([]);
  const [isLoadingDuplicates, setIsLoadingDuplicates] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState('keep_first');
  const [showDuplicateDetails, setShowDuplicateDetails] = useState(false);
  // 分页相关状态
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  // 折叠状态管理
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  // 筛选相关状态
  const [minDuplicateCount, setMinDuplicateCount] = useState<number>(0);

  // 区间选项
  const intervalOptions = [
    { value: '1m', label: '1分钟' },
    { value: '5m', label: '5分钟' },
    { value: '15m', label: '15分钟' },
    { value: '30m', label: '30分钟' },
    { value: '1h', label: '1小时' },
    { value: '4h', label: '4小时' },
    { value: '1d', label: '1天' },
  ];

  // 获取货币对列表
  const fetchSymbols = async () => {
    try {
      setIsLoadingSymbols(true);
      const response = await dataApi.getCryptoSymbols({
        crypto_type: systemConfig.crypto_trading_mode,
        exchange: systemConfig.exchange,
        limit: 1000
      });
      
      if (response.code === 0) {
        const symbols = response.data.symbols || [];
        setSymbolOptions(symbols.map((s: string) => ({ value: s, label: s })));
      }
    } catch (error) {
      message.error('获取货币对列表失败');
      console.error('获取货币对列表失败:', error);
    } finally {
      setIsLoadingSymbols(false);
    }
  };

  // 获取数据质量报告
  const fetchQualityReport = async () => {
    try {
      setIsLoading(true);
      // 响应拦截器已经处理了code === 0的情况，直接返回data
      const data = await dataApi.checkKlineQuality({
        symbol,
        interval
      });
      
      setQualityReport(data);
      message.success('获取数据质量报告成功');
      
      // 如果唯一性检查失败，自动获取重复记录详情
      if (data.checks.uniqueness.status === 'fail') {
        fetchDuplicateDetails();
      }
    } catch (error) {
      // 响应拦截器会将code !== 0的情况处理为ApiError
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      message.error(`获取数据质量报告失败: ${errorMessage}`);
      console.error('获取数据质量报告失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 获取重复记录详情
  const fetchDuplicateDetails = async () => {
    try {
      setIsLoadingDuplicates(true);
      const data = await dataApi.getKlineDuplicates({
        symbol,
        interval
      });
      
      setDuplicateDetails(data.duplicate_details);
      setShowDuplicateDetails(true);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      message.error(`获取重复记录详情失败: ${errorMessage}`);
      console.error('获取重复记录详情失败:', error);
    } finally {
      setIsLoadingDuplicates(false);
    }
  };

  // 处理重复记录
  const resolveDuplicates = async (groupKey?: string) => {
    try {
      setIsLoading(true);
      const data = await dataApi.resolveKlineDuplicates({
        symbol,
        interval,
        strategy: selectedStrategy,
        group_key: groupKey
      });
      
      message.success(`成功处理 ${data.processed_count} 条重复记录`);
      // 重新获取数据质量报告
      fetchQualityReport();
      // 重新获取重复记录详情
      fetchDuplicateDetails();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      message.error(`处理重复记录失败: ${errorMessage}`);
      console.error('处理重复记录失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 组件挂载时获取货币对列表
  useEffect(() => {
    fetchSymbols();
  }, [systemConfig.crypto_trading_mode, systemConfig.exchange]);

  // 计算总体质量评分
  const calculateQualityScore = () => {
    if (!qualityReport) return 0;
    
    // 确保所有检查维度都被包含
    const checks = Object.values(qualityReport.checks);
    const passedChecks = checks.filter(check => check.status === 'pass').length;
    return Math.round((passedChecks / checks.length) * 100);
  };

  // 获取状态标签颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pass':
        return 'green';
      case 'fail':
        return 'red';
      default:
        return 'blue';
    }
  };

  // 渲染概览卡片
  const renderOverview = () => {
    if (!qualityReport) return null;

    const score = calculateQualityScore();

    return (
      <Card title="数据质量概览" className="quality-overview">
        <Space size="large" wrap>
          <div className="overview-item">
            <Text strong>总体状态:</Text>
            <Tag color={getStatusColor(qualityReport.overall_status)} style={{ marginLeft: 8 }}>
              {qualityReport.overall_status === 'pass' ? '通过' : '失败'}
            </Tag>
          </div>
          <div className="overview-item">
            <Text strong>质量评分:</Text>
            <Progress percent={score} size="small" status="active" style={{ marginLeft: 8, width: 100 }} />
          </div>
          <div className="overview-item">
            <Text strong>货币对:</Text>
            <Text style={{ marginLeft: 8 }}>{qualityReport.symbol}</Text>
          </div>
          <div className="overview-item">
            <Text strong>时间周期:</Text>
            <Text style={{ marginLeft: 8 }}>{qualityReport.interval}</Text>
          </div>
          <div className="overview-item">
            <Text strong>总记录数:</Text>
            <Text style={{ marginLeft: 8 }}>{qualityReport.total_records}</Text>
          </div>
        </Space>
      </Card>
    );
  };

  // 渲染详细检查结果
  const renderCheckDetails = () => {
    if (!qualityReport) return null;

    const tabItems = [
      {
        key: 'continuity',
        label: <span><CalendarOutlined /> 连续性检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.continuity.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.continuity.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            <Space size="large" wrap style={{ margin: '16px 0' }}>
              <div className="check-item">
                <Text strong>预期记录数:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.continuity.expected_records}</Text>
              </div>
              <div className="check-item">
                <Text strong>实际记录数:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.continuity.actual_records}</Text>
              </div>
              <div className="check-item">
                <Text strong>缺失记录数:</Text>
                <Text style={{ marginLeft: 8, color: qualityReport.checks.continuity.missing_records > 0 ? 'red' : 'black' }}>
                  {qualityReport.checks.continuity.missing_records}
                </Text>
              </div>
              <div className="check-item">
                <Text strong>覆盖率:</Text>
                <Progress 
                  percent={Math.round(qualityReport.checks.continuity.coverage_ratio * 100)} 
                  size="small" 
                  status="active" 
                  style={{ marginLeft: 8, width: 100 }} 
                />
              </div>
            </Space>
            
            {/* 缺失时间段 */}
            {qualityReport.checks.continuity.missing_time_ranges.length > 0 && (
              <div className="missing-ranges">
                <Title level={5} style={{ marginTop: 16, marginBottom: 16 }}>缺失时间段</Title>
                <Table
                  columns={[
                    { title: '开始时间', dataIndex: 'start', key: 'start' },
                    { title: '结束时间', dataIndex: 'end', key: 'end' },
                    { title: '持续时间', dataIndex: 'duration', key: 'duration' },
                    { title: '缺失记录数', dataIndex: 'count', key: 'count', align: 'right' }
                  ]}
                  dataSource={qualityReport.checks.continuity.missing_time_ranges}
                  rowKey={(record) => `${record.start}-${record.end}`}
                  bordered
                  pagination={{ pageSize: 5 }}
                />
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'coverage',
        label: <span><BarChartOutlined /> 覆盖率检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.coverage.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.coverage.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            <Space size="large" wrap style={{ margin: '16px 0' }}>
              <div className="check-item">
                <Text strong>数据开始日期:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.coverage.data_start_date}</Text>
              </div>
              <div className="check-item">
                <Text strong>数据结束日期:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.coverage.data_end_date}</Text>
              </div>
              <div className="check-item">
                <Text strong>预期开始日期:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.coverage.expected_start_date}</Text>
              </div>
              <div className="check-item">
                <Text strong>预期结束日期:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.coverage.expected_end_date}</Text>
              </div>
            </Space>
            
            <Divider />
            
            <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
              <div className="coverage-item">
                <Text strong>历史数据缺失:</Text>
                <Tag color={qualityReport.checks.coverage.missing_historical_data ? 'red' : 'green'} style={{ marginLeft: 8 }}>
                  {qualityReport.checks.coverage.missing_historical_data ? '是' : '否'}
                </Tag>
                {qualityReport.checks.coverage.missing_historical_data && (
                  <Text style={{ marginLeft: 8, color: 'red' }}>
                    缺失 {qualityReport.checks.coverage.historical_gap_days} 天
                  </Text>
                )}
              </div>
              <div className="coverage-item">
                <Text strong>未来数据缺失:</Text>
                <Tag color={qualityReport.checks.coverage.missing_future_data ? 'red' : 'green'} style={{ marginLeft: 8 }}>
                  {qualityReport.checks.coverage.missing_future_data ? '是' : '否'}
                </Tag>
                {qualityReport.checks.coverage.missing_future_data && (
                  <Text style={{ marginLeft: 8, color: 'red' }}>
                    缺失 {qualityReport.checks.coverage.future_gap_days} 天
                  </Text>
                )}
              </div>
            </Space>
          </div>
        ),
      },
      {
        key: 'integrity',
        label: <span><InfoCircleOutlined /> 完整性检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.integrity.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.integrity.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            <Space size="large" wrap style={{ margin: '16px 0' }}>
              <div className="check-item">
                <Text strong>总记录数:</Text>
                <Text style={{ marginLeft: 8 }}>{qualityReport.checks.integrity.total_records}</Text>
              </div>
            </Space>
            
            {qualityReport.checks.integrity.missing_columns.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>缺失列:</Text>
                <Tag color="red" style={{ marginLeft: 8 }}>
                  {qualityReport.checks.integrity.missing_columns.join(', ')}
                </Tag>
              </div>
            )}
            
            {Object.keys(qualityReport.checks.integrity.missing_values).length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>缺失值:</Text>
                <Space wrap style={{ marginLeft: 8 }}>
                  {Object.entries(qualityReport.checks.integrity.missing_values).map(([column, count]) => (
                    <Tag key={column} color="orange">
                      {column}: {count}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'validity',
        label: <span><InfoCircleOutlined /> 有效性检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.validity.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.validity.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            <Space size="large" wrap style={{ margin: '16px 0' }}>
              <div className="check-item">
                <Text strong>总无效记录数:</Text>
                <Text style={{ marginLeft: 8, color: qualityReport.checks.validity.total_invalid_records > 0 ? 'red' : 'black' }}>
                  {qualityReport.checks.validity.total_invalid_records}
                </Text>
              </div>
            </Space>
            
            {qualityReport.checks.validity.negative_prices.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>负价格记录:</Text>
                <Text style={{ marginLeft: 8, color: 'red' }}>
                  共 {qualityReport.checks.validity.negative_prices.length} 条记录
                </Text>
              </div>
            )}
            
            {qualityReport.checks.validity.negative_volumes.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>负成交量记录:</Text>
                <Text style={{ marginLeft: 8, color: 'red' }}>
                  共 {qualityReport.checks.validity.negative_volumes.length} 条记录
                </Text>
              </div>
            )}
            
            {qualityReport.checks.validity.invalid_high_low.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>无效高低价记录:</Text>
                <Text style={{ marginLeft: 8, color: 'red' }}>
                  共 {qualityReport.checks.validity.invalid_high_low.length} 条记录
                </Text>
              </div>
            )}
            
            {qualityReport.checks.validity.invalid_price_logic.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>无效价格逻辑记录:</Text>
                <Text style={{ marginLeft: 8, color: 'red' }}>
                  共 {qualityReport.checks.validity.invalid_price_logic.length} 条记录
                </Text>
              </div>
            )}
            
            {qualityReport.checks.validity.abnormal_price_changes.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>异常涨跌幅记录:</Text>
                <Table
                  columns={[
                    { title: '时间', dataIndex: 'timestamp', key: 'timestamp' },
                    { 
                      title: '涨跌幅(%)', 
                      dataIndex: 'change_pct', 
                      key: 'change_pct',
                      render: (text: number) => (
                        <Text style={{ color: text > 0 ? 'red' : 'green' }}>
                          {text.toFixed(2)}
                        </Text>
                      )
                    }
                  ]}
                  dataSource={qualityReport.checks.validity.abnormal_price_changes}
                  rowKey={(record) => `abnormal-price-${record.timestamp}`}
                  bordered
                  pagination={{ pageSize: 5 }}
                  style={{ marginTop: 8 }}
                />
              </div>
            )}
            
            {qualityReport.checks.validity.abnormal_volumes.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>异常成交量记录:</Text>
                <Table
                  columns={[
                    { title: '时间', dataIndex: 'timestamp', key: 'timestamp' },
                    { title: '成交量', dataIndex: 'volume', key: 'volume' },
                    { title: '30天平均成交量', dataIndex: 'avg_30d_volume', key: 'avg_30d_volume' }
                  ]}
                  dataSource={qualityReport.checks.validity.abnormal_volumes}
                  rowKey={(record) => `abnormal-volume-${record.timestamp}`}
                  bordered
                  pagination={{ pageSize: 5 }}
                  style={{ marginTop: 8 }}
                />
              </div>
            )}
            
            {qualityReport.checks.validity.price_gaps.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>价格跳空异常记录:</Text>
                <Table
                  columns={[
                    { title: '时间', dataIndex: 'timestamp', key: 'timestamp' },
                    { 
                      title: '跳空幅度(%)', 
                      dataIndex: 'gap_pct', 
                      key: 'gap_pct',
                      render: (text: number) => (
                        <Text style={{ color: text > 0 ? 'red' : 'green' }}>
                          {text.toFixed(2)}
                        </Text>
                      )
                    }
                  ]}
                  dataSource={qualityReport.checks.validity.price_gaps}
                  rowKey={(record) => `price-gap-${record.timestamp}`}
                  bordered
                  pagination={{ pageSize: 5 }}
                  style={{ marginTop: 8 }}
                />
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'consistency',
        label: <span><InfoCircleOutlined /> 一致性检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.consistency.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.consistency.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            {qualityReport.checks.consistency.time_format_issues.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>时间格式问题:</Text>
                {qualityReport.checks.consistency.time_format_issues.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
            
            {qualityReport.checks.consistency.duplicate_codes.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>重复代码:</Text>
                {qualityReport.checks.consistency.duplicate_codes.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
            
            {qualityReport.checks.consistency.code_name_mismatches.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>代码名称不匹配:</Text>
                {qualityReport.checks.consistency.code_name_mismatches.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
            
            {qualityReport.checks.consistency.inconsistent_adj_factors.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>复权因子不一致:</Text>
                {qualityReport.checks.consistency.inconsistent_adj_factors.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'logic',
        label: <span><InfoCircleOutlined /> 逻辑性检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.logic.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.logic.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            {qualityReport.checks.logic.trading_time_issues.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>交易时间问题:</Text>
                {qualityReport.checks.logic.trading_time_issues.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
            
            {qualityReport.checks.logic.suspension_issues.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>停牌数据处理问题:</Text>
                {qualityReport.checks.logic.suspension_issues.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
            
            {qualityReport.checks.logic.price_limit_issues.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>涨跌停规则问题:</Text>
                {qualityReport.checks.logic.price_limit_issues.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'uniqueness',
        label: <span><InfoCircleOutlined /> 唯一性检查</span>,
        children: (
          <div className="check-section">
            <div className="check-header">
              <Text strong>状态:</Text>
              <Tag color={getStatusColor(qualityReport.checks.uniqueness.status)} style={{ marginLeft: 8 }}>
                {qualityReport.checks.uniqueness.status === 'pass' ? '通过' : '失败'}
              </Tag>
            </div>
            
            <Space size="large" wrap style={{ margin: '16px 0' }}>
              <div className="check-item">
                <Text strong>重复记录数:</Text>
                <Text style={{ marginLeft: 8, color: qualityReport.checks.uniqueness.duplicate_records > 0 ? 'red' : 'black' }}>
                  {qualityReport.checks.uniqueness.duplicate_records}
                </Text>
              </div>
            </Space>
            
            {qualityReport.checks.uniqueness.duplicate_records > 0 && (
              <div className="issue-section" style={{ marginTop: 16 }}>
                <Space size="middle" wrap>
                  <Button 
                    type="primary" 
                    onClick={fetchDuplicateDetails} 
                    loading={isLoadingDuplicates}
                  >
                    查看重复记录详情
                  </Button>
                  <Button 
                    danger 
                    onClick={() => {
                      Modal.confirm({
                        title: '确认处理所有重复记录',
                        content: `确定要使用「${selectedStrategy === 'keep_first' ? '保留第一条记录' : 
                                 selectedStrategy === 'keep_last' ? '保留最后一条记录' : 
                                 selectedStrategy === 'keep_max_volume' ? '保留成交量最大的记录' : 
                                 '保留成交量最小的记录'}」策略处理所有重复记录吗？`,
                        okText: '确定',
                        cancelText: '取消',
                        onOk: () => resolveDuplicates()
                      });
                    }}
                    loading={isLoading}
                  >
                    处理所有重复记录
                  </Button>
                  <Select
                    value={selectedStrategy}
                    onChange={setSelectedStrategy}
                    placeholder="选择处理策略"
                    style={{ width: 200 }}
                    options={[
                      { value: 'keep_first', label: '保留第一条记录' },
                      { value: 'keep_last', label: '保留最后一条记录' },
                      { value: 'keep_max_volume', label: '保留成交量最大的记录' },
                      { value: 'keep_min_volume', label: '保留成交量最小的记录' }
                    ]}
                  />
                </Space>
              </div>
            )}
            
            {qualityReport.checks.uniqueness.duplicate_periods.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>重复时间周期:</Text>
                <Text style={{ marginLeft: 8, color: 'red' }}>
                  共 {qualityReport.checks.uniqueness.duplicate_periods.length} 个重复周期
                </Text>
              </div>
            )}
            
            {qualityReport.checks.uniqueness.duplicate_code_timestamp.length > 0 && (
              <div className="issue-section">
                <Text strong style={{ color: 'red' }}>重复代码+时间戳记录:</Text>
                {qualityReport.checks.uniqueness.duplicate_code_timestamp.map((issue, index) => (
                  <Tag key={index} color="red" style={{ marginLeft: 8, marginTop: 8 }}>
                    {issue}
                  </Tag>
                ))}
              </div>
            )}
            
            {/* 重复记录详情表格 */}
            {showDuplicateDetails && duplicateDetails.length > 0 && (
              <div className="duplicate-details" style={{ marginTop: 24 }}>
                <Title level={4}>重复记录详情</Title>
                {/* 统计信息 */}
                <Card size="small" style={{ marginBottom: 16 }}>
                  <Space size="middle">
                    <Text strong>总重复组数: {duplicateDetails.length}</Text>
                    <Text strong>总重复记录数: {duplicateDetails.reduce((sum, group) => sum + group.count, 0)}</Text>
                  </Space>
                </Card>
                {/* 筛选表单 */}
                <Card size="small" style={{ marginBottom: 16 }}>
                  <Space size="middle" wrap>
                    <div>
                      <Text strong>最小重复数量: </Text>
                      <Select
                        value={minDuplicateCount}
                        onChange={setMinDuplicateCount}
                        style={{ width: 120 }}
                        options={[
                          { value: 0, label: '全部' },
                          { value: 2, label: '≥2' },
                          { value: 5, label: '≥5' },
                          { value: 10, label: '≥10' },
                          { value: 50, label: '≥50' },
                          { value: 100, label: '≥100' }
                        ]}
                      />
                    </div>
                  </Space>
                </Card>
                <Spin spinning={isLoadingDuplicates}>
                  {(() => {
                    // 筛选逻辑
                    const filteredGroups = duplicateDetails.filter(group => {
                      return group.count >= minDuplicateCount;
                    });
                    
                    // 分页逻辑
                    const startIndex = (currentPage - 1) * pageSize;
                    const endIndex = startIndex + pageSize;
                    const paginatedGroups = filteredGroups.slice(startIndex, endIndex);
                    
                    return (
                      <>
                        {paginatedGroups.map((group) => {
                          // 检查当前组是否展开
                          const isExpanded = expandedGroups.has(group.key);
                            
                          return (
                            <Card key={`group-${group.key}`} title={`重复组: ${group.key}`} style={{ marginBottom: 16 }}>
                              <Space size="middle" style={{ marginBottom: 16 }}>
                                <Text strong>重复记录数: {group.count}</Text>
                                <Button 
                                  type="default" 
                                  onClick={() => {
                                    // 切换折叠状态
                                    const newExpanded = new Set(expandedGroups);
                                    if (isExpanded) {
                                      newExpanded.delete(group.key);
                                    } else {
                                      newExpanded.add(group.key);
                                    }
                                    setExpandedGroups(newExpanded);
                                  }}
                                  size="small"
                                >
                                  {isExpanded ? '收起' : '展开'}
                                </Button>
                                <Button 
                                  danger 
                                  onClick={() => {
                                    Modal.confirm({
                                      title: '确认处理重复记录',
                                      content: `确定要使用「${selectedStrategy === 'keep_first' ? '保留第一条记录' : 
                                               selectedStrategy === 'keep_last' ? '保留最后一条记录' : 
                                               selectedStrategy === 'keep_max_volume' ? '保留成交量最大的记录' : 
                                               '保留成交量最小的记录'}」策略处理此组重复记录吗？`,
                                      okText: '确定',
                                      cancelText: '取消',
                                      onOk: () => resolveDuplicates(group.key)
                                    });
                                  }}
                                  loading={isLoading}
                                  size="small"
                                >
                                  处理此组
                                </Button>
                              </Space>
                              
                              {/* 根据折叠状态显示或隐藏表格 */}
                              {isExpanded && (
                                <Table
                                  columns={[
                                    { title: '序号', dataIndex: 'row_number', key: 'row_number', width: 80 },
                                    { title: '时间', dataIndex: 'timestamp', key: 'timestamp' },
                                    { title: '开盘价', dataIndex: 'open', key: 'open', width: 120, render: (text: number) => text.toFixed(4) },
                                    { title: '最高价', dataIndex: 'high', key: 'high', width: 120, render: (text: number) => text.toFixed(4) },
                                    { title: '最低价', dataIndex: 'low', key: 'low', width: 120, render: (text: number) => text.toFixed(4) },
                                    { title: '收盘价', dataIndex: 'close', key: 'close', width: 120, render: (text: number) => text.toFixed(4) },
                                    { title: '成交量', dataIndex: 'volume', key: 'volume', width: 150, render: (text: number) => text.toFixed(2) },
                                  ]}
                                  dataSource={group.records}
                                  // 组合id和row_number确保key唯一性
                                  rowKey={(record) => `record-${record.id}-${record.row_number}`}
                                  bordered
                                  pagination={false}
                                  size="small"
                                  // 性能优化
                                  scroll={{ x: 800 }}
                                  // 只在展开时渲染表格，减少初始渲染压力
                                />
                              )}
                            </Card>
                          );
                        })}
                        
                        {/* 分页组件 */}
                        <div style={{ marginTop: 16, textAlign: 'center' }}>
                          <Pagination
                            current={currentPage}
                            pageSize={pageSize}
                            total={filteredGroups.length}
                            onChange={(page, size) => {
                              setCurrentPage(page);
                              setPageSize(size);
                            }}
                            pageSizeOptions={['10', '20', '50', '100']}
                            showSizeChanger
                            showTotal={(total) => `共 ${total} 组，筛选后 ${filteredGroups.length} 组`}
                          />
                        </div>
                      </>
                    );
                  })()}
                </Spin>
              </div>
            )}
          </div>
        ),
      },
    ];

    return (
      <Card title="详细检查结果" className="quality-details">
        <Tabs defaultActiveKey="continuity" type="card" items={tabItems} />
      </Card>
    );
  };

  // 渲染查询表单
  const renderQueryForm = () => {
    return (
      <Card title="查询条件" className="query-form">
        <Space size="large" wrap>
          <Select
            value={symbol}
            onChange={setSymbol}
            placeholder="选择货币对"
            loading={isLoadingSymbols}
            style={{ width: 200 }}
            options={symbolOptions}
          />
          <Select
            value={interval}
            onChange={setInterval}
            placeholder="选择时间周期"
            style={{ width: 120 }}
            options={intervalOptions}
          />
          <Button
            type="primary"
            onClick={fetchQualityReport}
            loading={isLoading}
            icon={<ReloadOutlined />}
          >
            检查数据质量
          </Button>
        </Space>
      </Card>
    );
  };

  return (
    <div className="data-quality-container">
      <Title level={2}>数据质量检查</Title>
      <Divider />
      
      {renderQueryForm()}
      
      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
          <div style={{ textAlign: 'center' }}>
            <Text>正在生成数据质量报告...</Text>
            <Spin size="large" style={{ marginTop: 16 }} />
          </div>
        </div>
      ) : qualityReport ? (
        <Space orientation="vertical" size="large" style={{ width: '100%', marginTop: 16 }}>
          {renderOverview()}
          {renderCheckDetails()}
        </Space>
      ) : null}
    </div>
  );
};

export default DataQuality;