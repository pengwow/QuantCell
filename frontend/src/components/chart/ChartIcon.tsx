import React, { type CSSProperties } from 'react';

interface ChartIconProps {
  /** kebab-case 图标文件名（不含 .svg），对应 public/chart-icons 下的资源 */
  name: string;
  className?: string;
  style?: CSSProperties;
}

/**
 * 图表工具栏图标
 *
 * ponytail: 不内联 SVG path，改用 CSS mask 引用 public/chart-icons/*.svg。
 * 图标资源与代码解耦（可单独替换）；颜色由 background-color 控制，
 * hover / 选中 / 暗亮主题只换颜色即可，无需重复维护多份 SVG。
 */
const ChartIcon: React.FC<ChartIconProps> = ({ name, className = '', style }) => (
  <i
    className={`k-ico ${className}`.trim()}
    style={{ ...style, '--icon': `url(/chart-icons/${name}.svg)` } as CSSProperties}
  />
);

export default ChartIcon;
