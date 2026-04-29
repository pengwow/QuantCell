/**
 * LogSettingsPanel - 日志设置主面板
 * 提供日志文件管理、清理和配置的统一入口（整合版）
 */
import LogSettingsUnified from './LogSettingsUnified';

interface LogSettingsPanelProps {
  onClose?: () => void;
}

const LogSettingsPanel: React.FC<LogSettingsPanelProps> = ({ onClose }) => {
  return (
    <div className="log-settings-panel">
      <LogSettingsUnified onClose={onClose} />
    </div>
  );
};

export default LogSettingsPanel;
