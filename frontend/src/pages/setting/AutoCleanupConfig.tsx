/**
 * AutoCleanupConfig - 自动清理配置
 * 提供日志自动清理参数的配置界面
 */
import { useState, useEffect, useCallback } from 'react';
import { App } from 'antd';
import {
  Card,
  Switch,
  InputNumber,
  Radio,
  Button,
  Statistic,
  Row,
  Col,
  Space,
  Divider,
  Spin,
  Alert,
  Progress,
} from 'antd';
import {
  IconSettings,
  IconRefresh,
  IconCheck,
  IconClock,
  IconDatabase,
} from '@tabler/icons-react';
import { systemApi } from '../../api';
import type { LogAutoCleanupConfig, LogDiskUsage } from './types';

const AutoCleanupConfig: React.FC = () => {
  const { message: antMessage } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<LogAutoCleanupConfig>({
    enabled: false,
    retentionDays: 30,
    maxSizeGB: 10,
    cleanupSchedule: 'weekly',
    lastCleanupTime: null,
    nextCleanupTime: null,
    spaceUsed: 0,
  });
  const [diskUsage, setDiskUsage] = useState<LogDiskUsage | null>(null);
  const [originalConfig, setOriginalConfig] = useState<LogAutoCleanupConfig | null>(null);

  // 加载配置
  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const [configData, diskData] = await Promise.all([
        systemApi.getAutoCleanupConfig(),
        systemApi.getLogDiskUsage(),
      ]);
      setConfig(configData);
      setOriginalConfig(configData);
      setDiskUsage(diskData);
    } catch (error) {
      console.error('加载配置失败:', error);
      antMessage.error('无法加载自动清理配置');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // 更新配置
  const handleSave = async () => {
    try {
      setSaving(true);
      await systemApi.updateAutoCleanupConfig(config);
      setOriginalConfig({ ...config });
      antMessage.success('配置保存成功');
    } catch (error) {
      console.error('保存配置失败:', error);
      antMessage.error('保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  // 重置配置
  const handleReset = () => {
    if (originalConfig) {
      setConfig({ ...originalConfig });
      antMessage.info('配置已重置');
    }
  };

  // 手动触发清理
  const handleExecuteCleanup = async () => {
    try {
      const result = await systemApi.executeCleanup();

      if (result.success) {
        antMessage.success(`清理完成，删除了 ${result.deletedCount || 0} 个文件`);
        loadConfig(); // 刷新数据
      } else {
        antMessage.warning('清理过程中出现问题');
      }
    } catch (error) {
      console.error('执行清理失败:', error);
      antMessage.error('执行清理失败');
    }
  };

  // 计算空间使用百分比
  const getSpacePercent = (): number => {
    if (!config.maxSizeGB || config.maxSizeGB === 0) return 0;
    return Math.min((config.spaceUsed / (config.maxSizeGB * 1024)) * 100, 100);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Spin size="large" tip="加载配置中..." />
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* 启用开关 */}
      <Card
        size="small"
        className="mb-4 shadow-sm"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <IconSettings size={20} className="text-blue-500" />
            <span className="font-semibold">自动清理设置</span>
          </div>
          <Switch
            checked={config.enabled}
            onChange={(checked) =>
              setConfig(prev => ({ ...prev, enabled: checked }))
            }
            checkedChildren="已启用"
            unCheckedChildren="已禁用"
          />
        </div>
      </Card>

      {/* 配置项（仅在启用时显示） */}
      {config.enabled && (
        <Card
          title={
            <span className="flex items-center gap-2">
              <IconDatabase size={16} />
              清理规则配置
            </span>
          }
          size="small"
          className="mb-4 shadow-sm"
        >
          <Row gutter={[24, 16]}>
            {/* 保留天数 */}
            <Col span={12}>
              <div className="mb-2">
                <label className="text-sm font-medium text-gray-700 block mb-1">
                  保留天数
                </label>
                <InputNumber
                  min={1}
                  max={365}
                  value={config.retentionDays}
                  onChange={(value) =>
                    setConfig(prev => ({
                      ...prev,
                      retentionDays: value || 30,
                    }))
                  }
                  style={{ width: '100%' }}
                  addonAfter="天"
                />
                <p className="text-xs text-gray-500 mt-1">
                  超过此天数的日志文件将被自动删除
                </p>
              </div>
            </Col>

            {/* 最大存储空间 */}
            <Col span={12}>
              <div className="mb-2">
                <label className="text-sm font-medium text-gray-700 block mb-1">
                  最大存储空间
                </label>
                <InputNumber
                  min={0}
                  max={1000}
                  value={config.maxSizeGB}
                  onChange={(value) =>
                    setConfig(prev => ({
                      ...prev,
                      maxSizeGB: value || 0,
                    }))
                  }
                  style={{ width: '100%' }}
                  addonAfter="GB"
                />
                <p className="text-xs text-gray-500 mt-1">
                  设置为 0 表示不限制空间大小
                </p>
              </div>
            </Col>

            {/* 清理频率 */}
            <Col span={24}>
              <div className="mb-2">
                <label className="text-sm font-medium text-gray-700 block mb-1">
                  清理频率
                </label>
                <Radio.Group
                  value={config.cleanupSchedule}
                  onChange={(e) =>
                    setConfig(prev => ({
                      ...prev,
                      cleanupSchedule: e.target.value,
                    }))
                  }
                  optionType="button"
                  buttonStyle="solid"
                >
                  <Radio.Button value="daily">每天</Radio.Button>
                  <Radio.Button value="weekly">每周</Radio.Button>
                </Radio.Group>
              </div>
            </Col>
          </Row>

          <Divider />

          {/* 操作按钮 */}
          <Space>
            <Button
              type="primary"
              icon={<IconCheck size={14} />}
              onClick={handleSave}
              loading={saving}
              disabled={!originalConfig || JSON.stringify(config) === JSON.stringify(originalConfig)}
            >
              保存配置
            </Button>
            <Button
              onClick={handleReset}
              disabled={!originalConfig || JSON.stringify(config) === JSON.stringify(originalConfig)}
            >
              重置
            </Button>
          </Space>
        </Card>
      )}

      {/* 当前状态 */}
      <Card
        title={
          <span className="flex items-center gap-2">
            <IconClock size={16} />
            当前状态
          </span>
        }
        size="small"
        className="mb-4 shadow-sm"
      >
        <Row gutter={[24, 16]}>
          {/* 占用空间 */}
          <Col span={12}>
            <Statistic
              title="占用空间"
              value={config.spaceUsed}
              suffix="MB"
              precision={2}
              valueStyle={{
                color: config.spaceUsed > config.maxSizeGB * 1024 / 2 ? '#cf1322' : '#3f8600',
              }}
            />
            {config.maxSizeGB > 0 && (
              <Progress
                percent={getSpacePercent()}
                status={getSpacePercent() > 80 ? 'exception' : 'active'}
                size="small"
                className="mt-2"
              />
            )}
          </Col>

          {/* 上次清理时间 */}
          <Col span={12}>
            <Statistic
              title="上次清理"
              value={
                config.lastCleanupTime ?
                  new Date(config.lastCleanupTime).toLocaleString('zh-CN') :
                  '-'
              }
              valueStyle={{ fontSize: 14 }}
            />
          </Col>

          {/* 下次清理时间 */}
          <Col span={12}>
            <Statistic
              title="下次清理"
              value={
                config.nextCleanupTime ?
                  new Date(config.nextCleanupTime).toLocaleString('zh-CN') :
                  '-'
              }
              valueStyle={{ fontSize: 14 }}
            />
          </Col>

          {/* 日志文件总数 */}
          <Col span={12}>
            <Statistic
              title="日志文件数"
              value={diskUsage ?
                Object.values(diskUsage.logTypes).reduce((sum, t) => sum + t.count, 0) :
                0
            }
            />
          </Col>
        </Row>
      </Card>

      {/* 磁盘使用详情 */}
      {diskUsage && Object.keys(diskUsage.logTypes).length > 0 && (
        <Card
          title="各类型占用情况"
          size="small"
          className="shadow-sm"
        >
          <Row gutter={[16, 8]}>
            {Object.entries(diskUsage.logTypes).map(([type, info]) => (
              <Col key={type} span={12}>
                <div className="flex justify-between items-center p-2 bg-gray-50 rounded">
                  <Tag color="blue">{type}</Tag>
                  <span className="font-mono text-sm">
                    {info.count} 个文件 / {(info.totalSize / 1024 / 1024).toFixed(2)} MB
                  </span>
                </div>
              </Col>
            ))}
          </Row>
        </Card>
      )}

      {/* 手动操作区 */}
      <Card
        size="small"
        className="mt-4 shadow-sm"
      >
        <Alert
          type="info"
          showIcon
          message="手动清理"
          description="可以立即执行一次基于当前配置的清理操作，删除超过保留天数的旧日志文件"
          className="mb-3"
        />
        <Button
          danger
          icon={<IconRefresh size={14} />}
          onClick={handleExecuteCleanup}
        >
          立即执行一次清理
        </Button>
      </Card>
    </div>
  );
};

export default AutoCleanupConfig;
