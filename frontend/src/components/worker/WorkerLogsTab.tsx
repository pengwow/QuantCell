/**
 * Worker 日志 tab（6 tab 重构：对账卡从总览 tab 迁入，与日志面板同屏）
 */

import { Space } from 'antd';
import WorkerLogsPanel from './WorkerLogsPanel';
import WorkerReconcileCard from './WorkerReconcileCard';

interface WorkerLogsTabProps {
  workerId: number;
}

const WorkerLogsTab: React.FC<WorkerLogsTabProps> = ({ workerId }) => {
  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <div style={{ minHeight: 500 }}>
        <WorkerLogsPanel
          workerId={workerId}
          maxHeight={600}
        />
      </div>
      {/* 对账卡（迁移自总览 tab）：日志 tab 无「激活态」概念，active 恒 true */}
      <WorkerReconcileCard workerId={workerId} active />
    </Space>
  );
};

export default WorkerLogsTab;
