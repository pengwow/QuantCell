/**
 * 系统信息模块
 * 功能：显示系统版本、运行状态、资源使用等系统信息
 */
import React from 'react';
import { Card, Button } from 'antd';
import type { SystemInfo } from './types';

interface SystemInfoProps {
  systemInfo: SystemInfo;
  isSaving: boolean;
  saveError: string | null;
  updateLocalStateAndForm: () => void;
}

const SystemInfo: React.FC<SystemInfoProps> = ({
  systemInfo,
  isSaving,
  saveError,
  updateLocalStateAndForm
}) => {


  return (
    <div style={{ display: 'block' }}>
      <Card className="settings-panel" title="系统信息" variant="outlined">
        {/* 加载状态 */}
        {isSaving ? (
          <div className="loading-state" style={{ textAlign: 'center', padding: '40px' }}>
            <div className="loading-spinner"></div>
            <span style={{ display: 'block', marginTop: '16px' }}>加载系统信息中...</span>
          </div>
        ) : saveError ? (
          <div className="error-state" style={{ textAlign: 'center', padding: '40px' }}>
            <div className="error-icon" style={{ fontSize: '24px', marginBottom: '8px' }}>⚠️</div>
            <span style={{ display: 'block', marginBottom: '16px' }}>{saveError}</span>
            <Button type="default" onClick={updateLocalStateAndForm}>
              重试
            </Button>
          </div>
        ) : (
          <div className="system-info">
            <Card size="small" title="版本信息" style={{ marginBottom: 16 }}>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>系统版本：</span>
                <span className="info-value">{systemInfo.version.system_version}</span>
              </div>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>Python 版本：</span>
                <span className="info-value">{systemInfo.version.python_version}</span>
              </div>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>构建日期：</span>
                <span className="info-value">{systemInfo.version.build_date}</span>
              </div>
              {systemInfo.apiVersion && (
                <div className="info-item" style={{ marginBottom: '8px' }}>
                  <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>API 版本：</span>
                  <span className="info-value">{systemInfo.apiVersion}</span>
                </div>
              )}
            </Card>

            <Card size="small" title="运行状态" style={{ marginBottom: 16 }}>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>运行时间：</span>
                <span className="info-value">{systemInfo.running_status.uptime}</span>
              </div>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>服务状态：</span>
                <span
                  className="info-value"
                  style={{ color: systemInfo.running_status.status_color === 'green' ? '#52c41a' : '#ff4d4f', fontWeight: 'bold' }}
                >
                  {systemInfo.running_status.status === 'running' ? '正常运行' : systemInfo.running_status.status}
                </span>
              </div>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>最后检查：</span>
                <span className="info-value">{new Date(systemInfo.running_status.last_check).toLocaleString()}</span>
              </div>
            </Card>

            <Card size="small" title="资源使用">
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>CPU 使用率：</span>
                <span className="info-value">{systemInfo.resource_usage.cpu_usage}%</span>
              </div>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>内存使用：</span>
                <span className="info-value">{systemInfo.resource_usage.memory_usage}</span>
              </div>
              <div className="info-item" style={{ marginBottom: '8px' }}>
                <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>磁盘空间：</span>
                <span className="info-value">{systemInfo.resource_usage.disk_space}</span>
              </div>
            </Card>
          </div>
        )}
      </Card>
    </div>
  );
};

export default SystemInfo;
