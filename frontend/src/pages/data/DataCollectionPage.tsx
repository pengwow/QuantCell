/**
 * 数据采集页面组件
 * 从旧版本迁移过来，包含完整的数据采集功能
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
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
  Empty,
  message
} from 'antd';
import {
  IconDownload,
  IconRefresh
} from '@tabler/icons-react';
import PageContainer from '@/components/PageContainer';
import { dataApi } from '@/api/dataApi';
import { wsService } from '@/services/websocketService';
import type { Task } from '@/types/data';
import { setPageTitle } from '@/router';

const { Text } = Typography;

// 系统配置
const SYSTEM_CONFIG = {
  current_market_type: 'crypto',
  exchange: 'binance',
  crypto_trading_mode: 'spot'
};

const DataCollectionPage = () => {
  const { t } = useTranslation();
  const [collectionForm] = Form.useForm();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('data_collection') || '数据采集');
  }, [t]);

  // 任务状态管理
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [taskProgress, setTaskProgress] = useState<number>(0);

  // 品种选项数据
  const [symbolOptions, setSymbolOptions] = useState<Array<{ value: string; label: string; type: string; symbols?: string[] }>>([]);
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false);

  // 设置表单默认日期范围
  useEffect(() => {
    if (collectionForm) {
      const endDate = dayjs();
      const startDate = dayjs().subtract(1, 'month');
      collectionForm.setFieldsValue({
        start: startDate,
        end: endDate
      });
    }
  }, [collectionForm]);

  // 获取任务列表
  const getTasks = async (showLoading = true) => {
    if (showLoading) {
      setIsLoading(true);
    }
    try {
      const params = {
        page: 1,
        page_size: 5,
        sort_by: 'created_at',
        sort_order: 'desc',
        task_type: 'download_crypto'
      };
      const response = await dataApi.getTasks(params);
      const taskList: Task[] = Array.isArray(response.tasks) ? response.tasks : [];
      setTasks(taskList);
    } catch (error) {
      console.error('获取任务列表失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 获取品种选项数据
  const fetchSymbolOptions = async () => {
    try {
      setSymbolOptionsLoading(true);
      const response = await dataApi.getCollectionSymbols({
        type: SYSTEM_CONFIG.crypto_trading_mode,
        exchange: SYSTEM_CONFIG.exchange
      });

      const dataPoolOptions = [];
      const directSymbolOptions = [];

      if (response) {
        if (Array.isArray(response.data_pools)) {
          dataPoolOptions.push(...response.data_pools.map((pool: any) => ({
            value: `pool_${pool.id}`,
            label: `${pool.name} (数据池)`,
            type: 'data_pool',
            symbols: pool.symbols
          })));
        }

        if (Array.isArray(response.direct_symbols)) {
          directSymbolOptions.push(...response.direct_symbols.map((symbol: string) => ({
            value: symbol,
            label: `${symbol}`,
            type: 'direct_symbol'
          })));
        }
      }

      const mergedOptions = [...dataPoolOptions, ...directSymbolOptions];
      setSymbolOptions(mergedOptions);
    } catch (error) {
      console.error('获取品种选项失败:', error);
      message.error('获取品种选项失败');
    } finally {
      setSymbolOptionsLoading(false);
    }
  };

  // 组件挂载时获取任务列表，并设置WebSocket连接
  useEffect(() => {
    getTasks(true);
    fetchSymbolOptions();

    wsService.connect();

    const handleTaskProgress = (data: any) => {
      if (data.task_id === currentTaskId) {
        setTaskProgress(data.progress.percentage || 0);
      }
    };

    const handleTaskStatus = (data: any) => {
      if (data.task_id === currentTaskId) {
        setTaskStatus(data.status);
        if (data.status === 'completed' || data.status === 'failed') {
          getTasks(false);
        }
      }
    };

    const handleTaskList = () => {
      getTasks(false);
    };

    wsService.on('task:progress', handleTaskProgress);
    wsService.on('task:status', handleTaskStatus);
    wsService.on('task:list', handleTaskList);

    return () => {
      wsService.off('task:progress', handleTaskProgress);
      wsService.off('task:status', handleTaskStatus);
      wsService.off('task:list', handleTaskList);
    };
  }, [currentTaskId]);

  // 开始下载
  const handleDownload = async () => {
    try {
      const values = await collectionForm.validateFields();
      const selectedValues = values.symbols || [];
      const mergedSymbols = new Set<string>();

      for (const selectedValue of selectedValues) {
        if (selectedValue.startsWith('pool_')) {
          const poolOption = symbolOptions.find(option => option.value === selectedValue);
          if (poolOption && poolOption.symbols) {
            poolOption.symbols.forEach(symbol => mergedSymbols.add(symbol));
          }
        } else {
          mergedSymbols.add(selectedValue);
        }
      }

      const response = await dataApi.downloadCryptoData({
        symbols: Array.from(mergedSymbols),
        interval: values.interval || ['15m'],
        start: values.start ? values.start.format('YYYY-MM-DD') : '',
        end: values.end ? values.end.format('YYYY-MM-DD') : '',
        exchange: 'binance',
        max_workers: 1,
        candle_type: 'spot'
      });

      if (response.task_id) {
        const taskId = response.task_id;
        setCurrentTaskId(taskId);
        setTaskStatus('running');
        setTaskProgress(0);

        if (!wsService.getConnected()) {
          wsService.connect();
        }

        wsService.subscribe(['task:progress', 'task:status']);
        getTasks();
        message.success('下载任务已启动');
      }
    } catch (error) {
      console.error('下载失败:', error);
      message.error('下载失败');
    }
  };

  return (
    <PageContainer title={t('data_collection') || '数据采集'}>
      <div className="space-y-6">
        {/* 数据获取配置 */}
        <Card title="数据获取" className="shadow-sm">
          <Form
            form={collectionForm}
            layout="vertical"
          >
            {/* 第一行：品种和周期 */}
            <Space.Compact className="w-full">
              <Form.Item
                name="symbols"
                label="品种"
                className="flex-1 mr-4"
                rules={[{ required: true, message: '请选择品种' }]}
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
                className="flex-1"
                rules={[{ required: true, message: '请选择周期' }]}
              >
                <Select mode="multiple" placeholder="选择周期">
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
            <Space.Compact className="w-full mt-4">
              <Form.Item
                name="start"
                label="开始日期"
                className="flex-1 mr-4"
                rules={[{ required: true, message: '请选择开始日期' }]}
              >
                <DatePicker className="w-full" />
              </Form.Item>

              <Form.Item
                name="end"
                label="结束日期"
                className="flex-1"
                rules={[{ required: true, message: '请选择结束日期' }]}
              >
                <DatePicker className="w-full" />
              </Form.Item>
            </Space.Compact>

            {/* 操作按钮 */}
            <div className="mt-6">
              <Space>
                <Button
                  type="primary"
                  icon={<IconDownload size={16} />}
                  onClick={handleDownload}
                >
                  开始下载
                </Button>
                <Button
                  icon={<IconRefresh size={16} />}
                  onClick={fetchSymbolOptions}
                  loading={symbolOptionsLoading}
                >
                  刷新品种数据
                </Button>
              </Space>
            </div>
          </Form>
        </Card>

        {/* 任务管理 */}
        <Card title="任务管理" className="shadow-sm">
          {/* 当前任务状态 */}
          {currentTaskId && (
            <Card className="mb-6" title="当前任务" size="small">
              <div className="mb-4">
                <Space className="w-full">
                  <div className="flex-[2]">
                    <Text strong>任务ID:</Text>
                    <Text className="ml-2">{currentTaskId}</Text>
                  </div>
                  <div className="flex-1 text-right">
                    <Text strong>状态:</Text>
                    <Text
                      className="ml-2 font-medium"
                      style={{
                        color: taskStatus === 'running' ? '#1890ff' :
                          taskStatus === 'completed' ? '#52c41a' :
                            taskStatus === 'failed' ? '#ff4d4f' : '#666'
                      }}
                    >
                      {taskStatus === 'running' ? '运行中' :
                        taskStatus === 'completed' ? '已完成' :
                          taskStatus === 'failed' ? '失败' :
                            taskStatus === 'pending' ? '等待中' : taskStatus}
                    </Text>
                  </div>
                </Space>
              </div>

              <div className="mb-4">
                <Progress
                  percent={taskProgress}
                  status={
                    taskStatus === 'running' ? 'active' :
                      taskStatus === 'completed' ? 'success' :
                        taskStatus === 'failed' ? 'exception' : 'normal'
                  }
                />
                <Text className="block text-center mt-2">{taskProgress}%</Text>
              </div>
            </Card>
          )}

          {/* 最近任务列表 */}
          <div>
            <h4 className="mb-4 font-medium">最近任务</h4>
            {isLoading ? (
              <div className="text-center py-10">
                <Spin size="large" />
              </div>
            ) : tasks.length === 0 ? (
              <div className="text-center py-10">
                <Empty description="暂无任务记录" />
              </div>
            ) : (
              <Space direction="vertical" className="w-full">
                {tasks.map(task => (
                  <Card key={task.task_id} className="w-full" size="small">
                    <div className="flex justify-between items-center mb-4">
                      <div>
                        <Text strong>任务ID:</Text>
                        <Text className="ml-2">{task.task_id}</Text>
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

                    <div className="mb-4">
                      <Space direction="vertical" className="w-full">
                        {task.params && (
                          <Space className="w-full">
                            <div className="flex-1">
                              <Text strong>品种:</Text>
                              <Text className="ml-2">
                                {Array.isArray(task.params.symbols) ?
                                  (task.params.symbols.length > 3 ?
                                    `${task.params.symbols.slice(0, 3).join(', ')}...` :
                                    task.params.symbols.join(', ')) :
                                  task.params.symbols || '未指定'}
                              </Text>
                            </div>
                            <div className="flex-1">
                              <Text strong>周期:</Text>
                              <Text className="ml-2">
                                {Array.isArray(task.params.interval) ?
                                  (task.params.interval.length > 2 ?
                                    `${task.params.interval.slice(0, 2).join(', ')}...` :
                                    task.params.interval.join(', ')) :
                                  task.params.interval || '未指定'}
                              </Text>
                            </div>
                          </Space>
                        )}

                        <Space className="w-full">
                          <div className="flex-1">
                            <Text strong>创建时间:</Text>
                            <Text className="ml-2">
                              {task.created_at ? new Date(task.created_at).toLocaleString() : '未知'}
                            </Text>
                          </div>
                          {task.completed_at && (
                            <div className="flex-1">
                              <Text strong>完成时间:</Text>
                              <Text className="ml-2">
                                {new Date(task.completed_at).toLocaleString()}
                              </Text>
                            </div>
                          )}
                        </Space>
                      </Space>
                    </div>

                    <div>
                      <Space direction="vertical" className="w-full">
                        <div className="flex items-center gap-4 mb-2">
                          <Text strong className="w-16">进度:</Text>
                          <Progress
                            percent={task.progress?.percentage || 0}
                            className="flex-1"
                            status={
                              task.status === 'completed' ? 'success' :
                                task.status === 'failed' ? 'exception' :
                                  task.status === 'running' ? 'active' : 'normal'
                            }
                            format={percent => `${percent}%`}
                          />
                        </div>

                        {task.task_type && (
                          <div className="flex items-center">
                            <Text strong className="w-16">类型:</Text>
                            <Text className="ml-2">{task.task_type}</Text>
                          </div>
                        )}
                      </Space>
                    </div>
                  </Card>
                ))}
              </Space>
            )}
          </div>
        </Card>
      </div>
    </PageContainer>
  );
};

export default DataCollectionPage;
