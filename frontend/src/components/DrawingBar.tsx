import React, { useState, useMemo } from 'react';
import {
  LineOutlined,
  BorderOutlined,
  ColumnWidthOutlined,
  RiseOutlined,
  FallOutlined,
  ArrowsAltOutlined,
  LockOutlined,
  UnlockOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  DeleteOutlined,
  DownOutlined
} from '@ant-design/icons';
import './DrawingBar.css';

// 定义工具选项类型
interface ToolOption {
  key: string;
  text: string;
  icon: React.ReactNode;
}

// 定义组件属性类型
interface DrawingBarProps {
  onDrawingItemClick: (overlay: { name: string; lock: boolean; mode: string }) => void;
  onModeChange: (mode: string) => void;
  onLockChange: (lock: boolean) => void;
  onVisibleChange: (visible: boolean) => void;
  onRemoveClick: (groupId: string) => void;
}

// 创建工具选项的辅助函数
const createSingleLineOptions = (): ToolOption[] => [
  { key: 'horizontalStraightLine', text: '水平线', icon: <LineOutlined /> },
  { key: 'horizontalRayLine', text: '水平射线', icon: <LineOutlined /> },
  { key: 'horizontalSegment', text: '水平线段', icon: <ColumnWidthOutlined /> },
  { key: 'verticalStraightLine', text: '垂直线', icon: <LineOutlined style={{ transform: 'rotate(90deg)' }} /> },
  { key: 'straightLine', text: '直线', icon: <LineOutlined style={{ transform: 'rotate(45deg)' }} /> },
  { key: 'rayLine', text: '射线', icon: <RiseOutlined /> },
  { key: 'segment', text: '线段', icon: <ColumnWidthOutlined style={{ transform: 'rotate(45deg)' }} /> },
  { key: 'arrow', text: '箭头', icon: <FallOutlined /> },
  { key: 'priceLine', text: '价格线', icon: <LineOutlined /> }
];

const createMoreLineOptions = (): ToolOption[] => [
  { key: 'priceChannelLine', text: '价格通道线', icon: <ColumnWidthOutlined /> },
  { key: 'parallelStraightLine', text: '平行线', icon: <ColumnWidthOutlined /> }
];

const createPolygonOptions = (): ToolOption[] => [
  { key: 'circle', text: '圆形', icon: <BorderOutlined style={{ borderRadius: '50%' }} /> },
  { key: 'rect', text: '矩形', icon: <BorderOutlined /> },
  { key: 'parallelogram', text: '平行四边形', icon: <BorderOutlined style={{ transform: 'skewX(-20deg)' }} /> },
];

const createFibonacciOptions = (): ToolOption[] => [
  { key: 'fibonacciLine', text: '斐波那契线', icon: <ArrowsAltOutlined /> },
  { key: 'fibonacciSegment', text: '斐波那契线段', icon: <ArrowsAltOutlined /> },
  { key: 'fibonacciCircle', text: '斐波那契圆', icon: <BorderOutlined style={{ borderRadius: '50%' }} /> },
  { key: 'fibonacciSpiral', text: '斐波那契螺旋', icon: <ArrowsAltOutlined /> },
];

const createWaveOptions = (): ToolOption[] => [
  { key: 'xabcd', text: 'XABCD形态', icon: <RiseOutlined /> },
  { key: 'abcd', text: 'ABCD形态', icon: <FallOutlined /> },
  { key: 'threeWaves', text: '三浪', icon: <RiseOutlined /> },
  { key: 'fiveWaves', text: '五浪', icon: <FallOutlined /> },
];

const createMagnetOptions = (): ToolOption[] => [
  { key: 'weak_magnet', text: '弱磁吸', icon: <ArrowsAltOutlined /> },
  { key: 'strong_magnet', text: '强磁吸', icon: <ArrowsAltOutlined /> }
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
  const [, setModeIcon] = useState<string>('weak_magnet');
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

  // 获取当前显示的工具图标
  const getCurrentToolIcon = (key: string) => {
    const tool = overlays.find(o => o.key === key);
    if (tool) {
      const option = tool.list.find(l => l.key === tool.icon);
      return option?.icon || <LineOutlined />;
    }
    return <LineOutlined />;
  };

  return (
    <div className="drawing-bar">
      {overlays.map(item => (
        <div
          key={item.key}
          className="drawing-bar-item"
          tabIndex={0}
          onBlur={() => setPopoverKey('')}
        >
          <div
            className="drawing-bar-icon-container"
            onClick={() => {
              if (item.key === popoverKey) {
                setPopoverKey('');
              } else {
                setPopoverKey(item.key);
              }
            }}
          >
            <span className="drawing-bar-icon">
              {getCurrentToolIcon(item.key)}
            </span>
            <span className="drawing-bar-arrow">
              <DownOutlined className={item.key === popoverKey ? 'rotate' : ''} />
            </span>
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
                  {data.icon}
                  <span className="drawing-bar-item-text">{data.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {/* 模式选择 */}
      <div
        className="drawing-bar-item"
        tabIndex={0}
        onBlur={() => setPopoverKey('')}
      >
        <div
          className="drawing-bar-icon-container"
          onClick={() => {
            if (popoverKey === 'mode') {
              setPopoverKey('');
            } else {
              setPopoverKey('mode');
            }
          }}
        >
          <span className="drawing-bar-icon">
            <ArrowsAltOutlined />
          </span>
          <span className="drawing-bar-arrow">
            <DownOutlined className={popoverKey === 'mode' ? 'rotate' : ''} />
          </span>
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
                {data.icon}
                <span className="drawing-bar-item-text">{data.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <span className="drawing-bar-split" />

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
          {lock ? <LockOutlined /> : <UnlockOutlined />}
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
          {visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
        </span>
      </div>

      <span className="drawing-bar-split" />

      {/* 删除按钮 */}
      <div className="drawing-bar-item">
        <span
          className="drawing-bar-icon"
          onClick={() => onRemoveClick(GROUP_ID)}
        >
          <DeleteOutlined />
        </span>
      </div>
    </div>
  );
};

export default DrawingBar;
