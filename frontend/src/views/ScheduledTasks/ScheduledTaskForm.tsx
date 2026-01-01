import React, { useState, useEffect } from 'react';
import { Card, Form, Input, Select, Switch, Button, Space, message, InputNumber } from 'antd';
import { LeftOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import dayjs from 'dayjs';

// 导入API服务
import { scheduledTaskApi } from '../../api';



// 表单类型定义
interface ScheduledTaskFormData {
  name: string;
  description?: string;
  task_type: string;
  status?: string;
  cron_expression?: string;
  interval?: string;
  start_time?: string;
  end_time?: string;
  frequency_type: string;
  symbols?: string[];
  exchange?: string;
  candle_type: string;
  save_dir?: string;
  max_workers: number;
  incremental_enabled: boolean;
  notification_enabled: boolean;
  notification_type?: string;
  notification_email?: string;
  notification_webhook?: string;
}

/**
 * 定时任务表单组件
 * 功能：用于创建和编辑定时任务
 */
const ScheduledTaskForm: React.FC = () => {
  const navigate = useNavigate();
  const params = useParams<{ id: string }>();
  const [form] = Form.useForm<ScheduledTaskFormData>();
  const [loading, setLoading] = useState<boolean>(false);
  const [isEdit, setIsEdit] = useState<boolean>(false);

  // 任务类型选项
  const taskTypeOptions = [
    { label: '加密货币数据下载', value: 'download_crypto' },
  ];

  // 频率类型选项
  const frequencyTypeOptions = [
    { label: '按小时', value: 'hourly' },
    { label: '按天', value: 'daily' },
    { label: '按周', value: 'weekly' },
    { label: '按月', value: 'monthly' },
    { label: 'CRON表达式', value: 'cron' },
    { label: '时间间隔', value: 'interval' },
    { label: '单次执行', value: 'date' },
  ];

  // 通知类型选项
  const notificationTypeOptions = [
    { label: '邮件', value: 'email' },
    { label: 'Webhook', value: 'webhook' },
  ];

  // 蜡烛图类型选项
  const candleTypeOptions = [
    { label: '现货', value: 'spot' },
    { label: '期货', value: 'futures' },
    { label: '期权', value: 'option' },
  ];

  // 交易所选项
  const exchangeOptions = [
    { label: 'Binance', value: 'binance' },
  ];

  // 加载任务详情（编辑模式）
  const loadTaskDetails = async (taskId: number) => {
    try {
      setLoading(true);
      const data = await scheduledTaskApi.getTask(taskId.toString());
      const task = data.task;
      if (task) {
        // 格式化日期时间
        const formattedTask = {
          ...task,
          start_time: task.start_time ? dayjs(task.start_time).format('YYYY-MM-DD HH:mm:ss') : undefined,
          end_time: task.end_time ? dayjs(task.end_time).format('YYYY-MM-DD HH:mm:ss') : undefined,
        };
        // 设置表单值
        form.setFieldsValue(formattedTask);
      }
    } catch (error) {
      console.error('加载任务详情失败:', error);
      message.error('加载任务详情失败');
    } finally {
      setLoading(false);
    }
  };

  // 组件挂载时，如果是编辑模式则加载任务详情
  useEffect(() => {
    if (params.id) {
      setIsEdit(true);
      loadTaskDetails(Number(params.id));
    }
  }, [params.id]);

  // 提交表单
  const handleSubmit = async (values: ScheduledTaskFormData) => {
    try {
      setLoading(true);
      
      // 格式化请求数据
      const requestData = {
        ...values,
        // 将日期字符串转换为日期对象
        start_time: values.start_time ? new Date(values.start_time) : undefined,
        end_time: values.end_time ? new Date(values.end_time) : undefined,
      };
      
      if (isEdit && params.id) {
        // 编辑模式
        await scheduledTaskApi.updateTask(params.id, requestData);
      } else {
        // 创建模式
        await scheduledTaskApi.createTask(requestData);
      }
      
      message.success(isEdit ? '定时任务更新成功' : '定时任务创建成功');
      // 导航回列表页面
      navigate('/scheduled-tasks');
    } catch (error) {
      console.error(`${isEdit ? '更新' : '创建'}定时任务失败:`, error);
      message.error(`${isEdit ? '更新' : '创建'}定时任务失败`);
    } finally {
      setLoading(false);
    }
  };

  // 返回列表页面
  const handleBack = () => {
    navigate('/scheduled-tasks');
  };

  return (
    <div className="scheduled-task-form-page">
      <Card
        title={
          <Space>
            <Button
              type="link"
              icon={<LeftOutlined />}
              onClick={handleBack}
              size="small"
            />
            {isEdit ? '编辑定时任务' : '新建定时任务'}
          </Space>
        }
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            task_type: 'download_crypto',
            candle_type: 'spot',
            max_workers: 1,
            incremental_enabled: true,
            notification_enabled: false,
            frequency_type: 'daily',
          }}
        >
          <Form.Item
            name="name"
            label="任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="请输入任务名称" />
          </Form.Item>

          <Form.Item
            name="description"
            label="任务描述"
          >
            <Input.TextArea
              placeholder="请输入任务描述"
              rows={4}
            />
          </Form.Item>

          <Form.Item
            name="task_type"
            label="任务类型"
            rules={[{ required: true, message: '请选择任务类型' }]}
          >
            <Select
              options={taskTypeOptions}
              placeholder="请选择任务类型"
            />
          </Form.Item>

          <Form.Item
            name="frequency_type"
            label="频率类型"
            rules={[{ required: true, message: '请选择频率类型' }]}
          >
            <Select
              options={frequencyTypeOptions}
              placeholder="请选择频率类型"
            />
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.frequency_type !== currentValues.frequency_type}
          >
            {({ getFieldValue }) => {
              const frequencyType = getFieldValue('frequency_type');
              return frequencyType === 'cron' ? (
                <Form.Item
                  name="cron_expression"
                  label="CRON表达式"
                  rules={[{ required: true, message: '请输入CRON表达式' }]}
                >
                  <Input placeholder="请输入CRON表达式，如 0 0 * * * 表示每天凌晨执行" />
                </Form.Item>
              ) : frequencyType === 'interval' ? (
                <Form.Item
                  name="interval"
                  label="时间间隔"
                  rules={[{ required: true, message: '请输入时间间隔' }]}
                >
                  <Input placeholder="请输入时间间隔，如1h, 1d, 1w" />
                </Form.Item>
              ) : null;
            }}
          </Form.Item>

          <Form.Item
            name="start_time"
            label="开始执行时间"
          >
            <Input
              type="datetime-local"
              placeholder="请选择开始执行时间"
            />
          </Form.Item>

          <Form.Item
            name="end_time"
            label="结束执行时间"
          >
            <Input
              type="datetime-local"
              placeholder="请选择结束执行时间"
            />
          </Form.Item>

          <Form.Item
            name="symbols"
            label="交易对"
            rules={[{ required: true, message: '请输入交易对' }]}
          >
            <Input
              placeholder="请输入交易对，多个交易对用逗号分隔，如 BTCUSDT,ETHUSDT"
              onChange={(e) => {
                const value = e.target.value;
                // 将逗号分隔的字符串转换为数组
                const symbols = value ? value.split(',').map(s => s.trim()).filter(s => s) : [];
                form.setFieldValue('symbols', symbols);
              }}
            />
          </Form.Item>

          <Form.Item
            name="exchange"
            label="交易所"
            rules={[{ required: true, message: '请选择交易所' }]}
          >
            <Select
              options={exchangeOptions}
              placeholder="请选择交易所"
            />
          </Form.Item>

          <Form.Item
            name="candle_type"
            label="蜡烛图类型"
            rules={[{ required: true, message: '请选择蜡烛图类型' }]}
          >
            <Select
              options={candleTypeOptions}
              placeholder="请选择蜡烛图类型"
            />
          </Form.Item>

          <Form.Item
            name="save_dir"
            label="保存目录"
          >
            <Input placeholder="请输入数据保存目录" />
          </Form.Item>

          <Form.Item
            name="max_workers"
            label="最大工作线程数"
            rules={[{ required: true, message: '请输入最大工作线程数' }]}
          >
            <InputNumber min={1} max={10} placeholder="请输入最大工作线程数" />
          </Form.Item>

          <Form.Item
            name="incremental_enabled"
            label="启用增量采集"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="notification_enabled"
            label="启用通知"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.notification_enabled !== currentValues.notification_enabled}
          >
            {({ getFieldValue }) => {
              const notificationEnabled = getFieldValue('notification_enabled');
              if (notificationEnabled) {
                return (
                  <>
                    <Form.Item
                      name="notification_type"
                      label="通知类型"
                      rules={[{ required: true, message: '请选择通知类型' }]}
                    >
                      <Select
                        options={notificationTypeOptions}
                        placeholder="请选择通知类型"
                      />
                    </Form.Item>

                    <Form.Item
                      noStyle
                      shouldUpdate={(prevValues, currentValues) => prevValues.notification_type !== currentValues.notification_type}
                    >
                      {({ getFieldValue }) => {
                        const notificationType = getFieldValue('notification_type');
                        if (notificationType === 'email') {
                          return (
                            <Form.Item
                              name="notification_email"
                              label="通知邮箱"
                              rules={[{ required: true, message: '请输入通知邮箱' }, { type: 'email', message: '请输入有效的邮箱地址' }]}
                            >
                              <Input placeholder="请输入通知邮箱" />
                            </Form.Item>
                          );
                        } else if (notificationType === 'webhook') {
                          return (
                            <Form.Item
                              name="notification_webhook"
                              label="Webhook URL"
                              rules={[{ required: true, message: '请输入Webhook URL' }]}
                            >
                              <Input placeholder="请输入Webhook URL" />
                            </Form.Item>
                          );
                        }
                        return null;
                      }}
                    </Form.Item>
                  </>
                );
              }
              return null;
            }}
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                {isEdit ? '更新任务' : '创建任务'}
              </Button>
              <Button onClick={handleBack}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default ScheduledTaskForm;
