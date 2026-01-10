/**
 * 数据质量组件
 * 功能：显示和管理数据质量报告，包括K线数据的完整性、连续性、有效性、唯一性和覆盖率
 */
import { useState, useEffect } from 'react';
import { dataApi } from '../api';
import { Spin, Card, Progress, Table, Select, Button, message, Space, Typography, Divider, Tabs, Tag } from 'antd';
import { ReloadOutlined, InfoCircleOutlined, CalendarOutlined, BarChartOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

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
      total_invalid_records: number;
    };
    uniqueness: {
      status: string;
      duplicate_records: number;
      duplicate_periods: string[];
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
        type: systemConfig.crypto_trading_mode,
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
      const response = await dataApi.checkKlineQuality({
        symbol,
        interval,
        exchange: systemConfig.exchange
      });
      
      if (response.code === 0) {
        setQualityReport(response.data);
        message.success('获取数据质量报告成功');
      } else {
        message.error(`获取数据质量报告失败: ${response.message}`);
      }
    } catch (error) {
      message.error('获取数据质量报告失败');
      console.error('获取数据质量报告失败:', error);
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
            <Text style={{ marginLeft: 8 }}>{score}%</Text>
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

    return (
      <Card title="详细检查结果" className="quality-details">
        <Tabs defaultActiveKey="continuity" type="card">
          {/* 连续性检查 */}
          <TabPane tab={<span><CalendarOutlined /> 连续性检查</span>} key="continuity">
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
                  <Text style={{ marginLeft: 8 }}>
                    {Math.round(qualityReport.checks.continuity.coverage_ratio * 100)}%
                  </Text>
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
          </TabPane>

          {/* 覆盖率检查 */}
          <TabPane tab={<span><BarChartOutlined /> 覆盖率检查</span>} key="coverage">
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
          </TabPane>

          {/* 完整性检查 */}
          <TabPane tab={<span><InfoCircleOutlined /> 完整性检查</span>} key="integrity">
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
          </TabPane>

          {/* 有效性检查 */}
          <TabPane tab={<span><InfoCircleOutlined /> 有效性检查</span>} key="validity">
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
            </div>
          </TabPane>

          {/* 唯一性检查 */}
          <TabPane tab={<span><InfoCircleOutlined /> 唯一性检查</span>} key="uniqueness">
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
            </div>
          </TabPane>
        </Tabs>
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
          <Spin tip="正在生成数据质量报告..." size="large" />
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
