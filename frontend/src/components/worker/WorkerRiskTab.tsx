/**
 * Worker 风控 tab 容器（6 tab 重构：原「风控」tab 与参数 tab 的人工风控卡归并于此）
 *
 * 组成：
 * - WorkerRiskStatusCard：运行态风控状态（熔断/限额用量），30s 轮询
 * - WorkerRiskControlCard：人工风控配置三态明细（从参数 tab 迁入）
 */

import { Space } from 'antd';
import WorkerRiskStatusCard from './WorkerRiskStatusCard';
import WorkerRiskControlCard from './WorkerRiskControlCard';

interface WorkerRiskTabProps {
  workerId: number;
  /** tab 是否激活；激活时状态卡才轮询 */
  active?: boolean;
  /** 递增触发配置卡重拉：编辑弹窗保存成功后由父页面更新 */
  reloadKey?: number;
  /** 配置卡「编辑」按钮回调（父页面联动 EditModal） */
  onEdit?: () => void;
}

const WorkerRiskTab: React.FC<WorkerRiskTabProps> = ({ workerId, active = true, reloadKey, onEdit }) => {
  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      {/* 状态卡不传 onNavigate：其内部 onNavigate && 条件渲染会自动隐藏「前往参数配置」链接
       *  （人工风控配置已迁入本 tab，跳参数 tab 的入口不再成立），WorkerRiskStatusCard 零改动。
       *  其根节点自带 <Card size="small">，此处不再包一层 Card（避免双边框） */}
      <WorkerRiskStatusCard workerId={workerId} active={active} />
      <WorkerRiskControlCard workerId={workerId} reloadKey={reloadKey} onEdit={onEdit} />
    </Space>
  );
};

export default WorkerRiskTab;
