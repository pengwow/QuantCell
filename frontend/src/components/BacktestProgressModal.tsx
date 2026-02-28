/**
 * 回测进度弹窗组件
 * 功能：展示回测的各个阶段进度，包括数据准备、执行回测、结果统计
 * 适用场景：策略回测、数据下载、批量处理等需要展示多阶段进度的场景
 */
import {
  Modal,
  Steps,
  Progress,
  Typography,
  Space,
  Alert,
  Card,
  Button,
  Tooltip,
  Popconfirm,
} from 'antd';
import {
  DatabaseOutlined,
  PlayCircleOutlined,
  BarChartOutlined,
  CheckCircleFilled,
  LoadingOutlined,
  CloseCircleFilled,
  DownloadOutlined,
  StopOutlined,
} from '@ant-design/icons';


const { Text } = Typography;

// 步骤状态类型
export type StepStatus = 'wait' | 'process' | 'finish' | 'error';

// 进度数据接口
export interface ProgressData {
  overall: number;
  dataPrep?: {
    percent: number;
    downloading?: boolean;
    downloadProgress?: number;
  };
  execution?: {
    percent: number;
    current: number;
    total: number;
    currentSymbol?: string;
  };
}

// 步骤状态接口
export interface StepStatusState {
  dataPrep: StepStatus;
  execution: StepStatus;
  analysis: StepStatus;
}

// 组件属性接口
interface BacktestProgressModalProps {
  visible: boolean;
  onCancel: () => void;
  currentStep: number;
  stepStatus: StepStatusState;
  progressData: ProgressData;
  errorMessage?: string;
  onStop?: () => void;
  isRunning?: boolean;
}

