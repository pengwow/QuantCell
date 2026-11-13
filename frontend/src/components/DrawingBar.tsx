import React, { useState } from 'react';
import ChartIcon from './chart/ChartIcon';
import './chart/chart-toolbars.css';

interface OverlayOption {
  /** klinecharts 的 overlay 名称 */
  name: string;
  label: string;
}

interface OverlayGroup {
  key: string;
  /** 分组默认展示的工具（对应 pro 各分组的默认图标） */
  defaultName: string;
  options: OverlayOption[];
}

// 绘图工具分组：名称与 klinecharts 内置 / QuantCell 自定义扩展的 overlay 名一致
const OVERLAY_GROUPS: OverlayGroup[] = [
  {
    key: 'singleLine',
    defaultName: 'horizontalStraightLine',
    options: [
      { name: 'horizontalStraightLine', label: '水平线' },
      { name: 'horizontalRayLine', label: '水平射线' },
      { name: 'horizontalSegment', label: '水平线段' },
      { name: 'verticalStraightLine', label: '垂直线' },
      { name: 'verticalRayLine', label: '垂直射线' },
      { name: 'verticalSegment', label: '垂直线段' },
      { name: 'straightLine', label: '直线' },
      { name: 'rayLine', label: '射线' },
      { name: 'segment', label: '线段' },
      { name: 'arrow', label: '箭头' },
      { name: 'priceLine', label: '价格线' },
    ],
  },
  {
    key: 'moreLine',
    defaultName: 'priceChannelLine',
    options: [
      { name: 'priceChannelLine', label: '价格通道线' },
      { name: 'parallelStraightLine', label: '平行直线' },
    ],
  },
  {
    key: 'polygon',
    defaultName: 'circle',
    options: [
      { name: 'circle', label: '圆' },
      { name: 'rect', label: '矩形' },
      { name: 'parallelogram', label: '平行四边形' },
      { name: 'triangle', label: '三角形' },
    ],
  },
  {
    key: 'fibonacci',
    defaultName: 'fibonacciLine',
    options: [
      { name: 'fibonacciLine', label: '斐波那契线' },
      { name: 'fibonacciSegment', label: '斐波那契线段' },
      { name: 'fibonacciCircle', label: '斐波那契圆' },
      { name: 'fibonacciSpiral', label: '斐波那契螺旋' },
      { name: 'fibonacciSpeedResistanceFan', label: '斐波那契速度阻力扇' },
      { name: 'fibonacciExtension', label: '斐波那契扩展' },
      { name: 'gannBox', label: '甘氏箱' },
    ],
  },
  {
    key: 'wave',
    defaultName: 'xabcd',
    options: [
      { name: 'xabcd', label: 'XABCD' },
      { name: 'abcd', label: 'ABCD' },
      { name: 'threeWaves', label: '三浪' },
      { name: 'fiveWaves', label: '五浪' },
      { name: 'eightWaves', label: '八浪' },
      { name: 'anyWaves', label: '任意浪' },
    ],
  },
];

const MAGNET_OPTIONS: OverlayOption[] = [
  { name: 'weak_magnet', label: '弱磁吸' },
  { name: 'strong_magnet', label: '强磁吸' },
];

const GROUP_ID = 'drawing_tools';

/** overlay 名（camelCase / snake_case）→ public/chart-icons 下的 kebab-case 文件名 */
const iconNameOf = (overlayName: string): string =>
  overlayName
    .replace(/_/g, '-')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .toLowerCase();

// 定义组件属性类型
interface DrawingBarProps {
  onDrawingItemClick: (overlay: { name: string; lock: boolean; mode: string }) => void;
  onModeChange: (mode: string) => void;
  onLockChange: (lock: boolean) => void;
  onVisibleChange: (visible: boolean) => void;
  onRemoveClick: (groupId: string) => void;
}

/**
 * 左侧绘图工具栏：复刻 klinecharts-pro 的 drawing-bar
 * 5 个绘图分组 + 磁吸模式 + 锁定/显示 + 全部清除。
 * 行为：划线分组的整行（含主图标）点击展开/收起浮层列表，选中子工具即发起
 * 绘制并更新主图标（无选中态）；磁吸主图标在 normal 与上次磁吸模式之间循环，
 * 右侧箭头展开磁吸选项。
 */
