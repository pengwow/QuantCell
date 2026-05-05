import { useTranslation } from 'react-i18next';
import WorkerLogsPanel from './WorkerLogsPanel';

interface WorkerLogsTabProps {
  workerId: number;
}

const WorkerLogsTab: React.FC<WorkerLogsTabProps> = ({ workerId }) => {
  const { t } = useTranslation();

  return (
    <div style={{ minHeight: 500 }}>
      <WorkerLogsPanel
        workerId={workerId}
        maxHeight={600}
      />
    </div>
  );
};

export default WorkerLogsTab;
