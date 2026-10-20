/**
 * 收益率曲线图表组件
 * 功能：使用ECharts展示权益曲线，支持存款(balance)和净值(equity)两根线
 * 适用场景：回测结果、投资组合收益展示等
 */
import { useRef, useState, useEffect } from 'react';
import EChart from '@/components/EChart';
import type { EChartsOption, LineSeriesOption, TooltipComponentFormatterCallbackParams } from 'echarts';
import { theme } from 'antd';
import { useQuantColors } from '@/utils/colors';

// 权益数据接口（统一用小写字段：equity / balance / margin）
export interface EquityData {
  datetime?: string;
  formatted_time?: string;
  equity?: number;
  balance?: number;
  margin?: number;
  timestamp?: number;
}

// 组件属性接口
export interface EquityChartProps {
  data: EquityData[];
  height?: string | number;
  title?: string;
  isDark?: boolean; // 是否为暗色主题
  initialCash?: number; // 旧回测结果（无 balance 字段）的存款兜底水平线；有 balance 曲线时不使用
}

const EquityChart = ({ data, height = '400px', isDark: _isDark = false, initialCash }: EquityChartProps) => {
  const { token } = theme.useToken();
  const qc = useQuantColors();
  const chartWrapperRef = useRef<HTMLDivElement>(null);
  const [chartHeight, setChartHeight] = useState(0);

  // ResizeObserver 监听图表容器实际像素高度，用来自适应回撤子图刻度密度
  // （回撤子图只有总高的 ~22%，矮容器下 splitNumber 过大 → 刻度纵向堆叠重叠）
  useEffect(() => {
    const el = chartWrapperRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      setChartHeight(entries[0].contentRect.height);
    });
    ro.observe(el);
    // 首次 layout 后立即取一次，避免初始 0 导致 splitNumber 退回默认值
    setChartHeight(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  if (!data || data.length === 0) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>暂无数据</div>;
  }

  // ponytail: 所有颜色统一从 quantColors 派生

  // 自适应回撤子图 splitNumber：回撤子图高度 ≈ 总高 × 22%
  // 每个刻度标签 ~16px 字体 + ~10px 间距 = 26px 期望垂直空间；
  // splitNumber 是"期望段数"，实际刻度数 = splitNumber + 1
  // 夹在 2-6 之间：最少 3 个刻度（只留 0 / -50% / -100%），最多 7 个
  const hasDrawdown = data.some((item) => item.equity !== undefined);
  const drawdownSplitNumber = (() => {
    if (!hasDrawdown || chartHeight <= 0) return 5;
    const subplotHeight = chartHeight * 0.22;
    const maxTicks = Math.floor(subplotHeight / 26);
    return Math.max(2, Math.min(6, maxTicks - 1));
  })();

  // 提取时间（优先使用 formatted_time，其次是 datetime）
  const dates = data.map((item) => item.formatted_time || item.datetime || '');

  // 提取权益值
  const getEquityValue = (item: EquityData): number => {
    return item.equity !== undefined ? item.equity : 0;
  };

  // 提取存款值
  const getBalanceValue = (item: EquityData): number => {
    return item.balance !== undefined ? item.balance : 0;
  };

  // 检查数据是否包含字段（不仅检查第一个点，而是检查所有点）
  const hasEquityField = data.some(item => item.equity !== undefined);
  const hasBalanceField = data.some(item => item.balance !== undefined);

  // 提取数据
  const equityValues = data.map(getEquityValue);
  const balanceValues = data.map(getBalanceValue);

  // 水下回撤序列：相对历史峰值的百分比（口径与后端报告图一致），单点为 0
  const drawdowns: number[] = [];
  let peak = equityValues.length > 0 ? equityValues[0] : 0;
  for (const v of equityValues) {
    peak = Math.max(peak, v);
    drawdowns.push(peak > 0 ? (v / peak - 1) * 100 : 0);
  }

  // 存款基准：约定传入初始资金；未传时退化为曲线首点权益（与后端指标汇总的兜底口径一致）
  const deposit = initialCash && initialCash > 0 ? initialCash : equityValues[0];

  const minDrawdown = drawdowns.length > 0 ? Math.min(...drawdowns) : 0;

  // 计算最小值和最大值用于Y轴范围（存款线也纳入，保证基准线全程可见）
  const allValues = [...equityValues, ...balanceValues, ...(deposit > 0 ? [deposit] : [])].filter(v => v > 0);
  const minValue = allValues.length > 0 ? Math.min(...allValues) : 0;
  const maxValue = allValues.length > 0 ? Math.max(...allValues) : 100;
  const padding = (maxValue - minValue) * 0.1;

  // 构建数据系列 - 只要字段存在就显示，不管值是否相同
  const series: LineSeriesOption[] = [];

  if (hasBalanceField) {
    // 存款曲线（引擎 balance：本金 + 已实现盈亏 − 费用；持仓期间不随行情波动）
    // 净值高于它即浮盈、低于即浮亏
    series.push({
      name: '存款',
      type: 'line',
      data: balanceValues,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 1.5,
        color: qc.chartMark,
      },
      animationDuration: 1000,
      animationEasing: 'cubicOut',
    });
  } else if (deposit > 0) {
    // 旧回测结果（存储 JSON 无 balance）兜底：用初始资金画水平基准线
    series.push({
      name: '存款',
      type: 'line',
      data: data.map(() => deposit),
      smooth: false,
      symbol: 'none',
      lineStyle: {
        width: 1,
        color: qc.chartMark,
        type: 'dashed',
      },
      animationDuration: 0,
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
        color: qc.chartLine,
        type: 'dashed',
      },
      animationDuration: 1000,
      animationEasing: 'cubicOut',
    });
    // 回撤线（独立子图，红面积，横轴与上图共用同一时间序列）
    series.push({
      name: '回撤%',
      type: 'line',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: drawdowns,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 1,
        color: qc.negative,
      },
      areaStyle: {
        color: qc.negative,
        opacity: 0.25,
      },
      animationDuration: 1000,
      animationEasing: 'cubicOut',
    });
  }

  // 构建图例数据（顺序与 series 一致：存款 → 净值 → 回撤%）
  const legendData: string[] = [];
  if (hasBalanceField || deposit > 0) legendData.push('存款');
  if (hasEquityField) legendData.push('净值', '回撤%');

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
        color: qc.neutral,
      },
    },
    // 提示框
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          // 十字标签会贴在横轴/竖轴上跟随鼠标移动。用 antd Tooltip 同款配色
          // （深色底 + 浅色字）。旧写法把底色设为 colorBgElevated（亮色主题下是白色），
          // 而 ECharts 标签文字默认也是白色 → 白字白底变成"空白块"盖住坐标轴。
          backgroundColor: token.colorBgSpotlight,
          color: token.colorTextLightSolid,
          padding: [4, 8],
        },
        crossStyle: {
          color: qc.chartAxis,
        },
      },
      formatter: (params: TooltipComponentFormatterCallbackParams) => {
        const list = Array.isArray(params) ? params : [params];
        let result = `${list[0].name}<br/>`;
        list.forEach((param) => {
          result += `${param.marker || ''} ${param.seriesName}: ${Number(param.value).toFixed(2)}<br/>`;
        });
        // 净值与存款同时存在时补充浮盈（MT4 口径：净值 − 存款）
        const equityItem = list.find((param) => param.seriesName === '净值');
        const depositItem = list.find((param) => param.seriesName === '存款');
        if (equityItem && depositItem) {
          const floating = Number(equityItem.value) - Number(depositItem.value);
          result += `浮盈: ${floating.toFixed(2)}<br/>`;
        }
        return result;
      },
    },
    // 两个子图的十字光标联动：在一个子图内移动鼠标，另一个子图的竖线同步移动
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
    },
    // 网格配置：净值/存款在上图，回撤在下方独立子图；无净值数据时退化为单图
    // containLabel: true 让 ECharts 先算 Y 轴标签实际宽度再留白，自适应回撤子图 % 标签
    // 的宽度（比资金绝对值标签更宽）。用 left: '3%' 做下限，containLabel 在此基础上追加
    grid: hasDrawdown
      ? [
          { left: '3%', right: '4%', top: '14%', height: '46%', containLabel: true },
          { left: '3%', right: '4%', top: '68%', height: '22%', containLabel: true },
        ]
      : {
          left: '3%',
          right: '4%',
          bottom: '3%',
          top: '15%',
          containLabel: true,
        },
    // X轴：上下两个子图各一条，共用同一时间序列；上图隐藏刻度标签避免重复
    xAxis: hasDrawdown
      ? [
          {
            type: 'category',
            gridIndex: 0,
            boundaryGap: false,
            data: dates,
            axisLine: {
              lineStyle: {
                color: qc.chartAxis,
              },
            },
            axisLabel: {
              show: false,
            },
            splitLine: {
              show: true,
              lineStyle: {
                color: qc.chartSplit,
              },
            },
          },
          {
            type: 'category',
            gridIndex: 1,
            boundaryGap: false,
            data: dates,
            axisLine: {
              lineStyle: {
                color: qc.chartAxis,
              },
            },
            axisLabel: {
              color: qc.neutral,
              formatter: (value: string) => {
                return value.slice(0, 10);
              },
              rotate: 30,
            },
            splitLine: {
              show: true,
              lineStyle: {
                color: qc.chartSplit,
              },
            },
          },
        ]
      : {
          type: 'category',
          boundaryGap: false,
          data: dates,
          axisLine: {
            lineStyle: {
              color: qc.chartAxis,
            },
          },
          axisLabel: {
            color: qc.neutral,
            formatter: (value: string) => {
              return value.slice(0, 10);
            },
            rotate: 30,
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: qc.chartSplit,
            },
          },
        },
    // Y轴：上图资金绝对值；下图回撤百分比（max 0 让 0 贴顶，回撤恒 ≤ 0）
    yAxis: hasDrawdown
      ? [
          {
            type: 'value',
            gridIndex: 0,
            scale: true,
            min: Math.max(0, minValue - padding),
            max: maxValue + padding,
            axisLine: {
              lineStyle: {
                color: qc.chartAxis,
              },
            },
            axisLabel: {
              color: qc.neutral,
              formatter: (value: number) => value.toFixed(0),
            },
            splitLine: {
              show: true,
              lineStyle: {
                color: qc.chartSplit,
              },
            },
          },
          {
            type: 'value',
            gridIndex: 1,
            scale: true,
            max: 0,
            // 留 15% 余量，最深处不贴下边框；无回撤时给一个 -1 的可见刻度
            min: minDrawdown < 0 ? minDrawdown * 1.15 : -1,
            // splitNumber 自适应：由 ResizeObserver 测容器高度后动态计算，保证每个刻度至少 26px 垂直空间
            splitNumber: drawdownSplitNumber,
            axisLine: {
              show: false,
            },
            axisLabel: {
              color: qc.neutral,
              formatter: (value: number) => `${value.toFixed(0)}%`,
            },
            splitLine: {
              show: false,
            },
          },
        ]
      : {
          type: 'value',
          scale: true,
          min: Math.max(0, minValue - padding),
          max: maxValue + padding,
          axisLine: {
            lineStyle: {
              color: qc.chartAxis,
            },
          },
          axisLabel: {
            color: qc.neutral,
            formatter: (value: number) => value.toFixed(0),
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: qc.chartSplit,
            },
          },
        },
    // 数据系列
    series,
    // 数据缩放（仅保留内置缩放，删除下方拖拽条）；两个子图同步缩放
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
        xAxisIndex: hasDrawdown ? [0, 1] : [0],
      },
    ],
  };

  return (
    <div ref={chartWrapperRef} style={{ height, width: '100%' }}>
      <EChart
        option={option}
        style={{ height: '100%', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  );
};

export default EquityChart;
