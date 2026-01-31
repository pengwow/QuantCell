/**
 * 数据采集页面组件
 */
import { useState, useEffect } from 'react';
import { useDataManagementStore } from '../../store';
import { dataApi } from '../../api';
import dayjs from 'dayjs';
import { wsService } from '../../services/websocketService';
import {
  Form,
  Select,
  Button,
  Space,
  Typography,
  DatePicker,
  Card,
  Progress,
  Spin,
  Empty
} from 'antd';
import {
  DownloadOutlined,
  ReloadOutlined
} from '@ant-design/icons';

const { Text } = Typography;

const DataCollectionPage = () => {
  // 从状态管理中获取数据和操作方法
  const {
    tasks,
    isLoading,
    getTasks
  } = useDataManagementStore();

  // 表单实例
  const [collectionForm] = Form.useForm();
  
  // 当前任务状态管理
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [taskProgress, setTaskProgress] = useState<number>(0);


  // 系统配置
  const [systemConfig] = useState({
    current_market_type: 'crypto',
    exchange: 'binance',
    crypto_trading_mode: 'spot'
  });
  // 品种选项数据
  const [symbolOptions, setSymbolOptions] = useState<Array<{ value: string; label: string; type: string; symbols?: string[] }>>([]);
  // 品种选项加载状态
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false);

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

  // 获取品种选项数据
  const fetchSymbolOptions = async () => {
    try {
      setSymbolOptionsLoading(true);
      
      // 调用API获取品种选项数据
      const response = await dataApi.getCollectionSymbols({
        type: systemConfig.crypto_trading_mode,
        exchange: systemConfig.exchange
      });
      
      // 处理数据池数据，确保response和data_pools存在
      const dataPoolOptions = [];
      const directSymbolOptions = [];
      
      if (response) {
        // 处理数据池数据
        if (Array.isArray(response.data_pools)) {
          console.log('数据池数据:', response.data_pools);
          dataPoolOptions.push(...response.data_pools.map((pool: any) => ({
            value: `pool_${pool.id}`, // 使用pool_前缀标识数据池
            label: `${pool.name} (数据池)`, // 显示名称后添加类型标识
            type: 'data_pool',
            symbols: pool.symbols
          })));
        } else {
          console.warn('data_pools不是数组:', response.data_pools);
        }
        
        // 处理直接货币对数据
        if (Array.isArray(response.direct_symbols)) {
          directSymbolOptions.push(...response.direct_symbols.map((symbol: string) => ({
            value: symbol, // 直接使用货币对作为值
            label: `${symbol}`, // 显示名称后添加类型标识
            type: 'direct_symbol'
          })));
        }
      }
      
      // 合并数据，数据池排在顶部
      const mergedOptions = [...dataPoolOptions, ...directSymbolOptions];
      setSymbolOptions(mergedOptions);
    } catch (error) {
      console.error('获取品种选项失败:', error);
    } finally {
      setSymbolOptionsLoading(false);
    }
  };

  // 组件挂载时获取一次任务列表，并设置WebSocket连接
  useEffect(() => {
    // 初始获取任务列表，显示加载状态
    getTasks(true);
    fetchSymbolOptions();
    
    // 初始化WebSocket连接
    wsService.connect();
    
    // 添加WebSocket监听器
    const handleTaskProgress = (data: any) => {
      if (data.task_id === currentTaskId) {
        setTaskProgress(data.progress.percentage || 0);
      }
    };
    
    const handleTaskStatus = (data: any) => {
      if (data.task_id === currentTaskId) {
        setTaskStatus(data.status);
        // 如果任务完成或失败，更新任务列表
        if (data.status === 'completed' || data.status === 'failed') {
          getTasks(false);
        }
      }
    };
    
    const handleTaskList = (_data: any) => {
      getTasks(false);
    };
    
    // 注册监听器
    wsService.on('task:progress', handleTaskProgress);
    wsService.on('task:status', handleTaskStatus);
    wsService.on('task:list', handleTaskList);
    
    // 清理函数
    return () => {
      // 移除监听器
      wsService.off('task:progress', handleTaskProgress);
      wsService.off('task:status', handleTaskStatus);
      wsService.off('task:list', handleTaskList);
    };
  }, [getTasks, currentTaskId]);



  return (
    <>
      <h2>数据采集</h2>
      <div className="data-section">
        <div style={{ marginBottom: 16 }}>
          <h3>数据获取</h3>
        </div>
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
                          // 处理数据池，获取数据池中的所有货币对
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
                         
                        // 设置当前任务ID
                        setCurrentTaskId(taskId);
                        // 初始化任务状态
                        setTaskStatus('running');
                        setTaskProgress(0);
                        
                        // 确保WebSocket连接已建立
                        if (!wsService.getConnected()) {
                          wsService.connect();
                        }
                        
                        // 订阅任务相关主题
                        wsService.subscribe(['task:progress', 'task:status']);
                         
                        // 立即刷新任务列表，确保新创建的任务显示在列表中
                        getTasks();
                      }
                    } catch (error) {
                      console.error('下载失败:', error);
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
                  <div className="task-id" style={{ flex: 2 }}>
                    <Text strong>任务ID:</Text>
                    <Text style={{ marginLeft: 8 }}>{currentTaskId}</Text>
                  </div>
                  <div className="task-status" style={{ flex: 1, textAlign: 'right' }}>
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
                <Spin size="large" />
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
                            format={percent => `${percent}%`}
                          />
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
    </>
  );
};

export default DataCollectionPage;