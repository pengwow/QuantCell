/**
 * 系统信息模块
 * 功能：显示系统版本、运行状态、资源使用、系统状态和系统日志等信息
 */
import { Card, Descriptions, Progress, Tag, Badge } from 'antd';
import { useSettings } from './SettingsContext';
import SystemLogs from './SystemLogs';
import type { SystemInfo as SystemInfoType, SystemMetrics } from './types';

interface SystemInfoProps {
  systemInfo: SystemInfoType;
}

const SystemInfo = ({ systemInfo }: SystemInfoProps) => {
  const { systemMetrics } = useSettings();

  // 获取状态标签颜色
  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case '运行中':
        return 'green';
      case 'stopped':
      case '已停止':
        return 'red';
      case 'error':
      case '错误':
        return 'red';
      default:
        return 'default';
    }
  };

  // 获取连接状态颜色
  const getConnectionStatusColor = (status: SystemMetrics['connectionStatus']) => {
    switch (status) {
      case 'connected':
        return 'success';
      case 'disconnected':
        return 'default';
      case 'error':
        return 'error';
      default:
        return 'default';
    }
  };

  // 获取连接状态文本
  const getConnectionStatusText = (status: SystemMetrics['connectionStatus']) => {
    switch (status) {
      case 'connected':
        return '已连接';
      case 'disconnected':
        return '未连接';
      case 'error':
        return '连接错误';
      default:
        return '未知';
    }
  };

  // 获取使用率状态
  const getUsageStatus = (percent: number): 'normal' | 'warning' | 'critical' => {
    if (percent >= 85) return 'critical';
    if (percent >= 70) return 'warning';
    return 'normal';
  };

  return (
    <div className="block space-y-4">
      <Card className="settings-panel" title="系统信息" variant="outlined">
        {/* 版本信息 */}
        <Card size="small" className="mb-4">
          <Descriptions title="版本信息" bordered column={1}>
            <Descriptions.Item label="系统版本">
              {systemInfo.version.system_version}
            </Descriptions.Item>
            <Descriptions.Item label="Python版本">
              {systemInfo.version.python_version}
            </Descriptions.Item>
            <Descriptions.Item label="构建日期">
              {systemInfo.version.build_date}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* 运行状态 */}
        <Card size="small" className="mb-4">
          <Descriptions title="运行状态" bordered column={1}>
            <Descriptions.Item label="运行时间">
              {systemInfo.running_status.uptime}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={getStatusColor(systemInfo.running_status.status)}>
                {systemInfo.running_status.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="最后检查时间">
              {systemInfo.running_status.last_check}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* 资源使用 */}
        <Card size="small" className="mb-4">
          <Descriptions title="资源使用" bordered column={1}>
            <Descriptions.Item label="CPU使用率">
              <Progress
                percent={systemInfo.resource_usage.cpu_usage}
                size="small"
                status={systemInfo.resource_usage.cpu_usage > 80 ? 'exception' : 'normal'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="内存使用">
              {systemInfo.resource_usage.memory_usage}
            </Descriptions.Item>
            <Descriptions.Item label="磁盘空间">
              {systemInfo.resource_usage.disk_space}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* 系统状态 - 从左侧菜单栏迁移过来 */}
        <Card size="small">
          <Descriptions title="系统状态" bordered column={1}>
            <Descriptions.Item label="连接状态">
              <Badge
                status={getConnectionStatusColor(systemMetrics.connectionStatus)}
                text={getConnectionStatusText(systemMetrics.connectionStatus)}
              />
            </Descriptions.Item>
            <Descriptions.Item label="CPU使用率">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    getUsageStatus(systemMetrics.cpuUsage) === 'critical'
                      ? 'bg-red-500'
                      : getUsageStatus(systemMetrics.cpuUsage) === 'warning'
                      ? 'bg-yellow-500'
                      : 'bg-green-500'
                  }`}
                />
                <span>{systemMetrics.cpuUsage}%</span>
              </div>
            </Descriptions.Item>
            <Descriptions.Item label="内存使用">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    getUsageStatus(
                      (parseFloat(systemMetrics.memoryUsed) / parseFloat(systemMetrics.memoryTotal)) * 100
                    ) === 'critical'
                      ? 'bg-red-500'
                      : getUsageStatus(
                          (parseFloat(systemMetrics.memoryUsed) / parseFloat(systemMetrics.memoryTotal)) * 100
                        ) === 'warning'
                      ? 'bg-yellow-500'
                      : 'bg-green-500'
                  }`}
                />
                <span>{systemMetrics.memoryUsed} / {systemMetrics.memoryTotal}</span>
              </div>
            </Descriptions.Item>
            <Descriptions.Item label="磁盘空间">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    getUsageStatus(
                      (parseFloat(systemMetrics.diskUsed) / parseFloat(systemMetrics.diskTotal)) * 100
                    ) === 'critical'
                      ? 'bg-red-500'
                      : getUsageStatus(
                          (parseFloat(systemMetrics.diskUsed) / parseFloat(systemMetrics.diskTotal)) * 100
                        ) === 'warning'
                      ? 'bg-yellow-500'
                      : 'bg-green-500'
                  }`}
                />
                <span>{systemMetrics.diskUsed} / {systemMetrics.diskTotal}</span>
              </div>
            </Descriptions.Item>
            <Descriptions.Item label="最后更新">
              {new Date(systemMetrics.lastUpdated).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Card>

      {/* 系统日志 */}
      <SystemLogs />
    </div>
  );
};

export default SystemInfo;
