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

  // 判断是否在列表页（列表页不需要返回按钮）- 回测首页已删除，所有页面都显示返回按钮
  const isListPage = false;

  // 返回处理 - 优先使用 URL 参数中的 returnUrl，否则返回上一页
  const handleBack = () => {
    const searchParams = new URLSearchParams(location.search);
    const returnUrl = searchParams.get('returnUrl');
    if (returnUrl) {
      navigate(decodeURIComponent(returnUrl));
    } else {
      navigate(-1);
    }
  };

  return (
    <div>
      {/* 页面标题区域 - 仅在非列表页显示返回按钮 */}
      {!isListPage && (
        <div className="px-6 pt-4 pb-2">
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

      {/* 内容区域 - 子页面使用 PageContainer 控制边距 */}
      <Outlet />
    </div>
  );
};

export default BacktestLayout;
