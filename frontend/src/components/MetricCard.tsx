/**
 * 指标卡片组件
 * 功能：显示指标的标签和数值，根据类型显示不同颜色
 * 适用场景：回测结果、仪表盘、数据展示等
 */
import { Card, Typography } from 'antd';
import { QUANT_COLORS } from '@/utils/colors';

const { Text } = Typography;

export interface MetricCardProps {
  label: string;
  value: string | number;
  type?: 'positive' | 'negative' | 'neutral';
}

// ponytail: 所有颜色统一从 colors.ts 取 QUANT_COLORS，禁止硬编码 antd v5 风格颜色
const getColorByType = (type: MetricCardProps['type']): string => {
  switch (type) {
    case 'positive': return QUANT_COLORS.positive;
    case 'negative': return QUANT_COLORS.negative;
    case 'neutral':
    default: return QUANT_COLORS.neutral;
  }
};

const MetricCard = ({ label, value, type = 'neutral' }: MetricCardProps) => {
  const color = getColorByType(type);

  return (
    <Card
      size="small"
      style={{
        textAlign: 'center',
        borderRadius: '8px',
      }}
      styles={{
        body: {
          padding: '16px 12px',
        },
      }}
    >
      <Text
        type="secondary"
        style={{
          display: 'block',
          fontSize: '12px',
          marginBottom: '8px',
        }}
      >
        {label}
      </Text>
      <Text
        strong
        style={{
          fontSize: '20px',
          color,
        }}
      >
        {value}
      </Text>
    </Card>
  );
};

export default MetricCard;
