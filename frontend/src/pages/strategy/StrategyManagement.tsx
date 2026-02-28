import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Space, Tag, Tooltip, Modal, message, Spin } from 'antd';
import { EditOutlined, DeleteOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { strategyApi } from '../../api';
import type { Strategy } from '../../types';
import { useTranslation } from 'react-i18next';
import { useResponsive } from '../../hooks/useResponsive';
import { setPageTitle } from '@/router';
import PageContainer from '@/components/PageContainer';

const { confirm } = Modal;

/**
 * 策略管理页面组件
 * 功能：展示策略列表，支持编辑、删除、回测等操作
 */
const StrategyManagement = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { isMobile, isTablet } = useResponsive();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('strategy_management'));
  }, [t]);

  // 加载策略列表
  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getStrategies() as { strategies: Strategy[] };
      if (response && response.strategies) {
        setStrategies(response.strategies);
      }
    } catch (error) {
      console.error('加载策略列表失败:', error);
      message.error('加载策略列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 组件挂载时加载策略列表
  useEffect(() => {
    loadStrategies();
  }, []);

  // 创建新策略
  const handleCreateStrategy = () => {
    navigate('/strategy-editor');
  };

  // 编辑策略
  const handleEditStrategy = (strategy: Strategy) => {
    navigate(`/strategy-editor/${strategy.name}`);
  };

  // 删除策略
  const handleDeleteStrategy = (strategy: Strategy) => {
    confirm({
      title: t('confirm_delete_strategy') || '确认删除策略',
      content: t('delete_strategy_confirm_msg', { name: strategy.name }) || `确定要删除策略 "${strategy.name}" 吗？`,
      okText: t('delete') || '删除',
      okType: 'danger',
      cancelText: t('cancel') || '取消',
      onOk: async () => {
        try {
          setLoading(true);
          await strategyApi.deleteStrategy(strategy.name);
          message.success('策略删除成功');
          loadStrategies();
        } catch (error) {
          console.error('删除策略失败:', error);
          message.error('删除策略失败');
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // 回测策略
  const handleBacktestStrategy = (strategy: Strategy) => {
    navigate('/backtest-config', { state: { strategy, showConfig: true } });
  };

  // 安全的日期格式化函数
  const formatDate = (dateString: string | undefined): string => {
    if (!dateString) {
      return '';
    }
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return '';
      }
      return date.toLocaleString();
    } catch (error) {
      console.error('日期解析错误:', error);
      return '';
    }
  };

  return (
    <PageContainer title={t('strategy_management')}>
      <div className="flex justify-between items-center mb-4">
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreateStrategy}
        >
          {t('create_strategy') || '新建策略'}
        </Button>
      </div>

      <Spin spinning={loading} tip={t('loading') || '加载中...'}>
        <div
          className="grid gap-4"
          style={{
            gridTemplateColumns: isMobile
              ? '1fr'
              : isTablet
                ? 'repeat(auto-fill, minmax(280px, 1fr))'
                : 'repeat(auto-fill, minmax(350px, 1fr))',
          }}
        >
          {strategies.length > 0 ? (
            strategies.map((strategy) => (
              <Card
                key={strategy.name}
                title={
                  <Space wrap>
                    <span>{strategy.name}</span>
                    <Tag color="blue">v{(strategy as any).version || '1.0.0'}</Tag>
                  </Space>
                }
                extra={
                  <Space>
                    <Tooltip title={t('edit_strategy') || '编辑策略'}>
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        onClick={() => handleEditStrategy(strategy)}
                      />
                    </Tooltip>
                    <Tooltip title={t('delete_strategy') || '删除策略'}>
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDeleteStrategy(strategy)}
                      />
                    </Tooltip>
                    <Tooltip title={t('backtest_strategy') || '回测策略'}>
                      <Button
                        type="text"
                        icon={<PlayCircleOutlined />}
                        onClick={() => handleBacktestStrategy(strategy)}
                      />
                    </Tooltip>
                  </Space>
                }
                hoverable
                variant="borderless"
                className="h-full flex flex-col rounded-lg"
                style={{
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                }}
              >
                <div className="mb-4 flex-1">
                  <div className="mb-2 font-medium">{t('strategy_description') || '策略描述'}</div>
                  <Tooltip title={strategy.description} placement="topLeft">
                    <div
                      className="overflow-hidden text-ellipsis"
                      style={{
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical',
                      }}
                    >
                      {strategy.description || t('no_description') || '暂无描述'}
                    </div>
                  </Tooltip>
                </div>

                <div className="mt-auto">
                  <Space direction="vertical" size="small" className="w-full">
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>{t('created_at') || '创建时间'}:</span>
                      <span>{formatDate((strategy as any).created_at)}</span>
                    </div>
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>{t('updated_at') || '更新时间'}:</span>
                      <span>{formatDate((strategy as any).updated_at)}</span>
                    </div>
                  </Space>
                </div>
              </Card>
            ))
          ) : (
            <Card
              variant="borderless"
              className="text-center rounded-lg"
              style={{
                gridColumn: '1 / -1',
                padding: '60px 0',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
              }}
            >
              <div className="mb-4">{t('no_strategies') || '暂无策略'}</div>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateStrategy}>
                {t('create_first_strategy') || '创建第一个策略'}
              </Button>
            </Card>
          )}
        </div>
      </Spin>
    </PageContainer>
  );
};

export default StrategyManagement;
