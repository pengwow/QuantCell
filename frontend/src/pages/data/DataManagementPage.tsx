/**
 * 统一数据管理页面
 * 整合数据池、数据采集、数据质量三个核心功能模块
 * 参考主流金融工具设计，以货币对为核心展示单位
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Tabs,
  Table,
  Button,
  Input,
  Select,
  Tag,
  Space,
  Badge,
  Progress,
  Form,
  DatePicker,
  message,
  Empty,
  Switch,
  Divider,
  Typography,
  Row,
  Col,
  Statistic,
} from 'antd';
import {
  SearchOutlined,
  StarOutlined,
  StarFilled,
  DownloadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  CloudDownloadOutlined,
  EyeOutlined,
} from '@ant-design/icons';

import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { dataApi } from '@/api/dataApi';
import { wsService } from '@/services/websocketService';
import type { Task } from '@/types/data';

const { Text } = Typography;
const { TabPane } = Tabs;
const { RangePicker } = DatePicker;

// 系统配置
const SYSTEM_CONFIG = {
  current_market_type: 'crypto',
  exchange: 'binance',
  crypto_trading_mode: 'spot',
};

// 货币对数据接口
interface SymbolData {
  symbol: string;
  baseAsset: string;
  quoteAsset: string;
  price: number;
  priceChange24h: number;
  priceChangePercent24h: number;
  volume24h: number;
  high24h: number;
  low24h: number;
  isFavorite: boolean;
  hasData: boolean;
  lastUpdateTime?: string;
  dataQuality?: 'good' | 'warning' | 'bad' | 'unknown';
  availableIntervals: string[];
  autoUpdate: boolean;
}





/**
 * 统一数据管理页面组件
 */
