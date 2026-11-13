/**
 * 蜡烛图类型迷你预览图标：三根竖条 + CSS 变体绘制各类型形态，
 * 不引入图片资源，颜色继承 currentColor（自动适配亮暗主题）。
 * 组件仅提供 DOM 结构，形态样式集中定义在 chart-toolbars.css。
 */
const ChartTypeIcon: React.FC<{ type: string; className?: string }> = ({ type, className }) => (
  <span className={['candle-type-icon', `candle-type-icon--${type}`, className].filter(Boolean).join(' ')} aria-hidden="true">
    <i /><i /><i />
  </span>
);

export default ChartTypeIcon;
