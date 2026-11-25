/**
 * 系统信息模块
 * 功能：显示系统日志、系统信息（版本+状态）等信息
 */
import { useState } from 'react';
import { Card, Descriptions, Drawer } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSettings } from './SettingsContext';
import SystemLogs from './SystemLogs';
import LogSettingsPanel from './LogSettingsPanel';
import type { SystemInfo as SystemInfoType } from './types';

interface SystemInfoProps {
  systemInfo: SystemInfoType;
}

const SystemInfo = ({ systemInfo }: SystemInfoProps) => {
  const { t } = useTranslation();
  const { systemMetrics } = useSettings();
  const [showLogSettings, setShowLogSettings] = useState(false);

  // 获取状态徽章（语义 chip）
  const getStatusChip = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case '运行中':
        return 'qc-chip ok';
      case 'stopped':
      case '已停止':
      case 'error':
      case '错误':
        return 'qc-chip down';
      default:
        return 'qc-chip quiet';
    }
  };

  // 使用率状态
  const getUsageStatus = (percent: number): 'normal' | 'warning' | 'critical' => {
    if (percent >= 85) return 'critical';
    if (percent >= 70) return 'warning';
    return 'normal';
  };

  // 使用率状态点颜色：≥85 error、≥70 warning、其余 success（§2.2 语义色）
  const usageDotColor = (percent: number) =>
    getUsageStatus(percent) === 'critical'
      ? 'var(--qc-error)'
      : getUsageStatus(percent) === 'warning'
      ? 'var(--qc-warning)'
      : 'var(--qc-success)';

  return (
    <div className="space-y-6">
      {/* 系统日志 - 放在最上方 */}
      <SystemLogs onLogSettingsClick={() => setShowLogSettings(true)} />

      {/* 系统信息 - 合并版本信息和系统状态 */}
      <div>
        <h3 className="mb-3 font-[650]" style={{ fontSize: 13 }}>{t('system_info')}</h3>
        <Card size="small" className="qc-card">
          <Descriptions
            bordered
            column={1}
            styles={{
              label: { color: 'var(--qc-text-quaternary)', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 11, letterSpacing: '.02em' },
              content: { fontSize: 12 },
            }}
          >
            {/* 版本信息 */}
            <Descriptions.Item label={t('system_version')}>
              {systemInfo.version.system_version}
            </Descriptions.Item>
            <Descriptions.Item label={t('system_python_version')}>
              {systemInfo.version.python_version}
            </Descriptions.Item>
            <Descriptions.Item label={t('system_build_date')}>
              {systemInfo.version.build_date}
            </Descriptions.Item>

            {/* 运行状态信息 */}
            <Descriptions.Item label={t('uptime')}>
              {systemInfo.running_status.uptime}
            </Descriptions.Item>
            <Descriptions.Item label={t('running_status')}>
              <span className={getStatusChip(systemInfo.running_status.status)}>
                {systemInfo.running_status.status}
              </span>
            </Descriptions.Item>

            {/* 资源状态 */}
            <Descriptions.Item label={t('cpu_usage')}>
              <div className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ background: usageDotColor(systemMetrics.cpuUsage) }}
                />
                <span>{systemMetrics.cpuUsage}%</span>
              </div>
            </Descriptions.Item>
            <Descriptions.Item label={t('memory_usage')}>
              <div className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{
                    background: usageDotColor(
                      (parseFloat(systemMetrics.memoryUsed) / parseFloat(systemMetrics.memoryTotal)) * 100
                    ),
                  }}
                />
                <span>{systemMetrics.memoryUsed} / {systemMetrics.memoryTotal}</span>
              </div>
            </Descriptions.Item>
            <Descriptions.Item label={t('disk_space')}>
              <div className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{
                    background: usageDotColor(
                      (parseFloat(systemMetrics.diskUsed) / parseFloat(systemMetrics.diskTotal)) * 100
                    ),
                  }}
                />
                <span>{systemMetrics.diskUsed} / {systemMetrics.diskTotal}</span>
              </div>
            </Descriptions.Item>
            <Descriptions.Item label={t('system_last_updated')}>
              {new Date(systemMetrics.lastUpdated).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>

      {/* 日志设置面板 - 右侧抽屉 */}
      <Drawer
        title={t('system_log_settings')}
        placement="right"
        size="large"
        onClose={() => setShowLogSettings(false)}
        open={showLogSettings}
        destroyOnHidden
      >
        <LogSettingsPanel onClose={() => setShowLogSettings(false)} />
      </Drawer>
    </div>
  );
};

export default SystemInfo;
