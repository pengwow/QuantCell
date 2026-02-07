/**
 * 指标工具栏组件
 * 默认显示单个指标按钮，点击后弹出指标选择弹窗
 */

import React, { useState } from 'react';
import { FundOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { type Indicator, type ActiveIndicator } from '../hooks/useIndicators';
import IndicatorSelectorModal from './IndicatorSelectorModal';

interface IndicatorToolbarProps {
  activeIndicators: ActiveIndicator[];
  onToggleIndicator: (indicator: Indicator, params?: Record<string, any>) => void;
}

const IndicatorToolbar: React.FC<IndicatorToolbarProps> = ({
  activeIndicators,
  onToggleIndicator,
}) => {
  const { t } = useTranslation();
  const [modalVisible, setModalVisible] = useState(false);

  return (
    <>
      {/* 指标选择弹窗 */}
      <IndicatorSelectorModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        activeIndicators={activeIndicators}
        onToggleIndicator={onToggleIndicator}
      />

      {/* 默认显示的指标按钮 */}
      <div className="indicator-toolbar">
        <Tooltip title={t('indicator.selectTitle', '选择技术指标')} placement="bottom">
          <Button
            type={activeIndicators.length > 0 ? 'primary' : 'default'}
            size="small"
            icon={<FundOutlined />}
            onClick={() => setModalVisible(true)}
            className="indicator-main-btn"
          >
            {t('indicator.title', '指标')}
            {activeIndicators.length > 0 && (
              <span className="active-count">({activeIndicators.length})</span>
            )}
          </Button>
        </Tooltip>
      </div>
    </>
  );
};

export default IndicatorToolbar;
