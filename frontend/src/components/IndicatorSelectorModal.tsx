/**
 * 指标选择弹窗组件
 * 整合内置指标和自定义指标，提供统一的选择界面
 */

import React, { useState } from 'react';
import {
  LineChartOutlined,
  BarChartOutlined,
  AreaChartOutlined,
  DotChartOutlined,
  RobotOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  FundOutlined,
} from '@ant-design/icons';
import {
  Modal,
  Button,
  Card,
  Tooltip,
  Tag,
  message,
  Empty,
  Divider,
} from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useIndicators,
  builtInIndicators,
  type Indicator,
  type ActiveIndicator,
} from '../hooks/useIndicators';
import IndicatorEditor from './IndicatorEditor';

interface IndicatorSelectorModalProps {
  visible: boolean;
  onClose: () => void;
  activeIndicators: ActiveIndicator[];
  onToggleIndicator: (indicator: Indicator, params?: Record<string, any>) => void;
}

// 指标类型图标映射
const indicatorTypeIcons: Record<string, React.ReactNode> = {
  line: <LineChartOutlined />,
  macd: <BarChartOutlined />,
  band: <AreaChartOutlined />,
  adx: <DotChartOutlined />,
};

const IndicatorSelectorModal: React.FC<IndicatorSelectorModalProps> = ({
  visible,
  onClose,
  activeIndicators,
  onToggleIndicator,
}) => {
  const { t } = useTranslation();
  const { indicators, loading, deleteIndicator, fetchIndicators } = useIndicators();
  const [editorVisible, setEditorVisible] = useState(false);
  const [editingIndicator, setEditingIndicator] = useState<Indicator | null>(null);

  // 检查指标是否已激活
  const isIndicatorActive = (indicatorId: number | string) => {
    return activeIndicators.some((ind) => ind.id === indicatorId);
  };

  // 处理内置指标点击
  const handleBuiltInClick = (indicator: (typeof builtInIndicators)[0]) => {
    // 内置指标保持字符串ID，以便ChartPage正确识别
    const mockIndicator: Indicator = {
      id: indicator.id as unknown as number,
      name: indicator.shortName,
      description: indicator.name,
      code: '',
      user_id: 0,
      is_buy: 0,
      end_time: 1,
      publish_to_community: 0,
      pricing_type: 'free',
      price: 0,
      is_encrypted: 0,
    };

    // 传递内置指标标记和原始ID
    onToggleIndicator(mockIndicator, { ...indicator.defaultParams, _builtInId: indicator.id });
    onClose();
  };

  // 处理自定义指标点击
  const handleCustomIndicatorClick = (indicator: Indicator) => {
    onToggleIndicator(indicator);
    onClose();
  };

  // 打开编辑器创建新指标
  const handleCreateIndicator = () => {
    setEditingIndicator(null);
    setEditorVisible(true);
  };

  // 编辑指标
  const handleEditIndicator = (indicator: Indicator, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingIndicator(indicator);
    setEditorVisible(true);
  };

  // 删除指标
  const handleDeleteIndicator = async (indicator: Indicator, e: React.MouseEvent) => {
    e.stopPropagation();
    Modal.confirm({
      title: t('indicator.deleteConfirmTitle', '确认删除'),
      content: t('indicator.deleteConfirmContent', '确定要删除指标 "{{name}}" 吗？此操作不可撤销。', { name: indicator.name }),
      okText: t('common.delete', '删除'),
      okType: 'danger',
      cancelText: t('common.cancel', '取消'),
      onOk: async () => {
        try {
          await deleteIndicator(indicator.id);
          message.success(t('indicator.deleteSuccess', '删除成功'));
        } catch {
          message.error(t('indicator.deleteError', '删除失败'));
        }
      },
    });
  };

  // 保存指标后刷新列表
  const handleSaveIndicator = () => {
    fetchIndicators();
    setEditorVisible(false);
  };

  return (
    <>
      {/* 指标编辑器弹窗 */}
      <IndicatorEditor
        visible={editorVisible}
        editingIndicator={editingIndicator}
        onClose={() => setEditorVisible(false)}
        onSave={handleSaveIndicator}
      />

      {/* 指标选择主弹窗 */}
      <Modal
        title={
          <div className="indicator-modal-title">
            <FundOutlined />
            <span>{t('indicator.selectTitle', '选择技术指标')}</span>
          </div>
        }
        open={visible}
        onCancel={onClose}
        footer={null}
        width={640}
        className="indicator-selector-modal"
        centered
      >
        <div className="indicator-selector-content">
          {/* 内置指标区域 */}
          <Card
            size="small"
            title={
              <div className="indicator-section-header">
                <LineChartOutlined className="section-icon" />
                <span>{t('indicator.builtIn', '内置指标')}</span>
              </div>
            }
            className="indicator-section-card"
            variant="borderless"
          >
            <div className="built-in-indicators-grid">
              {builtInIndicators.map((indicator) => {
                const isActive = isIndicatorActive(indicator.id);
                return (
                  <Tooltip key={indicator.id} title={indicator.name} placement="top">
                    <Button
                      type={isActive ? 'primary' : 'default'}
                      size="middle"
                      icon={indicatorTypeIcons[indicator.type] || <LineChartOutlined />}
                      onClick={() => handleBuiltInClick(indicator)}
                      className={`indicator-grid-btn ${isActive ? 'active' : ''}`}
                    >
                      {indicator.shortName}
                    </Button>
                  </Tooltip>
                );
              })}
            </div>
          </Card>

          <Divider className="indicator-divider" />

          {/* 自定义指标区域 */}
          <Card
            size="small"
            title={
              <div className="indicator-section-header">
                <RobotOutlined className="section-icon" />
                <span>{t('indicator.custom', '自定义指标')}</span>
              </div>
            }
            extra={
              <Button
                type="primary"
                size="small"
                icon={<PlusOutlined />}
                onClick={handleCreateIndicator}
              >
                {t('indicator.create', '创建')}
              </Button>
            }
            className="indicator-section-card"
            variant="borderless"
            loading={loading}
          >
            {indicators.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('indicator.noCustomIndicators', '暂无自定义指标')}
                className="indicator-empty"
              />
            ) : (
              <div className="custom-indicators-list">
                {indicators.map((indicator) => {
                  const isActive = isIndicatorActive(indicator.id);
                  return (
                    <div
                      key={indicator.id}
                      className={`custom-indicator-item ${isActive ? 'active' : ''}`}
                      onClick={() => handleCustomIndicatorClick(indicator)}
                    >
                      <div className="custom-indicator-info">
                        <div className="custom-indicator-name">
                          {indicator.name}
                          {isActive && (
                            <Tag color="success" className="running-tag">
                              {t('indicator.running', '运行中')}
                            </Tag>
                          )}
                        </div>
                        <div className="custom-indicator-desc">
                          {indicator.description || t('indicator.noDescription', '暂无描述')}
                        </div>
                      </div>
                      <div className="custom-indicator-actions">
                        <Tooltip title={isActive ? t('indicator.stop', '停止') : t('indicator.start', '启动')}>
                          <Button
                            type="text"
                            size="small"
                            icon={isActive ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCustomIndicatorClick(indicator);
                            }}
                          />
                        </Tooltip>
                        <Tooltip title={t('common.edit', '编辑')}>
                          <Button
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={(e) => handleEditIndicator(indicator, e)}
                          />
                        </Tooltip>
                        <Tooltip title={t('common.delete', '删除')}>
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={(e) => handleDeleteIndicator(indicator, e)}
                          />
                        </Tooltip>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      </Modal>
    </>
  );
};

export default IndicatorSelectorModal;
