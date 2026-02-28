/**
 * 指标卡片组件
 * 功能：显示指标的标签和数值，根据类型显示不同颜色
 * 适用场景：回测结果、仪表盘、数据展示等
 */
import { Card, Typography } from 'antd';

const { Text } = Typography;

// 组件属性接口
export interface MetricCardProps {
  label: string;
  value: string | number;
  type?: 'positive' | 'negative' | 'neutral';
}

/**
 * 根据类型获取对应的颜色值
 */
const getColorByType = (type: MetricCardProps['type']): string => {
  switch (type) {
    case 'positive':
      return '#52c41a'; // 绿色 - 正向指标
    case 'negative':
      return '#ff4d4f'; // 红色 - 负向指标
    case 'neutral':
    default:
      return 'rgba(0, 0, 0, 0.88)'; // 默认颜色
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
      bodyStyle={{
        padding: '16px 12px',
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
