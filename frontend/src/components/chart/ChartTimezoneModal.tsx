import React from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from 'antd';

/**
 * 时区列表：与 klinecharts-pro 的 timezone-modal 一致（18 项，IANA 时区名）
 * ponytail: 偏移量按标准时写死，不处理夏令时——只做显示用途，
 * 真正的换算交给 klinecharts 的 setTimezone。
 */
const TIMEZONES: { value: string; label: string; offset: string }[] = [
  { value: 'Etc/UTC', label: 'UTC', offset: 'UTC+0' },
  { value: 'Pacific/Honolulu', label: '檀香山', offset: 'UTC-10' },
  { value: 'America/Juneau', label: '朱诺', offset: 'UTC-8' },
  { value: 'America/Los_Angeles', label: '洛杉矶', offset: 'UTC-8' },
  { value: 'America/Chicago', label: '芝加哥', offset: 'UTC-6' },
  { value: 'America/Toronto', label: '多伦多', offset: 'UTC-5' },
  { value: 'America/Sao_Paulo', label: '圣保罗', offset: 'UTC-3' },
  { value: 'Europe/London', label: '伦敦', offset: 'UTC+0' },
  { value: 'Europe/Berlin', label: '柏林', offset: 'UTC+1' },
  { value: 'Asia/Bahrain', label: '巴林', offset: 'UTC+3' },
  { value: 'Asia/Dubai', label: '迪拜', offset: 'UTC+4' },
  { value: 'Asia/Ashkhabad', label: '阿什哈巴德', offset: 'UTC+5' },
  { value: 'Asia/Almaty', label: '阿拉木图', offset: 'UTC+6' },
  { value: 'Asia/Bangkok', label: '曼谷', offset: 'UTC+7' },
  { value: 'Asia/Shanghai', label: '上海', offset: 'UTC+8' },
  { value: 'Asia/Tokyo', label: '东京', offset: 'UTC+9' },
  { value: 'Australia/Sydney', label: '悉尼', offset: 'UTC+10' },
  { value: 'Pacific/Norfolk', label: '诺福克', offset: 'UTC+11' },
];

interface ChartTimezoneModalProps {
  open: boolean;
  onClose: () => void;
  /** 当前时区（IANA） */
  current: string;
  onSelect: (timezone: string) => void;
}

const ChartTimezoneModal: React.FC<ChartTimezoneModalProps> = ({
  open,
  onClose,
  current,
  onSelect,
}) => {
  const { t } = useTranslation();

  return (
    <Modal
      title={t('chart.timezone.title', '时区')}
      open={open}
      onCancel={onClose}
      footer={null}
      width={320}
    >
      <ul className="chart-tz-list">
        {TIMEZONES.map((tz) => (
          <li
            key={tz.value}
            className={tz.value === current ? 'selected' : ''}
            onClick={() => {
              onSelect(tz.value);
              onClose();
            }}
          >
            <span>{tz.label}</span>
            <span className="chart-tz-offset">{tz.offset}</span>
          </li>
        ))}
      </ul>
    </Modal>
  );
};

export default ChartTimezoneModal;
