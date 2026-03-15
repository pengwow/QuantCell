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
  EyeOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

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
    message?: string;
  };
  execution?: {
    percent: number;
    current: number;
    total: number;
    currentSymbol?: string;
    message?: string;
  };
  analysis?: {
    percent?: number;
    message?: string;
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
  taskId?: string; // 回测任务ID
  strategyName?: string; // 策略名称
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
  taskId,
  strategyName,
}: BacktestProgressModalProps) => {
  const navigate = useNavigate();
  const { t } = useTranslation();

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
      title: t('data_preparation') || '数据准备',
      icon: getStepIcon(stepStatus.dataPrep, <DatabaseOutlined />),
      description: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {stepStatus.dataPrep === 'process' && progressData.dataPrep && (
            <>
              {progressData.dataPrep.downloading ? (
                <>
                  <Text type="warning">
                    <DownloadOutlined /> {progressData.dataPrep.message || (t('data_missing_auto_download') || '检测到数据缺失，正在自动下载...')}
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
                  <Text type="secondary">{progressData.dataPrep.message || (t('checking_data_integrity') || '正在检查数据完整性...')}</Text>
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
              message={t('preparation_failed') || '数据准备失败'}
              description={errorMessage || (t('data_integrity_check_failed') || '数据完整性检查或下载失败')}
              type="error"
              showIcon
            />
          )}
          {stepStatus.dataPrep === 'finish' && (
            <Text type="success" style={{ fontSize: '12px' }}>
              <CheckCircleFilled /> {progressData.dataPrep?.message || (t('data_integrity_passed') || '数据完整性检查通过')}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: t('executing_backtest') || '执行回测',
      icon: getStepIcon(stepStatus.execution, <PlayCircleOutlined />),
      description: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {stepStatus.execution === 'process' && progressData.execution && (
            <>
              <Text type="secondary">
                {progressData.execution.message || (t('backtest_executing', { progress: progressData.execution.currentSymbol || t('loading') || '准备中' }) || `正在回测: ${progressData.execution.currentSymbol || '准备中'}`)}
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
              message={t('backtest_execute_failed') || '回测执行失败'}
              description={errorMessage || (t('backtest_execute_error') || '回测过程中发生错误')}
              type="error"
              showIcon
            />
          )}
          {stepStatus.execution === 'finish' && (
            <Text type="success" style={{ fontSize: '12px' }}>
              <CheckCircleFilled /> {progressData.execution?.message || (t('backtest_execute_complete') || '回测执行完成')}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: t('result_statistics') || '结果统计',
      icon: getStepIcon(stepStatus.analysis, <BarChartOutlined />),
      description: (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {stepStatus.analysis === 'process' && (
            <>
              <Text type="secondary">{progressData.analysis?.message || (t('generating_report') || '正在生成统计报告...')}</Text>
              {progressData.analysis?.percent !== undefined && (
                <Progress
                  percent={progressData.analysis.percent}
                  size="small"
                  status="active"
                />
              )}
            </>
          )}
          {stepStatus.analysis === 'error' && (
            <Alert
              message={t('statistics_failed') || '结果统计失败'}
              description={errorMessage || (t('generate_report_error') || '生成统计报告时发生错误')}
              type="error"
              showIcon
            />
          )}
          {stepStatus.analysis === 'finish' && (
            <Text type="success" style={{ fontSize: '12px' }}>
              <CheckCircleFilled /> {progressData.analysis?.message || (t('statistics_complete') || '结果统计完成')}
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

  // 跳转到策略管理-回测记录页面
  const handleViewResult = () => {
    // 构建查询参数
    const params = new URLSearchParams();
    params.set('tab', 'backtests');
    if (taskId) {
      params.set('taskId', taskId);
    }
    if (strategyName) {
      params.set('strategy', strategyName);
    }

    // 关闭弹窗并跳转
    onCancel();
    navigate(`/strategy-management?${params.toString()}`);
  };

  return (
    <Modal
      title={t('backtest_progress') || '回测进度'}
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
          background: isError ? 'rgba(255, 241, 240, 0.1)' : isFinished ? 'rgba(246, 255, 237, 0.1)' : 'rgba(230, 247, 255, 0.1)',
          borderColor: isError ? '#ffccc7' : isFinished ? '#b7eb8f' : '#91d5ff',
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>
            {isError ? (isStopped ? t('backtest_terminated') || '回测已终止' : t('error') || '回测失败') : isFinished ? t('backtest_completed') || '回测完成' : t('overall_progress') || '总体进度'}
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
              {t('backtest_success_complete') || '回测已成功完成！'}
            </Text>
          )}
          {isError && !isStopped && (
            <Text type="danger" style={{ textAlign: 'center', display: 'block' }}>
              {t('backtest_error_occurred') || '回测过程中发生错误，请检查配置后重试'}
            </Text>
          )}
          {isStopped && (
            <Text type="warning" style={{ textAlign: 'center', display: 'block' }}>
              {t('backtest_user_terminated_status') || '回测已被用户终止'}
            </Text>
          )}
        </Space>
      </Card>

      {/* 操作按钮区域 */}
      <div style={{ marginTop: '24px', textAlign: 'center' }}>
        {/* 终止回测按钮 - 仅在运行中显示 */}
        {isRunning && !isFinished && !isError && onStop && (
          <Popconfirm
            title={t('confirm_terminate_backtest') || '确认终止回测？'}
            description={t('terminate_warning') || '终止后无法恢复，已执行的回测结果将保留。'}
            onConfirm={onStop}
            okText={t('confirm_terminate') || '确认终止'}
            cancelText={t('cancel') || '取消'}
            okButtonProps={{ danger: true }}
          >
            <Tooltip title={t('terminate_current_backtest') || '终止当前回测进程'}>
              <Button
                type="primary"
                danger
                icon={<StopOutlined />}
                size="large"
                style={{ minWidth: '140px' }}
              >
                {t('terminate_backtest_btn') || '终止回测'}
              </Button>
            </Tooltip>
          </Popconfirm>
        )}

        {/* 查看结果按钮 - 仅在完成时显示 */}
        {isFinished && (
          <Button
            type="primary"
            icon={<EyeOutlined />}
            size="large"
            style={{ minWidth: '140px' }}
            onClick={handleViewResult}
          >
            {t('view_result') || '查看结果'}
          </Button>
        )}
      </div>
    </Modal>
  );
};

export default BacktestProgressModal;
