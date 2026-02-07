/**
 * 指标面板组件
 * 显示内置指标和自定义指标列表，支持启动/停止指标
 */

import React, { useState } from 'react';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  RobotOutlined,
  LineChartOutlined,
  BarChartOutlined,
  AreaChartOutlined,
  DotChartOutlined,
} from '@ant-design/icons';
import { Button, Card, List, Tag, Tooltip, Modal, Input, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { useIndicators, builtInIndicators, type Indicator, type ActiveIndicator } from '../hooks/useIndicators';

interface IndicatorPanelProps {
  activeIndicators: ActiveIndicator[];
  onToggleIndicator: (indicator: Indicator, params?: Record<string, any>) => void;
  onOpenEditor: () => void;
  onEditIndicator: (indicator: Indicator) => void;
}

// 指标类型图标映射
const indicatorTypeIcons: Record<string, React.ReactNode> = {
  line: <LineChartOutlined />,
  macd: <BarChartOutlined />,
  band: <AreaChartOutlined />,
  adx: <DotChartOutlined />,
};



const IndicatorPanel: React.FC<IndicatorPanelProps> = ({
  activeIndicators,
  onToggleIndicator,
  onOpenEditor,
  onEditIndicator,
}) => {
  const { t } = useTranslation();
  const { indicators, loading, deleteIndicator } = useIndicators();
  const [paramModalVisible, setParamModalVisible] = useState(false);
  const [selectedIndicator, setSelectedIndicator] = useState<Indicator | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, any>>({});

  // 检查指标是否已激活
  const isIndicatorActive = (indicatorId: number | string) => {
    return activeIndicators.some(ind => ind.id === indicatorId);
  };

  // 处理内置指标点击
  const handleBuiltInClick = (indicator: typeof builtInIndicators[0]) => {
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

    if (Object.keys(indicator.defaultParams).length > 0) {
      setSelectedIndicator(mockIndicator);
      setParamValues(indicator.defaultParams);
      setParamModalVisible(true);
    } else {
      onToggleIndicator(mockIndicator);
    }
  };

  // 处理自定义指标点击
  const handleCustomIndicatorClick = (indicator: Indicator) => {
    if (isIndicatorActive(indicator.id)) {
      // 如果已激活，则停止
      onToggleIndicator(indicator);
    } else {
      // 如果未激活，启动
      setSelectedIndicator(indicator);
      setParamValues({});
      setParamModalVisible(true);
    }
  };

  // 确认参数并启动指标
  const handleConfirmParams = () => {
    if (selectedIndicator) {
      onToggleIndicator(selectedIndicator, paramValues);
      setParamModalVisible(false);
      setSelectedIndicator(null);
    }
  };

  // 删除指标
  const handleDelete = async (indicator: Indicator, e: React.MouseEvent) => {
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

  // 编辑指标
  const handleEdit = (indicator: Indicator, e: React.MouseEvent) => {
    e.stopPropagation();
    onEditIndicator(indicator);
  };

  return (
    <div className="indicator-panel">
      {/* 内置指标区域 */}
      <Card
        size="small"
        title={
          <div className="indicator-section-title">
            <LineChartOutlined />
            <span>{t('indicator.builtIn', '内置指标')}</span>
          </div>
        }
        className="indicator-section"
      >
        <div className="built-in-indicators">
          {builtInIndicators.map(indicator => (
            <Tooltip key={indicator.id} title={indicator.name} placement="left">
              <Button
                type={isIndicatorActive(indicator.id) ? 'primary' : 'default'}
                size="small"
                icon={indicatorTypeIcons[indicator.type] || <LineChartOutlined />}
                onClick={() => handleBuiltInClick(indicator)}
                className="indicator-btn"
                style={{ margin: '2px' }}
              >
                {indicator.shortName}
              </Button>
            </Tooltip>
          ))}
        </div>
      </Card>

      {/* 自定义指标区域 */}
      <Card
        size="small"
        title={
          <div className="indicator-section-title">
            <RobotOutlined />
            <span>{t('indicator.custom', '自定义指标')}</span>
          </div>
        }
        extra={
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={onOpenEditor}
          >
            {t('indicator.create', '创建')}
          </Button>
        }
        className="indicator-section"
      >
        <List
          size="small"
          loading={loading}
          dataSource={indicators}
          locale={{ emptyText: t('indicator.noCustomIndicators', '暂无自定义指标') }}
          renderItem={(indicator) => (
            <List.Item
              className={`indicator-list-item ${isIndicatorActive(indicator.id) ? 'active' : ''}`}
              onClick={() => handleCustomIndicatorClick(indicator)}
              actions={[
                <Tooltip key="toggle" title={isIndicatorActive(indicator.id) ? t('indicator.stop', '停止') : t('indicator.start', '启动')}>
                  <Button
                    type="text"
                    size="small"
                    icon={isIndicatorActive(indicator.id) ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCustomIndicatorClick(indicator);
                    }}
                  />
                </Tooltip>,
                <Tooltip key="edit" title={t('common.edit', '编辑')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={(e) => handleEdit(indicator, e)}
                  />
                </Tooltip>,
                <Tooltip key="delete" title={t('common.delete', '删除')}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => handleDelete(indicator, e)}
                  />
                </Tooltip>,
              ]}
            >
              <List.Item.Meta
                title={
                  <div className="indicator-item-title">
                    <span>{indicator.name}</span>
                    {isIndicatorActive(indicator.id) && (
                      <Tag color="success">{t('indicator.running', '运行中')}</Tag>
                    )}
                  </div>
                }
                description={
                  <span className="indicator-item-desc">
                    {indicator.description || t('indicator.noDescription', '暂无描述')}
                  </span>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      {/* 参数配置弹窗 */}
      <Modal
        title={t('indicator.paramConfig', '指标参数配置')}
        open={paramModalVisible}
        onOk={handleConfirmParams}
        onCancel={() => setParamModalVisible(false)}
        okText={t('common.confirm', '确认')}
        cancelText={t('common.cancel', '取消')}
      >
        {selectedIndicator && (
          <div className="param-config-form">
            <div className="param-form-item">
              <label>{t('indicator.name', '指标名称')}</label>
              <Input value={selectedIndicator.name} disabled />
            </div>
            {Object.entries(paramValues).map(([key, value]) => (
              <div key={key} className="param-form-item">
                <label>{key}</label>
                <Input
                  type="number"
                  value={value}
                  onChange={(e) => setParamValues(prev => ({
                    ...prev,
                    [key]: parseInt(e.target.value) || value
                  }))}
                />
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default IndicatorPanel;
