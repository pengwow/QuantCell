/**
 * 系统信息模块
 * 功能：显示系统日志、系统信息（版本+状态）等信息
 */
import { Card, Descriptions, Tag } from 'antd';
import { useSettings } from './SettingsContext';
import SystemLogs from './SystemLogs';
import type { SystemInfo as SystemInfoType } from './types';

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

  // 获取使用率状态
  const getUsageStatus = (percent: number): 'normal' | 'warning' | 'critical' => {
    if (percent >= 85) return 'critical';
    if (percent >= 70) return 'warning';
    return 'normal';
  };

  return (
    <div className="space-y-6">
      {/* 系统日志 - 放在最上方 */}
      <SystemLogs />

      {/* 系统信息 - 合并版本信息和系统状态 */}
      <div>
        <h3 className="text-lg font-medium mb-4">系统信息</h3>
        <Card size="small">
          <Descriptions bordered column={1}>
            {/* 版本信息 */}
            <Descriptions.Item label="系统版本">
              {systemInfo.version.system_version}
            </Descriptions.Item>
            <Descriptions.Item label="Python版本">
              {systemInfo.version.python_version}
            </Descriptions.Item>
            <Descriptions.Item label="构建日期">
              {systemInfo.version.build_date}
            </Descriptions.Item>

            {/* 运行状态信息 */}
            <Descriptions.Item label="运行时间">
              {systemInfo.running_status.uptime}
            </Descriptions.Item>
            <Descriptions.Item label="运行状态">
              <Tag color={getStatusColor(systemInfo.running_status.status)}>
                {systemInfo.running_status.status}
              </Tag>
            </Descriptions.Item>

            {/* 资源状态 */}
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
      </div>
    </div>
  );
};

export default SystemInfo;
