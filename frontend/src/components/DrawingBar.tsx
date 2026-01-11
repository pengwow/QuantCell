import React, { useState, useMemo } from 'react';
import './DrawingBar.css';

// 定义工具选项类型
interface ToolOption {
  key: string;
  text: string;
}

// 定义组件属性类型
interface DrawingBarProps {
  onDrawingItemClick: (overlay: { name: string; lock: boolean; mode: string; groupId?: string }) => void;
  onModeChange: (mode: string) => void;
  onLockChange: (lock: boolean) => void;
  onVisibleChange: (visible: boolean) => void;
  onRemoveClick: (groupId: string) => void;
}

// 图标组件映射表
const iconComponents: Record<string, React.FC<{ className?: string }>> = {
  // 单线工具图标
  horizontalStraightLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 11H19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  horizontalRayLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 11H11L11 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  horizontalSegment: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M5 11H17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="5" cy="11" r="2" fill="currentColor" />
      <circle cx="17" cy="11" r="2" fill="currentColor" />
    </svg>
  ),
  verticalStraightLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M11 3V19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  verticalRayLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M11 3V11L9 11L13 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  verticalSegment: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M11 5V17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="11" cy="5" r="2" fill="currentColor" />
      <circle cx="11" cy="17" r="2" fill="currentColor" />
    </svg>
  ),
  straightLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 19L19 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  rayLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 3L11 11L13 9L15 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  segment: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M5 17L17 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="5" cy="17" r="2" fill="currentColor" />
      <circle cx="17" cy="5" r="2" fill="currentColor" />
    </svg>
  ),
  arrow: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M5 5L15 15L12 12L15 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  // 多线工具图标
  priceChannelLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 19L11 11L19 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M3 5L11 13L19 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  parallelStraightLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 5L17 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 17L19 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  // 多边形工具图标
  circle: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  ),
  triangle: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M11 3L19 17H3L11 3Z" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round" />
    </svg>
  ),
  rect: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <rect x="3" y="5" width="16" height="12" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round" />
    </svg>
  ),
  parallelogram: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 5L15 5L19 17L7 17L3 5Z" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round" />
    </svg>
  ),
  // 斐波那契工具图标
  fibonacciLine: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 19L11 9L19 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 9V19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  fibonacciSegment: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 19L11 9L19 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  fibonacciCircle: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="5" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="3" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  ),
  fibonacciSpiral: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M11 3A8 8 0 0 1 19 11" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="M11 3A5 5 0 0 0 6 11" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  ),
  fibonacciSpeedResistanceFan: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M11 3L11 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 3L19 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 3L5 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  fibonacciExtension: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 5L11 13L19 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 13L19 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 13L3 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  gannBox: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <rect x="3" y="3" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round" />
      <line x1="11" y1="3" x2="11" y2="19" stroke="currentColor" strokeWidth="2" />
      <line x1="3" y1="11" x2="19" y2="11" stroke="currentColor" strokeWidth="2" />
      <line x1="3" y1="3" x2="19" y2="19" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
  // 波浪工具图标
  threeWaves: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 15L7 9L11 15L15 9L19 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  fiveWaves: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 15L5 9L7 15L9 9L11 15L13 9L15 15L17 9L19 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  eightWaves: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 15L4 9L5 15L6 9L7 15L8 9L9 15L10 9L11 15L12 9L13 15L14 9L15 15L16 9L17 15L18 9L19 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  anyWaves: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 11C3 7 6 4 10 4C14 4 17 7 17 11C17 15 14 18 10 18C6 18 3 15 3 11Z" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  ),
  abcd: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 5L7 11L11 5L15 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  xabcd: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M3 5L7 11L11 5L15 11L11 17L7 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  // 模式图标
  weak_magnet: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="5" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="2" fill="currentColor" />
    </svg>
  ),
  strong_magnet: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <circle cx="11" cy="11" r="9" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="6" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="3" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="2" fill="currentColor" />
    </svg>
  ),
  // 其他图标
  lock: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <rect x="5" y="8" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="M8 8V6C8 4.9 8.9 4 10 4H12C13.1 4 14 4.9 14 6V8" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
  unlock: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <rect x="5" y="8" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="M14 8V6C14 4.9 13.1 4 12 4H10C8.9 4 8 4.9 8 6V8" stroke="currentColor" strokeWidth="2" />
      <path d="M3 11L7 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  visible: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="11" cy="11" r="3" fill="currentColor" />
      <line x1="1" y1="1" x2="5" y2="5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <line x1="17" y1="17" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  invisible: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <path d="M1 1L21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M1 21L21 1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 15C5 12 7 10 11 10C15 10 17 12 17 15" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  ),
  remove: ({ className }) => (
    <svg className={className} width="20" height="20" viewBox="0 0 22 22" fill="none">
      <line x1="5" y1="5" x2="17" y2="17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <line x1="17" y1="5" x2="5" y2="17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
};

