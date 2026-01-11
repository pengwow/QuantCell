import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Space, Tag, Tooltip, Modal, message, Spin } from 'antd';
import { EditOutlined, DeleteOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { strategyApi } from '../api';
import type { Strategy } from '../types';
import { useTranslation } from 'react-i18next';

const { confirm } = Modal;

/**
 * 策略管理页面组件
 * 功能：展示策略列表，支持编辑、删除、回测等操作
 */
const StrategyManagement: React.FC = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const navigate = useNavigate();
  const { t } = useTranslation();

  // 加载策略列表
  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getStrategies();
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

  // 编辑策略
  const handleEditStrategy = (strategy: Strategy) => {
    navigate(`/strategy-editor/${strategy.name}`);
  };

  // 删除策略
  const handleDeleteStrategy = (strategy: Strategy) => {
    confirm({
      title: t('confirm_delete_strategy'),
      content: t('delete_strategy_confirm_msg', { name: strategy.name }),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          setLoading(true);
          // 调用删除策略的API
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
    navigate('/backtest', { state: { strategy, showConfig: true } });
  };

  // 创建新策略
  const handleCreateStrategy = () => {
    navigate('/strategy-editor');
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
    <div style={{ padding: '24px', minHeight: '100vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 500 }}>
          {t('strategy_management')}
        </h2>
        <Button 
          type="primary" 
          icon={<PlusOutlined />}
          onClick={handleCreateStrategy}
        >
          {t('create_strategy')}
        </Button>
      </div>

      <Spin spinning={loading} tip={t('loading')}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '24px' }}>
          {strategies.length > 0 ? (
            strategies.map((strategy) => (
              <Card 
                key={strategy.name} 
                title={
                  <Space>
                    <span>{strategy.name}</span>
                    <Tag color="blue">v{(strategy as any).version || '1.0.0'}</Tag>
                  </Space>
                }
                extra={
                  <Space>
                    <Tooltip title={t('edit_strategy')}>
                      <Button 
                        type="text" 
                        icon={<EditOutlined />} 
                        onClick={() => handleEditStrategy(strategy)}
                      />
                    </Tooltip>
                    <Tooltip title={t('delete_strategy')}>
                      <Button 
                        type="text" 
                        danger
                        icon={<DeleteOutlined />} 
                        onClick={() => handleDeleteStrategy(strategy)}
                      />
                    </Tooltip>
                    <Tooltip title={t('backtest_strategy')}>
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
                style={{ 
                  height: '100%', 
                  display: 'flex', 
                  flexDirection: 'column',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                  borderRadius: '8px'
                }}
              >
                <div style={{ marginBottom: '16px', flex: 1 }}>
                  <div style={{ marginBottom: '8px', fontWeight: 500 }}>{t('strategy_description')}</div>
                  <Tooltip title={strategy.description} placement="topLeft">
                    <div style={{ 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      display: '-webkit-box', 
                      WebkitLineClamp: 3, 
                      WebkitBoxOrient: 'vertical' 
                    }}>
                      {strategy.description || t('no_description')}
                    </div>
                  </Tooltip>
                </div>
                
                <div style={{ marginTop: 'auto' }}>
                  <Space orientation="vertical" size="small" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#666' }}>
                      <span>{t('created_at')}:</span>
                      <span>{formatDate((strategy as any).created_at)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#666' }}>
                      <span>{t('updated_at')}:</span>
                      <span>{formatDate((strategy as any).updated_at)}</span>
                    </div>
                  </Space>
                </div>
              </Card>
            ))
          ) : (
            <Card 
              bordered={false}
              style={{ 
                gridColumn: '1 / -1', 
                textAlign: 'center', 
                padding: '60px 0',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                borderRadius: '8px'
              }}
            >
              <div style={{ marginBottom: '16px' }}>{t('no_strategies')}</div>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateStrategy}>
                {t('create_first_strategy')}
              </Button>
            </Card>
          )}
        </div>
      </Spin>
    </div>
  );
};

export default StrategyManagement;