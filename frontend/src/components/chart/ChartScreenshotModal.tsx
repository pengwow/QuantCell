import React from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Modal } from 'antd';

interface ChartScreenshotModalProps {
  open: boolean;
  onClose: () => void;
  /** 由 klinecharts getConvertPictureUrl 生成的图片 dataURL */
  url: string;
}

/** 截图预览弹窗：对应 pro 的 screenshot-modal */
const ChartScreenshotModal: React.FC<ChartScreenshotModalProps> = ({ open, onClose, url }) => {
  const { t } = useTranslation();

  const handleSave = () => {
    // ponytail: 直接触发下载，不做 canvas 二次编码
    const link = document.createElement('a');
    link.href = url;
    link.download = 'chart-screenshot.jpeg';
    link.click();
  };

  return (
    <Modal
      title={t('chart.screenshot.title', '图表截图')}
      open={open}
      onCancel={onClose}
      footer={
        <Button type="primary" onClick={handleSave}>
          {t('chart.screenshot.save', '保存图片')}
        </Button>
      }
      width={560}
    >
      {url ? <img className="chart-screenshot-img" src={url} alt="chart screenshot" /> : null}
    </Modal>
  );
};

export default ChartScreenshotModal;
