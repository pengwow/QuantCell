import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button, Typography, Space } from 'antd';
import { IconArrowLeft } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

/**
 * 回测模块布局组件
 * 功能：提供统一的页面布局和导航，遵循应用标准设计系统
 */
const BacktestLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  // 判断是否在列表页（列表页不需要返回按钮）
  const isListPage = location.pathname === '/backtest' || location.pathname === '/backtest/';

  // 返回回测首页
  const handleBack = () => {
    navigate('/backtest');
  };

  return (
    <div className="px-6 py-4">
      {/* 页面标题区域 */}
      {!isListPage && (
        <div className="mb-6">
          <Space align="center" size="middle">
            <Button
              icon={<IconArrowLeft size="1.25em" stroke={1.5} />}
              onClick={handleBack}
              type="text"
            />
            <Title level={3} className="!m-0">
              {t('strategy_backtest') || '策略回测'}
            </Title>
          </Space>
        </div>
      )}

      {/* 内容区域 */}
      <Outlet />
    </div>
  );
};

export default BacktestLayout;
