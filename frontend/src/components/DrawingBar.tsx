import React, { useState } from 'react';
import { Tooltip } from 'antd';
import { DRAWING_TOOL_ICONS } from './icons/drawingToolIcons';
import './DrawingBar.css';

export interface DrawingTool {
  key: string;  // overlay name，createOverlay 直接使用
  text: string; // 工具中文名
}

// QuantDinger 工具栏的单列 14 工具（顺序与 QuantDinger 一致）
export const DRAWING_TOOLS: DrawingTool[] = [
  { key: 'segment', text: '线段' },
  { key: 'horizontalStraightLine', text: '水平线' },
  { key: 'horizontalRayLine', text: '水平射线' },
  { key: 'horizontalSegment', text: '水平线段' },
  { key: 'verticalStraightLine', text: '垂直线' },
  { key: 'rayLine', text: '射线' },
  { key: 'arrow', text: '箭头' },
  { key: 'straightLine', text: '直线' },
  { key: 'measure', text: '涨跌测量' },
  { key: 'parallelStraightLine', text: '平行线' },
  { key: 'rect', text: '矩形' },
  { key: 'priceLine', text: '价格线' },
  { key: 'priceChannelLine', text: '价格通道线' },
  { key: 'fibonacciLine', text: '斐波那契线' }
];

export interface DrawingBarProps {
  onSelect: (tool: string) => void; // 选中工具 → ChartPage createOverlay(tool)
  onDeselect: () => void;           // 二次点击 → ChartPage 移除进行中的 overlay
  onClearAll: () => void;           // 清除全部图形
}

/**
 * QuantDinger 风格左侧绘图工具栏：
 * 点击进入绘制（激活高亮），二次点击取消，右侧 tooltip。
 * klinecharts 无绘制完成回调，激活态保持到再次点击/切换工具/清除——与 QuantDinger 一致。
 */
const DrawingBar: React.FC<DrawingBarProps> = ({ onSelect, onDeselect, onClearAll }) => {
  const [activeTool, setActiveTool] = useState<string | null>(null);

  const handleClick = (tool: string) => {
    if (activeTool === tool) {
      setActiveTool(null);
      onDeselect();
    } else {
      setActiveTool(tool);
      onSelect(tool);
    }
  };

  const handleClear = () => {
    setActiveTool(null);
    onClearAll();
  };

  return (
    <div className="drawing-bar">
      {DRAWING_TOOLS.map(tool => (
        <Tooltip key={tool.key} placement="right" title={tool.text}>
          <button
            type="button"
            className={`drawing-tool-btn${activeTool === tool.key ? ' active' : ''}`}
            aria-label={tool.text}
            aria-pressed={activeTool === tool.key}
            onClick={() => handleClick(tool.key)}
          >
            {DRAWING_TOOL_ICONS[tool.key]}
          </button>
        </Tooltip>
      ))}
      <span className="drawing-tool-divider" />
      <Tooltip placement="right" title="清除全部">
        <button
          type="button"
          className="drawing-tool-btn"
          aria-label="清除全部"
          onClick={handleClear}
        >
          {DRAWING_TOOL_ICONS.clear}
        </button>
      </Tooltip>
    </div>
  );
};

export default DrawingBar;