const BacktestProgressModal = ({
  visible,
  onCancel,
  currentStep,
  stepStatus,
  progressData,
  errorMessage,
  onStop,
  isRunning = false,
}: BacktestProgressModalProps) => {
  // 获取步骤图标
  const getStepIcon = (status: StepStatus, defaultIcon: React.ReactNode) => {
    switch (status) {
      case 'process':
        return <LoadingOutlined />;
      case 'finish':
        return <CheckCircleFilled style={{ color: '#52c41a' }} />;
      case 'error':
        return <CloseCircleFilled style={{ color: '#ff4d4f' }} />;
      default:
        return defaultIcon;
    }
  };

  // 步骤配置
  const steps = [
    {
      title: '数据准备',
      icon: getStepIcon(stepStatus.dataPrep, <DatabaseOutlined />),
      description: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {stepStatus.dataPrep === 'process' && progressData.dataPrep && (
            <>
              {progressData.dataPrep.downloading ? (
                <>
                  <Text type="warning">
                    <DownloadOutlined /> 检测到数据缺失，正在自动下载...
                  </Text>
                  <Progress
                    percent={progressData.dataPrep.downloadProgress || 0}
                    size="small"
                    status="active"
                    format={(percent) => `${percent}%`}
                  />
                </>
              ) : (
                <>
                  <Text type="secondary">正在检查数据完整性...</Text>
                  <Progress
                    percent={progressData.dataPrep.percent}
                    size="small"
                    status="active"
                    format={(percent) => `${percent}%`}
                  />
                </>
              )}
            </>
          )}
          {stepStatus.dataPrep === 'error' && (
            <Alert
              message="数据准备失败"
              description={errorMessage || '数据完整性检查或下载失败'}
              type="error"
              showIcon
            />
          )}
          {stepStatus.dataPrep === 'finish' && (
            <Text type="success" style={{ fontSize: '12px' }}>
              <CheckCircleFilled /> 数据完整性检查通过
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '执行回测',
      icon: getStepIcon(stepStatus.execution, <PlayCircleOutlined />),
      description: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {stepStatus.execution === 'process' && progressData.execution && (
            <>
              <Text type="secondary">
                正在回测: {progressData.execution.currentSymbol || '准备中'}
                <span style={{ marginLeft: 8, color: '#8c8c8c' }}>
                  ({progressData.execution.current}/{progressData.execution.total})
                </span>
              </Text>
              <Progress
                percent={progressData.execution.percent}
                size="small"
                status="active"
              />
            </>
          )}
          {stepStatus.execution === 'error' && (
            <Alert
              message="回测执行失败"
              description={errorMessage || '回测过程中发生错误'}
              type="error"
              showIcon
            />
          )}
          {stepStatus.execution === 'finish' && (
            <Text type="success" style={{ fontSize: '12px' }}>
              <CheckCircleFilled /> 回测执行完成
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '结果统计',
      icon: getStepIcon(stepStatus.analysis, <BarChartOutlined />),
      description: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {stepStatus.analysis === 'process' && (
            <Text type="secondary">正在生成统计报告...</Text>
          )}
          {stepStatus.analysis === 'error' && (
            <Alert
              message="结果统计失败"
              description={errorMessage || '生成统计报告时发生错误'}
              type="error"
              showIcon
            />
          )}
          {stepStatus.analysis === 'finish' && (
            <Text type="success" style={{ fontSize: '12px' }}>
              <CheckCircleFilled /> 结果统计完成
            </Text>
          )}
        </Space>
      ),
    },
  ];

  // 判断是否完成或出错
  const isFinished = stepStatus.analysis === 'finish';
  const isError =
    stepStatus.dataPrep === 'error' ||
    stepStatus.execution === 'error' ||
    stepStatus.analysis === 'error';
  const isStopped = errorMessage?.includes('已终止') || errorMessage?.includes('已取消');

  return (
    <Modal
      title="回测进度"
      open={visible}
      onCancel={onCancel}
      footer={null}
      width={600}
      closable={true}
      maskClosable={false}
      destroyOnHidden
    >
      <Steps
        direction="vertical"
        current={currentStep}
        items={steps}
        style={{ marginTop: '16px' }}
      />

      {/* 总体进度 */}
      <Card
        size="small"
        style={{
          marginTop: '24px',
          background: isError ? '#fff2f0' : isFinished ? '#f6ffed' : '#e6f7ff',
          borderColor: isError ? '#ffccc7' : isFinished ? '#b7eb8f' : '#91d5ff',
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>
            {isError ? (isStopped ? '回测已终止' : '回测失败') : isFinished ? '回测完成' : '总体进度'}
          </Text>
          <Progress
            percent={Number(((progressData.overall || 0)).toFixed(2))}
            status={isError ? 'exception' : isFinished ? 'success' : 'active'}
            strokeColor={
              isError
                ? '#ff4d4f'
                : {
                    '0%': '#108ee9',
                    '100%': '#87d068',
                  }
            }
          />
          {isFinished && (
            <Text type="success" style={{ textAlign: 'center', display: 'block' }}>
              回测已成功完成！
            </Text>
          )}
          {isError && !isStopped && (
            <Text type="danger" style={{ textAlign: 'center', display: 'block' }}>
              回测过程中发生错误，请检查配置后重试
            </Text>
          )}
          {isStopped && (
            <Text type="warning" style={{ textAlign: 'center', display: 'block' }}>
              回测已被用户终止
            </Text>
          )}
        </Space>
      </Card>

      {/* 终止回测按钮 */}
      {isRunning && !isFinished && !isError && onStop && (
        <div style={{ marginTop: '24px', textAlign: 'center' }}>
          <Popconfirm
            title="确认终止回测？"
            description="终止后无法恢复，已执行的回测结果将保留。"
            onConfirm={onStop}
            okText="确认终止"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="终止当前回测进程">
              <Button
                type="primary"
                danger
                icon={<StopOutlined />}
                size="large"
                style={{ minWidth: '140px' }}
              >
                终止回测
              </Button>
            </Tooltip>
          </Popconfirm>
        </div>
      )}
    </Modal>
  );
};

export default BacktestProgressModal;