// 根据名称获取对应的图标组件
const Icon: React.FC<{ className?: string; name: string }> = ({ className, name }) => {
  const IconComponent = iconComponents[name] || iconComponents.straightLine;
  return <IconComponent className={className} />;
};

// 创建工具选项的辅助函数
const createSingleLineOptions = (): ToolOption[] => [
  { key: 'horizontalStraightLine', text: '水平线' },
  { key: 'horizontalRayLine', text: '水平射线' },
  { key: 'horizontalSegment', text: '水平线段' },
  { key: 'verticalStraightLine', text: '垂直线' },
  { key: 'verticalRayLine', text: '垂直射线' },
  { key: 'verticalSegment', text: '垂直线段' },
  { key: 'straightLine', text: '直线' },
  { key: 'rayLine', text: '射线' },
  { key: 'segment', text: '线段' },
  { key: 'arrow', text: '箭头' },
  { key: 'priceLine', text: '价格线' }
];

const createMoreLineOptions = (): ToolOption[] => [
  { key: 'priceChannelLine', text: '价格通道线' },
  { key: 'parallelStraightLine', text: '平行线' }
];

const createPolygonOptions = (): ToolOption[] => [
  { key: 'circle', text: '圆形' },
  { key: 'rect', text: '矩形' },
  { key: 'parallelogram', text: '平行四边形' },
  { key: 'triangle', text: '三角形' }
];

const createFibonacciOptions = (): ToolOption[] => [
  { key: 'fibonacciLine', text: '斐波那契线' },
  { key: 'fibonacciSegment', text: '斐波那契线段' },
  { key: 'fibonacciCircle', text: '斐波那契圆' },
  { key: 'fibonacciSpiral', text: '斐波那契螺旋' },
  { key: 'fibonacciSpeedResistanceFan', text: '斐波那契速度阻力扇' },
  { key: 'fibonacciExtension', text: '斐波那契扩展' },
  { key: 'gannBox', text: '江恩箱' }
];

const createWaveOptions = (): ToolOption[] => [
  { key: 'xabcd', text: 'XABCD形态' },
  { key: 'abcd', text: 'ABCD形态' },
  { key: 'threeWaves', text: '三浪' },
  { key: 'fiveWaves', text: '五浪' },
  { key: 'eightWaves', text: '八浪' },
  { key: 'anyWaves', text: '任意浪' }
];

const createMagnetOptions = (): ToolOption[] => [
  { key: 'weak_magnet', text: '弱磁吸' },
  { key: 'strong_magnet', text: '强磁吸' }
];

const GROUP_ID = 'drawing_tools';

