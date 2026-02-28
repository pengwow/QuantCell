/**
 * 最大回撤图表组件
 * 功能：使用ECharts展示最大回撤，红色柱状图
 * 适用场景：回测风险分析、投资组合风险评估等
 */
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

// 组件属性接口
export interface DrawdownChartProps {
  value: number;
  height?: string | number;
  title?: string;
}

const DrawdownChart = ({ value, height = '300px', title = '最大回撤' }: DrawdownChartProps) => {
  // 将值转换为百分比显示
  const percentageValue = Math.abs(value) * 100;

  const option: EChartsOption = {
    // 图表标题
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: {
        fontSize: 14,
        fontWeight: 'normal',
      },
    },
    // 提示框
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
      formatter: () => `最大回撤: ${percentageValue.toFixed(2)}%`,
    },
    // 网格配置
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '20%',
      containLabel: true,
    },
    // X轴配置
    xAxis: {
      type: 'category',
      data: ['最大回撤'],
      axisTick: {
        alignWithLabel: true,
      },
      axisLabel: {
        show: false,
      },
    },
    // Y轴配置
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: {
        formatter: '{value}%',
      },
      splitLine: {
        lineStyle: {
          type: 'dashed',
        },
      },
    },
    // 数据系列
    series: [
      {
        name: '最大回撤',
        type: 'bar',
        barWidth: '40%',
        data: [percentageValue],
        itemStyle: {
          color: '#ff4d4f', // 红色
          borderRadius: [4, 4, 0, 0],
        },
        // 标签显示
        label: {
          show: true,
          position: 'top',
          formatter: () => `${percentageValue.toFixed(2)}%`,
          fontSize: 16,
          fontWeight: 'bold',
          color: '#ff4d4f',
        },
        // 初始动画
        animationDuration: 1000,
        animationEasing: 'elasticOut',
      },
    ],
    // 工具栏
    toolbox: {
      feature: {
        saveAsImage: {
          title: '保存图片',
        },
      },
      right: 20,
    },
  };

  return (
    <ReactECharts
      option={option}
      style={{ height, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
};

export default DrawdownChart;