const DataManagementPage = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('symbols');

  // 货币对列表状态
  const [symbols, setSymbols] = useState<SymbolData[]>([]);
  const [filteredSymbols, setFilteredSymbols] = useState<SymbolData[]>([]);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [quoteFilter, setQuoteFilter] = useState<string>('all');
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);

  // 数据质量状态
  const [selectedSymbolForQuality, setSelectedSymbolForQuality] = useState<string>('');
  const [selectedIntervalForQuality, setSelectedIntervalForQuality] = useState<string>('');
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityDetail, setQualityDetail] = useState<any>(null);

  // 数据采集状态
  const [collectionForm] = Form.useForm();
  const [collectionTasks, setCollectionTasks] = useState<Task[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [taskProgress, setTaskProgress] = useState<number>(0);

  // 初始化加载数据
  useEffect(() => {
    fetchSymbols();
    fetchCollectionTasks();
  }, []);

  // WebSocket 连接
  useEffect(() => {
    wsService.connect();

    const handleTaskProgress = (data: any) => {
      if (data.task_id === currentTaskId) {
        setTaskProgress(data.progress?.percentage || 0);
      }
    };

    const handleTaskStatus = (data: any) => {
      if (data.task_id === currentTaskId) {
        setTaskStatus(data.status);
        if (data.status === 'completed' || data.status === 'failed') {
          fetchCollectionTasks();
        }
      }
    };

    wsService.on('task:progress', handleTaskProgress);
    wsService.on('task:status', handleTaskStatus);

    return () => {
      wsService.off('task:progress', handleTaskProgress);
      wsService.off('task:status', handleTaskStatus);
    };
  }, [currentTaskId]);

  // 搜索过滤
  useEffect(() => {
    let result = symbols;

    if (searchText) {
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(searchText.toLowerCase()) ||
          s.baseAsset.toLowerCase().includes(searchText.toLowerCase())
      );
    }

    if (quoteFilter !== 'all') {
      result = result.filter((s) => s.quoteAsset === quoteFilter);
    }

    if (showFavoritesOnly) {
      result = result.filter((s) => s.isFavorite);
    }

    setFilteredSymbols(result);
  }, [symbols, searchText, quoteFilter, showFavoritesOnly]);

  // 获取货币对列表
  const fetchSymbols = async () => {
    try {
      setSymbolLoading(true);
      await dataApi.getCryptoSymbols({
        exchange: SYSTEM_CONFIG.exchange,
        limit: 500,
      });

      // 模拟数据，实际应从API获取
      const mockSymbols: SymbolData[] = [
        {
          symbol: 'BTCUSDT',
          baseAsset: 'BTC',
          quoteAsset: 'USDT',
          price: 67542.32,
          priceChange24h: 1250.5,
          priceChangePercent24h: 1.89,
          volume24h: 28500000000,
          high24h: 68200.0,
          low24h: 66100.0,
          isFavorite: true,
          hasData: true,
          lastUpdateTime: '2024-01-15 14:30:00',
          dataQuality: 'good',
          availableIntervals: ['1m', '5m', '15m', '1h', '4h', '1d'],
          autoUpdate: true,
        },
        {
          symbol: 'ETHUSDT',
          baseAsset: 'ETH',
          quoteAsset: 'USDT',
          price: 3456.78,
          priceChange24h: -45.2,
          priceChangePercent24h: -1.29,
          volume24h: 15200000000,
          high24h: 3520.0,
          low24h: 3400.0,
          isFavorite: true,
          hasData: true,
          lastUpdateTime: '2024-01-15 14:30:00',
          dataQuality: 'good',
          availableIntervals: ['1m', '5m', '15m', '1h', '4h', '1d'],
          autoUpdate: true,
        },
        {
          symbol: 'SOLUSDT',
          baseAsset: 'SOL',
          quoteAsset: 'USDT',
          price: 98.45,
          priceChange24h: 5.32,
          priceChangePercent24h: 5.71,
          volume24h: 3200000000,
          high24h: 102.0,
          low24h: 93.0,
          isFavorite: false,
          hasData: true,
          lastUpdateTime: '2024-01-15 14:25:00',
          dataQuality: 'warning',
          availableIntervals: ['5m', '15m', '1h', '4h', '1d'],
          autoUpdate: false,
        },
        {
          symbol: 'BNBUSDT',
          baseAsset: 'BNB',
          quoteAsset: 'USDT',
          price: 312.56,
          priceChange24h: 2.1,
          priceChangePercent24h: 0.68,
          volume24h: 890000000,
          high24h: 318.0,
          low24h: 308.0,
          isFavorite: false,
          hasData: false,
          dataQuality: 'unknown',
          availableIntervals: [],
          autoUpdate: false,
        },
        {
          symbol: 'ADAUSDT',
          baseAsset: 'ADA',
          quoteAsset: 'USDT',
          price: 0.5234,
          priceChange24h: -0.012,
          priceChangePercent24h: -2.24,
          volume24h: 450000000,
          high24h: 0.54,
          low24h: 0.51,
          isFavorite: false,
          hasData: true,
          lastUpdateTime: '2024-01-15 14:20:00',
          dataQuality: 'bad',
          availableIntervals: ['1h', '4h', '1d'],
          autoUpdate: false,
        },
      ];

      setSymbols(mockSymbols);
      setFilteredSymbols(mockSymbols);
    } catch (error) {
      message.error('获取货币对列表失败');
      console.error('获取货币对列表失败:', error);
    } finally {
      setSymbolLoading(false);
    }
  };

  // 切换自选状态
  const toggleFavorite = (symbol: string) => {
    setSymbols((prev) =>
      prev.map((s) => (s.symbol === symbol ? { ...s, isFavorite: !s.isFavorite } : s))
    );
    message.success('自选状态已更新');
  };

  // 切换自动更新
  const toggleAutoUpdate = (symbol: string) => {
    setSymbols((prev) =>
      prev.map((s) => (s.symbol === symbol ? { ...s, autoUpdate: !s.autoUpdate } : s))
    );
    message.success('自动更新设置已更新');
  };

  // 获取采集任务列表
  const fetchCollectionTasks = async () => {
    try {
      const params = {
        page: 1,
        page_size: 10,
        sort_by: 'created_at',
        sort_order: 'desc',
        task_type: 'download_crypto',
      };
      const response = await dataApi.getTasks(params);
      const taskList: Task[] = Array.isArray(response.tasks) ? response.tasks : [];
      setCollectionTasks(taskList);
    } catch (error) {
      console.error('获取任务列表失败:', error);
    }
  };

  // 开始数据采集
  const startCollection = async (symbol: string) => {
    try {
      const endDate = dayjs();
      const startDate = dayjs().subtract(1, 'month');

      const response = await dataApi.downloadCryptoData({
        symbols: [symbol],
        interval: ['15m', '1h', '1d'],
        start: startDate.format('YYYY-MM-DD'),
        end: endDate.format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: 1,
        candle_type: SYSTEM_CONFIG.crypto_trading_mode,
      });

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        setTaskStatus('running');
        setTaskProgress(0);
        wsService.subscribe(['task:progress', 'task:status']);
        fetchCollectionTasks();
        message.success(`已开始采集 ${symbol} 数据`);
      }
    } catch (error) {
      message.error('启动采集任务失败');
      console.error('启动采集任务失败:', error);
    }
  };

  // 批量采集
  const handleBatchCollection = async () => {
    try {
      const values = await collectionForm.validateFields();
      const symbols = values.symbols || [];

      if (symbols.length === 0) {
        message.warning('请至少选择一个货币对');
        return;
      }

      const response = await dataApi.downloadCryptoData({
        symbols: symbols,
        interval: values.intervals || ['15m'],
        start: values.dateRange?.[0]?.format('YYYY-MM-DD') || dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
        end: values.dateRange?.[1]?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: 2,
        candle_type: SYSTEM_CONFIG.crypto_trading_mode,
      });

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        setTaskStatus('running');
        setTaskProgress(0);
        wsService.subscribe(['task:progress', 'task:status']);
        fetchCollectionTasks();
        message.success('批量采集任务已启动');
      }
    } catch (error) {
      message.error('启动批量采集失败');
      console.error('启动批量采集失败:', error);
    }
  };

  // 检查数据质量
  const checkQuality = async (symbol: string, interval: string) => {
    try {
      setQualityLoading(true);
      setSelectedSymbolForQuality(symbol);
      setSelectedIntervalForQuality(interval);

      const response = await dataApi.checkKlineQuality({
        symbol,
        interval,
      });

      setQualityDetail(response);
      setActiveTab('quality');
      message.success('数据质量检查完成');
    } catch (error) {
      message.error('数据质量检查失败');
      console.error('数据质量检查失败:', error);
    } finally {
      setQualityLoading(false);
    }
  };

  // 获取质量状态标签
  const getQualityTag = (quality?: string) => {
    switch (quality) {
      case 'good':
        return <Tag icon={<CheckCircleOutlined />} color="success">良好</Tag>;
      case 'warning':
        return <Tag icon={<ExclamationCircleOutlined />} color="warning">警告</Tag>;
      case 'bad':
        return <Tag icon={<CloseCircleOutlined />} color="error">异常</Tag>;
      default:
        return <Tag>未检测</Tag>;
    }
  };

  // 获取价格变化颜色
  const getPriceChangeColor = (change: number) => {
    return change >= 0 ? '#52c41a' : '#ff4d4f';
  };

  // 货币对列表列定义
  const symbolColumns = [
    {
      title: '自选',
      key: 'favorite',
      width: 80,
      render: (_: any, record: SymbolData) => (
        <Button
          type="text"
          icon={record.isFavorite ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
          onClick={() => toggleFavorite(record.symbol)}
        />
      ),
    },
    {
      title: '货币对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (text: string, record: SymbolData) => (
        <Space>
          <Text strong>{text}</Text>
          {record.hasData && <Badge status="success" />}
        </Space>
      ),
    },
    {
      title: '最新价格',
      dataIndex: 'price',
      key: 'price',
      align: 'right' as const,
      render: (price: number) => <Text strong>${price.toLocaleString()}</Text>,
    },
    {
      title: '24h涨跌',
      key: 'change',
      align: 'right' as const,
      render: (_: any, record: SymbolData) => (
        <Text style={{ color: getPriceChangeColor(record.priceChangePercent24h) }}>
          {record.priceChangePercent24h >= 0 ? '+' : ''}
          {record.priceChangePercent24h.toFixed(2)}%
        </Text>
      ),
    },
    {
      title: '24h成交量',
      dataIndex: 'volume24h',
      key: 'volume24h',
      align: 'right' as const,
      render: (volume: number) => `$${(volume / 1000000000).toFixed(2)}B`,
    },
    {
      title: '数据状态',
      key: 'dataStatus',
      render: (_: any, record: SymbolData) => (
        <Space>
          {record.hasData ? (
            <>
              {getQualityTag(record.dataQuality)}
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.lastUpdateTime}
              </Text>
            </>
          ) : (
            <Tag>无数据</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '自动更新',
      key: 'autoUpdate',
      width: 100,
      render: (_: any, record: SymbolData) => (
        <Switch
          size="small"
          checked={record.autoUpdate}
          onChange={() => toggleAutoUpdate(record.symbol)}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_: any, record: SymbolData) => (
        <Space>
          {!record.hasData && (
            <Button
              type="primary"
              size="small"
              icon={<CloudDownloadOutlined />}
              onClick={() => startCollection(record.symbol)}
            >
              采集
            </Button>
          )}
          {record.hasData && (
            <>
              <Button
                size="small"
                icon={<BarChartOutlined />}
                onClick={() => checkQuality(record.symbol, '1h')}
              >
                质量
              </Button>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => startCollection(record.symbol)}
              >
                更新
              </Button>
            </>
          )}
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => {
              setSelectedSymbolForQuality(record.symbol);
              setActiveTab('quality');
            }}
          >
            详情
          </Button>
        </Space>
      ),
    },
  ];

  // 渲染货币对列表
  const renderSymbolList = () => (
    <Card>
      {/* 筛选栏 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Input
            placeholder="搜索货币对"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
          />
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Select
            placeholder="计价货币"
            value={quoteFilter}
            onChange={setQuoteFilter}
            style={{ width: '100%' }}
            options={[
              { value: 'all', label: '全部' },
              { value: 'USDT', label: 'USDT' },
              { value: 'BTC', label: 'BTC' },
              { value: 'ETH', label: 'ETH' },
              { value: 'BUSD', label: 'BUSD' },
            ]}
          />
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Button
            type={showFavoritesOnly ? 'primary' : 'default'}
            icon={<StarFilled />}
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
          >
            只看自选
          </Button>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6} style={{ textAlign: 'right' }}>
          <Space>
            <Text type="secondary">共 {filteredSymbols.length} 个</Text>
            <Button icon={<ReloadOutlined />} onClick={fetchSymbols} loading={symbolLoading}>
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="总货币对"
              value={symbols.length}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="我的自选"
              value={symbols.filter((s) => s.isFavorite).length}
              prefix={<StarFilled style={{ color: '#faad14' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="有数据"
              value={symbols.filter((s) => s.hasData).length}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="自动更新"
              value={symbols.filter((s) => s.autoUpdate).length}
              prefix={<ReloadOutlined style={{ color: '#1890ff' }} />}
            />
          </Card>
        </Col>
      </Row>

      {/* 货币对表格 */}
      <Table
        columns={symbolColumns}
        dataSource={filteredSymbols}
        rowKey="symbol"
        loading={symbolLoading}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        scroll={{ x: 1200 }}
      />
    </Card>
  );

  // 渲染数据采集
  const renderCollection = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <Card title="批量数据采集">
          <Form
            form={collectionForm}
            layout="vertical"
            initialValues={{
              dateRange: [dayjs().subtract(1, 'month'), dayjs()],
              intervals: ['15m'],
            }}
          >
            <Form.Item
              name="symbols"
              label="选择货币对"
              rules={[{ required: true, message: '请至少选择一个货币对' }]}
            >
              <Select
                mode="multiple"
                placeholder="请选择货币对"
                showSearch
                options={symbols.map((s) => ({
                  value: s.symbol,
                  label: `${s.symbol} (${s.isFavorite ? '自选' : '未自选'})`,
                }))}
                filterOption={(input, option) =>
                  (option?.label || '').toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>

            <Form.Item
              name="intervals"
              label="时间周期"
              rules={[{ required: true, message: '请至少选择一个时间周期' }]}
            >
              <Select
                mode="multiple"
                placeholder="选择时间周期"
                options={[
                  { value: '1m', label: '1分钟' },
                  { value: '5m', label: '5分钟' },
                  { value: '15m', label: '15分钟' },
                  { value: '30m', label: '30分钟' },
                  { value: '1h', label: '1小时' },
                  { value: '4h', label: '4小时' },
                  { value: '1d', label: '1天' },
                ]}
              />
            </Form.Item>

            <Form.Item
              name="dateRange"
              label="时间范围"
              rules={[{ required: true, message: '请选择时间范围' }]}
            >
              <RangePicker style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={handleBatchCollection}
                block
              >
                开始批量采集
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card title="采集任务">
          {currentTaskId && (
            <Card size="small" style={{ marginBottom: 16 }} title="当前任务">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row justify="space-between">
                  <Text type="secondary">任务ID:</Text>
                  <Text copyable>{currentTaskId}</Text>
                </Row>
                <Row justify="space-between">
                  <Text type="secondary">状态:</Text>
                  <Tag
                    color={
                      taskStatus === 'running'
                        ? 'processing'
                        : taskStatus === 'completed'
                        ? 'success'
                        : taskStatus === 'failed'
                        ? 'error'
                        : 'default'
                    }
                  >
                    {taskStatus === 'running'
                      ? '运行中'
                      : taskStatus === 'completed'
                      ? '已完成'
                      : taskStatus === 'failed'
                      ? '失败'
                      : '等待中'}
                  </Tag>
                </Row>
                <Progress percent={taskProgress} status={taskStatus === 'running' ? 'active' : 'normal'} />
              </Space>
            </Card>
          )}

          <div style={{ maxHeight: 400, overflow: 'auto' }}>
            {collectionTasks.length === 0 ? (
              <Empty description="暂无采集任务" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {collectionTasks.map((task) => (
                  <Card key={task.task_id} size="small">
                    <Row justify="space-between" align="middle">
                      <Space direction="vertical" size={0}>
                        <Text strong>{task.task_id}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {task.created_at ? dayjs(task.created_at).format('YYYY-MM-DD HH:mm') : '-'}
                        </Text>
                      </Space>
                      <Tag
                        color={
                          task.status === 'running'
                            ? 'processing'
                            : task.status === 'completed'
                            ? 'success'
                            : task.status === 'failed'
                            ? 'error'
                            : 'default'
                        }
                      >
                        {task.status === 'running'
                          ? '运行中'
                          : task.status === 'completed'
                          ? '已完成'
                          : task.status === 'failed'
                          ? '失败'
                          : '等待中'}
                      </Tag>
                    </Row>
                    <Progress
                      percent={task.progress?.percentage || 0}
                      size="small"
                      style={{ marginTop: 8 }}
                    />
                  </Card>
                ))}
              </Space>
            )}
          </div>
        </Card>
      </Col>
    </Row>
  );

  // 渲染数据质量
  const renderQuality = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card title="质量概览">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic
                  title="已检测"
                  value={symbols.filter((s) => s.dataQuality !== 'unknown').length}
                  suffix={`/ ${symbols.length}`}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="良好"
                  value={symbols.filter((s) => s.dataQuality === 'good').length}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="警告"
                  value={symbols.filter((s) => s.dataQuality === 'warning').length}
                  valueStyle={{ color: '#faad14' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="异常"
                  value={symbols.filter((s) => s.dataQuality === 'bad').length}
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Col>
            </Row>

            <Divider />

            <div>
              <Text strong>快速检测</Text>
              <Select
                placeholder="选择货币对"
                style={{ width: '100%', marginTop: 8 }}
                value={selectedSymbolForQuality || undefined}
                onChange={(value) => setSelectedSymbolForQuality(value)}
                options={symbols
                  .filter((s) => s.hasData)
                  .map((s) => ({ value: s.symbol, label: s.symbol }))}
              />
              <Select
                placeholder="选择周期"
                style={{ width: '100%', marginTop: 8 }}
                value={selectedIntervalForQuality || undefined}
                onChange={(value) => setSelectedIntervalForQuality(value)}
                options={[
                  { value: '1m', label: '1分钟' },
                  { value: '5m', label: '5分钟' },
                  { value: '15m', label: '15分钟' },
                  { value: '1h', label: '1小时' },
                  { value: '4h', label: '4小时' },
                  { value: '1d', label: '1天' },
                ]}
              />
              <Button
                type="primary"
                icon={<BarChartOutlined />}
                style={{ width: '100%', marginTop: 8 }}
                loading={qualityLoading}
                disabled={!selectedSymbolForQuality || !selectedIntervalForQuality}
                onClick={() =>
                  checkQuality(selectedSymbolForQuality, selectedIntervalForQuality)
                }
              >
                开始检测
              </Button>
            </div>
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={16}>
        <Card title="检测结果" loading={qualityLoading}>
          {qualityDetail ? (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={[16, 16]}>
                <Col span={8}>
                  <Card size="small">
                    <Statistic
                      title="总体状态"
                      value={qualityDetail.overall_status === 'pass' ? '通过' : '失败'}
                      valueStyle={{
                        color: qualityDetail.overall_status === 'pass' ? '#52c41a' : '#ff4d4f',
                      }}
                    />
                  </Card>
                </Col>
                <Col span={8}>
                  <Card size="small">
                    <Statistic title="总记录数" value={qualityDetail.total_records} />
                  </Card>
                </Col>
                <Col span={8}>
                  <Card size="small">
                    <Statistic
                      title="质量评分"
                      value={(() => {
                        const checks = Object.values(qualityDetail.checks || {});
                        const passed = checks.filter((c: any) => c.status === 'pass').length;
                        return checks.length > 0 ? Math.round((passed / checks.length) * 100) : 0;
                      })()}
                      suffix="分"
                    />
                  </Card>
                </Col>
              </Row>

              {qualityDetail.checks && (
                <Tabs type="card" size="small">
                  <TabPane tab="连续性" key="continuity">
                    <Space direction="vertical">
                      <Text>状态: {qualityDetail.checks.continuity?.status === 'pass' ? '通过' : '失败'}</Text>
                      <Text>预期记录: {qualityDetail.checks.continuity?.expected_records}</Text>
                      <Text>实际记录: {qualityDetail.checks.continuity?.actual_records}</Text>
                      <Text>缺失记录: {qualityDetail.checks.continuity?.missing_records}</Text>
                      <Text>
                        覆盖率:{' '}
                        {Math.round((qualityDetail.checks.continuity?.coverage_ratio || 0) * 100)}%
                      </Text>
                    </Space>
                  </TabPane>
                  <TabPane tab="完整性" key="integrity">
                    <Space direction="vertical">
                      <Text>状态: {qualityDetail.checks.integrity?.status === 'pass' ? '通过' : '失败'}</Text>
                      <Text>总记录: {qualityDetail.checks.integrity?.total_records}</Text>
                    </Space>
                  </TabPane>
                  <TabPane tab="唯一性" key="uniqueness">
                    <Space direction="vertical">
                      <Text>状态: {qualityDetail.checks.uniqueness?.status === 'pass' ? '通过' : '失败'}</Text>
                      <Text>重复记录: {qualityDetail.checks.uniqueness?.duplicate_records}</Text>
                    </Space>
                  </TabPane>
                </Tabs>
              )}
            </Space>
          ) : (
            <Empty description="请选择货币对并点击检测按钮" />
          )}
        </Card>
      </Col>
    </Row>
  );

  return (
    <PageContainer title={t('data_management') || '数据管理'}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        items={[
          {
            key: 'symbols',
            label: (
              <span>
                <DatabaseOutlined /> 货币对
              </span>
            ),
            children: renderSymbolList(),
          },
          {
            key: 'collection',
            label: (
              <span>
                <CloudDownloadOutlined /> 数据采集
              </span>
            ),
            children: renderCollection(),
          },
          {
            key: 'quality',
            label: (
              <span>
                <BarChartOutlined /> 数据质量
              </span>
            ),
            children: renderQuality(),
          },
        ]}
      />
    </PageContainer>
  );
};

export default DataManagementPage;
