/**
 * 收益率曲线图表组件
 * 功能：使用ECharts展示权益曲线，面积图样式
 * 适用场景：回测结果、投资组合收益展示等
 */
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

// 权益数据接口
export interface EquityData {
  datetime: string;
  Equity: number;
}

// 组件属性接口
export interface EquityChartProps {
  data: EquityData[];
  height?: string | number;
  title?: string;
}

const EquityChart = ({ data, height = '400px', title = '权益曲线' }: EquityChartProps) => {
  // 提取时间和权益值
  const dates = data.map((item) => item.datetime);
  const equityValues = data.map((item) => item.Equity);

  // 计算最小值和最大值用于Y轴范围
  const minEquity = Math.min(...equityValues);
  const maxEquity = Math.max(...equityValues);
  const padding = (maxEquity - minEquity) * 0.1;

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
        type: 'cross',
        label: {
          backgroundColor: '#6a7985',
        },
      },
      formatter: (params: any) => {
        const param = params[0];
        return `${param.name}<br/>权益: ${param.value.toFixed(2)}`;
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
      axisLabel: {
        formatter: (value: string) => {
          // 简化日期显示
          return value.slice(0, 10);
        },
        rotate: 30,
      },
    },
    // Y轴配置
    yAxis: {
      type: 'value',
      scale: true,
      min: Math.max(0, minEquity - padding),
      max: maxEquity + padding,
      axisLabel: {
        formatter: (value: number) => value.toFixed(0),
      },
    },
    // 数据系列
    series: [
      {
        name: '权益',
        type: 'line',
        data: equityValues,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 2,
          color: '#1890ff',
        },
        // 面积图样式
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              {
                offset: 0,
                color: 'rgba(24, 144, 255, 0.4)',
              },
              {
                offset: 1,
                color: 'rgba(24, 144, 255, 0.05)',
              },
            ],
          },
        },
        // 初始动画
        animationDuration: 1000,
        animationEasing: 'cubicOut',
      },
    ],
    // 工具栏
    toolbox: {
      feature: {
        saveAsImage: {
          title: '保存图片',
        },
        dataZoom: {
          title: {
            zoom: '区域缩放',
            back: '缩放还原',
          },
        },
      },
      right: 20,
    },
    // 数据缩放
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
      {
        start: 0,
        end: 100,
        height: 20,
        bottom: 0,
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