const DrawingBar: React.FC<DrawingBarProps> = ({
  onDrawingItemClick,
  onModeChange,
  onLockChange,
  onVisibleChange,
  onRemoveClick
}) => {
  // 工具图标状态
  const [singleLineIcon, setSingleLineIcon] = useState<string>('horizontalStraightLine');
  const [moreLineIcon, setMoreLineIcon] = useState<string>('priceChannelLine');
  const [polygonIcon, setPolygonIcon] = useState<string>('circle');
  const [fibonacciIcon, setFibonacciIcon] = useState<string>('fibonacciLine');
  const [waveIcon, setWaveIcon] = useState<string>('xabcd');
  
  // 模式状态
  const [modeIcon, setModeIcon] = useState<string>('weak_magnet');
  const [mode, setMode] = useState<string>('normal');
  
  // 锁定和可见性状态
  const [lock, setLock] = useState<boolean>(false);
  const [visible, setVisible] = useState<boolean>(true);
  
  // 弹出菜单状态
  const [popoverKey, setPopoverKey] = useState<string>('');
  
  // 工具分组配置
  const overlays = useMemo(() => [
    { 
      key: 'singleLine', 
      icon: singleLineIcon, 
      list: createSingleLineOptions(), 
      setter: setSingleLineIcon 
    },
    { 
      key: 'moreLine', 
      icon: moreLineIcon, 
      list: createMoreLineOptions(), 
      setter: setMoreLineIcon 
    },
    { 
      key: 'polygon', 
      icon: polygonIcon, 
      list: createPolygonOptions(), 
      setter: setPolygonIcon 
    },
    { 
      key: 'fibonacci', 
      icon: fibonacciIcon, 
      list: createFibonacciOptions(), 
      setter: setFibonacciIcon 
    },
    { 
      key: 'wave', 
      icon: waveIcon, 
      list: createWaveOptions(), 
      setter: setWaveIcon 
    }
  ], [singleLineIcon, moreLineIcon, polygonIcon, fibonacciIcon, waveIcon]);
  
  const modes = useMemo(() => createMagnetOptions(), []);
  
  return (
    <div className="drawing-bar">
      {overlays.map(item => (
        <div 
          key={item.key}
          className="drawing-bar-item"
          tabIndex={0}
          onBlur={() => setPopoverKey('')}
        >
          <span 
            className="drawing-bar-icon"
            onClick={() => {
              onDrawingItemClick({
                groupId: GROUP_ID,
                name: item.icon,
                lock,
                mode
              });
            }}
          >
            <Icon name={item.icon} />
          </span>
          <div 
            className="drawing-bar-arrow"
            onClick={() => {
              if (item.key === popoverKey) {
                setPopoverKey('');
              } else {
                setPopoverKey(item.key);
              }
            }}
          >
            <svg 
              className={item.key === popoverKey ? 'rotate' : ''}
              viewBox="0 0 4 6"
              width="4" 
              height="6"
            >
              <path d="M1.07298,0.159458C0.827521,-0.0531526,0.429553,-0.0531526,0.184094,0.159458C-0.0613648,0.372068,-0.0613648,0.716778,0.184094,0.929388L2.61275,3.03303L0.260362,5.07061C0.0149035,5.28322,0.0149035,5.62793,0.260362,5.84054C0.505822,6.05315,0.903789,6.05315,1.14925,5.84054L3.81591,3.53075C4.01812,3.3556,4.05374,3.0908,3.92279,2.88406C3.93219,2.73496,3.87113,2.58315,3.73964,2.46925L1.07298,0.159458Z" 
                stroke="none" 
                strokeOpacity="0"
                fill="currentColor"
              />
            </svg>
          </div>
          {item.key === popoverKey && (
            <ul className="drawing-bar-list">
              {item.list.map(data => (
                <li 
                  key={data.key}
                  onClick={() => {
                    item.setter(data.key);
                    onDrawingItemClick({ 
                      name: data.key, 
                      lock, 
                      mode 
                    });
                    setPopoverKey('');
                  }}
                >
                  <Icon name={data.key} />
                  <span className="drawing-bar-item-text">{data.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      
      <span className="drawing-bar-split" />
      
      {/* 模式选择 */}
      <div 
        className="drawing-bar-item"
        tabIndex={0}
        onBlur={() => setPopoverKey('')}
      >
        <span 
          className="drawing-bar-icon"
          onClick={() => {
            let currentMode = modeIcon;
            if (mode !== 'normal') {
              currentMode = 'normal';
            }
            setMode(currentMode);
            onModeChange(currentMode);
          }}
        >
          {modeIcon === 'weak_magnet' 
            ? (mode === 'weak_magnet' ? <Icon name="weak_magnet" className="selected" /> : <Icon name="weak_magnet" />) 
            : (mode === 'strong_magnet' ? <Icon name="strong_magnet" className="selected" /> : <Icon name="strong_magnet" />)
          }
        </span>
        <div 
          className="drawing-bar-arrow"
          onClick={() => {
            if (popoverKey === 'mode') {
              setPopoverKey('');
            } else {
              setPopoverKey('mode');
            }
          }}
        >
          <svg 
            className={popoverKey === 'mode' ? 'rotate' : ''}
            viewBox="0 0 4 6"
            width="4" 
            height="6"
          >
            <path d="M1.07298,0.159458C0.827521,-0.0531526,0.429553,-0.0531526,0.184094,0.159458C-0.0613648,0.372068,-0.0613648,0.716778,0.184094,0.929388L2.61275,3.03303L0.260362,5.07061C0.0149035,5.28322,0.0149035,5.62793,0.260362,5.84054C0.505822,6.05315,0.903789,6.05315,1.14925,5.84054L3.81591,3.53075C4.01812,3.3556,4.05374,3.0908,3.92279,2.88406C3.93219,2.73496,3.87113,2.58315,3.73964,2.46925L1.07298,0.159458Z" 
              stroke="none" 
              strokeOpacity="0"
              fill="currentColor"
            />
          </svg>
        </div>
        {popoverKey === 'mode' && (
          <ul className="drawing-bar-list">
            {modes.map(data => (
              <li 
                key={data.key}
                onClick={() => {
                  setModeIcon(data.key);
                  setMode(data.key);
                  onModeChange(data.key);
                  setPopoverKey('');
                }}
              >
                <Icon name={data.key} />
                <span className="drawing-bar-item-text">{data.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      
      {/* 锁定按钮 */}
      <div className="drawing-bar-item">
        <span 
          className="drawing-bar-icon"
          onClick={() => {
            const currentLock = !lock;
            setLock(currentLock);
            onLockChange(currentLock);
          }}
        >
          {lock ? <Icon name="lock" /> : <Icon name="unlock" />}
        </span>
      </div>
      
      {/* 可见性按钮 */}
      <div className="drawing-bar-item">
        <span 
          className="drawing-bar-icon"
          onClick={() => {
            const newVisible = !visible;
            setVisible(newVisible);
            onVisibleChange(newVisible);
          }}
        >
          {visible ? <Icon name="visible" /> : <Icon name="invisible" />}
        </span>
      </div>
      
      <span className="drawing-bar-split" />
      
      {/* 删除按钮 */}
      <div className="drawing-bar-item">
        <span 
          className="drawing-bar-icon"
          onClick={() => onRemoveClick(GROUP_ID)}
        >
          <Icon name="remove" />
        </span>
      </div>
    </div>
  );
};

export default DrawingBar;