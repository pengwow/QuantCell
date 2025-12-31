/**
 * 数据管理页面组件
 * 功能：展示和管理加密货币与股票数据
 */
import { useState, useEffect, useRef } from 'react';
import { useDataManagementStore } from '../store';
import { dataApi, configApi } from '../api';
import { init, dispose } from 'klinecharts';
import AssetPoolManager from '../components/AssetPoolManager';
import '../styles/DataManagement.css';
import dayjs from 'dayjs';

import {
  Layout,
  Menu,
  Table,
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Upload,
  message,
  Spin,
  Empty,
  Progress,
  Card,
  Space,
  Typography,
  DatePicker
} from 'antd';
import {
  DatabaseOutlined,
  ImportOutlined,
  ExportOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SettingOutlined,
  PlusOutlined,
  InfoCircleOutlined,
  BarChartOutlined
} from '@ant-design/icons';

const { Sider, Content } = Layout;
const { Text } = Typography;

const DataManagement = () => {
  // 从状态管理中获取数据和操作方法
  const {
    currentTab,
    cryptoData,
    stockData,
    tasks,
    isLoading,
    refreshCryptoData,
    refreshStockData,
    getTasks
  } = useDataManagementStore();

  // 当前选中的标签页
  const [selectedTab, setSelectedTab] = useState(currentTab);
  // 显示成功消息标志
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  // 成功消息内容
  const [successMessage, setSuccessMessage] = useState('');
  // 导入进度
  const [importProgress, setImportProgress] = useState(0);
  // 导入日志
  const [importLog, setImportLog] = useState<string[]>([]);
  // K线数据
  const [klineData, setKlineData] = useState<any[]>([]);
  // K线数据加载状态
  const [isLoadingKline, setIsLoadingKline] = useState(false);
  // K线数据错误信息
  const [klineError, setKlineError] = useState<string | null>(null);
  // 当前K线配置
  const [klineConfig, setKlineConfig] = useState({
    symbol: 'BTCUSDT',
    interval: '15m',
    limit: 500
  });

  // 表单实例 - 始终在组件顶层创建
  const [importForm] = Form.useForm();
  const [collectionForm] = Form.useForm();
  
  // 设置表单默认日期范围
  useEffect(() => {
    if (collectionForm) {
      // 计算当前时间作为结束日期
      const endDate = dayjs();
      // 计算一个月前的时间作为开始日期
      const startDate = dayjs().subtract(1, 'month');
      
      // 设置数据采集表单默认值 - 使用dayjs对象
      collectionForm.setFieldsValue({
        start: startDate,
        end: endDate
      });
    }
  }, [collectionForm]);
  
  // 设置数据导入表单默认值
  useEffect(() => {
    if (importForm) {
      // 计算当前时间作为结束日期
      const endDate = dayjs();
      // 计算一个月前的时间作为开始日期
      const startDate = dayjs().subtract(1, 'month');
      
      // 设置数据导入表单默认值 - 使用YYYY-MM-DD格式字符串
      importForm.setFieldsValue({
        startDate: startDate.format('YYYY-MM-DD'),
        endDate: endDate.format('YYYY-MM-DD')
      });
    }
  }, [importForm]);
  
  // 图表实例
  const chartRef = useRef<any>(null);
  // 图表容器引用
  const chartContainerRef = useRef<HTMLDivElement>(null);
  // 系统配置
  const [systemConfig, setSystemConfig] = useState({
    current_market_type: 'crypto',
    exchange: 'binance',
    crypto_trading_mode: 'spot'
  });
  // 品种选项数据
  const [symbolOptions, setSymbolOptions] = useState<Array<{ value: string; label: string; type: string; symbols?: string[] }>>([]);
  // 品种选项加载状态
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false);

  // 当前任务状态管理
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [taskProgress, setTaskProgress] = useState<number>(0);
  // 任务状态轮询定时器引用
  const taskIntervalRef = useRef<number | null>(null);

  // 菜单项列表
  const menuItems = [
    { id: 'asset-pools', title: '资产池管理', icon: 'icon-asset-pool' },
    { id: 'collection', title: '数据采集', icon: 'icon-collection' },
    { id: 'quality', title: '数据质量', icon: 'icon-quality' },
    { id: 'visualization', title: '数据可视化', icon: 'icon-visualization' },
    
  ];

  // 加载系统配置
  const loadSystemConfig = async () => {
    try {
      const configData = await configApi.getConfig();
      setSystemConfig({
        current_market_type: configData.current_market_type || 'crypto',
        exchange: configData.exchange || 'binance',
        crypto_trading_mode: configData.crypto_trading_mode || 'spot'
      });
    } catch (error) {
      console.error('加载系统配置失败:', error);
      // 使用默认配置
      setSystemConfig({
        current_market_type: 'crypto',
        exchange: 'binance',
        crypto_trading_mode: 'spot'
      });
    }
  };

  // 获取品种选项数据
  const fetchSymbolOptions = async () => {
    try {
      setSymbolOptionsLoading(true);
      console.log('开始获取品种选项数据，系统配置:', systemConfig);
      
      // 调用新API获取品种选项数据，传递系统配置中的类型和交易商
      const response = await dataApi.getCollectionSymbols({
        type: systemConfig.crypto_trading_mode,
        exchange: systemConfig.exchange
      });
      
      // 添加调试日志，打印完整响应数据
      console.log('API响应数据:', response);
      
      // 处理资产池数据，确保response和asset_pools存在
      const assetPoolOptions = [];
      const directSymbolOptions = [];
      
      if (response) {
        // 处理资产池数据
        if (Array.isArray(response.asset_pools)) {
          console.log('资产池数据:', response.asset_pools);
          assetPoolOptions.push(...response.asset_pools.map((pool: any) => ({
            value: `pool_${pool.id}`, // 使用pool_前缀标识资产池
            label: `${pool.name} (资产池)`, // 显示名称后添加类型标识
            type: 'asset_pool',
            symbols: pool.symbols
          })));
        } else {
          console.warn('asset_pools不是数组:', response.asset_pools);
        }
        
        // 处理直接货币对数据
        if (Array.isArray(response.direct_symbols)) {
          console.log('直接货币对数据:', response.direct_symbols);
          directSymbolOptions.push(...response.direct_symbols.map((symbol: string) => ({
            value: symbol, // 直接使用货币对作为值
            label: `${symbol}`, // 显示名称后添加类型标识
            type: 'direct_symbol'
          })));
        } else {
          console.warn('direct_symbols不是数组:', response.direct_symbols);
        }
      } else {
        console.warn('API响应数据格式异常:', response);
      }
      
      // 合并数据，资产池排在顶部
      const mergedOptions = [...assetPoolOptions, ...directSymbolOptions];
      console.log('处理后的选项数据:', mergedOptions);
      setSymbolOptions(mergedOptions);
    } catch (error) {
      console.error('获取品种选项失败:', error);
      message.error('获取品种选项失败');
    } finally {
      setSymbolOptionsLoading(false);
      console.log('获取品种选项结束，加载状态:', symbolOptionsLoading);
    }
  };

  // 组件挂载时获取任务列表和品种选项数据
  useEffect(() => {
    const initialize = async () => {
      await loadSystemConfig();
      await fetchSymbolOptions();
      getTasks();
    };
    initialize();
  }, [getTasks]);

  // 监听系统配置变化，更新品种选项数据（只在具体字段变化时触发）
  useEffect(() => {
    // 只在组件挂载后，系统配置的关键字段变化时才重新获取数据
    // 避免不必要的API请求
  }, [systemConfig.crypto_trading_mode, systemConfig.exchange]);

  // 组件挂载时获取一次任务列表，不再定时刷新
  useEffect(() => {
    // 初始获取任务列表
    getTasks();
  }, [getTasks]);

  // 专门用于轮询当前任务状态的useEffect钩子
  useEffect(() => {
    // 只有当currentTaskId存在时才设置轮询
    if (currentTaskId) {
      console.log(`当前任务ID: ${currentTaskId}，设置轮询定时器，每1秒查询一次`);
      
      // 立即查询一次任务状态
      queryTaskStatus();
      
      // 设置轮询定时器，每1秒查询一次
      const intervalId = setInterval(queryTaskStatus, 1000);
      
      // 保存定时器ID，用于清理
      taskIntervalRef.current = intervalId;
      
      // 清理函数
      return () => {
        console.log(`清除轮询定时器，任务ID: ${currentTaskId}`);
        if (intervalId) {
          clearInterval(intervalId);
          taskIntervalRef.current = null;
        }
      };
    } else {
      // 如果currentTaskId不存在，清理轮询定时器
      if (taskIntervalRef.current) {
        console.log('currentTaskId不存在，清除轮询定时器');
        clearInterval(taskIntervalRef.current);
        taskIntervalRef.current = null;
      }
    }
  }, [currentTaskId]);

  /**
   * 格式化大数字
   * @param num 要格式化的数字
   * @returns 格式化后的字符串
   */
  const formatNumber = (num: number): string => {
    if (num >= 1000000000) {
      return (num / 1000000000).toFixed(2) + 'B';
    } else if (num >= 1000000) {
      return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(2) + 'K';
    }
    return num.toString();
  };

  /**
   * 显示操作成功消息
   * @param message 要显示的消息内容
   */
  const showMessage = (message: string): void => {
    setSuccessMessage(message);
    setShowSuccessMessage(true);
    // 3秒后隐藏成功提示
    setTimeout(() => {
      setShowSuccessMessage(false);
    }, 3000);
  };

  /**
   * 开始导入数据
   */
  const startImport = (): void => {
    setImportProgress(0);
    setImportLog(['开始导入数据...']);
    
    // 模拟导入过程
    const interval = setInterval(() => {
      setImportProgress(prev => {
        const newProgress = prev + 10;
        if (newProgress <= 100) {
          setImportLog(prevLog => [...prevLog, `导入进度: ${newProgress}%`]);
        } else {
          clearInterval(interval);
          setImportLog(prevLog => [...prevLog, '数据导入完成！']);
          showMessage('数据导入成功');
        }
        return newProgress;
      });
    }, 500);
  };

  /**
   * 获取K线数据
   */
  const fetchKlineData = async (): Promise<void> => {
    console.log('开始获取K线数据，配置:', klineConfig);
    setIsLoadingKline(true);
    setKlineError(null);
    
    try {
      const data = await dataApi.getKlines(klineConfig);
      console.log('获取K线数据成功，数量:', data.length);
      console.log('数据示例:', data.slice(0, 2));
      
      setKlineData(data);
      
      // 更新图表数据
      if (chartRef.current) {
        console.log('通过API获取数据后更新图表');
        chartRef.current.setDataLoader({
          getBars: ({ callback }: { callback: (data: any[]) => void }) => {
            callback(data);
          }
        });
      }
    } catch (error) {
      console.error('获取K线数据失败:', error);
      setKlineError('获取K线数据失败，请稍后重试');
      // 生成模拟数据作为fallback
      console.log('使用模拟数据作为fallback');
      generateMockKlineData();
    } finally {
      setIsLoadingKline(false);
    }
  };

  /**
   * 初始化和清理图表
   */
  useEffect(() => {
    // 初始化图表
    const initChart = async () => {
      try {
        if (chartContainerRef.current) {
          // 检查容器尺寸
          const container = chartContainerRef.current;
          const rect = container.getBoundingClientRect();
          
          // 确保容器有正确的尺寸
          if (rect.width === 0 || rect.height === 0) {
            console.warn('图表容器尺寸为0，等待容器可见后重试');
            return;
          }
          
          console.log('初始化图表，容器尺寸:', rect.width, 'x', rect.height);
          // 简化图表初始化，使用默认配置
          const chart = init(container);
          
          if (chart) {
            chartRef.current = chart;
            console.log('图表实例创建成功');
            
            // 设置图表信息
            chart.setSymbol({ ticker: klineConfig.symbol });
            chart.setPeriod({ span: parseInt(klineConfig.interval.replace('m', '')), type: 'minute' });
            
            // 添加默认指标
            chart.createIndicator('MA');
            
            // 设置数据加载器
            chart.setDataLoader({
              getBars: async (params) => {
                try {
                  console.log('获取K线数据，参数:', params.type, params.timestamp);
                  if (klineData.length > 0) {
                    console.log('使用已有的K线数据，数量:', klineData.length);
                    params.callback(klineData);
                  } else {
                    // 如果没有数据，尝试获取数据
                    console.log('没有现有数据，调用fetchKlineData');
                    await fetchKlineData();
                    params.callback(klineData);
                  }
                } catch (error) {
                  console.error('获取K线数据失败:', error);
                  params.callback([]);
                }
              }
            });
            
            // 如果已有数据，直接更新图表
            if (klineData.length > 0) {
              console.log('直接设置K线数据，数量:', klineData.length);
              chart.setDataLoader({
                getBars: ({ callback }) => {
                  callback(klineData);
                }
              });
            }
          } else {
            console.error('图表初始化失败，返回null');
          }
        }
      } catch (error) {
        console.error('图表初始化过程中发生错误:', error);
      }
    };
    
    initChart();
    
    // 清理函数
    return () => {
      try {
        if (chartRef.current) {
          console.log('销毁图表实例');
          dispose(chartRef.current);
          chartRef.current = null;
        }
      } catch (error) {
        console.error('销毁图表过程中发生错误:', error);
      }
    };
  }, [klineConfig.symbol, klineConfig.interval, klineData]);

  /**
   * 当K线数据变化时更新图表
   */
  useEffect(() => {
    if (chartRef.current && klineData.length > 0) {
      console.log('K线数据变化，更新图表数据，数量:', klineData.length);
      // 直接更新图表数据
      try {
        // 使用setDataLoader更新数据
        chartRef.current.setDataLoader({
          getBars: ({ callback }: { callback: (data: any[]) => void }) => {
            callback(klineData);
          }
        });
        console.log('图表数据更新成功');
      } catch (error) {
        console.error('更新图表数据失败:', error);
      }
    }
  }, [klineData]);

  /**
   * 查询任务状态
   */
  const queryTaskStatus = async () => {
    if (!currentTaskId) return;
    
    console.log(`开始查询任务状态，任务ID: ${currentTaskId}`);
    
    try {
      // 使用相对路径，通过Vite代理发送请求
      const taskData = await dataApi.getTaskStatus(currentTaskId);
      
      console.log(`任务状态查询结果:`, taskData);
      
      // 确保taskData是对象
      if (typeof taskData !== 'object' || taskData === null) {
        console.error('任务状态查询结果格式异常:', taskData);
        return;
      }
      
      // 更新任务状态
      const newStatus = taskData.status || 'unknown';
      setTaskStatus(newStatus);
      
      // 更新任务进度
      let progressValue = 0;
      if (taskData.progress) {
        if (typeof taskData.progress === 'object') {
          // 如果progress是对象，使用percentage字段
          progressValue = taskData.progress.percentage || 0;
        } else {
          // 否则直接使用progress值
          progressValue = Number(taskData.progress) || 0;
        }
      }
      setTaskProgress(progressValue);
      
      console.log(`任务状态更新: ${newStatus}, 进度: ${progressValue}%`);
      
      // 每次查询任务状态后都刷新任务列表，确保列表始终显示最新状态
      getTasks();
      
      // 如果任务完成、失败、取消或进度达到100%，停止定时查询
      if (newStatus === 'completed' || newStatus === 'failed' || newStatus === 'canceled' || progressValue >= 100) {
        if (taskIntervalRef.current) {
          console.log(`任务${newStatus}，停止轮询`);
          clearInterval(taskIntervalRef.current);
          taskIntervalRef.current = null;
        }
        message.success(`任务${newStatus === 'completed' ? '完成' : newStatus === 'failed' ? '失败' : newStatus === 'canceled' ? '已取消' : '完成'}`);
      }
    } catch (error) {
      console.error('查询任务状态失败:', error);
      // 后端报错，停止轮询
      if (taskIntervalRef.current) {
        console.log('查询任务状态失败，停止轮询');
        clearInterval(taskIntervalRef.current);
        taskIntervalRef.current = null;
      }
      message.error('查询任务状态失败，请检查后端服务是否正常');
    }
  };

  /**
   * 生成模拟K线数据
   */
  const generateMockKlineData = (): void => {
    const mockData: any[] = [];
    let currentPrice = 50000;
    const now = Date.now();
    const intervalMs = 15 * 60 * 1000; // 15分钟
    
    for (let i = 500; i >= 0; i--) {
      const timestamp = now - i * intervalMs;
      const open = currentPrice;
      const change = (Math.random() - 0.5) * 2000;
      const close = open + change;
      const high = Math.max(open, close) + Math.random() * 500;
      const low = Math.min(open, close) - Math.random() * 500;
      const volume = Math.random() * 1000 + 500;
      
      mockData.push({
        timestamp,
        open: parseFloat(open.toFixed(2)),
        high: parseFloat(high.toFixed(2)),
        low: parseFloat(low.toFixed(2)),
        close: parseFloat(close.toFixed(2)),
        volume: parseFloat(volume.toFixed(2))
      });
      
      currentPrice = close;
    }
    
    setKlineData(mockData);
  };

  return (
    <Layout className="data-management-container">
      {/* <Header className="page-header">
        <h2 style={{ margin: 0, color: '#333' }}>数据管理</h2>
      </Header> */}

      <Layout>
        {/* 侧边栏导航 */}
        <Sider width={200} className="data-management-sidebar">
          <Menu
            mode="inline"
            selectedKeys={[selectedTab]}
            style={{ height: '100%', borderRight: 0 }}
            onSelect={({ key }) => setSelectedTab(key)}
            items={menuItems.map(menu => ({
              key: menu.id,
              label: menu.title,
              icon: menu.icon === 'icon-crypto' ? <DatabaseOutlined /> :
                     menu.icon === 'icon-stock' ? <DatabaseOutlined /> :
                     menu.icon === 'icon-import' ? <ImportOutlined /> :
                     menu.icon === 'icon-collection' ? <DownloadOutlined /> :
                     menu.icon === 'icon-quality' ? <InfoCircleOutlined /> :
                     menu.icon === 'icon-visualization' ? <BarChartOutlined /> :
                     menu.icon === 'icon-asset-pool' ? <PlusOutlined /> : <SettingOutlined />
            }))}
          />
        </Sider>

        {/* 主内容区域 */}
        <Content className="data-management-main">
          {/* 加密货币数据 */}
          {selectedTab === 'crypto' && (
            <div className="data-panel">
              <h2>加密货币数据</h2>
              <div className="data-section">
                <Space style={{ marginBottom: 16 }}>
                  <Button type="primary" onClick={refreshCryptoData} icon={<ReloadOutlined />}>
                    刷新数据
                  </Button>
                  <Button icon={<ExportOutlined />}>
                    导出数据
                  </Button>
                </Space>
                
                <Table
                  columns={[
                    { title: '名称', dataIndex: 'name', key: 'name' },
                    { title: '符号', dataIndex: 'symbol', key: 'symbol' },
                    { 
                      title: '当前价格', 
                      dataIndex: 'currentPrice', 
                      key: 'currentPrice',
                      render: (price: number) => `$${price.toLocaleString()}`
                    },
                    { 
                      title: '24h变化', 
                      dataIndex: 'priceChange24h', 
                      key: 'priceChange24h',
                      render: (change: number) => (
                        <span className={change > 0 ? 'price-up' : 'price-down'}>
                          {change > 0 ? '+' : ''}{change.toFixed(2)}%
                        </span>
                      )
                    },
                    { 
                      title: '市值', 
                      dataIndex: 'marketCap', 
                      key: 'marketCap',
                      render: (cap: number) => `$${formatNumber(cap)}`
                    },
                    { 
                      title: '交易量', 
                      dataIndex: 'tradingVolume', 
                      key: 'tradingVolume',
                      render: (volume: number) => `$${formatNumber(volume)}`
                    }
                  ]}
                  dataSource={cryptoData}
                  rowKey="id"
                  bordered
                  pagination={{ pageSize: 10 }}
                  style={{ marginTop: 16 }}
                />
              </div>
            </div>
          )}

          {/* 股票数据 */}
          {selectedTab === 'stock' && (
            <div className="data-panel">
              <h2>股票数据</h2>
              <div className="data-section">
                <Space style={{ marginBottom: 16 }}>
                  <Button type="primary" onClick={refreshStockData} icon={<ReloadOutlined />}>
                    刷新数据
                  </Button>
                  <Button icon={<ExportOutlined />}>
                    导出数据
                  </Button>
                </Space>
                
                <Table
                  columns={[
                    { title: '公司名称', dataIndex: 'companyName', key: 'companyName' },
                    { title: '股票代码', dataIndex: 'symbol', key: 'symbol' },
                    { 
                      title: '当前价格', 
                      dataIndex: 'currentPrice', 
                      key: 'currentPrice',
                      render: (price: number) => `$${price.toFixed(2)}`
                    },
                    { 
                      title: '今日变化', 
                      key: 'priceChange',
                      render: (_, record: any) => (
                        <span className={record.priceChange > 0 ? 'price-up' : 'price-down'}>
                          {record.priceChange > 0 ? '+' : ''}{record.priceChange.toFixed(2)} ({record.priceChangePercent.toFixed(2)}%)
                        </span>
                      )
                    },
                    { 
                      title: '开盘价', 
                      dataIndex: 'openPrice', 
                      key: 'openPrice',
                      render: (price: number) => `$${price.toFixed(2)}`
                    },
                    { 
                      title: '最高价', 
                      dataIndex: 'highPrice', 
                      key: 'highPrice',
                      render: (price: number) => `$${price.toFixed(2)}`
                    },
                    { 
                      title: '最低价', 
                      dataIndex: 'lowPrice', 
                      key: 'lowPrice',
                      render: (price: number) => `$${price.toFixed(2)}`
                    }
                  ]}
                  dataSource={stockData}
                  rowKey="symbol"
                  bordered
                  pagination={{ pageSize: 10 }}
                  style={{ marginTop: 16 }}
                />
              </div>
            </div>
          )}

          {/* 数据导入 */}
          {selectedTab === 'import' && (
            <div className="data-panel">
              <h2>数据导入</h2>
              <div className="data-section">
                <Form
                  form={importForm}
                  layout="vertical"
                  className="import-form"
                >
                  <Space.Compact style={{ width: '100%' }}>
                    <Form.Item
                      name="dataType"
                      label="数据类型"
                      initialValue="crypto"
                      style={{ flex: 1, marginRight: 16 }}
                    >
                      <Select>
                        <Select.Option value="crypto">加密货币</Select.Option>
                        <Select.Option value="stock">股票</Select.Option>
                      </Select>
                    </Form.Item>
                    <Form.Item
                      name="exchange"
                      label="交易所"
                      initialValue="binance"
                      style={{ flex: 1 }}
                    >
                      <Select>
                        <Select.Option value="binance">Binance</Select.Option>
                        <Select.Option value="okx">OKX</Select.Option>
                      </Select>
                    </Form.Item>
                  </Space.Compact>
                  
                  <Space.Compact style={{ width: '100%', marginTop: 16 }}>
                    <Form.Item
                      name="startDate"
                      label="开始日期"
                      style={{ flex: 1, marginRight: 16 }}
                    >
                      <Input type="date" />
                    </Form.Item>
                    <Form.Item
                      name="endDate"
                      label="结束日期"
                      style={{ flex: 1 }}
                    >
                      <Input type="date" />
                    </Form.Item>
                  </Space.Compact>
                  
                  <Space.Compact style={{ width: '100%', marginTop: 16 }}>
                    <Form.Item
                      name="interval"
                      label="时间间隔"
                      initialValue="1d"
                      style={{ flex: 1, marginRight: 16 }}
                    >
                      <Select>
                        <Select.Option value="1d">日线</Select.Option>
                        <Select.Option value="1h">小时线</Select.Option>
                        <Select.Option value="30m">30分钟线</Select.Option>
                        <Select.Option value="15m">15分钟线</Select.Option>
                        <Select.Option value="5m">5分钟线</Select.Option>
                        <Select.Option value="1m">1分钟线</Select.Option>
                      </Select>
                    </Form.Item>
                    <Form.Item
                      name="symbols"
                      label="交易对"
                      style={{ flex: 1 }}
                    >
                      <Input placeholder="如: BTCUSDT,ETHUSDT" />
                    </Form.Item>
                  </Space.Compact>
                  
                  <Form.Item
                    name="fileUpload"
                    label="或上传文件"
                    style={{ marginTop: 16 }}
                  >
                    <Upload multiple>
                      <Button icon={<ImportOutlined />}>选择文件</Button>
                    </Upload>
                  </Form.Item>
                  
                  <div className="data-actions" style={{ marginTop: 24 }}>
                    <Space>
                      <Button type="primary" onClick={startImport} icon={<ImportOutlined />}>
                        开始导入
                      </Button>
                      <Button onClick={() => importForm.resetFields()} icon={<ReloadOutlined />}>
                        重置
                      </Button>
                    </Space>
                  </div>
                </Form>
                
                {importProgress > 0 && (
                  <div style={{ marginTop: 24 }}>
                    <Progress percent={importProgress} status="active" />
                    <Text style={{ display: 'block', textAlign: 'center', marginTop: 8 }}>
                      {importProgress}%
                    </Text>
                  </div>
                )}
                
                {importLog.length > 0 && (
                  <div className="import-log">
                    <h3>导入日志</h3>
                    <div className="log-content">
                      {importLog.map((log, index) => (
                        <div key={index} className="log-item">{log}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 数据采集 */}
          {selectedTab === 'collection' && (
            <div className="data-panel">
              <h2>数据采集</h2>
              <div className="data-section">
                <h3>数据获取</h3>
                <Form
                  form={collectionForm}
                  layout="vertical"
                  className="import-form"
                >
                  {/* 第一行：品种和周期 */}
                  <Space.Compact style={{ width: '100%' }}>
                    <Form.Item
                      name="symbols"
                      label="品种"
                      style={{ flex: 1, marginRight: 16 }}
                    >
                      <Select
                        mode="multiple"
                        options={symbolOptions}
                        loading={symbolOptionsLoading}
                        showSearch
                        placeholder="请选择或搜索品种"
                        onSearch={() => {
                          // 搜索逻辑由 Select 组件的 filterOption 处理
                        }}
                        filterOption={(input, option) => {
                          if (!input) return true;
                          const label = option?.label || '';
                          return label.toLowerCase().includes(input.toLowerCase());
                        }}
                      />
                    </Form.Item>
                    
                    <Form.Item
                      name="interval"
                      label="周期"
                      style={{ flex: 1 }}
                    >
                      <Select mode="multiple">
                        <Select.Option value="1m">1分钟</Select.Option>
                        <Select.Option value="5m">5分钟</Select.Option>
                        <Select.Option value="15m">15分钟</Select.Option>
                        <Select.Option value="30m">30分钟</Select.Option>
                        <Select.Option value="1h">1小时</Select.Option>
                        <Select.Option value="4h">4小时</Select.Option>
                        <Select.Option value="1d">1天</Select.Option>
                      </Select>
                    </Form.Item>
                  </Space.Compact>
                  
                  {/* 第二行：开始时间和结束时间 */}
                  <Space.Compact style={{ width: '100%', marginTop: 16 }}>
                    <Form.Item
                      name="start"
                      label="开始日期"
                      style={{ flex: 1, marginRight: 16 }}
                    >
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                    
                    <Form.Item
                      name="end"
                      label="结束日期"
                      style={{ flex: 1 }}
                    >
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                  </Space.Compact>
                  
                  {/* 操作按钮 */}
                  <div className="data-actions" style={{ marginTop: 24 }}>
                    <Space>
                      <Button 
                        type="primary" 
                        icon={<DownloadOutlined />}
                        onClick={async () => {
                          try {
                            // 获取表单数据
                            const values = await collectionForm.validateFields();
                            const selectedValues = values.symbols || [];
                            
                            // 处理选中的品种，合并资产池和直接货币对
                            const mergedSymbols = new Set<string>();
                            
                            for (const selectedValue of selectedValues) {
                              if (selectedValue.startsWith('pool_')) {
                                // 处理资产池，获取资产池中的所有货币对
                                const poolOption = symbolOptions.find(option => option.value === selectedValue);
                                if (poolOption && poolOption.symbols) {
                                  poolOption.symbols.forEach(symbol => mergedSymbols.add(symbol));
                                }
                              } else {
                                // 直接货币对，直接添加
                                mergedSymbols.add(selectedValue);
                              }
                            }
                            
                            // 调用下载API
                            const response = await dataApi.downloadCryptoData({
                              symbols: Array.from(mergedSymbols),
                              interval: values.interval || ['15m'],
                              start: values.start || '',
                              end: values.end || '',
                              exchange: 'binance',
                              max_workers: 1,
                              candle_type: 'spot'
                            });
                            
                            // 保存返回的task_id
                            if (response.task_id) {
                              const taskId = response.task_id;
                              console.log(`获取到任务ID: ${taskId}，开始设置轮询`);
                               
                              // 设置当前任务ID
                              setCurrentTaskId(taskId);
                              // 初始化任务状态
                              setTaskStatus('running');
                              setTaskProgress(0);
                               
                              // 立即刷新任务列表，确保新创建的任务显示在列表中
                              getTasks();
                               
                              // 开始定时查询任务状态，每1秒查询一次
                              if (taskIntervalRef.current) {
                                console.log('清除旧的轮询定时器');
                                clearInterval(taskIntervalRef.current);
                              }
                               
                              console.log('设置新的轮询定时器，每1秒查询一次');
                              taskIntervalRef.current = setInterval(queryTaskStatus, 1000);
                               
                              // 立即查询一次任务状态
                              console.log('立即查询一次任务状态');
                              await queryTaskStatus();
                               
                              message.success('数据下载任务已启动');
                            } else {
                              console.error('未获取到任务ID，响应数据:', response);
                              message.error('数据下载任务启动失败，未获取到任务ID');
                            }
                          } catch (error) {
                            console.error('下载失败:', error);
                            message.error('下载失败，请检查表单数据');
                          }
                        }}
                      >
                        开始下载
                      </Button>
                      <Button 
                        icon={<ReloadOutlined />}
                        onClick={fetchSymbolOptions}
                      >
                        刷新品种数据
                      </Button>
                    </Space>
                  </div>
                </Form>
              </div>
              
              {/* 任务管理 */}
              <div className="data-section">
                <h3>任务管理</h3>
                
                {/* 当前任务状态 */}
                {currentTaskId && (
                  <Card className="current-task-section" title="当前任务" style={{ marginBottom: 24 }}>
                    <div className="task-info" style={{ marginBottom: 16 }}>
                      <Space.Compact style={{ width: '100%' }}>
                        <div className="task-id" style={{ flex: 1 }}>
                          <Text strong>任务ID:</Text>
                          <Text style={{ marginLeft: 8 }}>{currentTaskId}</Text>
                        </div>
                        <div className="task-status" style={{ flex: 1 }}>
                          <Text strong>状态:</Text>
                          <Text 
                            style={{ 
                              marginLeft: 8, 
                              color: taskStatus === 'running' ? '#1890ff' : 
                              taskStatus === 'completed' ? '#52c41a' : 
                              taskStatus === 'failed' ? '#ff4d4f' : '#666',
                              fontWeight: 500
                            }}
                          >
                            {taskStatus === 'running' ? '运行中' : 
                             taskStatus === 'completed' ? '已完成' : 
                             taskStatus === 'failed' ? '失败' : 
                             taskStatus === 'pending' ? '等待中' : taskStatus}
                          </Text>
                        </div>
                        <div className="polling-status" style={{ flex: 1, textAlign: 'right' }}>
                          <Text strong>轮询状态:</Text>
                          <Text 
                            style={{ 
                              marginLeft: 8, 
                              color: taskIntervalRef.current ? '#52c41a' : '#ff4d4f',
                              fontWeight: 500
                            }}
                          >
                            {taskIntervalRef.current ? '运行中' : '已停止'}
                          </Text>
                        </div>
                      </Space.Compact>
                    </div>
                    
                    {/* 任务进度条 */}
                    <div className="task-progress" style={{ marginBottom: 16 }}>
                      <Progress 
                        percent={taskProgress} 
                        status={
                          taskStatus === 'running' ? 'active' : 
                          taskStatus === 'completed' ? 'success' : 
                          taskStatus === 'failed' ? 'exception' : 'normal'
                        } 
                      />
                      <Text style={{ display: 'block', textAlign: 'center', marginTop: 8 }}>
                        {taskProgress}%
                      </Text>
                    </div>
                  </Card>
                )}
                
                {/* 最近任务列表 */}
                <div className="recent-tasks-section">
                  <h4>最近任务</h4>
                  {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                      <Spin tip="加载中..." />
                    </div>
                  ) : tasks.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                      <Empty description="暂无任务记录" />
                    </div>
                  ) : (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      {tasks.map(task => (
                        <Card key={task.task_id} className="task-card">
                          <div className="task-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <div className="task-id-info">
                              <Text strong>任务ID:</Text>
                              <Text style={{ marginLeft: 8 }}>{task.task_id}</Text>
                            </div>
                            <Text 
                              style={{
                                color: task.status === 'running' ? '#1890ff' : 
                                task.status === 'completed' ? '#52c41a' : 
                                task.status === 'failed' ? '#ff4d4f' : '#666',
                                fontWeight: 500
                              }}
                            >
                              {task.status === 'running' ? '运行中' : 
                               task.status === 'completed' ? '已完成' : 
                               task.status === 'failed' ? '失败' : 
                               task.status === 'pending' ? '等待中' : task.status}
                            </Text>
                          </div>
                          
                          <div className="task-details" style={{ marginBottom: 16 }}>
                            <Space orientation="vertical" style={{ width: '100%' }}>
                              {/* 任务参数信息 */}
                              {task.params && (
                                <Space.Compact style={{ width: '100%' }}>
                                  <div className="param-item" style={{ flex: 1 }}>
                                    <Text strong>品种:</Text>
                                    <Text style={{ marginLeft: 8 }}>
                                      {Array.isArray(task.params.symbols) ? 
                                        (task.params.symbols.length > 3 ? 
                                          `${task.params.symbols.slice(0, 3).join(', ')}...` : 
                                          task.params.symbols.join(', ')) : 
                                        task.params.symbols || '未指定'}
                                    </Text>
                                  </div>
                                  <div className="param-item" style={{ flex: 1 }}>
                                    <Text strong>周期:</Text>
                                    <Text style={{ marginLeft: 8 }}>
                                      {Array.isArray(task.params.interval) ? 
                                        (task.params.interval.length > 2 ? 
                                          `${task.params.interval.slice(0, 2).join(', ')}...` : 
                                          task.params.interval.join(', ')) : 
                                        task.params.interval || '未指定'}
                                    </Text>
                                  </div>
                                </Space.Compact>
                              )}
                              
                              {/* 时间信息 */}
                              <Space.Compact style={{ width: '100%' }}>
                                <div className="time-item" style={{ flex: 1 }}>
                                  <Text strong>创建时间:</Text>
                                  <Text style={{ marginLeft: 8 }}>
                                    {task.created_at ? new Date(task.created_at).toLocaleString() : '未知'}
                                  </Text>
                                </div>
                                {task.completed_at && (
                                  <div className="time-item" style={{ flex: 1 }}>
                                    <Text strong>完成时间:</Text>
                                    <Text style={{ marginLeft: 8 }}>
                                      {new Date(task.completed_at).toLocaleString()}
                                    </Text>
                                  </div>
                                )}
                              </Space.Compact>
                            </Space>
                          </div>
                          
                          {/* 任务进度 */}
                          <div className="task-progress-info">
                            <Space orientation="vertical" style={{ width: '100%' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
                                <Text strong style={{ width: 60 }}>进度:</Text>
                                <Progress 
                                  percent={task.progress?.percentage || 0} 
                                  style={{ flex: 1 }} 
                                  status={
                                    task.status === 'completed' ? 'success' : 
                                    task.status === 'failed' ? 'exception' : 
                                    task.status === 'running' ? 'active' : 'normal'
                                  }
                                />
                                <Text>{task.progress?.percentage || 0}%</Text>
                              </div>
                              
                              {/* 任务类型 */}
                              {task.task_type && (
                                <div className="task-type" style={{ display: 'flex', alignItems: 'center' }}>
                                  <Text strong style={{ width: 60 }}>类型:</Text>
                                  <Text style={{ marginLeft: 8 }}>{task.task_type}</Text>
                                </div>
                              )}
                            </Space>
                          </div>
                        </Card>
                      ))}
                    </Space>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 数据可视化 */}
          {selectedTab === 'visualization' && (
            <div className="data-panel">
              <h2>数据可视化</h2>
              
              {/* K线图表配置 */}
              <div className="data-section">
                <div className="import-form">
                  <Space.Compact style={{ width: '100%' }}>
                    <div style={{ flex: 1, marginRight: 16 }}>
                      <div style={{ marginBottom: 8 }}>交易对</div>
                      <Select
                        value={klineConfig.symbol}
                        onChange={(value) => setKlineConfig(prev => ({ ...prev, symbol: value }))}
                      >
                        <Select.Option value="BTCUSDT">BTCUSDT</Select.Option>
                        <Select.Option value="ETHUSDT">ETHUSDT</Select.Option>
                        <Select.Option value="BNBUSDT">BNBUSDT</Select.Option>
                      </Select>
                    </div>
                    <div style={{ flex: 1, marginRight: 16 }}>
                      <div style={{ marginBottom: 8 }}>时间周期</div>
                      <Select
                        value={klineConfig.interval}
                        onChange={(value) => setKlineConfig(prev => ({ ...prev, interval: value }))}
                      >
                        <Select.Option value="1m">1分钟</Select.Option>
                        <Select.Option value="5m">5分钟</Select.Option>
                        <Select.Option value="15m">15分钟</Select.Option>
                        <Select.Option value="30m">30分钟</Select.Option>
                        <Select.Option value="1h">1小时</Select.Option>
                      </Select>
                    </div>
                    <div style={{ flex: 1, marginRight: 16 }}>
                      <div style={{ marginBottom: 8 }}>数据数量</div>
                      <InputNumber
                        value={klineConfig.limit}
                        min={100}
                        max={2000}
                        step={100}
                        onChange={(value: number | null) => setKlineConfig(prev => ({ ...prev, limit: value || 500 }))}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ marginBottom: 8 }}>操作</div>
                      <Button 
                        type="primary"
                        onClick={fetchKlineData}
                        disabled={isLoadingKline}
                        icon={<ReloadOutlined />}
                        block
                      >
                        {isLoadingKline ? '加载中...' : '获取数据'}
                      </Button>
                    </div>
                  </Space.Compact>
                </div>
              </div>
              
              {/* K线图表 */}
              <div className="data-section">
                <h3>K线图表</h3>
                {klineError && (
                  <div className="error-message">
                    {klineError}
                  </div>
                )}
                <div className="kline-chart-container">
                  {isLoadingKline ? (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '600px' }}>
                      <Spin tip="加载中..." size="large" />
                    </div>
                  ) : (
                    <div className="kline-chart">
                      <div className="chart-header" style={{ marginBottom: 16 }}>
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <div className="chart-title" style={{ fontSize: 18, fontWeight: 'bold' }}>
                            {klineConfig.symbol} {klineConfig.interval} K线图
                          </div>
                          <div className="chart-stats">
                            {klineData.length > 0 && (
                              <Space size={16}>
                                <div className="stat-item">
                                  <Text strong>最新价格: </Text>
                                  <Text>{klineData[klineData.length - 1].close.toLocaleString()}</Text>
                                </div>
                                <div className="stat-item">
                                  <Text strong>交易量: </Text>
                                  <Text>{klineData[klineData.length - 1].volume.toLocaleString()}</Text>
                                </div>
                              </Space>
                            )}
                          </div>
                        </Space>
                      </div>
                      <div className="chart-content">
                        {klineData.length > 0 ? (
                          <div 
                            ref={chartContainerRef}
                            className="kline-chart-wrapper"
                            style={{ width: '100%', height: '500px' }}
                          />
                        ) : (
                          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '500px' }}>
                            <Empty description="暂无数据，请点击'获取数据'按钮加载" />
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 资产池管理 */}
          {selectedTab === 'asset-pools' && (
            <div className="data-panel">
              {/* <h2>资产池管理</h2> */}
              <div className="data-section">
                {/* 资产池管理组件 */}
                <AssetPoolManager />
              </div>
            </div>
          )}

          {/* 操作成功提示 */}
          {showSuccessMessage && (
            <div className="success-message">
              {successMessage}
            </div>
          )}
        </Content>
      </Layout>
    </Layout>
  );
};

export default DataManagement;