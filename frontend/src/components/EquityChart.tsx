/**
 * 收益率曲线图表组件
 * 功能：使用ECharts展示权益曲线，支持结余(balance)和权益(equity)两根线
 * 适用场景：回测结果、投资组合收益展示等
 */
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

// 权益数据接口（支持后端返回的小写字段名）
export interface EquityData {
  datetime?: string;
  formatted_time?: string;
  Equity?: number;
  equity?: number;
  Balance?: number;
  balance?: number;
  Margin?: number;
  margin?: number;
  timestamp?: number;
}

// 组件属性接口
export interface EquityChartProps {
  data: EquityData[];
  height?: string | number;
  title?: string;
  isDark?: boolean; // 是否为暗色主题
}

const EquityChart = ({ data, height = '400px', isDark = false }: EquityChartProps) => {
  if (!data || data.length === 0) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>暂无数据</div>;
  }

  // 根据主题设置颜色
  const textColor = isDark ? '#ffffff' : '#333333';
  const axisColor = isDark ? '#888888' : '#666666';
  const gridColor = isDark ? '#333333' : '#eeeeee';

  // 提取时间（优先使用 formatted_time，其次是 datetime）
  const dates = data.map((item) => item.formatted_time || item.datetime || '');

  // 提取权益值（支持大小写字段名）
  const getEquityValue = (item: EquityData): number => {
    return item.equity !== undefined ? item.equity : (item.Equity !== undefined ? item.Equity : 0);
  };

  // 提取结余值（支持大小写字段名）
  const getBalanceValue = (item: EquityData): number => {
    return item.balance !== undefined ? item.balance : (item.Balance !== undefined ? item.Balance : 0);
  };

  // 检查数据是否包含字段（不仅检查第一个点，而是检查所有点）
  const hasEquityField = data.some(item => item.equity !== undefined || item.Equity !== undefined);
  const hasBalanceField = data.some(item => item.balance !== undefined || item.Balance !== undefined);

  // 提取数据
  const equityValues = data.map(getEquityValue);
  const balanceValues = data.map(getBalanceValue);

  // 计算最小值和最大值用于Y轴范围
  const allValues = [...equityValues, ...balanceValues].filter(v => v > 0);
  const minValue = allValues.length > 0 ? Math.min(...allValues) : 0;
  const maxValue = allValues.length > 0 ? Math.max(...allValues) : 100;
  const padding = (maxValue - minValue) * 0.1;

  // 构建数据系列 - 只要字段存在就显示，不管值是否相同
  const series: any[] = [];

  if (hasBalanceField) {
    // 结余线（可用余额，蓝色面积图）
    series.push({
      name: '结余',
      type: 'line',
      data: balanceValues,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 2,
        color: '#1890ff',
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(24, 144, 255, 0.4)' },
            { offset: 1, color: 'rgba(24, 144, 255, 0.05)' },
          ],
        },
      },
      animationDuration: 1000,
      animationEasing: 'cubicOut',
    });
  }

  if (hasEquityField) {
    // 权益线（账户总权益/净值，绿色虚线）
    series.push({
      name: '净值',
      type: 'line',
      data: equityValues,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 2,
        color: '#52c41a',
        type: 'dashed',
      },
      animationDuration: 1000,
      animationEasing: 'cubicOut',
    });
  }

  // 构建图例数据
  const legendData: string[] = [];
  if (hasBalanceField) legendData.push('结余');
  if (hasEquityField) legendData.push('净值');

  const option: EChartsOption = {
    // 不显示图表内部标题（使用卡片标题）
    title: {
      show: false,
    },
    // 图例
    legend: {
      data: legendData,
      top: 10,
      right: 20,
      show: true,
      textStyle: {
        color: textColor,
      },
    },
    // 提示框
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          backgroundColor: '#6a7985',
        },
      },
      formatter: (params: any) => {
        let result = `${params[0].name}<br/>`;
        params.forEach((param: any) => {
          result += `${param.marker} ${param.seriesName}: ${param.value.toFixed(2)}<br/>`;
        });
        return result;
      },
    },
    // 网格配置
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '15%',
      containLabel: true,
    },
    // X轴配置
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
      axisLine: {
        lineStyle: {
          color: axisColor,
        },
      },
      axisLabel: {
        color: textColor,
        formatter: (value: string) => {
          return value.slice(0, 10);
        },
        rotate: 30,
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: gridColor,
        },
      },
    },
    // Y轴配置
    yAxis: {
      type: 'value',
      scale: true,
      min: Math.max(0, minValue - padding),
      max: maxValue + padding,
      axisLine: {
        lineStyle: {
          color: axisColor,
        },
      },
      axisLabel: {
        color: textColor,
        formatter: (value: number) => value.toFixed(0),
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: gridColor,
        },
      },
    },
    // 数据系列
    series,
    // 工具栏已禁用（删除保存图片、区域缩放、缩放还原按钮）
    toolbox: {
      show: false,
    },
    // 数据缩放（仅保留内置缩放，删除下方拖拽条）
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      style={{ height, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
};

export default EquityChart;