const DrawingBar: React.FC<DrawingBarProps> = ({
  onDrawingItemClick,
  onModeChange,
  onLockChange,
  onVisibleChange,
  onRemoveClick,
}) => {
  // 各分组当前展示的工具名
  const [toolIcons, setToolIcons] = useState<Record<string, string>>(() =>
    Object.fromEntries(OVERLAY_GROUPS.map((group) => [group.key, group.defaultName])),
  );
  const [modeIcon, setModeIcon] = useState('weak_magnet');
  const [mode, setMode] = useState('normal');
  const [lock, setLock] = useState(false);
  const [visible, setVisible] = useState(true);
  // 当前展开浮层的分组 key（'' 表示全部收起）
  const [popoverKey, setPopoverKey] = useState('');

  const renderArrow = (groupKey: string, interactive = true) => (
    <div
      className="icon-arrow"
      // interactive=false：展开命中区已扩大到整个 item，箭头不再单独处理点击
      onClick={
        interactive
          ? () => setPopoverKey((prev) => (prev === groupKey ? '' : groupKey))
          : undefined
      }
    >
      <svg className={popoverKey === groupKey ? 'rotate' : ''} viewBox="0 0 4 6">
        <path d="M1.07298,0.159458C0.827521,-0.0531526,0.429553,-0.0531526,0.184094,0.159458C-0.0613648,0.372068,-0.0613648,0.716778,0.184094,0.929388L2.61275,3.03303L0.260362,5.07061C0.0149035,5.28322,0.0149035,5.62793,0.260362,5.84054C0.505822,6.05315,0.903789,6.05315,1.14925,5.84054L3.81591,3.53075C4.01812,3.3556,4.05374,3.0908,3.92279,2.88406C3.93219,2.73496,3.87113,2.58315,3.73964,2.46925L1.07298,0.159458Z" />
      </svg>
    </div>
  );

  return (
    <div className="drawing-bar">
      {OVERLAY_GROUPS.map((group) => {
        const currentName = toolIcons[group.key];
        return (
          <div
            key={group.key}
            className="item"
            tabIndex={0}
            onBlur={() => setPopoverKey('')}
            // 点击整行（含主图标）展开/收起子工具浮层；主图标不再直接发起绘制，
            // 绘制统一由浮层内选中子工具触发
            onClick={() => setPopoverKey((prev) => (prev === group.key ? '' : group.key))}
          >
            <span className="d-hit">
              <ChartIcon name={iconNameOf(currentName)} className="d-ico" />
            </span>
            {renderArrow(group.key, false)}
            {popoverKey === group.key && (
              <ul className="k-list">
                {group.options.map((option) => (
                  <li
                    key={option.name}
                    onClick={(e) => {
                      // 阻止冒泡：li 置空 popoverKey 后若再冒泡，item 的 toggle 会立即把浮层重新展开
                      e.stopPropagation();
                      setToolIcons((prev) => ({ ...prev, [group.key]: option.name }));
                      onDrawingItemClick({ name: option.name, lock, mode });
                      setPopoverKey('');
                    }}
                  >
                    <span className="d-hit">
                      <ChartIcon name={iconNameOf(option.name)} className="d-ico" />
                    </span>
                    <span className="lbl">{option.label}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}

      <span className="split-line" />

      {/* 磁吸模式：主图标在 normal 与上次磁吸模式间循环 */}
      <div className="item" tabIndex={0} onBlur={() => setPopoverKey('')}>
        <span
          className={`d-hit${mode === modeIcon ? ' selected' : ''}`}
          onClick={() => {
            const next = mode === 'normal' ? modeIcon : 'normal';
            setMode(next);
            onModeChange(next);
          }}
        >
          <ChartIcon name={iconNameOf(modeIcon)} className="d-ico" />
        </span>
        {renderArrow('mode')}
        {popoverKey === 'mode' && (
          <ul className="k-list">
            {MAGNET_OPTIONS.map((option) => (
              <li
                key={option.name}
                onClick={() => {
                  setModeIcon(option.name);
                  setMode(option.name);
                  onModeChange(option.name);
                  setPopoverKey('');
                }}
              >
                <span className="d-hit">
                  <ChartIcon name={iconNameOf(option.name)} className="d-ico" />
                </span>
                <span className="lbl">{option.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 锁定 / 隐藏：点击互切图标 */}
      <div className="item">
        <span
          className="d-hit"
          onClick={() => {
            const next = !lock;
            setLock(next);
            onLockChange(next);
          }}
        >
          <ChartIcon name={lock ? 'lock' : 'unlock'} className="d-ico" />
        </span>
      </div>
      <div className="item">
        <span
          className="d-hit"
          onClick={() => {
            const next = !visible;
            setVisible(next);
            onVisibleChange(next);
          }}
        >
          <ChartIcon name={visible ? 'visible' : 'invisible'} className="d-ico" />
        </span>
      </div>

      <span className="split-line" />

      {/* 清除全部绘图 */}
      <div className="item">
        <span className="d-hit" onClick={() => onRemoveClick(GROUP_ID)}>
          <ChartIcon name="remove" className="d-ico" />
        </span>
      </div>
    </div>
  );
};

export default DrawingBar;
